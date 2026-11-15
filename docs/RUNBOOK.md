# Runbook

## Run locally
```bash
uv venv && uv pip install -e ".[dev]" cryptography sse-starlette arq python-multipart
python scripts/prepare_jobs.py <path/to/upwork-jobs.csv>     # REAL data → data/processed
cp .env.example .env                                         # fill OPENAI_API_KEY for real runs
make api            # FastAPI on :8000 (serves apps/web/dist if built)
make web            # Vite dev server on :5173 (proxies /api)
make test           # fake LLM, 0 paid calls
make eval           # retrieval (free) + decision eval (GIGBID_LLM=openai to use the real model)
docker compose -f infra/docker-compose.yml up --build       # everything
```
Reviewer login: `reviewer` / value of `REVIEWER_PASSWORD` (default `gigbid-review`, change it in
the deployed `.env`; credentials go in the private submission comment, not the repo).

## Scheduling and politeness
* GigSim: saved searches scouted hourly (`worker/tasks.py` cron), max 2 concurrent analyses.
* **Live Upwork: every 4 h per saved search** (`marketplace.live_poll_minutes: 240`). Rationale: a
  freelancer checking a feed a few times a day is normal use; new-job discovery value decays
  over hours, not minutes; 6 reads/day/search keeps us far below anything that looks like
  scraping. No browser automation, cookies or page fetching; reads only via the official MCP.
* Marketplace server limiter: 20 req/min (GigSim allows 30), plus backoff on 429/503.

## Paid-call budget controls
`GIGBID_LLM=fake` for development/tests. Real runs: `llm.max_paid_calls` (or `--max-calls`) is a
hard cap; responses are cached (`data/processed/llm_cache.sqlite`); every call is appended to
`evals/results/llm_ledger.jsonl` with tokens and USD.

## Degraded mode drill (viva)
`POST /api/admin/marketplace {"down": true}` → GigSim returns 503 → tools retry with backoff →
runs move to `degraded_queued`, `/api/health` reports `marketplace: unavailable`, UI shows the
banner. `{"down": false}` → health recovers and queued jobs are re-run.

## Crash-and-resume drill
`python -m agent.cli run real-28572` (stops at approval) → kill the process → `python -m
agent.cli approve job-real-28572` from a new process → submitted once. Approving again is a
no-op (409 in the API; idempotency replay at the marketplace).

## Change request (platform policy update)
Rules and costs live in config, not code:
* Marketplace-side costs/rules: `gigsim/policy.yaml` (Connects tiers, letter length bounds).
* GigBid-side rules: `agent/config.yaml` → `compliance.block_patterns`, `banned_phrases`,
  `pricing.*`, `thresholds.*`; prompts in `agent/prompts/*.md` (versioned header).
The official 2 Nov 2026 change request text was not available for this build. Rehearsal: adding
a hypothetical rule "proposals may not mention a delivery date shorter than 3 days" is one regex
line in `compliance.block_patterns` plus a `version:` bump in `compliance.md`; a new Connects
cost is one edit to `gigsim/policy.yaml` (after re-freezing with
`scripts/check_gigsim_frozen.py --freeze`, since GigSim is treated as provided/frozen).
