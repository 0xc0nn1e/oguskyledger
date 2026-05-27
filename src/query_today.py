from datetime import datetime, timezone, timedelta

from db import connect, dict_cursor

JST = timezone(timedelta(hours=9))

def fmt_ts(ts):
    if not ts:
        return '-'
    dt = datetime.fromisoformat(ts)
    return dt.astimezone(JST).strftime('%Y-%m-%d %H:%M:%S JST')

today = datetime.now(JST).strftime('%Y-%m-%d')

conn = connect()
cur = dict_cursor(conn)
cur.execute(
    '''
    SELECT
      s.icao,
      COALESCE(MAX(NULLIF(TRIM(s.flight), '')), '') AS flight,
      COALESCE(MAX(NULLIF(TRIM(s.category), '')), '') AS category,
      COALESCE(MAX(NULLIF(TRIM(c.registration), '')), '') AS registration,
      COALESCE(MAX(NULLIF(TRIM(c.country), '')), '') AS country,
      COALESCE(MAX(NULLIF(TRIM(c.operator), '')), '') AS operator,
      MIN(s.seen_at) AS first_seen,
      MAX(s.seen_at) AS last_seen,
      MIN(CASE WHEN s.alt_baro IS NOT NULL THEN s.alt_baro END) AS min_alt_baro,
      MAX(CASE WHEN s.alt_baro IS NOT NULL THEN s.alt_baro END) AS max_alt_baro,
      COUNT(*) AS samples
    FROM sightings_raw s
    LEFT JOIN aircraft_registry_cache c ON c.icao = s.icao
    WHERE SUBSTR(s.seen_at, 1, 10) = %s
    GROUP BY s.icao
    ORDER BY last_seen DESC
    ''',
    (today,)
)
rows = cur.fetchall()
conn.close()

print(f'Today: {today}')
print(f'Aircraft seen by receiver: {len(rows)}')
print('-' * 150)
print(f"{'ICAO':8}  {'FLIGHT':10}  {'OPERATOR':18}  {'REG':10}  {'COUNTRY':6}  {'CAT':3}  {'ALT_MIN':>7}  {'ALT_MAX':>7}  {'SAMPLES':>7}  {'FIRST_SEEN':23}  {'LAST_SEEN':23}")
print('-' * 150)
for r in rows:
    flight = r['flight'].strip() if r['flight'] else '-'
    operator = r['operator'].strip() if r['operator'] else '-'
    registration = r['registration'].strip() if r['registration'] else '-'
    country = r['country'].strip() if r['country'] else '-'
    category = r['category'].strip() if r['category'] else '-'
    min_alt = str(int(r['min_alt_baro'])) if r['min_alt_baro'] is not None else '-'
    max_alt = str(int(r['max_alt_baro'])) if r['max_alt_baro'] is not None else '-'
    first_seen = fmt_ts(r['first_seen'])
    last_seen = fmt_ts(r['last_seen'])
    print(f"{r['icao']:8}  {flight:10}  {operator:18.18}  {registration:10}  {country:6}  {category:3}  {min_alt:>7}  {max_alt:>7}  {r['samples']:>7}  {first_seen:23}  {last_seen:23}")
