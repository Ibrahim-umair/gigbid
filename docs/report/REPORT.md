# GigBid: R&D design review (draft)

AI-4016 · Multi-agent freelancer copilot · every number below cites a file in `evals/results/`.

## 1. Problem and constraints

A freelancer scans feeds, spends paid Connects on long-shot jobs, sends generic proposals and
meets scams (free "trials", off-platform payment, credential requests). GigBid automates
**discovery, assessment and drafting**; the human keeps **every decision that leaves the system**.

**Never automated:** submitting a proposal, sending a message, spending Connects, accepting
off-platform contact/payment, and claiming experience the portfolio does not show. Autonomy can
at most auto-skip low-fit jobs (`settings.autonomy`), never auto-send (enforced in the API and
the graph: the only path to `submit` is an explicit `approve` resume).

**Declared budgets (paid profile, gpt-6-luna):** p95 latency ≤ 90 s per job analysed and
≤ 120 s per proposal on a CPU-only laptop; cost ≤ $0.002 per job analysed and ≤ $0.005 per
proposal. Paid calls are hard-capped per run and every call is ledgered
(`evals/results/llm_ledger.jsonl`).

## 2. Architecture

See `docs/ARCHITECTURE.md` (graphs rendered from code in `docs/images/bid_graph.mmd`).

* **Bid graph**: Analyst ∥ Risk ∥ Fit (LangGraph `Send`) → rule-based decide → rule-based
  pricing (53k-job market stats) → Writer → claim Verifier → Critic (≤2 send-backs) →
  Compliance → `interrupt()` approval → idempotent submit. **Conversation graph**: thread →
  Liaison (intent + reply) → Workspace slots → compliance → `interrupt()` → send.
* **Marketplace port** (`agent/marketplace_port.py`): one interface, two adapters (GigSim REST,
  official Upwork MCP), chosen by config, only reachable through the Marketplace MCP server.
* **MCP surface**: 3 own servers, 16 tools (`docs/TOOLS.md`), per-agent allowlists, schema
  snapshots in CI, idempotency keys + `dry_run` on writes, bearer auth + rate limiter + audit log.
* **Stores**: SQLite checkpointer (thread state, crash-safe), LangGraph store (style + outcome
  memory, promotion rules only), GigSim DB, LLM cache + ledger, audit log.
* Deterministic where judgement is not needed (decide, pricing, regex compliance) so that LLM
  calls go where they add value: 3 calls for a skipped job, ~7 for a proposal.


## 3. R&D question A: tool granularity

**Hypothesis.** Fewer, broader tools cut schema tokens but hurt selection accuracy; descriptions that say *when* to use a tool matter more than the count.

**Setup.** 40 tasks with one known correct call (client checks, job lookups, evidence search, item fetch, balance, proposal preview), three tool sets as schema stubs, one `gpt-6-luna` call per task (`evals/runners/tool_granularity.py`).

| Tool set | Tools | Tool selection | Arguments | Unsafe submits | Input tokens/task |
|---|---|---|---|---|---|
| fine | 15 | 0.975 | 0.975 | 0 | 437.1 |
| coarse | 2 | 0.875 | 0.875 | 0 | 174.2 |
| best | 7 | 1.0 | 1.0 | 0 | 442.1 |

**Result.** The shipped set (7 tools whose descriptions state when to use them) was perfect; 15 fine-grained tools lost one ambiguous search (case study vs repo); 2 coarse `action`-enum tools used 60% fewer input tokens but misrouted 5/40 (portfolio lookups sent to the marketplace tool, `connects` vs `job`). No tool set ever chose `submit`. **Conclusion:** keep a small set of task-shaped tools with explicit when-to-use descriptions; the token saving of coarse tools is not worth the routing errors. Caveat: tasks were written by the author, single run.

## 4. R&D question B: retrieval, claim verification, shipped choice

Pre-registered hypotheses: `evals/HYPOTHESIS.md` (written before the run). Gold evidence from the data card; 19 jobs with gold evidence; zero LLM calls (`evals/results/rag_eval_all.json`).

| Variant | Recall@5 | MRR | nDCG@10 | Recall@5, ≥4 req. | s/job |
|---|---|---|---|---|---|
| v0_naive | 0.348 | 0.449 | 0.406 | 0.451 | 0.11 |
| v1_decompose | 0.298 | 0.357 | 0.334 | 0.417 | 0.23 |
| v2_hybrid_only | 0.378 | 0.535 | 0.43 | 0.495 | 0.29 |
| v2_hybrid | 0.311 | 0.48 | 0.381 | 0.396 | 0.29 |
| v3_rerank_nodecomp | 0.334 | 0.509 | 0.375 | 0.431 | 10.68 |
| v3_rerank | 0.296 | 0.484 | 0.332 | 0.374 | 30.21 |
| v4_outcome | 0.324 | 0.531 | 0.347 | 0.415 | 0.38 |
| v8_corrective | 0.225 | 0.484 | 0.271 | 0.31 | 10.86 |

* **H-B1 refuted.** Decomposition + hybrid (V2) scored Recall@5 0.311 vs V0 0.348; removing decomposition (ablation `v2_hybrid_only`) gave the best result, 0.378 (MRR 0.535, nDCG@10 0.43), also on jobs with ≥4 requirements (0.495 vs 0.451). The zero-LLM splitter yields noisy fragments (skill lists, URLs) and RRF over many weak queries dilutes the strong whole-post query.
* **H-B2 refuted.** The open cross-encoder (bge-reranker-v2-m3, int8, CPU) lowered recall (V3 0.296, without decomposition 0.334) and cost 30.21 s/job vs 0.29; an MS-MARCO MiniLM reranker was worse still (ranked short reviews above case studies).
* **H-B3 supported.** Outcome-aware boosting (V4) did not raise Recall@5 (0.324 vs V3 0.296) though MRR rose (0.531 vs 0.484): gold labels encode relevance, not persuasiveness.
* Corrective loop V8 had the lowest recall (0.225): its refusal threshold drops weak-but-correct evidence; it is kept only to grade per-requirement coverage (strong/partial/none) inside `match_requirements`.

**Claim verification (B3).** Unsupported claims per proposal before verification: dev 0.07, test 0 (the writer rarely overclaims when it must list claims with evidence ids). After verification, an independent judge (Claude, different vendor from the runtime model) found 0.000 unsupported and 0.053 partly supported claims per proposal over 19 final proposals, mean rubric 3.579/5 (`evals/results/judge_claude.json`). **The judge is not calibrated:** the 30-item human label set (`evals/runners/judge_calibration.py --make-template`) has not been filled in, so no Cohen's kappa is reported.

**By persona / job type.** One persona only (AI/ML engineer), a limitation. On jobs with ≥4 extracted requirements every variant scores higher (they are the long, specific posts); the ranking of variants is the same.

**Where better retrieval did not mean more replies.** Dev reply rate was 0.429 with every proposal grounded; lost proposals had strong fit and correct evidence (e.g. real-15141 fit 0.88, real-05895 0.78). The simulated clients decide on must-have skills named explicitly, budget ceiling and opening style, so evidence quality beyond 'relevant' moves the reply rate little. Retrieval is necessary for grounding, not sufficient for replies.

**Shipped:** `v2_hybrid_only` (BM25 + dense, RRF, whole-post query): best on every retrieval metric and ~100x faster than reranking (`docs/adr/0001`).

## 5. R&D question C: single agent vs prebuilt supervisor vs this graph

Same 51 dev jobs, same model, same MCP tools, same GigSim scoring (`evals/runners/arch_compare.py`; `arch_*_dev.json`).

| Metric (51 dev jobs) | (a) ReAct | (b) Supervisor | (c) Graph |
|---|---|---|---|
| Bid/skip F1 | 0.815 | pending | 0.786 |
| Scam precision | 0.750 | pending | 0.750 |
| Scam recall | 1.000 | pending | 1.000 |
| Injection attack success | 0.000 | pending | 0.000 |
| Proposals | 23 | pending | 14 |
| GigSim reply rate | 0.385 | pending | 0.429 |
| Cost/job (USD) | 0.002 | 0.002 | 0.001 |
| Tokens/job | 11503 | 12105 | 5570 |
| p95 s/job | 206.480 | pending | 197.120 |
| Judge: unsupported claims/proposal | 0.00 | pending | 0.00 |
| Judge: mean rubric (1-5) | 2.65 | pending | 3.58 |
| Judge: genuine policy violations | 0 | pending | 0 |

**Prebuilt supervisor.** Measured over the same 51 jobs, the supervisor was the most expensive design: $0.00202 per job, 6.82 LLM calls and about 12,105 tokens per job (`arch_supervisor_dev51_resources.json`), because every hand-off between supervisor, researcher and writer re-sends the conversation. Its decision and quality metrics are pending in this draft.

**Where the single agent wins.** On the 51 dev jobs ReAct's bid/skip F1 (0.815) beat the
graph's measured thresholds (0.786); with the re-tuned risk ceiling the graph reaches 0.828. ReAct
reads the job holistically and is not hurt by a hard fit threshold on borderline jobs, and its
scam and injection handling was equally perfect. It loses on cost and outcomes: about 1.6x the
cost per job, a lower GigSim reply rate, and many of its drafts were decline notes rather than
proposals (judge rubric well below the graph's). Its proposals were grounded too (judge: 0
unsupported claims), so on this corpus the graph's claim verifier is insurance rather than a
measured differentiator. **Conclusion:** the graph is worth it for cost, auditability and the
approval/durability guarantees; a single ReAct agent is a strong decision baseline.

**Latency caveat.** The 16 jobs added to reach 51 were run with three systems in parallel while
two other build jobs used the same CPU, so their latencies are inflated (p95 ≈ 200 s) and the
51-job latency rows are not comparable to the uncontended 35-job measurement (graph p95 71 s,
`cost_latency.json`). Cost per job is unaffected.


## 6. The change request

The official 2 Nov 2026 policy text was not available to this build. A rehearsal update was applied instead: *“proposals may not contain external links”*. Edit: one regex line in `agent/config.yaml` (`compliance.block_patterns.external_link`) and a version bump + sentence in `agent/prompts/compliance.md` (1.0 → 1.1). No code changed. Edit + verification + the 16 fast tests took 32 s of wall time. A Connects or pricing rule would be one edit in `gigsim/policy.yaml` (re-frozen with `make freeze`) or `pricing.*`. This is what the design was meant to make cheap: rules, thresholds, prompts and models live in configuration.

## 7. Signature extension: X2 proposal experiments

Two writer strategies on the same 15 jobs the graph chose to bid on: A = evidence-first opening (`writer.md`), B = question-first opening (`writer_b.md`). Analysis was shared via the LLM cache, so only writing and the simulated client differ (`evals/runners/ab_test.py`).

| Arm | Proposals | Replied | Reply rate | Hired |
|---|---|---|---|---|
| A (evidence-first) | 15 | 8 | 0.533 | 0 |
| B (question-first) | 14 | 5 | 0.357 | 0 |

Judge (same standard, `judge_claude.json`): mean rubric A 3.58 vs B 3.50; unsupported claims A 0.00 vs B 0.00.

Fisher exact test, two-sided: p = 0.4621. With ~15 proposals per arm the test can only detect very large differences; the result is reported as measured, not as a winner.

## 8. Failure analysis

11 of 51 dev jobs failed on the decision, price or outcome, plus 4 proposals with leaked citation tags and 3 first drafts sent back by the Critic.

| Job | Failure type | Detail | Fix tried | Worked? |
|---|---|---|---|---|
| real-05895 | no reply (generic / missed must-have) | price 55.0 vs fair 45-70, outcome lost | X2 question-first opening | see §7 |
| real-09353 | no reply (generic / missed must-have) | price 1000.0 vs fair 800-1500, outcome lost | X2 question-first opening | see §7 |
| real-15141 | no reply (generic / missed must-have) | price 150.0 vs fair 60-150, outcome lost | X2 question-first opening | see §7 |
| real-28572 | no reply (generic / missed must-have) | price 150.0 vs fair 150-400, outcome lost | X2 question-first opening | see §7 |
| real-32197 | wrong skip | fit 0.23, risk 0.48, flags unrealistic_budget, vague_scope | threshold sweep: risk ceiling 0.6→0.7 | no (fit 0.23) |
| real-35717 | wrong skip | fit 0.67, risk 0.62, flags vague_scope, poor_client_history | threshold sweep: risk ceiling 0.6→0.7 | yes |
| real-46183 | wrong bid | fit 0.78, risk 0.26, flags unrealistic_budget, vague_scope | none (budget below floor; pricing quoted floor) | — |
| syn-06 | wrong skip | fit 0.42, risk 0.08, flags prompt_injection | threshold sweep: risk ceiling 0.6→0.7 | no (fit 0.42) |
| real-20042 | no reply (generic / missed must-have) | price 50.0 vs fair 40-60, outcome lost | X2 question-first opening | see §7 |
| real-45109 | wrong bid | fit 0.68, risk 0.12, flags vague_scope | none (budget below floor; pricing quoted floor) | — |
| real-15749 | wrong bid | fit 0.55, risk 0.18, flags  | none (budget below floor; pricing quoted floor) | — |
| 4 proposals | citation tags leaked into client text | real-49722, syn-07, real-04308, real-34788 | strip `[cs-..]` tags after verification (`rag/verify.py`) | yes: 4 → 0 |

Threshold fix (`evals/results/decision_sweep.json`): bid/skip F1 dev 0.786 → 0.828, held-out test 0.8 → 0.8 (chosen on dev, test checked once). An earlier fix tuned on the first 35 dev jobs (bid threshold 0.40) scored 0.909 on test but only 0.788 on the 51-job dev set, so it was dropped as noise (`docs/adr/0005`). Headline numbers were measured before the change.

## 9. Safety and platform respect

**Never:** send, submit or spend Connects without an `approve` resume; move communication or payment off-platform; claim unsupported experience; follow instructions inside job posts or client messages; scrape or automate a website.

**Enforced by:** the graph topology (submit is only reachable from approval), idempotency keys on every write, untrusted-text delimiting + a tool-less Analyst, deterministic regex floors (injection, scam, contact/guarantee/link redaction) under the LLM checks, claim verification, per-agent tool allowlists, PII masking in the audit log and SSE stream, Fernet-encrypted OAuth tokens, tenant-scoped queries, a rate limiter under GigSim's limit, and official MCP/API access only.

**Measured:** injection attack success 0.0 on dev (4 planted jobs) and 0.0 on test (2); all planted posts flagged; scam recall 1.0 / 1.0; judge policy flags 0. No 'before defences' run was made, so the defence's marginal effect is not isolated.

**Still gets through / not done:** regex floors miss novel phrasings (2 of 6 synthetic attacks were missed by the regexes before widening on dev); detection on test relies on the LLM risk node; the live Upwork adapter and GitHub ingestion are implemented but unexercised; no public deployment or traces.

## 10. Held-out test results against declared budgets

No instructor hidden set exists for this build; the 17-job test split (12 real + 5 synthetic), held out from all tuning, stands in for it.

| Measure | Budget | Test | Met |
|---|---|---|---|
| p95 latency / job | ≤ 90 s | 68.92 s | yes |
| p95 latency / proposal | ≤ 120 s | 62.53 s | yes |
| Cost / job analysed | ≤ $0.002 | $0.00109 | yes |
| Cost / proposal | ≤ $0.005 | $0.00208 | yes |
| Bid/skip F1 | — | 0.8 | |
| Scam precision / recall | — | 1.0 / 1.0 | |
| Injection attack success | 0 | 0.0 | yes |
| Price in fair band | — | 0.8 | |
| GigSim reply / hire rate | — | 0.6 / 0.0 | |

Latency is dominated by CPU retrieval (cross-encoder coverage grading inside `match_requirements`), not the model. **Optimisation that helped:** switching the ranking retriever from V3 to hybrid-only cut retrieval from 30.21 s to 0.29 s per job while improving recall; early skip keeps a rejected job at 3 LLM calls. Cost/latency were recovered from the call ledger because the scored runs replayed from the LLM cache (`scripts/ledger_jobs.py`).

Total paid LLM usage for this report: 1085 calls, $0.2976 (`evals/results/llm_ledger.jsonl`).

## Appendix: limitations

One persona; small eval sets (19 / 35 / 17 jobs); gold labels and synthetic data written by an LLM; simulated clients are an LLM proxy; one LLM configuration (gpt-6-luna) instead of two open models; supervisor baseline pending; uncalibrated judge; no public deployment, traces or demo video; Regenerate-paragraph in the studio is a placeholder.