"""Live Upwork adapter (A4): talks to the official Upwork MCP server (https://mcp.upwork.com/mcp,
OAuth 2.1) through MultiServerMCPClient over Streamable HTTP, and maps its tools onto the
marketplace port.

Status: implemented but NOT exercised (no Upwork account was connected for this build).
Rules enforced here regardless:
  * submit/send only create Upwork-side DRAFTS; the user confirms on Upwork itself.
  * no browser automation, cookies or scraping; reads are scheduled by the worker at
    marketplace.live_poll_minutes.
Tool names are mapped in TOOL_MAP so a change on Upwork's side is a one-line edit.
"""
from __future__ import annotations

import json
from typing import Any

from agent.marketplace_port import MarketplaceUnavailable

UPWORK_MCP_URL = "https://mcp.upwork.com/mcp"
TOOL_MAP = {  # port method -> Upwork MCP tool name (verify against list_tools() on connect)
    "search_jobs": "search_jobs",
    "get_job": "get_job_details",
    "get_client_history": "get_client_details",
    "get_connects_balance": "get_connects_balance",
    "list_messages": "list_messages",
    "create_proposal_draft": "create_proposal_draft",
    "send_message": "create_message_draft",
}


class UpworkLiveAdapter:
    def __init__(self, oauth_token: str | None):
        if not oauth_token:
            raise MarketplaceUnavailable("Upwork account not connected (no OAuth token)")
        from langchain_mcp_adapters.client import MultiServerMCPClient
        self.client = MultiServerMCPClient({"upwork": {
            "transport": "streamable_http", "url": UPWORK_MCP_URL,
            "headers": {"Authorization": f"Bearer {oauth_token}"}}})

    async def _call(self, method: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            async with self.client.session("upwork") as s:
                res = await s.call_tool(TOOL_MAP[method], args)
        except Exception as e:
            raise MarketplaceUnavailable(f"Upwork MCP error: {e}") from e
        if res.structuredContent:
            return res.structuredContent
        text = "".join(getattr(c, "text", "") for c in res.content)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}

    async def search_jobs(self, query: str, limit: int = 20, since_seq: int = -1):
        return await self._call("search_jobs", {"query": query, "limit": limit})

    async def get_job(self, job_id: str):
        return await self._call("get_job", {"job_id": job_id})

    async def get_client_history(self, client_id: str):
        return await self._call("get_client_history", {"client_id": client_id})

    async def get_connects_balance(self):
        return await self._call("get_connects_balance", {})

    async def list_messages(self, thread_id: str | None = None):
        return await self._call("list_messages", {"room_id": thread_id} if thread_id else {})

    async def create_proposal_draft(self, payload: dict[str, Any]):
        return await self._call("create_proposal_draft", payload)

    async def submit_proposal(self, payload: dict[str, Any], idempotency_key: str,
                              dry_run: bool = False):
        if dry_run:
            return {"dry_run": True, "payload": payload, "note": "Upwork shows cost on confirm"}
        # Live mode never submits directly: it creates a draft the user confirms on Upwork.
        draft = await self._call("create_proposal_draft", payload)
        return {"status": "draft_created_confirm_on_upwork", "draft": draft,
                "idempotency_key": idempotency_key}

    async def send_message(self, thread_id: str, text: str, idempotency_key: str):
        return await self._call("send_message", {"room_id": thread_id, "text": text})
