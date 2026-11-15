# Pre-registered hypotheses (written before running evals/runners/rag_eval.py)

**H-B1 (retrieval).** Requirement decomposition plus hybrid BM25+dense retrieval (V2) raises
evidence Recall@5 by at least 15 points over the naive dense baseline (V0) on dev jobs that have
gold evidence, because the persona corpus names exact libraries (Twilio, YOLOv8, Celery) that
dense embeddings blur, and multi-part jobs need one query per requirement.

**H-B2 (reranking).** A cross-encoder reranker on top of V2 (V3) adds a further gain in nDCG@10
but a smaller one in Recall@5 (precision at small k, not coverage).

**H-B3 (outcome-aware).** Boosting evidence cited by won/replied proposals (V4) does *not*
improve Recall@5 against gold evidence, because gold labels encode relevance, not persuasiveness;
any benefit would show up in simulated reply rate instead.

Setup: dev split only, jobs with non-empty gold evidence, k=5 for recall, k=10 for nDCG.
Requirement decomposition in this offline eval uses the zero-LLM heuristic splitter
(rag/variants/common.py) so the comparison costs no API calls; the live graph uses the
Job Analyst's LLM decomposition instead.
