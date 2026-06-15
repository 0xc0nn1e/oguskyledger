"""web app URL routing — page render only。

舊 `/aircraft?icao=<hex>` → 用 RedirectView 一層轉 `/aircraft/<hex>/`，保持舊書籤 / push.connie.hk
link 唔死。Frontend JS link 直接生 `/aircraft/<hex>/` 新 URL。
"""

from django.http import HttpResponseRedirect
from django.urls import path

from . import views


def _aircraft_legacy_redirect(request):
    """舊 `/aircraft?icao=<hex>` → 301 redirect 入 `/aircraft/<hex>/`。"""
    icao = (request.GET.get('icao') or '').strip().lower()
    if not icao:
        return HttpResponseRedirect('/')
    return HttpResponseRedirect(f'/aircraft/{icao}/')


urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),
    path('stats/', views.StatsView.as_view(), name='stats'),
    path('details/', views.DetailsView.as_view(), name='details'),
    path('map/', views.MapView.as_view(), name='map'),
    path('about/', views.AboutView.as_view(), name='about'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('push-rules/', views.PushRulesView.as_view(), name='push-rules'),
    path('push-log/', views.PushLogView.as_view(), name='push-log'),
    path('watchlist/', views.WatchlistView.as_view(), name='watchlist'),
    path('aircraft/<str:icao>/', views.AircraftDetailView.as_view(), name='aircraft-detail'),
    # /coverage 已 cut，舊 link 永久 301 → home
    path('coverage/', lambda r: HttpResponseRedirect('/'), name='coverage-legacy'),
    # legacy compat：舊 ?icao= query string 入面接住 redirect
    path('aircraft', _aircraft_legacy_redirect, name='aircraft-legacy'),
    # /discover 整合咗落 /stats，永久 301
    path('discover/', lambda r: HttpResponseRedirect('/stats/'), name='discover-legacy'),
    # 舊 auth path → Django built-in /accounts/* compat redirect
    # 舊 push.connie.hk / 書籤 / SSL proxy config 唔使改
    path('login', lambda r: HttpResponseRedirect('/accounts/login/' + ('?next=' + r.GET['next'] if r.GET.get('next') else '')), name='login-legacy'),
    path('logout', lambda r: HttpResponseRedirect('/accounts/logout/'), name='logout-legacy'),
    path('account', lambda r: HttpResponseRedirect('/accounts/password_change/'), name='account-legacy'),
    path('account/password', lambda r: HttpResponseRedirect('/accounts/password_change/'), name='account-password-legacy'),
]
