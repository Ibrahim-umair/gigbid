"""Request/response models: the OpenAPI schema the TypeScript client is generated from."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    token: str
    user: str


class JobCard(BaseModel):
    job_id: str
    title: str
    category: str | None = None
    budget: float | None = None
    is_hourly: bool | None = None
    hourly_low: float | None = None
    hourly_high: float | None = None
    connects_cost: int | None = None
    thread_id: str | None = None
    status: str | None = None
    action: str | None = None
    fit: float | None = None
    risk_score: float | None = None
    risk_flags: list[str] = []
    price: dict[str, Any] | None = None


class RunRef(BaseModel):
    thread_id: str


class ApprovalIn(BaseModel):
    action: Literal["approve", "edit", "reject"]
    text: str | None = None
    reason: str | None = None


class PendingApproval(BaseModel):
    thread_id: str
    kind: str
    ref_id: str
    payload: dict[str, Any]


class ThreadState(BaseModel):
    thread_id: str
    values: dict[str, Any]
    pending: dict[str, Any] | None = None
    next: list[str] = []


class PipelineCard(BaseModel):
    thread_id: str
    job_id: str
    title: str | None = None
    column: Literal["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"]
    amount: float | None = None


class Analytics(BaseModel):
    proposals: int
    submitted: int
    reply_rate: float | None
    hire_rate: float | None
    by_category: dict[str, dict[str, Any]]
    connects_spent: int
    cost_per_proposal_usd: float | None
    latency_note: str
    top_rejection_reasons: list[tuple[str, int]]
    llm_ledger: dict[str, Any]


class Health(BaseModel):
    api: str
    marketplace: Literal["ok", "unavailable"]
    queued_jobs: int
