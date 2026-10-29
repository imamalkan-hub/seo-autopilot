# Site-wide internal SEO architecture — v2 (Claude Opus review incorporated)

## 1. What changes vs v1
- Run **clinic duplicate consolidation (C) first**, before any city/state metadata work.
- **Do not write clinic counts into frontmatter.** City/state descriptions come from code at render time using live DB counts.
- Do **not** blanket-rewrite 2,926 city titles. Wave 1 fixes only objectively bad metadata:
  - city titles >70 characters (941 files),
  - all 51 state titles to “Sleep Centers in {State}”,
  - pages with no usable title.
- Freeze the 30-keyword pages and the 8 pages already tuned in the sample pass. GSC is not connected; that is an explicit limitation, so we do not claim a GSC-based freeze beyond those pages.
- Cities with 1 clinic: keep indexed; no body rewrite; shorten overlong titles only; make H1/meta singular-aware. No “compare 1 sleep centers” copy.
- Deterministic duplicate keeper rule + review reassignment + CSV + rollback.
- Full-file lint over every changed file before build; post-deploy checks include redirects/sitemap and both domains.

## 2. Current baseline
- 7,523 clinic rows, 2,926 city content files, 51 state content files, 357 articles.
- Template layer already live: brand-specific clinic meta; state H1 “Sleep centers and clinics”; city H1 “Sleep Clinics & Sleep Labs”; city labs/sleep-apnea sections and two “near me” FAQs; `/states` hub “Sleep centers by state”; state→city→clinic breadcrumbs and nearby/similar blocks.
- 279 clinic slugs end in `-2`/`-3`; only 5 `duplicate_of` values set.
- 2,923 entries in `data/_cityindex_replica.json` vs 2,926 city files.
- 941 city titles >70 chars; 2,656 >60; 1,538 cities have 1 clinic; 2,161 have ≤2.
- 46 state files still say “Sleep Clinics in XX”.

## 3. Execution order (mandatory)
1. Stop `seo-autopilot.timer` and `seo-autopilot-monitor.timer`; confirm `autopilot.lock` is free.
2. Snapshot: git status/tag or tar of `content/`, `data/directory.db`, `lib/`, `app/`; remote release tar; DB checksum.
3. **C — clinic duplicate consolidation**.
4. **Code — live-count metadata + singular-aware city copy**:
   - `cityMeta(city, state, count, guide)` ignores `guide.description`; always uses live count (and singular wording).
   - `stateMeta(name, count, guide)` ignores `guide.description`; uses live count.
   - City H1/meta singular when total = 1.
5. **A — city metadata audit/fix**:
   - Freeze list: 30 keyword URLs + 8 tuned pages.
   - For non-frozen city files with title >70 chars: title `Sleep Centers in {city}, {ST}` (or `Sleep Center in {city}, {ST}` if count = 1).
   - Leave titles ≤70 unchanged.
   - Do not edit descriptions/keywords/body/words; code supplies live descriptions.
   - Report all changes.
6. **B — state metadata**:
   - Normalize 51 state titles to `Sleep Centers in {State}`; leave frozen 5 (already normalized).
   - No description/body edits; code supplies live descriptions.
7. **Full-file lint** over every changed city/state file:
   - YAML valid; title ≤70; description ≤160; body hash and `words` unchanged; no duplicate titles.
8. Build production, deploy with `NEARME_DOMAIN=findsleepdoctors.com`, verify both domains and `/articles` count.
9. **D — QA**:
   - `/states`, all 51 states, 100 city pages, 100 clinic pages, `/articles`.
   - Exactly one H1; canonical self; JSON-LD parses; internal links 200.
   - Redirected duplicates: 308 → keeper 200; absent from `sitemap-clinics.xml`; not linked from city/state pages.
   - Sitemap lastmod not bumped for every city.
10. Restart both timers.

## 4. Clinic duplicate consolidation (C)
- Backup DB with checksum.
- Normalize address (suite/ste/#, St/Street, punctuation, case).
- Exact key: `name | address | phone_digits | city | state`.
- Keeper rule (deterministic): most approved reviews → has website → most complete fields (address, phone, services, lat/lng) → lowest id.
- Reassign approved reviews, `clinic_maps`, `clinic_npi` from duplicate to keeper before setting `duplicate_of`.
- Never set keeper to a duplicate; no chains. If a group has no clear keeper, skip and report.
- If the duplicate row is the URL already ranking/indexed, keep that row instead; record it.
- Write `duplicate-map.csv` with keeper/duplicate/reason; reversible with `UPDATE ... SET duplicate_of=NULL WHERE id IN (...)`.
- Report before/after counts, groups, integrity, sitemap exclusion.

## 5. City/state policy
- **1-clinic cities:** keep indexed, no body rewrite, no multi-clinic claims; singular H1/description; title shortened only if >70.
- **2-clinic cities:** plural wording; no body rewrite.
- **All cities:** preserve existing unique body; no template body injection; no new pages; no URL changes.
- **State pages:** 51 normalized titles; no body rewrite; preserve existing guides.
- **Freeze list:** the 30 keyword URLs from the operator plus the 8 pages already tuned; do not change their titles/descriptions in this wave.
- GSC is unavailable; no claim of traffic-based freeze. Wave 1 is limited to objective metadata length/normalization; wave 2 can use GSC later.

## 6. Internal linking / orphan audit
- Every non-duplicate clinic must be reachable from its city page; every city from its state page; every state from `/states`; articles→cities links audited.
- Report orphans; do not create pages.
- Fix only broken/missing links with data-driven anchors; no new generic blocks.

## 7. Rollback
- Local: `content.tar.gz`, `directory.db` + checksum, `lib/`/`app/` tar, git status snapshot.
- Remote: tar of `/opt/sleep-directory` before deploy.
- Rollback: stop service, restore `.next`, `data/`, `content/`, restart; DB restore from backup; `duplicate_of` reset from CSV.
- One-command rollback script documented.

## 8. QA gates
- Full-file lint over all 992 changed files (56 states + 941 city title fixes; exact count may vary).
- Title ≤70 including suffix; description ≤160; no duplicate titles in changed set.
- Body hash/words unchanged.
- Build passes; deploy verifies both domains 200.
- 100% sampled internal links 200; redirects 308→200; sitemap excludes duplicates.
- No mass `lastmod` bump.

## 9. Agent / writer rules
- A: only `content/cities/**`; B: only `content/states/**`; C: only DB.
- No agent builds or deploys; main process only.
- One writer per area; reports to `work/SITE-WIDE/`.
- No credentials/private data in prompts; public site/DB data only.

## 10. Requested final review
Claude Opus: approve this v2 or list only concrete blockers. State `APPROVED` or `CHANGES REQUIRED` on the first line.
