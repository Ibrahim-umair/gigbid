"""Schema snapshot: fails CI when a tool signature changes unintentionally.
Regenerate deliberately with UPDATE_SNAPSHOTS=1."""
import json
import os
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as mem

SNAP = Path(__file__).parent / "snapshots"


@pytest.mark.parametrize("server", ["portfolio", "marketplace", "workspace"])
async def test_tool_schema_snapshot(server):
    mod = __import__(f"mcp_servers.{server}.server", fromlist=["mcp"])
    async with mem(mod.mcp._mcp_server) as s:
        tools = (await s.list_tools()).tools
    current = {t.name: {"input": t.inputSchema, "output": t.outputSchema,
                        "annotations": t.annotations.model_dump() if t.annotations else None}
               for t in sorted(tools, key=lambda t: t.name)}
    path = SNAP / f"{server}.json"
    SNAP.mkdir(exist_ok=True)
    if os.getenv("UPDATE_SNAPSHOTS") or not path.exists():
        path.write_text(json.dumps(current, indent=1, sort_keys=True))
    assert current == json.loads(path.read_text()), f"{server} tool schema changed"


async def test_write_tools_annotated():
    from mcp_servers.marketplace.server import mcp
    async with mem(mcp._mcp_server) as s:
        tools = {t.name: t for t in (await s.list_tools()).tools}
    for name in ("submit_proposal", "send_message"):
        a = tools[name].annotations
        assert a.readOnlyHint is False and a.destructiveHint is True and a.idempotentHint is True
        assert "idempotency_key" in tools[name].inputSchema["required"]
    assert tools["get_job"].annotations.readOnlyHint is True
