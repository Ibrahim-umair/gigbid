"""Background worker (E1): scheduled scouting + long agent runs on Arq/Redis, outside web
requests.

    arq worker.tasks.WorkerSettings

* scout_saved_searches: every saved search runs on its own schedule (GigSim: hourly cron here,
  live Upwork: marketplace.live_poll_minutes, see docs/RUNBOOK.md). New jobs are de-duplicated
  by job_id and only unseen ones are queued.
* analyze_job: runs the bid graph to the approval interrupt. Idempotent: the thread id is
  derived from (user, job), so a worker restart or a duplicate enqueue never re-analyses or
  double-submits (submission additionally carries an idempotency key).
"""
from __future__ import annotations

import os

from arq import cron
from arq.connections import RedisSettings

from agent.config import cfg


async def startup(ctx):
    from apps.api.auth import users
    from apps.api.service import RT
    await RT.start()
    users.init()
    ctx["rt"] = RT


async def shutdown(ctx):
    await ctx["rt"].stop()


async def analyze_job(ctx, user: str, job_id: str) -> str:
    from agent.mcp_client import hub
    job = await hub().call("scout", "get_job", {"job_id": job_id})
    tid = await ctx["rt"].start_run(user, "bid", job_id, {"job": job})
    await ctx["rt"].tasks[tid] if tid in ctx["rt"].tasks else None
    return tid


async def scout_saved_searches(ctx):
    from agent.mcp_client import hub
    from apps.api.auth.users import get_settings
    from apps.api.service import db, runs_for
    queued = []
    for (user,) in db().execute("select id from users").fetchall():
        seen = {r["ref_id"] for r in runs_for(user, "bid")}
        for search in get_settings(user).get("saved_searches", []):
            res = await hub().call("scout", "search_jobs",
                                   {"query": search.get("query", ""), "limit": 20})
            for j in res["jobs"]:
                if j["job_id"] not in seen:  # de-dup
                    seen.add(j["job_id"])
                    await ctx["redis"].enqueue_job("analyze_job", user, j["job_id"],
                                                   _job_id=f"analyze:{user}:{j['job_id']}")
                    queued.append(j["job_id"])
    return queued


SCOUT_MINUTE = {0} if cfg("marketplace", "mode") == "gigsim" else {0}


class WorkerSettings:
    functions = [analyze_job, scout_saved_searches]
    cron_jobs = [cron(scout_saved_searches, minute=SCOUT_MINUTE,
                      hour=None if cfg("marketplace", "mode") == "gigsim"
                      else set(range(0, 24, max(1, cfg("marketplace", "live_poll_minutes")
                                                // 60))))]
    on_startup, on_shutdown = startup, shutdown
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    max_jobs = 2  # polite: few concurrent runs, stays under marketplace rate limits
