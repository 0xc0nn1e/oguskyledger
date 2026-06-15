import argparse
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from db import connect
from notifier import send_push
from push_rules import ensure_push_rules, load_enabled_rules, match_rule, rules_need_registry

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG = json.loads((BASE_DIR / 'src' / 'config.json').read_text())

RECEIVER_NAME = CONFIG['receiver']['name']
SOURCE_NAME = CONFIG['source']['name']

# HKE push 失敗每日最多重試咁多次（防止「送到但 response 失敗」無限重複轟炸）
HKE_PUSH_MAX_RETRY = 3
SOURCE_URL = CONFIG['source']['aircraft_json_url']

JST = timezone(timedelta(hours=9))


def fetch_aircraft():
    with urllib.request.urlopen(SOURCE_URL, timeout=10) as resp:
        return json.loads(resp.read().decode('utf-8'))


def jst_today_utc_range():
    now_jst = datetime.now(JST)
    start_jst = now_jst.replace(hour=0, minute=0, second=0, microsecond=0)
    end_jst = start_jst + timedelta(days=1)
    return (start_jst.astimezone(timezone.utc).isoformat(),
            end_jst.astimezone(timezone.utc).isoformat())


def ingest_once():
    payload = fetch_aircraft()
    now = datetime.now(timezone.utc).isoformat()
    aircraft = payload.get('aircraft', [])

    conn = connect()
    cur = conn.cursor()

    inserted = 0

    # Push：callsign 中咗 push_rules 入面任何一條 enabled rule 嘅前綴 + 已 enrich reg 才送
    # （今日 JST 第一次）。Rule 由 /push-rules/ 頁設定，唔再寫死 HKE/UO。
    today_jst = datetime.now(JST).strftime('%Y-%m-%d')
    push_secret = CONFIG.get('push', {}).get('secret')
    push_rules = []
    if push_secret:
        ensure_push_rules(conn)
        push_rules = load_enabled_rules(conn)

    for a in aircraft:
        icao = (a.get('hex') or '').strip().lower()
        if not icao:
            continue

        flight = (a.get('flight') or '').strip() or None
        category = a.get('category')
        alt_baro = a.get('alt_baro')
        if isinstance(alt_baro, str):  # tar1090 sends "ground" for landed aircraft
            alt_baro = None

        if push_secret and push_rules:
            # Push 條件：match 中咗某條 enabled rule，而且已 enrich registration（避免 push hex）。
            # callsign / icao 平路免查 registry；type / registration / route / country 要 registry
            # 先補查再 match。Dedup：aircraft_registry_cache.hke_notified_at（同 backfill 一致）。
            fields = {'callsign': flight, 'icao': icao}
            matched_label = match_rule(fields, push_rules)
            reg_row = None
            need_reg = matched_label is None and rules_need_registry(push_rules)
            if matched_label or need_reg:
                cur.execute(
                    "SELECT registration, from_airport, to_airport, aircraft_type, operator_country, "
                    "hke_notified_at, hke_push_failed_at, hke_push_fail_count "
                    "FROM aircraft_registry_cache WHERE icao = %s",
                    (icao,),
                )
                reg_row = cur.fetchone()
            if need_reg and reg_row:
                fields.update({'registration': reg_row[0], 'from': reg_row[1], 'to': reg_row[2],
                               'type': reg_row[3], 'country': reg_row[4]})
                matched_label = match_rule(fields, push_rules)
            if matched_label:
                registration = reg_row[0] if reg_row and reg_row[0] else None
                from_airport = reg_row[1] if reg_row and reg_row[1] else None
                to_airport = reg_row[2] if reg_row and reg_row[2] else None
                hke_notified_at = reg_row[5] if reg_row and reg_row[5] else None
                hke_push_failed_at = reg_row[6] if reg_row and reg_row[6] else None
                hke_push_fail_count = reg_row[7] if reg_row and reg_row[7] else 0

                if not registration:
                    # callsign 廣播咗 HKE/UO，但 reg 仲未 enrich → skip，等下個 cycle 補到再 push
                    print(json.dumps({
                        'event': 'push_hke_wait_reg',
                        'icao': icao,
                        'flight': flight,
                    }, ensure_ascii=False), flush=True)
                else:
                    already_notified_today = False
                    if hke_notified_at:
                        try:
                            last_jst = datetime.fromisoformat(hke_notified_at).astimezone(JST).strftime('%Y-%m-%d')
                            already_notified_today = (last_jst == today_jst)
                        except (ValueError, TypeError):
                            already_notified_today = False
                    # 失敗計數淨計今日 JST，舊嘅當 0（跨日自動 reset）
                    fail_count_today = 0
                    if hke_push_failed_at and hke_push_fail_count:
                        try:
                            failed_jst = datetime.fromisoformat(hke_push_failed_at).astimezone(JST).strftime('%Y-%m-%d')
                            if failed_jst == today_jst:
                                fail_count_today = hke_push_fail_count
                        except (ValueError, TypeError):
                            fail_count_today = 0
                    if not already_notified_today and fail_count_today < HKE_PUSH_MAX_RETRY:
                        # 格式：HKE confirm: HKE625 | B-LEL | Tokyo (HND)>Hong Kong (HKG)
                        flight_label = flight.strip()
                        parts = [f"{matched_label} confirm: {flight_label}", registration]
                        if from_airport and to_airport:
                            parts.append(f"{from_airport}>{to_airport}")
                        elif from_airport:
                            parts.append(from_airport)
                        elif to_airport:
                            parts.append(to_airport)

                        msg = " | ".join(parts) + f"\nhttps://www.flightradar24.com/data/aircraft/{registration.lower()}"
                        status = send_push(push_secret, msg)
                        # 送到（2xx）先寫 hke_notified_at，否則重試
                        # （封頂每日 HKE_PUSH_MAX_RETRY 次，唔好俾一次 timeout 收起成日通知）
                        if status and 200 <= status < 300:
                            cur.execute(
                                "UPDATE aircraft_registry_cache SET hke_notified_at = %s, hke_push_failed_at = NULL, hke_push_fail_count = 0 WHERE icao = %s",
                                (now, icao),
                            )
                            print(json.dumps({
                                'event': 'push_hke_confirm',
                                'icao': icao,
                                'flight': flight,
                                'registration': registration,
                                'from_airport': from_airport,
                                'to_airport': to_airport,
                                'status': status,
                            }, ensure_ascii=False), flush=True)
                        else:
                            cur.execute(
                                "UPDATE aircraft_registry_cache SET hke_push_failed_at = %s, hke_push_fail_count = %s WHERE icao = %s",
                                (now, fail_count_today + 1, icao),
                            )
                            print(json.dumps({
                                'event': 'push_hke_failed',
                                'icao': icao,
                                'flight': flight,
                                'registration': registration,
                                'status': status,
                                'attempt': fail_count_today + 1,
                                'max_retry': HKE_PUSH_MAX_RETRY,
                            }, ensure_ascii=False), flush=True)

        cur.execute(
            '''
            INSERT INTO sightings_raw (
              seen_at, receiver_name, source_name, icao, flight, category,
              alt_baro, alt_geom, gs, track, lat, lon, raw_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''',
            (
                now,
                RECEIVER_NAME,
                SOURCE_NAME,
                icao,
                flight,
                category,
                alt_baro,
                a.get('alt_geom'),
                a.get('gs'),
                a.get('track'),
                a.get('lat'),
                a.get('lon'),
                json.dumps(a, ensure_ascii=False),
            ),
        )
        inserted += 1

    conn.commit()
    conn.close()


    print(json.dumps({
        'seen_at': now,
        'receiver': RECEIVER_NAME,
        'source': SOURCE_NAME,
        'fetched_aircraft': len(aircraft),
        'inserted_rows': inserted
    }, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true', help='Run once')
    args = parser.parse_args()

    if args.once:
        ingest_once()
    else:
        ingest_once()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'ERROR: {e}', file=sys.stderr)
        sys.exit(1)
