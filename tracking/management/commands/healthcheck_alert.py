"""manage.py healthcheck_alert — 監察 ingest feed，超過 1 小時冇 update push 通知。

Diagnose 兩條 path：
  1. MySQL 連到 → SQL `SELECT 1` 正常
  2. tar1090 source URL 通 → HTTP 200 + JSON parse 到

Push message 例：
  ALERT · feed 無 update 87m · DB ok · tar1090 404
  ALERT · feed 無 update 65m · DB down: 2003 Can't connect
  ✓ recovered · feed 返來啦（last seen 0m ago）

Dedup：上次 alert < 6 小時前 skip，避免重複轟炸。
State 存喺 data/.healthcheck_state.json。launchd 用 StartInterval=900（15 分鐘）。
"""

import json
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


STATE_FILE = Path(settings.BASE_DIR) / 'data' / '.healthcheck_state.json'
THRESHOLD_MIN = 60       # 超過 60 分鐘冇 ingest 就 alert
DEDUP_HOURS = 6          # 兩個 alert 之間最少 6 小時
CHROME_PROC_ALERT = 30   # chromium headless 超過呢個數就 alert（正常 backfill run 6-12 個）


def _read_state():
    if not STATE_FILE.exists():
        return {'last_alert_at': 0.0, 'last_alerted': False}
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {'last_alert_at': 0.0, 'last_alerted': False}


def _write_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))


def _send(message):
    """Push 落 push.connie.hk 用舊 src/notifier.py 嘅 HMAC 簽名。"""
    import sys as _sys
    src_dir = Path(settings.BASE_DIR) / 'src'
    if str(src_dir) not in _sys.path:
        _sys.path.insert(0, str(src_dir))
    from notifier import send_push
    secret = (settings.PLANE_HISTORY.get('push') or {}).get('secret')
    if not secret:
        return None
    return send_push(secret, message)


def _last_sighting_age_min():
    """Query MAX(seen_at) 計幾耐之前 ingest 過。回 (age_minutes, db_error_string)。"""
    try:
        with connection.cursor() as cur:
            cur.execute('SELECT MAX(seen_at) FROM sightings_raw')
            row = cur.fetchone()
    except Exception as e:
        return None, str(e)[:120]
    if not row or not row[0]:
        return None, 'no rows'
    try:
        last_dt = datetime.fromisoformat(row[0])
    except ValueError:
        return None, 'invalid timestamp'
    age_sec = (datetime.now(timezone.utc) - last_dt).total_seconds()
    return max(0, int(age_sec / 60)), None


def _chromium_count():
    """數 chrome-headless-shell process；回 (count, total_rss_mb)，攞唔到回 (None, None)。"""
    try:
        out = subprocess.check_output(['ps', '-axo', 'rss=,comm='], text=True)
        rss = [int(line.split(None, 1)[0]) for line in out.splitlines()
               if 'chrome-headless-shell' in line]
        return len(rss), sum(rss) / 1024
    except Exception:
        return None, None


def _probe_tar1090():
    """Fetch tar1090 source URL；回 (status, detail_or_None)。"""
    url = (settings.PLANE_HISTORY.get('source') or {}).get('aircraft_json_url')
    if not url:
        return 'config-missing', 'no aircraft_json_url 喺 config.json'
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = resp.read(2048).decode('utf-8', errors='replace')
        try:
            json.loads(data)
            return 'ok', None
        except json.JSONDecodeError:
            return 'bad-json', data[:80]
    except urllib.error.HTTPError as e:
        return str(e.code), e.reason
    except Exception as e:
        return 'unreachable', str(e)[:80]


class Command(BaseCommand):
    help = 'Push 通知如果 ingest feed 停咗超過 1 小時。'

    def handle(self, *args, **opts):
        age_min, db_err = _last_sighting_age_min()
        state = _read_state()
        now_t = time.time()

        # Chromium 堆積 check：browser_bulk_backfill 漏 page 嗰陣 renderer 會
        # 愈積愈多（試過 59 個食 5.6GB），獨立 dedup，唔影響下面 feed alert。
        # 跌返落正常水平就靜靜哋 reset flag——每次 run 完自然回落，唔使 push recovery
        n_chrome, chrome_mb = _chromium_count()
        if n_chrome is not None:
            if n_chrome > CHROME_PROC_ALERT:
                hours_since = (now_t - state.get('chromium_last_alert_at', 0.0)) / 3600
                # 同 feed alert 一樣用 flag + dedup：回落過先算新事故，
                # 新事故即刻嗌；持續超標就 6 小時先嗌一次
                if not state.get('chromium_alerted', False) or hours_since >= DEDUP_HOURS:
                    push_status = _send(f'ALERT · chromium headless {n_chrome} 個 process（{chrome_mb:.0f} MB）· 疑似 backfill renderer 堆積')
                    # 送到（2xx）先 mark，否則下個 cycle（15 分鐘後）重試
                    if push_status and 200 <= push_status < 300:
                        state.update({'chromium_last_alert_at': now_t, 'chromium_alerted': True})
                        _write_state(state)
                    else:
                        self.stdout.write(self.style.ERROR(f'chromium alert push failed (status={push_status})'))
                self.stdout.write(self.style.WARNING(f'chromium {n_chrome} procs ({chrome_mb:.0f} MB) > {CHROME_PROC_ALERT}'))
            else:
                if state.get('chromium_alerted', False):
                    state['chromium_alerted'] = False
                    _write_state(state)
                self.stdout.write(f'chromium ok ({n_chrome} procs)')

        # Recovery case：之前 alert 過，而家 feed 返來
        if state['last_alerted'] and age_min is not None and age_min < THRESHOLD_MIN:
            _send(f'✓ recovered · feed 返來啦（last seen {age_min}m ago）')
            state.update({'last_alert_at': now_t, 'last_alerted': False})
            _write_state(state)
            self.stdout.write(self.style.SUCCESS(f'recovered, last seen {age_min}m ago'))
            return

        # 正常 case：唔需要 alert
        if db_err is None and age_min is not None and age_min < THRESHOLD_MIN:
            self.stdout.write(f'ok, last seen {age_min}m ago')
            return

        # 需要 alert：dedup check
        hours_since_last = (now_t - state['last_alert_at']) / 3600
        if state['last_alerted'] and hours_since_last < DEDUP_HOURS:
            self.stdout.write(f'skip alert (last alert {hours_since_last:.1f}h ago, dedup={DEDUP_HOURS}h)')
            return

        # Diagnose：DB 同 tar1090 各跑一次
        db_status = 'down: ' + db_err if db_err else 'ok'
        tar_status, tar_detail = _probe_tar1090()
        tar_str = tar_status + (f' ({tar_detail})' if tar_detail and tar_status != 'ok' else '')

        if age_min is None:
            age_str = 'unknown'
        else:
            age_str = f'{age_min}m'

        msg = f'ALERT · feed 無 update {age_str} · DB {db_status} · tar1090 {tar_str}'
        status = _send(msg)
        # 同 chromium alert 一樣：送到（2xx）先 mark，失敗下個 cycle 重試
        if status and 200 <= status < 300:
            state.update({'last_alert_at': now_t, 'last_alerted': True})
            _write_state(state)
            self.stdout.write(self.style.WARNING(f'alert sent: {msg} (push status={status})'))
        else:
            self.stdout.write(self.style.ERROR(f'alert push failed: {msg} (push status={status})'))
