"""Tracking models — sightings / passes / route snapshots。

設計重點：
- `db_table` 對返舊 table 名（`sightings_raw` / `aircraft_passes` / `aircraft_route_snapshots`），
  唔 wipe ~50 日歷史資料。
- `seen_at` / `first_seen` / `last_seen` / `observed_at` 暫保留 `CharField(max_length=40)`
  兼容舊 ISO string（UTC `+00:00` 同 JST `+09:00` 都會出現）。第二期 migration
  再 ALTER 做 DateTimeField，今期唔做避免大規模 backfill。
- ORM filter 用 `__gte` / `__lte` 對住 `.isoformat()` 嘅 string；ISO 8601 lexicographic
  compare 同 chronological 一致（前提：時區一致），所以暫時 work。
"""

from django.db import models


class Sighting(models.Model):
    """`sightings_raw`：每次抓 tar1090 寫入一條 row。"""

    seen_at = models.CharField(max_length=40, db_index=True)
    receiver_name = models.CharField(max_length=128)
    source_name = models.CharField(max_length=128)
    icao = models.CharField(max_length=16, db_index=True)
    flight = models.CharField(max_length=32, blank=True, null=True)
    category = models.CharField(max_length=16, blank=True, null=True)
    alt_baro = models.FloatField(blank=True, null=True)
    alt_geom = models.FloatField(blank=True, null=True)
    gs = models.FloatField(blank=True, null=True)
    track = models.FloatField(blank=True, null=True)
    lat = models.FloatField(blank=True, null=True)
    lon = models.FloatField(blank=True, null=True)
    # `raw_json` 係 LONGTEXT，唔係 MySQL native JSON，所以用 TextField 而唔係 JSONField，
    # 避免 `__contains` lookup 行錯
    raw_json = models.TextField()

    class Meta:
        db_table = 'sightings_raw'
        indexes = [
            models.Index(fields=['icao', 'seen_at'], name='idx_sightings_icao_seen_at'),
        ]

    def __str__(self):
        return f'{self.icao}@{self.seen_at}'


class Pass(models.Model):
    """`aircraft_passes`：每 20 分鐘 gap 聚合一個 pass。"""

    pass_id = models.AutoField(primary_key=True)
    pass_date = models.CharField(max_length=16, db_index=True)  # 'YYYY-MM-DD' (JST)
    icao = models.CharField(max_length=16, db_index=True)
    flight = models.CharField(max_length=32, blank=True, null=True)
    operator = models.CharField(max_length=255, blank=True, null=True)
    country = models.CharField(max_length=64, blank=True, null=True)
    category = models.CharField(max_length=16, blank=True, null=True)
    first_seen = models.CharField(max_length=40)
    last_seen = models.CharField(max_length=40)
    samples = models.IntegerField()
    min_alt_baro = models.FloatField(blank=True, null=True)
    max_alt_baro = models.FloatField(blank=True, null=True)
    min_gs = models.FloatField(blank=True, null=True)
    max_gs = models.FloatField(blank=True, null=True)
    from_airport = models.CharField(max_length=64, blank=True, null=True)
    to_airport = models.CharField(max_length=64, blank=True, null=True)

    class Meta:
        db_table = 'aircraft_passes'
        indexes = [
            models.Index(fields=['icao', 'pass_date'], name='idx_passes_icao_date'),
            # incremental build_passes 每 cycle `DELETE … WHERE last_seen >= W`，
            # 冇呢個 index 就 full-scan 成個（永遠增長嘅）aircraft_passes
            models.Index(fields=['last_seen'], name='idx_passes_last_seen'),
        ]

    def __str__(self):
        return f'{self.icao} {self.pass_date} ({self.flight or "—"})'


class RouteSnapshot(models.Model):
    """`aircraft_route_snapshots`：每次 FR24 攞到 from/to + ADS-B callsign 時記低。"""

    snapshot_id = models.AutoField(primary_key=True)
    icao = models.CharField(max_length=16)
    flight = models.CharField(max_length=32)
    from_airport = models.CharField(max_length=64, blank=True, null=True)
    to_airport = models.CharField(max_length=64, blank=True, null=True)
    observed_at = models.CharField(max_length=40)

    class Meta:
        db_table = 'aircraft_route_snapshots'
        indexes = [
            models.Index(fields=['icao', 'flight', 'observed_at'], name='idx_snap_icao_flight'),
        ]

    def __str__(self):
        return f'{self.icao}/{self.flight} {self.from_airport}>{self.to_airport}'
