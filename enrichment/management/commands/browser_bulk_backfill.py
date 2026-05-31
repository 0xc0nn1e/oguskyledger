"""manage.py browser_bulk_backfill — Playwright + Chromium 大量補 registration /
aircraft_type / operator / from_airport / to_airport，順手做 HKE push（reg 補到先 push）。

舊 src/browser_bulk_backfill.py 直接 reuse。launchd plist 用 StartInterval=180。
Playwright 環境變數（PATH / PLAYWRIGHT_BROWSERS_PATH）要喺 plist 顯式 set，
否則喺 launchd context 下搵唔到 Chromium。
"""

from django.core.management.base import BaseCommand

from tracking.services.runner import run_script


class Command(BaseCommand):
    help = 'Playwright 大量補 registry cache（reg / type / operator / from / to / FR24 ID）。'

    def handle(self, *args, **opts):
        # Playwright bulk run 一般 1-2 分鐘，但 backlog 多時可能 5-7 分鐘。
        # launchd 同 label 唔會並行起第二個 instance，所以即使長過 StartInterval 180s 都 safe。
        # timeout=None 即係無限（畀 subprocess.run），唔 kill 中途。
        r = run_script('browser_bulk_backfill.py', timeout=None)
        if r.returncode != 0:
            self.stderr.write(self.style.ERROR(f'browser_bulk_backfill.py rc={r.returncode}'))
