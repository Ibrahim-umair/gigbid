"""Offline 'fix' experiment for decision failures: the decide node is a deterministic rule over
the stored RiskReport / FitReport, so alternative thresholds can be scored on the paid runs'
outputs with zero LLM calls. Tune on dev, then check the held-out test split once.
Writes evals/results/decision_sweep.json."""
import itertools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "evals/results"


def gold():
    g = json.loads((ROOT / "evals/datasets/gold_real.json").read_text(encoding="utf-8"))
    g.update(json.loads((ROOT / "data/gigsim_seed/gold_synthetic.json").read_text(
        encoding="utf-8")))
    return g


def decide(r, bid_min, max_risk, scam_only):
    risk, fit = r["risk"] or {}, r["fit"] or 0
    if risk.get("is_scam") or (not scam_only and risk.get("score", 0) > max_risk):
        return False
    return fit >= bid_min


def f1(rows, g, **kw):
    tp = sum(decide(r, **kw) and g[r["job_id"]]["bid"] for r in rows)
    fp = sum(decide(r, **kw) and not g[r["job_id"]]["bid"] for r in rows)
    fn = sum(not decide(r, **kw) and g[r["job_id"]]["bid"] for r in rows)
    p = tp / (tp + fp) if tp + fp else 0
    rc = tp / (tp + fn) if tp + fn else 0
    return round(2 * p * rc / (p + rc), 3) if p + rc else 0.0


def main():
    g = gold()
    devf = R / "decision_eval_dev51_openai.json"
    dev = json.loads((devf if devf.exists() else R / "decision_eval_dev_openai.json")
                     .read_text())["rows"]
    test = json.loads((R / "decision_eval_test_openai.json").read_text())["rows"]
    shipped = {"bid_min": 0.55, "max_risk": 0.6, "scam_only": False}
    grid = [{"bid_min": b, "max_risk": m, "scam_only": s} for b, m, s in itertools.product(
        [0.35, 0.4, 0.45, 0.5, 0.55, 0.6], [0.6, 0.7, 0.8], [False, True])]
    scored = sorted(({**c, "dev_f1": f1(dev, g, **c)} for c in grid),
                    key=lambda c: (-c["dev_f1"], -c["bid_min"]))
    best = {k: scored[0][k] for k in shipped}
    out = {"shipped": {**shipped, "dev_f1": f1(dev, g, **shipped),
                       "test_f1": f1(test, g, **shipped)},
           "best_on_dev": {**best, "dev_f1": scored[0]["dev_f1"], "test_f1": f1(test, g, **best)},
           "top5_dev": scored[:5],
           "failures_dev": [{"job_id": r["job_id"], "action": r["action"], "fit": r["fit"],
                             "risk": (r["risk"] or {}).get("score"),
                             "flags": (r["risk"] or {}).get("flags"),
                             "gold_bid": g[r["job_id"]]["bid"], "outcome": r.get("outcome"),
                             "price": (r["price"] or {}).get("amount"),
                             "fair": g[r["job_id"]].get("fair_price")}
                            for r in dev if (r["action"] == "bid") != g[r["job_id"]]["bid"]
                            or (r.get("submission") and r.get("outcome") == "lost")
                            or (r["price"] and g[r["job_id"]].get("fair_price", {}).get("high")
                                and not g[r["job_id"]]["fair_price"]["low"]
                                <= r["price"]["amount"] <= g[r["job_id"]]["fair_price"]["high"])]}
    (R / "decision_sweep.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "failures_dev"}, indent=1))
    print(len(out["failures_dev"]), "failed dev jobs")


if __name__ == "__main__":
    main()
