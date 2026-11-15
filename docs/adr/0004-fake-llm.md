# ADR 0004: Deterministic fake LLM backend for tests and CI
Status: accepted. `GIGBID_LLM=fake` returns schema-valid outputs from the same inputs, so unit,
integration, crash-resume and API tests run with 0 paid calls and no flakiness. It is a test
double: no reported metric comes from it.
