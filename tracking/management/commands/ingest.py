"""manage.py ingest — 抓 tar1090 aircraft.json 寫入 sightings_raw，
順手做 HKE / Hong Kong Express callsign push detection。

舊 src/ingest.py 直接 reuse。launchd plist 用 StartInterval=60。
"""

from django.core.management.base import BaseCommand

from tracking.services.runner import run_script


class Command(BaseCommand):
    help = '抓一次 tar1090 aircraft.json 寫入 sightings_raw + HKE push detection。'

    def handle(self, *args, **opts):
        r = run_script('ingest.py', ['--once'], timeout=30)
        if r.returncode != 0:
            self.stderr.write(self.style.ERROR(f'ingest.py rc={r.returncode}'))
