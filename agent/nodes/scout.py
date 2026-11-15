"""Scout: scheduled saved-search scouting + de-dup lives in the worker
(worker/tasks.py: scout_saved_searches) using the marketplace `search_jobs` MCP tool; no LLM
is needed for de-duplication."""
