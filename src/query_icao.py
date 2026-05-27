import sys
from datetime import datetime, timezone, timedelta

from db import connect, dict_cursor

if len(sys.argv) < 2:
    print('Usage: python3 src/query_icao.py <icao-or-flight>')
    sys.exit(1)

JST = timezone(timedelta(hours=9))

def fmt_ts(ts):
    if not ts:
        return '-'
    dt = datetime.fromisoformat(ts)
    return dt.astimezone(JST).strftime('%Y-%m-%d %H:%M:%S JST')

term = sys.argv[1].strip().lower()

conn = connect()
cur = dict_cursor(conn)
cur.execute(
    '''
    SELECT
      s.icao,
      COALESCE(s.flight, '') AS flight,
      COALESCE(c.registration, '') AS registration,
      COALESCE(c.country, '') AS country,
      COALESCE(c.operator, '') AS operator,
      s.category,
      s.seen_at,
      s.alt_baro,
      s.gs,
      s.lat,
      s.lon
    FROM sightings_raw s
    LEFT JOIN aircraft_registry_cache c ON c.icao = s.icao
    WHERE LOWER(s.icao) = %s
       OR LOWER(COALESCE(s.flight, '')) LIKE CONCAT('%%', %s, '%%')
    ORDER BY s.seen_at DESC
    LIMIT 50
    ''',
    (term, term)
)
rows = cur.fetchall()
conn.close()

print(f'Results: {len(rows)}')
print('-' * 100)
for r in rows:
    flight = r['flight'].strip() if r['flight'] else '-'
    alt = str(int(r['alt_baro'])) if r['alt_baro'] is not None else '-'
    gs = f"{r['gs']:.1f}" if r['gs'] is not None else '-'
    lat = f"{r['lat']:.4f}" if r['lat'] is not None else '-'
    lon = f"{r['lon']:.4f}" if r['lon'] is not None else '-'
    reg = r['registration'].strip() if r['registration'] else '-'
    country = r['country'].strip() if r['country'] else '-'
    operator = r['operator'].strip() if r['operator'] else '-'
    cat = r['category'] or '-'
    print(f"{fmt_ts(r['seen_at'])}  {r['icao']}  {flight:10}  op={operator:18.18}  reg={reg:10}  country={country:6}  cat={cat:>3}  alt={alt:>6}  gs={gs:>6}  lat={lat} lon={lon}")
