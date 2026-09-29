"""End-to-end pipeline through the HTTP API (spec section 49). Run with:  pytest -m e2e

Real: FastAPI, MongoDB Atlas, Neo4j AuraDB (incl. vector indexes), sentence-transformers embeddings, NetworkX.
Stubbed: the LLM (deterministic structured output) and web/YouTube search, so the run is fast and repeatable.
The live-LLM/live-web variant is `python -m tests.e2e_pipeline`. Everything the test creates is deleted afterwards."""
import json
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.concepts import LLMRelationship, LLMRelationships, LLMConcept, LLMUnitConcepts
from app.schemas.curriculum import Curriculum
from app.schemas.quiz import LLMQuestion, LLMQuiz
from app.services import coverage_service, llm_service
from app.services import resource_service as rs
from tests.conftest import purge_test_users

pytestmark = pytest.mark.e2e

UNITS = {"Java Basics": ["Variables", "Operators", "Control Flow"], "OOP": ["Classes", "Inheritance", "Polymorphism"]}


# ------------------------------------------------------------------ stubs
async def fake_generate_json(system, user, schema, temperature=0.2, retries=1):
    name = schema.__name__
    if name == "Curriculum":
        return Curriculum.model_validate({
            "course": "Stub Java", "course_code": "SJ101", "version": "2026", "credit_hours": 4,
            "outcomes": ["Write object-oriented programs"], "explicit_prerequisites": [],
            "units": [{"title": u, "hours": 20, "topics": [{"title": u + " Topics", "subtopics": cs}]}
                      for u, cs in UNITS.items()]})
    if name == "LLMUnitConcepts":
        payload = json.loads(user)
        unit = payload["unit"]
        return LLMUnitConcepts(concepts=[
            LLMConcept(name=f"{c} Concept", description=f"{c} in {unit}", difficulty=2 + i, estimated_minutes=120,
                       topic=payload["topics"][0]["title"], outcomes=payload["course_outcomes"][:1])
            for i, c in enumerate(UNITS[unit])])
    if name == "LLMRelationships":
        names = [c["name"] for c in json.loads(user)["concepts"]]
        rels = [LLMRelationship(prerequisite=a, dependent=b, confidence=0.9, evidence="builds on")
                for a, b in zip(names, names[1:])]
        return LLMRelationships(relationships=rels)
    if name == "RequiredPoints":
        concept = json.loads(user)["concept"]
        return coverage_service.RequiredPoints(points=[f"{concept} basics", f"{concept} syntax",
                                                       f"{concept} examples", f"{concept} best practices"])
    if name == "LLMQuiz":
        concept = json.loads(user)["concept"]
        opts = ["alpha", "beta", "gamma", "delta"]
        qs = [LLMQuestion(question=f"Which statement about {concept} is correct? (variant {i})", type="MCQ",
                          options=[f"{o} {concept} {i}" for o in opts], correct=[0], explanation=f"Because {concept} says so.",
                          difficulty=2) for i in range(3)]
        qs.append(LLMQuestion(question=f"{concept} is used in Java programs.", type="TRUE_FALSE", options=["True", "False"],
                              correct=[0], explanation="It is.", difficulty=1))
        qs.append(LLMQuestion(question=f"Select all valid facts about {concept}.", type="MULTI",
                              options=[f"fact {o}" for o in opts], correct=[0, 1], explanation="Two are valid.", difficulty=3))
        return LLMQuiz(questions=qs)
    raise AssertionError(f"unexpected LLM schema {name}")


async def fake_search_youtube(query, limit=3):
    return []


async def fake_search_web(query, limit=4):
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
    return [{"title": f"{query} - Tutorial {i}", "url": f"https://e2e-test.example/{slug}-{i}", "source": "WEB",
             "author": None, "description": f"Everything about {query}", "duration_minutes": None, "published_at": None}
            for i in range(2)]


def fake_fetch_page(url):
    slug = url.rsplit("/", 1)[-1].rsplit("-", 1)[0].replace("-", " ")
    parts = ["basics", "syntax", "examples", "best practices", "common mistakes"]
    return " ".join(f"{slug} {p} explained in detail with a worked example." for p in parts) * 4, "2026-01-01"


@pytest.fixture()
def stubbed(monkeypatch):
    monkeypatch.setattr(llm_service, "generate_json", fake_generate_json)
    monkeypatch.setattr(rs, "search_youtube", fake_search_youtube)
    monkeypatch.setattr(rs, "search_web", fake_search_web)
    monkeypatch.setattr(rs, "_fetch_page_sync", fake_fetch_page)


# ------------------------------------------------------------------ the pipeline
def test_full_pipeline(stubbed, mongo_db, neo4j_driver):
    emails, cid, user_ids = [], None, []

    def register(c, role):
        email = f"e2e{uuid.uuid4().hex[:8]}@example.com"
        emails.append(email)
        r = c.post("/api/auth/register", json={"name": role.title(), "email": email, "password": "password123", "role": role})
        assert r.status_code == 201, r.text
        user_ids.append(r.json()["user"]["id"])
        return {"Authorization": "Bearer " + r.json()["access_token"]}, r.json()["user"]["id"]

    try:
        with TestClient(app) as c:
            # ---- register / login
            inst, inst_id = register(c, "INSTRUCTOR")
            assert c.post("/api/auth/login", json={"email": emails[0], "password": "password123"}).status_code == 200

            # ---- upload + extract + Verification #1
            up = c.post("/api/upload", files={"file": ("syllabus.txt", b"Stub Java\nUnit 1: Java Basics\nUnit 2: OOP\n")}, headers=inst)
            assert up.status_code == 202
            assert c.get(f"/api/upload/{up.json()['id']}", headers=inst).json()["status"] == "PROCESSED"
            draft = c.post("/api/curriculum/extract", json={"upload_id": up.json()["id"]}, headers=inst).json()
            cid = draft["id"]
            d = c.get(f"/api/curriculum/{cid}", headers=inst).json()
            assert d["status"] == "PENDING_REVIEW" and len(d["curriculum"]["units"]) == 2
            assert c.post("/api/concepts/generate", json={"curriculum_id": cid}, headers=inst).status_code == 409  # not approved yet
            fb = c.post("/api/curriculum/revise", json={"curriculum_id": cid, "feedback": "keep as is"}, headers=inst)
            assert fb.status_code == 202
            d = c.get(f"/api/curriculum/{cid}", headers=inst).json()
            assert d["status"] == "PENDING_REVIEW" and d["revision"] == 1  # AI revision loop returned to review
            assert c.post("/api/curriculum/verify", json={"curriculum_id": cid, "curriculum": d["curriculum"]}, headers=inst).json()["status"] == "APPROVED"

            # ---- concepts + prerequisites + graph validation + Verification #2 (+ Neo4j)
            assert c.post("/api/concepts/generate", json={"curriculum_id": cid}, headers=inst).status_code == 202
            g = c.get(f"/api/graph/{cid}", headers=inst).json()
            assert g["graph_status"] == "PENDING_REVIEW" and len(g["graph"]["concepts"]) == 6
            assert g["validation"]["is_dag"] and not g["validation"]["cycles"]
            # inject a cycle: approval must be refused, then accepted after the fix
            bad = json.loads(json.dumps(g["graph"]))
            first, last = bad["concepts"][0]["id"], bad["concepts"][2]["id"]
            bad["relationships"].append({"source": last, "target": first, "type": "PREREQUISITE_OF", "confidence": 0.5, "evidence": ""})
            assert c.post("/api/graph/verify", json={"curriculum_id": cid, "graph": bad}, headers=inst).status_code == 422
            ok = c.post("/api/graph/verify", json={"curriculum_id": cid, "graph": g["graph"]}, headers=inst)
            assert ok.status_code == 200
            g = c.get(f"/api/graph/{cid}", headers=inst).json()
            assert g["neo4j_status"] == "SAVED", g["neo4j_error"]
            kg = c.get(f"/api/graph/{cid}/knowledge", headers=inst).json()
            assert len(kg["concepts"]) == 6 and len(kg["relationships"]) == 5 and kg["course"]["version"] == "2026"

            # ---- sequencing + Verification #3
            p = c.post("/api/sequencing/generate", json={"curriculum_id": cid, "params": {"hours_per_week": 4, "weeks_per_semester": 2}}, headers=inst).json()
            assert p["validation"]["semesters"] >= 2 and not p["validation"]["violations"]
            assert c.post("/api/sequencing/verify", json={"curriculum_id": cid}, headers=inst).status_code == 200
            assert c.get(f"/api/sequencing/{cid}", headers=inst).json()["neo4j_status"] == "SAVED"

            # ---- resources: discovery, vector-search matching, coverage
            assert c.post("/api/resources/search", json={"curriculum_id": cid}, headers=inst).status_code == 202
            res = c.get(f"/api/resources/{cid}", headers=inst).json()
            assert res["status"] == "DONE" and not res["failed"], res
            assert all(len([r for r in x["resources"] if r]) >= 1 for x in res["concepts"])
            assert c.post("/api/resources/analyze", json={"curriculum_id": cid}, headers=inst).status_code == 202
            res = c.get(f"/api/resources/{cid}", headers=inst).json()
            assert res["analysis"]["status"] == "DONE" and not res["analysis"]["failed"], res["analysis"]
            assert all(x["gap_status"] == "COVERED" and x["coverage"] >= 0.6 for x in res["concepts"])
            first_res = next(r for x in res["concepts"] for r in x["resources"] if r)
            assert 0 <= first_res["coverage"] <= 1 and first_res["evidence_json"]  # coverage + quoted evidence stored

            # ---- publish, learner enrols
            assert c.post("/api/learning-path/publish", json={"curriculum_id": cid}, headers=inst).status_code == 200
            lrn, lrn_id = register(c, "LEARNER")
            assert c.post("/api/learning-path/enroll", json={"curriculum_id": cid}, headers=lrn).status_code == 201
            path = c.get(f"/api/learning-path/{lrn_id}", headers=lrn).json()
            assert path["progress"]["concepts_total"] == 6 and path["current"]["semester"] == 1
            assert all(k["resources"] for s in path["semesters"] for w in s["weeks"] for k in w["concepts"])

            # ---- quiz -> mastery -> gaps -> adaptive path
            by_name = {x["concept"]["name"]: x["concept"]["id"] for x in kg["concepts"]}
            easy, hard = by_name["Variables Concept"], by_name["Control Flow Concept"]   # chain: Variables -> Operators -> Control Flow
            job = c.post("/api/quiz/generate", json={"curriculum_id": cid, "concept_ids": [easy, hard]}, headers=lrn).json()
            assert c.get(f"/api/quiz/jobs/{job['job_id']}", headers=lrn).json()["status"] == "DONE"

            def answer(quiz_id, right):
                with neo4j_driver.session() as s:
                    rows = s.execute_read(lambda tx: tx.run(
                        "MATCH (:Quiz {id:$q})-[:HAS_QUESTION]->(x:Question) RETURN x.id AS id, x.correct AS c, size(x.options) AS n",
                        q=quiz_id).data())
                return {r["id"]: (r["c"] if right else [i for i in range(r["n"]) if i not in r["c"]][:1]) for r in rows}

            q_easy, q_hard = f"quiz:{easy}", f"quiz:{hard}"
            public = c.get(f"/api/quiz/{q_easy}", headers=lrn).json()
            assert len(public["questions"]) == 5
            assert all("correct" not in q and "explanation" not in q for q in public["questions"])  # answers never sent to the client
            resp1 = c.post("/api/quiz/submit", json={"quiz_id": q_easy, "answers": answer(q_easy, True)}, headers=lrn)
            assert resp1.status_code == 200, resp1.text
            r1 = resp1.json()
            assert r1["percent"] == 100 and r1["mastery"]["mastered"] and r1["mastery"]["attempt_count"] == 1
            resp2 = c.post("/api/quiz/submit", json={"quiz_id": q_hard, "answers": answer(q_hard, False)}, headers=lrn)
            assert resp2.status_code == 200, resp2.text
            r2 = resp2.json()
            assert r2["percent"] == 0 and not r2["mastery"]["mastered"]
            assert len(c.get("/api/quiz/history", params={"curriculum_id": cid}, headers=lrn).json()) == 2   # history in MongoDB

            m = c.get(f"/api/learner/{lrn_id}/mastery", headers=lrn).json()
            assert m["summary"]["mastered"] == 1 and m["summary"]["weak"] == 1
            gaps = c.get(f"/api/learner/{lrn_id}/gaps", headers=lrn).json()["gaps"]
            kinds = {x["concept"]: x["kind"] for x in gaps}
            assert kinds["Control Flow Concept"] == "WEAK" and kinds["Operators Concept"] == "PREREQUISITE_UNVERIFIED"
            ad = c.post("/api/adaptive-path/generate", json={"curriculum_id": cid}, headers=lrn).json()
            order = [(i["concept"], i["action"]) for w in ad["weeks"] for i in w["items"]]
            names = [n for n, _ in order]
            assert "Variables Concept" not in names and ad["summary"]["skipped"] == 1        # mastered -> skipped
            assert names.index("Operators Concept") < names.index("Control Flow Concept")   # prerequisite gap first
            assert dict(order)["Operators Concept"] == "REMEDIATE" and dict(order)["Control Flow Concept"] == "RETRY"

            # ---- dashboards
            ld = c.get(f"/api/dashboard/learner/{lrn_id}", headers=lrn).json()
            assert ld["progress"]["mastered"] == 1 and ld["mastery"]["counts"]["WEAK"] == 1
            idash = c.get(f"/api/dashboard/instructor/{cid}", headers=inst).json()
            assert all(p["done"] for p in idash["pipeline"]) and idash["coverage"]["unresolved"] == 0
            assert [l["name"] for l in idash["learners"]] == ["Learner"] and idash["learners"][0]["quiz_attempts"] == 2
            assert c.get(f"/api/dashboard/instructor/{cid}", headers=lrn).status_code == 403
    finally:
        purge_test_users(mongo_db, emails)
        def wipe(tx):
            if cid:
                tx.run("MATCH (n) WHERE n.course_id=$c OR n.id STARTS WITH $c OR n.id STARTS WITH $q DETACH DELETE n",
                       c=cid, q=f"quiz:{cid}").consume()
            tx.run("MATCH (l:Learner) WHERE l.user_id IN $ids DETACH DELETE l", ids=user_ids).consume()
            tx.run("MATCH (r:Resource) WHERE r.url CONTAINS 'e2e-test.example' DETACH DELETE r").consume()

        with neo4j_driver.session() as s:
            s.execute_write(wipe)  # managed transaction: retried on connection resets
