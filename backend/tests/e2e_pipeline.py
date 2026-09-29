"""Live end-to-end run against real MongoDB, Neo4j, Groq and the web. Not collected by pytest (name lacks test_).

Usage (from backend/):  python -m tests.e2e_pipeline [--stop-after STAGE]
Creates (or re-uses) the demo account demo.learner@example.com / password123 and runs the sample syllabus through
every human-verification gate programmatically (approving whatever the AI produced).
"""
import argparse
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

EMAIL, PASSWORD = "demo.learner@example.com", "password123"
SAMPLE = Path(__file__).resolve().parents[2] / "sample" / "java_syllabus.txt"
STAGES = ["extract", "concepts", "graph", "plan", "resources"]


def wait(c, h, path, key, busy=("EXTRACTING", "GENERATING", "SAVING", "RUNNING"), timeout=1800):
    end = time.time() + timeout
    while time.time() < end:
        d = c.get(path, headers=h).json()
        if d.get(key) not in busy:
            return d
        time.sleep(4)
    raise TimeoutError(path)


def step(name):
    print(f"\n== {name}", flush=True)
    return time.time()


def main(stop_after: str | None) -> None:
    with TestClient(app) as c:
        r = c.post("/api/auth/register", json={"name": "Demo Learner", "email": EMAIL, "password": PASSWORD, "role": "INSTRUCTOR"})
        if r.status_code == 409:
            r = c.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        r.raise_for_status()
        h = {"Authorization": "Bearer " + r.json()["access_token"]}

        t = step("upload")
        up = c.post("/api/upload", files={"file": (SAMPLE.name, SAMPLE.read_bytes())}, headers=h).json()
        time.sleep(1.5)
        print(c.get(f"/api/upload/{up['id']}", headers=h).json()["status"])

        t = step("extract (Groq)")
        cid = c.post("/api/curriculum/extract", json={"upload_id": up["id"]}, headers=h).json()["id"]
        d = wait(c, h, f"/api/curriculum/{cid}", "status")
        assert d["status"] == "PENDING_REVIEW", d
        print([u["title"] for u in d["curriculum"]["units"]], f"{time.time() - t:.0f}s")
        c.post("/api/curriculum/verify", json={"curriculum_id": cid, "curriculum": d["curriculum"]}, headers=h).raise_for_status()
        print("verification #1 approved")
        if stop_after == "extract":
            return print("curriculum id", cid)

        t = step("concepts + prerequisites (Groq)")
        c.post("/api/concepts/generate", json={"curriculum_id": cid}, headers=h).raise_for_status()
        g = wait(c, h, f"/api/concepts/{cid}", "graph_status")
        assert g["graph_status"] == "PENDING_REVIEW", g
        print(len(g["graph"]["concepts"]), "concepts,", len(g["graph"]["relationships"]), "relationships", f"{time.time() - t:.0f}s")
        if stop_after == "concepts":
            return print("curriculum id", cid)

        t = step("graph validation + verification #2 + Neo4j")
        gv = c.get(f"/api/graph/{cid}", headers=h).json()
        v = gv["validation"]
        print("dag", v["is_dag"], "cycles", len(v["cycles"]), "redundant", len(v["redundant_edges"]), "orphans", len(v["orphans"]))
        graph = gv["graph"]
        if not v["is_dag"]:  # auto-fix for the script: drop one edge per cycle until acyclic
            for cyc in v["cycles"]:
                a, b = cyc[-1], cyc[0]
                graph["relationships"] = [x for x in graph["relationships"] if not (x["source"] == a and x["target"] == b)]
            print("removed cycle-closing edges")
        vr = c.post("/api/graph/verify", json={"curriculum_id": cid, "graph": graph}, headers=h)
        assert vr.status_code == 200, vr.text
        s = wait(c, h, f"/api/graph/{cid}", "neo4j_status")
        assert s["neo4j_status"] == "SAVED", s
        print("neo4j:", s["neo4j_summary"], f"{time.time() - t:.0f}s")
        if stop_after == "graph":
            return print("curriculum id", cid)

        t = step("semester plan + verification #3")
        p = c.post("/api/sequencing/generate", json={"curriculum_id": cid, "params": {"hours_per_week": 8, "weeks_per_semester": 16}}, headers=h).json()
        print(p["validation"]["semesters"], "semester(s),", p["validation"]["total_hours"], "h")
        pv = c.post("/api/sequencing/verify", json={"curriculum_id": cid}, headers=h)
        assert pv.status_code == 200, pv.text
        s = wait(c, h, f"/api/sequencing/{cid}", "neo4j_status")
        print("plan neo4j:", s["neo4j_status"])
        if stop_after == "plan":
            return print("curriculum id", cid)

        t = step("resource discovery (YouTube + DuckDuckGo + Neo4j vector search)")
        c.post("/api/resources/search", json={"curriculum_id": cid}, headers=h).raise_for_status()
        rs = wait(c, h, f"/api/resources/{cid}", "status")
        print(rs["status"], rs["progress"], "failed:", len(rs["failed"]), f"{time.time() - t:.0f}s")
        for con in rs["concepts"][:5]:
            print("-", con["concept"])
            for r in con["resources"][:2]:
                print("    ", r["source"], round(r["rank_score"], 2), r["title"][:70].encode("ascii", "replace").decode(), r["warnings"][:1])
        print("\ncurriculum id", cid, "| login:", EMAIL, PASSWORD)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stop-after", choices=STAGES)
    main(ap.parse_args().stop_after)
    sys.exit(0)
