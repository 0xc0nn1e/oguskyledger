from django.contrib import admin

from .models import SiteConfig


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'page_size')

    def has_add_permission(self, request):
        # 單例：已有一筆就唔准再加
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
