"""V3 cross-encoder reranking over the V2 candidate pool (open CPU reranker).
Each requirement reranks the pool; an item's score is its best score across requirements, plus a
small bonus for covering several requirements."""
from rag.index.indexes import Index
from rag.variants.common import heuristic_requirements, to_items
from rag.variants.v2_hybrid import candidates


def retrieve(job: dict, index: Index, k: int = 5, requirements: list[str] | None = None,
             decompose: bool = True, pool: int | None = None):
    from agent.config import cfg
    pool = pool or cfg("retrieval", "rerank_pool", default=12)
    reqs = requirements or heuristic_requirements(job)
    cand = [cid for cid, _ in candidates(job, index, reqs, decompose)][:pool]
    best: dict[int, float] = {}
    hits: dict[str, int] = {}
    for r in (reqs if decompose else [job.get("title", "") + ". " + " ".join(reqs)]):
        for rank, (cid, s) in enumerate(index.rerank(f"{job.get('title', '')}: {r}", cand)):
            best[cid] = max(best.get(cid, -1e9), s)
            if rank < 3:
                iid = index.chunks[cid]["item_id"]
                hits[iid] = hits.get(iid, 0) + 1
    scored = [(cid, s + 0.5 * hits.get(index.chunks[cid]["item_id"], 0))
              for cid, s in best.items()]
    return to_items(index, sorted(scored, key=lambda x: -x[1]), k)
