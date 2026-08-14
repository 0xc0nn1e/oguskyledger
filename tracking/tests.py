"""tracking 純函數 test —— 全部 `SimpleTestCase`，唔掂 DB。

**點解一定要 SimpleTestCase**：`SimpleTestCase.databases` 係空 set，而 Django 個
`DiscoverRunner.get_databases(suite)` 只會 setup 個 suite 真正用到嘅 alias。全部係
SimpleTestCase 嘅話，`manage.py test` **完全唔會 create test database** —— 呢部機
跑緊 live MySQL，亦唔想 `plane_history` user 要有 CREATE 權限。
跑嘅時候 output 應該見到 `Skipping setup of unused database(s)`。

一改成 `TestCase` 就會即刻試 create `test_plane_history`，唔好改。
"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from tracking.management.commands import healthcheck_alert
from tracking.services import queries


class CategoryGroupTests(SimpleTestCase):
    """`queries.category_group()` —— /details 個 CAT filter 靠佢分組。"""

    def test_每個已分配_code_都對到自己個_group(self):
        for group, codes in queries.CATEGORY_GROUPS.items():
            for code in codes:
                self.assertEqual(queries.category_group(code), group, msg=f'{code} 應該係 {group}')

    def test_細楷同前後空格都認得(self):
        self.assertEqual(queries.category_group('a7'), 'heli')
        self.assertEqual(queries.category_group('  A7 '), 'heli')

    def test_冇資料一律當_unknown(self):
        for bad in (None, '', '   ', 'A0', 'B0', 'C0', 'B5', 'D1', 'ZZ'):
            self.assertEqual(queries.category_group(bad), 'unknown', msg=f'{bad!r} 應該係 unknown')

    def test_C3_係障礙物唔係地面車(self):
        # queries.py 特別註明過：C3 = Point Obstacle（繫留氣球 / 塔），
        # 唔可以同 C1/C2 地面車混埋。呢個 case 專登守住嗰個註解。
        self.assertEqual(queries.category_group('C3'), 'obstacle')
        self.assertNotIn('C3', queries.CATEGORY_GROUPS['ground'])


class CategoryTableInvariantTests(SimpleTestCase):
    """`CATEGORY_GROUPS` ↔ `_CATEGORY_CODE_TO_GROUP` 嘅結構不變量。"""

    def test_冇_code_出現喺多過一個_group(self):
        seen = {}
        for group, codes in queries.CATEGORY_GROUPS.items():
            for code in codes:
                self.assertNotIn(code, seen, msg=f'{code} 同時喺 {seen.get(code)} 同 {group}')
                seen[code] = group

    def test_反查表同正表一致(self):
        expected = {c: g for g, codes in queries.CATEGORY_GROUPS.items() for c in codes}
        self.assertEqual(queries._CATEGORY_CODE_TO_GROUP, expected)

    def test_unknown_唔可以列_code(self):
        # 'unknown' 係「認唔到」嘅接收桶，一列 code 就會令 category_group 嘅
        # fallback 語意同 /details 個 HAVING NOT IN 查詢對唔上。
        self.assertEqual(queries.CATEGORY_GROUPS['unknown'], ())


class JstDayBoundsTests(SimpleTestCase):
    """`queries.jst_day_utc_bounds()` —— JST 日 [00:00,24:00) 換做 UTC ISO 範圍。"""

    def test_一般日子(self):
        self.assertEqual(
            queries.jst_day_utc_bounds('2026-08-14'),
            ('2026-08-13T15:00:00+00:00', '2026-08-14T15:00:00+00:00'),
        )

    def test_跨月(self):
        start, end = queries.jst_day_utc_bounds('2026-09-01')
        self.assertEqual(start, '2026-08-31T15:00:00+00:00')
        self.assertEqual(end, '2026-09-01T15:00:00+00:00')

    def test_跨年(self):
        start, _ = queries.jst_day_utc_bounds('2027-01-01')
        self.assertEqual(start, '2026-12-31T15:00:00+00:00')

    def test_閏年_2_月_29(self):
        start, _ = queries.jst_day_utc_bounds('2028-03-01')
        self.assertEqual(start, '2028-02-29T15:00:00+00:00')

    def test_範圍剛好_24_小時且首尾相接(self):
        # 連續兩日嘅 end / start 一定要一樣，否則 /details 會漏 row 或者重覆計。
        _, end_a = queries.jst_day_utc_bounds('2026-08-14')
        start_b, _ = queries.jst_day_utc_bounds('2026-08-15')
        self.assertEqual(end_a, start_b)

    def test_壞日子會_raise(self):
        for bad in ('2026-13-01', 'not-a-date', ''):
            with self.assertRaises(ValueError):
                queries.jst_day_utc_bounds(bad)


class FmtTsTests(SimpleTestCase):
    """`queries.fmt_ts()` —— UTC ISO → JST 顯示字串。"""

    def test_冇值回一劃(self):
        self.assertEqual(queries.fmt_ts(None), '-')
        self.assertEqual(queries.fmt_ts(''), '-')

    def test_UTC_轉_JST_加_9_個鐘(self):
        self.assertEqual(
            queries.fmt_ts('2026-08-13T20:15:25+00:00'),
            '2026-08-14 05:15:25 JST',
        )

    def test_已經係_JST_嘅_offset_唔會再加(self):
        self.assertEqual(
            queries.fmt_ts('2026-08-14T05:15:25+09:00'),
            '2026-08-14 05:15:25 JST',
        )

    def test_壞字串會_raise(self):
        # 同 web.views._fmt_jst 特登唔同：嗰邊會吞低錯誤回原值，呢邊唔會。
        # 邊個 caller 用邊個要清楚，所以將呢個差異釘死。
        with self.assertRaises(ValueError):
            queries.fmt_ts('唔係時間')


class AllowedSortsTests(SimpleTestCase):
    """`queries.ALLOWED_SORTS` —— 直接插落 ORDER BY，係防 SQL injection 嘅命門。"""

    def test_有_last_seen_做_fallback(self):
        # query_rows() 行 ALLOWED_SORTS.get(key, ALLOWED_SORTS['last_seen'])，
        # 冇咗呢個 key 就會 KeyError，任何未知 sort 參數都會 500。
        self.assertIn('last_seen', queries.ALLOWED_SORTS)

    def test_每個值都係安全嘅_ORDER_BY_片段(self):
        import re
        safe = re.compile(r'^[A-Za-z_]+ (ASC|DESC)(, [A-Za-z_]+ (ASC|DESC))*$')
        for key, frag in queries.ALLOWED_SORTS.items():
            self.assertRegex(frag, safe, msg=f'{key} 個 ORDER BY 片段唔安全: {frag!r}')


class WorkerTimeoutScanTests(SimpleTestCase):
    """`healthcheck_alert._scan_worker_timeouts()` —— 掃 gunicorn error log。"""

    TIMEOUT_LINE = '[2026-08-13 11:07:54 +0900] [883] [CRITICAL] WORKER TIMEOUT (pid:1025)\n'
    SIGKILL_LINE = ('[2026-08-13 11:07:59 +0900] [883] [ERROR] '
                    'Worker (pid:1025) was sent SIGKILL! Perhaps out of memory?\n')

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.log = Path(self.tmpdir.name) / 'django-error.log'
        self.log.write_text(self.TIMEOUT_LINE)
        patcher = mock.patch.object(healthcheck_alert, 'ERROR_LOG', self.log)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_第一次跑唔會就住歷史狂嗌(self):
        # 冇 offset = 未監察過。個 log 有兩個月歷史，一嗌就係幾十個 push。
        n, pids, offset = healthcheck_alert._scan_worker_timeouts({})
        self.assertEqual((n, pids), (0, []))
        self.assertEqual(offset, self.log.stat().st_size)

    def test_冇新增就唔嗌(self):
        state = {'error_log_offset': self.log.stat().st_size}
        self.assertEqual(healthcheck_alert._scan_worker_timeouts(state)[:2], (0, []))

    def test_只數_WORKER_TIMEOUT_唔數_SIGKILL(self):
        # 2026-06-13 嗰批 SIGKILL 冇 WORKER TIMEOUT 前置，係 macOS _scproxy
        # fork-safety，已經由 web plist 兩個 env 修好。數埋就會捉錯已修好嘅舊問題。
        state = {'error_log_offset': self.log.stat().st_size}
        with self.log.open('a') as f:
            f.write(self.TIMEOUT_LINE.replace('1025', '1024'))
            f.write(self.SIGKILL_LINE)
        n, pids, _ = healthcheck_alert._scan_worker_timeouts(state)
        self.assertEqual((n, pids), (1, ['1024']))

    def test_log_被清空唔會爆(self):
        state = {'error_log_offset': 999999}
        self.log.write_text('')
        n, pids, offset = healthcheck_alert._scan_worker_timeouts(state)
        self.assertEqual((n, pids, offset), (0, [], 0))

    def test_log_唔存在唔會爆(self):
        with mock.patch.object(healthcheck_alert, 'ERROR_LOG', Path('/nope/missing.log')):
            self.assertEqual(
                healthcheck_alert._scan_worker_timeouts({'error_log_offset': 5}),
                (0, [], 5),
            )


class BootTimeTests(SimpleTestCase):
    """`queries._BOOT_AT` —— /about 同 /health 嘅 uptime 由佢計。"""

    def test_係_timezone_aware_UTC(self):
        # naive datetime 減 aware datetime 會 TypeError，令 /about 500。
        self.assertIsNotNone(queries._BOOT_AT.tzinfo)
        self.assertEqual(queries._BOOT_AT.utcoffset(), timezone.utc.utcoffset(None))
        self.assertLessEqual(queries._BOOT_AT, datetime.now(timezone.utc))
