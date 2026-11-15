"""Dense (fastembed, open model on CPU) + BM25 + cross-encoder, cached on disk by corpus hash."""
from __future__ import annotations

import functools
import hashlib
import json
import re

import numpy as np
from rank_bm25 import BM25Okapi

from agent.config import ROOT, cfg
from rag.ingest.loaders import chunk, load_items

CACHE = ROOT / "data/processed/index"


def tokenize(text: str) -> list[str]:
    # keep library names like "yolov8", "pgvector", "next.js" intact
    return re.findall(r"[a-z0-9][a-z0-9.+#_-]*[a-z0-9+#]|[a-z0-9]", text.lower())


@functools.lru_cache
def embedder():
    from fastembed import TextEmbedding
    return TextEmbedding(cfg("models", "embeddings"))


@functools.lru_cache
def reranker():
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    return TextCrossEncoder(cfg("models", "reranker"))


def embed(texts: list[str]) -> np.ndarray:
    v = np.array(list(embedder().embed(texts)), dtype=np.float32)
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)


class Index:
    """Chunk-level index over one persona's evidence items."""

    def __init__(self, persona: str = "ml_engineer"):
        self.persona = persona
        self.items = {i["id"]: i for i in load_items(persona)}
        self.chunks = [c for it in self.items.values() for c in chunk(it)]
        texts = [f"{self.items[c['item_id']]['title']}. {c['text']}" for c in self.chunks]
        h = hashlib.sha256((cfg("models", "embeddings") + json.dumps(texts)).encode()).hexdigest()
        path = CACHE / f"{persona}-{h[:16]}.npy"
        if path.exists():
            self.vecs = np.load(path)
        else:
            CACHE.mkdir(parents=True, exist_ok=True)
            self.vecs = embed(texts) if texts else np.zeros((0, 384), np.float32)
            np.save(path, self.vecs)
        self.bm25 = BM25Okapi([tokenize(t) for t in texts]) if texts else None
        self.texts = texts

    def dense(self, query: str, k: int = 20) -> list[tuple[int, float]]:
        if not len(self.chunks):
            return []
        s = self.vecs @ embed([query])[0]
        top = np.argsort(-s)[:k]
        return [(int(i), float(s[i])) for i in top]

    def sparse(self, query: str, k: int = 20) -> list[tuple[int, float]]:
        if self.bm25 is None:
            return []
        s = self.bm25.get_scores(tokenize(query))
        top = np.argsort(-s)[:k]
        return [(int(i), float(s[i])) for i in top if s[i] > 0]

    def rerank(self, query: str, chunk_ids: list[int]) -> list[tuple[int, float]]:
        """Cross-encoder scores, cached per (model, query, chunk) on disk: V3/V4/V8 and the live
        match_requirements tool share most pairs, and CPU reranking is the slowest step."""
        if not chunk_ids:
            return []
        con = _rerank_cache()
        model = cfg("models", "reranker")
        keys = {i: hashlib.sha1(f"{model}|{query}|{self.texts[i]}".encode()).hexdigest()
                for i in chunk_ids}
        got = dict(con.execute(
            f"select k, s from r where k in ({','.join('?' * len(keys))})",
            list(keys.values())).fetchall())
        todo = [i for i in chunk_ids if keys[i] not in got]
        if todo:
            new = list(reranker().rerank(query, [self.texts[i] for i in todo]))
            con.executemany("insert or replace into r values (?,?)",
                            [(keys[i], float(s)) for i, s in zip(todo, new, strict=True)])
            con.commit()
            got.update({keys[i]: float(s) for i, s in zip(todo, new, strict=True)})
        return sorted(((i, got[keys[i]]) for i in chunk_ids), key=lambda x: -x[1])


@functools.lru_cache
def _rerank_cache():
    import sqlite3
    CACHE.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(CACHE / "rerank_cache.sqlite", check_same_thread=False)
    con.execute("create table if not exists r (k text primary key, s real)")
    return con


@functools.lru_cache
def get_index(persona: str = "ml_engineer") -> Index:
    return Index(persona)
