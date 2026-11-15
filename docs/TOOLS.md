# Tools (generated from tests/contract/snapshots by scripts; do not hand-edit the table)

Every capability an agent uses is an MCP tool with a schema, an owner and a test
(`tests/contract/test_tool_schemas.py` snapshots, `mcp_servers/marketplace/tests/`).
Agents get only the tools in their allowlist (`agent/mcp_client.py`, filtered by name).

| Tool | Server | R/W | Annotations | Auth | Allowed agents |
|---|---|---|---|---|---|
| `get_case_study` | portfolio | read | destructive=False, idempotent=True, openWorld=False, readOnly=True | local, read-only | critic, writer |
| `list_skills` | portfolio | read | destructive=False, idempotent=True, openWorld=False, readOnly=True | local, read-only | — |
| `match_requirements` | portfolio | read | destructive=False, idempotent=True, openWorld=False, readOnly=True | local, read-only | fit_matcher |
| `search_evidence` | portfolio | read | destructive=False, idempotent=True, openWorld=False, readOnly=True | local, read-only | fit_matcher |
| `create_proposal_draft` | marketplace | write | destructive=False, idempotent=True, openWorld=True, readOnly=False | Bearer token (HTTP) / process (stdio); per-user rate limit; audit log | approval_gate |
| `get_client_history` | marketplace | read | destructive=False, idempotent=True, openWorld=True, readOnly=True | Bearer token (HTTP) / process (stdio); per-user rate limit; audit log | risk_assessor |
| `get_connects_balance` | marketplace | read | destructive=False, idempotent=True, openWorld=True, readOnly=True | Bearer token (HTTP) / process (stdio); per-user rate limit; audit log | pricing |
| `get_job` | marketplace | read | destructive=False, idempotent=True, openWorld=True, readOnly=True | Bearer token (HTTP) / process (stdio); per-user rate limit; audit log | evaluator, scout |
| `list_messages` | marketplace | read | destructive=False, idempotent=True, openWorld=True, readOnly=True | Bearer token (HTTP) / process (stdio); per-user rate limit; audit log | client_liaison |
| `search_jobs` | marketplace | read | destructive=False, idempotent=True, openWorld=True, readOnly=True | Bearer token (HTTP) / process (stdio); per-user rate limit; audit log | scout |
| `send_message` | marketplace | write | destructive=True, idempotent=True, openWorld=True, readOnly=False | Bearer token (HTTP) / process (stdio); per-user rate limit; audit log | liaison_sender |
| `sim_advance` | marketplace | write | destructive=False, idempotent=False, openWorld=False, readOnly=False | Bearer token (HTTP) / process (stdio); per-user rate limit; audit log | evaluator |
| `submit_proposal` | marketplace | write | destructive=True, idempotent=True, openWorld=True, readOnly=False | Bearer token (HTTP) / process (stdio); per-user rate limit; audit log | submitter |
| `create_email_draft` | workspace | write | destructive=False, idempotent=False, readOnly=False | local mock | — |
| `create_interview_hold` | workspace | write | destructive=False, idempotent=True, readOnly=False | local mock | liaison_sender |
| `free_slots` | workspace | read | idempotent=True, readOnly=True | local mock | client_liaison |

Write tools (`create_proposal_draft`, `submit_proposal`, `send_message`) take an
`idempotency_key` (submit/send) and a `dry_run` flag; the approval screen shows the dry-run
preview (exact payload, Connects cost, balance after). Resources: `portfolio://case/{id}`,
`portfolio://repo/{id}`, `portfolio://proposal/{id}`. Prompts: *Answer a screening question
from my portfolio*, *Summarise fit for a job*.

## Third-party servers and trust rationale

| Server | Use | Trust rationale |
|---|---|---|
| Upwork official MCP (`https://mcp.upwork.com/mcp`, OAuth 2.1, Streamable HTTP) | Live-mode marketplace adapter (`mcp_servers/marketplace/adapters/upwork_live.py`) | First-party server run by the platform itself; every write is a draft the user confirms on Upwork, so GigBid can never send on its own. Not exercised in this build (no account connected). |
| GitHub official MCP (`github/github-mcp-server`) | Repo ingestion for the portfolio (`rag/ingest/github.py`) | Maintained by GitHub, scoped read-only token (`repo:read`), used only to read READMEs/code the user owns. |
