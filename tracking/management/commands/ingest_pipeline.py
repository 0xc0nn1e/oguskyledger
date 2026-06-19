"""manage.py ingest_pipeline — sequential pipeline，跟舊 run_ingest.sh 嘅 order。

launchd 用 StartInterval=60 trigger。Build_passes 永遠跑喺 ingest 之後，
避免 race condition（兩個 60s plist 唔保證 order）。

Step：
1. ingest.py --once          — 抓 tar1090 + HKE push
2. enrich_registry.py        — prefix/country fallback
3. backfill_reg_browser.py   — quick browser reg backfill（容錯，rc 非零繼續）
4. enrich_operator.py        — operator by flight prefix
5. build_passes.py           — 20 min gap aggregate
6. prune_raw.py              — retention，清舊 sightings_raw（容錯）

跑完再做直升機群集事故 alert push（query_live 即時快照 → detect → cooldown dedup → push）。
"""

import sys
import time
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection

from tracking.services.queries import query_live
from tracking.services.runner import run_script


PIPELINE = [
    ('ingest.py', ['--once'], 30, False),                  # script, args, timeout, lenient
    ('enrich_registry.py', None, 60, False),
    ('backfill_reg_browser.py', None, 180, True),          # 容錯
    ('enrich_operator.py', None, 60, False),
    ('build_passes.py', None, 120, False),
    ('prune_raw.py', None, 60, True),                      # 容錯：retention，prune 舊 sightings_raw，失敗唔 stop pipeline
]

HELI_LABEL = 'HELI-CLUSTER'   # push_log label，同時做 cluster push 嘅 dedup key


class Command(BaseCommand):
    help = '跑成個 60 秒 pipeline：ingest → enrich → build_passes（sequential）+ 直升機群集 push。'

    def handle(self, *args, **opts):
        self._run_pipeline()
        # 唔理 pipeline 有冇中途 stop，都試做 cluster push（只靠即時 live 快照，獨立於上面 step）。
        self._heli_cluster_push()

    def _run_pipeline(self):
        for script, script_args, timeout, lenient in PIPELINE:
            start = time.monotonic()
            try:
                r = run_script(script, script_args, timeout=timeout)
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'{script} crashed: {e!r}'))
                if not lenient:
                    return
                continue
            duration = time.monotonic() - start
            if r.returncode != 0:
                tag = 'WARNING' if lenient else 'ERROR'
                fn = self.style.WARNING if lenient else self.style.ERROR
                self.stderr.write(fn(f'{tag} {script} rc={r.returncode} duration={duration:.1f}s'))
                if not lenient:
                    return  # 非容錯 step 失敗就 stop pipeline（同舊 run_ingest.sh `set -e` 邏輯一致）

    def _heli_cluster_push(self):
        """直升機群集 → push（cooldown 內 dedup，借 push_log，零新表）。

        任何例外都吞咗、淨係出 warning，唔好搞冧 pipeline。
        """
        try:
            from web.models import SiteConfig
            cfg = SiteConfig.load()
            secret = (settings.PLANE_HISTORY.get('push') or {}).get('secret')
            if not secret:
                return
            # query_live 已經按 SiteConfig 計好 heli_cluster（含 radius_km）；disabled 會回 active=False。
            hc = query_live().get('heli_cluster') or {}
            if not hc.get('active'):
                return
            # dedup：cooldown 分鐘內已 push 過 HELI-CLUSTER 就唔再 push。
            # （interval job 每 cycle 都係 fresh process，所以一定要靠 DB 持久 dedup，唔可以用記憶體。）
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT pushed_at FROM push_log WHERE label = %s ORDER BY id DESC LIMIT 1",
                    [HELI_LABEL],
                )
                row = cur.fetchone()
            if row and row[0]:
                try:
                    last = datetime.fromisoformat(row[0])
                    if datetime.now(timezone.utc) - last < timedelta(minutes=cfg.heli_cluster_cooldown_min):
                        return  # 仲喺 cooldown，skip
                except (ValueError, TypeError):
                    pass  # pushed_at 格式怪 → 當冇 dedup 紀錄，照 push

            n = hc.get('count')
            center = hc.get('center') or [0.0, 0.0]
            lat, lon = float(center[0]), float(center[1])
            msg = f'⚠ {n} 架直升機喺 ({lat:.2f}, {lon:.2f}) 附近聚集 — 可能有事故'

            # notifier 純 subprocess（openssl + curl），無 DB import，唔會撞 runner 講嗰個 PyMySQL 問題。
            src_dir = str(settings.BASE_DIR / 'src')
            if src_dir not in sys.path:
                sys.path.insert(0, src_dir)
            from notifier import send_push
            status = send_push(secret, msg)

            with connection.cursor() as cur:
                cur.execute(
                    "INSERT INTO push_log (pushed_at, icao, callsign, registration, label, route, http_status, ok) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    [datetime.now(timezone.utc).isoformat(), None, f'{n}機', None, HELI_LABEL,
                     f'{lat:.2f},{lon:.2f}', status, 1 if (status and 200 <= status < 300) else 0],
                )
            self.stdout.write(f'heli cluster push：{n} 機 @ ({lat:.2f},{lon:.2f}) status={status}')
        except Exception as e:
            self.stderr.write(self.style.WARNING(f'heli_cluster_push 出錯（唔影響 pipeline）: {e!r}'))
