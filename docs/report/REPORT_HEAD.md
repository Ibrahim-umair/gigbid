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
