"""V0 baseline: fixed chunks, top-k cosine on the whole job post."""
from rag.index.indexes import Index
from rag.variants.common import job_query, to_items


def retrieve(job: dict, index: Index, k: int = 5, requirements: list[str] | None = None):
    return to_items(index, index.dense(job_query(job), k=50), k)
