# ADR 0005: Raise the risk ceiling 0.6 -> 0.7; keep the bid threshold at 0.55
Status: accepted (revised). Evidence: `evals/results/decision_sweep.json`. The decide node is a
rule over stored RiskReport/FitReport, so thresholds were swept offline on the paid runs' outputs
(0 LLM calls).
First attempt (35 dev jobs): bid fit 0.55 -> 0.40 + risk 0.6 -> 0.7 raised dev F1 0.818 -> 0.88
and test 0.80 -> 0.909. **It did not survive more data:** on the 51-job dev set the same change
gives 0.788 (vs 0.786 shipped). Re-tuned on 51 dev jobs, the best rule keeps bid 0.55 and only
raises the risk ceiling to 0.7: dev F1 0.786 -> 0.828, test unchanged at 0.80. It fixes a good
job skipped for "poor client history" at risk 0.62 (real-35717). Lesson: a 35-job dev set and a
17-job test set are too small to tune thresholds on; the earlier test gain was noise.
