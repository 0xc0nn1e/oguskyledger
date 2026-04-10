import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG = json.loads((BASE_DIR / 'src' / 'config.json').read_text())
DB_PATH = BASE_DIR / CONFIG['db']['path']

PASS_GAP_MINUTES = 20
UTC = timezone.utc
JST = timezone(timedelta(hours=9))

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.executescript(
    '''
    CREATE TABLE IF NOT EXISTS aircraft_passes (
      pass_id INTEGER PRIMARY KEY AUTOINCREMENT,
      pass_date TEXT NOT NULL,
      icao TEXT NOT NULL,
      flight TEXT,
      operator TEXT,
      country TEXT,
      category TEXT,
      first_seen TEXT NOT NULL,
      last_seen TEXT NOT NULL,
      samples INTEGER NOT NULL,
      min_alt_baro REAL,
      max_alt_baro REAL,
      min_gs REAL,
      max_gs REAL
    );
    CREATE INDEX IF NOT EXISTS idx_passes_date ON aircraft_passes(pass_date);
    CREATE INDEX IF NOT EXISTS idx_passes_icao_date ON aircraft_passes(icao, pass_date);
    DELETE FROM aircraft_passes;
    '''
)

cur.execute(
    '''
    SELECT
      s.icao,
      s.seen_at,
      COALESCE(s.flight, '') AS flight,
      COALESCE(s.category, '') AS category,
      s.alt_baro,
      s.gs,
      COALESCE(c.operator, '') AS operator,
      COALESCE(c.country, '') AS country
    FROM sightings_raw s
    LEFT JOIN aircraft_registry_cache c ON c.icao = s.icao
    ORDER BY s.icao ASC, s.seen_at ASC
    '''
)
rows = cur.fetchall()

passes = []
current = None
last_dt = None

for r in rows:
    dt = datetime.fromisoformat(r['seen_at'])
    if current is None or r['icao'] != current['icao'] or (dt - last_dt) > timedelta(minutes=PASS_GAP_MINUTES):
        if current is not None:
            passes.append(current)
        current = {
            'icao': r['icao'],
            'flight': (r['flight'] or '').strip() or None,
            'operator': (r['operator'] or '').strip() or None,
            'country': (r['country'] or '').strip() or None,
            'category': (r['category'] or '').strip() or None,
            'first_seen': r['seen_at'],
            'last_seen': r['seen_at'],
            'samples': 1,
            'min_alt_baro': r['alt_baro'],
            'max_alt_baro': r['alt_baro'],
            'min_gs': r['gs'],
            'max_gs': r['gs'],
        }
    else:
        current['last_seen'] = r['seen_at']
        current['samples'] += 1
        if r['alt_baro'] is not None:
            current['min_alt_baro'] = r['alt_baro'] if current['min_alt_baro'] is None else min(current['min_alt_baro'], r['alt_baro'])
            current['max_alt_baro'] = r['alt_baro'] if current['max_alt_baro'] is None else max(current['max_alt_baro'], r['alt_baro'])
        if r['gs'] is not None:
            current['min_gs'] = r['gs'] if current['min_gs'] is None else min(current['min_gs'], r['gs'])
            current['max_gs'] = r['gs'] if current['max_gs'] is None else max(current['max_gs'], r['gs'])
        if not current['flight'] and r['flight']:
            current['flight'] = r['flight'].strip()
        if not current['operator'] and r['operator']:
            current['operator'] = r['operator'].strip()
        if not current['country'] and r['country']:
            current['country'] = r['country'].strip()
        if not current['category'] and r['category']:
            current['category'] = r['category'].strip()
    last_dt = dt

if current is not None:
    passes.append(current)

for p in passes:
    pass_date = datetime.fromisoformat(p['first_seen']).astimezone(JST).strftime('%Y-%m-%d')
    cur.execute(
        '''
        INSERT INTO aircraft_passes (
          pass_date, icao, flight, operator, country, category,
          first_seen, last_seen, samples, min_alt_baro, max_alt_baro, min_gs, max_gs
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            pass_date, p['icao'], p['flight'], p['operator'], p['country'], p['category'],
            p['first_seen'], p['last_seen'], p['samples'], p['min_alt_baro'], p['max_alt_baro'], p['min_gs'], p['max_gs']
        )
    )

conn.commit()
conn.close()
print(json.dumps({'passes_built': len(passes), 'gap_minutes': PASS_GAP_MINUTES}, ensure_ascii=False))
