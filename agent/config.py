from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


@functools.lru_cache
def load_config(path: str | None = None) -> dict[str, Any]:
    p = Path(path or os.getenv("GIGBID_CONFIG", ROOT / "agent/config.yaml"))
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def cfg(*keys: str, default: Any = None) -> Any:
    node: Any = load_config()
    for k in keys:
        if not isinstance(node, dict) or k not in node:
            return default
        node = node[k]
    return node


def model_for(node: str) -> str:
    prof = cfg("models", "profiles", cfg("models", "profile"))
    return prof.get("nodes", {}).get(node) or prof["default"]


def fallback_model() -> str | None:
    return cfg("models", "profiles", cfg("models", "profile"), "fallback")
