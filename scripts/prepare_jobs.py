"""Preprocess the Kaggle Upwork 2024 job postings (REAL data) into GigSim inputs.

Outputs (data/processed/, git-ignored except the small split files):
  - pricing_stats.json : budget/hourly quantiles per job category (all 53k rows)
  - jobs_real_dev.json / jobs_real_test.json : sampled real jobs for evaluation

Source: kaggle.com/datasets/asaniczka/upwork-job-postings-dataset-2024-50k-records
(see docs/DATA_CARD.md for license and limitations).
"""
from __future__ import annotations

import csv
import json
import random
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "datasets/upwork50k/upwork-jobs.csv"
OUT = ROOT / "data/processed"

CATEGORIES = {
    "ml_ai": r"\b(machine learning|deep learning|llm|nlp|computer vision|pytorch|tensorflow|"
             r"langchain|rag|fine[- ]tun|openai|gpt|hugging ?face|ml engineer|ai engineer|chatbot)\b",  # noqa: E501
    "data": r"\b(data analy|data scien|pandas|sql|tableau|power bi|dashboard|etl|dbt|"
            r"airflow|"
            r"data pipeline|scraping|excel)\b",
    "web": r"\b(react|next\.?js|node|django|flask|fastapi|full[- ]stack|frontend|backend|"
           r"wordpress|shopify|php|laravel)\b",
    "mobile": r"\b(ios|android|flutter|react native|swift|kotlin|mobile app)\b",
    "marketing": r"\b(seo|social media|ads manager|media buyer|marketing|copywrit|lead gen)\b",
    "design": r"\b(logo|graphic design|figma|ui/ux|illustrat|video edit)\b",
}


def categorize(text: str) -> str:
    t = text.lower()
    for cat, pat in CATEGORIES.items():  # order = priority
        if re.search(pat, t):
            return cat
    return "other"


def fnum(v: str) -> float | None:
    try:
        x = float(v)
        return x if x > 0 else None
    except (TypeError, ValueError):
        return None


def quantiles(xs: list[float]) -> dict:
    if len(xs) < 5:
        return {}
    q = statistics.quantiles(xs, n=4)
    return {"n": len(xs), "p25": round(q[0], 2), "median": round(q[1], 2), "p75": round(q[2], 2)}


def main() -> None:
    csv.field_size_limit(10**8)
    rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
    fixed: dict[str, list[float]] = {}
    hourly: dict[str, list[float]] = {}
    pool: dict[str, list[dict]] = {}
    seen_titles: set[str] = set()
    for i, r in enumerate(rows):
        text = f"{r['title']} {r['description']}"
        cat = categorize(text)
        b, lo, hi = fnum(r["budget"]), fnum(r["hourly_low"]), fnum(r["hourly_high"])
        if r["is_hourly"] == "True" and lo:
            hourly.setdefault(cat, []).append((lo + (hi or lo)) / 2)
        elif b:
            fixed.setdefault(cat, []).append(b)
        key = r["title"].strip().lower()
        if len(r["description"]) > 400 and (b or lo) and key not in seen_titles:
            seen_titles.add(key)
            pool.setdefault(cat, []).append({
                "job_id": f"real-{i:05d}",
                "source": "kaggle_upwork_2024",  # REAL data
                "title": r["title"].strip(),
                "description": r["description"].strip()[:3000],
                "category": cat,
                "is_hourly": r["is_hourly"] == "True",
                "budget": b, "hourly_low": lo, "hourly_high": hi,
                "country": r["country"] or None,
                "published_date": r["published_date"],
            })

    OUT.mkdir(parents=True, exist_ok=True)
    stats = {c: {"fixed": quantiles(fixed.get(c, [])), "hourly": quantiles(hourly.get(c, []))}
             for c in CATEGORIES | {"other": ""}}
    (OUT / "pricing_stats.json").write_text(json.dumps(stats, indent=2))

    rng = random.Random(4016)
    # Persona is an AI/ML engineer: mostly in-domain jobs plus off-domain ones it should skip.
    mix = {"ml_ai": 24, "data": 8, "web": 4, "marketing": 2, "design": 2}
    sample = [j for cat, n in mix.items() for j in rng.sample(pool[cat], n)]
    rng.shuffle(sample)
    dev, test = sample[:28], sample[28:]
    for name, part in (("jobs_real_dev.json", dev), ("jobs_real_test.json", test)):
        (OUT / name).write_text(json.dumps(part, indent=2, ensure_ascii=False),
                                encoding="utf-8")
    print(f"rows={len(rows)} dev={len(dev)} test={len(test)}")
    print(json.dumps({c: s["fixed"].get("median") for c, s in stats.items()}))


if __name__ == "__main__":
    main()
