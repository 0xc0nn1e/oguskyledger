import json
import re
from datetime import datetime, timezone

from db import connect, dict_cursor, column_set

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


conn = connect()
cur = dict_cursor(conn)

columns = column_set(conn, 'aircraft_registry_cache')
if 'operator' not in columns:
    cur.execute("ALTER TABLE aircraft_registry_cache ADD COLUMN operator VARCHAR(255)")
if 'operator_country' not in columns:
    cur.execute("ALTER TABLE aircraft_registry_cache ADD COLUMN operator_country VARCHAR(64)")

# 淨係攞 operator 或 operator_country 仲係空嘅機（browser backfill 會寫 operator
# 但唔寫 operator_country，所以兩個欄位都要檢查，唔可以淨睇 operator）。
# 以前全表攞晒再每分鐘重寫 1000+ 行一樣嘅值，個大 transaction 鎖住
# aircraft_registry_cache，搞到 build_passes 成日 lock wait timeout、
# 成個 step 又撞 ingest_pipeline 嘅 60 秒上限
cur.execute(
    '''
    SELECT s.icao, COALESCE(MAX(s.flight), '') AS flight
    FROM sightings_raw s
    LEFT JOIN aircraft_registry_cache c ON c.icao = s.icao
    GROUP BY s.icao
    HAVING COALESCE(MAX(c.operator), '') = ''
        OR COALESCE(MAX(c.operator_country), '') = ''
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

    cur.execute('SELECT country FROM aircraft_registry_cache WHERE icao = %s', (icao,))
    existing = cur.fetchone()
    existing_country = existing['country'] if existing else None

    cur.execute(
        '''
        INSERT INTO aircraft_registry_cache (icao, registration, country, lookup_source, last_lookup_at, operator, operator_country)
        VALUES (%s, NULL, %s, 'operator-infer', %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          -- 現有值優先：browser backfill 嘅 operator 係權威來源，
          -- prefix infer 淨係准補空位，唔准覆寫
          operator = COALESCE(NULLIF(aircraft_registry_cache.operator, ''), VALUES(operator)),
          operator_country = COALESCE(NULLIF(aircraft_registry_cache.operator_country, ''), VALUES(operator_country)),
          country = CASE
            WHEN VALUES(operator_country) IN ('香港') THEN VALUES(operator_country)
            ELSE COALESCE(aircraft_registry_cache.country, VALUES(country))
          END,
          last_lookup_at = VALUES(last_lookup_at)
        ''',
        (icao, existing_country or op_country or '未知', now, operator, op_country)
    )
    updated += 1

conn.commit()
conn.close()
print(json.dumps({'updated': updated, 'at': now}, ensure_ascii=False))
