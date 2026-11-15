"""Ingest the user's GitHub repos into the portfolio through the official GitHub MCP server
(third-party server, A5). Writes repos/<id>/README.md + code files + an index.json entry, then the
portfolio index re-embeds incrementally (corpus-hash cache).

    GITHUB_TOKEN=... python -m rag.ingest.github owner/repo [owner/repo ...]

Status: implemented, not exercised in this build (no GitHub token configured); the persona's
repos were loaded from disk instead.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

from agent.config import ROOT

GITHUB_MCP = {"transport": "streamable_http", "url": "https://api.githubcopilot.com/mcp/",
              "headers": {"Authorization": f"Bearer {os.getenv('GITHUB_TOKEN', '')}"}}
CODE_EXT = (".py", ".ts", ".js", ".sql", ".ipynb")


async def ingest(repos: list[str], persona: str = "ml_engineer"):
    from langchain_mcp_adapters.client import MultiServerMCPClient
    client = MultiServerMCPClient({"github": GITHUB_MCP})
    base = ROOT / "data/personas" / persona / "repos"
    index = json.loads((base / "index.json").read_text()) if (base / "index.json").exists() else []
    async with client.session("github") as s:
        for full in repos:
            owner, name = full.split("/")
            rid = f"gh-{name}"
            folder = base / rid
            folder.mkdir(parents=True, exist_ok=True)
            readme = await s.call_tool("get_file_contents",
                                       {"owner": owner, "repo": name, "path": "README.md"})
            (folder / "README.md").write_text("".join(getattr(c, "text", "") for c in
                                                      readme.content), encoding="utf-8")
            listing = await s.call_tool("get_file_contents",
                                        {"owner": owner, "repo": name, "path": ""})
            files = json.loads("".join(getattr(c, "text", "") for c in listing.content) or "[]")
            for f in [f for f in files if f.get("name", "").endswith(CODE_EXT)][:5]:
                body = await s.call_tool("get_file_contents",
                                         {"owner": owner, "repo": name, "path": f["path"]})
                (folder / f["name"]).write_text("".join(getattr(c, "text", "") for c in
                                                        body.content), encoding="utf-8")
            index = [r for r in index if r["id"] != rid] + [
                {"id": rid, "name": name, "description": f"GitHub: {full}", "skills": [],
                 "date": None, "related_case_study": None, "synthetic": False}]
    (base / "index.json").write_text(json.dumps(index, indent=1))


if __name__ == "__main__":
    asyncio.run(ingest(sys.argv[1:]))
