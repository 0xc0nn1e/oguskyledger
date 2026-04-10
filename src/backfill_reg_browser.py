import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / 'data' / 'plane_history.sqlite3'

REG_DATA = {
    '71c010': ('HL8010', '韓國'),
    '71bf34': ('HL7734', '韓國'),
    '78195c': ('B-20EU', '中國'),
    '845dee': ('JA114A', '日本'),
    '84b794': ('JA213A', '日本'),
    '8514b4': ('JA321J', '日本'),
    '851bfe': ('JA342J', '日本'),
    '851c64': ('JA345J', '日本'),
    '861e70': ('JA611A', '日本'),
    '861f22': ('JA616J', '日本'),
    '868094': ('JA73AN', '日本'),
    '8681b6': ('JA73NQ', '日本'),
}

conn = sqlite3.connect(DB_PATH)
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
now = datetime.now(timezone.utc).isoformat()
updated = 0
for icao, (reg, country) in REG_DATA.items():
    cur.execute(
        '''
        INSERT INTO aircraft_registry_cache (icao, registration, country, lookup_source, last_lookup_at)
        VALUES (?, ?, ?, 'tar1090-browser', ?)
        ON CONFLICT(icao) DO UPDATE SET
          registration = excluded.registration,
          country = excluded.country,
          lookup_source = excluded.lookup_source,
          last_lookup_at = excluded.last_lookup_at
        ''',
        (icao.lower(), reg, country, now)
    )
    updated += 1
conn.commit()
conn.close()
print(json.dumps({'updated': updated, 'source': 'tar1090-browser', 'at': now}, ensure_ascii=False))
