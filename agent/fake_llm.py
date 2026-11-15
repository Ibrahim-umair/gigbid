"""Deterministic stand-in for the LLM (backend=fake). Produces schema-valid, plausible outputs
from the same inputs the real prompt gets, so the whole graph, tests and CI run with 0 paid
calls. It is a test double, not a baseline: reported quality numbers come from the real model."""
from __future__ import annotations

import html
import re
from typing import Any

from pydantic import BaseModel

from agent import handoffs as H
from agent.guards import SCAM_PATTERNS as SCAM, detect_injection

OFF_DOMAIN = r"\b(android|ios|flutter|swift|kotlin|php|laravel|shopify|wordpress|figma|logo|" \
             r"bookkeep|accounting|seo|marketing|graphic design|virtual assistant|translation)\b"


def _text(job: dict) -> str:
    return html.unescape(f"{job.get('title', '')} {job.get('description', '')}")


def fake_response(schema: type[BaseModel], ctx: dict[str, Any]) -> BaseModel:
    return FAKES[schema.__name__](ctx)


def _jobspec(c):
    from rag.variants.common import heuristic_requirements
    j = c["job"]
    return H.JobSpec(
        job_id=j["job_id"], title=j["title"], category=j.get("category", "other"),
        requirements=heuristic_requirements(j), required_skills=[],
        budget_type="hourly" if j.get("is_hourly") else "fixed" if j.get("budget") else "unknown",
        budget_min=j.get("hourly_low") if j.get("is_hourly") else j.get("budget"),
        budget_max=j.get("hourly_high") if j.get("is_hourly") else j.get("budget"),
        screening_questions=re.findall(r"[^.?!\n]*\?", j.get("description", ""))[:3])


def _risk(c):
    t = _text(c["job"]).lower()
    flags = [f for f, p in SCAM.items() if re.search(p, t)]
    inj = bool(detect_injection(t))
    if inj:
        flags.append("prompt_injection")
    cl = c.get("client") or {}
    q = 0.5
    if cl:
        q = min(1.0, 0.2 + 0.3 * bool(cl.get("payment_verified"))
                + 0.3 * min((cl.get("total_spent_usd") or 0) / 10000, 1)
                + 0.2 * (cl.get("hire_rate") or 0))
    scam_flags = [f for f in flags if f != "prompt_injection"]
    score = min(1.0, 0.35 * len(scam_flags) + (0.3 if q < 0.3 else 0))
    return H.RiskReport(score=score, client_quality=round(q, 2),
                        is_scam=len(scam_flags) >= 2 or (len(scam_flags) == 1 and q < 0.3),
                        flags=flags, injection_detected=inj, explanation="heuristic (fake LLM)")


def _fit(c):
    cov = c.get("coverage", {})
    matches = [H.RequirementMatch(requirement=r, evidence_ids=v["evidence_ids"][:3],
                                  strength=v["strength"]) for r, v in cov.items()]
    w = {"strong": 1.0, "partial": 0.5, "none": 0.0}
    score = sum(w[m.strength] for m in matches) / max(len(matches), 1)
    if re.search(OFF_DOMAIN, _text(c.get("job", {})).lower()):
        score *= 0.4
    return H.FitReport(score=round(score, 2), matches=matches,
                       missing=[m.requirement for m in matches if m.strength == "none"],
                       reasons="coverage-based (fake LLM)")


def _draft(c):
    ev = list(c.get("evidence", {}).values())[:3]
    spec = c.get("job_spec", {})
    claims, lines = [], []
    for e in ev:
        s = f"In {e['title']}, I delivered work directly relevant to this."
        claims.append(H.Claim(text=s, evidence_ids=[e["id"]]))
        lines.append(s)
    body = (f"You need {spec.get('title', 'this project').lower()} delivered reliably. "
            + " ".join(lines) + " I would start with a short scoping call, agree milestones, and "
            "ship a working first version early so you can give feedback. My plan covers the "
            "requirements you listed and keeps everything documented and maintainable for your "
            "team. Which part of the project matters most to you in the first week?")
    return H.ProposalDraft(job_id=spec.get("job_id", ""), cover_letter=body, claims=claims,
                           screening_answers=["Answered from portfolio evidence."] *
                           len(spec.get("screening_questions", [])),
                           revision=c.get("revision", 0))


def _verify(c):
    ev = c.get("evidence_map", {})
    return H.ClaimVerification(checks=[
        H.ClaimCheck(claim=x["claim"], evidence_ids=x["evidence_ids"],
                     verdict="supported" if all(e in ev for e in x["evidence_ids"])
                     else "unsupported") for x in c.get("claims", [])])


def _critique(c):
    words = len(c.get("draft", "").split())
    issues = [] if 80 <= words <= 260 else [f"length {words} words outside 120-220"]
    return H.Critique(approve=not issues, personalisation=4, grounding=4, issues=issues)


def _compliance(c):
    pre = c.get("precheck", [])
    return H.ComplianceVerdict(allowed=not pre, violations=pre)


def _reply(c):
    last = (c.get("thread", {}).get("messages") or [{}])[-1].get("text", "").lower()
    if re.search(SCAM["off_platform_contact"] + "|" + SCAM["off_platform_payment"], last):
        return H.ReplyDraft(intent="scam_signal", reply="Thanks! I keep all communication and "
                            "payments on the platform, so let's continue here.")
    if re.search(r"\b(call|talk|interview|meet|thursday|monday|available)\b", last):
        return H.ReplyDraft(intent="interview_request", reply="Happy to talk. Here are times "
                            "that work for me:", propose_slots=True)
    if re.search(r"\b(price|rate|budget|discount|cheaper|lower)\b", last):
        return H.ReplyDraft(intent="negotiation", reply="I can adjust scope to fit your budget, "
                            "but my rate reflects the work involved.")
    return H.ReplyDraft(intent="question", reply="Good question. Based on my past work, here is "
                        "how I would approach it.")


def _client(c):
    from gigsim.client_sim import heuristic_decision
    return heuristic_decision(c.get("prefs", {}), c.get("proposal", {}))


def _client_cls():
    from gigsim.client_sim import ClientDecision
    return ClientDecision


FAKES = {"JobSpec": _jobspec, "RiskReport": _risk, "FitReport": _fit, "ProposalDraft": _draft,
         "ClaimVerification": _verify, "Critique": _critique, "ComplianceVerdict": _compliance,
         "ReplyDraft": _reply, "ClientDecision": _client}
