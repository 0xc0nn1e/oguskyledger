"""manage.py healthcheck_alert — 監察 ingest feed，超過 1 小時冇 update push 通知。

Diagnose 兩條 path：
  1. MySQL 連到 → SQL `SELECT 1` 正常
  2. tar1090 source URL 通 → HTTP 200 + JSON parse 到

另外獨立監察兩樣嘢（各有自己 dedup，唔影響 feed alert）：
  - chromium headless process 堆積
  - gunicorn WORKER TIMEOUT（有 request hang 爆 --timeout）

Push message 例：
  ALERT · feed 無 update 87m · DB ok · tar1090 404
  ALERT · feed 無 update 65m · DB down: 2003 Can't connect
  ALERT · gunicorn worker timeout ×2（pid 1024, 1025）· 有 request hang 爆 30s…
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
ERROR_LOG = Path(settings.BASE_DIR) / 'data' / 'django-error.log'
THRESHOLD_MIN = 60       # 超過 60 分鐘冇 ingest 就 alert
DEDUP_HOURS = 6          # 兩個 alert 之間最少 6 小時
CHROME_PROC_ALERT = 30   # chromium headless 超過呢個數就 alert（正常 backfill run 6-12 個）
# Worker timeout 係「事件」唔係「水平」，用短 dedup：一次事故通常爆幾單
# （2026-08-13 十七分鐘內五單），1 小時夠收埋一個 burst，又唔會蓋走下一單事故。
WORKER_TIMEOUT_DEDUP_HOURS = 1


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


def _scan_worker_timeouts(state):
    """由上次 offset 掃 django-error.log 新增部分，數 gunicorn WORKER TIMEOUT。

    回 (count, sample_pids, new_offset)。用 byte offset 而唔係每次讀成個檔，
    因為個 log 冇 rotation，只會愈嚟愈大。

    背景：`WORKER TIMEOUT` 係 arbiter 見到 worker 超過 --timeout 冇 heartbeat 先出，
    之後 3-5 秒補一發 SIGKILL。要同 2026-06-13 嗰批「冇 WORKER TIMEOUT 前置」嘅
    SIGKILL 分開睇——嗰批係 macOS _scproxy fork-safety，已經由 plist 兩個 env 修好。
    所以呢度只數 WORKER TIMEOUT，唔數 SIGKILL，否則會捉錯已修好嘅舊問題。
    """
    try:
        size = ERROR_LOG.stat().st_size
    except OSError:
        return 0, [], state.get('error_log_offset')

    offset = state.get('error_log_offset')
    # 第一次跑：淨係記低而家個位，唔好就住兩個月歷史狂 push。
    if offset is None:
        return 0, [], size
    # 檔案縮咗（有人清過 / 將來加 rotation）→ 由頭再嚟
    if offset > size:
        offset = 0

    try:
        with ERROR_LOG.open('r', encoding='utf-8', errors='replace') as f:
            f.seek(offset)
            new_text = f.read()
            new_offset = f.tell()
    except OSError:
        return 0, [], offset

    hits = [ln for ln in new_text.splitlines() if 'WORKER TIMEOUT' in ln]
    pids = []
    for ln in hits:
        _, _, tail = ln.partition('pid:')
        pid = tail.partition(')')[0].strip()
        if pid:
            pids.append(pid)
    return len(hits), pids, new_offset


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

        # Gunicorn worker timeout check：有 request hang 足 --timeout（30s）就 alert。
        # 獨立 dedup，同下面 feed alert 冇關；一定要喺 feed 嗰堆 early return 之前跑。
        n_timeouts, timeout_pids, new_offset = _scan_worker_timeouts(state)
        commit_offset = True
        if n_timeouts:
            hours_since = (now_t - state.get('worker_timeout_last_alert_at', 0.0)) / 3600
            if hours_since >= WORKER_TIMEOUT_DEDUP_HOURS:
                pid_str = ', '.join(timeout_pids[:5]) or '?'
                push_status = _send(
                    f'ALERT · gunicorn worker timeout ×{n_timeouts}（pid {pid_str}）'
                    f'· 有 request hang 爆 30s，查 django-access.log 尾二欄（微秒）')
                if push_status and 200 <= push_status < 300:
                    state['worker_timeout_last_alert_at'] = now_t
                else:
                    # 送唔到就唔好推進 offset，下個 cycle（15 分鐘後）連呢批一齊重試
                    commit_offset = False
                    self.stdout.write(self.style.ERROR(
                        f'worker timeout alert push failed (status={push_status})'))
            self.stdout.write(self.style.WARNING(f'worker timeout ×{n_timeouts} 新增'))
        else:
            self.stdout.write('worker timeout 冇新增')
        if commit_offset and new_offset is not None and new_offset != state.get('error_log_offset'):
            state['error_log_offset'] = new_offset
        _write_state(state)

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
