"""Top-level URL routing。

`/admin/` → Django admin
`/api/`   → DRF viewsets + custom endpoints（`api` app）
`/accounts/` → Django built-in auth (login / logout / password change)
`/i18n/`  → Django built-in `set_language` view
其餘 → web app (home / stats / details / map / coverage / aircraft / about)
"""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView
from django.views.i18n import JavaScriptCatalog

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
    path('i18n/', include('django.conf.urls.i18n')),
    # JS i18n catalog：browser 由呢度攞 gettext() function + msgstr table。
    # 對應當前 request 嘅 `django_language` cookie / Accept-Language 自動揀 lang。
    path('jsi18n/', JavaScriptCatalog.as_view(), name='javascript-catalog'),
    # PWA service worker：要喺 root（/sw.js）serve 先 control 到全站 scope。
    path('sw.js', TemplateView.as_view(template_name='sw.js', content_type='application/javascript'), name='sw'),
    # PWA manifest：經 Django route serve 確保 application/manifest+json（whitenoise 會出 octet-stream）。
    path('manifest.webmanifest', TemplateView.as_view(template_name='manifest.webmanifest', content_type='application/manifest+json'), name='manifest'),
    path('', include('web.urls')),
]
