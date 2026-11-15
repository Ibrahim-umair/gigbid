FastAPI backend: `main.py` (app + static web), `service.py` (runtime: graphs, checkpointer, ToolHub, run registry, SSE queues), `routers/core.py` (auth, jobs, approvals, runs/SSE, pipeline, messages, analytics, settings, memory, portfolio upload), `auth/users.py` (sessions, PBKDF2, Fernet token store), `schemas/models.py` (OpenAPI).
Run: `make api`. OpenAPI export: see apps/web/README.md.
