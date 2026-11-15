"""Single entry point for every LLM call.

* Prompts come from agent/prompts/<name>.md (no inline prompts).
* Model per node comes from config (route by node), never from code.
* Backend `fake` returns deterministic, schema-valid outputs (agent/fake_llm.py): tests and graph
  development cost 0 paid calls. Backend `openai` makes real calls.
* Every real call is cached (sqlite) so re-runs of unchanged prompts are free, counted against a
  hard cap (llm.max_paid_calls), and appended to a cost ledger (evals/results/llm_ledger.jsonl).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from agent.config import ROOT, cfg, fallback_model, model_for

T = TypeVar("T", bound=BaseModel)
PROMPTS = ROOT / "agent/prompts"
LEDGER = ROOT / "evals/results/llm_ledger.jsonl"
_lock = threading.Lock()
_paid_calls = 0


class BudgetExceeded(RuntimeError):
    pass


def backend() -> str:
    return os.getenv("GIGBID_LLM", cfg("llm", "backend", default="fake"))


def load_prompt(name: str) -> tuple[str, str, str]:
    """Return (version, system, user_template). File format: front line `version: x`,
    then system text, then a line `---user---`, then the user template with {{var}} slots."""
    raw = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    first, _, rest = raw.partition("\n")
    version = first.split(":", 1)[1].strip() if first.startswith("version:") else "0"
    system, _, user = rest.partition("---user---")
    return version, system.strip(), user.strip()


def render(template: str, variables: dict[str, Any]) -> str:
    out = template
    for k, v in variables.items():
        if not isinstance(v, str):
            v = json.dumps(v, ensure_ascii=False, indent=1, default=str)
        out = out.replace("{{" + k + "}}", v)
    return out


def _cache() -> sqlite3.Connection:
    path = ROOT / cfg("llm", "cache")
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.execute("create table if not exists c (k text primary key, v text)")
    return con


def _price(model: str, tin: int, tout: int) -> float:
    p = cfg("models", "pricing_usd_per_mtok", model, default={"in": 0, "out": 0})
    return (tin * p["in"] + tout * p["out"]) / 1e6


def paid_calls() -> int:
    return _paid_calls


async def structured(node: str, prompt: str, variables: dict[str, Any], schema: type[T],
                     ctx: dict[str, Any] | None = None) -> tuple[T, dict]:
    """Call the model for `node` with prompt file `prompt`; return (parsed, usage)."""
    version, system, user_t = load_prompt(prompt)
    user = render(user_t, variables)
    model = model_for(node)
    t0 = time.perf_counter()

    if backend() == "fake":
        from agent.fake_llm import fake_response
        obj = fake_response(schema, {**variables, **(ctx or {})})
        return obj, {node: {"calls": 1, "in": 0, "out": 0, "cost": 0.0,
                            "secs": time.perf_counter() - t0}}

    key = hashlib.sha256(f"{model}|{prompt}@{version}|{schema.__name__}|{system}|{user}"
                         .encode()).hexdigest()
    con = _cache()
    row = con.execute("select v from c where k=?", (key,)).fetchone()
    if row:  # cache hit: no paid call, but report the original call's tokens and cost
        data = json.loads(row[0])
        if isinstance(data, dict) and "__obj" in data:
            u = data["__u"]
            return schema.model_validate(data["__obj"]), {
                node: {"calls": 0, "in": u["in"], "out": u["out"], "cost": u["cost"],
                       "secs": 0.0}}
        return schema.model_validate(data), {
            node: {"calls": 0, "in": 0, "out": 0, "cost": 0.0, "secs": 0.0}}

    obj, tin, tout, used = await _call_openai(node, model, system, user, schema)
    secs = time.perf_counter() - t0
    cost = _price(used, tin, tout)
    with _lock:
        con.execute("insert or replace into c values (?,?)", (key, json.dumps(
            {"__obj": obj.model_dump(mode="json"),
             "__u": {"in": tin, "out": tout, "cost": cost, "secs": secs}})))
        con.commit()
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "node": node, "model": used, "prompt": prompt,
                                "in": tin, "out": tout, "cost": round(cost, 6),
                                "secs": round(secs, 2)}) + "\n")
    return obj, {node: {"calls": 1, "in": tin, "out": tout, "cost": cost, "secs": secs}}


async def _call_openai(node: str, model: str, system: str, user: str, schema: type[T]):
    global _paid_calls
    from langchain_openai import ChatOpenAI

    retries = cfg("llm", "retries", default=2)
    models = [model] + ([fallback_model()] if fallback_model() and fallback_model() != model
                        else [])
    last: Exception | None = None
    for m in models:
        for attempt in range(retries + 1):
            with _lock:
                if _paid_calls >= int(os.getenv("GIGBID_MAX_CALLS",
                                                cfg("llm", "max_paid_calls", default=200))):
                    raise BudgetExceeded(f"paid-call cap reached ({_paid_calls})")
                _paid_calls += 1
            try:
                llm = ChatOpenAI(model=m, timeout=cfg("llm", "timeout_s", default=60),
                                 max_retries=0)
                runnable = llm.with_structured_output(schema, method="function_calling",
                                                      include_raw=True)
                res = await runnable.ainvoke([("system", system), ("user", user)])
                if res.get("parsing_error") or res.get("parsed") is None:
                    raise ValueError(f"parse error: {res.get('parsing_error')}")
                um = getattr(res["raw"], "usage_metadata", None) or {}
                return res["parsed"], um.get("input_tokens", 0), um.get("output_tokens", 0), m
            except BudgetExceeded:
                raise
            except Exception as e:  # rate limit / 5xx / parse: bounded retry with backoff
                last = e
                await asyncio.sleep(min(2 ** attempt * 2, 20))
    raise RuntimeError(f"LLM call failed for node={node}: {last}")


def usage_totals(usage: dict) -> dict:
    tot = {"calls": 0, "in": 0, "out": 0, "cost": 0.0, "secs": 0.0}
    for u in (usage or {}).values():
        for k in tot:
            tot[k] += u.get(k, 0)
    tot["cost"] = round(tot["cost"], 6)
    return tot


def ledger_summary(path: Path = LEDGER) -> dict:
    if not path.exists():
        return {"calls": 0, "cost": 0.0}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return {"calls": len(rows), "cost": round(sum(r["cost"] for r in rows), 4),
            "in": sum(r["in"] for r in rows), "out": sum(r["out"] for r in rows)}
