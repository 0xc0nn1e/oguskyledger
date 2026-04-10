import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG = json.loads((BASE_DIR / 'src' / 'config.json').read_text())
DB_PATH = BASE_DIR / CONFIG['db']['path']

JST = timezone(timedelta(hours=9))

def fmt_ts(ts):
    if not ts:
        return '-'
    dt = datetime.fromisoformat(ts)
    return dt.astimezone(JST).strftime('%Y-%m-%d %H:%M:%S JST')

today = datetime.now(JST).strftime('%Y-%m-%d')

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT COUNT(*) AS c FROM sightings_raw WHERE substr(seen_at,1,10)=?", (today,))
rows_today = cur.fetchone()['c']

cur.execute("SELECT COUNT(DISTINCT icao) AS c FROM sightings_raw WHERE substr(seen_at,1,10)=?", (today,))
unique_today = cur.fetchone()['c']

cur.execute(
    '''
    SELECT COALESCE(category, '-') AS category, COUNT(DISTINCT icao) AS c
    FROM sightings_raw
    WHERE substr(seen_at,1,10)=?
    GROUP BY COALESCE(category, '-')
    ORDER BY c DESC
    LIMIT 10
    ''',
    (today,)
)
by_category = cur.fetchall()

cur.execute(
    '''
    SELECT
      icao,
      COALESCE(MAX(flight), '') AS flight,
      COUNT(*) AS samples,
      MIN(seen_at) AS first_seen,
      MAX(seen_at) AS last_seen
    FROM sightings_raw
    WHERE substr(seen_at,1,10)=?
    GROUP BY icao
    ORDER BY samples DESC, last_seen DESC
    LIMIT 10
    ''',
    (today,)
)
top_seen = cur.fetchall()

conn.close()

print(f'Daily Summary: {today}')
print(f'Total rows: {rows_today}')
print(f'Unique aircraft: {unique_today}')
print('Top categories:')
for r in by_category:
    print(f"- {r['category']}: {r['c']}")
print('Top seen aircraft:')
for r in top_seen:
    flight = r['flight'].strip() if r['flight'] else '-'
    print(f"- {r['icao']} {flight} samples={r['samples']} first={fmt_ts(r['first_seen'])} last={fmt_ts(r['last_seen'])}")
