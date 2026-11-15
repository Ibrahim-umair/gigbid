from agent.memory.promotion_rules import record_edit, record_outcome
from agent.memory.store import outcome_notes, style_rules

BEFORE = "I am passionate about AI. You need a chatbot. I built three bots."
AFTER = "You need a chatbot. I built three bots."


def test_style_rule_needs_two_distinct_edits():
    assert record_edit("u1", "t1", BEFORE, AFTER) == []
    assert record_edit("u1", "t1", BEFORE, AFTER) == []  # same thread does not count twice
    promoted = record_edit("u1", "t2", BEFORE, AFTER)
    assert promoted and any("opening" in r for r in style_rules("u1"))


def test_outcome_promoted_only_with_enough_evidence():
    assert not record_outcome("u2", "ml_ai", "p1", "replied")
    assert not record_outcome("u2", "ml_ai", "p2", "lost")
    assert outcome_notes("u2", "ml_ai") is None
    assert record_outcome("u2", "ml_ai", "p3", "hired")
    assert outcome_notes("u2", "ml_ai")["reply_rate"] == round(2 / 3, 2)
