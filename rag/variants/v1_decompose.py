"""V1 requirement decomposition: one dense retrieval per requirement, merged with RRF."""
from rag.index.indexes import Index
from rag.variants.common import heuristic_requirements, rrf, to_items


def retrieve(job: dict, index: Index, k: int = 5, requirements: list[str] | None = None):
    reqs = requirements or heuristic_requirements(job)
    rankings = [[cid for cid, _ in index.dense(f"{job.get('title', '')}: {r}", 20)] for r in reqs]
    return to_items(index, rrf(rankings), k)
