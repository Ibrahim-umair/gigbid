# Every upgrade I planned made my retrieval worse

*What I learned building a multi-agent freelancing copilot on a $0.30 budget.*

I spent a week building GigBid, a system where a team of LangGraph agents reads freelance job
posts, decides which ones are worth bidding on, and drafts proposals that can only claim what a
portfolio actually proves. A human approves every proposal before anything leaves the system.
It runs on three MCP servers, a simulated marketplace, open embedding models on my laptop's CPU,
and a small OpenAI model for the agent steps. The whole evaluation cost about thirty cents.

I expected the interesting part to be the agents. It wasn't. The interesting part was how often
the thing I was sure would help made the numbers worse, and how one improvement I was proud of
fell apart as soon as I gave it sixteen more examples.

## The plan I wrote down before running anything

The retrieval step decides which portfolio items the proposal writer is allowed to cite. If it
misses the right case study, the proposal is either generic or, worse, the model invents
something. So I put effort into retrieval, and I wrote my hypothesis into the repo before running
the comparison, so I couldn't quietly move the goalposts later:

> Requirement decomposition plus hybrid BM25 + dense retrieval will raise evidence Recall@5 by at
> least 15 points over a naive dense baseline.

The reasoning felt solid. Job posts ask for several things at once ("voice chatbot, web
integration, speech-to-text"), so one query per requirement should find evidence for each.
Portfolios name exact libraries (Twilio, YOLOv8, pgvector) that embeddings blur together, so a
keyword index should catch them. On top of that I planned a cross-encoder reranker for precision,
an outcome-aware boost for evidence that appeared in proposals that won, and a corrective loop
that re-queries weak requirements and refuses to claim anything it can't support.

The test set was small but real: job posts from a public Kaggle dump of 53,000 Upwork listings,
and a synthetic portfolio for a fictional ML engineer (15 case studies, 6 repos with code, 12
reviews, 60 past proposals labelled won, replied or ignored). Gold labels said which portfolio
items genuinely proved fit for each job. Nineteen jobs had gold evidence.

## What actually happened

| Variant | Recall@5 | MRR | Seconds per job |
|---|---|---|---|
| Naive dense (baseline) | 0.348 | 0.449 | 0.11 |
| Hybrid BM25 + dense, whole post | **0.378** | **0.535** | 0.29 |
| Decomposition + hybrid (my hypothesis) | 0.311 | 0.480 | 0.29 |
| + cross-encoder reranking | 0.296 | 0.484 | 30.21 |
| Outcome-aware boost | 0.324 | 0.531 | 0.38 |
| Corrective re-query loop | 0.225 | 0.484 | 10.86 |

The hypothesis wasn't just wrong; it pointed the wrong way. Decomposition made recall *worse*
than the baseline. Plain hybrid search with the whole job post as one query won on every metric,
and the margin over the baseline was three points, not fifteen.

The reranker was the biggest surprise. Cross-encoders are the standard answer to "my top results
are noisy", and the one I used (bge-reranker-v2-m3, quantised, on CPU) is well regarded. On this
corpus it lowered recall and turned a 0.3-second step into a 30-second one. A smaller MS-MARCO
reranker I tried first was worse still: it consistently ranked short client reviews and the CV
above the case studies that actually described the work. Those models were trained to match a
question to a passage that answers it. "Here is a job post, which of my projects proves I can do
it" is a different relation, and a model that's great at the first can be mediocre at the second.

Decomposition failed for a duller reason. My requirement splitter was a cheap heuristic (no LLM,
to keep the comparison free), and real job posts are messy. It produced fragments like a skill
list pasted from a form, or half a sentence with a URL in it. Reciprocal rank fusion over six weak
queries diluted the one strong query (the whole post) instead of sharpening it. A better splitter
might change this. But "the clever version needs a clever component to beat the simple version"
is itself the finding.

The corrective loop is the one I'd defend most in a design review, and it scored lowest. Its job
is to refuse to claim experience when the evidence is weak. That's exactly what it did, including
for evidence that was weak-looking but correct. I kept it, but only for what it's good at: grading
per-requirement coverage (strong, partial, none) so the writer knows what it must not claim, not
for ranking.

What shipped is the boring one, hybrid search on the whole post. It's also a hundred times faster
than the reranked pipeline, which mattered more than I expected. Retrieval latency was the main
reason my end-to-end p95 was over a minute per job.

## The fix that didn't survive sixteen more jobs

The second surprise was worse for my ego.

The bid/skip decision in GigBid is a rule, not a model: bid if the fit score clears a threshold
and the risk score stays under a ceiling. Because the rule runs over stored model outputs, I could
sweep thresholds offline for free. On my 35 development jobs, lowering the fit threshold from
0.55 to 0.40 and raising the risk ceiling from 0.6 to 0.7 lifted bid/skip F1 from 0.818 to 0.88.
I checked the held-out test set once, as you're supposed to, and it went from 0.80 to 0.909. I
wrote it up as a win and changed the config.

Later I needed more development data for another experiment, so I sampled 16 more real jobs and
labelled them the same way. On the 51-job development set, the "fix" scored 0.788. The original
thresholds scored 0.786. The improvement was essentially gone. The test-set jump had been luck:
with 17 test jobs, two decisions flipping is 0.11 of F1.

Re-tuned on all 51 jobs, the best rule kept the original fit threshold and only raised the risk
ceiling. It helped on development data (0.786 to 0.828) and did nothing on test (0.80 either
way). That's a much less exciting result, and it's the true one.

I did everything "right" the first time: tuned on dev, touched test once. It still fooled me,
because both sets were too small for the size of the effect I was chasing. Nothing in the
procedure warns you about that. You only find out by getting more data, which in most projects
is exactly the step that gets skipped.

## Better retrieval didn't mean more replies

The marketplace simulator has clients with hidden preferences (must-have skills, a budget
ceiling, a dislike of generic openings) who decide whether to reply. An independent judge, a
different vendor's model from the one running the agents, found zero unsupported claims in the
final proposals. They were grounded and relevant. About half still got no reply, including
proposals with fit scores of 0.88.

Retrieval quality is necessary for honest proposals. It isn't what wins the reply. That's decided
by whether the opening names the client's problem and whether the must-have skills appear in so
many words, things the retrieval metrics don't measure at all. If I'd only tracked Recall@5, I'd
have optimised the wrong thing.

## Was the multi-agent graph worth it?

The assignment asked me to compare the hand-built graph against a single ReAct agent holding every
tool. On 51 jobs, the single agent made slightly *better* bid/skip calls (F1 0.815 vs 0.786 at
the original thresholds). It reads the whole post at once and isn't tripped up by a hard threshold
on borderline jobs. Its scam detection and prompt-injection resistance were just as perfect.

Where the graph won was everything around the decision. It used half the tokens per job (5,570 vs
11,503), cost about 60% as much, got a higher simulated reply rate, and produced proposals the
judge rated clearly better (3.58 vs 2.65 out of 5). Many of the single agent's drafts were polite
decline notes rather than proposals. And the graph gives you things a single agent doesn't:
a hard approval interrupt, exactly-once submission across a crash, and a trace you can audit node
by node.

So the honest answer is "yes, but not for the reason I'd have given at the start". The graph
isn't smarter. It's cheaper, more controllable and easier to trust.

## What I'd tell myself a week ago

Write the hypothesis down first. I would have rationalised every one of these results if I
hadn't. Expect the plain baseline to be hard to beat on a small, specific corpus, and measure the
expensive component before building around it. And treat any improvement measured on a few dozen
examples as a rumour until it survives more data, even when you followed the procedure.

The code, data card, every result file and the full report are in the repo:
github.com/Ibrahim-umair/gigbid. One persona, small evaluation sets and LLM-written gold labels
are real limitations; the report lists them all.
