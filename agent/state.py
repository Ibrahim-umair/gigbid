"""Graph state (C2).

Three things are kept apart:
  * State (this module): what one job/conversation needs right now.
  * Execution trace: `trace` here is a per-thread audit list (tool, args, result summary, node);
    the durable copy is the MCP servers' audit log + LangSmith/Langfuse spans.
  * Long-term memory: only promoted knowledge in the LangGraph store (agent/memory/), never raw
    tool output.
Parallel branches (analyst / risk / matcher) write to distinct keys; shared accumulators use
additive reducers so concurrent writes merge instead of clobbering.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_usage(a: dict | None, b: dict | None) -> dict:
    out = dict(a or {})
    for node, u in (b or {}).items():
        cur = out.setdefault(node, {"calls": 0, "in": 0, "out": 0, "cost": 0.0, "secs": 0.0})
        for k in cur:
            cur[k] += u.get(k, 0)
    return out


class BidState(TypedDict, total=False):
    user_id: str
    job: dict[str, Any]              # raw job (untrusted text inside)
    client: dict[str, Any]           # client history from marketplace
    job_spec: dict[str, Any]         # JobSpec
    risk: dict[str, Any]             # RiskReport
    fit: dict[str, Any]              # FitReport
    evidence: dict[str, dict]        # evidence_id -> item (retrieved, shown to writer + UI)
    decision: dict[str, Any]         # BidDecision
    price: dict[str, Any]            # PriceQuote
    draft: dict[str, Any]            # ProposalDraft (latest)
    verification: dict[str, Any]     # ClaimVerification of latest draft
    unsupported_before: int          # unsupported claims before verification rewrite
    critiques: Annotated[list[dict], operator.add]
    revisions: int
    compliance: dict[str, Any]       # ComplianceVerdict
    preview: dict[str, Any]          # dry_run preview from marketplace
    approval: dict[str, Any]         # {action: approve|edit|reject, text?, reason?}
    submission: dict[str, Any]
    status: str                      # running|skipped|awaiting_approval|submitted|rejected|
                                     # blocked|needs_attention|dead_letter
    steps: Annotated[int, operator.add]
    usage: Annotated[dict, merge_usage]
    trace: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]


class ConversationState(TypedDict, total=False):
    user_id: str
    thread: dict[str, Any]
    reply: dict[str, Any]
    slots: list[dict]
    compliance: dict[str, Any]
    approval: dict[str, Any]
    sent: dict[str, Any]
    status: str
    steps: Annotated[int, operator.add]
    usage: Annotated[dict, merge_usage]
    trace: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]
