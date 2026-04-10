import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path.home() / "plane-history"
DB = BASE / 'data' / 'plane_history.sqlite3'
LOG = BASE / 'data' / 'browser_bulk_backfill.log'
URL = 'http://192.168.x.x:8080/?icao={}'


def log_line(payload):
    line = json.dumps(payload, ensure_ascii=False)
    print(line, flush=True)
    with LOG.open('a', encoding='utf-8') as f:
        f.write(line + '\n')


conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("select s.icao from sightings_raw s left join aircraft_registry_cache c on c.icao=s.icao where date(s.seen_at, '+9 hours')=date('now', '+9 hours') group by s.icao having coalesce(max(c.registration),'')='' order by max(s.seen_at) desc")
hexes = [r[0].lower() for r in cur.fetchall()]
updated = 0
checked = 0
errors = 0
start = datetime.now(timezone.utc).isoformat()
log_line({'event': 'start', 'count': len(hexes), 'at': start})
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    for hex in hexes:
        checked += 1
        try:
            page.goto(URL.format(hex), wait_until='domcontentloaded', timeout=15000)
            page.wait_for_timeout(1800)
            reg = page.locator('#selected_registration').inner_text().strip()
            country = page.locator('#selected_country').inner_text().strip()
            if reg and reg != 'n/a':
                if country == 'Japan': country = '日本'
                elif country == 'South Korea': country = '韓國'
                elif country == 'China': country = '中國'
                elif country == 'United States': country = '美國'
                cur.execute("INSERT INTO aircraft_registry_cache (icao, registration, country, lookup_source, last_lookup_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(icao) DO UPDATE SET registration=excluded.registration, country=excluded.country, lookup_source=excluded.lookup_source, last_lookup_at=excluded.last_lookup_at", (hex, reg, country if country != 'n/a' else None, 'tar1090-browser-bulk', datetime.now(timezone.utc).isoformat()))
                updated += 1
                log_line({'event': 'updated', 'icao': hex, 'registration': reg, 'country': country})
            else:
                log_line({'event': 'skip', 'icao': hex, 'reason': 'n/a'})
        except Exception as e:
            errors += 1
            log_line({'event': 'error', 'icao': hex, 'error': str(e)})
    browser.close()
conn.commit()
cur.execute("select count(*) from (select s.icao from sightings_raw s left join aircraft_registry_cache c on c.icao=s.icao where date(s.seen_at, '+9 hours')=date('now', '+9 hours') group by s.icao having coalesce(max(c.registration),'')='')")
remaining = cur.fetchone()[0]
conn.close()
log_line({'event': 'done', 'checked': checked, 'updated': updated, 'errors': errors, 'remaining_without_reg': remaining, 'at': datetime.now(timezone.utc).isoformat()})
