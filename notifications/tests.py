"""notifications 純函數 test —— 全部 `SimpleTestCase`，唔掂 DB。

`PushRule(...)` 淨係起 instance 唔 save，所以唔會連 DB。
點解一定要 SimpleTestCase：見 `tracking/tests.py` 個 module docstring。
"""

from django.test import SimpleTestCase

from notifications.models import PushRule


def _rule(prefixes):
    """未 save 嘅 PushRule，淨係為咗行 prefix_list()。"""
    return PushRule(label='t', callsign_prefixes=prefixes, match_type='callsign')


class PrefixListTests(SimpleTestCase):
    """`PushRule.prefix_list()` —— push 比對同 watchlist 都靠佢拆前綴。"""

    def test_逗號拆開兼去空格(self):
        self.assertEqual(_rule('HKE, CPA ,ANA').prefix_list(), ['HKE', 'CPA', 'ANA'])

    def test_一律轉大楷(self):
        # /api/watch 寫入嗰陣已經 upper()，但 admin 可以打細楷落去，
        # 比對嗰邊淨係用大楷，所以 prefix_list 一定要自己 normalise。
        self.assertEqual(_rule('hke,780cb0').prefix_list(), ['HKE', '780CB0'])

    def test_單一值(self):
        self.assertEqual(_rule('HKE').prefix_list(), ['HKE'])

    def test_空值回空_list(self):
        for empty in ('', '   ', ',', ' , , '):
            self.assertEqual(_rule(empty).prefix_list(), [], msg=f'{empty!r} 應該回空 list')

    def test_尾隨逗號唔會整出空字串(self):
        # 出過空字串就大鑊：'' 會 match 到所有 callsign，變成無差別 push。
        self.assertEqual(_rule('HKE,').prefix_list(), ['HKE'])
        self.assertNotIn('', _rule('HKE,,CPA,').prefix_list())
