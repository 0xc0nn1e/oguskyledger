import json
from datetime import datetime, timedelta, timezone

from db import connect, dict_cursor, column_set

PASS_GAP_MINUTES = 20
# Incremental rebuild：只重砌近 REBUILD_DAYS 日嘅 pass，舊 pass 凍結保留，
# 唔再每 cycle 由全史 full-rebuild（之前 O(所有歷史)/分鐘、無上限）。
# 配合 retention（prune 舊 sightings_raw）：full rebuild 已退役，唔好再用。
REBUILD_DAYS = 3
# Scan 由 W - BUFFER_HOURS 開始，令跨越 W 邊界（first_seen<W、last_seen>=W）嘅 pass
# 完整重砌唔被截斷。BUFFER 必須 > 最長 pass 時長（觀測 max ~9h；24h 有充足 margin）。
BUFFER_HOURS = 24
UTC = timezone.utc
JST = timezone(timedelta(hours=9))

_now = datetime.now(UTC)
W = (_now - timedelta(days=REBUILD_DAYS)).isoformat()                         # 重砌 cutoff
W_SCAN = (_now - timedelta(days=REBUILD_DAYS, hours=BUFFER_HOURS)).isoformat()  # scan 起點（含 buffer）

conn = connect()
cur = dict_cursor(conn)

# 自我修復 schema：from/to column + snapshots 表
_pass_cols = column_set(conn, 'aircraft_passes')
if 'from_airport' not in _pass_cols:
    cur.execute('ALTER TABLE aircraft_passes ADD COLUMN from_airport VARCHAR(64)')
if 'to_airport' not in _pass_cols:
    cur.execute('ALTER TABLE aircraft_passes ADD COLUMN to_airport VARCHAR(64)')
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

# 拎每組 (icao, flight) 最新一條 route snapshot，俾起 pass 嗰陣 lookup 用
cur.execute(
    '''SELECT s.icao, s.flight, s.from_airport, s.to_airport
       FROM aircraft_route_snapshots s
       INNER JOIN (
         SELECT icao, flight, MAX(observed_at) AS latest
         FROM aircraft_route_snapshots
         GROUP BY icao, flight
       ) m ON m.icao = s.icao AND m.flight = s.flight AND m.latest = s.observed_at'''
)
snapshot_map = {(r['icao'], r['flight']): (r['from_airport'], r['to_airport'])
                for r in cur.fetchall()}

# 只刪近窗（last_seen >= W）嘅 pass；舊 pass（last_seen < W）凍結保留。
cur.execute('DELETE FROM aircraft_passes WHERE last_seen >= %s', (W,))

# Scan 由 W_SCAN（含 buffer）起，等過界 pass 完整重砌；下面 insert 只揀返 last_seen >= W 嗰啲。
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
    WHERE s.seen_at >= %s
    ORDER BY s.icao ASC, s.seen_at ASC
    ''',
    (W_SCAN,)
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

inserted = 0
for p in passes:
    # buffer 區（last_seen < W）嘅 pass 冇被 DELETE，仲喺 DB，唔好重複 insert。
    if p['last_seen'] < W:
        continue
    pass_date = datetime.fromisoformat(p['first_seen']).astimezone(JST).strftime('%Y-%m-%d')
    # per-pass from/to：用 (icao, flight) 喺 snapshot map 揾返。冇 callsign 就唔填，唔好亂用 registry 嘅最新一條。
    from_airport = None
    to_airport = None
    if p['flight']:
        snap = snapshot_map.get((p['icao'], p['flight']))
        if snap:
            from_airport, to_airport = snap
    cur.execute(
        '''
        INSERT INTO aircraft_passes (
          pass_date, icao, flight, operator, country, category,
          first_seen, last_seen, samples, min_alt_baro, max_alt_baro, min_gs, max_gs,
          from_airport, to_airport
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''',
        (
            pass_date, p['icao'], p['flight'], p['operator'], p['country'], p['category'],
            p['first_seen'], p['last_seen'], p['samples'], p['min_alt_baro'], p['max_alt_baro'], p['min_gs'], p['max_gs'],
            from_airport, to_airport,
        )
    )
    inserted += 1

conn.commit()
conn.close()
print(json.dumps({'passes_built': inserted, 'window_days': REBUILD_DAYS, 'gap_minutes': PASS_GAP_MINUTES}, ensure_ascii=False))
