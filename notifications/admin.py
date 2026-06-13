from django.contrib import admin

from .models import PushRule


@admin.register(PushRule)
class PushRuleAdmin(admin.ModelAdmin):
    list_display = ('label', 'callsign_prefixes', 'enabled')
    list_editable = ('enabled',)
    search_fields = ('label', 'callsign_prefixes')
