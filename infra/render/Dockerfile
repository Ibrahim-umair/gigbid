# Render free web service (512 MB): API + built UI + in-process GigSim, lite retrieval mode.
FROM node:24-slim AS web
WORKDIR /web
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir uv && uv pip install --system --no-cache -e .
COPY --from=web /web/dist apps/web/dist
ENV GIGSIM_BASE_URL=inproc GIGBID_LITE=1 GIGBID_LLM=fake FASTEMBED_CACHE_PATH=/app/.fastembed
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"
CMD ["sh", "-c", "uvicorn apps.api.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
