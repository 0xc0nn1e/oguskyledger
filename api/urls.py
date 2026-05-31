"""api app URL routing — DRF endpoints。

每個 path 對返舊 src/web_app.py 嘅 /api/* route。Frontend 唔需要改 fetch URL。
"""

from django.urls import path

from . import views

urlpatterns = [
    path('health', views.health, name='api-health'),
    path('me', views.me, name='api-me'),
    path('about', views.about, name='api-about'),
    path('stats', views.stats, name='api-stats'),
    path('discover', views.discover, name='api-discover'),
    path('live', views.live, name='api-live'),
    path('aircraft', views.aircraft, name='api-aircraft'),
    path('aircraft/track', views.aircraft_track, name='api-aircraft-track'),
    path('coverage', views.coverage, name='api-coverage'),
    path('today', views.today, name='api-today'),
    path('summary', views.summary, name='api-summary'),
]
