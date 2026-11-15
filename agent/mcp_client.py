"""MCP client setup (A6). One ToolHub per process holds a session to each server.

* transport=stdio: MultiServerMCPClient launches each server as a subprocess (production path).
* transport=memory: in-memory sessions to the same FastMCP servers (tests, fast offline eval).
Each agent may only call the tools in its allowlist (filtered by name). Every call has a timeout
and bounded retries with backoff; marketplace failures surface as MarketplaceUnavailable so the
graph can enter degraded mode and queue the job.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import time
from typing import Any

from agent.config import ROOT
from agent.marketplace_port import MarketplaceUnavailable

ALLOWLIST: dict[str, dict[str, list[str]]] = {
    "scout": {"marketplace": ["search_jobs", "get_job"]},
    "analyst": {},
    "risk_assessor": {"marketplace": ["get_client_history"]},
    "fit_matcher": {"portfolio": ["match_requirements", "search_evidence"]},
    "pricing": {"marketplace": ["get_connects_balance"]},
    "writer": {"portfolio": ["get_case_study"]},
    "critic": {"portfolio": ["get_case_study"]},
    "compliance": {},
    "approval_gate": {"marketplace": ["create_proposal_draft"]},
    "submitter": {"marketplace": ["submit_proposal"]},
    "client_liaison": {"marketplace": ["list_messages"], "workspace": ["free_slots"]},
    "liaison_sender": {"marketplace": ["send_message"], "workspace": ["create_interview_hold"]},
    "evaluator": {"marketplace": ["sim_advance", "get_job"]},
}
SERVERS = ["portfolio", "marketplace", "workspace"]


class ToolDenied(PermissionError):
    pass


class ToolError(RuntimeError):
    pass


def tools_for(agent: str) -> list[str]:
    return [t for ts in ALLOWLIST.get(agent, {}).values() for t in ts]


class ToolHub:
    def __init__(self, transport: str | None = None, timeout: float = 300, retries: int = 2):
        self.transport = transport or os.getenv("GIGBID_MCP_TRANSPORT", "memory")
        self.timeout, self.retries = timeout, retries
        self.sessions: dict[str, Any] = {}
        self.calls: list[dict] = []
        self._stack = contextlib.AsyncExitStack()

    async def __aenter__(self):
        if self.transport == "stdio":
            from langchain_mcp_adapters.client import MultiServerMCPClient
            env = {**os.environ, "PYTHONPATH": str(ROOT)}
            client = MultiServerMCPClient({
                s: {"transport": "stdio", "command": sys.executable,
                    "args": ["-m", f"mcp_servers.{s}.server"], "cwd": str(ROOT), "env": env}
                for s in SERVERS})
            for s in SERVERS:
                self.sessions[s] = await self._stack.enter_async_context(client.session(s))
        else:
            from mcp.shared.memory import create_connected_server_and_client_session as mem

            from mcp_servers.marketplace.server import mcp as m_mcp
            from mcp_servers.portfolio.server import mcp as p_mcp
            from mcp_servers.workspace.server import mcp as w_mcp
            for s, srv in {"portfolio": p_mcp, "marketplace": m_mcp, "workspace": w_mcp}.items():
                self.sessions[s] = await self._stack.enter_async_context(mem(srv._mcp_server))
        return self

    async def __aexit__(self, *exc):
        await self._stack.aclose()

    async def call(self, agent: str, tool: str, args: dict[str, Any]) -> Any:
        server = next((s for s, ts in ALLOWLIST.get(agent, {}).items() if tool in ts), None)
        if server is None:
            raise ToolDenied(f"agent '{agent}' may not call '{tool}'")
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            t0 = time.perf_counter()
            try:
                res = await asyncio.wait_for(self.sessions[server].call_tool(tool, args),
                                             self.timeout)
                out = _parse(res)
                self.calls.append({"agent": agent, "tool": tool, "ok": True,
                                   "secs": round(time.perf_counter() - t0, 3)})
                return out
            except ToolError as e:
                last = e
                if "unavailable" not in str(e).lower():
                    raise  # validation / business errors are not retried
            except (asyncio.TimeoutError, OSError, RuntimeError) as e:
                last = e
            self.calls.append({"agent": agent, "tool": tool, "ok": False, "error": str(last)})
            await asyncio.sleep(min(2 ** attempt, 8))
        if server == "marketplace":
            raise MarketplaceUnavailable(f"{tool}: {last}")
        raise ToolError(f"{tool} failed after retries: {last}")


def _parse(res) -> Any:
    text = "".join(getattr(c, "text", "") for c in res.content or [])
    if res.isError:
        raise ToolError(text or "tool error")
    sc = res.structuredContent
    if sc is not None:
        return sc["result"] if set(sc) == {"result"} else sc
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


_HUB: ToolHub | None = None


def set_hub(h: ToolHub | None):
    global _HUB
    _HUB = h


def hub() -> ToolHub:
    if _HUB is None:
        raise RuntimeError("ToolHub not started: use `async with ToolHub() as h: set_hub(h)`")
    return _HUB
