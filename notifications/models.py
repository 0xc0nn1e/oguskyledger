"""Push 規則 model。

每條 rule = 一個 operator（label）+ 一組 callsign 前綴（逗號分隔，例如 HKE,UO）。
enabled 控制 on/off。callsign 中咗任何一條 enabled rule 嘅前綴就 push
（per-機-per-日 dedup，state 仲係喺 aircraft_registry_cache.hke_notified_at）。

src/ingest.py 同 src/browser_bulk_backfill.py 直接讀 push_rules 表（src/push_rules.py
helper），所以呢個 model 同 init_db.py 嘅 DDL 要對得返。
"""

from django.db import models


class PushRule(models.Model):
    label = models.CharField(max_length=64, help_text='顯示名，會用喺 push message 開頭')
    callsign_prefixes = models.CharField(max_length=128, help_text='逗號分隔嘅 match 值，例如 callsign 用 HKE,UO；type 用 A380；icao 用 hex')
    match_type = models.CharField(
        max_length=16, default='callsign',
        help_text='match 邊個欄：callsign / icao / registration / type / route / country',
    )
    enabled = models.BooleanField(default=True)

    class Meta:
        db_table = 'push_rules'
        verbose_name = 'Push 規則'
        verbose_name_plural = 'Push 規則'

    def __str__(self):
        return f'{self.label} ({self.callsign_prefixes})'

    def prefix_list(self):
        return [p.strip().upper() for p in self.callsign_prefixes.split(',') if p.strip()]
