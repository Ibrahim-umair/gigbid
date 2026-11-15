"""Extend the dev split to >=50 jobs (R&D C asks for 50 dev jobs): sample N more REAL jobs with
the same category mix, excluding every job already in dev/test. Appends to
data/processed/jobs_real_dev.json and writes the new ids to data/processed/dev_extension.json."""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_jobs as P  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/processed"


def main(n_extra: int = 16):
    import csv
    csv.field_size_limit(10**8)
    dev = json.loads((OUT / "jobs_real_dev.json").read_text(encoding="utf-8"))
    test = json.loads((OUT / "jobs_real_test.json").read_text(encoding="utf-8"))
    taken = {j["job_id"] for j in dev + test} | {j["title"].strip().lower() for j in dev + test}
    rows = list(csv.DictReader(open(P.SRC, encoding="utf-8")))
    pool: dict[str, list] = {}
    for i, r in enumerate(rows):
        jid = f"real-{i:05d}"
        b, lo = P.fnum(r["budget"]), P.fnum(r["hourly_low"])
        title = r["title"].strip()
        if jid in taken or title.lower() in taken or len(r["description"]) <= 400 or not (b or lo):
            continue
        cat = P.categorize(f"{title} {r['description']}")
        pool.setdefault(cat, []).append({
            "job_id": jid, "source": "kaggle_upwork_2024", "title": title,
            "description": r["description"].strip()[:3000], "category": cat,
            "is_hourly": r["is_hourly"] == "True", "budget": b, "hourly_low": lo,
            "hourly_high": P.fnum(r["hourly_high"]), "country": r["country"] or None,
            "published_date": r["published_date"]})
    rng = random.Random(4017)
    mix = {"ml_ai": 9, "data": 4, "web": 2, "marketing": 1}
    new = [j for cat, k in mix.items() for j in rng.sample(pool[cat], k)][:n_extra]
    (OUT / "jobs_real_dev.json").write_text(json.dumps(dev + new, indent=2, ensure_ascii=False),
                                            encoding="utf-8")
    (OUT / "dev_extension.json").write_text(json.dumps([j["job_id"] for j in new], indent=1))
    for j in new:
        print(j["job_id"], j["category"], "|", j["title"][:70])


if __name__ == "__main__":
    main()
