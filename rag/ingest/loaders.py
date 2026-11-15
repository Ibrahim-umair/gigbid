"""Load a persona corpus into evidence items + past proposals (B1).

Item metadata: persona, type, project, skills, date, client_industry, outcome (proposals).
Repo code is ingested alongside the README (README-only retrieval misses skills shown in code).
GitHub repos can be added through the GitHub MCP server (rag/ingest/github.py); the persona's
repos are read from disk here.
"""
from __future__ import annotations

import json
import re

import yaml

from agent.config import ROOT

PERSONAS = ROOT / "data/personas"


def _frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if not m:
        return {}, text
    return yaml.safe_load(m.group(1)) or {}, m.group(2)


def load_items(persona: str = "ml_engineer") -> list[dict]:
    base = PERSONAS / persona
    items: list[dict] = []
    if (base / "cv.md").exists():
        items.append({"id": "cv", "type": "cv", "title": "CV", "persona": persona,
                      "text": (base / "cv.md").read_text(encoding="utf-8"), "skills": [],
                      "date": None, "project": None, "client_industry": None})
    for f in sorted((base / "case_studies").glob("*.md")):
        meta, body = _frontmatter(f.read_text(encoding="utf-8"))
        items.append({"id": meta.get("id", f.stem), "type": "case_study", "persona": persona,
                      "title": meta.get("title", f.stem), "text": body.strip(),
                      "skills": meta.get("skills", []), "date": str(meta.get("date", "")),
                      "project": meta.get("id", f.stem),
                      "client_industry": meta.get("client_industry")})
    idx = base / "repos/index.json"
    for r in json.loads(idx.read_text(encoding="utf-8")) if idx.exists() else []:
        folder = base / "repos" / r["id"]
        readme = (folder / "README.md").read_text(encoding="utf-8") if (
            folder / "README.md").exists() else ""
        code = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                         for p in sorted(folder.glob("*")) if p.suffix in {".py", ".js", ".ts",
                                                                          ".sql", ".ipynb"})
        items.append({"id": r["id"], "type": "repo", "persona": persona,
                      "title": r.get("name", r["id"]), "readme": readme, "code": code,
                      "text": f"{r.get('description', '')}\n{readme}\n{code}",
                      "skills": r.get("skills", []), "date": str(r.get("date", "")),
                      "project": r.get("related_case_study") or r["id"],
                      "client_industry": None})
    rev = base / "reviews.json"
    for r in json.loads(rev.read_text(encoding="utf-8")) if rev.exists() else []:
        items.append({"id": r["id"], "type": "review", "persona": persona,
                      "title": f"Review ({r.get('client_industry')})", "text": r["text"],
                      "skills": [], "date": str(r.get("date", "")),
                      "project": r.get("project_ref"),
                      "client_industry": r.get("client_industry"), "rating": r.get("rating")})
    return items


def load_proposals(persona: str = "ml_engineer") -> list[dict]:
    p = PERSONAS / persona / "proposals.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def load_profile(persona: str = "ml_engineer") -> dict:
    p = PERSONAS / persona / "profile.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def chunk(item: dict, words: int = 120, overlap: int = 20) -> list[dict]:
    """Fixed-size word chunks (V0 baseline chunking)."""
    toks = item["text"].split()
    out, i, n = [], 0, 0
    while i < max(len(toks), 1):
        out.append({"chunk_id": f"{item['id']}#{n}", "item_id": item["id"],
                    "text": " ".join(toks[i:i + words])})
        i += words - overlap
        n += 1
    return out
