"""Merge the 35-job dev runs with the 16-job extension (and the supervisor's partial 12 + rest
39) into one 51-job result per system, so R&D C compares (a) ReAct, (b) supervisor and (c) the
graph on the same 51 dev jobs. Graph rows use the thresholds that were measured
(evals/config_measured_v1.yaml); cost/latency of the cached 35-job graph rows come from the
ledger recovery (cost_latency.json). Writes *_dev51*.json in evals/results/."""
import json
import statistics
from pathlib import Path

from evals.runners.decision_eval import pct, score
from evals.runners.rag_eval import load_gold, load_jobs

R = Path(__file__).resolve().parents[1] / "evals/results"


def J(n):
    return json.loads((R / n).read_text(encoding="utf-8"))


def finish(rows, gold, jobs, cost_secs):
    res = score(rows, gold, jobs)
    costs = [cost_secs[r["job_id"]][0] for r in rows]
    secs = [cost_secs[r["job_id"]][1] for r in rows]
    props = [cost_secs[r["job_id"]][0] for r in rows if r["proposal"]]
    res["summary"].update({"cost_per_job_usd": round(statistics.mean(costs), 5),
                           "cost_per_proposal_usd": round(statistics.mean(props), 5)
                           if props else None,
                           "latency_p50_s": pct(secs, 0.5), "latency_p95_s": pct(secs, 0.95),
                           "tokens_per_job": round(statistics.mean(
                               cost_secs[r["job_id"]][2] for r in rows))})
    return res


def main():
    gold, jobs = load_gold(), load_jobs()
    # (c) graph
    g35, g16 = J("decision_eval_dev_openai.json"), J("decision_eval_custom_ext16_openai.json")
    led = {p["job_id"]: p for p in J("cost_latency.json")["dev"]["per_job"]}
    cs = {r["job_id"]: (led[r["job_id"]]["cost"], led[r["job_id"]]["llm_secs"],
                        led[r["job_id"]]["tokens"]) for r in g35["rows"]}
    cs.update({r["job_id"]: (r["usage"]["cost"], r["secs"], r["usage"]["in"] + r["usage"]["out"])
               for r in g16["rows"]})
    graph = finish(g35["rows"] + g16["rows"], gold, jobs, cs)
    graph["meta"] = {"jobs": [r["job_id"] for r in graph["rows"]], "system": "graph",
                     "thresholds": "measured v1 (bid 0.55, risk 0.6)"}
    (R / "decision_eval_dev51_openai.json").write_text(json.dumps(graph, indent=1, default=str))
    # (a) ReAct
    a35, a16 = J("arch_react_dev.json"), J("arch_react_dev_ext16.json")
    rows = a35["rows"] + a16["rows"]
    react = finish(rows, gold, jobs, {r["job_id"]: (r["usage"]["cost"], r["secs"],
                                                 r["usage"]["in"] + r["usage"]["out"])
                                      for r in rows})
    (R / "arch_react_dev51.json").write_text(json.dumps(react, indent=1, default=str))
    # (b) supervisor: only when a valid run exists (earlier runs were invalid, see report)
    if not (R / "arch_supervisor_dev_rest39.json").exists():
        print("supervisor: no valid run; skipped")
        for name, res in (("graph", graph), ("react", react)):
            print(name, res["summary"]["tokens_per_job"], res["summary"]["bid_f1"])
        return
    p12, r39 = J("arch_supervisor_dev_partial.json"), J("arch_supervisor_dev_rest39.json")
    rows = [{"job_id": r["job_id"], "status": r["action"], "action": r["action"], "fit": None,
             "risk": {"is_scam": r["is_scam"]}, "price": None, "unsupported_before": None,
             "claims": 0, "revisions": 0, "compliance": {}, "proposal": "", "submission": None,
             "errors": ["partial run: proposal not captured"], "secs": r["secs"],
             "usage": {"calls": r["calls"], "in": 0, "out": 0, "cost": r["cost"]},
             "outcome": None} for r in p12["rows"]] + r39["rows"]
    sup = finish(rows, gold, jobs, {r["job_id"]: (r["usage"]["cost"], r["secs"],
                                               r["usage"]["in"] + r["usage"]["out"])
                                    for r in rows})
    sup["summary"]["note"] = ("12 of 51 jobs from the stopped first run (decisions, cost, "
                              "latency only); proposals and reply rate cover the other 39.")
    (R / "arch_supervisor_dev51.json").write_text(json.dumps(sup, indent=1, default=str))
    for name, res in (("graph", graph), ("react", react), ("supervisor", sup)):
        s = res["summary"]
        print(f"{name:<10} n={s['n_jobs']} F1={s['bid_f1']} scamR={s['scam_recall']} "
              f"attack={s['attack_success_rate']} props={s['proposals']} "
              f"reply={s['gigsim_reply_rate']} $/job={s['cost_per_job_usd']} "
              f"p95={s['latency_p95_s']}")


if __name__ == "__main__":
    main()
