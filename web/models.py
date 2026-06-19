from django.db import models


class SiteConfig(models.Model):
    """單例網站設定（owner 喺 Django admin 改）。而家淨係放長表每頁顯示數。

    用 pk=1 單例：save() 強制 pk=1，load() 回 first() or 預設 instance（唔 write-on-read）。
    """
    page_size = models.PositiveIntegerField(
        default=50, help_text='長表每頁顯示幾多 row（通過履歷 / details 等 server 分頁）')

    # 直升機群集事故 alert 門檻（多架直升機聚埋 = 可能有事故；map 橫額 + push 共用）
    heli_cluster_enabled = models.BooleanField(
        default=True, help_text='開唔開直升機群集 alert（地圖橫額 + push）')
    heli_cluster_min = models.PositiveIntegerField(
        default=4, help_text='最少幾架直升機喺範圍內先當 cluster')
    heli_cluster_radius_km = models.PositiveIntegerField(
        default=8, help_text='聚集判定半徑（km）')
    heli_cluster_cooldown_min = models.PositiveIntegerField(
        default=30, help_text='同一 cluster 幾多分鐘內唔再 push（dedup，防 spam）')

    class Meta:
        verbose_name = '網站設定'
        verbose_name_plural = '網站設定'

    def __str__(self):
        return f'每頁 {self.page_size}'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        return cls.objects.first() or cls()
