"""API end-to-end with the fake LLM: login -> inbox -> analyze -> pending approval read from the
checkpoint -> approve -> submitted -> pipeline; plus degraded mode."""
import os
import time

from fastapi.testclient import TestClient

os.environ.setdefault("GIGBID_APP_DB", os.path.join(os.environ["GIGBID_STORE"] + "-app.sqlite"))


def _wait(c, h, tid, until, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = c.get(f"/api/threads/{tid}", headers=h).json()
        if until(st):
            return st
        time.sleep(1)
    raise AssertionError(f"timeout waiting on {tid}: {st.get('values', {}).get('status')}")


def test_api_flow():
    from apps.api.main import app
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "reviewer",
                                               "password": "wrong"}).status_code == 401
        tok = c.post("/api/auth/login", json={"username": "reviewer",
                                              "password": "gigbid-review"}).json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        assert c.get("/api/jobs").status_code == 401
        jobs = c.get("/api/jobs?limit=50", headers=h).json()
        assert any(j["job_id"] == "real-28572" for j in jobs)

        tid = c.post("/api/jobs/real-28572/analyze", headers=h).json()["thread_id"]
        st = _wait(c, h, tid, lambda s: s["pending"] is not None
                   or s["values"].get("status") not in (None, "running"))
        assert st["pending"]["kind"] == "proposal_approval"
        assert [p["thread_id"] for p in c.get("/api/approvals", headers=h).json()] == [tid]

        r = c.post(f"/api/approvals/{tid}", headers=h, json={"action": "approve"})
        assert r.status_code == 200
        st = _wait(c, h, tid, lambda s: s["values"].get("status") == "submitted")
        assert st["values"]["submission"]["proposal_id"]
        # approving again is refused (nothing pending) -> no double submit
        assert c.post(f"/api/approvals/{tid}", headers=h,
                      json={"action": "approve"}).status_code == 409
        assert any(p["column"] == "submitted" for p in c.get("/api/pipeline", headers=h).json())

        # tenant scoping: another user cannot read this thread
        tok2 = c.post("/api/auth/login", json={"username": "demo", "password": "demo"}).json()
        assert c.get(f"/api/threads/{tid}",
                     headers={"Authorization": f"Bearer {tok2['token']}"}).status_code == 404

        # degraded mode
        c.post("/api/admin/marketplace", headers=h, json={"down": True})
        assert c.get("/api/health").json()["marketplace"] == "unavailable"
        assert c.get("/api/jobs", headers=h).status_code == 503
        c.post("/api/admin/marketplace", headers=h, json={"down": False})
        assert c.get("/api/health").json()["marketplace"] == "ok"
