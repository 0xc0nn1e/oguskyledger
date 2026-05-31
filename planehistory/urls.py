"""Top-level URL routing。

`/admin/` → Django admin
`/api/`   → DRF viewsets + custom endpoints（`api` app）
`/accounts/` → Django built-in auth (login / logout / password change)
`/i18n/`  → Django built-in `set_language` view
其餘 → web app (home / stats / details / map / coverage / aircraft / about)
"""

from django.contrib import admin
from django.urls import include, path
from django.views.i18n import JavaScriptCatalog

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
    path('i18n/', include('django.conf.urls.i18n')),
    # JS i18n catalog：browser 由呢度攞 gettext() function + msgstr table。
    # 對應當前 request 嘅 `django_language` cookie / Accept-Language 自動揀 lang。
    path('jsi18n/', JavaScriptCatalog.as_view(), name='javascript-catalog'),
    path('', include('web.urls')),
]
