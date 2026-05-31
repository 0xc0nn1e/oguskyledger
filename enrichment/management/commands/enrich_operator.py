"""manage.py enrich_operator — 用 flight prefix 補 operator + operator_country。

舊 src/enrich_operator.py 直接 reuse。pipeline 入面跑喺 bulk backfill 之後。
唔會用 NULL 覆蓋 browser / FR24 補回嘅 operator。
"""

from django.core.management.base import BaseCommand

from tracking.services.runner import run_script


class Command(BaseCommand):
    help = '用 flight prefix 推斷 operator + operator_country。'

    def handle(self, *args, **opts):
        r = run_script('enrich_operator.py', timeout=60)
        if r.returncode != 0:
            self.stderr.write(self.style.ERROR(f'enrich_operator.py rc={r.returncode}'))
