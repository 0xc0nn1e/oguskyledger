import argparse
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from db import connect
from notifier import send_push

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG = json.loads((BASE_DIR / 'src' / 'config.json').read_text())

RECEIVER_NAME = CONFIG['receiver']['name']
SOURCE_NAME = CONFIG['source']['name']
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

    # Send one sample message on first sighting today (JST)
    today_jst = datetime.now(JST).strftime('%Y-%m-%d')
    today_start_utc, today_end_utc = jst_today_utc_range()
    push_secret = CONFIG.get('push', {}).get('secret')

    for a in aircraft:
        icao = (a.get('hex') or '').strip().lower()
        if not icao:
            continue

        flight = (a.get('flight') or '').strip() or None
        category = a.get('category')
        alt_baro = a.get('alt_baro')
        if isinstance(alt_baro, str):  # tar1090 sends "ground" for landed aircraft
            alt_baro = None

        if push_secret:
            cur.execute(
                "SELECT registration, country, operator, aircraft_type FROM aircraft_registry_cache WHERE icao = %s",
                (icao,),
            )
            reg_row = cur.fetchone()
            registration = reg_row[0] if reg_row and reg_row[0] else None
            country = reg_row[1] if reg_row and reg_row[1] else None
            operator = reg_row[2] if reg_row and reg_row[2] else None
            aircraft_type = reg_row[3] if reg_row and reg_row[3] else None

            is_hke = bool((flight and flight.startswith('HKE')) or operator == 'Hong Kong Express')
            if is_hke:
                cur.execute(
                    """
                    SELECT 1 FROM sightings_raw
                    WHERE icao = %s
                      AND seen_at >= %s AND seen_at < %s
                      AND (
                        (flight IS NOT NULL AND flight LIKE 'HKE%%')
                        OR icao IN (SELECT icao FROM aircraft_registry_cache WHERE operator = 'Hong Kong Express')
                      )
                    LIMIT 1
                    """,
                    (icao, today_start_utc, today_end_utc),
                )
                already_confirmed_today = cur.fetchone() is not None
                if not already_confirmed_today:
                    title = registration or icao.upper()
                    parts = [f"HKE confirm: {title}"]
                    if flight:
                        parts.append(f"flight {flight}")
                    if operator:
                        parts.append(operator)
                    if aircraft_type:
                        parts.append(aircraft_type)
                    if country:
                        parts.append(country)

                    link_target = (registration or icao).lower()
                    msg = " | ".join(parts) + f"\nhttps://www.flightradar24.com/data/aircraft/{link_target}"
                    status = send_push(push_secret, msg)
                    print(json.dumps({
                        'event': 'push_hke_confirm',
                        'icao': icao,
                        'flight': flight,
                        'registration': registration,
                        'operator': operator,
                        'aircraft_type': aircraft_type,
                        'country': country,
                        'status': status,
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
