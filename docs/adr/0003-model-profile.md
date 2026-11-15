# ADR 0003: Paid profile on gpt-6-luna; open profile placeholder
Status: accepted by the user (budget). All LLM nodes use `gpt-6-luna` (no fallback model, user
choice); embeddings/reranker are open CPU models in both profiles. The `open` profile (Qwen3 via
a hosted open-model provider) is configured but not run: no GPU locally and no provider key.
This deviates from "open-first" and from "compare two LLM configurations"; only one LLM
configuration was measured.
