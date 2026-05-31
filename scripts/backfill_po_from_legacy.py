"""一次性腳本：由 web/_legacy_strings.STRINGS 自動生 .po files。

舊 dict 結構：STRINGS[lang][key] = translation
新 gettext：msgid（key/源字串） → msgstr（lang-specific 翻譯）

策略：英文版做 msgid（gettext convention：用源字串做 key）；
日 + HK 翻譯就用 STRINGS['jp'] / STRINGS['hk'] 對應同 key 嘅 value。
如果 EN 版本同 key 一樣（即 key 本身就係 fallback），就用 KEY 自己做 msgid。

一次 run 完之後，呢個檔可以 archive；之後修改翻譯直接改 .po。
"""

import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'planehistory.settings')
django.setup()

from web._legacy_strings import STRINGS

BASE = Path(__file__).resolve().parent.parent
LOCALE = BASE / 'locale'

LANG_DIR = {
    'ja': LOCALE / 'ja' / 'LC_MESSAGES',
    'zh_Hant': LOCALE / 'zh_Hant' / 'LC_MESSAGES',
}


def _po_escape(s):
    return s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')


def write_po(lang_code, source_dict, target_dict):
    """Write locale/<lang_code>/LC_MESSAGES/django.po。

    msgid 用 EN string（gettext 慣例）。同 key 對應嘅 source/target lang
    value 入做 msgstr。
    """
    out_dir = LANG_DIR[lang_code]
    out_dir.mkdir(parents=True, exist_ok=True)
    po_path = out_dir / 'django.po'

    lines = [
        'msgid ""',
        'msgstr ""',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Language: ' + lang_code + '\\n"',
        '',
    ]

    en = STRINGS['en']
    # 用 EN 字串做 msgid。若 EN 字串重複，gettext 只 keep 一條。
    # List values（e.g. stats_heatmap_wd 7 個 weekday）每個 element 一個 entry。
    seen_msgids = set()

    def emit(msgid, msgstr, ref):
        if not msgid or msgid in seen_msgids:
            return
        seen_msgids.add(msgid)
        lines.append('#: web/_legacy_strings.py:' + ref)
        lines.append('msgid "' + _po_escape(msgid) + '"')
        lines.append('msgstr "' + _po_escape(msgstr or '') + '"')
        lines.append('')

    for key, en_val in en.items():
        target_val = target_dict.get(key, '')
        if isinstance(en_val, list):
            # 同步 list：assume target 同樣係 list 且長度一致
            target_list = target_val if isinstance(target_val, list) else []
            for i, item in enumerate(en_val):
                tgt = target_list[i] if i < len(target_list) else ''
                emit(str(item), str(tgt), f'{key}[{i}]')
        else:
            emit(str(en_val) if en_val else key, str(target_val), key)

    po_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f'  wrote {po_path}: {len(seen_msgids)} entries')


def main():
    print('Generating .po from web/_legacy_strings.STRINGS...')
    write_po('ja', STRINGS['en'], STRINGS['jp'])
    write_po('zh_Hant', STRINGS['en'], STRINGS['hk'])
    print('Done. Run: django-admin compilemessages -l ja -l zh_Hant')


if __name__ == '__main__':
    main()
