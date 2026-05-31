"""manage.py ingest_pipeline — sequential 5-step pipeline，跟舊 run_ingest.sh 嘅 order。

launchd 用 StartInterval=60 trigger。Build_passes 永遠跑喺 ingest 之後，
避免 race condition（兩個 60s plist 唔保證 order）。

Step：
1. ingest.py --once          — 抓 tar1090 + HKE push
2. enrich_registry.py        — prefix/country fallback
3. backfill_reg_browser.py   — quick browser reg backfill（容錯，rc 非零繼續）
4. enrich_operator.py        — operator by flight prefix
5. build_passes.py           — 20 min gap aggregate
"""

import time

from django.core.management.base import BaseCommand

from tracking.services.runner import run_script


PIPELINE = [
    ('ingest.py', ['--once'], 30, False),                  # script, args, timeout, lenient
    ('enrich_registry.py', None, 60, False),
    ('backfill_reg_browser.py', None, 180, True),          # 容錯
    ('enrich_operator.py', None, 60, False),
    ('build_passes.py', None, 120, False),
]


class Command(BaseCommand):
    help = '跑成個 60 秒 pipeline：ingest → enrich → build_passes（sequential）。'

    def handle(self, *args, **opts):
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
