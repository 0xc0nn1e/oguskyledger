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


conn = sqlite3.connect(DB, timeout=30)
cur = conn.cursor()
cur.execute("select s.icao from sightings_raw s left join aircraft_registry_cache c on c.icao=s.icao where date(s.seen_at, '+9 hours')=date('now', '+9 hours') group by s.icao having coalesce(max(c.registration),'')='' or coalesce(max(c.country),'')='' or coalesce(max(c.aircraft_type),'')='' or coalesce(max(c.operator),'')='' order by max(s.seen_at) desc")
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
            aircraft_type = ''
            type_desc = ''
            for selector in ['#selected_type', '#selected_aircraft_type', '#selected_icao_type']:
                loc = page.locator(selector)
                if loc.count() > 0:
                    value = loc.inner_text().strip()
                    if value and value != 'n/a':
                        aircraft_type = value
                        break
            desc_loc = page.locator('#selected_typedesc')
            if desc_loc.count() > 0:
                value = desc_loc.inner_text().strip()
                if value and value != 'n/a':
                    type_desc = value
            if not aircraft_type:
                kv = page.locator('#selected_infoblock')
                if kv.count() > 0:
                    text = kv.inner_text()
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    for idx, line in enumerate(lines):
                        if line == 'Type:' and idx + 1 < len(lines):
                            candidate = lines[idx + 1].strip()
                            if candidate and candidate != 'n/a':
                                aircraft_type = candidate
                        if line == 'Type Desc:' and idx + 1 < len(lines):
                            candidate = lines[idx + 1].strip()
                            if candidate and candidate != 'n/a':
                                type_desc = candidate
            if not aircraft_type:
                for key in ['t', 'icao_type', 'aircraft_type']:
                    value = page.evaluate(f"() => window.selected && window.selected['{key}'] ? String(window.selected['{key}']).trim() : ''")
                    if value and value != 'n/a':
                        aircraft_type = value
                        break
            operator = None
            last_seen_older_than_30m = False
            cur.execute("SELECT MAX(seen_at) FROM sightings_raw WHERE icao = ?", (hex,))
            last_seen_row = cur.fetchone()
            if last_seen_row and last_seen_row[0]:
                try:
                    last_seen_dt = datetime.fromisoformat(last_seen_row[0])
                    last_seen_older_than_30m = (datetime.now(timezone.utc) - last_seen_dt).total_seconds() > 1800
                except Exception:
                    last_seen_older_than_30m = False

            if reg and reg != 'n/a' and last_seen_older_than_30m:
                try:
                    fr24_page = browser.new_page()
                    fr24_page.goto(f'https://www.flightradar24.com/data/aircraft/{reg.lower()}', wait_until='domcontentloaded', timeout=15000)
                    fr24_page.wait_for_timeout(1800)
                    op_loc = fr24_page.locator("label:text-is('OPERATOR') + span.details, label:text-is('Operator') + span.details").first
                    if op_loc.count() > 0:
                        value = op_loc.inner_text().strip()
                        if value:
                            operator = value
                    if not operator:
                        info_text = fr24_page.locator('#cnt-aircraft-info').inner_text() if fr24_page.locator('#cnt-aircraft-info').count() > 0 else fr24_page.locator('body').inner_text()
                        lines = [x.strip() for x in info_text.splitlines() if x.strip()]
                        for idx, line in enumerate(lines):
                            if line.upper() == 'OPERATOR' and idx + 1 < len(lines):
                                candidate = lines[idx + 1].strip()
                                if candidate and candidate.upper() != 'OPERATOR':
                                    operator = candidate
                                    break
                    fr24_page.close()
                except Exception as e:
                    log_line({'event': 'operator_lookup_error', 'icao': hex, 'registration': reg, 'error': str(e)})

            if reg and reg != 'n/a':
                if country == 'Japan': country = '日本'
                elif country == 'South Korea': country = '韓國'
                elif country == 'China': country = '中國'
                elif country == 'United States': country = '美國'
                elif country == 'Hong Kong': country = '香港'
                elif country == 'Taiwan': country = '台灣'
                elif country == 'Singapore': country = '新加坡'
                elif country == 'Canada': country = '加拿大'
                elif country == 'Thailand': country = '泰國'
                elif country == 'Philippines': country = '菲律賓'
                elif country == 'Viet Nam': country = '越南'
                elif country == 'United Arab Emirates': country = '阿聯酋'
                elif country == 'Luxembourg': country = '盧森堡'
                elif country == 'Malaysia': country = '馬來西亞'
                cur.execute("INSERT INTO aircraft_registry_cache (icao, registration, country, aircraft_type, lookup_source, last_lookup_at, operator) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(icao) DO UPDATE SET registration=excluded.registration, country=excluded.country, aircraft_type=COALESCE(NULLIF(excluded.aircraft_type, ''), aircraft_registry_cache.aircraft_type), operator=COALESCE(NULLIF(excluded.operator, ''), aircraft_registry_cache.operator), lookup_source=excluded.lookup_source, last_lookup_at=excluded.last_lookup_at", (hex, reg, country if country != 'n/a' else None, aircraft_type or None, 'tar1090-browser-bulk', datetime.now(timezone.utc).isoformat(), operator))
                conn.commit()
                updated += 1
                log_line({'event': 'updated', 'icao': hex, 'registration': reg, 'country': country, 'aircraft_type': aircraft_type or None, 'operator': operator})
            else:
                log_line({'event': 'skip', 'icao': hex, 'reason': 'n/a'})
        except Exception as e:
            errors += 1
            log_line({'event': 'error', 'icao': hex, 'error': str(e)})
    browser.close()
conn.commit()
cur.execute("select count(*) from (select s.icao from sightings_raw s left join aircraft_registry_cache c on c.icao=s.icao where date(s.seen_at, '+9 hours')=date('now', '+9 hours') group by s.icao having coalesce(max(c.registration),'')='' or coalesce(max(c.country),'')='' or coalesce(max(c.aircraft_type),'')='' or coalesce(max(c.operator),'')='')")
remaining = cur.fetchone()[0]
conn.close()
log_line({'event': 'done', 'checked': checked, 'updated': updated, 'errors': errors, 'remaining_without_reg': remaining, 'at': datetime.now(timezone.utc).isoformat()})
