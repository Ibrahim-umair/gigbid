"""R&D question C: is the multi-agent graph worth it?

    GIGBID_LLM=openai python -m evals.runners.arch_compare --system react --split dev
    GIGBID_LLM=openai python -m evals.runners.arch_compare --system supervisor --split dev

(a) one prebuilt ReAct agent holding all read tools, (b) a prebuilt supervisor
(langgraph-supervisor) over a researcher + writer, compared with (c) the hand-built bid graph
(evals/results/decision_eval_dev_openai.json). Same model, same MCP tools, same jobs, same
GigSim scoring. Paid calls go through a callback that enforces a hard cap and writes the ledger.
Baselines have no human-approval step; the harness submits their proposals as if approved.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import time

from langchain_core.callbacks import AsyncCallbackHandler
from pydantic import BaseModel, Field

from agent.config import ROOT, model_for
from agent.guards import compliance_scan
from agent.handoffs import Claim
from agent.llm import LEDGER, BudgetExceeded, _price, load_prompt
from evals.runners.decision_eval import _isolate, score

READ_TOOLS = {"get_client_history", "match_requirements", "search_evidence", "get_case_study",
              "get_connects_balance"}


class BidOutcome(BaseModel):
    action: str = Field(description="bid | watch | skip")
    is_scam: bool = False
    injection_detected: bool = False
    fit: float = Field(0.0, ge=0, le=1)
    price_type: str = "fixed"
    price_amount: float | None = None
    proposal: str = ""
    claims: list[Claim] = Field(default_factory=list)


class Budget(AsyncCallbackHandler):
    def __init__(self, cap: int, tag: str):
        self.cap, self.tag = cap, tag
        self.calls, self.tin, self.tout, self.cost = 0, 0, 0, 0.0

    async def on_chat_model_start(self, *a, **kw):
        if self.calls >= self.cap:
            raise BudgetExceeded(f"{self.tag}: cap {self.cap} reached")
        self.calls += 1

    async def on_llm_end(self, response, **kw):
        model = model_for("writer")
        for gens in response.generations:
            for g in gens:
                um = getattr(getattr(g, "message", None), "usage_metadata", None) or {}
                tin, tout = um.get("input_tokens", 0), um.get("output_tokens", 0)
                c = _price(model, tin, tout)
                self.tin, self.tout, self.cost = self.tin + tin, self.tout + tout, self.cost + c
                with LEDGER.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": time.time(), "node": self.tag, "model": model,
                                        "prompt": self.tag, "in": tin, "out": tout,
                                        "cost": round(c, 6), "secs": 0}) + "\n")

    def snap(self):
        return self.calls, self.tin, self.tout, self.cost


def _sys(name: str) -> str:
    return load_prompt(name)[1]


def _build(system: str, model, tools):
    from langgraph.prebuilt import create_react_agent
    if system == "react":
        return create_react_agent(model, tools, prompt=_sys("react_single"),
                                  response_format=BidOutcome)
    from langgraph_supervisor import create_supervisor
    research_tools = {"get_client_history", "match_requirements", "search_evidence"}
    researcher = create_react_agent(model, [t for t in tools if t.name in research_tools],
                                    prompt=_sys("researcher_agent"), name="researcher")
    writer = create_react_agent(model, [t for t in tools if t.name == "get_case_study"],
                                prompt=_sys("writer_agent"), name="writer")
    from langgraph.prebuilt.chat_agent_executor import AgentStateWithStructuredResponse
    # the outer supervisor graph only keeps `messages` unless the schema carries
    # `structured_response` (otherwise the final decision is silently dropped)
    return create_supervisor([researcher, writer], model=model, prompt=_sys("supervisor"),
                             response_format=BidOutcome,
                             state_schema=AgentStateWithStructuredResponse).compile()


async def run(system: str, ids: list[str], gold: dict, jobs: dict, cap: int) -> dict:
    from langchain_mcp_adapters.tools import load_mcp_tools
    from langchain_openai import ChatOpenAI

    from agent.mcp_client import ToolHub, set_hub
    budget = Budget(cap, f"arch_{system}")
    model = ChatOpenAI(model=model_for("writer"), timeout=90, max_retries=1)
    user_t = load_prompt("react_single" if system == "react" else "supervisor")[2]
    rows = []
    async with ToolHub("memory") as h:
        set_hub(h)
        tools = [t for s in ("portfolio", "marketplace")
                 for t in await load_mcp_tools(h.sessions[s]) if t.name in READ_TOOLS]
        agent = _build(system, model, tools)
        for jid in ids:
            job = await h.call("scout", "get_job", {"job_id": jid})
            c0, i0, o0, k0 = budget.snap()
            t0 = time.perf_counter()
            msg = user_t.replace("{{job}}", json.dumps(job, ensure_ascii=False)[:4000])
            err, out = None, BidOutcome(action="skip")
            try:
                res = await agent.ainvoke({"messages": [("user", msg)]},
                                          {"callbacks": [budget], "recursion_limit": 30})
                if res.get("structured_response") is None:
                    err = "no structured_response returned (decision missing)"
                else:
                    out = res["structured_response"]
            except BudgetExceeded:
                print(f"{system}: call cap reached at {jid}; scoring completed jobs", flush=True)
                break
            except Exception as e:  # noqa: BLE001 - record and continue
                err = repr(e)[:300]
            c1, i1, o1, k1 = budget.snap()
            text = out.proposal or ""
            sub = None
            if out.action == "bid" and len(text) >= 200:
                try:
                    sub = await h.call("submitter", "submit_proposal", {
                        "job_id": jid, "cover_letter": text[:5000],
                        "bid_type": "hourly" if out.price_type == "hourly" else "fixed",
                        "bid_amount": max(out.price_amount or 150, 1),
                        "idempotency_key": f"{system}:{jid}:"
                                           + hashlib.sha1(text.encode()).hexdigest()[:10]})
                except Exception as e:  # noqa: BLE001
                    err = f"submit failed: {e!r}"[:300]
            rows.append({
                "job_id": jid, "status": "submitted" if sub else (out.action or "skip"),
                "action": out.action, "fit": out.fit,
                "risk": {"is_scam": out.is_scam, "injection_detected": out.injection_detected},
                "price": {"type": out.price_type, "amount": out.price_amount}
                if out.price_amount else None,
                "unsupported_before": None, "claims": len(out.claims), "revisions": 0,
                "compliance": {"violations_in_output": compliance_scan(text)},
                "proposal": text, "submission": sub, "errors": [err] if err else [],
                "secs": round(time.perf_counter() - t0, 2),
                "usage": {"calls": c1 - c0, "in": i1 - i0, "out": o1 - o0,
                          "cost": round(k1 - k0, 6)}})
            print(f"{system} {jid:<12} act={out.action} scam={out.is_scam} calls={c1 - c0} "
                  f"${k1 - k0:.4f} {rows[-1]['secs']}s {err or ''}", flush=True)
        adv = await h.call("evaluator", "sim_advance", {})
    outcome = {a["job_id"]: a["status"] for a in adv["advanced"]}
    for r in rows:
        r["outcome"] = outcome.get(r["job_id"])
    res = score(rows, gold, jobs)
    res["summary"]["compliance_violations_in_output"] = sum(
        bool(r["compliance"]["violations_in_output"]) for r in rows if r["proposal"])
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", choices=["react", "supervisor"], required=True)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--max-calls", type=int, default=250)
    ap.add_argument("--jobs", default="", help="comma-separated ids or @file.json (list)")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    _isolate(f"arch-{args.system}{args.tag}")
    from evals.runners.rag_eval import load_gold, load_jobs
    gold, jobs = load_gold(), load_jobs()
    if args.jobs.startswith("@"):
        ids = json.loads(open(args.jobs[1:]).read())
    elif args.jobs:
        ids = args.jobs.split(",")
    else:
        ids = sorted(j for j, g in gold.items() if g["split"] == args.split)
    res = asyncio.run(run(args.system, ids, gold, jobs, args.max_calls))
    res["meta"] = {"system": args.system, "split": args.split, "model": model_for("writer"),
                   "ts": time.strftime("%Y-%m-%d %H:%M"), "backend": os.getenv("GIGBID_LLM")}
    out = ROOT / f"evals/results/arch_{args.system}_{args.split}{args.tag}.json"
    out.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res["summary"], indent=1))


if __name__ == "__main__":
    main()
