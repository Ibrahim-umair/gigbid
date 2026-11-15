# clinic-policy-rag

Answer staff questions from a pile of policy PDFs, and always say where the answer came from.

## How it works
1. `ingest` splits each PDF on headings and stores the chunks with a vector in a Postgres table (pgvector extension, cosine distance).
2. `ask` embeds the question, pulls the 8 nearest chunks, reranks them, and builds a prompt that forbids answers not supported by the passages.
3. The reply includes document title, page and effective date.

## Run
```
docker compose up -d db
python app.py ingest ./policies
python app.py ask "How long must incident reports be kept?"
```

Environment variables: `DATABASE_URL`, `EMBED_MODEL`, `LLM_MODEL`.

Evaluation set lives in `eval/questions.jsonl` (not included in this public copy).
