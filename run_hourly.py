#!/usr/bin/env python3
"""Hourly SEO autopilot: generate and publish 25 articles per site.

Uses a non-blocking lock so a slow run cannot overlap the next timer tick.
"""
from __future__ import annotations

import concurrent.futures, fcntl, json, os, sys, time
from pathlib import Path

from autopilot import LOG_DIR, ROOT, SITES, log_event, now
from pipeline import run_site
import monitor

LOCK = ROOT / "autopilot.lock"
PER_SITE = int(os.environ.get("PER_SITE", "25"))
# Sites are generated in parallel; each site runs GEN_WORKERS generators, so
# the yuxor lane sees SITE_WORKERS * GEN_WORKERS requests. The local proxy
# queues them against the upstream's 5-stream cap instead of failing.
SITE_WORKERS = int(os.environ.get("SITE_WORKERS", "2"))
RUN_LOG = LOG_DIR / "hourly.jsonl"


def main() -> int:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    fh = LOCK.open("w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another run is active; skipping")
        return 0
    fh.write(str(os.getpid()))
    fh.flush()
    started = time.time()
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=SITE_WORKERS) as ex:
        futs = {ex.submit(run_site, key, PER_SITE, True): key for key in SITES}
        for f in concurrent.futures.as_completed(futs):
            key = futs[f]
            try:
                results[key] = f.result()
            except Exception as e:
                results[key] = {"site": key, "error": str(e)}
                log_event("hourly_error", site=key, error=str(e)[:600])
    summary = {
        "time": now(), "seconds": round(time.time() - started, 1),
        "per_site": PER_SITE, "results": results,
    }
    with RUN_LOG.open("a") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    fcntl.flock(fh, fcntl.LOCK_UN)
    fh.close()
    monitor.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
