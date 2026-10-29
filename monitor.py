#!/usr/bin/env python3
"""Monitor the SEO autopilot and write a human-readable report.

Run every 15 minutes (systemd timer). Exit code 1 when an alert is present.
Writes:
  STATUS.md   — current state
  ALERTS.md   — only when something needs attention
"""
from __future__ import annotations

import datetime as dt, json, re, sqlite3, subprocess
from pathlib import Path

import requests

from autopilot import LOG_DIR, QUEUE_DIR, ROOT, SITES, SSH, load_queue, open_db

STATUS = ROOT / "STATUS.md"
ALERTS = ROOT / "ALERTS.md"


def last_run(site_key: str):
    p = LOG_DIR / "events.jsonl"
    if not p.exists():
        return None
    lines = p.read_text().splitlines()[-500:]
    for line in reversed(lines):
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("kind") == "run" and e.get("site") == site_key:
            return e
    return None


def live_article_count(domain: str) -> int | None:
    try:
        html = requests.get(domain + "/articles", timeout=30).text
        return len(set(re.findall(r'href="(/articles/[^"#?]+)"', html)))
    except Exception:
        return None


def check(site_key: str) -> dict:
    site = SITES[site_key]
    con = open_db(site)
    total = con.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    published = con.execute("SELECT COUNT(*) FROM articles WHERE published=1").fetchone()[0]
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    sample = con.execute(
        "SELECT slug FROM articles WHERE published=1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    con.close()

    q = load_queue(site)
    pending = sum(1 for x in q if x.get("status") == "pending")
    failed = sum(1 for x in q if x.get("status") == "failed")
    last = last_run(site_key)
    live = live_article_count(site["domain"])
    try:
        services = subprocess.check_output(
            ["ssh", SSH, f"systemctl is-active {site['service']}"], text=True, timeout=30
        ).strip()
    except Exception as e:
        services = f"error: {e}"

    alerts = []
    if integrity != "ok":
        alerts.append(f"{site_key}: DB integrity={integrity}")
    if services != "active":
        alerts.append(f"{site_key}: service {site['service']} is {services}")
    if live is not None and live != published:
        alerts.append(f"{site_key}: /articles shows {live}, DB published={published}")
    if last:
        try:
            age = (dt.datetime.now(dt.timezone.utc) -
                   dt.datetime.fromisoformat(last["time"].replace("Z", "+00:00"))).total_seconds() / 60
        except Exception:
            age = None
        if pending > 0 and age is not None and age > 90:
            alerts.append(f"{site_key}: last run {age:.0f} min ago; {pending} pending")
        if last.get("failed", 0) > 0:
            rate = last["failed"] / max(1, last.get("requested", 1))
            alerts.append(f"{site_key}: last run had {last['failed']} failed ({rate:.0%})")
    else:
        if pending > 0:
            alerts.append(f"{site_key}: no run recorded; {pending} pending")

    return {
        "site": site_key, "total": total, "published": published,
        "pending": pending, "failed": failed, "live": live, "service": services,
        "integrity": integrity, "last_run": last.get("time") if last else None,
        "last_ok": last.get("ok") if last else None,
        "last_failed": last.get("failed") if last else None,
        "sample": f"{site['domain']}/articles/{sample[0]}" if sample else None,
        "alerts": alerts,
    }


def main() -> int:
    rows = [check(k) for k in SITES]
    all_alerts = [a for r in rows for a in r["alerts"]]
    lines = [
        "# SEO Autopilot — status",
        "",
        f"Updated: {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "| Site | Published | /articles | Pending | Failed | Service | Integrity | Last run |",
        "|---|---:|---:|---:|---:|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['site']} | {r['published']} | {r['live']} | {r['pending']} | "
            f"{r['failed']} | {r['service']} | {r['integrity']} | {r['last_run'] or '—'} |"
        )
    lines += ["", "## Latest sample URL", ""]
    for r in rows:
        lines.append(f"- {r['site']}: {r['sample'] or '—'}")
    if all_alerts:
        lines += ["", "## Alerts", ""] + [f"- {a}" for a in all_alerts]
    STATUS.write_text("\n".join(lines) + "\n")
    if all_alerts:
        ALERTS.write_text(
            f"# SEO Autopilot alerts\n\n{dt.datetime.now(dt.timezone.utc).isoformat()}\n\n"
            + "\n".join(f"- {a}" for a in all_alerts) + "\n"
        )
        print("\n".join(all_alerts))
        return 1
    if ALERTS.exists():
        ALERTS.unlink()
    print(f"OK — {len(rows)} sites checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
