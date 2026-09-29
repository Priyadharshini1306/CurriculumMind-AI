"""Run coverage analysis on the demo curriculum. Usage: python -m tests.run_analysis [Concept Name ...]"""
import json
import sys
import time

from fastapi.testclient import TestClient

from app.main import app

CID = "6ab7b9b052a719a045d6d0ad"
names = sys.argv[1:]
with TestClient(app) as c:
    h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "demo.learner@example.com", "password": "password123"}).json()["access_token"]}
    ids = None
    if names:
        kg = c.get(f"/api/graph/{CID}/knowledge", headers=h).json()
        ids = [x["concept"]["id"] for x in kg["concepts"] if x["concept"]["name"] in names]
    t = time.time()
    c.post("/api/resources/analyze", json={"curriculum_id": CID, "concept_ids": ids}, headers=h).raise_for_status()
    d = c.get(f"/api/resources/{CID}", headers=h).json()
    print("ANALYSIS", d["analysis"], f"{time.time() - t:.0f}s")
    for x in d["concepts"]:
        if names and x["concept"] not in names:
            continue
        print(f"\n## {x['concept']}  status={x.get('gap_status')} coverage={x.get('coverage')} points={x.get('required_points')}")
        if x.get("missing_points"):
            print("   missing:", x["missing_points"], "message:", x.get("gap_message"))
        for r in [r for r in x["resources"] if r]:
            ev = json.loads(r["evidence_json"]) if r.get("evidence_json") else []
            print(f"  #{r.get('rank')} score={r.get('rank_score')} cov={r.get('coverage')} evid={r.get('evidence')} conf={r.get('confidence')} acc={r.get('accepted')} | {r['title'][:55]}".encode("ascii", "replace").decode())
            for e in ev[:1]:
                print(f"       evidence[{e['point']}] {e['score']}: {e['snippet'][:110]}".encode("ascii", "replace").decode())
