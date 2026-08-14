"""web 純函數 test —— 全部 `SimpleTestCase`，唔掂 DB。

點解一定要 SimpleTestCase：見 `tracking/tests.py` 個 module docstring。
"""

from django.test import SimpleTestCase

from web.views import _fmt_jst


class FmtJstTests(SimpleTestCase):
    """`web.views._fmt_jst()` —— push log 表格顯示用，容錯版時間格式化。"""

    def test_UTC_轉_JST_加_9_個鐘(self):
        self.assertEqual(_fmt_jst('2026-08-13T20:15:25+00:00'), '08-14 05:15:25')

    def test_已經係_JST_offset_唔會再加(self):
        self.assertEqual(_fmt_jst('2026-08-14T05:15:25+09:00'), '08-14 05:15:25')

    def test_冇值回長劃(self):
        self.assertEqual(_fmt_jst(None), '—')
        self.assertEqual(_fmt_jst(''), '—')

    def test_壞字串原樣回_唔會爆(self):
        # 呢個係 push log 頁嘅 render path，一筆爛資料唔應該炸親成頁。
        # 同 queries.fmt_ts 特登相反（嗰邊會 raise），差異喺兩邊 test 都釘死咗。
        self.assertEqual(_fmt_jst('唔係時間'), '唔係時間')
        self.assertEqual(_fmt_jst('2026-13-99'), '2026-13-99')

    def test_唔會靜靜哋當咗_UTC(self):
        # 用兩個代表同一刻但寫法唔同嘅 offset，結果一定要一樣，
        # 否則即係邊度漏咗 astimezone。
        self.assertEqual(
            _fmt_jst('2026-08-13T20:15:25+00:00'),
            _fmt_jst('2026-08-13T22:15:25+02:00'),
        )
