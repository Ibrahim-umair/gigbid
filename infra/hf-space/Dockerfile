# Hugging Face Space (Docker SDK, free CPU tier: 2 vCPU / 16 GB). One container runs the
# FastAPI app + built React UI + in-process GigSim + in-memory MCP servers + SQLite stores.
FROM node:24-slim AS web
WORKDIR /web
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web ./
RUN npm run build

FROM python:3.12-slim
RUN useradd -m -u 1000 user
WORKDIR /app
COPY pyproject.toml ./
COPY . .
RUN pip install --no-cache-dir uv && uv pip install --system --no-cache -e .
COPY --from=web /web/dist apps/web/dist
RUN chown -R user:user /app
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH GIGSIM_BASE_URL=inproc \
    FASTEMBED_CACHE_PATH=/home/user/.cache/fastembed
# warm the open models at build time so the first request is not a 2 GB download
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')" && \
    python -c "from fastembed.rerank.cross_encoder import TextCrossEncoder as T; T('BAAI/bge-reranker-v2-m3-int8')"
EXPOSE 7860
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "7860"]
