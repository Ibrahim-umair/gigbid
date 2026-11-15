"""Long-term memory (C2/R7): a LangGraph store with two promoted namespaces.

  ("style", user)   - rules learned from the user's edits ("never say passionate")
  ("outcome", user) - what won / got replies per job category
Raw observations go to ("style_obs", user) / ("outcome_obs", user) staging namespaces; only
agent/memory/promotion_rules.py writes to the promoted namespaces. Raw tool output never does.
"""
from __future__ import annotations

import functools
import os

from agent.config import ROOT


@functools.lru_cache
def get_store():
    path = os.getenv("GIGBID_STORE", str(ROOT / "data/processed/memory.sqlite"))
    try:
        import sqlite3

        from langgraph.store.sqlite import SqliteStore
        store = SqliteStore(sqlite3.connect(path, check_same_thread=False, isolation_level=None))
        store.setup()
        return store
    except Exception:  # pragma: no cover - fallback keeps the app running
        from langgraph.store.memory import InMemoryStore
        return InMemoryStore()


def style_rules(user: str) -> list[str]:
    return [i.value["rule"] for i in get_store().search(("style", user), limit=50)]


def outcome_notes(user: str, category: str) -> dict | None:
    item = get_store().get(("outcome", user), category)
    return item.value if item else None


def forget(user: str, namespace: str, key: str):
    """User-facing delete (memory viewer)."""
    get_store().delete((namespace, user), key)


def list_memory(user: str) -> dict:
    s = get_store()
    return {ns: [{"key": i.key, **i.value} for i in s.search((ns, user), limit=100)]
            for ns in ("style", "outcome")}
