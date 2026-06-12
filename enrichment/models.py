"""Enrichment models — registry cache（每架機嘅補完資料）。

`hke_notified_at` 一定要喺 admin readonly：reset 返 NULL 會令今日重複 push。
"""

from django.db import models


class AircraftRegistryCache(models.Model):
    """`aircraft_registry_cache`：每個 ICAO 一條，補完 registration / country / type / operator。"""

    icao = models.CharField(primary_key=True, max_length=16)
    registration = models.CharField(max_length=32, blank=True, null=True)
    country = models.CharField(max_length=64, blank=True, null=True)
    lookup_source = models.CharField(max_length=64, blank=True, null=True)
    last_lookup_at = models.CharField(max_length=40)
    operator = models.CharField(max_length=255, blank=True, null=True)
    operator_country = models.CharField(max_length=64, blank=True, null=True)
    aircraft_type = models.CharField(max_length=16, blank=True, null=True)
    fr24_id = models.CharField(max_length=64, blank=True, null=True)
    from_airport = models.CharField(max_length=64, blank=True, null=True)
    to_airport = models.CharField(max_length=64, blank=True, null=True)
    hke_notified_at = models.CharField(max_length=40, blank=True, null=True)
    # HKE push 失敗重試 state（per JST 日封頂重試，成功 / 跨日 reset）
    hke_push_failed_at = models.CharField(max_length=40, blank=True, null=True)
    hke_push_fail_count = models.IntegerField(default=0)

    class Meta:
        db_table = 'aircraft_registry_cache'
        verbose_name = '機體資料'
        verbose_name_plural = '機體資料'

    def __str__(self):
        return f'{self.icao} {self.registration or "—"}'
