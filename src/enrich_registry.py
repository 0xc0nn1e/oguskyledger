import json
from datetime import datetime, timezone

from db import connect, dict_cursor

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


conn = connect()
cur = dict_cursor(conn)

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
        INSERT INTO aircraft_registry_cache (icao, registration, country, lookup_source, last_lookup_at)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          registration = VALUES(registration),
          country = VALUES(country),
          lookup_source = VALUES(lookup_source),
          last_lookup_at = VALUES(last_lookup_at)
        ''',
        (icao, registration, country, source, now)
    )
    added += 1

conn.commit()
conn.close()
print(json.dumps({'enriched': added, 'at': now}, ensure_ascii=False))
