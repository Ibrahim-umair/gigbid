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
