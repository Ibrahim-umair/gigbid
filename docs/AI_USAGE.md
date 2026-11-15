# AI usage disclosure

| What | Tool / model | Human role |
|---|---|---|
| Architecture, all Python code, tests, docs | Claude Code (Claude Opus 5.5) | Directed scope, budget and model choices; reviewed |
| React frontend + Playwright specs | Claude Code subagent (Claude Sonnet 5.5) | Specified screens and API contract |
| Synthetic persona corpus, clients, scam/injection jobs, message threads | Claude Sonnet 5.5 subagents | Specified schema and constraints |
| Gold labels (bid/skip, evidence, fair price) for the 40 real jobs | Claude Sonnet 5.5 subagent | Not hand-checked: **limitation** |
| GigBid's runtime agents and the simulated GigSim clients | OpenAI `gpt-6-luna` via API (paid profile) | Approved the spend before every paid run |
| Embeddings / reranker | `BAAI/bge-small-en-v1.5`, `BAAI/bge-reranker-v2-m3` (open, local CPU) | — |

Separation: the model that wrote the gold labels (Claude) is not the model being evaluated
(OpenAI), so the system does not grade its own answers. No human-labelled judge calibration set
exists yet (the assignment asks for 30 self-labelled items + Cohen's kappa); see the report.
