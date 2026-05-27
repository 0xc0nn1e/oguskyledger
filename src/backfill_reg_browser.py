import json
from datetime import datetime, timezone

from db import connect

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

conn = connect()
cur = conn.cursor()
now = datetime.now(timezone.utc).isoformat()
updated = 0
for icao, (reg, country) in REG_DATA.items():
    cur.execute(
        '''
        INSERT INTO aircraft_registry_cache (icao, registration, country, lookup_source, last_lookup_at)
        VALUES (%s, %s, %s, 'tar1090-browser', %s)
        ON DUPLICATE KEY UPDATE
          registration = VALUES(registration),
          country = VALUES(country),
          lookup_source = VALUES(lookup_source),
          last_lookup_at = VALUES(last_lookup_at)
        ''',
        (icao.lower(), reg, country, now)
    )
    updated += 1
conn.commit()
conn.close()
print(json.dumps({'updated': updated, 'source': 'tar1090-browser', 'at': now}, ensure_ascii=False))
