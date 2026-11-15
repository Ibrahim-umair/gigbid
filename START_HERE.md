# Start here: a guided tour of GigBid (v1)

This is the plain-language map of the folder. Read it top to bottom once, then open the files
it points to. For the formal write-up see `docs/report/REPORT.pdf`.

## 1. What the system does, in one picture

```
job post ──> 3 agents look at it at the same time ──> decide: bid / watch / skip
             • Analyst: what does the client want?        (skip = stop here, 3 AI calls)
             • Risk: is it a scam / a trick aimed at AI?
             • Fit: what in my portfolio proves I can do it?
                     │ bid
                     v
   price it ──> write proposal ──> check every claim ──> critic (may send back, max 2x)
   ──> compliance (no phone numbers, no guarantees, no links) ──> STOP and ask the human
                                                                     │ approve
                                                                     v
                                                         submit once (crash-safe)
```

## 2. Where each part lives (read in this order)

| # | Folder / file | What it is | Assignment part |
|---|---|---|---|
| 1 | `data/` | The data. `processed/jobs_real_*.json` = **real** Upwork jobs (Kaggle). `personas/ml_engineer/` = the **synthetic** freelancer's portfolio. `gigsim_seed/` = synthetic clients, scams, injection jobs. | Data card |
| 2 | `gigsim/` | A fake marketplace website (REST API) so we never touch the real Upwork. Simulated clients decide whether to reply. | Starter kit stand-in |
| 3 | `mcp_servers/` | The **tools** agents may use, as MCP servers: `portfolio` (search my evidence), `marketplace` (jobs, clients, submit; wraps GigSim or Upwork), `workspace` (calendar slots). | Part A |
| 4 | `rag/` | How evidence is found. `variants/` holds the 8 search methods we compared; `verify.py` checks claims. | Part B |
| 5 | `agent/` | The brain. `graphs/bid_graph.py` = the picture above as code. `nodes/bid.py` = what each agent does. `prompts/*.md` = the instructions each AI agent gets. `config.yaml` = every setting (models, thresholds, rules). | Part C |
| 6 | `apps/api/` | The backend server the website talks to (FastAPI). | Part D |
| 7 | `apps/web/` | The website (React). 9 screens: inbox, job detail, proposal studio, pipeline, messages, live run view, analytics, settings, login. | Part D |
| 8 | `worker/`, `infra/`, `.github/` | Background jobs, Docker, CI (automatic tests on GitHub). | Part E |
| 9 | `evals/` | The experiments. `runners/` = scripts; `results/` = every measured number (JSON). | R&D questions |
| 10 | `tests/` | Automatic tests (they use a fake AI, so they cost nothing). | Part A/C/E |
| 11 | `docs/` | Architecture, tools list, data card, runbook, decision records, report. | Portfolio |

## 3. The three ideas that matter most for the viva

1. **Human approval is enforced by the graph, not by a prompt.** The only path to `submit` goes
   through `approval_gate`, which calls LangGraph `interrupt()` and waits.
   (`agent/nodes/bid.py`: `approval_gate`, `submit`)
2. **Exactly-once submit.** Submitting is a separate step after approval and carries an
   idempotency key (thread id + hash of the proposal). If the server crashes and the step
   re-runs, the marketplace recognises the key and does not submit or charge twice.
   Test: `tests/integration/test_bid_graph.py::test_crash_and_resume_submits_once`.
3. **No made-up experience.** The writer must list every claim with the portfolio item that
   proves it; `rag/verify.py` checks them and deletes unsupported ones before the critic sees
   the draft. An independent judge found 0 unsupported claims in the final proposals.

## 4. Key results (all from `evals/results/`)

* Search: plain hybrid search (keyword + meaning) beat every fancier method and is ~100x faster
  than reranking: my pre-registered hypothesis was wrong, and the report says so.
* Decisions on held-out jobs: bid/skip F1 0.80 (a threshold fix that looked like +0.11 on 35 dev jobs did not hold up on 51),
  scams caught 100%, 0 successful prompt-injection attacks.
* Cost: about $0.001 per job analysed, $0.002 per proposal (gpt-6-luna).
* The full tables: `evals/results/tables.md`; the story: `docs/report/REPORT.pdf`.

## 5. Try it yourself

```bash
cd gigbid
.venv/Scripts/python -m pytest -q                 # all tests, fake AI, $0
.venv/Scripts/python -m agent.cli run real-28572  # one real job (uses the fake AI unless GIGBID_LLM=openai)
.venv/Scripts/python -m agent.cli approve job-real-28572
make api   # then in another terminal: make web  -> http://localhost:5173  (reviewer / gigbid-review)
```

## 6. What is not done (honest list)

No public deployment, demo video, public traces or LinkedIn write-up; only one LLM tested
(gpt-6-luna, your choice) instead of two open models; the judge is not calibrated (needs 30
labels from you: `python -m evals.runners.judge_calibration --make-template`); live Upwork and
GitHub ingestion are written but never connected; "Regenerate paragraph" is a placeholder.
