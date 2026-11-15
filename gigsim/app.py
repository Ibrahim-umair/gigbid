"""GigSim: marketplace simulator for development and evaluation.

Jobs: REAL Kaggle Upwork 2024 postings (data/processed) + SYNTHETIC scams/injections
(data/gigsim_seed). Clients are synthetic, each with hidden preferences used by a simulated
client (LLM node `sim_client`, or a deterministic heuristic under the fake backend) to decide
reply / interview / hire. Behaves like a real platform: bearer auth, per-token rate limit (429),
optional random 503s, Connects balance, idempotent writes, dry_run previews.
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
import threading
import time
from pathlib import Path

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
POLICY = yaml.safe_load((ROOT / "gigsim/policy.yaml").read_text(encoding="utf-8"))
DB = Path(os.getenv("GIGSIM_DB", ROOT / "data/processed/gigsim.sqlite"))
TOKENS = {t.split(":")[0]: t.split(":")[1] for t in
          os.getenv("GIGSIM_TOKENS", "dev-token:demo,reviewer-token:reviewer").split(",")}
_lock = threading.Lock()
_hits: dict[str, list[float]] = {}
_rng = random.Random(7)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def connects_for(job: dict) -> int:
    if job.get("connects_cost"):
        return int(job["connects_cost"])
    if job.get("is_hourly"):
        return POLICY["hourly_connects_cost"]
    b = job.get("budget") or 0
    for tier in POLICY["connects_cost"]:
        if tier["max_budget"] is None or b <= tier["max_budget"]:
            return tier["cost"]
    return 8


def _seed() -> tuple[dict, dict]:
    jobs = (_load(ROOT / "data/processed/jobs_real_dev.json")
            + _load(ROOT / "data/processed/jobs_real_test.json")
            + _load(ROOT / "data/gigsim_seed/jobs_synthetic.json"))
    clients = {c["client_id"]: c for c in _load(ROOT / "data/gigsim_seed/clients.json")}
    owner = {j: c["client_id"] for c in clients.values() for j in c["job_ids"]}
    out = {}
    for seq, j in enumerate(jobs):
        j = dict(j)
        j["client_id"] = owner.get(j["job_id"])
        j["connects_cost"] = connects_for(j)
        j["seq"] = seq
        out[j["job_id"]] = j
    return out, clients


JOBS, CLIENTS = _seed()


def db() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript("""
    create table if not exists balances (user text primary key, connects int);
    create table if not exists proposals (id text primary key, user text, job_id text,
        body text, status text, outcome text, created real);
    create table if not exists idem (user text, key text, response text,
        primary key (user, key));
    create table if not exists messages (id text primary key, user text, thread_id text,
        sender text, text text, ts real);
    """)
    return con


def auth(request: Request, authorization: str = Header(default="")) -> str:
    token = authorization.removeprefix("Bearer ").strip()
    if token not in TOKENS:
        raise HTTPException(401, "invalid token")
    now = time.time()
    with _lock:
        hits = [t for t in _hits.get(token, []) if now - t < 60]
        if len(hits) >= POLICY["rate_limit_per_minute"]:
            raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": "5"})
        hits.append(now)
        _hits[token] = hits
    if _rng.random() < float(os.getenv("GIGSIM_ERROR_RATE", POLICY["error_rate"])):
        raise HTTPException(503, "temporarily unavailable")
    return TOKENS[token]


app = FastAPI(title="GigSim", version=str(POLICY["version"]))


def public_job(j: dict) -> dict:
    return {k: v for k, v in j.items() if k not in {"split", "attack", "seq"}}


@app.get("/v1/health")
def health():
    return {"status": "ok", "jobs": len(JOBS), "policy_version": POLICY["version"]}


@app.get("/v1/jobs")
def search_jobs(q: str = "", limit: int = 20, since_seq: int = -1, user: str = Depends(auth)):
    terms = [t for t in q.lower().split() if t]
    hits = [j for j in JOBS.values() if j["seq"] > since_seq and
            all(t in (j["title"] + " " + j["description"]).lower() for t in terms)]
    hits.sort(key=lambda j: j["seq"])
    return {"jobs": [public_job(j) for j in hits[:limit]],
            "next_seq": hits[min(limit, len(hits)) - 1]["seq"] if hits else since_seq}


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str, user: str = Depends(auth)):
    if job_id not in JOBS:
        raise HTTPException(404, "job not found")
    return public_job(JOBS[job_id])


@app.get("/v1/clients/{client_id}")
def get_client(client_id: str, user: str = Depends(auth)):
    c = CLIENTS.get(client_id)
    if not c:
        raise HTTPException(404, "client not found")
    return {k: v for k, v in c.items() if k != "hidden_prefs"}


@app.get("/v1/connects")
def connects(user: str = Depends(auth)):
    con = db()
    row = con.execute("select connects from balances where user=?", (user,)).fetchone()
    if not row:
        con.execute("insert into balances values (?,?)", (user, POLICY["starting_connects"]))
        con.commit()
        return {"user": user, "connects": POLICY["starting_connects"]}
    return {"user": user, "connects": row["connects"]}


class ProposalIn(BaseModel):
    job_id: str
    cover_letter: str = Field(min_length=1)
    bid_type: str = Field(pattern="^(fixed|hourly)$")
    bid_amount: float = Field(gt=0)
    screening_answers: list[str] = Field(default_factory=list)


@app.post("/v1/proposals")
def submit_proposal(p: ProposalIn, dry_run: bool = False,
                    idempotency_key: str = Header(default=""), user: str = Depends(auth)):
    if p.job_id not in JOBS:
        raise HTTPException(404, "job not found")
    n = len(p.cover_letter)
    if not POLICY["min_cover_letter_chars"] <= n <= POLICY["max_cover_letter_chars"]:
        raise HTTPException(422, f"cover letter length {n} outside policy bounds")
    cost = JOBS[p.job_id]["connects_cost"]
    bal = connects(user)["connects"]
    preview = {"job_id": p.job_id, "connects_cost": cost, "balance_before": bal,
               "balance_after": bal - cost, "payload": p.model_dump(),
               "policy_version": POLICY["version"]}
    if dry_run:
        return {"dry_run": True, **preview}
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header required")
    con = db()
    with _lock:
        row = con.execute("select response from idem where user=? and key=?",
                          (user, idempotency_key)).fetchone()
        if row:
            return {**json.loads(row["response"]), "idempotent_replay": True}
        if bal < cost:
            raise HTTPException(402, "not enough connects")
        pid = f"prop-{int(time.time() * 1000)}-{_rng.randint(100, 999)}"
        con.execute("update balances set connects=connects-? where user=?", (cost, user))
        con.execute("insert into proposals values (?,?,?,?,?,?,?)",
                    (pid, user, p.job_id, p.model_dump_json(), "submitted", None, time.time()))
        resp = {"proposal_id": pid, "status": "submitted", "connects_spent": cost,
                "balance_after": bal - cost}
        con.execute("insert into idem values (?,?,?)", (user, idempotency_key, json.dumps(resp)))
        con.commit()
    return resp


@app.get("/v1/proposals")
def list_proposals(user: str = Depends(auth)):
    rows = db().execute("select id, job_id, status, outcome from proposals where user=?",
                        (user,)).fetchall()
    return {"proposals": [dict(r) for r in rows]}


@app.get("/v1/proposals/{pid}")
def get_proposal(pid: str, user: str = Depends(auth)):
    r = db().execute("select * from proposals where id=? and user=?", (pid, user)).fetchone()
    if not r:
        raise HTTPException(404, "proposal not found")
    return {**dict(r), "body": json.loads(r["body"]),
            "outcome": json.loads(r["outcome"]) if r["outcome"] else None}


@app.post("/v1/sim/advance")
async def advance(user: str = Depends(auth)):
    """Let simulated clients read pending proposals and decide (reply / interview / hire)."""
    from gigsim.client_sim import decide
    con = db()
    rows = con.execute("select * from proposals where user=? and status='submitted'",
                       (user,)).fetchall()
    results = []
    for r in rows:
        job = JOBS[r["job_id"]]
        client = CLIENTS.get(job.get("client_id"), {})
        dec = await decide(job, client, json.loads(r["body"]))
        status = ("hired" if dec["hired"] else "interview" if dec["interview"]
                  else "replied" if dec["replied"] else "lost")
        con.execute("update proposals set status=?, outcome=? where id=?",
                    (status, json.dumps(dec), r["id"]))
        results.append({"proposal_id": r["id"], "job_id": r["job_id"], "status": status})
    con.commit()
    return {"advanced": results}


class MessageIn(BaseModel):
    thread_id: str
    text: str = Field(min_length=1, max_length=4000)


@app.get("/v1/messages")
def list_messages(thread_id: str | None = None, user: str = Depends(auth)):
    seed = {t["thread_id"]: t for t in _load(ROOT / "data/gigsim_seed/messages.json")}
    threads = [seed[thread_id]] if thread_id in seed else list(seed.values())
    rows = db().execute("select * from messages where user=?", (user,)).fetchall()
    out = []
    for t in threads:
        extra = [{"from": "freelancer", "text": r["text"], "ts": r["ts"]} for r in rows
                 if r["thread_id"] == t["thread_id"]]
        out.append({**t, "messages": t["messages"] + extra})
    return {"threads": out}


@app.post("/v1/messages")
def send_message(m: MessageIn, idempotency_key: str = Header(default=""),
                 user: str = Depends(auth)):
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header required")
    con = db()
    with _lock:
        row = con.execute("select response from idem where user=? and key=?",
                          (user, idempotency_key)).fetchone()
        if row:
            return {**json.loads(row["response"]), "idempotent_replay": True}
        mid = f"msg-{int(time.time() * 1000)}"
        con.execute("insert into messages values (?,?,?,?,?,?)",
                    (mid, user, m.thread_id, "freelancer", m.text, time.time()))
        resp = {"message_id": mid, "status": "sent"}
        con.execute("insert into idem values (?,?,?)", (user, idempotency_key, json.dumps(resp)))
        con.commit()
    return resp
