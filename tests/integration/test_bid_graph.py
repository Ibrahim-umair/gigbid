"""Bid graph against in-process GigSim with the fake LLM (0 paid calls).

test_crash_and_resume_submits_once runs the graph in one OS process until it pauses for
approval, lets that process exit (the "kill"), then approves from a *new* process twice.
The proposal must be submitted exactly once and Connects spent exactly once."""
import os
import sqlite3
import subprocess
import sys

from agent.config import ROOT
from agent.mcp_client import hub
from agent.runner import final_state, pending_approval, resume, session, stream_job


async def _run(g, job_id, tid):
    job = await hub().call("scout", "get_job", {"job_id": job_id})
    nodes = [n async for n, _ in stream_job(g, job, tid)]
    return nodes, await final_state(g, tid)


async def test_scam_is_skipped_before_writing():
    async with session("memory") as g:
        nodes, st = await _run(g, "syn-02", "t-scam")
    assert st["status"] == "skipped" and st["risk"]["is_scam"]
    assert {"analyst", "risk_assessor", "fit_matcher"} <= set(nodes)
    assert "writer" not in nodes


async def test_good_job_pauses_for_approval_then_reject():
    async with session("memory") as g:
        nodes, st = await _run(g, "real-28572", "t-good")
        assert st["decision"]["action"] == "bid", st["decision"]
        payload = await pending_approval(g, "t-good")
        assert payload["kind"] == "proposal_approval"
        assert payload["dry_run_preview"]["connects_cost"] > 0
        assert payload["evidence"] and payload["price"]["amount"] > 0
        _ = [x async for x in resume(g, "t-good", {"action": "reject", "reason": "too cheap"})]
        st = await final_state(g, "t-good")
    assert st["status"] == "rejected" and not st.get("submission")


def _cli(*args):
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.run([sys.executable, "-m", "agent.cli", *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=900)


def _count(job_id):
    if not os.path.exists(os.environ["GIGSIM_DB"]):
        return 0
    con = sqlite3.connect(os.environ["GIGSIM_DB"])
    try:
        return con.execute("select count(*) from proposals where job_id=?",
                           (job_id,)).fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    finally:
        con.close()


def test_crash_and_resume_submits_once():
    before = _count("real-28572")
    r1 = _cli("run", "real-28572")
    assert "awaiting approval" in r1.stdout, r1.stdout + r1.stderr[-2000:]
    r2 = _cli("approve", "job-real-28572")      # new process = restarted API
    assert "status: submitted" in r2.stdout, r2.stdout + r2.stderr[-2000:]
    _cli("approve", "job-real-28572")           # double click / retry after restart
    assert _count("real-28572") - before == 1  # exactly one new submission
