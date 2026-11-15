"""CI: every decimal metric in README.md's results section must equal some number in a file
under evals/results/ (compared as values, so 0.310 == 0.31)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NUM = r"(?<![\w.])-?\d+\.\d+(?![\w.])"
blob = "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                 for p in (ROOT / "evals/results").glob("*")
                 if p.suffix in {".json", ".csv", ".jsonl"} and p.name != "tables.md")
known = {round(float(x), 4) for x in re.findall(NUM, blob)}
readme = (ROOT / "README.md").read_text(encoding="utf-8")
section = readme.split("<!-- results -->")[1].split("<!-- /results -->")[0]
missing = sorted({n for n in re.findall(NUM, section) if round(float(n), 4) not in known})
if missing:
    sys.exit(f"README numbers not found in evals/results: {missing}")
print(f"all {len(re.findall(NUM, section))} README result numbers trace to evals/results")
