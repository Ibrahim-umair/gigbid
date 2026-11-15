"""Regenerate the results tables (README + report) from evals/results/*.json only.

    python scripts/build_results.py   -> evals/results/summary.json + evals/results/tables.md
"""
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1] / "evals/results"


def load(name):
    p = R / name
    return json.loads(p.read_text()) if p.exists() else None


def main():
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    rag = load("rag_eval_all.json")["variants"]
    dev = load("decision_eval_dev51_openai.json") or load("decision_eval_dev_openai.json")
    test = load("decision_eval_test_openai.json")
    judge = load("judge_claude.json")
    ledger = [json.loads(line) for line in (R / "llm_ledger.jsonl").read_text().splitlines()
              if line]
    out = ["### Retrieval (19 jobs with gold evidence, dev+test; no LLM)", "",
           "| Variant | Recall@5 | MRR | nDCG@10 | Recall@5 (jobs with ≥4 req.) | s/job |",
           "|---|---|---|---|---|---|"]
    for v, m in rag.items():
        out.append(f"| {v} | {m['recall@5']:.3f} | {m['mrr']:.3f} | {m['ndcg@10']:.3f} | "
                   f"{m['recall@5_jobs_4plus_req']:.3f} | {m['secs_per_job']:.2f} |")
    keys = [("bid_f1", "Bid/skip F1"), ("bid_precision", "Bid precision"),
            ("bid_recall", "Bid recall"), ("scam_precision", "Scam precision"),
            ("scam_recall", "Scam recall"), ("attack_success_rate", "Injection attack success"),
            ("price_in_fair_band", "Price in fair band"),
            ("unsupported_claims_per_proposal_before_verify",
             "Unsupported claims / proposal (before verification)"),
            ("critic_send_backs", "Critic send-backs"),
            ("compliance_blocked", "Compliance blocks"),
            ("gigsim_reply_rate", "GigSim reply rate"), ("gigsim_hire_rate", "GigSim hire rate"),
            ("latency_p50_s", "Latency p50 (s/job)"), ("latency_p95_s", "Latency p95 (s/job)"),
            ("cost_per_job_usd", "Cost / job analysed (USD)"),
            ("cost_per_proposal_usd", "Cost / proposal (USD)"),
            ("tokens_per_job", "Tokens / job"), ("llm_calls", "LLM calls"),
            ("n_jobs", "Jobs"), ("proposals", "Proposals drafted")]
    out += ["", "### End-to-end decisions (gpt-6-luna, shipped config)", "",
            f"| Metric | Dev ({(dev or {}).get('summary', {}).get('n_jobs')} jobs) | Test (held out) |", "|---|---|---|"]  # noqa: E501
    for k, label in keys:
        d = (dev or {}).get("summary", {}).get(k)
        t = (test or {}).get("summary", {}).get(k)
        out.append(f"| {label} | {d if d is not None else '—'} | "
                   f"{t if t is not None else '—'} |")
    cl = load("cost_latency.json")
    if cl:
        out += ["", "### Cost and latency of the paid runs (recovered from the call ledger)", "",
                "| Run | Cost/job (USD) | Cost/proposal (USD) | p50 s/job | p95 s/job | "
                "p95 s/proposal | Tokens/job |", "|---|---|---|---|---|---|---|"]
        for k in ("dev", "test"):
            c = cl[k]
            out.append(f"| {k} | {c['cost_per_job_usd']} | {c['cost_per_proposal_usd']} | "
                       f"{c['latency_p50_s']} | {c['latency_p95_s']} | "
                       f"{c['proposal_latency_p95_s']} | {c['tokens_per_job']} |")
    tg = load("tool_granularity.json")
    if tg:
        out += ["", f"### R&D A: tool granularity (40 tasks, {tg['model']})", "",
                "| Tool set | # tools | Tool-selection acc. | Argument acc. | Unsafe submits "
                "| Input tokens/task |", "|---|---|---|---|---|---|"]
        for k, v in tg["results"].items():
            out.append(f"| {k} | {v['tools']} | {v['tool_selection_acc']} | "
                       f"{v['argument_acc']} | {v['unsafe_submit_calls']} | "
                       f"{v['input_tokens_per_task']} |")
    arch = {"react": load("arch_react_dev51.json") or load("arch_react_dev.json"),
            "supervisor": load("arch_supervisor_dev51.json")}
    if any(arch.values()):
        cols = [("bid_f1", "Bid/skip F1"), ("scam_recall", "Scam recall"),
                ("scam_precision", "Scam precision"),
                ("attack_success_rate", "Injection attack success"),
                ("price_in_fair_band", "Price in band"), ("proposals", "Proposals"),
                ("gigsim_reply_rate", "GigSim reply rate"),
                ("cost_per_job_usd", "Cost/job (USD)"), ("tokens_per_job", "Tokens/job"),
                ("latency_p50_s", "p50 s/job"), ("latency_p95_s", "p95 s/job")]
        g = dict((dev or {}).get("summary", {}))
        if cl and not load("decision_eval_dev51_openai.json"):
            g.update({k: cl["dev"][k] for k in ("cost_per_job_usd", "tokens_per_job",
                                                "latency_p50_s", "latency_p95_s")})
        out += ["", "### R&D C: single agent vs prebuilt supervisor vs hand-built graph "
                    f"({g.get('n_jobs')} dev jobs)", "",
                "| Metric | (a) ReAct, all tools | (b) Supervisor (pending) | (c) GigBid graph |",  # noqa: E501
                "|---|---|---|---|"]
        for k, label in cols:
            vals = [((arch[a] or {}).get("summary", {})).get(k, "—") for a in
                    ("react", "supervisor")]
            out.append(f"| {label} | {vals[0]} | {vals[1]} | {g.get(k, '—')} |")
        jsum = (judge or {}).get("summary", {})
        for k, label in (("unsupported_claims_per_proposal", "Judge: unsupported claims/proposal"),
                         ("mean_rubric", "Judge: mean rubric"),
                         ("policy_flags", "Judge: genuine policy violations")):
            v = [jsum.get(sy, {}).get(k, "—") for sy in ("react", "supervisor", "graph")]
            out.append(f"| {label} | {v[0]} | {v[1]} | {v[2]} |")
    sp = None if arch["supervisor"] else load("arch_supervisor_dev_partial.json")
    if sp:
        out += ["", f"### R&D C (partial): same {sp['n_jobs']} dev jobs, supervisor stopped early "
                    "to save cost", "", "| Metric | (a) ReAct | (b) Supervisor | (c) Graph |",
                "|---|---|---|---|"]
        for k, label in (("bid_skip_accuracy", "Bid/skip accuracy"),
                         ("calls_per_job", "LLM calls/job"), ("cost_per_job_usd", "Cost/job (USD)"),
                         ("secs_per_job", "Seconds/job")):
            v = sp[k]
            out.append(f"| {label} | {v['react']} | {v['supervisor']} | {v['graph']} |")
    ab = load("ab_test_writer.json")
    if ab:
        out += ["", "### X2: proposal strategy A/B in GigSim", "",
                "| Arm | Prompt | Proposals | Replied | Reply rate | Hired |",
                "|---|---|---|---|---|---|"]
        for k in ("arm_a", "arm_b"):
            v = ab[k]
            out.append(f"| {k[-1].upper()} | {v['prompt']} | {v['n']} | {v['replied']} | "
                       f"{v['reply_rate']} | {v['hired']} |")
        out += ["", f"Fisher exact test (two-sided) p = {ab['fisher_exact_p_two_sided']}."]
    if judge:
        out += ["", "### Proposal judge (Claude, independent of the runtime model; uncalibrated)",
                "", "| System | Proposals | Unsupported/proposal | Partly supported/proposal | "
                "Mean rubric | Policy flags |", "|---|---|---|---|---|---|"]
        for sy, v in judge["summary"].items():
            out.append(f"| {sy} | {v.get('n')} | {v.get('unsupported_claims_per_proposal')} | "
                       f"{v.get('partly_supported_per_proposal')} | {v.get('mean_rubric')} | "
                       f"{v.get('policy_flags')} |")
    total = round(sum(r["cost"] for r in ledger), 4)
    out += ["", f"Paid LLM usage for everything above: {len(ledger)} calls, "
                f"${total} (evals/results/llm_ledger.jsonl)."]
    (R / "tables.md").write_text("\n".join(out), encoding="utf-8")
    (R / "summary.json").write_text(json.dumps({
        "rag": rag, "dev": (dev or {}).get("summary"), "test": (test or {}).get("summary"),
        "judge": (judge or {}).get("summary"), "cost_latency": {
            k: {kk: vv for kk, vv in (cl or {}).get(k, {}).items() if kk != "per_job"}
            for k in ("dev", "test")}, "paid_calls": len(ledger),
        "paid_cost_usd": total}, indent=1))
    print("\n".join(out))


if __name__ == "__main__":
    main()
