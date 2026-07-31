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

# Django 遷移後 supervisor 已拆做五個獨立 launchd job
LAUNCHD_JOBS = ['backfill', 'healthcheck', 'ingest', 'stats-cache', 'web']

# uid 攞唔到都唔好炸死成個 healthcheck，後面 DB / log 檢查照行
try:
    uid = subprocess.check_output(['id', '-u']).decode().strip()
except Exception as e:
    uid = None
    print(f'launchd: ERROR 攞唔到 uid（{e}），跳過 launchd 檢查')

for job in (LAUNCHD_JOBS if uid is not None else []):
    label = f'com.connie.plane-history.{job}'
    try:
        out = subprocess.check_output([
            'launchctl', 'print', f'gui/{uid}/{label}'
        ], stderr=subprocess.STDOUT).decode()
        state_line = next((line.strip() for line in out.splitlines() if 'state =' in line), 'state = unknown')
        exit_line = next((line.strip() for line in out.splitlines() if 'last exit code =' in line), 'last exit code = unknown')
        print(f'launchd[{job}]: {state_line} | {exit_line}')
    except Exception as e:
        print(f'launchd[{job}]: ERROR {e}')

# chromium headless 數量——browser_bulk_backfill 漏 page 嗰陣 renderer 會堆積
# （試過堆到 59 個食成 5.6GB RAM），正常一次 run 大約 6-12 個
try:
    ps_out = subprocess.check_output(['ps', '-axo', 'rss=,comm='], text=True)
    chrome_rss = [int(line.split(None, 1)[0]) for line in ps_out.splitlines()
                  if 'chrome-headless-shell' in line]
    n_chrome = len(chrome_rss)
    rss_mb = sum(chrome_rss) / 1024
    if n_chrome > 20:
        print(f'chromium: 警告 {n_chrome} 個 process（{rss_mb:.0f} MB）——疑似 renderer 堆積，檢查 browser_bulk_backfill')
    else:
        print(f'chromium: OK {n_chrome} 個 process（{rss_mb:.0f} MB）')
except Exception as e:
    print(f'chromium: ERROR {e}')

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

# django-web.log 係 gunicorn stdout，設計上長期 0 byte，唔擺入嚟以免似 false alarm；
# web 嘅實際 log 係 access / error。五個 job 嘅 *.err（launchd StandardErrorPath）
# 全部要睇——management command 起唔到身 / traceback 係落呢度，唔係 *.log
for name in ['data/django-ingest.log', 'data/django-backfill.log',
              'data/django-healthcheck.log', 'data/browser_bulk_backfill.log',
              'data/django-stats-cache.log',
              'data/django-access.log', 'data/django-error.log',
              'data/django-ingest.err', 'data/django-backfill.err',
              'data/django-healthcheck.err', 'data/django-stats-cache.err',
              'data/django-web.err']:
    p = BASE_DIR / name
    if p.exists():
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=JST).strftime('%Y-%m-%d %H:%M:%S JST')
        print(f'log: {name} ({p.stat().st_size} bytes, 最後寫入 {mtime})')
    else:
        print(f'log: {name} missing')
