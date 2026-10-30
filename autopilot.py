#!/usr/bin/env python3
"""SEO Autopilot — programmatic metro city/state guides for two sleep directories.

Commands:
  python3 autopilot.py queue --site scd
  python3 autopilot.py data  --site scd --slug sleep-clinics-houston-tx
  python3 autopilot.py run   --site scd --count 2 --publish
  python3 autopilot.py monitor
"""
from __future__ import annotations

import argparse, concurrent.futures, datetime as dt, difflib, hashlib, json, math
import os, re, shutil, sqlite3, subprocess, sys, time, urllib.request
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path("/root/seo-autopilot")
QUEUE_DIR = ROOT / "queue"
LOG_DIR = ROOT / "logs"
BACKUP_DIR = ROOT / "backups"
for d in (QUEUE_DIR, LOG_DIR, BACKUP_DIR):
    d.mkdir(parents=True, exist_ok=True)

SSH = os.environ.get("SEO_SSH_HOST", "")  # e.g. deploy@host — set via env, never committed
OFM_URL = "http://127.0.0.1:18899/v1/chat/completions"
# yuxor Claude lane goes through the local proxy (8788) rather than straight to
# api.yuxor.tech: the proxy owns the concurrency queue, the 429 backoff/retry
# and the response cache. Upstream caps at 5 simultaneous streams, so the
# autopilot shares them with the operator's own sessions instead of colliding.
YUXOR_URL = "http://127.0.0.1:8788/v1/chat/completions"
CONFIG_PATH = Path(os.environ.get("SEO_MODEL_CONFIG", "/root/.config/opencode/opencode.jsonc"))

# Cloudflare's browser-integrity rule (error 1010) rejects the default
# Python-urllib User-Agent, so every request through the yuxor lane came back
# 403 even though curl and the AI SDK went through. Send a normal UA.
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# Minimum entity rows a city guide must carry so the comparison table is
# real content rather than thin filler. Same order as min_city, so the
# looser city threshold still yields a usable table.
MIN_ROWS = 4

SITES = {
    "scd": {
        "key": "scd",
        "repo": Path("/root/sleep-directory"),
        "db": Path("/root/sleep-directory/data/directory.db"),
        "domain": "https://sleepclinicdirectory.com",
        "service": "sleepdir",
        "remote_db": "/opt/sleep-directory/data/directory.db",
        "remote_repo": "/opt/sleep-directory",
        "entity_table": "clinics",
        "entity_url": "/clinic/{slug}",
        "city_url": "/states/{state_slug}/{city_slug}",
        "region_url": "/states/{state_slug}",
        "min_city": 4,
        "min_region": 20,
        "prefix": "sleep-clinics-",
        "static_articles": True,
        "articles_json": Path("/root/sleep-directory/scripts/content/articles.json"),
        "indexnow": "scripts/indexnow.js",
        "byline": "Sleep Clinic Directory Editorial Team",
        "site_name": "Sleep Clinic Directory",
        "sources": [
            ("American Academy of Sleep Medicine", "https://aasm.org/"),
            ("NHLBI", "https://www.nhlbi.nih.gov/"),
            ("Medicare.gov", "https://www.medicare.gov/"),
        ],
    },
    "fsd": {
        "key": "fsd",
        "repo": Path("/root/sleep-doctor-nearme/site"),
        "db": Path("/root/sleep-doctor-nearme/site/data/directory.db"),
        "domain": "https://findsleepdoctors.com",
        "service": "sleepdir-nearme",
        "remote_db": "/opt/sleep-doctor-nearme/data/directory.db",
        "remote_repo": "/opt/sleep-doctor-nearme",
        "entity_table": "doctors",
        "entity_url": "/{country}/{region_slug}/{city_slug}/{slug}",
        "city_url": "/{country}/{region_slug}/{city_slug}",
        "region_url": "/{country}/{region_slug}",
        "min_city": 8,
        "min_region": 20,
        "prefix": "sleep-doctors-",
        "static_articles": False,
        "articles_json": None,
        "indexnow": "scripts/indexnow.js",
        "byline": "Find Sleep Doctors Editorial Team",
        "site_name": "Find Sleep Doctors",
        "sources": [
            ("American Academy of Sleep Medicine", "https://aasm.org/"),
            ("NHLBI", "https://www.nhlbi.nih.gov/"),
        ],
    },
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(s: str) -> str:
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


def load_api_key() -> str:
    txt = CONFIG_PATH.read_text()
    m = re.search(r'"ofm"\s*:\s*\{.*?"settings"\s*:\s*\{.*?"apiKey"\s*:\s*"([^"]+)"', txt, re.S)
    if not m:
        raise RuntimeError("OFM apiKey not found")
    return m.group(1)


def load_yuxor_key() -> str:
    """Read the yuxor provider key from the opencode config.

    Falls back to the environment so the autopilot can run even if the
    opencode config is being rewritten.
    """
    txt = CONFIG_PATH.read_text()
    m = re.search(r'"yuxor"\s*:\s*\{.*?"settings"\s*:\s*\{.*?"apiKey"\s*:\s*"([^"]+)"', txt, re.S)
    if m:
        return m.group(1)
    env = os.environ.get("YUXOR_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if env:
        return env
    raise RuntimeError("yuxor apiKey not found")


def city_slugify(s: str) -> str:
    s = s.lower().replace("'", "").replace("\u2019", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


def state_names() -> dict[str, str]:
    txt = Path("/root/sleep-directory/lib/states.js").read_text()
    return dict(re.findall(r"([A-Z]{2}): '([^']+)'", txt))


def open_db(site: dict) -> sqlite3.Connection:
    con = sqlite3.connect(site["db"], timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=60000")
    return con


def existing_slugs(site: dict) -> set[str]:
    con = open_db(site)
    rows = con.execute("SELECT slug FROM articles").fetchall()
    con.close()
    return {r[0] for r in rows}


def load_queue(site: dict) -> list[dict]:
    p = QUEUE_DIR / f"{site['key']}.json"
    return json.loads(p.read_text()) if p.exists() else []


def save_queue(site: dict, q: list[dict]) -> None:
    (QUEUE_DIR / f"{site['key']}.json").write_text(json.dumps(q, ensure_ascii=False, indent=2))


def log_event(kind: str, **kw) -> None:
    row = {"time": now(), "kind": kind, **kw}
    with (LOG_DIR / "events.jsonl").open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_queue(site_key: str) -> list[dict]:
    site = SITES[site_key]
    con = open_db(site)
    existing = existing_slugs(site)
    q: list[dict] = []

    if site_key == "scd":
        names = state_names()
        # State hubs first
        for r in con.execute(
            """SELECT state, COUNT(*) n FROM clinics
               WHERE duplicate_of IS NULL AND state <> '' GROUP BY state
               HAVING n >= ? ORDER BY n DESC""", (site["min_region"],)
        ):
            code = r["state"].upper()
            if code not in names:
                continue
            slug = site["prefix"] + slugify(names[code])
            if slug in existing:
                continue
            q.append({
                "id": slug, "site": site_key, "type": "state", "slug": slug,
                "state": code, "state_name": names[code], "state_slug": code.lower(),
                "count": r["n"], "priority": 1, "status": "pending",
                "title_hint": f"Sleep Clinics in {names[code]}: Metro-by-Metro Guide",
                "focus_keyword": f"sleep clinics {names[code].lower()}",
            })
        # Metro cities
        for r in con.execute(
            """SELECT city, state, COUNT(*) n FROM clinics
               WHERE duplicate_of IS NULL AND city <> '' AND state <> ''
               GROUP BY city, state HAVING n >= ? ORDER BY n DESC LIMIT 500""",
            (site["min_city"],)
        ):
            code = r["state"].upper()
            if code not in names:
                continue
            # A guide needs enough rows for a real table; below this the page
            # would be thin content.
            if r["n"] < MIN_ROWS:
                continue
            city_slug = city_slugify(r["city"])
            slug = site["prefix"] + city_slug + "-" + code.lower()
            if slug in existing:
                continue
            q.append({
                "id": slug, "site": site_key, "type": "city", "slug": slug,
                "city": r["city"], "state": code, "state_name": names[code],
                "state_slug": code.lower(), "city_slug": city_slug,
                "count": r["n"], "priority": 2, "status": "pending",
                "title_hint": f"Sleep Clinics in {r['city']}, {code}: How to Choose One",
                "focus_keyword": f"sleep clinics {r['city'].lower()} {code.lower()}",
            })
    else:
        # Region hubs
        for r in con.execute(
            """SELECT d.country_code, d.region_id, rg.name region_name, rg.slug region_slug,
                      COUNT(*) n
               FROM doctors d JOIN regions rg ON rg.id=d.region_id
               GROUP BY d.country_code, d.region_id HAVING n >= ?
               ORDER BY n DESC LIMIT 500""", (site["min_region"],)
        ):
            slug = site["prefix"] + r["region_slug"] + "-" + r["country_code"]
            if slug in existing:
                continue
            name = r["region_name"]
            q.append({
                "id": slug, "site": site_key, "type": "region", "slug": slug,
                "country": r["country_code"], "region_code": r["region_code"] if "region_code" in r.keys() else "",
                "region_name": name, "region_slug": r["region_slug"],
                "count": r["n"], "priority": 1, "status": "pending",
                "title_hint": f"Sleep Doctors in {name}: How to Find a Specialist",
                "focus_keyword": f"sleep doctors {name.lower()}",
            })
        # City guides
        for r in con.execute(
            """SELECT d.country_code, rg.name region_name, rg.slug region_slug,
                      ci.name city_name, ci.slug city_slug, COUNT(*) n
               FROM doctors d JOIN cities ci ON ci.id=d.city_id
               JOIN regions rg ON rg.id=d.region_id
               GROUP BY d.country_code, d.region_id, d.city_id
               HAVING n >= ? ORDER BY n DESC LIMIT 1000""", (site["min_city"],)
        ):
            slug = site["prefix"] + r["city_slug"] + "-" + r["region_slug"] + "-" + r["country_code"]
            if slug in existing:
                continue
            # Region in the title/focus keeps same-named cities apart
            # (Vancouver BC vs WA, Greenville NC vs SC). When the city and
            # region share a name (New York, Dublin), use "<City> City" so
            # the guide does not collide with the region hub's title.
            if r["city_name"].lower() == r["region_name"].lower():
                display_city = f"{r['city_name']} City"
                focus_city = f"{r['city_name'].lower()} city"
            else:
                display_city = f"{r['city_name']}, {r['region_name']}"
                focus_city = f"{r['city_name'].lower()} {r['region_slug']}"
            q.append({
                "id": slug, "site": site_key, "type": "city", "slug": slug,
                "country": r["country_code"], "region_name": r["region_name"],
                "region_slug": r["region_slug"], "city": r["city_name"],
                "city_slug": r["city_slug"], "count": r["n"], "priority": 2,
                "status": "pending",
                "title_hint": f"Sleep Doctors in {display_city}: How to Find the Right Specialist",
                "focus_keyword": f"sleep doctors {focus_city}",
            })

    # Different source rows can map to the same slug (e.g. "Lee's Summit" and
    # "Lees Summit"); keep one target per slug so the batch cannot collide.
    seen: set[str] = set()
    unique: list[dict] = []
    for x in q:
        if x["slug"] in seen:
            continue
        seen.add(x["slug"])
        unique.append(x)

    unique.sort(key=lambda x: (x["priority"], -x["count"]))
    con.close()
    save_queue(site, unique)
    return unique


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["queue", "data", "run", "monitor"])
    ap.add_argument("--site", choices=list(SITES), default="scd")
    ap.add_argument("--slug")
    ap.add_argument("--count", type=int, default=2)
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()
    if args.cmd == "queue":
        q = build_queue(args.site)
        print(f"{args.site}: {len(q)} targets queued")
        for x in q[:5]:
            print(x["priority"], x["slug"], x["count"], x.get("title_hint"))
    elif args.cmd == "data":
        q = load_queue(SITES[args.site])
        t = next((x for x in q if x["slug"] == args.slug), None)
        if not t:
            raise SystemExit("target not found")
        from pipeline import target_data
        print(json.dumps(target_data(args.site, t), ensure_ascii=False, indent=2))
    elif args.cmd == "run":
        from pipeline import run_site
        s = run_site(args.site, args.count, args.publish, args.slug)
        print(json.dumps(s, ensure_ascii=False, indent=2))
    else:
        print("monitor not implemented yet")
