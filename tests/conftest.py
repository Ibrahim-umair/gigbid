"""Isolate all state in a temp dir and force the fake LLM (0 paid calls in tests)."""
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="gigbid-test-")
os.environ.update({
    "GIGBID_LLM": "fake",
    "GIGSIM_DB": os.path.join(_TMP, "gigsim.sqlite"),
    "GIGBID_CHECKPOINTS": os.path.join(_TMP, "ckpt.sqlite"),
    "GIGBID_STORE": os.path.join(_TMP, "memory.sqlite"),
    "GIGBID_AUDIT_LOG": os.path.join(_TMP, "audit.jsonl"),
    "GIGBID_WORKSPACE": os.path.join(_TMP, "workspace.json"),
    "GIGSIM_BASE_URL": "inproc",
})
