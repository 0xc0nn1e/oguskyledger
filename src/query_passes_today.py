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
    SELECT pass_id, icao, COALESCE(flight, '') AS flight, COALESCE(operator, '') AS operator,
           COALESCE(country, '') AS country, COALESCE(category, '') AS category,
           first_seen, last_seen, samples, min_alt_baro, max_alt_baro
    FROM aircraft_passes
    WHERE pass_date = %s
    ORDER BY first_seen DESC
    ''',
    (today,)
)
rows = cur.fetchall()
conn.close()

print(f'Passes Today: {today}')
print(f'Total passes: {len(rows)}')
print('-' * 170)
print(f"{'PASS_ID':7}  {'ICAO':8}  {'FLIGHT':10}  {'OPERATOR':18}  {'COUNTRY':6}  {'CAT':3}  {'SAMPLES':7}  {'FIRST_SEEN':23}  {'LAST_SEEN':23}")
print('-' * 170)
for r in rows:
    flight = r['flight'].strip() if r['flight'] else '-'
    operator = r['operator'].strip() if r['operator'] else '-'
    country = r['country'].strip() if r['country'] else '-'
    category = r['category'].strip() if r['category'] else '-'
    print(f"{r['pass_id']:7}  {r['icao']:8}  {flight:10}  {operator:18.18}  {country:6}  {category:3}  {r['samples']:7}  {fmt_ts(r['first_seen']):23}  {fmt_ts(r['last_seen']):23}")
