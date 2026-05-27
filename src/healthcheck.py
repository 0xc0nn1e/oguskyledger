import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

from db import connect, dict_cursor

BASE_DIR = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))


def fmt_ts(ts):
    if not ts:
        return '-'
    dt = datetime.fromisoformat(ts)
    return dt.astimezone(JST).strftime('%Y-%m-%d %H:%M:%S JST')

print('plane-history healthcheck')
print('=' * 60)

try:
    uid = subprocess.check_output(['id', '-u']).decode().strip()
    out = subprocess.check_output([
        'launchctl', 'print', f'gui/{uid}/com.connie.plane-history.supervisor'
    ], stderr=subprocess.STDOUT).decode()
    state_line = next((line.strip() for line in out.splitlines() if 'state =' in line), 'state = unknown')
    exit_line = next((line.strip() for line in out.splitlines() if 'last exit code =' in line), 'last exit code = unknown')
    runs_line = next((line.strip() for line in out.splitlines() if 'runs =' in line), 'runs = unknown')
    print(f'launchd: {state_line}')
    print(f'launchd: {exit_line}')
    print(f'launchd: {runs_line}')
except Exception as e:
    print(f'launchd: ERROR {e}')

try:
    conn = connect()
    cur = dict_cursor(conn)
    cur.execute('SELECT COUNT(*) AS c FROM sightings_raw')
    raw_count = cur.fetchone()['c']
    cur.execute('SELECT COUNT(*) AS c FROM aircraft_passes')
    pass_count = cur.fetchone()['c']
    cur.execute('SELECT MAX(seen_at) AS ts FROM sightings_raw')
    last_seen = cur.fetchone()['ts']
    conn.close()
    print('db: OK (mysql)')
    print(f'raw rows: {raw_count}')
    print(f'passes: {pass_count}')
    print(f'last sample: {fmt_ts(last_seen)}')
except Exception as e:
    print(f'db: ERROR {e}')

for name in ['data/ingest.log', 'data/launchd.out.log', 'data/launchd.err.log']:
    p = BASE_DIR / name
    if p.exists():
        print(f'log: {name} ({p.stat().st_size} bytes)')
    else:
        print(f'log: {name} missing')
