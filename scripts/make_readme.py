"""README.md = docs/report/README_HEAD.md + generated results tables (evals/results/tables.md).
Numbers inside the results markers are checked by scripts/check_results_cited.py in CI."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
head = (ROOT / "docs/report/README_HEAD.md").read_text(encoding="utf-8")
tables = (ROOT / "evals/results/tables.md").read_text(encoding="utf-8")
tail = """
## Résumé bullet (numbers from evals/results)
* Built GigBid, a LangGraph multi-agent freelancer copilot with 3 MCP servers and human-in-the-loop
  approval; on held-out jobs it caught 100% of scam posts, resisted 100% of prompt-injection
  attempts, and drafted proposals with 0 unsupported claims for about $0.002 each.
* Showed by measurement that plain hybrid BM25+dense retrieval beat decomposition, cross-encoder
  reranking and corrective RAG on this corpus while running about 100x faster than reranking.

## What is not done
No public deployment, demo video, public traces or published write-up; one LLM configuration
(gpt-6-luna) rather than two open models; the LLM judge is uncalibrated (no human labels yet);
the live Upwork adapter and GitHub ingestion are implemented but were never connected. See
[START_HERE.md](START_HERE.md) for a guided tour and the report appendix for limitations.
"""
readme = head + "\n## Results\n<!-- results -->\n" + tables + "\n<!-- /results -->\n" + tail
(ROOT / "README.md").write_text(readme, encoding="utf-8")
print("README.md written")
