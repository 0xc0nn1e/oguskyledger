"""manage.py enrich_registry — 用 flight prefix + country fallback 補 registry。

舊 src/enrich_registry.py 直接 reuse。pipeline 入面行 ingest 之後、bulk backfill 之前。
"""

from django.core.management.base import BaseCommand

from tracking.services.runner import run_script


class Command(BaseCommand):
    help = '用 prefix/country fallback 補 aircraft_registry_cache。'

    def handle(self, *args, **opts):
        r = run_script('enrich_registry.py', timeout=60)
        if r.returncode != 0:
            self.stderr.write(self.style.ERROR(f'enrich_registry.py rc={r.returncode}'))
