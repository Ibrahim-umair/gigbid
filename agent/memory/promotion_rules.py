"""Explicit promotion rules (R7). Observations are staged; promotion needs repetition/evidence.

Style rule: an edit pattern (deleted phrase / cut opening sentence) observed in >= 2 distinct
approved edits is promoted to a style rule the Writer must follow.
Outcome rule: a job category's reply/hire stats are promoted once >= 3 proposals in that category
have a known outcome; below that the numbers are noise and nothing is written.
"""
from __future__ import annotations

import difflib
import hashlib
import re

from agent.memory.store import get_store

STYLE_MIN_OBS = 2
OUTCOME_MIN_N = 3


def edit_patterns(before: str, after: str) -> list[str]:
    pats = []
    b_sents = re.split(r"(?<=[.!?])\s+", before.strip())
    a = after.strip()
    if b_sents and b_sents[0] and b_sents[0] not in a:
        pats.append("cut_first_sentence")
    sm = difflib.SequenceMatcher(a=before.split(), b=after.split())
    for op, i1, i2, _, _ in sm.get_opcodes():
        if op == "delete" and 1 <= i2 - i1 <= 4:
            phrase = re.sub(r"[^\w\s-]", "", " ".join(before.split()[i1:i2]).lower()).strip()
            if phrase:
                pats.append(f"delete:{phrase}")
    return pats


RULE_TEXT = {"cut_first_sentence": "Start directly with the client's problem; no warm-up "
                                   "opening sentence."}


def record_edit(user: str, thread_id: str, before: str, after: str) -> list[str]:
    """Stage observations from one approved edit; return newly promoted rules."""
    s = get_store()
    promoted = []
    for pat in set(edit_patterns(before, after)):
        key = hashlib.sha1(pat.encode()).hexdigest()[:12]
        obs = s.get(("style_obs", user), key)
        threads = set(obs.value["threads"]) if obs else set()
        threads.add(thread_id)
        s.put(("style_obs", user), key, {"pattern": pat, "threads": sorted(threads)})
        if len(threads) >= STYLE_MIN_OBS and not s.get(("style", user), key):
            rule = RULE_TEXT.get(pat) or f"Never use the phrase \"{pat.split(':', 1)[1]}\"."
            s.put(("style", user), key, {"rule": rule, "pattern": pat, "support": len(threads)})
            promoted.append(rule)
    return promoted


def record_outcome(user: str, category: str, proposal_id: str, status: str) -> bool:
    """Stage one outcome; promote category stats once there is enough evidence."""
    s = get_store()
    obs = s.get(("outcome_obs", user), category)
    seen = dict(obs.value["seen"]) if obs else {}
    seen[proposal_id] = status
    s.put(("outcome_obs", user), category, {"seen": seen})
    n = len(seen)
    if n < OUTCOME_MIN_N:
        return False
    replied = sum(v in {"replied", "interview", "hired"} for v in seen.values())
    s.put(("outcome", user), category, {"n": n, "reply_rate": round(replied / n, 2),
                                        "hire_rate": round(sum(v == "hired" for v in
                                                               seen.values()) / n, 2)})
    return True
