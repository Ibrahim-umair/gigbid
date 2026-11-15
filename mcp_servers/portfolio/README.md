# gigbid-portfolio: an MCP server for your freelance portfolio

Read-only MCP server that lets Claude Desktop, Cursor or any MCP host search your portfolio
(case studies, repos with code, reviews, CV) for evidence that you can do a job, using hybrid
BM25 + dense retrieval with open models on CPU (no API keys).

## Install / run
```bash
# from the GigBid repo
uvx --from . gigbid-portfolio
# or
python -m mcp_servers.portfolio.server
# or Docker
docker build -f infra/docker/api.Dockerfile -t gigbid . && docker run -i gigbid python -m mcp_servers.portfolio.server
```
Claude Desktop (`claude_desktop_config.json`):
```json
{"mcpServers": {"portfolio": {"command": "uvx", "args": ["--from", "/path/to/gigbid", "gigbid-portfolio"],
                              "env": {"GIGBID_PERSONA": "ml_engineer"}}}}
```

## Your data
Put your portfolio in `data/personas/<name>/`: `cv.md`, `case_studies/*.md` (YAML front matter:
id, title, client_industry, date, skills), `repos/index.json` + `repos/<id>/README.md` and code,
`reviews.json`, `proposals.json` (with `outcome`: won/replied/ignored). Set `GIGBID_PERSONA`.

## Tools
| Tool | What it does |
|---|---|
| `search_evidence(requirement, k, types)` | Evidence items with type, source URI, date, snippet |
| `match_requirements(job_title, requirements, k)` | Per-requirement coverage (strong/partial/none) + items; "none" means do not claim it |
| `get_case_study(id)` | Full text of an item |
| `list_skills()` | Declared skills + skills tagged on evidence |

Resources: `portfolio://case/{id}`, `portfolio://repo/{id}`, `portfolio://proposal/{id}`.
Prompts: *Answer a screening question from my portfolio*, *Summarise fit for a job*.
