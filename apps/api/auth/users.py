"""Multi-user auth (sessions) + encrypted OAuth token store (E4).

Passwords: PBKDF2-SHA256. Sessions: random bearer tokens. Marketplace OAuth tokens: encrypted
with Fernet (key from APP_SECRET_KEY), never logged, scoped per user (tenant)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from cryptography.fernet import Fernet
from fastapi import Depends, Header, HTTPException

from apps.api.service import db


def _fernet() -> Fernet:
    secret = os.getenv("APP_SECRET_KEY", "dev-only-secret-change-me")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def init():
    db().executescript("""
    create table if not exists users (id text primary key, pw text, settings text);
    create table if not exists sessions (token text primary key, user_id text, created real);
    create table if not exists oauth_tokens (user_id text, provider text, token_enc blob,
        primary key (user_id, provider));""")
    reviewer_pw = os.getenv("REVIEWER_PASSWORD", "gigbid-review")
    for uid, pw in (("reviewer", reviewer_pw), ("demo", os.getenv("DEMO_PASSWORD", "demo"))):
        if not db().execute("select 1 from users where id=?", (uid,)).fetchone():
            create_user(uid, pw)


DEFAULT_SETTINGS = {"persona": "ml_engineer", "autonomy": "auto_skip_low_fit",
                    "weekly_connects_budget": 80, "hourly_floor": 35, "fixed_floor": 150,
                    "saved_searches": [{"query": "", "every_hours": 4}],
                    "marketplace": "gigsim"}


def _hash(pw: str, salt: bytes) -> str:
    return salt.hex() + ":" + hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000).hex()


def create_user(uid: str, pw: str):
    db().execute("insert into users values (?,?,?)",
                 (uid, _hash(pw, secrets.token_bytes(16)), json.dumps(DEFAULT_SETTINGS)))


def login(uid: str, pw: str) -> str:
    row = db().execute("select pw from users where id=?", (uid,)).fetchone()
    if not row:
        raise HTTPException(401, "invalid credentials")
    salt = bytes.fromhex(row["pw"].split(":")[0])
    if not hmac.compare_digest(_hash(pw, salt), row["pw"]):
        raise HTTPException(401, "invalid credentials")
    tok = secrets.token_urlsafe(32)
    db().execute("insert into sessions values (?,?,?)", (tok, uid, time.time()))
    return tok


def current_user(authorization: str = Header(default="")) -> str:
    tok = authorization.removeprefix("Bearer ").strip()
    row = db().execute("select user_id from sessions where token=?", (tok,)).fetchone()
    if not row:
        raise HTTPException(401, "not signed in")
    return row["user_id"]


def get_settings(uid: str) -> dict:
    row = db().execute("select settings from users where id=?", (uid,)).fetchone()
    return {**DEFAULT_SETTINGS, **json.loads(row["settings"])}


def put_settings(uid: str, s: dict):
    db().execute("update users set settings=? where id=?", (json.dumps(s), uid))


def store_oauth_token(uid: str, provider: str, token: str):
    db().execute("insert or replace into oauth_tokens values (?,?,?)",
                 (uid, provider, _fernet().encrypt(token.encode())))


def load_oauth_token(uid: str, provider: str) -> str | None:
    row = db().execute("select token_enc from oauth_tokens where user_id=? and provider=?",
                       (uid, provider)).fetchone()
    return _fernet().decrypt(row["token_enc"]).decode() if row else None


User = Depends(current_user)
