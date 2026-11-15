"""Workspace MCP server (A3): calendar slots, tentative interview holds, email drafts.
Backed by a documented local mock (data/processed/workspace.json); swapping in Google Calendar /
Gmail changes this file only — agents see the same MCP tools."""
from __future__ import annotations

import datetime as dt
import json
import os
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from agent.config import ROOT

STORE = ROOT / os.getenv("GIGBID_WORKSPACE", "data/processed/workspace.json")
mcp = FastMCP("gigbid-workspace")
WORK_HOURS = (9, 17)


class Slot(BaseModel):
    start: str
    end: str


class SlotList(BaseModel):
    slots: list[Slot]


def _load() -> dict:
    return json.loads(STORE.read_text()) if STORE.exists() else {"holds": [], "drafts": []}


def _save(d: dict):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(d, indent=1))


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True))
def free_slots(days_ahead: Annotated[int, Field(ge=1, le=14)] = 5,
               duration_min: Annotated[int, Field(ge=15, le=120)] = 30,
               max_slots: Annotated[int, Field(ge=1, le=10)] = 3,
               start_date: str | None = None) -> SlotList:
    """Free interview slots on weekdays within working hours, excluding existing holds."""
    held = {h["start"] for h in _load()["holds"]}
    day = dt.date.fromisoformat(start_date) if start_date else dt.date.today()
    out: list[Slot] = []
    for d in range(1, days_ahead + 1):
        date = day + dt.timedelta(days=d)
        if date.weekday() >= 5:
            continue
        for hour in (10, 14, 16):
            s = dt.datetime(date.year, date.month, date.day, hour)
            if s.isoformat() not in held and WORK_HOURS[0] <= hour < WORK_HOURS[1]:
                out.append(Slot(start=s.isoformat(),
                                end=(s + dt.timedelta(minutes=duration_min)).isoformat()))
            if len(out) >= max_slots:
                return SlotList(slots=out)
    return SlotList(slots=out)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                      idempotentHint=True))
def create_interview_hold(start: str, end: str,
                          title: Annotated[str, Field(max_length=200)]) -> dict:
    """Create a tentative calendar hold (idempotent on start time)."""
    d = _load()
    if not any(h["start"] == start for h in d["holds"]):
        d["holds"].append({"start": start, "end": end, "title": title, "status": "tentative"})
        _save(d)
    return {"status": "tentative", "start": start}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                      idempotentHint=False))
def create_email_draft(to: Annotated[str, Field(max_length=200)],
                       subject: Annotated[str, Field(max_length=200)],
                       body: Annotated[str, Field(max_length=5000)]) -> dict:
    """Create an email draft (never sends)."""
    d = _load()
    d["drafts"].append({"to": to, "subject": subject, "body": body})
    _save(d)
    return {"status": "draft", "id": len(d["drafts"])}


if __name__ == "__main__":
    mcp.run()
