"""manage.py build_passes — 用 20 分鐘 gap 聚合 sightings_raw → aircraft_passes，
順手由 aircraft_route_snapshots match per-pass FROM/TO。

舊 src/build_passes.py 直接 reuse。launchd plist 用 StartInterval=60（pipeline 末段）。
"""

from django.core.management.base import BaseCommand

from tracking.services.runner import run_script


class Command(BaseCommand):
    help = '聚合 sightings_raw → aircraft_passes（20 分鐘 gap）+ per-pass FROM/TO snapshot。'

    def handle(self, *args, **opts):
        r = run_script('build_passes.py', timeout=120)
        if r.returncode != 0:
            self.stderr.write(self.style.ERROR(f'build_passes.py rc={r.returncode}'))
