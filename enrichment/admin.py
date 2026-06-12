"""Enrichment admin — registry cache 部分 editable，部分 readonly。

`operator` / `aircraft_type` 容許 manual fix-up（例如 FR24 lookup 偶然錯）。
`hke_notified_at` 一定 readonly：如果 reset 返 NULL，今日 ingest cycle 會
重新 trigger HKE push，制造 duplicate notification。
"""

from django.contrib import admin

from .models import AircraftRegistryCache


@admin.register(AircraftRegistryCache)
class AircraftRegistryCacheAdmin(admin.ModelAdmin):
    list_display = (
        'icao', 'registration', 'aircraft_type', 'operator', 'country',
        'from_airport', 'to_airport', 'hke_notified_at',
    )
    list_filter = ('country', 'operator', 'aircraft_type', 'lookup_source')
    search_fields = ('icao', 'registration', 'operator', 'aircraft_type')
    ordering = ('icao',)
    list_per_page = 50

    # icao 係 PK + ingest pipeline 認得，唔可以改；同 hke_notified_at 防意外 re-push
    readonly_fields = ('icao', 'last_lookup_at', 'lookup_source', 'fr24_id', 'hke_notified_at',
                       'hke_push_failed_at', 'hke_push_fail_count')

    fieldsets = (
        ('機體 identifier', {
            'fields': ('icao', 'registration', 'aircraft_type'),
        }),
        ('營運', {
            'fields': ('operator', 'operator_country', 'country'),
        }),
        ('航線（最近一次 FR24 / FR24 search 結果）', {
            'fields': ('from_airport', 'to_airport', 'fr24_id'),
        }),
        ('Lookup metadata', {
            'fields': ('lookup_source', 'last_lookup_at', 'hke_notified_at',
                       'hke_push_failed_at', 'hke_push_fail_count'),
            'description': '`hke_notified_at` readonly：reset 返 NULL 會令今日重複 push HKE notification。'
                           '`hke_push_*` 係重試 state，亂改會擾亂每日封頂邏輯。',
        }),
    )

    def has_delete_permission(self, request, obj=None):
        # Sighting 入面有 ICAO 但 cache delete 咗會令所有 enriched view 突然「reset」，
        # 同 ingest cycle 會即時補返一行新 cache row。手動 delete 唔安全，直接 disable。
        return False
