import json

from agent.config import ROOT
from agent.guards import compliance_scan, detect_injection, mask_pii, redact, scam_signals


def _syn():
    """Dev split only: the test split is held out and measured, never tuned on."""
    jobs = json.loads((ROOT / "data/gigsim_seed/jobs_synthetic.json").read_text(encoding="utf-8"))
    return [j for j in jobs if j["split"] == "dev"]


def test_planted_injections_detected():
    inj = [j for j in _syn() if j.get("attack")]
    hit = [j["job_id"] for j in inj if detect_injection(j["description"])]
    assert len(hit) == len(inj), f"missed: {set(j['job_id'] for j in inj) - set(hit)}"


def test_scam_jobs_raise_signals():
    scams = [j for j in _syn() if not j.get("attack")]
    flagged = [j for j in scams if scam_signals(j["title"] + " " + j["description"])]
    assert len(flagged) == len(scams)


def test_pii_masked():
    out = mask_pii("mail me jo@x.com or +1 (555) 123-4567")
    assert "jo@x.com" not in out and "555" not in out


def test_compliance_scan_and_redact():
    text = "I built a RAG bot. Message me on WhatsApp. I guarantee 100% accuracy."
    assert {"off_platform", "guarantee"} <= set(compliance_scan(text))
    assert compliance_scan(redact(text)) == []
    assert "RAG bot" in redact(text)
