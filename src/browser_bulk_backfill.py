import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

from db import connect, column_set
from notifier import send_push
from push_rules import ensure_push_rules, load_enabled_rules, match_rule

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
push_rules = []
if push_secret:
    ensure_push_rules(conn)
    push_rules = load_enabled_rules(conn)

if 'hke_notified_at' not in column_set(conn, 'aircraft_registry_cache'):
    cur.execute("ALTER TABLE aircraft_registry_cache ADD COLUMN hke_notified_at VARCHAR(40)")
    conn.commit()

# push 失敗重試計數（per JST 日，封頂 HKE_PUSH_MAX_RETRY 次），
# 防止「push 送到但 response 失敗」嘅情況無限重複轟炸
if 'hke_push_failed_at' not in column_set(conn, 'aircraft_registry_cache'):
    cur.execute("ALTER TABLE aircraft_registry_cache ADD COLUMN hke_push_failed_at VARCHAR(40)")
    cur.execute("ALTER TABLE aircraft_registry_cache ADD COLUMN hke_push_fail_count INT NOT NULL DEFAULT 0")
    conn.commit()

HKE_PUSH_MAX_RETRY = 3

# snapshots 表：per-(icao, callsign) 嘅 route 史，俾 build_passes 揾返 per-pass route
cur.execute('''
    CREATE TABLE IF NOT EXISTS aircraft_route_snapshots (
      snapshot_id    INT AUTO_INCREMENT PRIMARY KEY,
      icao           VARCHAR(16) NOT NULL,
      flight         VARCHAR(32) NOT NULL,
      from_airport   VARCHAR(64),
      to_airport     VARCHAR(64),
      observed_at    VARCHAR(40) NOT NULL,
      KEY idx_snap_icao_flight (icao, flight, observed_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
''')
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
# 連續 error（多數係接收機頁面 goto timeout）去到上限就提早收工，
# 唔好成個 run 逐架機白等 15 秒 timeout 拖成粒鐘
MAX_CONSECUTIVE_ERRORS = 5
consecutive_errors = 0
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
            # goto timeout 會拋 exception，page 一定要喺 finally 閂返，
            # 否則每次 error 漏一個 renderer process，堆落去會食爆 RAM
            search_page = None
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
            except Exception as e:
                log_line({'event': 'fr24_search_error', 'icao': hex, 'error': str(e)})
            finally:
                if search_page is not None:
                    try:
                        search_page.close()
                    except Exception:
                        pass
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
                fr24_page = None
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
                except Exception as e:
                    log_line({'event': 'operator_lookup_error', 'icao': hex, 'registration': reg, 'error': str(e)})
                finally:
                    if fr24_page is not None:
                        try:
                            fr24_page.close()
                        except Exception:
                            pass

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

                # 如果有 from/to + ADS-B callsign，記低一條 (icao, flight) → route snapshot
                if (from_airport or to_airport):
                    cur.execute(
                        "SELECT flight FROM sightings_raw WHERE icao = %s AND COALESCE(flight, '') <> '' ORDER BY seen_at DESC LIMIT 1",
                        (hex,),
                    )
                    snap_cs_row = cur.fetchone()
                    snap_callsign = (snap_cs_row[0] or '').strip() if snap_cs_row else ''
                    if snap_callsign:
                        cur.execute(
                            "INSERT INTO aircraft_route_snapshots (icao, flight, from_airport, to_airport, observed_at) VALUES (%s, %s, %s, %s, %s)",
                            (hex, snap_callsign, from_airport, to_airport, now_iso),
                        )

                if push_secret and push_rules and reg and from_airport and to_airport:
                    # Push 條件：最近一條 sightings_raw 嘅 callsign 中咗某條 enabled rule 嘅前綴
                    # （即係廣播確認），唔再用 operator path / fr24_id 補位（兩者都會出 hex-like string）。
                    cur.execute(
                        "SELECT flight FROM sightings_raw WHERE icao = %s AND COALESCE(flight, '') <> '' ORDER BY seen_at DESC LIMIT 1",
                        (hex,),
                    )
                    cs_row = cur.fetchone()
                    callsign = cs_row[0].strip().upper() if cs_row and cs_row[0] else None
                    # backfill 已有齊 enrichment local vars，直接砌 fields（callsign / icao /
                    # registration / type / route / country 全部 match 得到）
                    fields = {'callsign': callsign, 'icao': hex, 'registration': reg,
                              'type': aircraft_type, 'from': from_airport, 'to': to_airport,
                              'country': country if country != 'n/a' else None}
                    matched_label = match_rule(fields, push_rules)
                    if not matched_label:
                        # callsign 仲未廣播中 rule，唔 push；下個 cycle ingest 補到 callsign 自己會 trigger
                        log_line({'event': 'push_hke_wait_callsign', 'icao': hex, 'registration': reg, 'operator': operator, 'last_callsign': callsign})
                    else:
                        today_jst = datetime.now(JST).strftime('%Y-%m-%d')
                        cur.execute("SELECT hke_notified_at, hke_push_failed_at, hke_push_fail_count FROM aircraft_registry_cache WHERE icao = %s", (hex,))
                        notify_row = cur.fetchone()
                        already_notified_today = False
                        last_notified_at = notify_row[0] if notify_row and notify_row[0] else None
                        if last_notified_at:
                            try:
                                last_notified_jst = datetime.fromisoformat(last_notified_at).astimezone(JST).strftime('%Y-%m-%d')
                                already_notified_today = (last_notified_jst == today_jst)
                            except Exception:
                                already_notified_today = False
                        # 失敗計數淨計今日 JST，舊嘅當 0（跨日自動 reset）
                        fail_count_today = 0
                        if notify_row and notify_row[1] and notify_row[2]:
                            try:
                                failed_jst = datetime.fromisoformat(notify_row[1]).astimezone(JST).strftime('%Y-%m-%d')
                                if failed_jst == today_jst:
                                    fail_count_today = notify_row[2]
                            except Exception:
                                fail_count_today = 0
                        if not already_notified_today and fail_count_today < HKE_PUSH_MAX_RETRY:
                            msg = f"{matched_label} confirm: {callsign} | {reg} | {from_airport}>{to_airport}\nhttps://www.flightradar24.com/data/aircraft/{reg.lower()}"
                            status = send_push(push_secret, msg)
                            # 送到（2xx）先寫 hke_notified_at，否則重試（封頂每日 HKE_PUSH_MAX_RETRY 次，同 ingest.py 一致）
                            if status and 200 <= status < 300:
                                cur.execute("UPDATE aircraft_registry_cache SET hke_notified_at = %s, hke_push_failed_at = NULL, hke_push_fail_count = 0 WHERE icao = %s", (now_iso, hex))
                                log_line({'event': 'push_hke_confirm', 'icao': hex, 'flight_code': callsign, 'registration': reg, 'from_airport': from_airport, 'to_airport': to_airport, 'status': status, 'last_notified_at': last_notified_at, 'today_jst': today_jst})
                            else:
                                cur.execute("UPDATE aircraft_registry_cache SET hke_push_failed_at = %s, hke_push_fail_count = %s WHERE icao = %s", (now_iso, fail_count_today + 1, hex))
                                log_line({'event': 'push_hke_failed', 'icao': hex, 'flight_code': callsign, 'registration': reg, 'status': status, 'attempt': fail_count_today + 1, 'max_retry': HKE_PUSH_MAX_RETRY})
                        elif already_notified_today:
                            log_line({'event': 'push_hke_skipped_already_notified', 'icao': hex, 'flight_code': callsign, 'registration': reg, 'last_notified_at': last_notified_at, 'today_jst': today_jst})

                conn.commit()
                updated += 1
                log_line({'event': 'updated', 'icao': hex, 'registration': reg, 'country': country, 'aircraft_type': aircraft_type or None, 'operator': operator, 'fr24_id': fr24_id, 'from_airport': from_airport, 'to_airport': to_airport, 'live_flight': live_flight})
            else:
                log_line({'event': 'skip', 'icao': hex, 'reason': 'n/a'})
            consecutive_errors = 0
        except Exception as e:
            errors += 1
            consecutive_errors += 1
            log_line({'event': 'error', 'icao': hex, 'error': str(e)})
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                # 接收機頁面好可能成個唔響應，剩低嘅留返下個 cycle（180 秒後）再試
                log_line({'event': 'abort_consecutive_errors', 'consecutive': consecutive_errors, 'remaining_hexes': len(hexes) - checked})
                break
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
