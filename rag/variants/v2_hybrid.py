"""V2 hybrid: BM25 + dense per requirement, fused with reciprocal rank fusion.
`decompose=False` gives the hybrid-only ablation (whole post as one query)."""
from rag.index.indexes import Index
from rag.variants.common import heuristic_requirements, job_query, rrf, to_items


def candidates(job: dict, index: Index, requirements: list[str] | None, decompose: bool = True,
               per_query: int = 20) -> list[tuple[int, float]]:
    queries = ([f"{job.get('title', '')}: {r}" for r in
                (requirements or heuristic_requirements(job))] if decompose else [job_query(job)])
    rankings = []
    for q in queries:
        rankings.append([cid for cid, _ in index.dense(q, per_query)])
        rankings.append([cid for cid, _ in index.sparse(q, per_query)])
    return rrf(rankings)


def retrieve(job: dict, index: Index, k: int = 5, requirements: list[str] | None = None,
             decompose: bool = True):
    return to_items(index, candidates(job, index, requirements, decompose), k)
