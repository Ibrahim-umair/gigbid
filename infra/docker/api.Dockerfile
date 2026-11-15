# One image for API, worker, GigSim and MCP servers (different commands in compose).
FROM node:24-slim AS web
WORKDIR /web
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
COPY . .
RUN uv pip install --system -e . cryptography sse-starlette arq python-multipart
COPY --from=web /web/dist apps/web/dist
# warm the open embedding model so the first request is fast
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
