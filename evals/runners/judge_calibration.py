"""Judge calibration (B4): Cohen's kappa between the LLM judge and 30 human-labelled items.

    python -m evals.runners.judge_calibration --make-template   # writes the CSV to fill in
    python -m evals.runners.judge_calibration                   # computes kappa

Label per proposal: `grounded` = 1 if every factual claim about the freelancer is supported by
the portfolio, else 0; `good` = 1 if you would send it as-is (specific opening, answers the job,
120-220 words), else 0.
"""
from __future__ import annotations

import csv
import json
import sys

from agent.config import ROOT

R = ROOT / "evals/results"
TEMPLATE = ROOT / "evals/datasets/judge_labels_human.csv"


def kappa(a: list[int], b: list[int]) -> float:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0


def main():
    judge = json.loads((R / "judge_claude.json").read_text())["items"]
    if "--make-template" in sys.argv:
        items = judge[:30]
        with TEMPLATE.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["item_id", "grounded", "good", "proposal"])
            for it in items:
                w.writerow([it["item_id"], "", "", it.get("proposal", "")[:1500]])
        print(f"fill in {TEMPLATE} (30 rows), then rerun without --make-template")
        return
    rows = [r for r in csv.DictReader(TEMPLATE.open(encoding="utf-8")) if r["grounded"] != ""]
    by_id = {j["item_id"]: j for j in judge}
    h_g = [int(r["grounded"]) for r in rows]
    j_g = [int(by_id[r["item_id"]]["unsupported_claims"] == 0) for r in rows]
    h_q = [int(r["good"]) for r in rows]
    j_q = [int(by_id[r["item_id"]]["rubric"] >= 4) for r in rows]
    out = {"n": len(rows), "kappa_grounded": kappa(h_g, j_g), "kappa_good": kappa(h_q, j_q)}
    (R / "judge_calibration.json").write_text(json.dumps(out, indent=1))
    print(out)


if __name__ == "__main__":
    main()
