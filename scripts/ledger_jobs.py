"""Recover per-job cost and LLM latency for the paid dev/test runs from the call ledger.

Why: the re-scored runs replayed from the LLM cache, so their per-job cost/latency read 0.
The ledger kept every real call (node, tokens, USD, end time, duration) in order. Jobs ran
sequentially; each starts with its analysis calls (analyst/risk/fit, in parallel), so a new job
begins when an analysis node follows a writing node or repeats within the current analysis
block. Segments are matched in order to the sorted job ids of each run. Latency = last call end
- first call start within the job (LLM-dominated wall time; retrieval overlaps the analysis calls).
Writes evals/results/cost_latency.json.
"""
import json
import statistics
from pathlib import Path

R = Path(__file__).resolve().parents[1] / "evals/results"
ANALYSIS = {"analyst", "risk_assessor", "fit_matcher"}
GRAPH = ANALYSIS | {"writer", "verifier", "critic", "compliance"}


def segments(rows):
    segs, cur, seen = [], [], set()
    for r in rows:
        n = r["node"]
        if n in ANALYSIS and cur and (n in seen or any(c["node"] not in ANALYSIS for c in cur)):
            segs.append(cur)
            cur, seen = [], set()
        cur.append(r)
        if n in ANALYSIS:
            seen.add(n)
    if cur:
        segs.append(cur)
    return segs


def pct(xs, q):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))], 2)


def stats(segs, ids, proposals):
    per = []
    for jid, s in zip(ids, segs, strict=True):
        start = min(r["ts"] - r["secs"] for r in s)
        per.append({"job_id": jid, "calls": len(s), "cost": round(sum(r["cost"] for r in s), 6),
                    "llm_secs": round(max(r["ts"] for r in s) - start, 2),
                    "tokens": sum(r["in"] + r["out"] for r in s),
                    "proposal": jid in proposals})
    props = [p for p in per if p["proposal"]]
    return {"n_jobs": len(per),
            "cost_per_job_usd": round(statistics.mean(p["cost"] for p in per), 5),
            "cost_per_proposal_usd": round(statistics.mean(p["cost"] for p in props), 5)
            if props else None,
            "latency_p50_s": pct([p["llm_secs"] for p in per], 0.5),
            "latency_p95_s": pct([p["llm_secs"] for p in per], 0.95),
            "proposal_latency_p95_s": pct([p["llm_secs"] for p in props], 0.95)
            if props else None,
            "tokens_per_job": round(statistics.mean(p["tokens"] for p in per)),
            "per_job": per}


def main():
    rows = [json.loads(line) for line in (R / "llm_ledger.jsonl").read_text().splitlines()]
    graph = [(i, r) for i, r in enumerate(rows) if r["node"] in GRAPH | {"sim_client"}]
    # run boundaries (by ledger position): smoke = first 7 calls; dev = after the smoke's sim
    # call + 1 aborted call until the 10 sim calls; test = the rest (aborted part + final part).
    sims = [k for k, (_, r) in enumerate(graph) if r["node"] == "sim_client"]
    dev_rows = [r for _, r in graph[sims[0] + 2:sims[1]]]
    test_rows = [r for _, r in graph[sims[1]:] if r["node"] in GRAPH]
    out = {}
    for name, rws in (("dev", dev_rows), ("test", test_rows)):
        res = json.loads((R / f"decision_eval_{name}_openai.json").read_text())
        ids = res["meta"]["jobs"]
        props = {r["job_id"] for r in res["rows"] if r["proposal"]}
        segs = segments(rws)
        if len(segs) != len(ids):
            raise SystemExit(f"{name}: {len(segs)} segments for {len(ids)} jobs")
        out[name] = stats(segs, ids, props)
        print(name, {k: v for k, v in out[name].items() if k != "per_job"})
    out["method"] = __doc__.strip().splitlines()[0]
    (R / "cost_latency.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
