"""web app views — HTML page render only。JSON 走 api/ app。

每個 page extend PlaneHistoryBaseMixin 注入 base.html JS 需要嘅 t_dict_json + lang_code。
今輪 task #19 第一輪：所有 page 都 stub TemplateView，extend base shell，純 placeholder。
詳細內容（recent contacts table / stats panels / live map / coverage radar / aircraft detail / 等）
下輪 task #19 fill：每個 page 一個 sprint，順手抽 page-specific CSS / JS 去 static/。

aircraft 用 DetailView（DRF style），其他純 TemplateView。
"""

import json

from django.conf import settings
from django.views.generic import TemplateView

from ._legacy_strings import LANGS, STRINGS


class PlaneHistoryBaseMixin:
    """所有 page view 行呢個 mixin 攞 nav strings + lang，注入畀 base.html inline JS。

    過渡期：由 `_legacy_strings.STRINGS`（舊 web_app.py copy 過嚟）載入。
    Task #22 換 Django gettext 之後可以剝走 mixin 同 `_legacy_strings.py`。
    """

    def get_lang(self):
        lang = self.request.COOKIES.get('lang', '')
        return lang if lang in LANGS else 'hk'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        lang = self.get_lang()
        ctx['lang_code'] = lang
        ctx['t_dict_json'] = json.dumps(STRINGS[lang], ensure_ascii=False)
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
