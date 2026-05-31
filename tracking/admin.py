"""Tracking admin — sightings / passes / route snapshots 全部 read-only。

Sighting / Pass / RouteSnapshot 喺 admin 唔可以 add / delete / edit；
咁就算 sleep 緊撳錯掣都唔會 corrupt ingest pipeline 嘅資料。
"""

from django.contrib import admin

from .models import Pass, RouteSnapshot, Sighting


class _ReadOnlyAdminMixin:
    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Sighting)
class SightingAdmin(_ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('seen_at', 'icao', 'flight', 'alt_baro', 'gs', 'receiver_name')
    list_filter = ('receiver_name', 'source_name', 'category')
    search_fields = ('icao', 'flight')
    ordering = ('-seen_at',)
    list_per_page = 50


@admin.register(Pass)
class PassAdmin(_ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        'pass_id', 'pass_date', 'icao', 'flight', 'operator',
        'from_airport', 'to_airport', 'first_seen', 'samples', 'max_alt_baro',
    )
    list_filter = ('pass_date', 'country', 'operator')
    search_fields = ('icao', 'flight', 'operator', 'from_airport', 'to_airport')
    ordering = ('-last_seen',)
    list_per_page = 50


@admin.register(RouteSnapshot)
class RouteSnapshotAdmin(_ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('snapshot_id', 'icao', 'flight', 'from_airport', 'to_airport', 'observed_at')
    search_fields = ('icao', 'flight', 'from_airport', 'to_airport')
    ordering = ('-observed_at',)
    list_per_page = 50
