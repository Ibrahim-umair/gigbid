"""Conversation graph (C1): one thread per client conversation.

START -> load_thread -> liaison (intent + draft) -> slots (interview requests only)
      -> compliance -> approval [interrupt] -> send -> END
Rejected or blocked replies end without sending."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.graphs.bid_graph import safe
from agent.nodes import liaison as L
from agent.state import ConversationState


def build_conversation_graph(checkpointer=None, store=None):
    g = StateGraph(ConversationState)
    for n in ("load_thread", "liaison", "slots", "compliance", "approval", "send"):
        g.add_node(n, safe(getattr(L, n)))
    g.add_edge(START, "load_thread")
    g.add_edge("load_thread", "liaison")
    g.add_edge("liaison", "slots")
    g.add_edge("slots", "compliance")
    g.add_conditional_edges("compliance",
                            lambda s: "approval" if s.get("status") != "blocked" else END,
                            ["approval", END])
    g.add_conditional_edges("approval",
                            lambda s: "send" if s["approval"]["action"] in {"approve", "edit"}
                            else END, ["send", END])
    g.add_edge("send", END)
    return g.compile(checkpointer=checkpointer, store=store)
