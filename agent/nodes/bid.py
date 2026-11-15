"""Bid-graph nodes. Each returns a partial state update; hand-offs are Pydantic models (C3).
External capabilities come only from MCP tools via the ToolHub allowlist (A6)."""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from agent.config import ROOT, cfg
from agent.guards import compliance_scan, detect_injection, redact, scam_signals, wrap_untrusted
from agent.handoffs import (BidDecision, ComplianceVerdict, Critique, FitReport, JobSpec,
                            PriceQuote, ProposalDraft, RiskReport)
from agent.llm import structured
from agent.mcp_client import hub
from agent.memory.promotion_rules import record_edit
from agent.memory.store import outcome_notes, style_rules
from rag.ingest.loaders import load_profile
from rag.variants.common import heuristic_requirements
from rag.verify import apply_fixes, verify

PERSONA = "ml_engineer"


def _t(node: str, **info) -> list[dict]:
    return [{"node": node, "ts": time.time(), **info}]


def _fields(job: dict) -> dict:
    return {k: job.get(k) for k in ("job_id", "title", "is_hourly", "budget", "hourly_low",
                                    "hourly_high", "country", "connects_cost", "category")}


def _evidence_text(evidence: dict[str, dict]) -> str:
    return "\n".join(f"[{e['id']}] ({e['type']}) {e['title']}: {e.get('snippet', '')[:350]}"
                     for e in evidence.values())


# ---------------- parallel analysis ----------------
async def analyst(state: dict) -> dict:
    job = state["job"]
    spec, usage = await structured("analyst", "analyst",
                                   {"fields": _fields(job),
                                    "job_post": wrap_untrusted(job["description"])},
                                   JobSpec, ctx={"job": job})
    spec = spec.model_copy(update={"job_id": job["job_id"], "title": job["title"],
                                   "category": job.get("category", spec.category)})
    return {"job_spec": spec.model_dump(), "usage": usage, "steps": 1,
            "trace": _t("analyst", requirements=len(spec.requirements))}


async def risk_assessor(state: dict) -> dict:
    job = state["job"]
    client = {}
    if job.get("client_id"):
        client = await hub().call("risk_assessor", "get_client_history",
                                  {"client_id": job["client_id"]})
    text = f"{job['title']}\n{job['description']}"
    signals = {"scam_patterns": scam_signals(text), "injection": bool(detect_injection(text))}
    rep, usage = await structured("risk_assessor", "risk_assessor",
                                  {"signals": signals, "client": client,
                                   "job_post": wrap_untrusted(text)},
                                  RiskReport, ctx={"job": job, "client": client})
    if signals["injection"] and not rep.injection_detected:  # deterministic floor
        rep = rep.model_copy(update={"injection_detected": True,
                                     "flags": rep.flags + ["prompt_injection"]})
    return {"risk": rep.model_dump(), "client": client, "usage": usage, "steps": 1,
            "trace": _t("risk_assessor", score=rep.score, flags=rep.flags,
                        tool="get_client_history")}


async def fit_matcher(state: dict) -> dict:
    job = state["job"]
    reqs = heuristic_requirements(job)  # runs in parallel with the Analyst, so no JobSpec yet
    res = await hub().call("fit_matcher", "match_requirements",
                           {"job_title": job["title"], "requirements": reqs, "k": 6})
    evidence = {e["id"]: e for e in res["items"]}
    coverage = {c["requirement"]: {"evidence_ids": c["evidence_ids"], "strength": c["strength"]}
                for c in res["coverage"]}
    fit, usage = await structured(
        "fit_matcher", "fit_matcher",
        {"profile": {k: v for k, v in load_profile(PERSONA).items() if k != "synthetic"},
         "requirements": reqs, "coverage": coverage, "evidence": _evidence_text(evidence)},
        FitReport, ctx={"coverage": coverage, "evidence": evidence, "job": job})
    for m in fit.matches:  # never let invented ids through
        m.evidence_ids = [e for e in m.evidence_ids if e in evidence]
    return {"fit": fit.model_dump(), "evidence": evidence, "usage": usage, "steps": 1,
            "trace": _t("fit_matcher", score=fit.score, tool="match_requirements",
                        evidence=list(evidence))}


# ---------------- decision + pricing ----------------
def decide(state: dict) -> dict:
    th = cfg("thresholds")
    risk, fit = RiskReport(**state["risk"]), FitReport(**state["fit"])
    reasons = []
    if risk.is_scam or risk.score > th["max_risk"]:
        action = "skip"
        reasons.append(f"risk {risk.score:.2f} flags={risk.flags}")
    elif fit.score < th["watch_min_fit"]:
        action = "skip"
        reasons.append(f"fit {fit.score:.2f} below {th['watch_min_fit']}")
    elif fit.score < th["bid_min_fit"] or risk.client_quality < th["min_client_quality_for_bid"]:
        action = "watch"
        reasons.append(f"fit {fit.score:.2f} / client quality {risk.client_quality:.2f}")
    else:
        action = "bid"
        reasons.append(f"fit {fit.score:.2f}, risk {risk.score:.2f}")
    if risk.injection_detected:
        reasons.append("job post contains instructions aimed at AI; ignored")
    d = BidDecision(action=action, reasons=reasons)
    status = {"skip": "skipped", "watch": "watching", "bid": "running"}[action]
    return {"decision": d.model_dump(), "status": status, "steps": 1,
            "trace": _t("decide", action=action, reasons=reasons)}


def _stats() -> dict:
    return json.loads((ROOT / "data/processed/pricing_stats.json").read_text())


async def pricing(state: dict) -> dict:
    job, prof, pc = state["job"], load_profile(PERSONA), cfg("pricing")
    fit = state["fit"]["score"]
    stats = _stats().get(job.get("category", "other"), {})
    if job.get("is_hourly"):
        lo = job.get("hourly_low") or stats.get("hourly", {}).get("p25") or prof[
            "hourly_rate_floor"]
        hi = job.get("hourly_high") or max(lo, stats.get("hourly", {}).get("p75") or lo)
        amount = max(prof["hourly_rate_floor"], min(prof["hourly_rate_target"], hi))
        typ, value = "hourly", amount * 20  # assume ~20h engagement for expected value
        why = (f"client range ${lo:g}-{hi:g}/h; target ${prof['hourly_rate_target']}/h; floor "
               f"${prof['hourly_rate_floor']}/h")
    else:
        b = job.get("budget") or stats.get("fixed", {}).get("median") or prof["fixed_price_floor"]
        amount = max(prof["fixed_price_floor"] * pc["fixed_floor_multiplier"], b)
        typ, value = "fixed", amount
        why = (f"client budget ${b:g}; market median ${stats.get('fixed', {}).get('median')}; "
               f"floor ${prof['fixed_price_floor']}")
    cost = int(job.get("connects_cost") or pc["default_connects_cost"])
    bal = await hub().call("pricing", "get_connects_balance", {})
    p_win = 0.05 + 0.25 * fit
    worth = (p_win * value >= pc["min_expected_value_ratio"] * cost * pc["connects_usd_value"]
             and bal["connects"] >= cost)
    q = PriceQuote(type=typ, amount=round(amount, 2), connects_cost=cost, connects_worth_it=worth,
                   rationale=f"{why}; Connects {cost} (balance {bal['connects']}); "
                             f"expected value ${p_win * value:.0f} at p(win)={p_win:.2f}")
    upd: dict[str, Any] = {"price": q.model_dump(), "steps": 1,
                           "trace": _t("pricing", amount=q.amount, worth=worth,
                                       tool="get_connects_balance")}
    if not worth:
        upd["status"] = "watching"
        upd["decision"] = {**state["decision"], "action": "watch",
                           "reasons": state["decision"]["reasons"] + ["Connects not worth it"]}
    return upd


# ---------------- writing loop ----------------
async def writer(state: dict) -> dict:
    job, ev = state["job"], state["evidence"]
    crit = state.get("critiques") or []
    feedback = crit[-1]["issues"] if crit and not crit[-1]["approve"] else []
    user = state.get("user_id", "demo")
    rules = style_rules(user)
    notes = outcome_notes(user, job.get("category", "other"))
    style = ""
    if rules:
        style += "User style rules (must follow):\n- " + "\n- ".join(rules)
    if notes:
        style += f"\nPast outcomes in this category: {notes}"
    rev = state.get("revisions", 0)
    draft, usage = await structured(
        "writer", os.getenv("GIGBID_WRITER_PROMPT", cfg("prompts", "writer", default="writer")),
        {"job_spec": state["job_spec"], "price": state["price"], "evidence": _evidence_text(ev),
         "feedback": feedback, "style_rules": style,
         "job_post": wrap_untrusted(job["description"])},
        ProposalDraft, ctx={"job_spec": state["job_spec"], "evidence": ev, "revision": rev})
    draft = draft.model_copy(update={"job_id": job["job_id"], "revision": rev})
    return {"draft": draft.model_dump(), "usage": usage, "steps": 1,
            "trace": _t("writer", revision=rev, claims=len(draft.claims))}


async def verifier(state: dict) -> dict:
    draft = ProposalDraft(**state["draft"])
    ver, usage = await verify(draft, state["evidence"])
    fixed = apply_fixes(draft, ver)
    return {"draft": fixed.model_dump(), "verification": ver.model_dump(),
            "unsupported_before": ver.unsupported, "usage": usage, "steps": 1,
            "trace": _t("verifier", claims=len(ver.checks), unsupported=ver.unsupported)}


async def critic(state: dict) -> dict:
    draft = state["draft"]
    crit, usage = await structured(
        "critic", "critic",
        {"job_spec": state["job_spec"], "verification": state.get("verification"),
         "draft": draft["cover_letter"] + "\n\nScreening answers: " +
                  json.dumps(draft.get("screening_answers", []))},
        Critique, ctx={"draft": draft["cover_letter"]})
    rev = state.get("revisions", 0)
    send_back = not crit.approve and rev < cfg("budgets", "max_revisions")
    return {"critiques": [{**crit.model_dump(), "send_back": send_back}],
            "revisions": rev + 1 if send_back else rev,
            "usage": usage, "steps": 1,
            "trace": _t("critic", approve=crit.approve, issues=crit.issues,
                        send_back=send_back)}


def route_after_critic(state: dict) -> str:
    if over_budget(state):
        return "needs_attention"
    return "writer" if state["critiques"][-1].get("send_back") else "compliance"


async def compliance(state: dict) -> dict:
    draft = dict(state["draft"])
    text = draft["cover_letter"] + "\n" + "\n".join(draft.get("screening_answers", []))
    pre = compliance_scan(text)
    if pre:  # deterministic redaction first
        draft["cover_letter"] = redact(draft["cover_letter"])
        draft["screening_answers"] = [redact(a) for a in draft.get("screening_answers", [])]
        text = draft["cover_letter"] + "\n" + "\n".join(draft["screening_answers"])
    unsupported = [c["claim"] for c in (state.get("verification") or {}).get("checks", [])
                   if c["verdict"] == "unsupported" and c["claim"] in text]
    verdict, usage = await structured(
        "compliance", "compliance",
        {"policy": (ROOT / "data/policy_pack/marketplace_policy.md").read_text(),
         "precheck": compliance_scan(text), "unsupported": unsupported, "text": text},
        ComplianceVerdict, ctx={"precheck": compliance_scan(text), "text": text})
    if not verdict.allowed and verdict.redacted_text:
        draft["cover_letter"] = verdict.redacted_text
        text = verdict.redacted_text
    remaining = compliance_scan(text)
    allowed = not remaining and (verdict.allowed or bool(verdict.redacted_text))
    final = ComplianceVerdict(allowed=allowed, violations=pre + verdict.violations + remaining,
                              redacted_text=draft["cover_letter"] if pre else None)
    return {"draft": draft, "compliance": final.model_dump(), "usage": usage, "steps": 1,
            "status": "running" if allowed else "blocked",
            "trace": _t("compliance", allowed=allowed, violations=final.violations)}


# ---------------- human approval + submit ----------------
async def approval_gate(state: dict, config: RunnableConfig) -> dict:
    draft, price = state["draft"], state["price"]
    thread_id = config["configurable"]["thread_id"]
    payload = {"job_id": state["job"]["job_id"], "cover_letter": draft["cover_letter"],
               "bid_type": price["type"], "bid_amount": price["amount"],
               "screening_answers": draft.get("screening_answers", [])}
    preview = await hub().call("approval_gate", "create_proposal_draft",
                               {**payload, "trace_id": thread_id})
    decision = interrupt({
        "kind": "proposal_approval", "thread_id": thread_id, "draft": draft,
        "evidence": {k: {"title": v["title"], "snippet": v["snippet"][:300]}
                     for k, v in state["evidence"].items()},
        "claims": draft.get("claims", []), "verification": state.get("verification"),
        "risk": state["risk"], "price": price, "critiques": state.get("critiques", []),
        "compliance": state.get("compliance"), "dry_run_preview": preview})
    action = decision.get("action")
    upd: dict[str, Any] = {"approval": decision, "preview": preview, "steps": 1,
                           "trace": _t("approval_gate", action=action)}
    if action == "edit":
        before = draft["cover_letter"]
        upd["draft"] = {**draft, "cover_letter": decision["text"]}
        upd["trace"][0]["promoted"] = record_edit(state.get("user_id", "demo"), thread_id,
                                                  before, decision["text"])
    elif action == "reject":
        upd["status"] = "rejected"
    return upd


def route_after_approval(state: dict) -> str:
    a = state["approval"]["action"]
    return {"approve": "submit", "edit": "compliance"}.get(a, "end")


def idempotency_key(thread_id: str, payload: dict) -> str:
    h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    return f"{thread_id}:{h}"


async def submit(state: dict, config: RunnableConfig) -> dict:
    """Only reachable after an explicit `approve`. Idempotency key = thread + payload hash, so a
    crash-and-resume re-run of this node never submits twice or spends Connects twice."""
    draft, price = state["draft"], state["price"]
    thread_id = config["configurable"]["thread_id"]
    payload = {"job_id": state["job"]["job_id"], "cover_letter": draft["cover_letter"],
               "bid_type": price["type"], "bid_amount": price["amount"],
               "screening_answers": draft.get("screening_answers", [])}
    res = await hub().call("submitter", "submit_proposal",
                           {**payload, "idempotency_key": idempotency_key(thread_id, payload),
                            "trace_id": thread_id})
    return {"submission": res, "status": "submitted", "steps": 1,
            "trace": _t("submit", proposal_id=res.get("proposal_id"),
                        replay=res.get("idempotent_replay"))}


# ---------------- budgets / failure states ----------------
def over_budget(state: dict) -> bool:
    toks = sum(u.get("in", 0) + u.get("out", 0) for u in (state.get("usage") or {}).values())
    return (state.get("steps", 0) >= cfg("budgets", "max_graph_steps")
            or toks >= cfg("budgets", "max_tokens_per_job"))


def needs_attention(state: dict) -> dict:
    return {"status": "needs_attention", "steps": 1,
            "trace": _t("needs_attention", steps=state.get("steps"))}
