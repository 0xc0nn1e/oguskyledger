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

    @classmethod
    def unwatch_icao(cls, icao):
        """由所有 match_type=icao rule 移走呢個 icao（rule 變空就刪）。

        watchlist unwatch 同 /api/watch off 共用：唔可以淨係刪 prefix_list==[icao]
        嘅單值 rule，否則多 icao 嘅 rule 撳 unwatch 會冇反應（user-visible state bug）。
        回有冇真係郁過。
        """
        iu = (icao or '').strip().upper()
        if not iu:
            return False
        changed = False
        for r in cls.objects.filter(match_type='icao'):
            pl = r.prefix_list()
            if iu not in pl:
                continue
            remaining = [p for p in pl if p != iu]
            if remaining:
                r.callsign_prefixes = ','.join(remaining)
                r.save(update_fields=['callsign_prefixes'])
            else:
                r.delete()
            changed = True
        return changed


class PushLog(models.Model):
    """每次 push 寫一筆（成敗都寫）。src/ingest.py / src/browser_bulk_backfill.py 經
    src/push_rules.py 嘅 log_push() 直接 INSERT，/push-log/ 頁經呢個 model 讀。"""
    pushed_at = models.CharField(max_length=40)
    icao = models.CharField(max_length=16, blank=True, null=True)
    callsign = models.CharField(max_length=32, blank=True, null=True)
    registration = models.CharField(max_length=32, blank=True, null=True)
    label = models.CharField(max_length=64, blank=True, null=True)
    route = models.CharField(max_length=128, blank=True, null=True)
    http_status = models.IntegerField(blank=True, null=True)
    ok = models.BooleanField(default=False)

    class Meta:
        db_table = 'push_log'
        verbose_name = 'Push 記錄'
        verbose_name_plural = 'Push 記錄'

    def __str__(self):
        return f'{self.pushed_at} {self.label} {self.registration} ok={self.ok}'
