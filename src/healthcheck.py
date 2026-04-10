import json
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG = json.loads((BASE_DIR / 'src' / 'config.json').read_text())
DB_PATH = BASE_DIR / CONFIG['db']['path']
JST = timezone(timedelta(hours=9))


def fmt_ts(ts):
    if not ts:
        return '-'
    dt = datetime.fromisoformat(ts)
    return dt.astimezone(JST).strftime('%Y-%m-%d %H:%M:%S JST')

print('plane-history healthcheck')
print('=' * 60)

try:
    out = subprocess.check_output([
        'launchctl', 'print', f'gui:{subprocess.check_output(["id", "-u"]).decode().strip()}/com.connie.plane-history.ingest'
    ], stderr=subprocess.STDOUT).decode()
    state_line = next((line.strip() for line in out.splitlines() if 'state =' in line), 'state = unknown')
    print(f'launchd: {state_line}')
except Exception as e:
    print(f'launchd: ERROR {e}')

if Path(DB_PATH).exists():
    print(f'db: OK {DB_PATH}')
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) AS c FROM sightings_raw')
    raw_count = cur.fetchone()['c']
    cur.execute('SELECT COUNT(*) AS c FROM aircraft_passes')
    pass_count = cur.fetchone()['c']
    cur.execute('SELECT MAX(seen_at) AS ts FROM sightings_raw')
    last_seen = cur.fetchone()['ts']
    conn.close()
    print(f'raw rows: {raw_count}')
    print(f'passes: {pass_count}')
    print(f'last sample: {fmt_ts(last_seen)}')
else:
    print('db: missing')

for name in ['data/ingest.log', 'data/launchd.out.log', 'data/launchd.err.log']:
    p = BASE_DIR / name
    if p.exists():
        print(f'log: {name} ({p.stat().st_size} bytes)')
    else:
        print(f'log: {name} missing')
