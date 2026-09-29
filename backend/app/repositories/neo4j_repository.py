from app.core.neo4j import get_driver
from app.models.neo4j_models import SCHEMA_STATEMENTS


async def ensure_learner(user_id: str) -> None:
    """Neo4j only stores the user_id; identity stays in MongoDB."""
    async with get_driver().session() as s:
        await s.run("MERGE (:Learner {user_id: $uid})", uid=user_id)


async def ping() -> bool:
    async with get_driver().session() as s:
        res = await s.run("RETURN 1 AS ok")
        return (await res.single())["ok"] == 1


async def init_schema() -> None:
    async with get_driver().session() as s:
        for stmt in SCHEMA_STATEMENTS:
            await s.run(stmt)


async def save_curriculum_graph(p: dict) -> None:
    """Write the whole approved curriculum graph in one transaction. Idempotent (MERGE by id)."""
    async def work(tx):
        await tx.run(
            "MERGE (c:Course {id: $id}) SET c.owner_id=$owner_id, c.name=$name, c.code=$code, "
            "c.version=$version, c.credit_hours=$credit_hours, c.semester=$semester", **p["course"])
        cid = p["course"]["id"]
        await tx.run(
            "UNWIND $rows AS r MATCH (c:Course {id:$cid}) MERGE (u:Unit {id:r.id}) "
            "SET u.title=r.title, u.order=r.order, u.hours=r.hours, u.weeks=r.weeks MERGE (c)-[:HAS_UNIT]->(u)",
            rows=p["units"], cid=cid)
        await tx.run(
            "UNWIND $rows AS r MATCH (u:Unit {id:r.unit_id}) MERGE (t:Topic {id:r.id}) "
            "SET t.title=r.title, t.order=r.order, t.subtopics=r.subtopics, t.embedding=r.embedding "
            "MERGE (u)-[:HAS_TOPIC]->(t)", rows=p["topics"])
        await tx.run(
            "UNWIND $rows AS r MATCH (c:Course {id:$cid}) MERGE (o:Outcome {id:r.id}) SET o.text=r.text "
            "MERGE (c)-[:HAS_OUTCOME]->(o)", rows=p["outcomes"], cid=cid)
        await tx.run(
            "UNWIND $rows AS r MERGE (k:Concept {id:r.id}) SET k.key=r.key, k.name=r.name, "
            "k.description=r.description, k.difficulty=r.difficulty, k.estimated_minutes=r.estimated_minutes, "
            "k.unit=r.unit, k.course_id=$cid, k.embedding=r.embedding "
            "WITH k, r OPTIONAL MATCH (t:Topic {id:r.topic_id}) "
            "FOREACH (_ IN CASE WHEN t IS NULL THEN [] ELSE [1] END | "
            "MERGE (t)-[:HAS_CONCEPT]->(k) MERGE (k)-[:PART_OF]->(t))", rows=p["concepts"], cid=cid)
        await tx.run(
            "UNWIND $rows AS r MATCH (k:Concept {id:r.concept_id}), (o:Outcome {id:r.outcome_id}) "
            "MERGE (k)-[:ALIGNS_WITH]->(o)", rows=p["aligns"])
        await tx.run(
            "UNWIND $rows AS r MATCH (a:Concept {id:r.source}), (b:Concept {id:r.target}) "
            "MERGE (a)-[e:PREREQUISITE_OF]->(b) SET e.confidence=r.confidence, e.evidence=r.evidence",
            rows=p["prereqs"])
        await tx.run(
            "UNWIND $rows AS r MATCH (a:Concept {id:r.source}), (b:Concept {id:r.target}) "
            "MERGE (a)-[e:RELATED_TO]->(b) SET e.confidence=r.confidence, e.evidence=r.evidence",
            rows=p["related"])

    async with get_driver().session() as s:
        await s.execute_write(work)


async def get_knowledge_graph(course_id: str, owner_id: str) -> dict | None:
    async with get_driver().session() as s:
        course = await (await s.run(
            "MATCH (c:Course {id:$id, owner_id:$owner}) RETURN c{.id,.name,.code,.version,.semester} AS c",
            id=course_id, owner=owner_id)).single()
        if not course:
            return None
        concepts = await (await s.run(
            "MATCH (k:Concept {course_id:$id}) "
            "OPTIONAL MATCH (k)-[:PART_OF]->(t:Topic) "
            "OPTIONAL MATCH (k)-[:ALIGNS_WITH]->(o:Outcome) "
            "OPTIONAL MATCH (r:Resource)-[cv:COVERS]->(k) "
            "RETURN k{.id,.name,.description,.difficulty,.estimated_minutes,.unit} AS concept, t.title AS topic, "
            "collect(DISTINCT o.text) AS outcomes, "
            "collect(DISTINCT CASE WHEN r IS NULL THEN null ELSE {title:r.title, url:r.url, coverage:cv.coverage_score} END) AS resources "
            "ORDER BY concept.name", id=course_id)).data()
        rels = await (await s.run(
            "MATCH (a:Concept {course_id:$id})-[e:PREREQUISITE_OF|RELATED_TO]->(b:Concept) "
            "RETURN a.id AS source, b.id AS target, type(e) AS type, e.confidence AS confidence, "
            "e.evidence AS evidence", id=course_id)).data()
    return {"course": course["c"], "concepts": concepts, "relationships": rels}


async def similar_concepts(embedding: list[float], k: int = 5) -> list[dict]:
    """Neo4j vector search over concept embeddings."""
    async with get_driver().session() as s:
        return await (await s.run(
            "CALL db.index.vector.queryNodes('concept_embedding', $k, $emb) YIELD node, score "
            "RETURN node.id AS id, node.name AS name, score", k=k, emb=embedding)).data()


async def save_sequence(course_id: str, owner_id: str, structure: list[dict]) -> None:
    """Store the approved semester plan: Semester/Week nodes and Concept -[:IN_SEMESTER|IN_WEEK]-> links."""
    rows = [{"sid": f"{course_id}:s{s['semester']}", "semester": s["semester"],
             "wid": f"{course_id}:s{s['semester']}:w{w['week']}", "week": w["week"],
             "concepts": [f"{course_id}:{c}" for c in w["concepts"]]}
            for s in structure for w in s["weeks"]]

    async def work(tx):
        # replace any previous plan for this course
        await tx.run("MATCH (c:Course {id:$cid, owner_id:$owner}) "
                     "OPTIONAL MATCH (s:Semester {course_id:$cid}) DETACH DELETE s", cid=course_id, owner=owner_id)
        await tx.run("MATCH (w:Week {course_id:$cid}) DETACH DELETE w", cid=course_id)
        await tx.run(
            "UNWIND $rows AS r "
            "MERGE (s:Semester {id:r.sid}) SET s.number=r.semester, s.course_id=$cid "
            "MERGE (w:Week {id:r.wid}) SET w.number=r.week, w.course_id=$cid "
            "MERGE (w)-[:IN_SEMESTER]->(s) "
            "WITH r, s, w UNWIND r.concepts AS kid MATCH (k:Concept {id:kid}) "
            "MERGE (k)-[:IN_SEMESTER]->(s) MERGE (k)-[:IN_WEEK]->(w)", rows=rows, cid=course_id)

    async with get_driver().session() as s:
        await s.execute_write(work)


# ------------------------------------------------------------------ resources
async def course_concepts(course_id: str, owner_id: str, ids: list[str] | None = None) -> list[dict]:
    async with get_driver().session() as s:
        return await (await s.run(
            "MATCH (:Course {id:$cid, owner_id:$owner})-[:HAS_UNIT]->(:Unit)-[:HAS_TOPIC]->(:Topic)-[:HAS_CONCEPT]->(k:Concept) "
            "WHERE $ids IS NULL OR k.id IN $ids "
            "RETURN k.id AS id, k.name AS name, k.description AS description, k.difficulty AS difficulty, "
            "k.estimated_minutes AS estimated_minutes, k.embedding AS embedding ORDER BY k.name",
            cid=course_id, owner=owner_id, ids=ids)).data()


async def upsert_resources(rows: list[dict]) -> None:
    if not rows:
        return
    async def work(tx):  # managed transaction: the driver retries transient connection failures
        await tx.run(
            "UNWIND $rows AS r MERGE (x:Resource {id:r.id}) "
            "SET x.title=r.title, x.url=r.url, x.source=r.source, x.author=r.author, x.description=r.description, "
            "x.duration_minutes=r.duration_minutes, x.published_at=r.published_at, x.difficulty=r.difficulty, "
            "x.version_hint=r.version_hint, x.warnings=r.warnings, x.has_transcript=r.has_transcript, "
            "x.text=r.text, x.embedding=r.embedding", rows=rows)
    async with get_driver().session() as s:
        await s.execute_write(work)


async def vector_resources(embedding: list[float], k: int = 15) -> list[dict]:
    """Neo4j vector search over resource embeddings."""
    async with get_driver().session() as s:
        return await (await s.run(
            "CALL db.index.vector.queryNodes('resource_embedding', $k, $emb) YIELD node, score "
            "RETURN node{.id,.title,.url,.source,.author,.description,.duration_minutes,.published_at,"
            ".difficulty,.version_hint,.warnings,.has_transcript,.text} AS r, score", k=k, emb=embedding)).data()


async def link_covers(concept_id: str, links: list[dict]) -> None:
    """Replace the COVERS links of a concept (idempotent). Coverage/evidence are filled in by the analysis phase."""
    async def work(tx):
        await tx.run("MATCH (:Resource)-[e:COVERS]->(:Concept {id:$cid}) DELETE e", cid=concept_id)
        await tx.run(
            "UNWIND $links AS l MATCH (r:Resource {id:l.resource_id}), (k:Concept {id:$cid}) "
            "MERGE (r)-[e:COVERS]->(k) SET e.similarity_score=l.similarity, e.rank_score=l.rank_score, "
            "e.rank=l.rank, e.reasons=l.reasons", links=links, cid=concept_id)
    async with get_driver().session() as s:
        await s.execute_write(work)


async def resources_for_course(course_id: str, owner_id: str) -> list[dict]:
    async with get_driver().session() as s:
        return await (await s.run(
            "MATCH (:Course {id:$cid, owner_id:$owner})-[:HAS_UNIT]->(:Unit)-[:HAS_TOPIC]->(:Topic)-[:HAS_CONCEPT]->(k:Concept) "
            "OPTIONAL MATCH (r:Resource)-[e:COVERS]->(k) "
            "WITH k, r, e ORDER BY e.rank "
            "RETURN k.id AS concept_id, k.name AS concept, "
            "collect(CASE WHEN r IS NULL THEN null ELSE r{.id,.title,.url,.source,.author,.duration_minutes,"
            ".published_at,.difficulty,.version_hint,.warnings,.has_transcript, "
            "similarity: e.similarity_score, rank_score: e.rank_score, rank: e.rank, reasons: e.reasons, "
            "coverage: e.coverage_score, evidence: e.evidence_score, confidence: e.confidence, "
            "accepted: e.accepted, covered_points: e.covered_points, missing_points: e.missing_points, "
            "evidence_json: e.evidence_json} END) AS resources, "
            "k.gap_status AS gap_status, k.coverage AS coverage, k.missing_points AS missing_points, "
            "k.gap_iterations AS gap_iterations, k.gap_message AS gap_message, k.required_points AS required_points "
            "ORDER BY concept",
            cid=course_id, owner=owner_id)).data()


# ------------------------------------------------------------------ coverage / gaps
async def analysis_inputs(course_id: str, owner_id: str, ids: list[str] | None = None) -> list[dict]:
    """Concepts with their required points and linked resources (including stored text) for coverage analysis."""
    async with get_driver().session() as s:
        return await (await s.run(
            "MATCH (:Course {id:$cid, owner_id:$owner})-[:HAS_UNIT]->(:Unit)-[:HAS_TOPIC]->(:Topic)-[:HAS_CONCEPT]->(k:Concept) "
            "WHERE $ids IS NULL OR k.id IN $ids "
            "OPTIONAL MATCH (r:Resource)-[e:COVERS]->(k) "
            "WITH k, r, e ORDER BY e.rank "
            "RETURN k{.id,.name,.description,.difficulty,.estimated_minutes,.required_points,.gap_status,.gap_iterations} AS concept, "
            "collect(CASE WHEN r IS NULL THEN null ELSE r{.id,.title,.url,.source,.description,.text,.difficulty,"
            ".duration_minutes,.published_at,.warnings, similarity: e.similarity_score, rank: e.rank, "
            "covered_points: e.covered_points, coverage: e.coverage_score} END) AS resources ORDER BY concept.name",
            cid=course_id, owner=owner_id, ids=ids)).data()


async def save_required_points(concept_id: str, points: list[str]) -> None:
    async with get_driver().session() as s:
        await s.run("MATCH (k:Concept {id:$id}) SET k.required_points=$p", id=concept_id, p=points)


async def save_resource_analysis(concept_id: str, rows: list[dict]) -> None:
    """Store coverage/evidence/confidence on the COVERS relationships (creating them for new gap resources).
    Links to resources that are not part of the final analysed set are removed so ranks stay consistent."""
    async def work(tx):
        await tx.run("MATCH (r:Resource)-[e:COVERS]->(:Concept {id:$cid}) WHERE NOT r.id IN $keep DELETE e",
                     cid=concept_id, keep=[r["resource_id"] for r in rows])
        await tx.run(
            "UNWIND $rows AS r MATCH (x:Resource {id:r.resource_id}), (k:Concept {id:$cid}) "
            "MERGE (x)-[e:COVERS]->(k) "
            "SET e.coverage_score=r.coverage, e.evidence_score=r.evidence, e.confidence=r.confidence, "
            "e.covered_points=r.covered_points, e.missing_points=r.missing_points, e.evidence_json=r.evidence_json, "
            "e.similarity_score=coalesce(r.similarity, e.similarity_score), e.rank_score=r.rank_score, "
            "e.rank=r.rank, e.accepted=r.accepted, e.reasons=r.reasons", rows=rows, cid=concept_id)
    async with get_driver().session() as s:
        await s.execute_write(work)


async def save_concept_coverage(concept_id: str, coverage: float, gap_status: str, missing: list[str],
                                iterations: int, message: str | None) -> None:
    async with get_driver().session() as s:
        await s.run("MATCH (k:Concept {id:$id}) SET k.coverage=$c, k.gap_status=$g, k.missing_points=$m, "
                    "k.gap_iterations=$i, k.gap_message=$msg",
                    id=concept_id, c=coverage, g=gap_status, m=missing, i=iterations, msg=message)


# ------------------------------------------------------------------ learning path
async def enroll(user_id: str, course_id: str) -> bool:
    """Learner -[:FOLLOWS]-> LearningPath -[:FOR_COURSE]-> Course. Returns False if the course is not in Neo4j."""
    async with get_driver().session() as s:
        rec = await (await s.run(
            "MATCH (c:Course {id:$cid}) MERGE (l:Learner {user_id:$uid}) "
            "MERGE (p:LearningPath {id:$pid}) ON CREATE SET p.created_at=datetime() "
            "SET p.user_id=$uid, p.course_id=$cid "
            "MERGE (l)-[f:FOLLOWS]->(p) ON CREATE SET f.since=datetime() "
            "MERGE (p)-[:FOR_COURSE]->(c) RETURN c.id AS id",
            cid=course_id, uid=user_id, pid=f"{course_id}:{user_id}")).single()
        return rec is not None


async def followed_courses(user_id: str) -> list[dict]:
    async with get_driver().session() as s:
        return await (await s.run(
            "MATCH (:Learner {user_id:$uid})-[f:FOLLOWS]->(:LearningPath)-[:FOR_COURSE]->(c:Course) "
            "RETURN c.id AS course_id, c.name AS name, c.version AS version, toString(f.since) AS since "
            "ORDER BY f.since DESC", uid=user_id)).data()


async def path_rows(course_id: str, user_id: str) -> list[dict]:
    """Flat rows: one per concept placed in the approved plan, with mastery and its top resources."""
    async with get_driver().session() as s:
        return await (await s.run(
            "MATCH (s:Semester {course_id:$cid})<-[:IN_SEMESTER]-(w:Week)<-[:IN_WEEK]-(k:Concept) "
            "OPTIONAL MATCH (:Learner {user_id:$uid})-[m:MASTERED]->(k) "
            "OPTIONAL MATCH (r:Resource)-[e:COVERS]->(k) "
            "WITH s, w, k, m, r, e ORDER BY e.rank "
            "RETURN s.number AS semester, w.number AS week, "
            "k{.id,.name,.description,.difficulty,.estimated_minutes,.unit,.gap_status,.gap_message,.coverage,.missing_points} AS concept, "
            "m.mastery_score AS mastery, "
            "[x IN collect(CASE WHEN r IS NULL THEN null ELSE r{.id,.title,.url,.source,.author,.duration_minutes,"
            ".difficulty,.warnings, coverage: e.coverage_score, similarity: e.similarity_score, "
            "rank_score: e.rank_score, accepted: e.accepted, reasons: e.reasons} END) WHERE x IS NOT NULL][0..3] AS resources "
            "ORDER BY semester, week, concept.name", cid=course_id, uid=user_id)).data()


async def set_learning(user_id: str, course_id: str, concept_ids: list[str], mastery_threshold: float = 0.8) -> None:
    """LEARNING = the concepts of the current week plus any attempted concept that is not yet mastered.
    Other LEARNING links in this course are removed."""
    async def work(tx):
        await tx.run(
            "MATCH (l:Learner {user_id:$uid})-[e:LEARNING]->(k:Concept {course_id:$cid}) "
            "WHERE NOT k.id IN $ids AND NOT EXISTS { (l)-[m:MASTERED]->(k) WHERE m.mastery_score < $thr } "
            "DELETE e", uid=user_id, cid=course_id, ids=concept_ids, thr=mastery_threshold)
        await tx.run("MATCH (l:Learner {user_id:$uid}) UNWIND $ids AS id MATCH (k:Concept {id:id}) "
                     "MERGE (l)-[e:LEARNING]->(k) ON CREATE SET e.since=datetime()", uid=user_id, ids=concept_ids)
    async with get_driver().session() as s:
        await s.execute_write(work)


# ------------------------------------------------------------------ quizzes
async def concept_context(course_id: str, concept_ids: list[str]) -> list[dict]:
    async with get_driver().session() as s:
        return await (await s.run(
            "MATCH (k:Concept) WHERE k.course_id=$cid AND k.id IN $ids "
            "OPTIONAL MATCH (k)-[:ALIGNS_WITH]->(o:Outcome) "
            "RETURN k.id AS id, k.name AS name, k.description AS description, k.required_points AS required_points, "
            "k.difficulty AS difficulty, collect(o.text) AS outcomes", cid=course_id, ids=concept_ids)).data()


async def save_quiz(quiz_id: str, concept_id: str, course_id: str, questions: list[dict]) -> None:
    """Quiz -[:HAS_QUESTION]-> Question and Quiz -[:TESTS]-> Concept. Replaces any previous questions."""
    async def work(tx):
        await tx.run("MATCH (:Quiz {id:$qid})-[:HAS_QUESTION]->(q:Question) DETACH DELETE q", qid=quiz_id)
        await tx.run(
            "MATCH (k:Concept {id:$kid}) MERGE (z:Quiz {id:$qid}) "
            "SET z.concept_id=$kid, z.course_id=$cid, z.question_count=$n, z.created_at=datetime() "
            "MERGE (z)-[:TESTS]->(k) "
            "WITH z UNWIND $qs AS q CREATE (x:Question {id:q.id}) "
            "SET x.text=q.question, x.type=q.type, x.options=q.options, x.correct=q.correct, "
            "x.explanation=q.explanation, x.difficulty=q.difficulty, x.outcome=q.outcome, x.order=q.order "
            "MERGE (z)-[:HAS_QUESTION]->(x)",
            qid=quiz_id, kid=concept_id, cid=course_id, n=len(questions), qs=questions)
    async with get_driver().session() as s:
        await s.execute_write(work)


async def get_quiz(quiz_id: str) -> dict | None:
    async with get_driver().session() as s:
        rec = await (await s.run(
            "MATCH (z:Quiz {id:$qid})-[:TESTS]->(k:Concept) "
            "OPTIONAL MATCH (z)-[:HAS_QUESTION]->(q:Question) WITH z, k, q ORDER BY q.order "
            "RETURN z.id AS quiz_id, z.course_id AS course_id, k.id AS concept_id, k.name AS concept, "
            "collect(q{.id,.text,.type,.options,.correct,.explanation,.difficulty,.outcome}) AS questions",
            qid=quiz_id)).single()
        return dict(rec) if rec else None


async def existing_quizzes(concept_ids: list[str]) -> dict[str, int]:
    async with get_driver().session() as s:
        rows = await (await s.run(
            "MATCH (z:Quiz)-[:TESTS]->(k:Concept) WHERE k.id IN $ids AND z.question_count > 0 "
            "RETURN k.id AS concept_id, z.id AS quiz_id", ids=concept_ids)).data()
    return {r["concept_id"]: r["quiz_id"] for r in rows}


async def record_attempt(user_id: str, quiz_id: str, score: float, total: int) -> None:
    async with get_driver().session() as s:
        await s.run("MERGE (l:Learner {user_id:$uid}) WITH l MATCH (z:Quiz {id:$qid}) "
                    "CREATE (l)-[:ATTEMPTED {score:$score, total:$total, at:datetime()}]->(z)",
                    uid=user_id, qid=quiz_id, score=score, total=total)


# ------------------------------------------------------------------ mastery
async def get_mastery(user_id: str, concept_id: str) -> dict | None:
    async with get_driver().session() as s:
        rec = await (await s.run(
            "MATCH (:Learner {user_id:$uid})-[m:MASTERED]->(:Concept {id:$cid}) "
            "RETURN m.mastery_score AS mastery_score, m.attempt_count AS attempt_count", uid=user_id, cid=concept_id)).single()
        return dict(rec) if rec else None


async def save_mastery(user_id: str, concept_id: str, state: dict) -> None:
    """Learner -[:MASTERED {mastery_score, attempt_count, last_updated}]-> Concept (recorded from the first attempt).
    A mastered concept stops being a LEARNING concept; a not-yet-mastered one stays LEARNING."""
    async def work(tx):
        await tx.run(
            "MERGE (l:Learner {user_id:$uid}) WITH l MATCH (k:Concept {id:$cid}) "
            "MERGE (l)-[m:MASTERED]->(k) "
            "SET m.mastery_score=$score, m.attempt_count=$n, m.last_score=$last, m.mastered=$mastered, "
            "m.last_updated=datetime($updated)",
            uid=user_id, cid=concept_id, score=state["mastery_score"], n=state["attempt_count"],
            last=state["last_score"], mastered=state["mastered"], updated=state["last_updated"])
        if state["mastered"]:
            await tx.run("MATCH (:Learner {user_id:$uid})-[e:LEARNING]->(:Concept {id:$cid}) DELETE e",
                         uid=user_id, cid=concept_id)
        else:
            await tx.run("MATCH (l:Learner {user_id:$uid}), (k:Concept {id:$cid}) "
                         "MERGE (l)-[e:LEARNING]->(k) ON CREATE SET e.since=datetime()", uid=user_id, cid=concept_id)
    async with get_driver().session() as s:
        await s.execute_write(work)


async def mastery_for_course(user_id: str, course_id: str) -> list[dict]:
    async with get_driver().session() as s:
        return await (await s.run(
            "MATCH (k:Concept {course_id:$cid}) "
            "OPTIONAL MATCH (:Learner {user_id:$uid})-[m:MASTERED]->(k) "
            "OPTIONAL MATCH (k)-[:IN_SEMESTER]->(s:Semester) "
            "OPTIONAL MATCH (k)-[:IN_WEEK]->(w:Week) "
            "RETURN k.id AS concept_id, k.name AS concept, k.unit AS unit, s.number AS semester, w.number AS week, "
            "m.mastery_score AS mastery_score, m.attempt_count AS attempt_count, "
            "toString(m.last_updated) AS last_updated ORDER BY semester, week, concept", cid=course_id, uid=user_id)).data()


# ------------------------------------------------------------------ gaps / adaptive path
async def course_structure(course_id: str) -> dict:
    """Concepts (with plan position) and PREREQUISITE_OF edges of a course."""
    async with get_driver().session() as s:
        concepts = await (await s.run(
            "MATCH (k:Concept {course_id:$cid}) "
            "OPTIONAL MATCH (k)-[:IN_SEMESTER]->(s:Semester) OPTIONAL MATCH (k)-[:IN_WEEK]->(w:Week) "
            "RETURN k.id AS id, k.name AS name, k.difficulty AS difficulty, k.estimated_minutes AS estimated_minutes, "
            "k.unit AS unit, s.number AS semester, w.number AS week", cid=course_id)).data()
        edges = await (await s.run(
            "MATCH (a:Concept {course_id:$cid})-[:PREREQUISITE_OF]->(b:Concept) RETURN a.id AS a, b.id AS b",
            cid=course_id)).data()
    return {"concepts": concepts, "edges": [(e["a"], e["b"]) for e in edges]}


async def resources_top(course_id: str, n: int = 6) -> dict[str, list[dict]]:
    async with get_driver().session() as s:
        rows = await (await s.run(
            "MATCH (r:Resource)-[e:COVERS]->(k:Concept {course_id:$cid}) WITH k, r, e ORDER BY e.rank "
            "RETURN k.id AS cid, collect(r{.id,.title,.url,.source,.duration_minutes,.difficulty, "
            "coverage: e.coverage_score, rank: e.rank, warnings: r.warnings})[0..$n] AS rs",
            cid=course_id, n=n)).data()
    return {r["cid"]: r["rs"] for r in rows}


async def mastery_map(user_id: str, course_id: str) -> dict[str, dict]:
    async with get_driver().session() as s:
        rows = await (await s.run(
            "MATCH (:Learner {user_id:$uid})-[m:MASTERED]->(k:Concept {course_id:$cid}) "
            "RETURN k.id AS id, m.mastery_score AS mastery_score, m.attempt_count AS attempt_count",
            uid=user_id, cid=course_id)).data()
    return {r["id"]: {"mastery_score": r["mastery_score"], "attempt_count": r["attempt_count"]} for r in rows}


async def save_gaps(user_id: str, course_id: str, gaps: list[dict]) -> None:
    """Learner -[:HAS_GAP {kind, severity, because}]-> Concept. Replaces the previous gaps of this learner in the course."""
    rows = [{"cid": g["concept_id"], "kind": g["kind"], "severity": g["severity"], "because": g["because"]} for g in gaps]

    async def work(tx):
        await tx.run("MATCH (:Learner {user_id:$uid})-[e:HAS_GAP]->(k:Concept {course_id:$course}) DELETE e",
                     uid=user_id, course=course_id)
        await tx.run("MERGE (l:Learner {user_id:$uid}) WITH l UNWIND $rows AS r MATCH (k:Concept {id:r.cid}) "
                     "MERGE (l)-[e:HAS_GAP]->(k) SET e.kind=r.kind, e.severity=r.severity, e.because=r.because, "
                     "e.updated_at=datetime()", uid=user_id, rows=rows)
    async with get_driver().session() as s:
        await s.execute_write(work)


async def save_adaptive_path(user_id: str, course_id: str, items: list[dict]) -> None:
    """LearningPath -[:NEXT {order, action, reason}]-> Concept: the current adaptive ordering for the learner."""
    rows = [{"cid": i["concept_id"], "order": n, "action": i["action"], "reason": i["reason"], "week": i["week"]}
            for n, i in enumerate(items, 1)]

    async def work(tx):
        await tx.run("MATCH (p:LearningPath {id:$pid})-[e:NEXT]->() DELETE e", pid=f"{course_id}:{user_id}")
        await tx.run("MATCH (p:LearningPath {id:$pid}) UNWIND $rows AS r MATCH (k:Concept {id:r.cid}) "
                     "MERGE (p)-[e:NEXT]->(k) SET e.order=r.order, e.action=r.action, e.reason=r.reason, e.week=r.week, "
                     "e.generated_at=datetime()", pid=f"{course_id}:{user_id}", rows=rows)
    async with get_driver().session() as s:
        await s.execute_write(work)

# ------------------------------------------------------------------ dashboards
async def dashboard_concepts(course_id: str) -> list[dict]:
    """Per-concept rows for the instructor dashboard: plan position, coverage/gap status, outcomes, resource stats."""
    async with get_driver().session() as s:
        return await (await s.run(
            "MATCH (k:Concept {course_id:$cid}) "
            "OPTIONAL MATCH (k)-[:IN_SEMESTER]->(s:Semester) OPTIONAL MATCH (k)-[:IN_WEEK]->(w:Week) "
            "OPTIONAL MATCH (k)-[:ALIGNS_WITH]->(o:Outcome) "
            "WITH k, s, w, collect(DISTINCT o.text) AS outcomes "
            "OPTIONAL MATCH (r:Resource)-[:COVERS]->(k) "
            "WITH k, s, w, outcomes, collect(DISTINCT r) AS rs "
            "RETURN k.id AS id, k.name AS name, k.unit AS unit, k.difficulty AS difficulty, "
            "k.estimated_minutes AS estimated_minutes, s.number AS semester, w.number AS week, "
            "k.coverage AS coverage, k.gap_status AS gap_status, k.missing_points AS missing_points, "
            "k.gap_message AS gap_message, outcomes, size(rs) AS resource_count, "
            "size([r IN rs WHERE any(x IN coalesce(r.warnings, []) WHERE x CONTAINS 'older than' OR x CONTAINS 'years ago')]) "
            "AS outdated_count ORDER BY semester, week, name", cid=course_id)).data()


async def course_outcomes(course_id: str) -> list[str]:
    async with get_driver().session() as s:
        rows = await (await s.run(
            "MATCH (:Course {id:$cid})-[:HAS_OUTCOME]->(o:Outcome) RETURN o.text AS t ORDER BY o.id", cid=course_id)).data()
    return [r["t"] for r in rows]


# ------------------------------------------------------------------ course deletion
async def delete_course(course_id: str, owner_id: str) -> None:
    """Remove a course and everything derived from it (units, topics, concepts, quizzes, plan, learner links).
    Shared Resource nodes are kept: other courses may use them."""
    async def work(tx):
        res = await tx.run("MATCH (c:Course {id:$c, owner_id:$o}) RETURN c.id AS id", c=course_id, o=owner_id)
        if await res.single() is None:
            return
        await tx.run("MATCH (n) WHERE n.course_id=$c OR n.id STARTS WITH $c OR n.id STARTS WITH $q DETACH DELETE n",
                     c=course_id, q="quiz:" + course_id)
    async with get_driver().session() as s:
        await s.execute_write(work)

# ------------------------------------------------------------------ resilience
# The Aura connection is occasionally reset by the network mid-query. The driver only retries managed
# transactions, so every repository function is wrapped to retry transient connection failures on a fresh
# connection. Functions that are not safe to repeat are listed in NOT_RETRIED.
import asyncio as _asyncio
import functools as _functools
import inspect as _inspect
import logging as _logging

from neo4j.exceptions import ServiceUnavailable as _ServiceUnavailable
from neo4j.exceptions import SessionExpired as _SessionExpired
from neo4j.exceptions import TransientError as _TransientError

_log = _logging.getLogger(__name__)
NOT_RETRIED = {"record_attempt"}  # CREATEs a relationship: a lost response could otherwise duplicate it
RETRIES = 3
# A connection the network silently killed can hang a query for a minute or more. Every attempt therefore has a
# client-side deadline, after which it is retried on a fresh connection. Writes get longer: they carry embeddings.
READ_TIMEOUT, WRITE_TIMEOUT = 12, 45
WRITE_PREFIXES = ("save_", "upsert_", "delete_", "link_", "enroll", "set_", "ensure_", "init_")


def _with_retry(fn):
    timeout = WRITE_TIMEOUT if fn.__name__.startswith(WRITE_PREFIXES) else READ_TIMEOUT

    @_functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        for attempt in range(RETRIES):
            try:
                return await _asyncio.wait_for(fn(*args, **kwargs), timeout)
            except (_ServiceUnavailable, _SessionExpired, _TransientError, ConnectionError, OSError,
                    _asyncio.TimeoutError) as e:
                if attempt == RETRIES - 1:
                    raise
                _log.warning("neo4j %s failed (%s); retrying", fn.__name__, type(e).__name__)
                await _asyncio.sleep(1.5 * (attempt + 1))
    return wrapper


for _name, _fn in list(globals().items()):
    if _inspect.iscoroutinefunction(_fn) and _fn.__module__ == __name__ and _name not in NOT_RETRIED \
            and not _name.startswith("_"):
        globals()[_name] = _with_retry(_fn)
