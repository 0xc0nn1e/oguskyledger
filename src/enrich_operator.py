import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG = json.loads((BASE_DIR / 'src' / 'config.json').read_text())
DB_PATH = BASE_DIR / CONFIG['db']['path']

OPERATOR_RULES = [
    (r'^ANA', 'All Nippon Airways', '日本'),
    (r'^JAL', 'Japan Airlines', '日本'),
    (r'^SKY', 'Skymark Airlines', '日本'),
    (r'^AAR', 'Asiana Airlines', '韓國'),
    (r'^KAL', 'Korean Air', '韓國'),
    (r'^CPA', 'Cathay Pacific', '香港'),
    (r'^HKE', 'Hong Kong Express', '香港'),
    (r'^CRK', 'Hong Kong Airlines', '香港'),
    (r'^AIC', 'Air India', '印度'),
    (r'^DAL', 'Delta Air Lines', '美國'),
    (r'^AAL', 'American Airlines', '美國'),
    (r'^UPS', 'UPS Airlines', '美國'),
    (r'^ITY', 'ITA Airways', '意大利'),
]


def infer_operator(flight):
    if not flight:
        return None, None
    flight = flight.strip().upper()
    for pattern, operator, country in OPERATOR_RULES:
        if re.match(pattern, flight):
            return operator, country
    return None, None


conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute(
    '''
    CREATE TABLE IF NOT EXISTS aircraft_registry_cache (
      icao TEXT PRIMARY KEY,
      registration TEXT,
      country TEXT,
      lookup_source TEXT,
      last_lookup_at TEXT NOT NULL,
      operator TEXT,
      operator_country TEXT
    )
    '''
)

cur.execute("PRAGMA table_info(aircraft_registry_cache)")
columns = {row[1] for row in cur.fetchall()}
if 'operator' not in columns:
    cur.execute("ALTER TABLE aircraft_registry_cache ADD COLUMN operator TEXT")
if 'operator_country' not in columns:
    cur.execute("ALTER TABLE aircraft_registry_cache ADD COLUMN operator_country TEXT")

cur.execute(
    '''
    SELECT s.icao, COALESCE(MAX(s.flight), '') AS flight
    FROM sightings_raw s
    GROUP BY s.icao
    ORDER BY s.icao
    '''
)
rows = cur.fetchall()

now = datetime.now(timezone.utc).isoformat()
updated = 0
for r in rows:
    icao = r['icao']
    flight = (r['flight'] or '').strip()
    operator, op_country = infer_operator(flight)
    if operator is None:
        continue

    cur.execute('SELECT country FROM aircraft_registry_cache WHERE icao = ?', (icao,))
    existing = cur.fetchone()
    existing_country = existing['country'] if existing else None

    cur.execute(
        '''
        INSERT INTO aircraft_registry_cache (icao, registration, country, lookup_source, last_lookup_at, operator, operator_country)
        VALUES (?, NULL, ?, 'operator-infer', ?, ?, ?)
        ON CONFLICT(icao) DO UPDATE SET
          operator = COALESCE(excluded.operator, aircraft_registry_cache.operator),
          operator_country = COALESCE(excluded.operator_country, aircraft_registry_cache.operator_country),
          country = CASE
            WHEN excluded.operator_country IN ('香港') THEN excluded.operator_country
            ELSE COALESCE(aircraft_registry_cache.country, excluded.country)
          END,
          last_lookup_at = excluded.last_lookup_at
        ''',
        (icao, existing_country or op_country or '未知', now, operator, op_country)
    )
    updated += 1

conn.commit()
conn.close()
print(json.dumps({'updated': updated, 'at': now}, ensure_ascii=False))
