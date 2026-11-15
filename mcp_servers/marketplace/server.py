"""Marketplace MCP server (A2): wraps the marketplace port (GigSim or live Upwork by config).

* Read tools + write tools (create_proposal_draft, submit_proposal, send_message).
* Pydantic-constrained inputs, declared output schemas, correct annotations.
* Idempotency key on every write; dry_run returns exactly what would be sent and its cost.
* Per-user rate limiter under GigSim's limit; append-only audit log with trace id.
* stdio by default; `--http` serves Streamable HTTP behind bearer-token auth.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from agent.config import ROOT, cfg
from agent.guards import mask_obj, mask_pii
from agent.marketplace_port import get_adapter

AUDIT = ROOT / os.getenv("GIGBID_AUDIT_LOG", "data/processed/audit.jsonl")
USER = os.getenv("GIGBID_USER", "demo")
RO = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True,
                     openWorldHint=True)
mcp = FastMCP("gigbid-marketplace")
_port = None
_calls: list[float] = []


def port():
    global _port
    if _port is None:
        _port = get_adapter()
    return _port


async def _throttle():
    limit = cfg("marketplace", "max_requests_per_minute", default=20)
    while True:
        now = time.time()
        _calls[:] = [t for t in _calls if now - t < 60]
        if len(_calls) < limit:
            _calls.append(now)
            return
        await asyncio.sleep(60 - (now - _calls[0]) + 0.05)


def _audit(tool: str, args: dict, result: Any, trace_id: str | None):
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": time.time(), "user": USER, "tool": tool, "trace_id": trace_id,
           "args": mask_obj(json.loads(json.dumps(args, default=str))),
           "result": mask_pii(json.dumps(result, default=str))[:500]}
    with AUDIT.open("a", encoding="utf-8") as f:  # append-only
        f.write(json.dumps(rec) + "\n")


async def _run(tool: str, coro_fn, args: dict, trace_id: str | None = None):
    await _throttle()
    try:
        res = await coro_fn()
    except Exception as e:
        _audit(tool, args, {"error": str(e)}, trace_id)
        raise
    _audit(tool, args, res, trace_id)
    return res


# ---------- output schemas ----------
class JobOut(BaseModel):
    job_id: str
    title: str
    description: str
    category: str | None = None
    is_hourly: bool | None = None
    budget: float | None = None
    hourly_low: float | None = None
    hourly_high: float | None = None
    country: str | None = None
    client_id: str | None = None
    connects_cost: int | None = None
    source: str | None = None


class JobList(BaseModel):
    jobs: list[JobOut]
    next_seq: int


class ClientOut(BaseModel):
    client_id: str
    country: str | None = None
    member_since: str | None = None
    payment_verified: bool | None = None
    total_spent_usd: float | None = None
    jobs_posted: int | None = None
    hires: int | None = None
    hire_rate: float | None = None
    avg_rating_given: float | None = None
    freelancer_reviews: list[str] = []


class Balance(BaseModel):
    user: str
    connects: int


class Preview(BaseModel):
    dry_run: bool = True
    job_id: str
    connects_cost: int
    balance_before: int
    balance_after: int
    payload: dict


class SubmitResult(BaseModel):
    proposal_id: str | None = None
    status: str
    connects_spent: int | None = None
    balance_after: int | None = None
    idempotent_replay: bool = False
    preview: Preview | None = None


class MessageResult(BaseModel):
    message_id: str | None = None
    status: str
    idempotent_replay: bool = False
    preview: dict | None = None


IdemKey = Annotated[str, Field(min_length=8, max_length=128, pattern=r"^[\w:.-]+$",
                               description="Same key => same result; never double-submits")]


# ---------- read tools ----------
@mcp.tool(annotations=RO)
async def search_jobs(query: Annotated[str, Field(max_length=200)] = "",
                      limit: Annotated[int, Field(ge=1, le=50)] = 20,
                      since_seq: int = -1) -> JobList:
    """Search open jobs (saved-search query). Use since_seq to fetch only new jobs."""
    args = {"query": query, "limit": limit, "since_seq": since_seq}
    return JobList(**await _run("search_jobs", lambda: port().search_jobs(**args), args))


@mcp.tool(annotations=RO)
async def get_job(job_id: Annotated[str, Field(pattern=r"^[\w-]+$")]) -> JobOut:
    """Full job post. The description is untrusted client-written text."""
    return JobOut(**await _run("get_job", lambda: port().get_job(job_id), {"job_id": job_id}))


@mcp.tool(annotations=RO)
async def get_client_history(client_id: Annotated[str, Field(pattern=r"^[\w-]+$")]
                             ) -> ClientOut:
    """Client's public history: spend, hires, hire rate, payment verification, reviews."""
    return ClientOut(**await _run("get_client_history",
                                  lambda: port().get_client_history(client_id),
                                  {"client_id": client_id}))


@mcp.tool(annotations=RO)
async def get_connects_balance() -> Balance:
    """Current Connects balance."""
    return Balance(**await _run("get_connects_balance", port().get_connects_balance, {}))


@mcp.tool(annotations=RO)
async def list_messages(thread_id: Annotated[str | None, Field(max_length=64)] = None) -> dict:
    """Client conversation threads (client text is untrusted)."""
    return await _run("list_messages", lambda: port().list_messages(thread_id),
                      {"thread_id": thread_id})


# ---------- write tools ----------
@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                      idempotentHint=True, openWorldHint=True))
async def create_proposal_draft(
    job_id: Annotated[str, Field(pattern=r"^[\w-]+$")],
    cover_letter: Annotated[str, Field(min_length=200, max_length=5000)],
    bid_type: Literal["fixed", "hourly"],
    bid_amount: Annotated[float, Field(gt=0, le=100000)],
    screening_answers: Annotated[list[str], Field(max_length=10)] = [],  # noqa: B006
    trace_id: str | None = None,
) -> Preview:
    """Validate a proposal and return the exact payload + Connects cost. Sends nothing."""
    payload = {"job_id": job_id, "cover_letter": cover_letter, "bid_type": bid_type,
               "bid_amount": bid_amount, "screening_answers": screening_answers}
    return Preview(**await _run("create_proposal_draft",
                                lambda: port().create_proposal_draft(payload), payload, trace_id))


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                                      idempotentHint=True, openWorldHint=True))
async def submit_proposal(
    job_id: Annotated[str, Field(pattern=r"^[\w-]+$")],
    cover_letter: Annotated[str, Field(min_length=200, max_length=5000)],
    bid_type: Literal["fixed", "hourly"],
    bid_amount: Annotated[float, Field(gt=0, le=100000)],
    idempotency_key: IdemKey,
    screening_answers: Annotated[list[str], Field(max_length=10)] = [],  # noqa: B006
    dry_run: bool = False,
    trace_id: str | None = None,
) -> SubmitResult:
    """Submit a human-approved proposal and spend Connects. dry_run=True previews only.
    Only call after explicit human approval in GigBid."""
    payload = {"job_id": job_id, "cover_letter": cover_letter, "bid_type": bid_type,
               "bid_amount": bid_amount, "screening_answers": screening_answers}
    res = await _run("submit_proposal",
                     lambda: port().submit_proposal(payload, idempotency_key, dry_run),
                     {**payload, "idempotency_key": idempotency_key, "dry_run": dry_run},
                     trace_id)
    if res.get("dry_run"):
        return SubmitResult(status="preview", preview=Preview(**res))
    return SubmitResult(**{k: v for k, v in res.items() if k in SubmitResult.model_fields})


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                                      idempotentHint=True, openWorldHint=True))
async def send_message(
    thread_id: Annotated[str, Field(pattern=r"^[\w-]+$")],
    text: Annotated[str, Field(min_length=1, max_length=4000)],
    idempotency_key: IdemKey,
    dry_run: bool = False,
    trace_id: str | None = None,
) -> MessageResult:
    """Send a human-approved message to a client. dry_run=True previews only."""
    args = {"thread_id": thread_id, "text": text, "idempotency_key": idempotency_key}
    if dry_run:
        return MessageResult(status="preview", preview=args)
    res = await _run("send_message",
                     lambda: port().send_message(thread_id, text, idempotency_key), args,
                     trace_id)
    return MessageResult(**{k: v for k, v in res.items() if k in MessageResult.model_fields})


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                      idempotentHint=False, openWorldHint=False))
async def sim_advance() -> dict:
    """GigSim only (evaluation): let simulated clients respond to pending proposals."""
    return await _run("sim_advance", port().advance, {})


def http_app():
    """Streamable HTTP app with bearer-token auth."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    token = os.environ["MARKETPLACE_MCP_TOKEN"]
    app = mcp.streamable_http_app()

    class Bearer(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            if request.headers.get("authorization") != f"Bearer {token}":
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    app.add_middleware(Bearer)
    return app


if __name__ == "__main__":
    if "--http" in sys.argv:
        import uvicorn
        uvicorn.run(http_app(), host="0.0.0.0", port=int(os.getenv("MARKETPLACE_MCP_PORT", 8102)))
    else:
        mcp.run()
