"""Routers: auth, jobs, approvals, runs (SSE), pipeline, messages, analytics, settings, memory.
Every query is scoped to the signed-in user (tenant)."""
from __future__ import annotations

import asyncio
import json
from collections import Counter

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from agent.llm import ledger_summary
from agent.mcp_client import hub
from agent.memory import store as mem
from agent.memory.promotion_rules import record_outcome
from apps.api.auth import users
from apps.api.auth.users import User
from apps.api.schemas.models import (Analytics, ApprovalIn, Health, JobCard, LoginIn, LoginOut,
                                     PendingApproval, PipelineCard, RunRef, ThreadState)
from apps.api.service import RT, runs_for

router = APIRouter()


def _own(user: str, thread_id: str):
    if not thread_id.startswith(f"{user}:"):
        raise HTTPException(404, "not found")


# ---------------- auth ----------------
@router.post("/auth/login", response_model=LoginOut, tags=["auth"])
def login(body: LoginIn):
    return LoginOut(token=users.login(body.username, body.password), user=body.username)


@router.get("/auth/me", tags=["auth"])
def me(user: str = User):
    return {"user": user, "settings": users.get_settings(user)}


@router.get("/health", response_model=Health, tags=["system"])
async def health():
    ok = await RT.check_marketplace()
    from apps.api.service import db
    queued = db().execute("select count(*) from runs where status='degraded_queued'").fetchone()[0]
    return Health(api="ok", marketplace="ok" if ok else "unavailable", queued_jobs=queued)


@router.post("/admin/marketplace", tags=["system"])
async def toggle_marketplace(body: dict, user: str = User):
    """Demo/viva switch: simulate the marketplace going down (GigSim returns 503s) and coming
    back. On recovery, queued jobs are re-run automatically."""
    import os
    os.environ["GIGSIM_ERROR_RATE"] = "1.0" if body.get("down") else "0.0"
    resumed = []
    if not body.get("down") and await RT.check_marketplace():
        for r in runs_for(user, "bid"):
            if r["status"] == "degraded_queued":
                job = await hub().call("scout", "get_job", {"job_id": r["ref_id"]})
                resumed.append(await RT.start_run(user, "bid", r["ref_id"], {"job": job}))
    return {"marketplace_down": bool(body.get("down")), "requeued": resumed}


# ---------------- jobs ----------------
@router.get("/jobs", response_model=list[JobCard], tags=["jobs"])
async def inbox(q: str = "", limit: int = 50, user: str = User):
    try:
        res = await hub().call("scout", "search_jobs",
                               {"query": q, "limit": max(1, min(limit, 50))})
        RT.marketplace_ok = True
    except Exception as e:
        RT.marketplace_ok = False
        raise HTTPException(503, f"marketplace unavailable: {e}") from e
    runs = {r["ref_id"]: r for r in runs_for(user, "bid")}
    cards = []
    for j in res["jobs"]:
        r = runs.get(j["job_id"])
        s = (r or {}).get("summary", {})
        cards.append(JobCard(**{k: j.get(k) for k in JobCard.model_fields if k in j},
                             thread_id=(r or {}).get("thread_id"), status=(r or {}).get("status"),
                             action=s.get("action"), fit=s.get("fit"),
                             risk_score=(s.get("risk") or {}).get("score"),
                             risk_flags=(s.get("risk") or {}).get("flags", []),
                             price=s.get("price")))
    cards.sort(key=lambda c: (c.fit is None, -(c.fit or 0)))
    return cards


@router.post("/jobs/{job_id}/analyze", response_model=RunRef, tags=["jobs"])
async def analyze(job_id: str, user: str = User):
    job = await hub().call("scout", "get_job", {"job_id": job_id})
    return RunRef(thread_id=await RT.start_run(user, "bid", job_id, {"job": job}))


@router.get("/threads/{thread_id}", response_model=ThreadState, tags=["runs"])
async def thread_state(thread_id: str, user: str = User):
    _own(user, thread_id)
    return ThreadState(thread_id=thread_id, **await RT.state(thread_id))


@router.get("/threads/{thread_id}/history", tags=["runs"])
async def thread_history(thread_id: str, user: str = User):
    _own(user, thread_id)
    return await RT.history(thread_id)


@router.get("/runs/{thread_id}/stream", tags=["runs"])
async def stream(thread_id: str, token: str):
    """SSE: node-by-node progress. EventSource cannot send headers, so the session token is a
    query parameter."""
    user = users.current_user(f"Bearer {token}")
    _own(user, thread_id)
    q = RT.subscribe(thread_id)

    async def gen():
        try:
            st = await RT.state(thread_id)
            for t in (st["values"] or {}).get("trace", []):
                yield {"event": "node", "data": json.dumps({"node": t["node"], "info": t},
                                                           default=str)}
            if st["pending"] or (st["values"] or {}).get("status") not in (None, "running"):
                yield {"event": "done", "data": json.dumps(await RT.summary(thread_id),
                                                           default=str)}
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), 15)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {"event": ev["type"], "data": json.dumps(ev, default=str)}
        finally:
            RT.unsubscribe(thread_id, q)
    return EventSourceResponse(gen())


# ---------------- approvals ----------------
@router.get("/approvals", response_model=list[PendingApproval], tags=["approvals"])
async def pending(user: str = User):
    """Read from durable checkpoints, so a refresh or API restart never loses one."""
    out = []
    for r in runs_for(user):
        st = await RT.state(r["thread_id"])
        if st["pending"]:
            out.append(PendingApproval(thread_id=r["thread_id"], kind=r["kind"],
                                       ref_id=r["ref_id"], payload=st["pending"]))
    return out


@router.post("/approvals/{thread_id}", response_model=RunRef, tags=["approvals"])
async def decide(thread_id: str, body: ApprovalIn, user: str = User):
    _own(user, thread_id)
    if not (await RT.state(thread_id))["pending"]:
        raise HTTPException(409, "nothing awaiting approval on this thread")
    if body.action == "edit" and not body.text:
        raise HTTPException(422, "edit requires text")
    await RT.resume(thread_id, body.model_dump(exclude_none=True))
    return RunRef(thread_id=thread_id)


# ---------------- pipeline ----------------
COL = {"awaiting_approval": "drafted", "submitted": "submitted", "replied": "replied",
       "interview": "interview", "hired": "hired", "lost": "lost", "rejected": "lost"}


@router.get("/pipeline", response_model=list[PipelineCard], tags=["pipeline"])
async def pipeline(user: str = User):
    cards = []
    for r in runs_for(user, "bid"):
        s = r["summary"]
        col = COL.get(s.get("outcome") or r["status"])
        if col:
            cards.append(PipelineCard(thread_id=r["thread_id"], job_id=r["ref_id"],
                                      column=col, amount=(s.get("price") or {}).get("amount")))
    return cards


@router.post("/pipeline/refresh", tags=["pipeline"])
async def refresh(user: str = User):
    """Pull marketplace events (GigSim: simulated clients respond) and feed outcome memory."""
    adv = await hub().call("evaluator", "sim_advance", {})
    from apps.api.service import _upsert
    by_job = {a["job_id"]: a["status"] for a in adv["advanced"]}
    for r in runs_for(user, "bid"):
        if r["ref_id"] in by_job:
            s = {**r["summary"], "outcome": by_job[r["ref_id"]]}
            _upsert(r["thread_id"], user, "bid", r["ref_id"], r["status"], s)
            record_outcome(user, s.get("category") or "other", r["thread_id"],
                           by_job[r["ref_id"]])
    return adv


# ---------------- messages ----------------
@router.get("/messages", tags=["messages"])
async def threads(user: str = User):
    res = await hub().call("client_liaison", "list_messages", {})
    runs = {r["ref_id"]: r for r in runs_for(user, "conv")}
    for t in res["threads"]:
        r = runs.get(t["thread_id"])
        t["run"] = {"thread_id": r["thread_id"], "status": r["status"]} if r else None
    return res["threads"]


@router.post("/messages/{thread_id}/draft", response_model=RunRef, tags=["messages"])
async def draft_reply(thread_id: str, user: str = User):
    return RunRef(thread_id=await RT.start_run(user, "conv", thread_id,
                                               {"thread": {"thread_id": thread_id}}))


# ---------------- analytics ----------------
@router.get("/analytics", response_model=Analytics, tags=["analytics"])
async def analytics(user: str = User):
    runs = runs_for(user, "bid")
    props = [r for r in runs if r["status"] in {"awaiting_approval", "submitted", "rejected"}]
    sent = [r for r in runs if r["status"] == "submitted"]
    outcomes = [r["summary"].get("outcome") for r in sent if r["summary"].get("outcome")]
    by_cat: dict[str, dict] = {}
    for r in sent:
        c = by_cat.setdefault(r["summary"].get("category") or "other",
                              {"submitted": 0, "replied": 0, "hired": 0})
        c["submitted"] += 1
        o = r["summary"].get("outcome")
        c["replied"] += o in {"replied", "interview", "hired"}
        c["hired"] += o == "hired"
    costs = [r["summary"].get("usage", {}).get("cost", 0) for r in props]
    reasons = Counter(r["summary"].get("reject_reason") or "unspecified" for r in runs
                      if r["status"] == "rejected")
    return Analytics(
        proposals=len(props), submitted=len(sent),
        reply_rate=round(sum(o in {"replied", "interview", "hired"} for o in outcomes)
                         / len(outcomes), 3) if outcomes else None,
        hire_rate=round(outcomes.count("hired") / len(outcomes), 3) if outcomes else None,
        by_category=by_cat,
        connects_spent=sum(int((r["summary"].get("price") or {}).get("connects_cost") or 0)
                           for r in sent),
        cost_per_proposal_usd=round(sum(costs) / len(costs), 5) if costs else None,
        latency_note="see evals/results/decision_eval_*.json for p50/p95",
        top_rejection_reasons=reasons.most_common(5), llm_ledger=ledger_summary())


# ---------------- settings + memory ----------------
@router.get("/settings", tags=["settings"])
def get_settings(user: str = User):
    return users.get_settings(user)


@router.put("/settings", tags=["settings"])
def put_settings(body: dict, user: str = User):
    s = {**users.get_settings(user), **body}
    if s.get("autonomy") not in {"manual", "auto_skip_low_fit"}:
        raise HTTPException(422, "autonomy must be manual or auto_skip_low_fit (never auto-send)")
    users.put_settings(user, s)
    return s


@router.get("/memory", tags=["settings"])
def memory(user: str = User):
    return mem.list_memory(user)


@router.delete("/memory/{namespace}/{key}", tags=["settings"])
def forget(namespace: str, key: str, user: str = User):
    if namespace not in {"style", "outcome"}:
        raise HTTPException(404, "unknown namespace")
    mem.forget(user, namespace, key)
    return {"deleted": key}


@router.post("/connect/{provider}", tags=["auth"])
def connect(provider: str, body: dict, user: str = User):
    """Store a marketplace OAuth token (Upwork live mode) encrypted, scoped to this user."""
    if provider not in {"upwork"}:
        raise HTTPException(404, "unknown provider")
    users.store_oauth_token(user, provider, body["access_token"])
    return {"connected": provider}


# ---------------- portfolio ingestion ----------------
from fastapi import File, UploadFile  # noqa: E402


@router.post("/portfolio/upload", tags=["portfolio"])
async def upload_portfolio(file: UploadFile = File(...), user: str = User):
    """Add a case study (Markdown/text). Incremental re-index: the embedding cache is keyed by
    corpus hash, so only the new corpus is re-embedded and the next retrieval sees it."""
    import re
    import time as _t

    from agent.config import ROOT
    from rag.index import indexes
    name = re.sub(r"[^\w.-]", "_", file.filename or "upload.md")
    if not name.lower().endswith((".md", ".txt")):
        raise HTTPException(415, "upload Markdown or text case studies")
    body = (await file.read()).decode("utf-8", errors="replace")[:20000]
    sid = f"up-{int(_t.time())}"
    title = body.strip().splitlines()[0].lstrip("# ")[:120] if body.strip() else name
    folder = ROOT / "data/personas/ml_engineer/case_studies"
    (folder / f"{sid}.md").write_text(
        f"---\nid: {sid}\ntitle: {title}\nuploaded_by: {user}\nsynthetic: false\n---\n{body}",
        encoding="utf-8")
    indexes.get_index.cache_clear()
    n = len(indexes.get_index().items)
    return {"id": sid, "title": title, "items_indexed": n}
