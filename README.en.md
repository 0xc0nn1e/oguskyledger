# 尾久 SKYLEDGER · TOKYO

[繁體中文](README.md) · [日本語](README.ja.md) · **English**

A personal project that records and visualises aircraft data picked up by a home receiver in Oku, Tokyo. A home ADS-B receiver pulls aircraft data, history is stored in MySQL, and a Django + DRF + gunicorn backend API + web dashboard visualises it — with a real-time push notification when an HKE flight enters the area.

https://flight.connie.hk/

# Tech stack
- Frontend
 HTML · CSS · vanilla JS · Three.js · Leaflet (all self-hosted/vendored — zero third-party executable JS)
- Backend
Python 3.13 · Django 5 · DRF · gunicorn
- Database
MySQL · PyMySQL
- Receiver
Raspberry Pi · dump1090 / readsb / tar1090
- Deploy
macOS launchd · gunicorn · whitenoise
- Notifications
push.connie.hk (HMAC)


Local ADS-B aircraft-pass recorder (receiver mode) + Django web stack.

## screenshot
*FrontPage*

![Demo screenshot](https://flight.connie.hk/static/img/screenshot_01_resize.png)

*Map*

![Demo screenshot](https://flight.connie.hk/static/img/screenshot_02_resize.png)

*rawdata*

![Demo screenshot](https://flight.connie.hk/static/img/screenshot_03_resize.png)


*stats*

![Demo screenshot](https://flight.connie.hk/static/img/screenshot_04_resize.png)

## Features

- Fetches tar1090 `aircraft.json` every 60 seconds
- Auto-fills `registration / country / aircraft_type` every 3 minutes
- `operator` is filled via two paths
  - first inferred from the flight prefix (e.g. `HKE`)
  - then, for matching aircraft, the real operator is pulled from the FR24 aircraft page
- Web dashboard (SKYLEDGER radar theme), multiple pages:
  - `/`: home — recent contacts + today's operator groups + 4 stat tiles (PEAK ALT links into that highest-altitude aircraft)
  - `/details`: historical aircraft-contact search / filter (operator · type · **category (CAT)** · route · country · altitude) + sort. CAT groups the ADS-B emitter category (planes / helicopters / gliders / balloons / parachutes / ultralights / drones / space vehicles / ground vehicles / obstacles / unclassified). Days older than the oldest raw row still on disk (normally anything outside the 30-day retention window) are rebuilt from `aircraft_passes` automatically, so old days stay searchable — except when `sightings_raw` is empty, where there is no floor to compare against and the fallback doesn't kick in
  - `/stats`: 7-day daily flights, last-24h hourly histogram, **last-30-day weekday × hour heatmap**, TOP 10 (type / operator / from / to / **ICAO**, 7-day + all-DB), peak altitude, busiest hour; **all-time records** (fastest, longest-lingering pass, busiest single day), **year-long calendar heatmap** (daily pass count, ~53 weeks), **heading compass** (last-7-day tracks bucketed into 16 points), **fastest TOP 10**, **ground-speed distribution histogram**; **long-window section**: cumulative unique-ICAO discovery curve, peak-altitude distribution histogram, rare-finds list (ICAOs seen only 1–2 times). The snapshot time is shown at the top of the page. Daily / hourly charts only cover **complete periods** (the histogram counts back 7 days from yesterday; the 24h chart shows 24 complete hours) so a partial period doesn't look like a crash to zero. The old `/discover` URL 301-redirects here
  - `/map`: live map, tar1090 live positions, FR24-style smooth movement, click for a detailed popup (`/api/live` has a 1-second TTL cache so N clients share one fetch)
  - `/aircraft/<hex>/`: single-aircraft history (aggregate stats, daily appearances, **SVG speed·altitude dual-axis profile chart**, pass log with per-pass FROM / TO + **speed range**, planespotters photo, enrichment data-freshness badge) — click an aircraft from `/`, `/details`, `/map`. The old `/aircraft?icao=` URL auto-redirects
  - `/about`: receiver status + uptime + records today + feed health
  - `/api/health`: monitoring endpoint (200 if DB ok, 503 if dead)
- Category emoji sprinkled before the ICAO: 🚁 helicopter (A7), 🪁 glider (B1), 🎈 balloon / UAV (B2/B6), 🚗 ground vehicle (C\*); airliners left blank to avoid noise
- Three-language i18n (Traditional Chinese / Japanese / English): Django gettext + .po + JavaScriptCatalog (`/about/` fully swapped, other pages still on the legacy STRINGS dict during the transition)
- Django built-in auth + custom login template (`/accounts/login/`; old `/login` 301-redirects)
- Any aircraft the receiver can pick up is treated as "received at home"
- Push rules (`/push-rules/`, editable after login): match by callsign / icao / registration / type / route / country prefix; a push fires when a match is enriched (once per aircraft per day, deduped). Default is HKE / Hong Kong Express (`HKE confirm: <flight no> | <reg> | <from>>HKG`)
- **Helicopter-cluster incident alert**: when several helicopters cluster in a small area (usually meaning a nearby incident/disaster — news + police/fire helicopters gather) → a live warning banner + range circle + member highlight on `/map`, plus a push (you get it even without the map open). Thresholds (count / radius / cooldown) are tunable at `/admin/web/siteconfig/`, with `push_log`-based cooldown dedup; on/off lives in the `/push-rules/` "System alerts" section
- **Feed watchdog**: checks `MAX(sightings_raw.seen_at)` every 15 minutes; if there's no update for over an hour, pushes an alert naming which of DB / tar1090 went down
- Writes to MySQL
- Auto-runs via macOS launchd

## Data sources

- tar1090 JSON endpoint: `http://192.168.x.x:8080/data/aircraft.json`
- tar1090 aircraft page: `http://192.168.x.x:8080/?icao=<HEX>`
- Receiver: `192.168.x.x`

## Configuration

```bash
cp src/config.example.json src/config.json
# Edit src/config.json: source.aircraft_json_url (real tar1090 URL),
#                     mysql.password, push.secret,
#                     django.secret_key (generate randomly with the command below),
#                     django.debug, django.allowed_hosts
.venv/bin/python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## Quick start

```bash
# 1. venv + Django
brew install python@3.13
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium

# 2. fake-initial (attach to the existing MySQL tables without re-creating them)
.venv/bin/python manage.py migrate --fake-initial
.venv/bin/python manage.py createsuperuser

# 3. try a pipeline run
.venv/bin/python manage.py ingest_pipeline
.venv/bin/python manage.py browser_bulk_backfill
.venv/bin/python manage.py healthcheck_alert
.venv/bin/python manage.py refresh_stats_cache
```

## Auto-run (launchd · 5 plists)

```bash
cp com.connie.plane-history.{web,ingest,backfill,healthcheck,stats-cache}.plist ~/Library/LaunchAgents/
for L in web ingest backfill healthcheck stats-cache; do
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.connie.plane-history.$L.plist
done
```

| Plist | What | Schedule |
|---|---|---|
| `.web` | gunicorn `:8765` (`0.0.0.0` bind, reachable on LAN) | KeepAlive |
| `.ingest` | `manage.py ingest_pipeline`, 6-step sequential | StartInterval=60 |
| `.backfill` | `manage.py browser_bulk_backfill` | StartInterval=180 |
| `.healthcheck` | `manage.py healthcheck_alert` | StartInterval=900 |
| `.stats-cache` | precomputes persistent `/api/stats` + `/api/discover` snapshots | StartInterval=3600 |

The sequence inside `ingest_pipeline`:

1. `manage.py ingest` (subprocess-wraps `src/ingest.py --once`)
2. `manage.py enrich_registry`
3. `manage.py backfill_reg_browser` (fault-tolerant, continues on non-zero rc)
4. `manage.py enrich_operator`
5. `manage.py build_passes`
6. `src/prune_raw.py` (fault-tolerant, continues on non-zero rc): drops `sightings_raw` older than 30 days

After the 6 steps it also runs the helicopter-cluster alert (`query_live` snapshot → detect → cooldown dedup → push), independently of the steps above.

`browser_bulk_backfill.py` fills:
- `registration`
- `country`
- `aircraft_type` (e.g. `A21N`, `B77W`)
- `operator`

Rules:
- `registration / country / aircraft_type` are filled first
- `operator` is pulled from the FR24 aircraft page for matching aircraft
- country is localised to Chinese where possible (e.g. `台灣`, `新加坡`, `加拿大`, `盧森堡`, `馬來西亞`)

## Key management commands

- `manage.py ingest`: fetches tar1090 `aircraft.json` into `sightings_raw`, and pushes to `push.connie.hk` when a callsign matches a broadcast rule (HKE/UO) and the registry already has the enriched registration
- `manage.py ingest_pipeline`: the 6-step sequence (listed above) + the helicopter-cluster push
- `manage.py enrich_registry`: prefix/country fallback enrichment
- `manage.py backfill_reg_browser`: browser-based REG backfill (quick source)
- `manage.py browser_bulk_backfill`: Playwright bulk backfill — sweeps ICAOs missing `registration / country / aircraft_type / operator` and writes them back; after filling, if it's HKE / Hong Kong Express and the callsign was broadcast, sends an `HKE confirm` push (once a day)
- `manage.py enrich_operator`: fills operator / operator_country by flight prefix (won't overwrite a browser/FR24-filled operator with a blank)
- `manage.py build_passes`: aggregates passes on a 20-minute gap; also recovers per-pass FROM / TO from `aircraft_route_snapshots`
- `manage.py healthcheck_alert`: feed watchdog — alerts after over an hour with no update and names DB vs tar1090
- `manage.py refresh_stats_cache`: precomputes the persistent JSON snapshot for `/api/stats` and `/api/discover` and writes it atomically to `data/stats-cache.json` (the previous file survives a failed run)

Transitional: the management commands are all thin wrappers (`tracking/services/runner.py` → `subprocess.run`) running the old `src/*.py` logic. A second phase will gradually refactor that into `tracking/services/` + `enrichment/services/` as imports.

The old `src/*.py` stays in the working tree as a rollback safety net. After 14 stable days it can be archived into `src/_archived/`.

## Logs / DB

- `data/django-{web,ingest,backfill,healthcheck,stats-cache}.{log,err}`: stdout / stderr for each of the 5 launchd jobs
- `data/ingest.log` / `data/browser_bulk_backfill.log`: detailed logs written directly by the old scripts
- `data/.healthcheck_state.json`: the feed watchdog's dedup state (last_alert_at + last_alerted)
- `data/stats-cache.json`: the hourly statistics snapshot behind `/api/stats` + `/api/discover` (written by `refresh_stats_cache`, read-only for web requests)
- MySQL: `127.0.0.1:3306`, DB `plane_history` (connection info in `src/config.json`)

## Web UI

`web.plist` starts gunicorn on `:8765` (`0.0.0.0` bind, reachable on LAN). Open `http://127.0.0.1:8765/` or on LAN `http://192.168.x.x:8765/`.

Pages: `/` (home), `/details` (search / filter / sort), `/stats` (stats + long-window discovery), `/map` (live map), `/aircraft/<hex>/` (single-aircraft history), `/about` (about / system health), `/admin/` (Django admin, read-only tracking / editable registry cache). Three-language switch (Traditional Chinese / Japanese / English).

JSON API:
- `/api/stats`: hourly statistics snapshot (7-day / 24h histogram, heatmap, top 10, records, calendar, compass, speed distribution, peak alt, busiest hour)
- `/api/discover`: discovery curve, rare finds, altitude distribution and all-DB top 10 ICAO from the same hourly snapshot (the `/stats` page fetches this alongside `/api/stats`)
- Both **only read** `data/stats-cache.json` — no slow SQL inside a request. If the snapshot is missing or its version doesn't match, they return 503 `stats_cache_unavailable`; on success they carry an `X-Stats-Cache-Generated-At` header (the frontend uses it to show the snapshot time)
- `/api/live`: tar1090 live aircraft (for the map, with registry enrichment, 1-second TTL cache)
- `/api/aircraft?icao=`: single-aircraft history (registry + passes aggregate, incl. per-pass FROM / TO)
- `/api/aircraft/track?icao=&from=&to=`: a single pass's sightings_raw track (for the alt + gs profile chart)
- `/api/today?day=&sort=&country=&operator=&type=&cat=&from=&to=`: for the home + details pages — rows + filter dropdown options (`cat` = ADS-B emitter-category group)
- `/api/summary?day=`: home-page operator breakdown + total aircraft count
- `/api/about`: receiver / feed status
- `/api/me`: current user info (used by the nav to show login / account)
- `/api/health`: health check (200 / 503)

## Notes

- `samples` = the number of rows the same ICAO produced in `sightings_raw` today
- `passes` = pass count after aggregating on a 20-minute gap
- `aircraft_route_snapshots` table: each `browser_bulk_backfill` records a `(icao, flight, from, to, observed_at)` from the FR24 from/to plus the ADS-B callsign broadcast at the time. On rebuild, `build_passes` finds the latest snapshot per `(icao, flight)` and fills `aircraft_passes.from_airport / to_airport`, giving per-pass routes instead of every pass sharing the registry's latest one
- Raw retention: `sightings_raw` keeps only 30 days (`src/prune_raw.py`, the pipeline's last step) while `aircraft_passes` is kept forever. So map tracks / profile charts reach back 30 days, but `/details` and the stats still cover older days (days past the retention floor are rebuilt from passes). The floor comes from `MIN(sightings_raw.seen_at)`, so an empty raw table (nothing ingested yet / just purged) means no floor and therefore no fallback
- `/api/live` uses a module-level dict cache (process-local, cleared on restart, no Redis needed)
- `/api/stats` + `/api/discover` use a file-backed snapshot (`data/stats-cache.json`): gunicorn checks the mtime before reloading it, and writes go through `os.replace()`, so a half-written JSON is never read
- REG bulk backfill depends on Python `playwright` + `chromium` (installed inside the venv)
- The frontend Three.js + Leaflet are self-hosted in `static/vendor/` (`base.html` import map points `three` at the vendor copy; Leaflet via `{% static %}`), so auth pages load zero third-party executable JS, and the vendored LICENSE files travel with them (THREE MIT / Leaflet BSD-2). The radar background is now the `base.html` default `radar_bg`, so login / back-office pages have it too. Map tiles (cartocdn) + the planespotters photo stay external (images, non-executable)
- `push.connie.hk` uses HMAC-header auth; the Python notifier uses `openssl + curl` to stay compatible with the existing shell signing flow
- The feed watchdog dedups 6 hours between alerts to avoid spamming; on recovery (feed back) it sends one `✓ recovered` confirm
- `/coverage` and `/api/coverage` were cut (unclear value); the old URLs 301-redirect to `/`
- i18n: `/about/` uses gettext + `.po`, other pages still use the STRINGS dict in `web/_legacy_strings.py` (transitional); the cookie keeps both `django_language` and the legacy `lang`
