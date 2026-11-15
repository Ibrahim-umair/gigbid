"""V8 corrective RAG as a LangGraph subgraph: retrieve per requirement -> grade -> re-query weak
requirements once with an expanded query -> refuse to claim requirements with no evidence.

The grader is the open cross-encoder score (no LLM call), threshold in config/arg.
Returns items plus `coverage`: requirement -> {evidence_ids, strength}."""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from rag.index.indexes import Index
from rag.variants.common import heuristic_requirements, to_items
from rag.variants.v2_hybrid import candidates

from agent.config import cfg

STRONG = cfg("retrieval", "v8_strong", default=-5.0)
PARTIAL = cfg("retrieval", "v8_partial", default=-6.5)


class CState(TypedDict, total=False):
    job: dict
    reqs: list[str]
    coverage: dict[str, dict]
    attempts: int
    weak: list[str]


def _grade_req(index: Index, job: dict, req: str, query: str) -> dict:
    pool = cfg("retrieval", "rerank_pool", default=12)
    cand = [cid for cid, _ in candidates(job, index, [query])][:pool]
    ranked = index.rerank(f"{job.get('title', '')}: {req}", cand)[:3]
    ids, best = [], -1e9
    for cid, s in ranked:
        iid = index.chunks[cid]["item_id"]
        best = max(best, s)
        if s >= PARTIAL and iid not in ids:
            ids.append(iid)
    strength = "strong" if best >= STRONG else "partial" if best >= PARTIAL else "none"
    return {"evidence_ids": ids if strength != "none" else [], "strength": strength,
            "best": round(best, 3), "chunks": ranked}


def build(index: Index):
    def retrieve(s: CState) -> dict:
        cov = {r: _grade_req(index, s["job"], r, r) for r in s["reqs"]}
        return {"coverage": cov, "attempts": 0}

    def grade(s: CState) -> dict:
        return {"weak": [r for r, c in s["coverage"].items() if c["strength"] == "none"]}

    def requery(s: CState) -> dict:
        cov = dict(s["coverage"])
        skills = " ".join(s["job"].get("skills", []) or [])
        for r in s["weak"]:
            again = _grade_req(index, s["job"], r, f"{r} {skills} {s['job'].get('title', '')}")
            if again["best"] > cov[r]["best"]:
                cov[r] = again
        return {"coverage": cov, "attempts": s["attempts"] + 1}

    def route(s: CState) -> str:
        return "requery" if s["weak"] and s["attempts"] < 1 else END

    g = StateGraph(CState)
    g.add_node("retrieve", retrieve)
    g.add_node("grade", grade)
    g.add_node("requery", requery)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", route, ["requery", END])
    g.add_edge("requery", "grade")
    return g.compile()


def retrieve_with_coverage(job: dict, index: Index, k: int = 5,
                           requirements: list[str] | None = None) -> dict[str, Any]:
    reqs = requirements or heuristic_requirements(job)
    out = build(index).invoke({"job": job, "reqs": reqs})
    scored: dict[int, float] = {}
    for c in out["coverage"].values():
        for cid, s in c["chunks"]:
            if s >= PARTIAL:
                scored[cid] = max(scored.get(cid, -1e9), s)
    items = to_items(index, sorted(scored.items(), key=lambda x: -x[1]), k)
    coverage = {r: {"evidence_ids": c["evidence_ids"], "strength": c["strength"]}
                for r, c in out["coverage"].items()}
    return {"items": items, "coverage": coverage}


def retrieve(job: dict, index: Index, k: int = 5, requirements: list[str] | None = None):
    return retrieve_with_coverage(job, index, k, requirements)["items"]
