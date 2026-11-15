"""R1: the single marketplace interface. Two adapters (GigSim, live Upwork) implement it and are
selected by config (marketplace.mode). Only the Marketplace MCP server holds an adapter; agents
reach the marketplace exclusively through MCP tools, so the graph cannot tell which is live."""
from __future__ import annotations

from typing import Any, Protocol


class MarketplaceUnavailable(RuntimeError):
    """Raised after bounded retries; the UI/graph shows degraded mode and queues the work."""


class MarketplacePort(Protocol):
    async def search_jobs(self, query: str, limit: int = 20,
                          since_seq: int = -1) -> dict[str, Any]: ...
    async def get_job(self, job_id: str) -> dict[str, Any]: ...
    async def get_client_history(self, client_id: str) -> dict[str, Any]: ...
    async def get_connects_balance(self) -> dict[str, Any]: ...
    async def list_messages(self, thread_id: str | None = None) -> dict[str, Any]: ...
    async def create_proposal_draft(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def submit_proposal(self, payload: dict[str, Any], idempotency_key: str,
                              dry_run: bool = False) -> dict[str, Any]: ...
    async def send_message(self, thread_id: str, text: str,
                           idempotency_key: str) -> dict[str, Any]: ...


def get_adapter(mode: str | None = None, user_token: str | None = None) -> MarketplacePort:
    from agent.config import cfg
    mode = mode or cfg("marketplace", "mode")
    if mode == "gigsim":
        from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
        return GigSimAdapter(token=user_token)
    if mode == "upwork_live":
        from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter
        return UpworkLiveAdapter(oauth_token=user_token)
    raise ValueError(f"unknown marketplace mode {mode}")
