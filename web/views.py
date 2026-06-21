"""web app views — HTML page render only。JSON 走 api/ app。

每個 page extend PlaneHistoryBaseMixin 注入 base.html JS 需要嘅 t_dict_json + lang_code。
今輪 task #19 第一輪：所有 page 都 stub TemplateView，extend base shell，純 placeholder。
詳細內容（recent contacts table / stats panels / live map / coverage radar / aircraft detail / 等）
下輪 task #19 fill：每個 page 一個 sprint，順手抽 page-specific CSS / JS 去 static/。

aircraft 用 DetailView（DRF style），其他純 TemplateView。
"""

import json
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import connection
from django.shortcuts import redirect
from django.views.generic import TemplateView

from notifications.models import PushLog, PushRule

from ._legacy_strings import STRINGS
from .models import SiteConfig

_JST = timezone(timedelta(hours=9))


def _fmt_jst(ts):
    """UTC ISO string → 'MM-DD HH:MM:SS'（JST）for push-log 顯示。"""
    try:
        return datetime.fromisoformat(ts).astimezone(_JST).strftime('%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return ts or '—'


class PlaneHistoryBaseMixin:
    """所有 page view 行呢個 mixin 攞 nav strings + lang，注入畀 base.html inline JS。

    過渡期：由 `_legacy_strings.STRINGS`（舊 web_app.py copy 過嚟）載入。
    Task #22 換 Django gettext 之後可以剝走 mixin 同 `_legacy_strings.py`。
    """

    def get_lang(self):
        # 同 context processor 共用一條判定鏈，普通 page 同 auth page 永遠一致
        from .context_processors import resolve_lang
        return resolve_lang(self.request)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        lang = self.get_lang()
        ctx['lang_code'] = lang
        ctx['t_dict_json'] = json.dumps(STRINGS[lang], ensure_ascii=False)
        ctx['page_size'] = SiteConfig.load().page_size  # server 分頁每頁數（admin 可改）
        return ctx


class HomeView(PlaneHistoryBaseMixin, TemplateView):
    template_name = 'web/home.html'


class StatsView(PlaneHistoryBaseMixin, TemplateView):
    template_name = 'web/stats.html'


class DetailsView(PlaneHistoryBaseMixin, TemplateView):
    template_name = 'web/details.html'


class MapView(PlaneHistoryBaseMixin, TemplateView):
    template_name = 'web/map.html'


class AircraftDetailView(PlaneHistoryBaseMixin, TemplateView):
    """單機歷史 page — 純 client-side render。

    舊 URL `/aircraft?icao=<hex>` redirect 入 `/aircraft/<hex>/`（web/urls.py legacy）。
    本身唔做 DB query；JS 由 location.pathname 攞 ICAO，fetch `/api/aircraft` + `/api/aircraft/track`。
    """
    template_name = 'web/aircraft.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['icao'] = self.kwargs.get('icao', '').lower()
        # 路線地圖以接收機做中心（config.json receiver.lat/lon，街區級就夠，
        # 會出現喺公開 HTML，唔好放精確 GPS）；冇設定就由 JS fallback fitBounds
        rx = settings.PLANE_HISTORY.get('receiver') or {}
        lat, lon = rx.get('lat'), rx.get('lon')
        if lat is not None and lon is not None:
            ctx['rx_center_json'] = json.dumps([lat, lon])
        return ctx


class AboutView(PlaneHistoryBaseMixin, TemplateView):
    template_name = 'web/about.html'


class DashboardView(LoginRequiredMixin, PlaneHistoryBaseMixin, TemplateView):
    """Owner 系統儀表板 — login 後先睇到（未登入彈去 /accounts/login/）。

    本身唔做 query；JS poll `/api/dashboard`（30 秒）攞 launchd / feed / DB / chrome /
    log 狀態。資料層喺 tracking.services.queries.query_dashboard。
    """
    template_name = 'web/dashboard.html'


class PushLogView(LoginRequiredMixin, PlaneHistoryBaseMixin, TemplateView):
    """Push 通知記錄 — login 後先睇到。列最近 200 筆（最新喺上），畀人 debug
    「到底有冇 push 到」。資料寫入喺 src/ingest.py / browser_bulk_backfill.py
    嘅 push hook（src/push_rules.py log_push）。"""
    template_name = 'web/push_log.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['rows'] = [{
            't': _fmt_jst(r.pushed_at), 'label': r.label, 'callsign': r.callsign,
            'reg': r.registration, 'route': r.route, 'ok': r.ok, 'status': r.http_status,
        } for r in PushLog.objects.order_by('-id')[:200]]
        ctx['T'] = STRINGS[self.get_lang()]
        return ctx


class WatchlistView(LoginRequiredMixin, PlaneHistoryBaseMixin, TemplateView):
    """我 watch 緊嘅機 — login 後先睇到。watch = 一條 match_type=icao 嘅 push rule
    （aircraft 頁個 ⭐ 掣加），呢度 list 晒 + 每架最近一筆 pass 狀態。"""
    template_name = 'web/watchlist.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rows = []
        with connection.cursor() as cur:
            for rule in PushRule.objects.filter(match_type='icao', enabled=True).order_by('id'):
                for icao_u in rule.prefix_list():
                    icao = icao_u.lower()
                    cur.execute('SELECT registration, operator FROM aircraft_registry_cache WHERE icao = %s', [icao])
                    reg_row = cur.fetchone()
                    cur.execute(
                        'SELECT last_seen, flight, from_airport, to_airport FROM aircraft_passes '
                        'WHERE icao = %s ORDER BY last_seen DESC LIMIT 1', [icao])
                    p = cur.fetchone()
                    route = f'{p[2]} › {p[3]}' if p and p[2] and p[3] else None
                    rows.append({
                        'icao': icao,
                        'reg': (reg_row[0] if reg_row else None) or None,
                        'operator': (reg_row[1] if reg_row else None) or None,
                        'last_pass': _fmt_jst(p[0]) if p else None,
                        'last_flight': (p[1] if p else None) or None,
                        'route': route,
                    })
        ctx['rows'] = rows
        ctx['T'] = STRINGS[self.get_lang()]
        return ctx

    def post(self, request, *args, **kwargs):
        # unwatch：由 rule 移走呢個 icao（多 icao rule 都 work；同 /api/watch off 一致）
        if request.POST.get('action') == 'unwatch':
            PushRule.unwatch_icao(request.POST.get('icao') or '')
        return redirect('watchlist')


class PushRulesView(LoginRequiredMixin, PlaneHistoryBaseMixin, TemplateView):
    """Push 規則設定 — login 後先入到（LoginRequiredMixin 未登入彈去 /accounts/login/）。

    GET：列出 rule + on/off + 加 / 刪。POST 三個 action：
      save   — 套用 enabled checkbox（成批）
      add    — 加新 rule（label + callsign 前綴）
      delete — 刪一條 rule
    """
    template_name = 'web/push_rules.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['rules'] = list(PushRule.objects.order_by('id'))
        ctx['heli_cluster_enabled'] = SiteConfig.load().heli_cluster_enabled  # 系統 alert on/off（直升機群集）
        ctx['T'] = STRINGS[self.get_lang()]
        return ctx

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        if action == 'add':
            label = (request.POST.get('label') or '').strip()
            prefixes = (request.POST.get('callsign_prefixes') or '').strip().upper()
            match_type = (request.POST.get('match_type') or 'callsign').strip().lower()
            if match_type not in {'callsign', 'icao', 'registration', 'type', 'route', 'country'}:
                match_type = 'callsign'
            if label and prefixes:
                PushRule.objects.create(
                    label=label, callsign_prefixes=prefixes, match_type=match_type, enabled=True)
        elif action == 'delete':
            rid = (request.POST.get('id') or '').strip()
            if rid.isdigit():
                PushRule.objects.filter(id=int(rid)).delete()
        elif action == 'save':
            enabled_ids = {x for x in request.POST.getlist('enabled') if x.isdigit()}
            for rule in PushRule.objects.all():
                want = str(rule.id) in enabled_ids
                if rule.enabled != want:
                    rule.enabled = want
                    rule.save(update_fields=['enabled'])
        elif action == 'system':
            # 系統 alert on/off（直升機群集 push）——source of truth 仍係 SiteConfig，
            # 門檻（架數 / 範圍 / 冷卻）喺 /admin/web/siteconfig/ 調，呢度淨係 on/off。
            cfg = SiteConfig.load()
            cfg.heli_cluster_enabled = bool(request.POST.get('heli_cluster_enabled'))
            cfg.save()
        return redirect('push-rules')
