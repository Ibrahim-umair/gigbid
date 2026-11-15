"""Run / resume bid threads with a durable checkpointer (C6) and a live ToolHub.

The checkpointer is SQLite (AsyncSqliteSaver) for the single-machine build; the Postgres saver
is a drop-in swap (see docs/adr/0002-checkpointer.md)."""
from __future__ import annotations

import contextlib
import os
from typing import Any, AsyncIterator

from langgraph.types import Command

from agent.config import ROOT
from agent.graphs.bid_graph import build_bid_graph
from agent.mcp_client import ToolHub, set_hub

CKPT = os.getenv("GIGBID_CHECKPOINTS", str(ROOT / "data/processed/checkpoints.sqlite"))


@contextlib.asynccontextmanager
async def session(transport: str | None = None) -> AsyncIterator[Any]:
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    from agent.memory.store import get_store
    async with AsyncSqliteSaver.from_conn_string(CKPT) as saver, ToolHub(transport) as h:
        set_hub(h)
        try:
            yield build_bid_graph(checkpointer=saver, store=get_store())
        finally:
            set_hub(None)


def thread_cfg(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": 60}


async def stream_job(graph, job: dict, thread_id: str, user_id: str = "demo"):
    """Yield (node, update) as each node finishes; stops at the approval interrupt."""
    async for chunk in graph.astream({"job": job, "user_id": user_id, "status": "running"},
                                     thread_cfg(thread_id), stream_mode="updates"):
        for node, upd in chunk.items():
            yield node, upd


async def resume(graph, thread_id: str, decision: dict):
    async for chunk in graph.astream(Command(resume=decision), thread_cfg(thread_id),
                                     stream_mode="updates"):
        for node, upd in chunk.items():
            yield node, upd


async def pending_approval(graph, thread_id: str) -> dict | None:
    snap = await graph.aget_state(thread_cfg(thread_id))
    for t in snap.tasks:
        for itr in t.interrupts:
            return itr.value
    return None


async def final_state(graph, thread_id: str) -> dict:
    return (await graph.aget_state(thread_cfg(thread_id))).values
