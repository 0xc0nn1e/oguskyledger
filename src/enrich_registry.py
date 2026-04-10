import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG = json.loads((BASE_DIR / 'src' / 'config.json').read_text())
DB_PATH = BASE_DIR / CONFIG['db']['path']

PREFIX_COUNTRY = [
    ((0x71C000, 0x71CFFF), 'HL-', '韓國'),
    ((0x71BE00, 0x71BFFF), 'HL-', '韓國'),
    ((0x840000, 0x87FFFF), 'JA-', '日本'),
    ((0x780000, 0x7BFFFF), 'B-', '中國'),
    ((0x800000, 0x83FFFF), 'VT-', '印度'),
    ((0xA00000, 0xAFFFFF), 'N-', '美國'),
    ((0x4CA000, 0x4CAFFF), 'EI-', '愛爾蘭'),
]


def infer_from_icao(icao):
    try:
        value = int(icao, 16)
    except Exception:
        return None, None, 'invalid'

    for (start, end), reg_prefix, country in PREFIX_COUNTRY:
        if start <= value <= end:
            return None, country, f'icao-prefix:{reg_prefix}'
    return None, '未知', 'icao-prefix:unknown'


conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.executescript(
    '''
    CREATE TABLE IF NOT EXISTS aircraft_registry_cache (
      icao TEXT PRIMARY KEY,
      registration TEXT,
      country TEXT,
      lookup_source TEXT,
      last_lookup_at TEXT NOT NULL
    );
    '''
)

cur.execute(
    '''
    SELECT DISTINCT s.icao
    FROM sightings_raw s
    LEFT JOIN aircraft_registry_cache c ON c.icao = s.icao
    WHERE c.icao IS NULL
    ORDER BY s.icao
    '''
)
missing = [r['icao'] for r in cur.fetchall()]

now = datetime.now(timezone.utc).isoformat()
added = 0
for icao in missing:
    registration, country, source = infer_from_icao(icao)
    cur.execute(
        '''
        INSERT OR REPLACE INTO aircraft_registry_cache (icao, registration, country, lookup_source, last_lookup_at)
        VALUES (?, ?, ?, ?, ?)
        ''',
        (icao, registration, country, source, now)
    )
    added += 1

conn.commit()
conn.close()
print(json.dumps({'enriched': added, 'at': now}, ensure_ascii=False))
