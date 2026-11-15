"""Bid graph (C1): one thread per job.

START ─Send─┬─ analyst ───────┐
            ├─ risk_assessor ─┼─> decide ─(bid)─> pricing ─> writer ─> verifier ─> critic
            └─ fit_matcher ───┘      │(skip/watch)                 ^                │
                                     v                             └─(send back ≤2)─┤
                                    END                                             v
            END <─(reject)─ approval_gate [interrupt] <─(allowed)─ compliance <─────┘
                       (approve)│      └─(edit)─> compliance (re-check)
                                v
                              submit ─> END

Failure states: degraded_queued (marketplace down), needs_attention (step/token budget),
dead_letter (unrecoverable node error), blocked (compliance)."""
from __future__ import annotations

import functools
import inspect
import traceback

from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agent.llm import BudgetExceeded
from agent.marketplace_port import MarketplaceUnavailable
from agent.nodes import bid as N
from agent.state import BidState

FAIL = {"degraded_queued", "needs_attention", "dead_letter", "blocked", "rejected", "skipped",
        "watching"}


def safe(fn):
    """Per-node failure handling: route failures to visible states instead of crashing."""
    takes_config = "config" in inspect.signature(fn).parameters

    async def run(state, config=None):
        if state.get("status") in FAIL - {"rejected"}:
            return {}
        try:
            res = fn(state, config) if takes_config else fn(state)
            return await res if inspect.isawaitable(res) else res
        except GraphBubbleUp:  # interrupts must propagate
            raise
        except MarketplaceUnavailable as e:
            return {"status": "degraded_queued", "errors": [f"{fn.__name__}: {e}"],
                    "trace": N._t(fn.__name__, error="marketplace unavailable")}
        except BudgetExceeded as e:
            return {"status": "needs_attention", "errors": [f"{fn.__name__}: {e}"]}
        except Exception as e:
            return {"status": "dead_letter",
                    "errors": [f"{fn.__name__}: {e!r}\n{traceback.format_exc(limit=3)}"],
                    "trace": N._t(fn.__name__, error=repr(e))}

    if takes_config:
        @functools.wraps(fn)
        async def wrapped(state, config):
            return await run(state, config)
    else:
        @functools.wraps(fn)
        async def wrapped(state):
            return await run(state)
    return wrapped


def fan_out(state: BidState):
    return [Send(n, state) for n in ("analyst", "risk_assessor", "fit_matcher")]


def _ok(state) -> bool:
    return state.get("status") not in FAIL


def route_decide(state):
    return "pricing" if _ok(state) and state["decision"]["action"] == "bid" else END


def route_pricing(state):
    return "writer" if _ok(state) else END


def route_compliance(state):
    if not _ok(state):
        return END
    return "needs_attention" if N.over_budget(state) else "approval_gate"


def route_approval(state):
    if state.get("status") in FAIL:
        return END
    return {"submit": "submit", "compliance": "compliance"}.get(N.route_after_approval(state),
                                                                END)


def route_critic(state):
    return N.route_after_critic(state) if _ok(state) else END


def build_bid_graph(checkpointer=None, store=None):
    g = StateGraph(BidState)
    for name in ["analyst", "risk_assessor", "fit_matcher", "decide", "pricing", "writer",
                 "verifier", "critic", "compliance", "approval_gate", "submit",
                 "needs_attention"]:
        g.add_node(name, safe(getattr(N, name)))
    g.add_conditional_edges(START, fan_out, ["analyst", "risk_assessor", "fit_matcher"])
    for n in ("analyst", "risk_assessor", "fit_matcher"):
        g.add_edge(n, "decide")
    g.add_conditional_edges("decide", route_decide, ["pricing", END])
    g.add_conditional_edges("pricing", route_pricing, ["writer", END])
    g.add_edge("writer", "verifier")
    g.add_edge("verifier", "critic")
    g.add_conditional_edges("critic", route_critic, ["writer", "compliance", "needs_attention",
                                                     END])
    g.add_conditional_edges("compliance", route_compliance, ["approval_gate", "needs_attention",
                                                             END])
    g.add_conditional_edges("approval_gate", route_approval, ["submit", "compliance", END])
    g.add_edge("submit", END)
    g.add_edge("needs_attention", END)
    return g.compile(checkpointer=checkpointer, store=store)
