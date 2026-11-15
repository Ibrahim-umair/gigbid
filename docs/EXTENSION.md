# Signature extension: X2 Proposal experiments

**What:** two proposal strategies run as an A/B test in GigSim with a significance test on reply
rate. Arm A is the shipped writer (`agent/prompts/writer.md`, evidence-first opening); arm B is
`agent/prompts/writer_b.md` (opens with one sharp question about the client's problem). The
arm is a config switch (`prompts.writer`, or env `GIGBID_WRITER_PROMPT`), so strategies are
data, not code.

**How:** `python -m evals.runners.ab_test` runs arm B on exactly the jobs the graph chose to bid
on in the measured dev+test runs (arm A's outcomes). Job analysis, risk, fit and pricing are
shared through the LLM cache, so only writing, verification, critic, compliance and the
simulated client differ. Reply rates are compared with a two-sided Fisher exact test
(implemented in the runner, checked against a textbook table). An independent judge scores both
arms' proposals on the same rubric.

**Result:** see `evals/results/ab_test_writer.json` and report §7. Arm A replied on 8/15
proposals, arm B on 5/14, Fisher p = 0.46. The judge found no unsupported claims in either arm
(mean rubric 3.67 vs 3.50). Conclusion: no evidence that the question-first opening helps; the
shipped strategy stays. With about 15 proposals per arm only very large effects are detectable;
a real decision needs roughly 10x the sample.
