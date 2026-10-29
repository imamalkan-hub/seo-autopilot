# SEO Autopilot — programmatic city guides for Find Sleep Doctors

Two directory sites are grown automatically with data-driven, local-intent landing
pages ("metro city guides") instead of generic blog posts.

| Site | Live | Focus |
|---|---|---|
| **https://findsleepdoctors.com** | 6 countries (US, UK, CA, AU, NZ, IE) | Sleep **doctors** & sleep centres — credentials, specialties, referral, booking |
| **https://sleepclinicdirectory.com** | USA | Sleep **clinics** — sleep study, CPAP, treatment, insurance |

**The primary site for this repository is [findsleepdoctors.com](https://findsleepdoctors.com).**

The system discovers eligible cities straight from the directory SQLite databases,
asks an LLM to write a guide around the *real* rows for that city, runs a strict
validation gate, publishes to the live site, and repeats — 25 articles per site
per hour.

---

## How it works

```
build_queue()      -> eligible city targets from the DB (city, region, country)
      |
target_data()      -> the exact clinic/doctor rows, addresses, phones, services
      |
build_prompt()     -> one prompt, with the table size taken from the data
      |
generate_one()     -> LLM call -> JSON -> validate_article() gate -> retry once
      |
publish_batch()    -> DB write -> backup -> rsync DB to the live host -> restart
                     the service -> revalidate the statically prerendered /articles
```

### Target discovery

A city qualifies when the directory holds at least `min_city` providers in it
(`MIN_ROWS` additionally guarantees the comparison table has real content):

| Site | `min_city` | `min_region` | Eligible cities |
|---|---|---|---|
| findsleepdoctors.com | 8 | 20 | ~635 city groups (US/UK/CA/AU/NZ/IE) |
| sleepclinicdirectory.com | 4 | 20 | ~460 city groups (US) |

Region/state hubs use `min_region`.

### Titles and focus keywords

City guides are region-qualified so that same-named cities never collide —
`Vancouver, British Columbia` vs `Vancouver, Washington`, `Greenville, North
Carolina` vs `Greenville, South Carolina`. When a city and its region share a
name (`New York`, `Dublin`), the city is rendered as `New York City` so the guide
does not fight the region hub's own page for the same query.

---

## Quality gate

Every article must pass all of these before it is published. Anything that fails
is retried **once** with an explicit corrective prompt, then parked as `failed`.

| Check | Threshold |
|---|---|
| Body length | 700–2500 words (retry prompt asks for ≥850, target 1000–1200) |
| Quick answer | present in the first block |
| H2 sections | ≥ 5 |
| FAQs | exactly 6 + valid `FAQPage` JSON-LD |
| Meta title / description | ≤ 60 / ≤ 160 characters |
| Internal links | ≥ 3, and every one must return HTTP 200 |
| Duplicate slug / title / focus keyword | 0 |
| Banned filler words | `delve`, `unlock`, `landscape`, `navigate`, `seamless`, `robust`, `testament`, … |
| Claim words | `top-rated`, `#1`, `guaranteed`, `cure`, `100%` — rejected |

The prompt's requested table size is derived from the number of rows actually
present in the data, so a thin city never gets padded with invented entries.

---

## Layout

```
autopilot.py     site registry, queue builder, DB helpers, slug rules
pipeline.py      prompt building, model calls, validation gate, publishing
run_hourly.py    hourly orchestration (lock + per-site workers)
monitor.py       STATUS.md / ALERTS.md report, exit 1 on alerts
STRATEGY.md      the SEO strategy this implements
```

Runtime state lives outside the repo and is git-ignored: `queue/`, `logs/`,
`generated/`, `backups/`, `drafts/`.

---

## Configuration

Secrets are **not** in the repository. Everything sensitive is read from the
environment:

| Variable | Meaning |
|---|---|
| `SEO_SSH_HOST` | SSH target for the live host, e.g. `deploy@example.com` |
| `SEO_MODEL_CONFIG` | Path to the model config that holds the API key (default `~/.config/opencode/opencode.jsonc`) |
| `PER_SITE` | Articles generated per site per run (default `25`) |

The model API key is never logged, never committed, and is read at runtime from
the local config file. The prerender revalidation token is read from the live
host's `prerender-manifest.json` and is likewise never written to a log.

---

## Running it

```bash
# rebuild the target queue from the current databases
python3 -c "import autopilot; autopilot.build_queue('fsd'); autopilot.build_queue('scd')"

# one hourly run
python3 run_hourly.py

# health report
python3 monitor.py
```

On a server this is wired to systemd:

```ini
# seo-autopilot.timer
[Timer]
OnCalendar=hourly
Persistent=true

# seo-autopilot-monitor.timer
[Timer]
OnCalendar=*:0/15
Persistent=true
```

`Persistent=true` matters: the box is small and gets restarted, and the timer
compensates for any run that was missed.

---

## Publishing

`publish_batch()` writes to the local database, takes a backup, then syncs the
database to the live host, restarts the site service and refreshes the statically
prerendered `/articles` index (plus the static article sitemap on
sleepclinicdirectory.com).

The whole remote sequence is wrapped in `try/finally`, so a failed `rsync` can
never leave the public service down — it is always restarted even when the
transfer fails.

---

## Monitoring

`monitor.py` compares the live `/articles` count against the database and writes
`STATUS.md` (always) and `ALERTS.md` (only when something needs attention). It
exits non-zero when an alert exists, which is what the systemd monitor timer
reports.

---

## Licence

MIT.
