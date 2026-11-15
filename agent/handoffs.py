"""Typed hand-offs between agents (C3). Anything a later step decides on is one of these."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class JobSpec(BaseModel):
    job_id: str
    title: str
    category: str = "other"
    deliverables: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(
        default_factory=list, description="Atomic requirements, one capability each")
    required_skills: list[str] = Field(default_factory=list)
    budget_type: Literal["fixed", "hourly", "unknown"] = "unknown"
    budget_min: float | None = None
    budget_max: float | None = None
    timeline: str | None = None
    screening_questions: list[str] = Field(default_factory=list)
    hidden_needs: list[str] = Field(default_factory=list)


class RiskReport(BaseModel):
    score: float = Field(ge=0, le=1, description="0 = safe, 1 = certain scam/abuse")
    client_quality: float = Field(ge=0, le=1, default=0.5)
    is_scam: bool = False
    flags: list[str] = Field(default_factory=list)
    injection_detected: bool = False
    explanation: str = ""


class RequirementMatch(BaseModel):
    requirement: str
    evidence_ids: list[str] = Field(default_factory=list)
    strength: Literal["strong", "partial", "none"] = "none"


class FitReport(BaseModel):
    score: float = Field(ge=0, le=1)
    matches: list[RequirementMatch] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    reasons: str = ""

    @property
    def evidence_ids(self) -> list[str]:
        seen: list[str] = []
        for m in self.matches:
            seen += [e for e in m.evidence_ids if e not in seen]
        return seen


class BidDecision(BaseModel):
    action: Literal["bid", "watch", "skip"]
    reasons: list[str] = Field(default_factory=list)


class PriceQuote(BaseModel):
    type: Literal["fixed", "hourly"]
    amount: float
    connects_cost: int = 0
    connects_worth_it: bool = True
    rationale: str = ""


class Claim(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class ProposalDraft(BaseModel):
    job_id: str = ""
    cover_letter: str
    claims: list[Claim] = Field(
        default_factory=list, description="Every factual claim about the freelancer + evidence")
    screening_answers: list[str] = Field(default_factory=list)
    revision: int = 0


class ClaimCheck(BaseModel):
    claim: str
    verdict: Literal["supported", "partly_supported", "unsupported"]
    evidence_ids: list[str] = Field(default_factory=list)
    fix: str | None = Field(None, description="Rewrite that is supported, or null to delete")


class ClaimVerification(BaseModel):
    checks: list[ClaimCheck] = Field(default_factory=list)

    @property
    def unsupported(self) -> int:
        return sum(c.verdict == "unsupported" for c in self.checks)


class Critique(BaseModel):
    approve: bool
    personalisation: int = Field(ge=1, le=5, default=3)
    grounding: int = Field(ge=1, le=5, default=3)
    issues: list[str] = Field(default_factory=list)


class ComplianceVerdict(BaseModel):
    allowed: bool
    violations: list[str] = Field(default_factory=list)
    redacted_text: str | None = None


class ReplyDraft(BaseModel):
    intent: Literal["question", "negotiation", "interview_request", "scam_signal", "other"]
    reply: str
    propose_slots: bool = False
