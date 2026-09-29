from datetime import datetime, timedelta, timezone

from app.services import resource_service as rs


def test_canonical_url_and_id_dedupe_variants():
    a = rs.canonical_url("https://www.youtube.com/watch?v=abc12345&t=10s")
    assert a == "https://www.youtube.com/watch?v=abc12345"
    assert rs.resource_id("http://www.example.com/x/") == rs.resource_id("https://example.com/x")


def test_iso_duration():
    assert rs.parse_iso_duration("PT1H2M30S") == 62.5
    assert rs.parse_iso_duration("PT45S") == 0.8
    assert rs.parse_iso_duration("garbage") is None


def test_difficulty_estimation():
    assert rs.estimate_difficulty("Java for Beginners") == 2
    assert rs.estimate_difficulty("Advanced Java Streams") == 4
    assert rs.estimate_difficulty("Java Collections") == 3


def test_version_warnings():
    hint, w = rs.detect_version_warnings("Spring Boot 2.7 tutorial", None)
    assert hint == "Spring Boot 2" and any("older than 3" in x for x in w)
    _, w = rs.detect_version_warnings("Java 1.8 basics", None)
    assert any("Java 8" in x for x in w)
    _, w = rs.detect_version_warnings("Java 21 records", None)
    assert w == []


def test_old_publication_warns():
    old = datetime.now(timezone.utc) - timedelta(days=365 * 6)
    _, w = rs.detect_version_warnings("Some tutorial", old)
    assert any("years ago" in x for x in w)


def test_freshness_and_fits():
    new = datetime.now(timezone.utc) - timedelta(days=100)
    assert rs.freshness_score(new, []) == 1.0
    assert rs.freshness_score(new, ["Uses Java 8 (older than 17)"]) < 1.0
    assert rs.difficulty_fit(3, 3) == 1.0 and rs.difficulty_fit(1, 5) == 0.0
    assert rs.duration_fit(600, 60) < rs.duration_fit(60, 60)


def test_rank_prefers_similar_and_fresh():
    concept = {"difficulty": 3, "estimated_minutes": 60}
    good = {"url": "https://docs.oracle.com/x", "source": "WEB", "difficulty": 3, "duration_minutes": 30,
            "published_at_dt": datetime.now(timezone.utc), "warnings": []}
    bad = {**good, "url": "https://random.example/x", "difficulty": 1, "published_at_dt": None,
           "warnings": ["Uses Java 8 (older than 17)"]}
    assert rs.rank_score(0.8, good, concept) > rs.rank_score(0.8, bad, concept)
    assert rs.rank_score(0.9, bad, concept) > rs.rank_score(0.2, bad, concept)


def test_dedupe_by_url_and_title():
    items = [{"url": "https://a.com/x", "title": "Java Maps"}, {"url": "https://www.a.com/x/", "title": "other"},
             {"url": "https://b.com/y", "title": "java  maps"}, {"url": "https://c.com/z", "title": "Different"}]
    assert [i["url"] for i in rs.dedupe(items)] == ["https://a.com/x", "https://c.com/z"]


def test_lexical_match_and_relevance_reject_generic_java_pages():
    arrays = {"title": "Chapter 10. Arrays - Oracle", "description": "Java arrays", "text": ""}
    cls = {"title": "What is Class in java?", "description": "", "text": ""}
    assert rs.lexical_match("Class Definition", cls) > rs.lexical_match("Class Definition", arrays)
    assert rs.relevance(0.66, "Class Definition", arrays) < 0.52 <= rs.relevance(0.79, "Class Definition", cls)
