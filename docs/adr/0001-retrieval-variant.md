# ADR 0001: Ship V2 hybrid-only retrieval (BM25 + dense, no decomposition, no reranker)
Status: accepted. Evidence: `evals/results/rag_eval_all.json` (19 jobs with gold evidence).
Hybrid-only had the best Recall@5, MRR and nDCG@10 and ran in ~0.3 s/job; cross-encoder
reranking (bge-reranker-v2-m3 int8 on CPU) lowered recall and cost ~30 s/job; heuristic
requirement decomposition lowered recall (noisy fragments dilute the fused ranking). The
pre-registered hypothesis H-B1 (decomposition + hybrid ≥ +15 pts over V0) was refuted.
