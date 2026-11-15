"""Conversation-graph nodes: Client Liaison reads a thread, classifies intent, drafts a reply
(plus real calendar slots for interview requests), compliance-checks it, and waits for approval."""
from __future__ import annotations

import hashlib
import time

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from agent.guards import compliance_scan, detect_injection, redact, wrap_untrusted
from agent.handoffs import ReplyDraft
from agent.llm import structured
from agent.mcp_client import hub
from rag.ingest.loaders import load_profile


def _t(node, **kw):
    return [{"node": node, "ts": time.time(), **kw}]


async def load_thread(state: dict) -> dict:
    tid = state["thread"]["thread_id"]
    res = await hub().call("client_liaison", "list_messages", {"thread_id": tid})
    thread = next(t for t in res["threads"] if t["thread_id"] == tid)
    return {"thread": thread, "steps": 1, "trace": _t("load_thread", tool="list_messages")}


async def liaison(state: dict) -> dict:
    th = state["thread"]
    convo = "\n".join(f"{m['from']}: {m['text']}" for m in th["messages"])
    injected = bool(detect_injection(th["messages"][-1]["text"]))
    reply, usage = await structured(
        "client_liaison", "client_liaison",
        {"profile": {k: v for k, v in load_profile().items() if k != "synthetic"},
         "thread": wrap_untrusted(convo, "CONVERSATION")},
        ReplyDraft, ctx={"thread": th})
    return {"reply": reply.model_dump(), "usage": usage, "steps": 1,
            "trace": _t("liaison", intent=reply.intent, injection=injected)}


async def slots(state: dict) -> dict:
    if not state["reply"].get("propose_slots"):
        return {"slots": [], "steps": 1}
    res = await hub().call("client_liaison", "free_slots", {"days_ahead": 5, "max_slots": 3})
    return {"slots": res["slots"], "steps": 1, "trace": _t("slots", n=len(res["slots"]))}


def compliance(state: dict) -> dict:
    text = state["reply"]["reply"]
    if state.get("slots"):
        text += "\n" + "\n".join(f"- {s['start'].replace('T', ' ')}" for s in state["slots"])
    found = compliance_scan(text)
    clean = redact(text) if found else text
    ok = not compliance_scan(clean)
    return {"reply": {**state["reply"], "final_text": clean},
            "compliance": {"allowed": ok, "violations": found}, "steps": 1,
            "status": "running" if ok else "blocked",
            "trace": _t("compliance", allowed=ok, violations=found)}


def approval(state: dict, config: RunnableConfig) -> dict:
    decision = interrupt({"kind": "message_approval",
                          "thread_id": state["thread"]["thread_id"],
                          "intent": state["reply"]["intent"],
                          "reply": state["reply"]["final_text"], "slots": state.get("slots", []),
                          "compliance": state["compliance"],
                          "last_client_message": state["thread"]["messages"][-1]["text"]})
    upd = {"approval": decision, "steps": 1, "trace": _t("approval", action=decision["action"])}
    if decision["action"] == "edit":
        upd["reply"] = {**state["reply"], "final_text": decision["text"]}
    if decision["action"] == "reject":
        upd["status"] = "rejected"
    return upd


async def send(state: dict, config: RunnableConfig) -> dict:
    text = state["reply"]["final_text"]
    if compliance_scan(text):  # edited text is re-checked before anything leaves
        return {"status": "blocked", "steps": 1,
                "trace": _t("send", blocked=compliance_scan(text))}
    key = f"{config['configurable']['thread_id']}:" + hashlib.sha256(text.encode()).hexdigest()[
        :16]
    res = await hub().call("liaison_sender", "send_message",
                           {"thread_id": state["thread"]["thread_id"], "text": text,
                            "idempotency_key": key})
    return {"sent": res, "status": "sent", "steps": 1, "trace": _t("send", **res)}
