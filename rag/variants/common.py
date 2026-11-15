"""Shared helpers: requirement decomposition fallback, RRF, chunk->item aggregation."""
from __future__ import annotations

import html
import re

from rag.index.indexes import Index

SKILL_HINT = re.compile(
    r"\b(python|pytorch|tensorflow|llm|gpt|openai|rag|langchain|chatbot|nlp|vision|yolo|"
    r"fastapi|api|sql|dashboard|pandas|scrap|react|android|ios|flutter|php|laravel|shopify|"
    r"wordpress|figma|design|whatsapp|sms|voice|speech|tts|stt|aws|docker|deploy|data|model|"
    r"train|fine[- ]?tun|hugging|embedding|vector|automation|integrat|excel|bookkeep|seo)\w*",
    re.I)


def heuristic_requirements(job: dict, max_n: int = 6) -> list[str]:
    """Zero-LLM requirement decomposition (used by fake LLM and the offline RAG eval)."""
    text = html.unescape(f"{job.get('title', '')}. {job.get('description', '')}")
    parts = re.split(r"(?<=[.!?;:])\s+|\n+|\s[-•*]\s", text)
    reqs = [p.strip(" -•*") for p in parts if SKILL_HINT.search(p) and 4 <= len(p.split()) <= 45]
    seen, out = set(), []
    for r in reqs:
        key = r.lower()[:60]
        if key not in seen:
            seen.add(key)
            out.append(r)
    from agent.config import cfg
    return out[:cfg("retrieval", "max_requirements", default=max_n)] or [job.get("title", "")]


def rrf(rankings: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])


def to_items(index: Index, scored_chunks: list[tuple[int, float]], k: int) -> list[dict]:
    """Collapse chunk hits to evidence items (max score per item)."""
    best: dict[str, float] = {}
    snippet: dict[str, str] = {}
    for cid, s in scored_chunks:
        iid = index.chunks[cid]["item_id"]
        if iid not in best or s > best[iid]:
            best[iid] = s
            snippet[iid] = index.chunks[cid]["text"][:400]
    ranked = sorted(best.items(), key=lambda x: -x[1])[:k]
    out = []
    for iid, s in ranked:
        it = index.items[iid]
        out.append({"id": iid, "type": it["type"], "title": it["title"], "score": round(s, 4),
                    "snippet": snippet[iid], "date": it.get("date"),
                    "client_industry": it.get("client_industry"), "skills": it.get("skills", []),
                    "source": f"portfolio://{it['type']}/{iid}"})
    return out


def job_query(job: dict) -> str:
    return html.unescape(f"{job.get('title', '')}. {job.get('description', '')}")[:2000]
