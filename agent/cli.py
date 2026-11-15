"""GigBid CLI.

    python -m agent.cli run real-28572            # analyse + draft; stops at approval
    python -m agent.cli pending <thread>          # show the approval payload
    python -m agent.cli approve <thread>          # approve -> submit (exactly once)
    python -m agent.cli reject <thread> "reason"
    python -m agent.cli edit <thread> file.txt
"""
from __future__ import annotations

import asyncio
import json
import sys

from agent.mcp_client import hub
from agent.runner import final_state, pending_approval, resume, session, stream_job


def _print(node, upd):
    tr = (upd or {}).get("trace") or [{}]
    info = {k: v for k, v in tr[-1].items() if k not in {"node", "ts"}}
    print(f"  ✓ {node:<14} {json.dumps(info, default=str)[:160]}", flush=True)


async def main(argv: list[str]):
    cmd, arg = argv[0], argv[1]
    async with session() as g:
        if cmd == "run":
            job = await hub().call("scout", "get_job", {"job_id": arg})
            tid = f"job-{arg}"
            print(f"thread {tid}: {job['title']}")
            async for node, upd in stream_job(g, job, tid):
                if node != "__interrupt__":
                    _print(node, upd)
            st = await final_state(g, tid)
            print("status:", st.get("status"), "| decision:", st.get("decision"))
            if await pending_approval(g, tid):
                print("\n--- awaiting approval ---\n" + st["draft"]["cover_letter"])
        elif cmd == "pending":
            print(json.dumps(await pending_approval(g, arg), indent=1, default=str)[:4000])
        elif cmd in {"approve", "reject", "edit"}:
            decision = {"action": cmd}
            if cmd == "reject":
                decision["reason"] = argv[2] if len(argv) > 2 else ""
            if cmd == "edit":
                decision["text"] = open(argv[2], encoding="utf-8").read()
            async for node, upd in resume(g, arg, decision):
                if node != "__interrupt__":
                    _print(node, upd)
            st = await final_state(g, arg)
            print("status:", st.get("status"), "| submission:", st.get("submission"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main(sys.argv[1:]))
