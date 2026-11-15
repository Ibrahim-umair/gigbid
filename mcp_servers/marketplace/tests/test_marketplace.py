"""Marketplace server through an in-memory MCP client."""
import os
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session as mem

from mcp_servers.marketplace.server import mcp

LETTER = "You need a voice chatbot for Volvo product questions. " * 6


async def _call(s, tool, args):
    r = await s.call_tool(tool, args)
    assert not r.isError, r.content
    return r.structuredContent


async def test_dry_run_then_idempotent_submit():
    async with mem(mcp._mcp_server) as s:
        before = (await _call(s, "get_connects_balance", {}))["connects"]
        args = {"job_id": "real-28572", "cover_letter": LETTER, "bid_type": "fixed",
                "bid_amount": 300, "idempotency_key": "test-key-0001"}
        prev = await _call(s, "submit_proposal", {**args, "dry_run": True})
        assert prev["status"] == "preview" and prev["preview"]["connects_cost"] > 0
        assert (await _call(s, "get_connects_balance", {}))["connects"] == before
        first = await _call(s, "submit_proposal", args)
        again = await _call(s, "submit_proposal", args)  # a retried call
        assert first["proposal_id"] == again["proposal_id"] and again["idempotent_replay"]
        after = (await _call(s, "get_connects_balance", {}))["connects"]
        assert after == before - prev["preview"]["connects_cost"]  # spent exactly once


async def test_input_constraints_enforced():
    async with mem(mcp._mcp_server) as s:
        r = await s.call_tool("submit_proposal", {"job_id": "real-28572", "cover_letter": "short",
                                                  "bid_type": "fixed", "bid_amount": 10,
                                                  "idempotency_key": "k-000001"})
        assert r.isError


async def test_audit_log_written():
    async with mem(mcp._mcp_server) as s:
        await _call(s, "get_job", {"job_id": "syn-01"})
    assert "get_job" in Path(os.environ["GIGBID_AUDIT_LOG"]).read_text()
