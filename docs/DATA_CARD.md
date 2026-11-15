# Data card

| Asset | Real or synthetic | Source / generator | Size | Used for |
|---|---|---|---|---|
| Job postings | **REAL** | Kaggle `asaniczka/upwork-job-postings-dataset-2024-50k-records` (Upwork RSS, Feb 2024) | 53,058 rows → 40 sampled jobs (28 dev / 12 test) | GigSim job stream, evaluation |
| Pricing statistics | **REAL** (derived) | Same dataset, all rows: fixed-budget and hourly quartiles per keyword category | 7 categories | Pricing Strategist |
| Scam + prompt-injection jobs | SYNTHETIC | Claude Sonnet subagent | 12 jobs (7 dev / 5 test): 6 scams, 6 injections with machine-checkable `attack` | Risk / injection eval |
| Clients (histories, hidden preferences) | SYNTHETIC | Claude Sonnet subagent (seeded templates + job-consistent prefs) | 52 | GigSim clients, simulated reply/hire |
| Persona corpus (fictional AI/ML engineer) | SYNTHETIC | Claude Sonnet subagent | CV, 15 case studies, 6 repos (README + code), 12 reviews, 60 past proposals (15 won / 15 replied / 30 ignored) | Portfolio RAG, outcome-aware ranking |
| Gold labels for real jobs | SYNTHETIC labels on real jobs | Claude Sonnet subagent, written *after* the corpus | 40 jobs: bid/skip, relevant evidence ids, fair price band | Decision + retrieval eval |
| Message threads | SYNTHETIC | Claude Sonnet subagent | 5 threads (question, negotiation, interview, scam, injection) | Conversation graph |

Every synthetic record carries `"synthetic": true` (or `source: synthetic`); real jobs carry
`source: kaggle_upwork_2024`.

## Preprocessing (`scripts/prepare_jobs.py`, seed 4016)
HTML entities kept (decoded at read time); descriptions truncated to 3,000 chars; jobs with
<400-char descriptions or no budget dropped; duplicate titles removed; keyword categoriser
(ml_ai, data, web, mobile, marketing, design, other); stratified sample 24 ml_ai / 8 data /
4 web / 2 marketing / 2 design so the persona sees both in-domain jobs and jobs it should skip.

## Licensing and attribution
* Kaggle dataset by asaniczka; check the dataset page's license before redistribution. The repo
  commits only the 40 sampled jobs (titles/descriptions as published publicly on Upwork RSS) and
  derived statistics; the full CSV is downloaded at build time and git-ignored.
* Synthetic data was generated for this project and may be shown publicly.
* The other suggested datasets (200k jobs, 60k jobs, 1.3M contracts, freelancer-success,
  trial-1) were reviewed but not used: the 50k set already covers job text + budgets, and the
  contracts set lacks text to link clients to jobs. Using it for client histories is future work.

## Limitations
* **Gold labels were written by an LLM (Claude)**, not by a human freelancer; GigBid's runtime
  model is a different vendor's (OpenAI `gpt-6-luna`), which avoids self-grading but labels are
  still one annotator's judgement. 72.5% of real jobs are labelled skip (honest: most sampled
  real jobs are off-domain or far below the persona's floor).
* Small eval: 19 jobs with gold evidence for retrieval; 35 dev / 17 test jobs for decisions.
  Differences of a few points are within noise.
* The keyword categoriser is noisy (e.g. "Website Testing" → ml_ai); it only affects sampling and
  pricing buckets.
* Simulated clients are an LLM with hidden preferences, a proxy for real reply rates, not ground
  truth.
* The hidden instructor test set does not exist for this build; the 17-job test split
  (12 real + 5 synthetic) was held out from all tuning and stands in for it.
