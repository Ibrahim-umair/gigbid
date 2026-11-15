"""Simulated client: reads a proposal against the client's hidden preferences and decides."""
from __future__ import annotations

import re

from pydantic import BaseModel

from agent.llm import structured


class ClientDecision(BaseModel):
    replied: bool
    interview: bool = False
    hired: bool = False
    reason: str = ""


async def decide(job: dict, client: dict, proposal: dict) -> dict:
    prefs = client.get("hidden_prefs", {})
    res, _ = await structured(
        "sim_client", "sim_client",
        {"job_title": job["title"], "job_description": job["description"][:1500],
         "hidden_prefs": prefs, "cover_letter": proposal["cover_letter"],
         "bid": {"type": proposal["bid_type"], "amount": proposal["bid_amount"]}},
        ClientDecision, ctx={"prefs": prefs, "proposal": proposal, "job": job})
    d = res.model_dump()
    d["interview"] = d["interview"] and d["replied"]
    d["hired"] = d["hired"] and d["interview"]
    return d


def heuristic_decision(prefs: dict, proposal: dict) -> ClientDecision:
    """Deterministic stand-in used by the fake backend."""
    letter = proposal.get("cover_letter", "").lower()
    must = [s.lower() for s in prefs.get("must_have_skills", [])]
    covered = sum(1 for s in must if s in letter) / max(len(must), 1)
    generic = bool(re.match(r"\s*(dear (sir|madam|hiring)|hi there|hello,? i am|i am passionate)",
                            letter))
    over = proposal.get("bid_amount", 0) > (prefs.get("budget_ceiling") or 1e9) * 1.1
    bar = {"easy": 0.2, "normal": 0.4, "picky": 0.6}.get(prefs.get("reply_threshold"), 0.4)
    score = covered - (0.3 if generic and prefs.get("dislikes_generic_openings") else 0) - (
        0.3 if over else 0)
    replied = score >= bar
    return ClientDecision(replied=replied, interview=replied and score >= bar + 0.2,
                          hired=replied and score >= bar + 0.4,
                          reason=f"coverage={covered:.2f} generic={generic} over_budget={over}")
