import argparse
import json
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG = json.loads((BASE_DIR / 'src' / 'config.json').read_text())
DB_PATH = BASE_DIR / CONFIG['db']['path']

RECEIVER_NAME = CONFIG['receiver']['name']
SOURCE_NAME = CONFIG['source']['name']
SOURCE_URL = CONFIG['source']['aircraft_json_url']


def fetch_aircraft():
    with urllib.request.urlopen(SOURCE_URL, timeout=10) as resp:
        return json.loads(resp.read().decode('utf-8'))


def ingest_once():
    payload = fetch_aircraft()
    now = datetime.now(timezone.utc).isoformat()
    aircraft = payload.get('aircraft', [])

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    inserted = 0

    for a in aircraft:
        icao = (a.get('hex') or '').strip().lower()
        if not icao:
            continue

        cur.execute(
            '''
            INSERT INTO sightings_raw (
              seen_at, receiver_name, source_name, icao, flight, category,
              alt_baro, alt_geom, gs, track, lat, lon, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                now,
                RECEIVER_NAME,
                SOURCE_NAME,
                icao,
                (a.get('flight') or '').strip() or None,
                a.get('category'),
                a.get('alt_baro'),
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
