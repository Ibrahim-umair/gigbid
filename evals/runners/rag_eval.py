"""Retrieval eval over all variants (zero LLM calls). Writes evals/results/rag_eval.json + .csv.

    python -m evals.runners.rag_eval [--split dev|test|all]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time

from agent.config import ROOT
from rag.index.indexes import get_index
from rag.retriever import VARIANTS, search
from rag.variants.common import heuristic_requirements

OUT = ROOT / "evals/results"


def load_jobs() -> dict[str, dict]:
    jobs = {}
    for f in ["data/processed/jobs_real_dev.json", "data/processed/jobs_real_test.json",
              "data/gigsim_seed/jobs_synthetic.json"]:
        for j in json.loads((ROOT / f).read_text(encoding="utf-8")):
            jobs[j["job_id"]] = j
    return jobs


def load_gold() -> dict[str, dict]:
    gold = json.loads((ROOT / "evals/datasets/gold_real.json").read_text(encoding="utf-8"))
    gold.update(json.loads((ROOT / "data/gigsim_seed/gold_synthetic.json")
                           .read_text(encoding="utf-8")))
    return gold


def metrics(ranked: list[str], gold: list[str]) -> dict:
    g = set(gold)
    r5 = len(g & set(ranked[:5])) / len(g)
    mrr = next((1 / (i + 1) for i, x in enumerate(ranked) if x in g), 0.0)
    dcg = sum(1 / math.log2(i + 2) for i, x in enumerate(ranked[:10]) if x in g)
    idcg = sum(1 / math.log2(i + 2) for i in range(min(len(g), 10)))
    return {"recall@5": r5, "mrr": mrr, "ndcg@10": dcg / idcg}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--variants", default=",".join(VARIANTS))
    args = ap.parse_args()
    jobs, gold = load_jobs(), load_gold()
    ids = [j for j, g in gold.items() if g.get("relevant_evidence")
           and (args.split == "all" or g["split"] == args.split)]
    get_index()
    results, per_job = {}, []
    for v in args.variants.split(","):
        rows, t0 = [], time.perf_counter()
        for jid in ids:
            ranked = [x["id"] for x in search(jobs[jid], variant=v, k=10)]
            m = metrics(ranked, gold[jid]["relevant_evidence"])
            nreq = len(heuristic_requirements(jobs[jid]))
            rows.append({**m, "job_id": jid, "n_req": nreq})
            per_job.append({"variant": v, "job_id": jid, "n_req": nreq, "top5": ranked[:5],
                            "gold": gold[jid]["relevant_evidence"], **m})
        secs = (time.perf_counter() - t0) / max(len(ids), 1)

        def avg(rs, k):
            return round(sum(r[k] for r in rs) / len(rs), 3) if rs else None
        many = [r for r in rows if r["n_req"] >= 4]
        results[v] = {"n_jobs": len(rows), **{k: avg(rows, k) for k in
                                               ["recall@5", "mrr", "ndcg@10"]},
                      "recall@5_jobs_4plus_req": avg(many, "recall@5"),
                      "n_jobs_4plus_req": len(many), "secs_per_job": round(secs, 2)}
        print(v, results[v], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"rag_eval_{args.split}.json").write_text(json.dumps(
        {"split": args.split, "variants": results, "per_job": per_job}, indent=1))
    with (OUT / f"rag_eval_{args.split}.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["variant", "n_jobs", "recall@5", "mrr", "ndcg@10", "recall@5_4plus_req",
                    "secs_per_job"])
        for v, r in results.items():
            w.writerow([v, r["n_jobs"], r["recall@5"], r["mrr"], r["ndcg@10"],
                        r["recall@5_jobs_4plus_req"], r["secs_per_job"]])


if __name__ == "__main__":
    main()
