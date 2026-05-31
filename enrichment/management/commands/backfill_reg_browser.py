"""manage.py backfill_reg_browser — quick browser-based REG backfill。

舊 src/backfill_reg_browser.py 直接 reuse。pipeline 入面係容錯一步：rc 非零照 continue。
"""

from django.core.management.base import BaseCommand

from tracking.services.runner import run_script


class Command(BaseCommand):
    help = '快速 browser REG backfill（容錯，失敗都唔停 pipeline）。'

    def handle(self, *args, **opts):
        r = run_script('backfill_reg_browser.py', timeout=180)
        if r.returncode != 0:
            # 容錯：write warning 但唔 raise
            self.stderr.write(self.style.WARNING(f'backfill_reg_browser.py rc={r.returncode} (continuing)'))
