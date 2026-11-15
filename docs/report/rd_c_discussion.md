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
