import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

from db import connect, column_set
from notifier import send_push

BASE = Path.home() / "plane-history"
LOG = BASE / 'data' / 'browser_bulk_backfill.log'

# 接收機 base URL 由 config.json -> source.aircraft_json_url 推導，
# 唔好硬編真 LAN IP（repo 只放 sample，真值放喺 untracked config.json）
_CFG = json.loads((BASE / 'src' / 'config.json').read_text())
_parts = urlsplit(_CFG['source']['aircraft_json_url'])
URL = f'{_parts.scheme}://{_parts.netloc}/?icao={{}}'

JST = timezone(timedelta(hours=9))


def log_line(payload):
    line = json.dumps(payload, ensure_ascii=False)
    print(line, flush=True)
    with LOG.open('a', encoding='utf-8') as f:
        f.write(line + '\n')


def jst_today_utc_range():
    now_jst = datetime.now(JST)
    start_jst = now_jst.replace(hour=0, minute=0, second=0, microsecond=0)
    end_jst = start_jst + timedelta(days=1)
    return (start_jst.astimezone(timezone.utc).isoformat(),
            end_jst.astimezone(timezone.utc).isoformat())


conn = connect()
cur = conn.cursor()
push_secret = _CFG.get('push', {}).get('secret')

if 'hke_notified_at' not in column_set(conn, 'aircraft_registry_cache'):
    cur.execute("ALTER TABLE aircraft_registry_cache ADD COLUMN hke_notified_at VARCHAR(40)")
    conn.commit()

start_utc, end_utc = jst_today_utc_range()
cur.execute(
    """
    SELECT s.icao
    FROM sightings_raw s
    LEFT JOIN aircraft_registry_cache c ON c.icao = s.icao
    WHERE s.seen_at >= %s AND s.seen_at < %s
    GROUP BY s.icao
    HAVING COALESCE(MAX(c.registration), '') = ''
       OR COALESCE(MAX(c.country), '') = ''
       OR COALESCE(MAX(c.aircraft_type), '') = ''
       OR COALESCE(MAX(c.operator), '') = ''
       OR COALESCE(MAX(c.fr24_id), '') = ''
       OR COALESCE(MAX(c.from_airport), '') = ''
       OR COALESCE(MAX(c.to_airport), '') = ''
    ORDER BY MAX(s.seen_at) DESC
    """,
    (start_utc, end_utc)
)
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
            fr24_id = None
            from_airport = None
            to_airport = None
            live_flight = None
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
            should_fetch_fr24_meta = (not fr24_id) or (not from_airport) or (not to_airport)
            try:
                search_page = browser.new_page()
                search_page.goto(f'https://www.flightradar24.com/v1/search/web/find?query={hex.upper()}&limit=50', wait_until='domcontentloaded', timeout=15000)
                search_page.wait_for_timeout(1200)
                raw = search_page.locator('body').inner_text()
                search_json = json.loads(raw)
                for item in search_json.get('results', []):
                    detail = item.get('detail') or {}
                    if item.get('type') == 'aircraft' and str(detail.get('hex', '')).lower() == hex.lower():
                        fr24_id = item.get('id')
                        break
                search_page.close()
            except Exception as e:
                log_line({'event': 'fr24_search_error', 'icao': hex, 'error': str(e)})
            last_seen_older_than_30m = False
            cur.execute("SELECT MAX(seen_at) FROM sightings_raw WHERE icao = %s", (hex,))
            last_seen_row = cur.fetchone()
            if last_seen_row and last_seen_row[0]:
                try:
                    last_seen_dt = datetime.fromisoformat(last_seen_row[0])
                    last_seen_older_than_30m = (datetime.now(timezone.utc) - last_seen_dt).total_seconds() > 1800
                except Exception:
                    last_seen_older_than_30m = False

            if reg and reg != 'n/a' and (last_seen_older_than_30m or should_fetch_fr24_meta):
                try:
                    fr24_page = browser.new_page()
                    fr24_page.goto(f'https://www.flightradar24.com/data/aircraft/{reg.lower()}', wait_until='domcontentloaded', timeout=15000)
                    fr24_page.wait_for_timeout(1800)
                    op_loc = fr24_page.locator("label:text-is('OPERATOR') + span.details, label:text-is('Operator') + span.details").first
                    if op_loc.count() > 0:
                        value = op_loc.inner_text().strip()
                        if value:
                            operator = value
                    info_text = fr24_page.locator('#cnt-aircraft-info').inner_text() if fr24_page.locator('#cnt-aircraft-info').count() > 0 else fr24_page.locator('body').inner_text()
                    lines = [x.strip() for x in info_text.splitlines() if x.strip()]
                    if not operator:
                        for idx, line in enumerate(lines):
                            if line.upper() == 'OPERATOR' and idx + 1 < len(lines):
                                candidate = lines[idx + 1].strip()
                                if candidate and candidate.upper() != 'OPERATOR':
                                    operator = candidate
                                    break
                    if not from_airport or not to_airport:
                        live_btn = fr24_page.locator("a.btn-playback:has-text('Live')").first
                        if live_btn.count() > 0:
                            row = live_btn.locator("xpath=ancestor::tr[1]")
                            cells = row.locator('td')
                            if cells.count() >= 6:
                                from_airport = cells.nth(3).inner_text().strip()
                                to_airport = cells.nth(4).inner_text().strip()
                                live_flight = cells.nth(5).inner_text().strip()
                                if from_airport == '':
                                    from_airport = None
                                if to_airport == '':
                                    to_airport = None
                                if live_flight == '':
                                    live_flight = None
                    if live_flight:
                        fr24_id = live_flight
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
                now_iso = datetime.now(timezone.utc).isoformat()
                cur.execute(
                    """
                    INSERT INTO aircraft_registry_cache
                      (icao, registration, country, aircraft_type, lookup_source, last_lookup_at,
                       operator, fr24_id, from_airport, to_airport)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      registration   = VALUES(registration),
                      country        = VALUES(country),
                      aircraft_type  = COALESCE(NULLIF(VALUES(aircraft_type), ''), aircraft_registry_cache.aircraft_type),
                      operator       = COALESCE(NULLIF(VALUES(operator), ''), aircraft_registry_cache.operator),
                      fr24_id        = COALESCE(NULLIF(VALUES(fr24_id), ''), aircraft_registry_cache.fr24_id),
                      from_airport   = COALESCE(NULLIF(VALUES(from_airport), ''), aircraft_registry_cache.from_airport),
                      to_airport     = COALESCE(NULLIF(VALUES(to_airport), ''), aircraft_registry_cache.to_airport),
                      lookup_source  = VALUES(lookup_source),
                      last_lookup_at = VALUES(last_lookup_at)
                    """,
                    (hex, reg, country if country != 'n/a' else None, aircraft_type or None,
                     'tar1090-browser-bulk', now_iso, operator, fr24_id, from_airport, to_airport)
                )

                if push_secret and fr24_id and reg and from_airport and to_airport:
                    flight_code = (fr24_id or '').upper()
                    is_uo = flight_code.startswith('UO') or operator == 'Hong Kong Express'
                    if is_uo:
                        today_jst = datetime.now(JST).strftime('%Y-%m-%d')
                        cur.execute("SELECT hke_notified_at FROM aircraft_registry_cache WHERE icao = %s", (hex,))
                        notify_row = cur.fetchone()
                        already_notified_today = False
                        last_notified_at = notify_row[0] if notify_row and notify_row[0] else None
                        if last_notified_at:
                            try:
                                last_notified_jst = datetime.fromisoformat(last_notified_at).astimezone(JST).strftime('%Y-%m-%d')
                                already_notified_today = (last_notified_jst == today_jst)
                            except Exception:
                                already_notified_today = False
                        if not already_notified_today:
                            msg = f"HKE confirm: {flight_code} | {reg} | {from_airport}>{to_airport} \nhttps://www.flightradar24.com/data/flights/{flight_code.lower()}"
                            status = send_push(push_secret, msg)
                            cur.execute("UPDATE aircraft_registry_cache SET hke_notified_at = %s WHERE icao = %s", (now_iso, hex))
                            log_line({'event': 'push_hke_confirm', 'icao': hex, 'flight_code': flight_code, 'registration': reg, 'from_airport': from_airport, 'to_airport': to_airport, 'status': status, 'last_notified_at': last_notified_at, 'today_jst': today_jst})
                        else:
                            log_line({'event': 'push_hke_skipped_already_notified', 'icao': hex, 'flight_code': flight_code, 'registration': reg, 'last_notified_at': last_notified_at, 'today_jst': today_jst})

                conn.commit()
                updated += 1
                log_line({'event': 'updated', 'icao': hex, 'registration': reg, 'country': country, 'aircraft_type': aircraft_type or None, 'operator': operator, 'fr24_id': fr24_id, 'from_airport': from_airport, 'to_airport': to_airport, 'live_flight': live_flight})
            else:
                log_line({'event': 'skip', 'icao': hex, 'reason': 'n/a'})
        except Exception as e:
            errors += 1
            log_line({'event': 'error', 'icao': hex, 'error': str(e)})
    browser.close()
conn.commit()
start_utc, end_utc = jst_today_utc_range()
cur.execute(
    """
    SELECT COUNT(*) FROM (
      SELECT s.icao
      FROM sightings_raw s
      LEFT JOIN aircraft_registry_cache c ON c.icao = s.icao
      WHERE s.seen_at >= %s AND s.seen_at < %s
      GROUP BY s.icao
      HAVING COALESCE(MAX(c.registration), '') = ''
         OR COALESCE(MAX(c.country), '') = ''
         OR COALESCE(MAX(c.aircraft_type), '') = ''
         OR COALESCE(MAX(c.operator), '') = ''
         OR COALESCE(MAX(c.fr24_id), '') = ''
         OR COALESCE(MAX(c.from_airport), '') = ''
         OR COALESCE(MAX(c.to_airport), '') = ''
    ) sub
    """,
    (start_utc, end_utc)
)
remaining = cur.fetchone()[0]
conn.close()
log_line({'event': 'done', 'checked': checked, 'updated': updated, 'errors': errors, 'remaining_without_reg': remaining, 'at': datetime.now(timezone.utc).isoformat()})
