"""Legacy lang cookie 橋接。

site 嘅 lang switch 制（同 lang_code context processor）以 `lang` cookie
（jp/hk/en）為準；Django LocaleMiddleware / {% trans %} 就睇 `django_language`。
兩個 cookie 任何一邊甩咗或者唔同步（舊 browser 狀態、其中一個先過期），
就會出「制著一種語言、內文另一種」。

呢個 middleware 喺 LocaleMiddleware 之前行：`lang` cookie 存在而有效，
就**無條件**將佢映射做當次 request 嘅 django_language——`lang` 係唯一
權威，兩個 cookie 永遠唔會各自為政。冇 `lang` 先輪到 django_language /
Accept-Language（lang_code context processor 嗰邊都係同一優先次序）。
"""

LANG_TO_DJANGO = {'jp': 'ja', 'hk': 'zh-hant', 'en': 'en'}


class LegacyLangCookieMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        mapped = LANG_TO_DJANGO.get(request.COOKIES.get('lang', ''))
        if mapped:
            request.COOKIES['django_language'] = mapped
        return self.get_response(request)
