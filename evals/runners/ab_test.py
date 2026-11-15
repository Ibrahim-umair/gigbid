"""Signature extension X2: proposal-strategy A/B test in GigSim.

    GIGBID_LLM=openai python -m evals.runners.ab_test --max-calls 120

Arm A = shipped writer prompt (agent/prompts/writer.md), outcomes from the main dev+test runs.
Arm B = question-first writer (agent/prompts/writer_b.md) on the same jobs that the graph chose
to bid on. Analysis nodes hit the LLM cache, so only writing/verification/critic/compliance and
the simulated client cost calls. Reply rates compared with a two-sided Fisher exact test.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from math import comb

from agent.config import ROOT

R = ROOT / "evals/results"
REPLY = {"replied", "interview", "hired"}


def fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """2x2 table [[a, b], [c, d]] (rows = arms, cols = replied / not)."""
    n1, n2, k = a + b, c + d, a + c
    n = n1 + n2

    def p(x):
        return comb(n1, x) * comb(n2, k - x) / comb(n, k)
    p0 = p(a)
    lo, hi = max(0, k - n2), min(k, n1)
    return min(1.0, sum(p(x) for x in range(lo, hi + 1) if p(x) <= p0 + 1e-12))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-calls", type=int, default=120)
    args = ap.parse_args()
    arm_a = []
    for f in ("decision_eval_dev_openai.json", "decision_eval_test_openai.json"):
        arm_a += [r for r in json.loads((R / f).read_text())["rows"] if r.get("submission")]
    ids = [r["job_id"] for r in arm_a]
    os.environ["GIGBID_WRITER_PROMPT"] = "writer_b"
    os.environ["GIGBID_MAX_CALLS"] = str(args.max_calls)
    from evals.runners.decision_eval import _isolate, run
    from evals.runners.rag_eval import load_gold, load_jobs
    _isolate("ab-writer_b")
    res_b = asyncio.run(run(ids, load_gold(), load_jobs()))
    arm_b = [r for r in res_b["rows"] if r.get("submission")]
    a_rep = sum(r["outcome"] in REPLY for r in arm_a)
    b_rep = sum(r["outcome"] in REPLY for r in arm_b)
    out = {"arm_a": {"prompt": "writer", "n": len(arm_a), "replied": a_rep,
                     "reply_rate": round(a_rep / len(arm_a), 3) if arm_a else None,
                     "hired": sum(r["outcome"] == "hired" for r in arm_a)},
           "arm_b": {"prompt": "writer_b", "n": len(arm_b), "replied": b_rep,
                     "reply_rate": round(b_rep / len(arm_b), 3) if arm_b else None,
                     "hired": sum(r["outcome"] == "hired" for r in arm_b),
                     "unsupported_before_verify": res_b["summary"][
                         "unsupported_claims_per_proposal_before_verify"],
                     "cost_per_proposal_usd": res_b["summary"]["cost_per_proposal_usd"]},
           "fisher_exact_p_two_sided": round(fisher_two_sided(
               a_rep, len(arm_a) - a_rep, b_rep, len(arm_b) - b_rep), 4),
           "jobs": ids, "rows_b": res_b["rows"]}
    (R / "ab_test_writer.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k not in {"rows_b", "jobs"}}, indent=1))


if __name__ == "__main__":
    main()
