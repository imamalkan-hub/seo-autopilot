from __future__ import annotations

import concurrent.futures, difflib, json, math, os, re, shutil, sqlite3, subprocess, time
import urllib.request
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from autopilot import (
    BACKUP_DIR, LOG_DIR, OFM_URL, ROOT, SITES, SSH, UA, YUXOR_URL, city_slugify, existing_slugs,
    load_api_key, load_queue, load_yuxor_key, log_event, now, open_db, save_queue, slugify,
    state_names,
)

BANNED = [
    "delve", "unlock", "landscape", "navigate", "seamless", "robust",
    "testament", "in today's world", "it's important to note", "when it comes to",
]

# Article generators run against the yuxor lane, which is queued by the local
# proxy (8788). Upstream allows 5 simultaneous streams and the operator's own
# sessions take part of that, so keep the generators below the cap and let the
# proxy's queue absorb the rest.
GEN_WORKERS = int(os.environ.get("GEN_WORKERS", "4"))
BAD_CLAIMS = re.compile(r"\b(top-rated|#1|guaranteed|guarantee|cure|100%)\b", re.I)


def haversine(a, b):
    lat1, lon1 = a
    lat2, lon2 = b
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _links_for(site_key, con, candidates):
    out = []
    for s in candidates:
        row = con.execute("SELECT slug FROM articles WHERE slug=? AND published=1", (s,)).fetchone()
        if row:
            out.append(f"{SITES[site_key]['domain']}/articles/{s}")
    return out[:4]


def target_data(site_key: str, target: dict) -> dict:
    site = SITES[site_key]
    con = open_db(site)
    domain = site["domain"]
    data = {
        "site": site["site_name"], "domain": domain, "type": target["type"],
        "target": target, "sources": site["sources"], "last_updated": "2026-10-26",
        "byline": site["byline"],
    }

    if site_key == "scd":
        if target["type"] == "state":
            cities = []
            for r in con.execute(
                """SELECT city, state, COUNT(*) n FROM clinics
                   WHERE duplicate_of IS NULL AND state=?
                   GROUP BY city, state ORDER BY n DESC LIMIT 15""", (target["state"],)
            ):
                cities.append({
                    "city": r["city"], "count": r["n"],
                    "url": f"{domain}/states/{target['state_slug']}/{city_slugify(r['city'])}",
                })
            clinics = []
            for r in con.execute(
                """SELECT slug,name,address_line,city,state,zip,phone,services,credentials
                   FROM clinics WHERE duplicate_of IS NULL AND state=?
                   ORDER BY featured DESC, length(description) DESC, name LIMIT 10""",
                (target["state"],)
            ):
                clinics.append(_clinic_row(r, domain))
            data.update({
                "state_name": target["state_name"], "state_url": f"{domain}{site['region_url'].format(state_slug=target['state_slug'])}",
                "clinic_count": target["count"], "cities": cities, "clinics": clinics,
                "article_links": _links_for(site_key, con, [
                    "sleep-study", "home-sleep-study", "how-to-choose-a-sleep-clinic",
                    "sleep-apnea-treatment-options", "does-insurance-cover-sleep-studies", "sleep-clinic",
                ]),
            })
        else:
            clinics = []
            for r in con.execute(
                """SELECT slug,name,address_line,city,state,zip,phone,services,credentials
                   FROM clinics WHERE duplicate_of IS NULL AND city=? AND state=?
                   ORDER BY featured DESC, length(description) DESC, name LIMIT 10""",
                (target["city"], target["state"])
            ):
                clinics.append(_clinic_row(r, domain))
            city_url = f"{domain}{site['city_url'].format(state_slug=target['state_slug'], city_slug=target['city_slug'])}"
            # nearby cities by centroid, same state
            rows = con.execute(
                """SELECT city,state,AVG(lat) lat,AVG(lng) lng,COUNT(*) n FROM clinics
                   WHERE duplicate_of IS NULL AND state=? AND city<>? AND lat IS NOT NULL
                   GROUP BY city,state HAVING n>=5""", (target["state"], target["city"])
            ).fetchall()
            tc = con.execute(
                "SELECT AVG(lat) lat, AVG(lng) lng FROM clinics WHERE city=? AND state=? AND lat IS NOT NULL",
                (target["city"], target["state"])
            ).fetchone()
            nearby = []
            if tc and tc["lat"]:
                for r in rows:
                    d = haversine((tc["lat"], tc["lng"]), (r["lat"], r["lng"]))
                    if d <= 80:
                        nearby.append({
                            "city": r["city"], "distance_miles": round(d),
                            "url": f"{domain}/states/{target['state_slug']}/{city_slugify(r['city'])}",
                        })
                nearby.sort(key=lambda x: x["distance_miles"])
            data.update({
                "city": target["city"], "state": target["state"], "state_name": target["state_name"],
                "city_url": city_url, "state_url": f"{domain}/states/{target['state_slug']}",
                "clinic_count": target["count"], "clinics": clinics, "nearby": nearby[:4],
                "article_links": _links_for(site_key, con, [
                    "sleep-study", "home-sleep-study", "how-to-choose-a-sleep-clinic",
                    "sleep-apnea-treatment-options", "does-insurance-cover-sleep-studies", "sleep-clinic",
                ]),
            })
    else:
        # FSD
        if target["type"] == "region":
            reg = con.execute(
                "SELECT id,name,slug FROM regions WHERE slug=? AND country_code=?",
                (target["region_slug"], target["country"])
            ).fetchone()
            if not reg:
                raise RuntimeError(f"region not found: {target}")
            cities = []
            for r in con.execute(
                """SELECT ci.name city_name, ci.slug city_slug, COUNT(*) n
                   FROM doctors d JOIN cities ci ON ci.id=d.city_id
                   WHERE d.region_id=? AND d.country_code=?
                   GROUP BY d.city_id ORDER BY n DESC LIMIT 15""", (reg["id"], target["country"])
            ):
                cities.append({
                    "city": r["city_name"], "count": r["n"],
                    "url": f"{domain}/{target['country']}/{reg['slug']}/{r['city_slug']}",
                })
            doctors = _doctor_rows(con, domain, "d.region_id=? AND d.country_code=?", (reg["id"], target["country"]))
            data.update({
                "country": target["country"], "region_name": reg["name"], "region_slug": reg["slug"],
                "region_url": f"{domain}{site['region_url'].format(country=target['country'], region_slug=reg['slug'])}",
                "doctor_count": target["count"], "cities": cities, "doctors": doctors,
                "article_links": _links_for(site_key, con, [
                    "sleep-doctor-near-me", "how-to-choose-a-sleep-clinic", "sleep-study",
                    "home-sleep-study", "does-insurance-cover-sleep-studies",
                ]),
            })
        else:
            ci = con.execute(
                """SELECT ci.id,ci.name,ci.slug,ci.lat,ci.lng,rg.name region_name,rg.slug region_slug
                   FROM cities ci JOIN regions rg ON rg.id=ci.region_id
                   WHERE ci.slug=? AND rg.slug=? AND rg.country_code=?""",
                (target["city_slug"], target["region_slug"], target["country"])
            ).fetchone()
            if not ci:
                raise RuntimeError(f"city not found: {target}")
            doctors = _doctor_rows(con, domain, "d.city_id=?", (ci["id"],))
            city_url = f"{domain}/{target['country']}/{ci['region_slug']}/{ci['slug']}"
            nearby = []
            if ci["lat"] is not None:
                for r in con.execute(
                    """SELECT ci.name city_name,ci.slug city_slug,ci.lat,ci.lng,rg.slug region_slug,COUNT(*) n
                       FROM doctors d JOIN cities ci ON ci.id=d.city_id JOIN regions rg ON rg.id=ci.region_id
                       WHERE ci.id<>? AND d.country_code=? AND ci.lat IS NOT NULL AND ci.lng IS NOT NULL
                       GROUP BY d.city_id HAVING n>=5""",
                    (ci["id"], target["country"])
                ):
                    d = haversine((ci["lat"], ci["lng"]), (r["lat"], r["lng"]))
                    if d <= 80:
                        nearby.append({
                            "city": r["city_name"], "distance_miles": round(d),
                            "url": f"{domain}/{target['country']}/{r['region_slug']}/{r['city_slug']}",
                        })
                nearby.sort(key=lambda x: x["distance_miles"])
            data.update({
                "country": target["country"], "region_name": ci["region_name"], "region_slug": ci["region_slug"],
                "city": ci["name"], "city_slug": ci["slug"], "city_url": city_url,
                "region_url": f"{domain}/{target['country']}/{ci['region_slug']}",
                "doctor_count": target["count"], "doctors": doctors, "nearby": nearby[:4],
                "article_links": _links_for(site_key, con, [
                    "sleep-doctor-near-me", "how-to-choose-a-sleep-clinic", "sleep-study",
                    "home-sleep-study", "does-insurance-cover-sleep-studies",
                ]),
            })
    con.close()
    return data


def _clinic_row(r, domain):
    try:
        services = json.loads(r["services"])[:4]
    except Exception:
        services = []
    return {
        "name": r["name"], "address": r["address_line"], "city": r["city"], "state": r["state"],
        "zip": r["zip"], "phone": r["phone"], "services": services,
        "credentials": json.loads(r["credentials"] or "[]")[:3],
        "url": f"{domain}/clinic/{r['slug']}",
    }


def _doctor_rows(con, domain, where, args):
    out = []
    for r in con.execute(
        f"""SELECT d.slug,d.name,d.credentials,d.specialty,d.clinic,d.address_line,d.phone,
                   d.languages,d.telehealth,d.accepting_patients,ci.name city_name,ci.slug city_slug,
                   rg.name region_name,rg.slug region_slug,d.country_code
            FROM doctors d JOIN cities ci ON ci.id=d.city_id JOIN regions rg ON rg.id=d.region_id
            WHERE {where} ORDER BY d.featured DESC, d.accepting_patients DESC, length(d.name) DESC LIMIT 10""",
        args
    ):
        out.append({
            "name": r["name"], "credentials": r["credentials"], "specialty": r["specialty"],
            "clinic": r["clinic"], "address": r["address_line"], "city": r["city_name"],
            "phone": r["phone"], "languages": r["languages"], "telehealth": r["telehealth"],
            "accepting": r["accepting_patients"],
            "url": f"{domain}/{r['country_code']}/{r['region_slug']}/{r['city_slug']}/{r['slug']}",
        })
    return out


def build_prompt(site_key: str, target: dict, data: dict) -> str:
    site = SITES[site_key]
    typ = target["type"]
    # How many entity rows the DATA actually carries. The table request must
    # match, otherwise the model pads a thin dataset with invented entries.
    n_clinics = len(data.get("clinics") or [])
    n_doctors = len(data.get("doctors") or [])
    if site_key == "scd":
        label = "sleep clinics"
        if typ == "state":
            title_hint = target["title_hint"]
            table = "a table of 10-15 Texas cities with clinic counts and links, plus a table of 8-10 clinics"
            focus = target["focus_keyword"]
        else:
            title_hint = target["title_hint"]
            n = n_clinics
            table = (f"a table of {n} {data.get('city','')} clinics with name, area/ZIP, phone, and listed services "
                     f"(one row per clinic listed in DATA — if DATA has fewer, list exactly those and nothing more)")
            focus = target["focus_keyword"]
        extra = "US spelling. Texas/Medicare context only where supported by the data; do not invent state rules."
    else:
        label = "sleep doctors"
        focus = target["focus_keyword"]
        if typ == "region":
            title_hint = target["title_hint"]
            table = "a table of 10-15 cities with doctor counts and links, plus a table of 8-10 doctors"
        else:
            title_hint = target["title_hint"]
            n = n_doctors
            table = (f"a table of {n} {data.get('city','')} providers with name, credentials, specialty, area, and phone "
                     f"(one row per provider listed in DATA — if DATA has fewer, list exactly those and nothing more)")
        extra = ("Neutral English. The site covers the US, UK, Canada, Australia, New Zealand and Ireland; "
                 "note country differences only when relevant, and do not assume US insurance rules.")

    structure = f"""
Return ONLY valid JSON (no markdown fences) with exactly these keys:
{{"title":"...","slug":"{target['slug']}","excerpt":"...","meta_title":"...","meta_description":"...","focus_keyword":"...","body_html":"...","faqs":[{{"q":"...","a":"..."}}]}}

Write an original, human-sounding {typ} guide for {site['site_name']}. Use only the facts in DATA. Do not invent ratings, wait times, prices, awards, patient reviews, statistics, or medical claims. Do not call any clinic or doctor "best"; do not rank them. This is directory information, not medical advice.

DATA:
{json.dumps(data, ensure_ascii=False)}

Title hint: {title_hint}
Focus keyword: {focus}
Coverage: {label}
Include {table}.
Body 1100-1500 words, hard limits 700-2500. Start body_html with:
<p><strong>Quick answer:</strong> ...</p>
(50-80 words; include the count and what the guide covers.)

Required H2 sections:
- "{label.title()} in {data.get('city') or data.get('state_name') or data.get('region_name')} at a glance" (or the closest natural variant)
- "How to choose a {label[:-1]} in {data.get('city') or data.get('state_name') or data.get('region_name')}"
- "What to expect"
- "Insurance, cost and access" (general; no invented prices; for non-US, adapt to the country)
- "Neighborhoods and access" (only use provided city/ZIP/address facts)
- "Questions to ask before booking"
- "Frequently asked questions" — exactly 6 H3 questions with short answers
- "How we built this guide" — directory data, sources, last updated 2026-10-26, byline "{site['byline']}", and a one-sentence disclaimer

Disclaimer requirement (the guide is REJECTED without it): the "How we built this guide" section MUST end with a sentence containing the exact phrase "not medical advice" (for example: "This directory guide is informational and is not medical advice, and it does not replace a consultation with a qualified clinician."). Do not paraphrase this phrase — write it literally.

Rules:
- Use 3-5 contextual internal links: entity URLs, city/region pages, and 2+ article_links. Absolute URLs only.
- All clinic/doctor facts must match DATA exactly. If a field is missing, omit it.
- No <h1>, <html>, <body>, <script>, or FAQ JSON-LD; the site adds schema.
- BAN these words/phrases: {', '.join(BANNED)}. No fake patient quotes.
- No "best", "top-rated", "#1", "guaranteed", "cure", "100%".
- {extra}
- {"The directory mixes individual physicians with sleep centers/clinics. Do not imply every table row is a physician. Call them 'listed sleep providers and centers' and use neutral wording." if site_key == "fsd" else ""}
- Meta title <=60 chars; meta description <=160 chars; excerpt 1-2 sentences.
"""
    return structure


def _post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    body = json.dumps(payload).encode()
    headers = {**headers, "User-Agent": UA}
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _err_text(e) -> str:
    msg = str(e)
    if hasattr(e, "read"):
        try:
            msg += " " + e.read().decode()[:300]
        except Exception:
            pass
    return msg[:600]


def call_model(prompt: str, site_key: str) -> tuple[str, str]:
    last = None

    # Lane 1: yuxor Claude (api2 OpenAI-compatible). Paid tier of the operator's
    # own key, unaffected by the exhausted free pools. Haiku first — it is the
    # cheapest and the generator only needs a structured article body.
    yuxor_key = load_yuxor_key()
    yuxor_chain = [
        ("claude-haiku-5-5", "yuxor-haiku"),
        ("claude-sonnet-5-5", "yuxor-sonnet"),
        ("claude-opus-5-5", "yuxor-opus"),
    ]
    for model, label in yuxor_chain:
        t0 = time.time()
        try:
            d = _post_json(
                YUXOR_URL,
                {"model": model, "messages": [{"role": "user", "content": prompt}],
                 "max_tokens": 12000, "temperature": 0.6},
                {"Content-Type": "application/json", "Authorization": "Bearer " + yuxor_key},
                timeout=420,
            )
            content = d["choices"][0]["message"].get("content") or ""
            if not content.strip():
                raise RuntimeError("empty content")
            log_event("model_ok", site=site_key, model=label, latency=round(time.time() - t0, 1),
                      usage=d.get("usage"))
            return content, label
        except Exception as e:
            msg = _err_text(e)
            log_event("model_fail", site=site_key, model=label, error=msg)
            last = msg
            continue

    # Lane 2: free pools via the local dsh gateway (often rate-limited).
    key = load_api_key()
    chain = [
        ("deepseek-v4.1-flash-free", "deepseek-free"),
        ("glm-5.3-flash-free", "glm-free"),
        ("reflection/beam-free", "kilo-free"),
    ]
    for model, label in chain:
        t0 = time.time()
        try:
            d = _post_json(
                OFM_URL,
                {"model": model, "messages": [{"role": "user", "content": prompt}],
                 "max_tokens": 12000, "temperature": 0.6, "reasoning_effort": "low"},
                {"Content-Type": "application/json", "Authorization": "Bearer " + key},
                timeout=420,
            )
            content = d["choices"][0]["message"].get("content") or ""
            if not content.strip():
                raise RuntimeError("empty content")
            log_event("model_ok", site=site_key, model=label, latency=round(time.time() - t0, 1),
                      usage=d.get("usage"))
            return content, label
        except Exception as e:
            msg = _err_text(e)
            log_event("model_fail", site=site_key, model=label, error=msg)
            last = msg
            continue
    # Paid fallback: OpenCode paid lane. Public content only; no credentials in prompt.
    try:
        p = subprocess.run(
            ["/root/.opencode/bin/opencode", "run", "-m", "opencode-go/deepseek-v4.1-flash",
             "--format", "json", prompt],
            capture_output=True, text=True, timeout=600,
        )
        if p.returncode == 0 and p.stdout.strip():
            log_event("model_ok", site=site_key, model="opencode-go/deepseek-v4.1-flash", fallback=True)
            return p.stdout, "paid-fallback"
        last = (p.stderr or p.stdout)[:600]
    except Exception as e:
        last = str(e)
    log_event("model_fail", site=site_key, model="paid-fallback", error=str(last)[:600])
    raise RuntimeError("all model lanes failed: " + str(last)[:300])


def parse_json(text: str) -> dict:
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    i = s.find("{")
    if i < 0:
        raise ValueError("no JSON object")
    obj, _ = json.JSONDecoder().raw_decode(s[i:])
    return obj


def _text(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def _claim_words(text: str) -> list[str]:
    """Claim words that are actually asserted.

    "no clinic can guarantee a cure" is a disclaimer, not a claim, and must
    not be rejected. Only flag the term when it is not negated and not part
    of a phrase that already denies it.
    """
    hits = []
    for m in BAD_CLAIMS.finditer(text):
        start = max(0, m.start() - 60)
        before = text[start:m.start()].lower()
        term = m.group(0).lower()
        if any(neg in before for neg in (
            "no ", "not ", "never ", "cannot ", "can't ", "won't ",
            "without ", "does not ", "do not ", "is not ", "are not ",
            "neither ", "nor ", "avoid ", "avoided ", "reject ",
        )):
            continue
        if term in ("cure", "100%") and re.search(
            r"\b(no|not|never|cannot|can't|without|nothing)\b[^.]*$", before
        ):
            continue
        hits.append(term)
    return hits


def _shingles(text: str, n=5):
    w = re.findall(r"[a-z0-9]+", text.lower())
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def validate_article(site_key: str, target: dict, a: dict, con, batch_texts) -> list[str]:
    errs = []
    req = ["title", "slug", "excerpt", "meta_title", "meta_description", "focus_keyword", "body_html", "faqs"]
    for k in req:
        if not a.get(k):
            errs.append(f"missing {k}")
    if errs:
        return errs
    if a["slug"] != target["slug"]:
        errs.append("slug mismatch")
    if len(a["meta_title"]) > 60:
        errs.append("meta_title >60")
    if len(a["meta_description"]) > 160:
        errs.append("meta_description >160")
    body = a["body_html"]
    if "<h1" in body.lower():
        errs.append("h1 in body")
    if not re.search(r"<p><strong>Quick answer:</strong>", body, re.I):
        errs.append("missing quick answer")
    words = len(_text(body).split())
    if not (700 <= words <= 2500):
        errs.append(f"word count {words}")
    if len(a.get("faqs") or []) != 6:
        errs.append("need 6 faqs")
    if body.count("<h2") < 5:
        errs.append("need 5+ h2")
    low = _text(body).lower()
    for b in BANNED:
        if b in low:
            errs.append(f"banned phrase: {b}")
    if _claim_words(_text(body)):
        errs.append("bad claim word")
    if "not medical advice" not in low and "not a substitute" not in low:
        errs.append("missing disclaimer")
    # Internal links must be 200
    links = re.findall(r'href="([^"]+)"', body)
    internal = [x for x in links if x.startswith(SITES[site_key]["domain"])]
    if len(internal) < 3:
        errs.append("need 3+ internal links")
    for u in dict.fromkeys(internal):
        try:
            r = requests.get(u, timeout=12, allow_redirects=True)
            if r.status_code != 200:
                errs.append(f"internal {r.status_code}: {u}")
        except Exception as e:
            errs.append(f"internal error: {u} {e}")
    # Duplicate title/focus in DB
    row = con.execute("SELECT slug FROM articles WHERE slug=? OR lower(title)=lower(?) OR lower(focus_keyword)=lower(?)",
                      (a["slug"], a["title"], a["focus_keyword"])).fetchone()
    if row:
        errs.append(f"duplicate slug/title/focus: {row[0]}")
    # Similarity against existing bodies + batch
    new = _shingles(_text(body))
    corpus = [r[0] for r in con.execute("SELECT body_html FROM articles ORDER BY id DESC LIMIT 220")]
    corpus += batch_texts
    for old in corpus:
        old = _shingles(_text(old))
        if old and new:
            j = len(new & old) / len(new | old)
            if j > 0.35:
                errs.append(f"similar to existing ({j:.2f})")
                break
    return errs


def insert_batch(site_key: str, records: list[dict]) -> None:
    site = SITES[site_key]
    con = open_db(site)
    cols = ["slug", "title", "excerpt", "body_html", "meta_title", "meta_description",
            "focus_keyword", "og_image", "published"]
    for rec in records:
        con.execute(
            f"""INSERT OR IGNORE INTO articles ({','.join(cols)})
                VALUES ({','.join('?' * len(cols))})""",
            [rec.get(c) for c in cols],
        )
    con.commit()
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    if site.get("articles_json"):
        p = site["articles_json"]
        data = json.loads(p.read_text())
        have = {x["slug"] for x in data["articles"]}
        for rec in records:
            if rec["slug"] not in have:
                data["articles"].append({
                    "slug": rec["slug"], "title": rec["title"], "excerpt": rec["excerpt"],
                    "body_html": rec["body_html"], "meta_title": rec["meta_title"],
                    "meta_description": rec["meta_description"], "focus_keyword": rec["focus_keyword"],
                    "og_image": "", "source": "autopilot-2026-10-26", "published": 1,
                })
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    # FSD local record archive
    if site_key == "fsd":
        p = site["repo"] / "work" / "AUTOPILOT" / "articles.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        old = json.loads(p.read_text()) if p.exists() else []
        have = {x["slug"] for x in old}
        for rec in records:
            if rec["slug"] not in have:
                old.append({k: rec.get(k) for k in cols})
        p.write_text(json.dumps(old, ensure_ascii=False, indent=2) + "\n")


def publish_batch(site_key: str, records: list[dict]) -> dict:
    site = SITES[site_key]
    urls = [f"{site['domain']}/articles/{r['slug']}" for r in records]
    con = open_db(site)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    ts = now().replace(":", "").replace("-", "")
    backup = BACKUP_DIR / f"{site_key}-{ts}.db"
    shutil.copy2(site["db"], backup)
    # Keep the four newest backups per site; the DB is ~19 MB each.
    for old in sorted(BACKUP_DIR.glob(f"{site_key}-*.db"), key=lambda p: p.stat().st_mtime)[:-4]:
        try:
            old.unlink()
        except OSError:
            pass
    # stop, rsync, start — always bring the service back up, even if the
    # transfer fails, so a network blip cannot leave the site down (502).
    subprocess.run(["ssh", SSH, f"systemctl stop {site['service']}"], check=True, timeout=60)
    try:
        subprocess.run(["rsync", "-az", str(site["db"]), f"{SSH}:{site['remote_db']}"], check=True, timeout=120)
    finally:
        subprocess.run(["ssh", SSH, f"rm -f {site['remote_db']}-wal {site['remote_db']}-shm; systemctl start {site['service']}"], check=True, timeout=60)
    time.sleep(3)
    # Refresh statically prerendered listing pages after the DB sync. Both
    # sites bake /articles at build time; without this the newest batch is
    # live but missing from the index. SCD also refreshes its static sitemap.
    try:
        manifest = f"{site['remote_repo']}/.next/prerender-manifest.json"
        remote_cmd = (
            "python3 -c \"import json;"
            f"print(json.load(open('{manifest}'))['preview']['previewModeId'])\""
        )
        tok = subprocess.check_output(["ssh", SSH, remote_cmd], text=True, timeout=30).strip()
        paths = ["/articles"] + (["/sitemap-articles.xml"] if site["static_articles"] else [])
        for path in paths:
            subprocess.run(["curl", "-s", "-o", "/dev/null", "-H", f"x-prerender-revalidate: {tok}",
                            site["domain"] + path], check=True, timeout=60)
    except Exception as e:
        log_event("revalidate_fail", site=site_key, error=str(e)[:300])
    # verify counts and URLs
    con = open_db(site)
    pub = con.execute("SELECT COUNT(*) FROM articles WHERE published=1").fetchone()[0]
    con.close()
    bad = []
    for u in urls:
        try:
            r = requests.get(u, timeout=20, allow_redirects=True)
            if r.status_code != 200:
                bad.append((u, r.status_code))
        except Exception as e:
            bad.append((u, str(e)))
    listing = requests.get(site["domain"] + "/articles", timeout=30).text
    listed = sum(1 for r in records if r["slug"] in listing)
    # IndexNow
    try:
        subprocess.run(["node", site["indexnow"], *urls], cwd=str(site["repo"]),
                       check=False, timeout=120, capture_output=True, text=True)
    except Exception:
        pass
    log_event("publish", site=site_key, count=len(records), published=pub, bad=len(bad),
              listed=listed, backup=str(backup))
    if bad:
        log_event("publish_error", site=site_key, bad=bad[:5])
    return {"published": pub, "bad": bad, "listed": listed, "backup": str(backup)}


def _record_for(site_key: str, target: dict, a: dict) -> dict:
    faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}}
        for f in a["faqs"]
    ]}
    body = a["body_html"].strip()
    body += '\n<script type="application/ld+json">' + json.dumps(faq, ensure_ascii=False) + "</script>"
    return {
        "slug": a["slug"], "title": a["title"], "excerpt": a["excerpt"],
        "body_html": body, "meta_title": a["meta_title"], "meta_description": a["meta_description"],
        "focus_keyword": a["focus_keyword"], "og_image": "", "published": 1,
    }


def generate_one(site_key: str, target: dict, batch_texts: list[str]) -> dict:
    data = target_data(site_key, target)
    prompt = build_prompt(site_key, target, data)
    last_err = None
    for attempt in range(2):
        text, model = call_model(prompt, site_key)
        try:
            a = parse_json(text)
            con = open_db(SITES[site_key])
            errs = validate_article(site_key, target, a, con, batch_texts)
            con.close()
        except Exception as e:
            errs = [str(e)]
            a = None
        if not errs:
            rec = _record_for(site_key, target, a)
            return {"ok": True, "target": target, "record": rec, "model": model,
                    "words": len(_text(a["body_html"]).split())}
        last_err = errs
        log_event("validation_fail", site=site_key, slug=target["slug"], errors=errs, attempt=attempt + 1)
        # one corrective retry with the error list + explicit thresholds
        prompt += (
            f"\n\nYour previous answer failed validation: {errs}.\n"
            "Return ONE corrected, COMPLETE JSON object with every required key "
            "(title, slug, excerpt, meta_title, meta_description, focus_keyword, body_html, faqs).\n"
            "Hard requirements:\n"
            "- body_html must be at least 850 words (aim for 1000-1200); expand the body, "
            "do not shorten it.\n"
            "- Keep the same slug and title as before.\n"
            "- meta_title <= 60 characters, meta_description <= 160 characters.\n"
            "- No claim words: top-rated, #1, guaranteed, guarantee, cure, 100%.\n"
            "- No banned filler phrases: delve, unlock, landscape, navigate, seamless, robust, "
            "testament, in today's world, it's important to note, when it comes to.\n"
            "- Exactly 6 FAQs, at least 5 H2 sections, and 3+ working internal links."
        )
    return {"ok": False, "target": target, "errors": last_err}


def run_site(site_key: str, count: int, publish: bool = True, slug: str | None = None) -> dict:
    site = SITES[site_key]
    q = load_queue(site)
    if slug:
        pending = [x for x in q if x["slug"] == slug][:1]
    else:
        # Retry failed items too: the model lanes change (yuxor Claude now
        # works), so a previously failed item is worth another attempt. The
        # attempts counter still climbs, so give up on genuinely stuck ones.
        max_attempts = int(os.environ.get("MAX_ATTEMPTS", "6"))
        pending = [x for x in q if x.get("status") in ("pending", "failed")
                   and x.get("attempts", 0) < max_attempts][:count]
    if not pending:
        return {"site": site_key, "generated": 0, "reason": "queue empty"}
    for t in pending:
        t["attempts"] = t.get("attempts", 0) + 1
    results = []
    batch_texts = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=GEN_WORKERS) as ex:
        futs = {ex.submit(generate_one, site_key, t, batch_texts): t for t in pending}
        for f in concurrent.futures.as_completed(futs):
            try:
                r = f.result()
            except Exception as e:
                r = {"ok": False, "target": futs[f], "errors": [str(e)]}
            results.append(r)
            if r.get("ok"):
                batch_texts.append(r["record"]["body_html"])
    good = [r for r in results if r.get("ok")]
    bad = [r for r in results if not r.get("ok")]
    for r in results:
        t = r["target"]
        t["status"] = "published" if r.get("ok") and publish else ("generated" if r.get("ok") else "failed")
        if not r.get("ok"):
            t["error"] = "; ".join(r.get("errors") or [])[:300]
    save_queue(site, q)
    pub = {}
    if good:
        gen = ROOT / "generated"
        gen.mkdir(exist_ok=True)
        for r in good:
            (gen / f"{site_key}-{r['record']['slug']}.json").write_text(
                json.dumps(r["record"], ensure_ascii=False, indent=2))
    if good and publish:
        insert_batch(site_key, [r["record"] for r in good])
        pub = publish_batch(site_key, [r["record"] for r in good])
    summary = {
        "site": site_key, "requested": len(pending), "ok": len(good), "failed": len(bad),
        "words": [r.get("words") for r in good], "publish": pub,
        "errors": [{"slug": r["target"]["slug"], "errors": r.get("errors")} for r in bad][:10],
        "time": now(),
    }
    log_event("run", **summary)
    return summary
