"""V4 outcome-aware ranking: boost evidence cited by past proposals that won or got replies.
Learns from what actually worked; proposals labelled `ignored` give no boost."""
import functools

from rag.index.indexes import Index
from rag.ingest.loaders import load_proposals
from rag.variants import v3_rerank

WEIGHT = {"won": 1.0, "replied": 0.5, "ignored": 0.0}


@functools.lru_cache
def outcome_prior(persona: str) -> dict[str, float]:
    prior: dict[str, float] = {}
    for p in load_proposals(persona):
        for e in p.get("evidence_refs", []):
            prior[e] = prior.get(e, 0.0) + WEIGHT.get(p.get("outcome"), 0.0)
    top = max(prior.values(), default=1.0) or 1.0
    return {e: v / top for e, v in prior.items()}


def retrieve(job: dict, index: Index, k: int = 5, requirements: list[str] | None = None,
             boost: float = 0.6):
    base = v3_rerank.retrieve(job, index, k=max(k * 3, 15), requirements=requirements)
    prior = outcome_prior(index.persona)
    if not base:
        return base
    lo, hi = min(b["score"] for b in base), max(b["score"] for b in base)
    for b in base:
        norm = (b["score"] - lo) / (hi - lo + 1e-9)
        b["score"] = round(norm + boost * prior.get(b["id"], 0.0), 4)
    return sorted(base, key=lambda b: -b["score"])[:k]
