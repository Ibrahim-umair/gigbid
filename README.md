# GigBid: a multi-agent freelancer copilot that never sends without you

GigBid finds freelance jobs, screens out scams and prompt-injection posts, maps each job's
requirements to **real portfolio evidence**, prices the bid from 53k real Upwork postings,
drafts a proposal where **every claim cites evidence**, checks it (claim verifier → critic →
compliance), and then **stops for your approval**. Only an approved proposal reaches the
marketplace, exactly once, even across a crash.

**Stack:** LangGraph (two hand-written graphs) · MCP (3 own servers, 16 tools + Upwork/GitHub
official servers) · FastAPI + SSE · React/Vite/TypeScript (typed client generated from
OpenAPI) · open CPU embeddings/reranker · OpenAI `gpt-6-luna` for the LLM nodes · SQLite
checkpointer + LangGraph store · Arq worker · Playwright · GitHub Actions eval gate.

> Live URL / demo GIF / public traces: **not produced in this build** (no hosting account or
> tracing key was configured). `docker compose -f infra/docker-compose.yml up --build` runs it
> locally; the reviewer login is `reviewer` / `$REVIEWER_PASSWORD`.

## Architecture
```
React (inbox · job detail · proposal studio · pipeline · messages · run viewer · analytics · settings)
   │  typed OpenAPI client, SSE stream
FastAPI ── Runtime ── bid graph ─┬ Job Analyst ┐
   │                             ├ Risk Assessor├─ decide ─ pricing ─ writer ─ verifier ─ critic(≤2)
   │                             └ Fit Matcher ┘                     ─ compliance ─ interrupt(approve)
   │                   conversation graph: liaison ─ slots ─ compliance ─ interrupt ─ send
   └─ ToolHub (MCP, per-agent allowlists) ── Portfolio · Marketplace (port: GigSim | Upwork) · Workspace
```
Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · tools: [docs/TOOLS.md](docs/TOOLS.md) ·
data: [docs/DATA_CARD.md](docs/DATA_CARD.md) · ops: [docs/RUNBOOK.md](docs/RUNBOOK.md) ·
decisions: [docs/adr/](docs/adr/) · report: [docs/report/REPORT.pdf](docs/report/REPORT.pdf)

## Quick start
```bash
make install            # Python venv + web deps
make test               # 0 paid calls (fake LLM): unit, contract, MCP, graph, crash-resume, API
make demo               # one real job end to end, stops at the approval interrupt
make api & make web     # http://localhost:5173  (login: reviewer / gigbid-review locally)
GIGBID_LLM=openai make eval-paid   # real model, hard-capped, every call ledgered
```

## Results
<!-- results -->
### Retrieval (19 jobs with gold evidence, dev+test; no LLM)

| Variant | Recall@5 | MRR | nDCG@10 | Recall@5 (jobs with ≥4 req.) | s/job |
|---|---|---|---|---|---|
| v0_naive | 0.348 | 0.449 | 0.406 | 0.451 | 0.11 |
| v1_decompose | 0.298 | 0.357 | 0.334 | 0.417 | 0.23 |
| v2_hybrid_only | 0.378 | 0.535 | 0.430 | 0.495 | 0.29 |
| v2_hybrid | 0.311 | 0.480 | 0.381 | 0.396 | 0.29 |
| v3_rerank_nodecomp | 0.334 | 0.509 | 0.375 | 0.431 | 10.68 |
| v3_rerank | 0.296 | 0.484 | 0.332 | 0.374 | 30.21 |
| v4_outcome | 0.324 | 0.531 | 0.347 | 0.415 | 0.38 |
| v8_corrective | 0.225 | 0.484 | 0.271 | 0.310 | 10.86 |

### End-to-end decisions (gpt-6-luna, shipped config)

| Metric | Dev (51 jobs) | Test (held out) |
|---|---|---|
| Bid/skip F1 | 0.786 | 0.8 |
| Bid precision | 0.786 | 0.8 |
| Bid recall | 0.786 | 0.8 |
| Scam precision | 0.75 | 1.0 |
| Scam recall | 1.0 | 1.0 |
| Injection attack success | 0.0 | 0.0 |
| Price in fair band | 0.929 | 0.8 |
| Unsupported claims / proposal (before verification) | 0.07 | 0 |
| Critic send-backs | 5 | 2 |
| Compliance blocks | 0 | 0 |
| GigSim reply rate | 0.429 | 0.6 |
| GigSim hire rate | 0.0 | 0.0 |
| Latency p50 (s/job) | 56.85 | 2.01 |
| Latency p95 (s/job) | 197.12 | 50.89 |
| Cost / job analysed (USD) | 0.00107 | 0.00023 |
| Cost / proposal (USD) | 0.00202 | 0.00039 |
| Tokens / job | 5570 | 1140 |
| LLM calls | 71 | 16 |
| Jobs | 51 | 17 |
| Proposals drafted | 14 | 5 |

### Cost and latency of the paid runs (recovered from the call ledger)

| Run | Cost/job (USD) | Cost/proposal (USD) | p50 s/job | p95 s/job | p95 s/proposal | Tokens/job |
|---|---|---|---|---|---|---|
| dev | 0.00109 | 0.00199 | 40.11 | 71.35 | 73.66 | 5571 |
| test | 0.00109 | 0.00208 | 34.69 | 68.92 | 62.53 | 5587 |

### R&D A: tool granularity (40 tasks, gpt-6-luna)

| Tool set | # tools | Tool-selection acc. | Argument acc. | Unsafe submits | Input tokens/task |
|---|---|---|---|---|---|
| fine | 15 | 0.975 | 0.975 | 0 | 437.1 |
| coarse | 2 | 0.875 | 0.875 | 0 | 174.2 |
| best | 7 | 1.0 | 1.0 | 0 | 442.1 |

### R&D C: single agent vs prebuilt supervisor vs hand-built graph (51 dev jobs)

| Metric | (a) ReAct, all tools | (b) Supervisor (pending) | (c) GigBid graph |
|---|---|---|---|
| Bid/skip F1 | 0.815 | — | 0.786 |
| Scam recall | 1.0 | — | 1.0 |
| Scam precision | 0.75 | — | 0.75 |
| Injection attack success | 0.0 | — | 0.0 |
| Price in band | 0.875 | — | 0.929 |
| Proposals | 23 | — | 14 |
| GigSim reply rate | 0.385 | — | 0.429 |
| Cost/job (USD) | 0.0017 | — | 0.00107 |
| Tokens/job | 11503 | — | 5570 |
| p50 s/job | 84.66 | — | 56.85 |
| p95 s/job | 206.48 | — | 197.12 |
| Judge: unsupported claims/proposal | 0.0 | — | 0.0 |
| Judge: mean rubric | 2.652 | — | 3.579 |
| Judge: genuine policy violations | 0 | — | 0 |

### X2: proposal strategy A/B in GigSim

| Arm | Prompt | Proposals | Replied | Reply rate | Hired |
|---|---|---|---|---|---|
| A | writer | 15 | 8 | 0.533 | 0 |
| B | writer_b | 14 | 5 | 0.357 | 0 |

Fisher exact test (two-sided) p = 0.4621.

### Proposal judge (Claude, independent of the runtime model; uncalibrated)

| System | Proposals | Unsupported/proposal | Partly supported/proposal | Mean rubric | Policy flags |
|---|---|---|---|---|---|
| graph | 19 | 0.0 | 0.053 | 3.579 | 0 |
| writer_b | 14 | 0.0 | 0.0 | 3.5 | 0 |
| react | 23 | 0.0 | 0.0 | 2.652 | 0 |

Paid LLM usage for everything above: 1085 calls, $0.2976 (evals/results/llm_ledger.jsonl).
<!-- /results -->

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
