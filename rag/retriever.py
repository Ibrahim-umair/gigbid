"""Variant factory: the deployed variant is chosen by config (retrieval.variant), set from
evals/results/rag_eval.json, not by default."""
from __future__ import annotations

import functools
import importlib

from agent.config import cfg
from rag.index.indexes import get_index

VARIANTS = {
    "v0_naive": ("rag.variants.v0_naive", {}),
    "v1_decompose": ("rag.variants.v1_decompose", {}),
    "v2_hybrid_only": ("rag.variants.v2_hybrid", {"decompose": False}),  # ablation
    "v2_hybrid": ("rag.variants.v2_hybrid", {}),
    "v3_rerank_nodecomp": ("rag.variants.v3_rerank", {"decompose": False}),  # ablation
    "v3_rerank": ("rag.variants.v3_rerank", {}),
    "v4_outcome": ("rag.variants.v4_outcome", {}),
    "v8_corrective": ("rag.variants.v8_corrective", {}),
}


def get_retriever(variant: str | None = None):
    mod, kwargs = VARIANTS[variant or cfg("retrieval", "variant")]
    fn = importlib.import_module(mod).retrieve
    return functools.partial(fn, **kwargs)


def search(job: dict, requirements: list[str] | None = None, persona: str = "ml_engineer",
           k: int | None = None, variant: str | None = None) -> list[dict]:
    return get_retriever(variant)(job, get_index(persona), k=k or cfg("retrieval", "k"),
                                  requirements=requirements)
