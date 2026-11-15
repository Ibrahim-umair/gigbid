"""Claim verification (B3). The writer emits claims with evidence ids; one batched LLM call
labels every claim supported / partly / unsupported against the cited evidence text.
Unsupported claims are deleted or replaced by their supported rewrite *before* the Critic.

Deterministic pre-check: a claim citing no evidence, or only ids that were never retrieved,
is unsupported without spending a call on it."""
from __future__ import annotations

import re

from agent.handoffs import ClaimCheck, ClaimVerification, ProposalDraft
from agent.llm import structured

CITE_TAG = re.compile(r"\s*[\[(](?:(?:cs|repo|rev|up)-[\w-]+|cv)(?:\s*,\s*(?:(?:cs|repo|rev|up)-[\w-]+|cv))*[\])]")  # noqa: E501


def precheck(draft: ProposalDraft, evidence: dict[str, dict]) -> tuple[list, list[ClaimCheck]]:
    to_llm, auto = [], []
    for c in draft.claims:
        valid = [e for e in c.evidence_ids if e in evidence]
        if not valid:
            auto.append(ClaimCheck(claim=c.text, verdict="unsupported", fix=None))
        else:
            to_llm.append({"claim": c.text, "evidence_ids": valid})
    return to_llm, auto


async def verify(draft: ProposalDraft, evidence: dict[str, dict]) -> tuple[ClaimVerification,
                                                                           dict]:
    to_llm, auto = precheck(draft, evidence)
    usage: dict = {}
    checks = list(auto)
    if to_llm:
        cited = {e: {"title": evidence[e]["title"], "text": evidence[e].get("snippet", "")}
                 for c in to_llm for e in c["evidence_ids"]}
        res, usage = await structured("verifier", "verifier",
                                      {"claims": to_llm, "evidence": cited}, ClaimVerification,
                                      ctx={"evidence_map": evidence})
        checks += res.checks
    return ClaimVerification(checks=checks), usage


def apply_fixes(draft: ProposalDraft, ver: ClaimVerification) -> ProposalDraft:
    """Remove unsupported claim sentences from the letter (or swap in the supported rewrite)."""
    letter = draft.cover_letter
    keep_claims = []
    by_claim = {c.claim: c for c in ver.checks}
    for claim in draft.claims:
        chk = by_claim.get(claim.text)
        if chk and chk.verdict == "unsupported":
            letter = _replace_sentence(letter, claim.text, chk.fix or "")
            if chk.fix:
                keep_claims.append(claim.model_copy(update={"text": chk.fix}))
        else:
            keep_claims.append(claim)
    letter = CITE_TAG.sub("", letter)  # evidence ids belong in `claims`, never in client text
    return draft.model_copy(update={"cover_letter": re.sub(r"\s{2,}", " ", letter).strip(),
                                    "claims": keep_claims})


def _replace_sentence(letter: str, claim: str, fix: str) -> str:
    if claim in letter:
        return letter.replace(claim, fix)
    # claim is a paraphrase: drop the sentence with the highest word overlap
    sents = re.split(r"(?<=[.!?])\s+", letter)
    cw = set(re.findall(r"\w+", claim.lower()))
    if not sents or not cw:
        return letter
    scores = [len(cw & set(re.findall(r"\w+", s.lower()))) / len(cw) for s in sents]
    i = max(range(len(sents)), key=scores.__getitem__)
    if scores[i] >= 0.5:
        sents[i] = fix
    return " ".join(s for s in sents if s)
