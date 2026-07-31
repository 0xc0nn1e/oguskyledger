"""預先計算 `/stats/` 需要嘅兩組 API payload。"""

from django.core.management.base import BaseCommand

from tracking.services.stats_cache import CACHE_PATH, refresh_stats_cache


class Command(BaseCommand):
    help = '重新計算 /api/stats 同 /api/discover，原子寫入持久 cache。'

    def handle(self, *args, **options):
        snapshot = refresh_stats_cache()
        self.stdout.write(self.style.SUCCESS(
            f"統計 cache 已更新：{CACHE_PATH}（{snapshot['duration_seconds']:.3f}s）"
        ))
