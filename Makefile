.PHONY: install dev api web worker test eval eval-paid seed demo lint freeze
PY ?= .venv/Scripts/python

install:
	uv venv && uv pip install -e ".[dev]" cryptography sse-starlette arq python-multipart
	cd apps/web && npm ci

seed:            ## REAL Kaggle data -> data/processed (needs the CSV, see docs/DATA_CARD.md)
	$(PY) scripts/prepare_jobs.py

api:
	$(PY) -m uvicorn apps.api.main:app --reload --port 8000

web:
	cd apps/web && npm run dev

worker:
	$(PY) -m arq worker.tasks.WorkerSettings

dev:             ## API + web (run in two terminals or use docker compose)
	$(MAKE) -j2 api web

test:            ## fake LLM: 0 paid calls
	GIGBID_LLM=fake $(PY) -m pytest -q
	cd apps/web && npx playwright test

eval:            ## retrieval (free) + decision eval on the fake backend
	$(PY) -m evals.runners.rag_eval --split all
	GIGBID_LLM=fake $(PY) -m evals.runners.decision_eval --split dev

eval-paid:       ## real model, hard-capped
	GIGBID_LLM=openai $(PY) -m evals.runners.decision_eval --split dev --max-calls 230
	GIGBID_LLM=openai $(PY) -m evals.runners.decision_eval --split test --max-calls 120
	$(PY) scripts/build_results.py

demo:            ## one job end to end, stops at approval
	$(PY) -m agent.cli run real-28572

lint:
	$(PY) -m ruff check agent rag mcp_servers apps evals gigsim worker scripts

freeze:          ## re-freeze gigsim/ after an intentional policy update
	$(PY) scripts/check_gigsim_frozen.py --freeze
