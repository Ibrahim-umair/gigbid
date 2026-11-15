"""GigSim adapter: REST client with timeouts, bounded retries + backoff on 429/5xx."""
from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from agent.marketplace_port import MarketplaceUnavailable


class GigSimAdapter:
    def __init__(self, token: str | None = None, base_url: str | None = None,
                 retries: int = 3, timeout: float = 15.0):
        self.token = token or os.getenv("GIGSIM_API_TOKEN", "dev-token")
        base = base_url or os.getenv("GIGSIM_BASE_URL", "inproc")
        if base == "inproc":  # same-process GigSim (tests, offline eval)
            from gigsim.app import app
            self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                            base_url="http://gigsim", timeout=timeout)
        else:
            self.client = httpx.AsyncClient(base_url=base, timeout=timeout)
        self.retries = retries

    async def _req(self, method: str, path: str, **kw) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.token}", **kw.pop("headers", {})}
        last = None
        for attempt in range(self.retries + 1):
            try:
                r = await self.client.request(method, path, headers=headers, **kw)
                if r.status_code in (429, 500, 502, 503, 504):
                    last = f"{r.status_code} {r.text[:100]}"
                    wait = float(r.headers.get("Retry-After", 2 ** attempt))
                    await asyncio.sleep(min(wait, 10))
                    continue
                if r.status_code >= 400:
                    raise ValueError(f"GigSim {r.status_code}: {r.text[:300]}")
                return r.json()
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last = repr(e)
                await asyncio.sleep(min(2 ** attempt, 10))
        raise MarketplaceUnavailable(f"GigSim unavailable after retries: {last}")

    async def search_jobs(self, query: str, limit: int = 20, since_seq: int = -1):
        return await self._req("GET", "/v1/jobs",
                               params={"q": query, "limit": limit, "since_seq": since_seq})

    async def get_job(self, job_id: str):
        return await self._req("GET", f"/v1/jobs/{job_id}")

    async def get_client_history(self, client_id: str):
        return await self._req("GET", f"/v1/clients/{client_id}")

    async def get_connects_balance(self):
        return await self._req("GET", "/v1/connects")

    async def list_messages(self, thread_id: str | None = None):
        return await self._req("GET", "/v1/messages",
                               params={"thread_id": thread_id} if thread_id else {})

    async def create_proposal_draft(self, payload: dict[str, Any]):
        # GigSim has no server-side drafts; a draft is the validated dry-run preview.
        return await self._req("POST", "/v1/proposals", params={"dry_run": True}, json=payload)

    async def submit_proposal(self, payload: dict[str, Any], idempotency_key: str,
                              dry_run: bool = False):
        return await self._req("POST", "/v1/proposals", params={"dry_run": dry_run},
                               json=payload, headers={"Idempotency-Key": idempotency_key})

    async def send_message(self, thread_id: str, text: str, idempotency_key: str):
        return await self._req("POST", "/v1/messages",
                               json={"thread_id": thread_id, "text": text},
                               headers={"Idempotency-Key": idempotency_key})

    async def advance(self):
        return await self._req("POST", "/v1/sim/advance")
