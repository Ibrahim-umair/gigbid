from agent.handoffs import (Claim, ClaimCheck, ClaimVerification, FitReport, ProposalDraft,
                            RiskReport)
from rag.verify import apply_fixes, precheck


def test_scores_bounded():
    assert 0 <= RiskReport(score=0.5).score <= 1
    assert 0 <= FitReport(score=0.8).score <= 1


def test_precheck_marks_uncited_claims_unsupported():
    d = ProposalDraft(cover_letter="x", claims=[Claim(text="A", evidence_ids=["cs-99"]),
                                                Claim(text="B", evidence_ids=["cs-01"])])
    to_llm, auto = precheck(d, {"cs-01": {}})
    assert [a.claim for a in auto] == ["A"] and to_llm[0]["claim"] == "B"


def test_apply_fixes_removes_and_rewrites():
    d = ProposalDraft(cover_letter="Intro here. I cut costs 90% for a bank. I built a bot.",
                      claims=[Claim(text="I cut costs 90% for a bank.", evidence_ids=["cs-1"]),
                              Claim(text="I built a bot.", evidence_ids=["cs-2"])])
    v = ClaimVerification(checks=[
        ClaimCheck(claim="I cut costs 90% for a bank.", verdict="unsupported", fix=None),
        ClaimCheck(claim="I built a bot.", verdict="partly_supported", fix=None)])
    out = apply_fixes(d, v)
    assert "90%" not in out.cover_letter and "I built a bot." in out.cover_letter
    assert len(out.claims) == 1


def test_citation_tags_stripped_from_letter():
    d = ProposalDraft(cover_letter="I built a voice bot [cs-11] and a YOLO app (repo-02, cs-03).",
                      claims=[])
    out = apply_fixes(d, ClaimVerification(checks=[]))
    assert "[" not in out.cover_letter and "repo-02" not in out.cover_letter
