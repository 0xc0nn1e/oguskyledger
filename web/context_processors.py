"""所有 template render 都注入 lang_code + t_dict_json。

PlaneHistoryBaseMixin 只 cover 自己啲 view；django.contrib.auth 嗰啲
（login / password_change）冇 mixin，base.html 嘅 lang switch 會永遠
highlight default hk。呢個 context processor 令任何 view（包括 auth）
都攞到一致嘅 lang context。View 自己 set 嘅同名 key 會優先，所以同
mixin 並存冇衝突。
"""

import json

from ._legacy_strings import LANGS, STRINGS

# Django locale → legacy lang code（跟 base.html 嘅 LANG_TO_DJANGO 反向）
DJANGO_TO_LANG = {'ja': 'jp', 'zh-hant': 'hk', 'en': 'en'}


def resolve_lang(request):
    """全站唯一嘅 lang 判定鏈：lang cookie > Django locale > hk。

    Mixin（普通 page）同 context processor（auth page）都行呢條，
    保證任何 page 嘅著燈 / T dict / {% trans %} 內文一致。
    """
    code = request.COOKIES.get('lang', '')
    if code in LANGS:
        return code
    # 冇 legacy cookie：跟 LocaleMiddleware 判定咗嘅 locale
    # （django_language cookie / Accept-Language），令制同內文一致
    return DJANGO_TO_LANG.get(getattr(request, 'LANGUAGE_CODE', ''), 'hk')


def lang(request):
    code = resolve_lang(request)
    return {
        'lang_code': code,
        't_dict_json': json.dumps(STRINGS[code], ensure_ascii=False),
    }
