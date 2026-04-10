import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG = json.loads((BASE_DIR / 'src' / 'config.json').read_text())
DB_PATH = BASE_DIR / CONFIG['db']['path']
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

schema = '''
CREATE TABLE IF NOT EXISTS sightings_raw (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  seen_at TEXT NOT NULL,
  receiver_name TEXT NOT NULL,
  source_name TEXT NOT NULL,
  icao TEXT NOT NULL,
  flight TEXT,
  category TEXT,
  alt_baro REAL,
  alt_geom REAL,
  gs REAL,
  track REAL,
  lat REAL,
  lon REAL,
  raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sightings_seen_at ON sightings_raw(seen_at);
CREATE INDEX IF NOT EXISTS idx_sightings_icao_seen_at ON sightings_raw(icao, seen_at);

CREATE TABLE IF NOT EXISTS aircraft_registry_cache (
  icao TEXT PRIMARY KEY,
  registration TEXT,
  country TEXT,
  lookup_source TEXT,
  last_lookup_at TEXT NOT NULL,
  operator TEXT,
  operator_country TEXT
);
'''

conn = sqlite3.connect(DB_PATH)
conn.executescript(schema)
conn.commit()
conn.close()
print(f'Initialized DB: {DB_PATH}')
