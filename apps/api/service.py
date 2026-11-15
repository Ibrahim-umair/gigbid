"""Runtime shared by the API and the worker: one ToolHub, one durable checkpointer, both graphs,
a run registry (tenant-scoped), and per-run event queues for streaming."""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from typing import Any

from langgraph.types import Command

from agent.config import ROOT
from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from agent.guards import mask_obj
from agent.llm import usage_totals
from agent.marketplace_port import MarketplaceUnavailable
from agent.mcp_client import ToolHub, hub, set_hub
from agent.memory.store import get_store

DB = os.getenv("GIGBID_APP_DB", str(ROOT / "data/processed/app.sqlite"))


class Runtime:
    def __init__(self):
        self.bid = self.conv = None
        self.queues: dict[str, list[asyncio.Queue]] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.marketplace_ok = True

    async def start(self):
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        self._saver_cm = AsyncSqliteSaver.from_conn_string(
            os.getenv("GIGBID_CHECKPOINTS", str(ROOT / "data/processed/checkpoints.sqlite")))
        saver = await self._saver_cm.__aenter__()
        self._hub = await ToolHub().__aenter__()
        set_hub(self._hub)
        self.bid = build_bid_graph(checkpointer=saver, store=get_store())
        self.conv = build_conversation_graph(checkpointer=saver, store=get_store())
        db().executescript("""
        create table if not exists runs (thread_id text primary key, user_id text, kind text,
            ref_id text, status text, created real, updated real, summary text);""")

    async def stop(self):
        await self._hub.__aexit__(None, None, None)
        await self._saver_cm.__aexit__(None, None, None)

    # ---------------- events ----------------
    def subscribe(self, thread_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.queues.setdefault(thread_id, []).append(q)
        return q

    def unsubscribe(self, thread_id: str, q: asyncio.Queue):
        if q in self.queues.get(thread_id, []):
            self.queues[thread_id].remove(q)

    def _emit(self, thread_id: str, event: dict):
        event = mask_obj(json.loads(json.dumps(event, default=str)))  # PII never streamed raw
        for q in self.queues.get(thread_id, []):
            q.put_nowait(event)

    # ---------------- runs ----------------
    def graph_for(self, kind: str):
        return self.bid if kind == "bid" else self.conv

    def cfg(self, thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": 60}

    async def start_run(self, user: str, kind: str, ref_id: str, payload: dict) -> str:
        thread_id = f"{user}:{kind}:{ref_id}"
        if thread_id in self.tasks and not self.tasks[thread_id].done():
            return thread_id  # idempotent: never double-analyse
        snap = await self.graph_for(kind).aget_state(self.cfg(thread_id))
        if snap.values and snap.values.get("status") not in {"degraded_queued", "dead_letter"}:
            return thread_id  # already processed
        if snap.values:  # retry a queued/dead-lettered run under a fresh thread
            thread_id = f"{thread_id}:{int(time.time())}"
        _upsert(thread_id, user, kind, ref_id, "running", {})
        self.tasks[thread_id] = asyncio.create_task(
            self._drive(thread_id, kind, {**payload, "user_id": user, "status": "running"}))
        return thread_id

    async def resume(self, thread_id: str, decision: dict):
        kind = thread_id.split(":")[1]
        self.tasks[thread_id] = asyncio.create_task(
            self._drive(thread_id, kind, Command(resume=decision)))

    async def _drive(self, thread_id: str, kind: str, inp: Any):
        g = self.graph_for(kind)
        try:
            async for chunk in g.astream(inp, self.cfg(thread_id), stream_mode="updates"):
                for node, upd in chunk.items():
                    if node == "__interrupt__":
                        continue
                    tr = (upd or {}).get("trace") or [{}]
                    self._emit(thread_id, {"type": "node", "node": node, "info": tr[-1]})
        except MarketplaceUnavailable:
            self.marketplace_ok = False
        st = await self.summary(thread_id)
        _upsert(thread_id, None, kind, None, st["status"], st)
        self._emit(thread_id, {"type": "done", "status": st["status"]})

    async def summary(self, thread_id: str) -> dict:
        kind = thread_id.split(":")[1]
        snap = await self.graph_for(kind).aget_state(self.cfg(thread_id))
        v = snap.values or {}
        pending = next((i.value for t in snap.tasks for i in t.interrupts), None)
        status = "awaiting_approval" if pending else v.get("status", "unknown")
        if status == "degraded_queued":
            self.marketplace_ok = False
        u = usage_totals(v.get("usage"))
        return {"status": status, "pending": pending,
                "action": (v.get("decision") or {}).get("action"),
                "fit": (v.get("fit") or {}).get("score"), "risk": v.get("risk"),
                "price": v.get("price"), "usage": u,
                "category": (v.get("job") or {}).get("category"),
                "proposal_id": (v.get("submission") or {}).get("proposal_id"),
                "reject_reason": (v.get("approval") or {}).get("reason"),
                "errors": v.get("errors", [])[-2:]}

    async def state(self, thread_id: str) -> dict:
        kind = thread_id.split(":")[1]
        snap = await self.graph_for(kind).aget_state(self.cfg(thread_id))
        return {"values": snap.values,
                "pending": next((i.value for t in snap.tasks for i in t.interrupts), None),
                "next": list(snap.next)}

    async def history(self, thread_id: str) -> list[dict]:
        kind = thread_id.split(":")[1]
        out = []
        async for s in self.graph_for(kind).aget_state_history(self.cfg(thread_id)):
            out.append({"checkpoint_id": s.config["configurable"]["checkpoint_id"],
                        "next": list(s.next), "step": s.metadata.get("step")})
        return out

    async def check_marketplace(self) -> bool:
        try:
            await hub().call("pricing", "get_connects_balance", {})
            self.marketplace_ok = True
        except Exception:
            self.marketplace_ok = False
        return self.marketplace_ok


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB, check_same_thread=False, isolation_level=None)
    con.row_factory = sqlite3.Row
    return con


def _upsert(thread_id, user, kind, ref_id, status, summary):
    con = db()
    row = con.execute("select * from runs where thread_id=?", (thread_id,)).fetchone()
    now = time.time()
    if row:
        con.execute("update runs set status=?, updated=?, summary=? where thread_id=?",
                    (status, now, json.dumps(summary, default=str), thread_id))
    else:
        con.execute("insert into runs values (?,?,?,?,?,?,?,?)",
                    (thread_id, user, kind, ref_id, status, now, now,
                     json.dumps(summary, default=str)))


def runs_for(user: str, kind: str | None = None) -> list[dict]:
    q = "select * from runs where user_id=?" + (" and kind=?" if kind else "")
    rows = db().execute(q + " order by updated desc", (user, kind) if kind else (user,))
    return [{**dict(r), "summary": json.loads(r["summary"] or "{}")} for r in rows]


RT = Runtime()
