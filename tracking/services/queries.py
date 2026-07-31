"""Read query helpers — 對應舊 src/web_app.py 嘅 query_* 函數。

過渡期：用 Django connection cursor + raw SQL，SQL 直接由舊 web_app.py copy 過嚟。
下輪 refactor：逐個 swap 做 ORM `annotate()` / `aggregate()`，當 learning。

公約：每個 query 回 dict / list[dict]，畀 DRF / view 直接 `JsonResponse(data)`。
"""

import json
import re
import subprocess
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

from django.conf import settings
from django.db import connection

from .incidents import detect_heli_cluster


JST = timezone(timedelta(hours=9))


# /details page sort 用嘅 ORDER BY whitelist，唔可以畀 user 直接傳 SQL。
ALLOWED_SORTS = {
    'last_seen': 'last_seen DESC',
    'country': 'country ASC, operator ASC, last_seen DESC',
    'operator': 'operator ASC, country ASC, last_seen DESC',
    'type': 'aircraft_type ASC, operator ASC, last_seen DESC',
}


# ADS-B emitter category code → 語意分組（/details 個 CAT filter 用），跟 DO-260B。
# 排序即係 dropdown 出現嘅次序。下面列晒所有「已分配」嘅 code，唔好淨係列常見嗰幾個：
# 漏咗嘅合法 code 會跌落 'unknown'，即係將有明確意思嘅機標成「未分類」。
# 特別注意 C3 係 Point Obstacle（繫留氣球 / 塔），唔係地面車輛，要同 C1/C2 分開。
# 'unknown' 冇列 code：淨係接住明確「冇資料」嘅 A0/B0/C0、reserved（B5/C6/C7/D*）同空字串。
CATEGORY_GROUPS = {
    'plane': ('A1', 'A2', 'A3', 'A4', 'A5', 'A6'),
    'heli': ('A7',),
    'glider': ('B1',),
    'balloon': ('B2',),
    'parachute': ('B3',),
    'ultralight': ('B4',),
    'drone': ('B6',),
    'space': ('B7',),
    'ground': ('C1', 'C2'),
    'obstacle': ('C3', 'C4', 'C5'),
    'unknown': (),
}

# code → group 反查表（大寫 key）
_CATEGORY_CODE_TO_GROUP = {
    code: group for group, codes in CATEGORY_GROUPS.items() for code in codes
}


def category_group(code):
    """ADS-B category code → group key。認唔到（含 '' / None / A0）一律 'unknown'。"""
    return _CATEGORY_CODE_TO_GROUP.get((code or '').strip().upper(), 'unknown')


def fmt_ts(ts):
    """ISO UTC string → 'YYYY-MM-DD HH:MM:SS JST' for display。"""
    if not ts:
        return '-'
    dt = datetime.fromisoformat(ts)
    return dt.astimezone(JST).strftime('%Y-%m-%d %H:%M:%S JST')


def jst_day_utc_bounds(day_str):
    """JST day [00:00, 24:00) 對應 UTC (day-1) 15:00 → day 15:00。

    seen_at 存 ISO UTC string，可以直接做 lexicographic 範圍比較。
    """
    d = date.fromisoformat(day_str)
    start = (datetime.combine(d, datetime.min.time()) - timedelta(hours=9)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
    end = (datetime.combine(d, datetime.min.time()) + timedelta(hours=15)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
    return start, end

# Module-level：process boot 時間，畀 /about / /health 用。
_BOOT_AT = datetime.now(timezone.utc)

# Module-level cache：process-local，restart 即清，唔需要 Redis。
_LIVE_CACHE = {'at': 0.0, 'data': None}
_LIVE_TTL = 1.0  # 秒：N 個 client polling 都最多每秒打 tar1090 + DB 一次

# 由 settings.PLANE_HISTORY 讀 tar1090 source URL
_SOURCE_URL = (settings.PLANE_HISTORY.get('source') or {}).get('aircraft_json_url')


def _dict_cursor(cur):
    """Django cursor → list[dict]，模擬 PyMySQL dict_cursor 嘅 fetchall()。"""
    columns = [c[0] for c in cur.description]
    return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]


def _dict_one(cur):
    """Django cursor → dict | None，模擬 fetchone()。"""
    row = cur.fetchone()
    if row is None:
        return None
    columns = [c[0] for c in cur.description]
    return dict(zip(columns, row, strict=True))


def _receiver_snapshot():
    """共用：最後一筆 sample 幾耐之前（秒）同今日 pass 數。會 raise 如果 DB connect 唔到。"""
    today_jst = datetime.now(JST).strftime('%Y-%m-%d')
    with connection.cursor() as cur:
        cur.execute('SELECT MAX(seen_at) AS ts FROM sightings_raw')
        row = _dict_one(cur)
        cur.execute('SELECT COUNT(*) AS c FROM aircraft_passes WHERE pass_date = %s', [today_jst])
        records_today = _dict_one(cur)['c']

    last_secs = None
    if row and row['ts']:
        try:
            last_dt = datetime.fromisoformat(row['ts'])
            last_secs = max(0, int((datetime.now(timezone.utc) - last_dt).total_seconds()))
        except ValueError:
            last_secs = None
    return last_secs, records_today


def _feed_health(last_secs):
    """pipeline 每 60 秒一 cycle：180 秒內當正常、900 秒內當遲、再耐就當停。"""
    if last_secs is None:
        return 'down'
    if last_secs <= 180:
        return 'ok'
    if last_secs <= 900:
        return 'stale'
    return 'down'


def query_about():
    """畀 /api/about 用，回 receiver / feed 健康狀態 + uptime + records_today。"""
    last_secs, records_today = _receiver_snapshot()
    uptime_secs = (datetime.now(timezone.utc) - _BOOT_AT).total_seconds()
    return {
        'receiver': 'Oku Home RX',
        'source': 'Pi / dump1090 / readsb',
        'uptime_secs': int(uptime_secs),
        'last_update_secs': last_secs,
        'feed_health': _feed_health(last_secs),
        'records_today': records_today,
    }


def query_health():
    """畀 /api/health 用，回 (payload, http_status)。

    Service 健唔健康 = API 起到 + DB 連到。Receiver 遲 / 停當 degraded，唔當 503。
    """
    db_ok = True
    last_secs = None
    records_today = None
    try:
        last_secs, records_today = _receiver_snapshot()
    except Exception:
        db_ok = False

    receiver = _feed_health(last_secs) if db_ok else 'down'
    healthy = db_ok
    payload = {
        'status': 'ok' if healthy else 'error',
        'api': 'ok',
        'db': 'ok' if db_ok else 'down',
        'receiver': receiver,
        'receiver_last_seen_secs': last_secs,
        'records_today': records_today,
        'uptime_secs': int((datetime.now(timezone.utc) - _BOOT_AT).total_seconds()),
    }
    return payload, (200 if healthy else 503)


def _scrub(line):
    """Log 行出 web 之前清走 /Users/<user>/ 路徑（CLAUDE.md：唔可以暴露用戶名 / home 路徑）。"""
    return re.sub(r'/Users/[^/\s]+/', '~/', line)


# Dashboard 睇嘅 launchd job（同 src/healthcheck.py 一致）
_DASH_JOBS = ['ingest', 'backfill', 'healthcheck', 'stats-cache', 'web']
# 出畀 dashboard 嘅 error log（只 basename，唔出絕對路徑；StandardErrorPath 先有 traceback）
_DASH_LOGS = [
    'django-ingest.err', 'django-backfill.err', 'django-stats-cache.err',
    'django-web.err', 'django-error.log',
]


def query_dashboard():
    """Owner 系統儀表板資料 —— api/views.py 守住 login 先入到。

    對得返 src/healthcheck.py，但只回狀態，唔回接收機 LAN IP / config secret /
    用戶 home 路徑（log tail 經 _scrub 清走 /Users/<user>/）。
    """
    out = {
        'now_jst': datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S JST'),
        'uptime_secs': int((datetime.now(timezone.utc) - _BOOT_AT).total_seconds()),
    }

    # 1) launchd 五個 job —— launchctl list 一 call 攞晒（pid\tstatus\tlabel）
    rows = {}
    try:
        listing = subprocess.check_output(['launchctl', 'list'], text=True, timeout=5)
        for line in listing.splitlines()[1:]:
            parts = line.split('\t')
            if len(parts) >= 3 and parts[2].startswith('com.connie.plane-history.'):
                rows[parts[2].rsplit('.', 1)[1]] = {'pid': parts[0], 'status': parts[1]}
    except Exception:
        pass
    out['jobs'] = [{
        'job': j,
        'loaded': j in rows,
        'running': bool(rows.get(j) and rows[j]['pid'] not in ('-', '0')),
        'last_exit': rows[j]['status'] if j in rows else None,
    } for j in _DASH_JOBS]

    # 2) chromium headless 數量（renderer leak 試過堆到 59 個食 5.6GB，正常 6-12 個）
    try:
        ps_out = subprocess.check_output(['ps', '-axo', 'rss=,comm='], text=True, timeout=5)
        rss = [int(l.split(None, 1)[0]) for l in ps_out.splitlines() if 'chrome-headless-shell' in l]
        out['chrome'] = {'count': len(rss), 'rss_mb': round(sum(rss) / 1024)}
    except Exception:
        out['chrome'] = {'count': None, 'rss_mb': None}

    # 3) feed / DB 統計
    last_secs, records_today, db_ok = None, None, True
    try:
        last_secs, records_today = _receiver_snapshot()
    except Exception:
        db_ok = False
    out['feed'] = {
        'health': _feed_health(last_secs) if db_ok else 'down',
        'last_update_secs': last_secs,
        'records_today': records_today,
    }
    db = {'ok': db_ok}
    if db_ok:
        try:
            with connection.cursor() as cur:
                cur.execute('SELECT COUNT(*) FROM sightings_raw')
                db['raw'] = cur.fetchone()[0]
                cur.execute('SELECT COUNT(*) FROM aircraft_passes')
                db['passes'] = cur.fetchone()[0]
                cur.execute('SELECT MAX(seen_at) FROM sightings_raw')
                db['last_sample'] = fmt_ts(cur.fetchone()[0])
        except Exception:
            db['ok'] = False
    out['db'] = db

    # 4) 最近 error log 尾 8 行（basename + scrub /Users/<user>/）
    logs = []
    for name in _DASH_LOGS:
        p = settings.BASE_DIR / 'data' / name
        entry = {'name': name, 'exists': p.exists(), 'size': None, 'tail': []}
        if p.exists():
            entry['size'] = p.stat().st_size
            if entry['size']:
                try:
                    # 只 seek 尾 16KB，唔好成個 multi-MB log 讀晒落 memory
                    with open(p, 'rb') as fh:
                        fh.seek(max(0, entry['size'] - 16384))
                        tail = fh.read().decode('utf-8', errors='replace')
                    entry['tail'] = [_scrub(x) for x in tail.splitlines()[-8:]]
                except Exception:
                    pass
        logs.append(entry)
    out['logs'] = logs
    return out


def query_stats():
    """/api/stats：7 日 histogram、24h hourly、30 日 weekday×hour heatmap、TOP 10、peak alt、busiest hour。"""
    today_jst = datetime.now(JST).date()
    start_day = today_jst - timedelta(days=6)
    days = [(start_day + timedelta(days=i)).isoformat() for i in range(7)]
    start_date = start_day.isoformat()
    end_date = today_jst.isoformat()

    with connection.cursor() as cur:
        # 7 日每日 histogram
        histogram = []
        for d in days:
            cur.execute('SELECT COUNT(*) AS t FROM aircraft_passes WHERE pass_date = %s', [d])
            histogram.append({'day': d, 'count': _dict_one(cur)['t']})

        def top10(col, from_passes=False):
            if from_passes:
                sql = f"""
                    SELECT COALESCE(NULLIF(TRIM(p.{col}), ''), '(unknown)') AS k, COUNT(*) AS cnt
                    FROM aircraft_passes p
                    WHERE p.pass_date >= %s AND p.pass_date <= %s
                    GROUP BY COALESCE(NULLIF(TRIM(p.{col}), ''), '(unknown)')
                    ORDER BY cnt DESC, k ASC LIMIT 10
                """
            else:
                sql = f"""
                    SELECT COALESCE(NULLIF(TRIM(c.{col}), ''), '(unknown)') AS k, COUNT(*) AS cnt
                    FROM aircraft_passes p
                    LEFT JOIN aircraft_registry_cache c ON c.icao = p.icao
                    WHERE p.pass_date >= %s AND p.pass_date <= %s
                    GROUP BY COALESCE(NULLIF(TRIM(c.{col}), ''), '(unknown)')
                    ORDER BY cnt DESC, k ASC LIMIT 10
                """
            cur.execute(sql, [start_date, end_date])
            return [{'name': r['k'], 'count': r['cnt']} for r in _dict_cursor(cur)]

        top_types = top10('aircraft_type')
        top_ops = top10('operator', from_passes=True)
        top_from = top10('from_airport')
        top_to = top10('to_airport')

        # ICAO TOP 10 (7 日 + 全 DB) — 同樣 SQL pattern
        def top_icao(where_clause, params):
            cur.execute(
                f"""SELECT p.icao,
                           COALESCE(NULLIF(TRIM(c.registration), ''), '') AS reg,
                           COALESCE(NULLIF(TRIM(c.aircraft_type), ''), '') AS type,
                           COALESCE(NULLIF(TRIM(c.operator), ''), '') AS operator,
                           COUNT(*) AS cnt
                    FROM aircraft_passes p
                    LEFT JOIN aircraft_registry_cache c ON c.icao = p.icao
                    {where_clause}
                    GROUP BY p.icao, reg, type, operator
                    ORDER BY cnt DESC, p.icao ASC LIMIT 10""",
                params,
            )
            return [
                {'icao': r['icao'], 'reg': r['reg'], 'type': r['type'],
                 'operator': r['operator'], 'count': r['cnt']}
                for r in _dict_cursor(cur)
            ]

        top_icao_7d = top_icao('WHERE p.pass_date >= %s AND p.pass_date <= %s', [start_date, end_date])
        top_icao_db = top_icao('', [])

        cur.execute('SELECT COUNT(*) AS t FROM aircraft_passes')
        db_total = _dict_one(cur)['t']

        cur.execute(
            """SELECT COUNT(DISTINCT TRIM(aircraft_type)) AS t
               FROM aircraft_registry_cache
               WHERE aircraft_type IS NOT NULL AND TRIM(aircraft_type) <> ''"""
        )
        db_types = _dict_one(cur)['t']

        # 全 DB 最高高度（帶埋邊班機）
        cur.execute(
            """SELECT max_alt_baro AS alt, flight, icao FROM aircraft_passes
               WHERE max_alt_baro IS NOT NULL
               ORDER BY max_alt_baro DESC LIMIT 1"""
        )
        row = _dict_one(cur)
        peak_alt = {'alt': row['alt'], 'flight': row['flight'], 'icao': row['icao']} if row else None

        # 全 DB 最繁忙時段（JST）
        # 注意：傳 [] 做 params 等 PyMySQL unescape `%%` → `%`；冇 params 嘅話
        # `%%Y-%%m-%%d` 字面照傳俾 MySQL，STR_TO_DATE 認唔到 format 全部回 NULL。
        cur.execute(
            """SELECT HOUR(DATE_ADD(
                     STR_TO_DATE(SUBSTRING(first_seen, 1, 19), '%%Y-%%m-%%dT%%H:%%i:%%s'),
                     INTERVAL 9 HOUR)) AS hr,
                   COUNT(*) AS cnt
               FROM aircraft_passes
               GROUP BY hr
               ORDER BY cnt DESC, hr ASC LIMIT 1""",
            [],
        )
        row = _dict_one(cur)
        busiest_hour = (
            {'hour': row['hr'], 'count': row['cnt']}
            if row and row['hr'] is not None else None
        )

        # 近 24h rolling hourly histogram（JST 顯示）
        now_utc = datetime.now(timezone.utc)
        window_start = now_utc - timedelta(hours=24)
        cur.execute(
            'SELECT first_seen FROM aircraft_passes WHERE first_seen >= %s',
            [window_start.isoformat()],
        )
        cur_hour = now_utc.astimezone(JST).replace(minute=0, second=0, microsecond=0)
        starts = [cur_hour - timedelta(hours=23 - i) for i in range(24)]
        counts = dict.fromkeys(starts, 0)
        for r in _dict_cursor(cur):
            try:
                slot = (datetime.fromisoformat(r['first_seen'])
                        .astimezone(JST)
                        .replace(minute=0, second=0, microsecond=0))
            except (ValueError, TypeError):
                continue
            if slot in counts:
                counts[slot] += 1
        hourly = [
            {'hour': s.hour, 'count': counts[s], 'current': (s == cur_hour)}
            for s in starts
        ]

        # 近 30 日 weekday × hour heatmap（JST）
        heatmap_start = (now_utc - timedelta(days=30)).isoformat()
        cur.execute(
            """SELECT
                 WEEKDAY(DATE_ADD(
                   STR_TO_DATE(SUBSTRING(first_seen, 1, 19), '%%Y-%%m-%%dT%%H:%%i:%%s'),
                   INTERVAL 9 HOUR)) AS wd,
                 HOUR(DATE_ADD(
                   STR_TO_DATE(SUBSTRING(first_seen, 1, 19), '%%Y-%%m-%%dT%%H:%%i:%%s'),
                   INTERVAL 9 HOUR)) AS hr,
                 COUNT(*) AS cnt
               FROM aircraft_passes
               WHERE first_seen >= %s
               GROUP BY wd, hr""",
            [heatmap_start],
        )
        heat_cells = [[0] * 24 for _ in range(7)]
        heat_max = 0
        for r in _dict_cursor(cur):
            if r['wd'] is None or r['hr'] is None:
                continue
            heat_cells[int(r['wd'])][int(r['hr'])] = int(r['cnt'])
            if r['cnt'] > heat_max:
                heat_max = int(r['cnt'])

        # operator 國籍 TOP10（registry）+ 機種類分佈（passes）+ route pair TOP10
        top_op_country = top10('operator_country')
        category_dist = top10('category', from_passes=True)
        cur.execute(
            """SELECT TRIM(from_airport) AS f, TRIM(to_airport) AS t, COUNT(*) AS cnt
               FROM aircraft_passes
               WHERE pass_date >= %s AND pass_date <= %s
                 AND TRIM(COALESCE(from_airport, '')) NOT IN ('', '—', '-', 'n/a')
                 AND TRIM(COALESCE(to_airport, '')) NOT IN ('', '—', '-', 'n/a')
               GROUP BY f, t ORDER BY cnt DESC, f ASC LIMIT 10""",
            [start_date, end_date],
        )
        route_top = [{'from': r['f'], 'to': r['t'], 'count': r['cnt']} for r in _dict_cursor(cur)]

        # ===== 紀錄榜 / 之最（全 DB）=====
        # 最快：全 DB 最高 groundspeed
        cur.execute(
            """SELECT max_gs AS gs, flight, icao FROM aircraft_passes
               WHERE max_gs IS NOT NULL
               ORDER BY max_gs DESC LIMIT 1"""
        )
        row = _dict_one(cur)
        rec_fastest = {'gs': row['gs'], 'flight': row['flight'], 'icao': row['icao']} if row else None

        # 停留最耐：last_seen − first_seen 最長嘅一個 pass。
        # 傳 [] 做 params，等 PyMySQL 將 `%%` → `%`（同上面 busiest_hour 一樣）。
        cur.execute(
            """SELECT
                 TIMESTAMPDIFF(SECOND,
                   STR_TO_DATE(SUBSTRING(first_seen, 1, 19), '%%Y-%%m-%%dT%%H:%%i:%%s'),
                   STR_TO_DATE(SUBSTRING(last_seen, 1, 19), '%%Y-%%m-%%dT%%H:%%i:%%s')) AS secs,
                 flight, icao, pass_date
               FROM aircraft_passes
               ORDER BY secs DESC LIMIT 1""",
            [],
        )
        row = _dict_one(cur)
        rec_longest = (
            {'secs': int(row['secs']), 'flight': row['flight'],
             'icao': row['icao'], 'date': str(row['pass_date'])}
            if row and row['secs'] is not None else None
        )

        # 最繁忙一日：單日 pass 數最多
        cur.execute(
            """SELECT pass_date, COUNT(*) AS cnt FROM aircraft_passes
               GROUP BY pass_date ORDER BY cnt DESC, pass_date DESC LIMIT 1"""
        )
        row = _dict_one(cur)
        rec_busiest_day = {'date': str(row['pass_date']), 'count': row['cnt']} if row else None

        # ===== 航向羅盤：近 7 日 sightings 嘅 track（course over ground）分佈 =====
        # 16 方位：bucket = FLOOR(MOD(track + 11.25, 360) / 22.5)。
        # 用 MOD() 唔好用 `%` operator —— 有 param 嘅 SQL `%` 會撞 PyMySQL placeholder。
        compass_start = (now_utc - timedelta(days=7)).isoformat()
        cur.execute(
            """SELECT FLOOR(MOD(track + 11.25, 360) / 22.5) AS bucket, COUNT(*) AS cnt
               FROM sightings_raw
               WHERE track IS NOT NULL AND seen_at >= %s
               GROUP BY bucket""",
            [compass_start],
        )
        compass_buckets = [0] * 16
        compass_max = 0
        for r in _dict_cursor(cur):
            if r['bucket'] is None:
                continue
            b = int(r['bucket']) % 16
            compass_buckets[b] = int(r['cnt'])
            if r['cnt'] > compass_max:
                compass_max = int(r['cnt'])

    return {
        'histogram': histogram,
        'top_types': top_types,
        'top_ops': top_ops,
        'top_from': top_from,
        'top_to': top_to,
        'top_op_country': top_op_country,
        'category_dist': category_dist,
        'route_top': route_top,
        'db_total': db_total,
        'db_types': db_types,
        'peak_alt': peak_alt,
        'busiest_hour': busiest_hour,
        'hourly': hourly,
        'heatmap': {'max': heat_max, 'cells': heat_cells},
        'top_icao_7d': top_icao_7d,
        'top_icao_db': top_icao_db,
        'records': {
            'fastest': rec_fastest,
            'longest_pass': rec_longest,
            'busiest_day': rec_busiest_day,
        },
        'compass': {'max': compass_max, 'buckets': compass_buckets},
    }


def query_discover():
    """/api/discover：長窗口統計 — discovery curve、rare finds、altitude 分佈、全 DB top icao。"""
    with connection.cursor() as cur:
        # Discovery curve：每架 ICAO 嘅首見日，累積成 cumulative
        cur.execute(
            """SELECT icao, MIN(pass_date) AS first_date
               FROM aircraft_passes GROUP BY icao ORDER BY first_date ASC"""
        )
        by_date = {}
        for r in _dict_cursor(cur):
            d = r['first_date']
            d_str = d.isoformat() if hasattr(d, 'isoformat') else str(d)
            by_date[d_str] = by_date.get(d_str, 0) + 1
        curve = []
        running = 0
        for d_str in sorted(by_date.keys()):
            running += by_date[d_str]
            curve.append({'date': d_str, 'total': running})

        # Rare finds：得 1–2 次 pass 嘅 ICAO，last_seen 排頭
        cur.execute(
            """SELECT p.icao,
                      COALESCE(NULLIF(TRIM(c.registration), ''), '') AS reg,
                      COALESCE(NULLIF(TRIM(c.aircraft_type), ''), '') AS type,
                      COALESCE(NULLIF(TRIM(c.operator), ''), '') AS operator,
                      COALESCE(NULLIF(TRIM(c.country), ''), '') AS country,
                      COUNT(*) AS cnt,
                      MIN(p.first_seen) AS first_seen,
                      MAX(p.last_seen) AS last_seen
               FROM aircraft_passes p
               LEFT JOIN aircraft_registry_cache c ON c.icao = p.icao
               GROUP BY p.icao, reg, type, operator, country
               HAVING cnt <= 2
               ORDER BY last_seen DESC LIMIT 50"""
        )
        rare = [
            {
                'icao': r['icao'], 'reg': r['reg'], 'type': r['type'],
                'operator': r['operator'], 'country': r['country'],
                'count': r['cnt'],
                'first_seen': r['first_seen'], 'last_seen': r['last_seen'],
            }
            for r in _dict_cursor(cur)
        ]

        # 最高高度分佈：每 5000 ft 一桶（0–50k+）
        cur.execute(
            """SELECT LEAST(FLOOR(max_alt_baro/5000), 10) AS bucket, COUNT(*) AS cnt
               FROM aircraft_passes
               WHERE max_alt_baro IS NOT NULL
               GROUP BY bucket ORDER BY bucket"""
        )
        raw_buckets = {int(r['bucket']): int(r['cnt']) for r in _dict_cursor(cur) if r['bucket'] is not None}
        alt_dist = []
        for b in range(11):
            lo = b * 5000
            hi = (b + 1) * 5000 if b < 10 else None
            alt_dist.append({'lo': lo, 'hi': hi, 'count': raw_buckets.get(b, 0)})

        # 全 DB ICAO TOP 10
        cur.execute(
            """SELECT p.icao,
                      COALESCE(NULLIF(TRIM(c.registration), ''), '') AS reg,
                      COALESCE(NULLIF(TRIM(c.aircraft_type), ''), '') AS type,
                      COALESCE(NULLIF(TRIM(c.operator), ''), '') AS operator,
                      COUNT(*) AS cnt
               FROM aircraft_passes p
               LEFT JOIN aircraft_registry_cache c ON c.icao = p.icao
               GROUP BY p.icao, reg, type, operator
               ORDER BY cnt DESC, p.icao ASC LIMIT 10"""
        )
        top_icao_db = [
            {'icao': r['icao'], 'reg': r['reg'], 'type': r['type'],
             'operator': r['operator'], 'count': r['cnt']}
            for r in _dict_cursor(cur)
        ]

        # ===== 全年日曆 heatmap：每日 pass 數（窗 ~53 週）=====
        cal_start = (datetime.now(JST).date() - timedelta(days=371)).isoformat()
        cur.execute(
            """SELECT pass_date, COUNT(*) AS cnt FROM aircraft_passes
               WHERE pass_date >= %s GROUP BY pass_date ORDER BY pass_date""",
            [cal_start],
        )
        calendar = [{'date': str(r['pass_date']), 'count': int(r['cnt'])} for r in _dict_cursor(cur)]

        # ===== 速度分佈：每 50 kt 一桶（0–550+）=====
        cur.execute(
            """SELECT LEAST(FLOOR(max_gs/50), 11) AS bucket, COUNT(*) AS cnt
               FROM aircraft_passes
               WHERE max_gs IS NOT NULL
               GROUP BY bucket ORDER BY bucket"""
        )
        raw_spd = {int(r['bucket']): int(r['cnt']) for r in _dict_cursor(cur) if r['bucket'] is not None}
        speed_dist = []
        for b in range(12):
            lo = b * 50
            hi = (b + 1) * 50 if b < 11 else None
            speed_dist.append({'lo': lo, 'hi': hi, 'count': raw_spd.get(b, 0)})

        # ===== 最快 TOP 10：每架機歷來最高 groundspeed =====
        cur.execute(
            """SELECT p.icao,
                      COALESCE(NULLIF(TRIM(c.registration), ''), '') AS reg,
                      COALESCE(NULLIF(TRIM(c.aircraft_type), ''), '') AS type,
                      COALESCE(NULLIF(TRIM(c.operator), ''), '') AS operator,
                      MAX(p.max_gs) AS gs
               FROM aircraft_passes p
               LEFT JOIN aircraft_registry_cache c ON c.icao = p.icao
               WHERE p.max_gs IS NOT NULL
               GROUP BY p.icao, reg, type, operator
               ORDER BY gs DESC, p.icao ASC LIMIT 10"""
        )
        fastest_icao = [
            {'icao': r['icao'], 'reg': r['reg'], 'type': r['type'],
             'operator': r['operator'], 'gs': r['gs']}
            for r in _dict_cursor(cur)
        ]

    return {
        'discovery_curve': curve,
        'rare_finds': rare,
        'altitude_dist': alt_dist,
        'top_icao_db': top_icao_db,
        'calendar': calendar,
        'speed_dist': speed_dist,
        'fastest_icao': fastest_icao,
    }


def query_live():
    """server 端即時抓 tar1090 aircraft.json，trim 返有定位嘅機畀 `/map` 用。

    Cache 1 秒：N 個 client polling 都最多每秒打 tar1090 + DB 一次。
    """
    now_t = time.time()
    if _LIVE_CACHE['data'] is not None and (now_t - _LIVE_CACHE['at']) < _LIVE_TTL:
        return _LIVE_CACHE['data']

    if not _SOURCE_URL:
        return {'aircraft': [], 'error': 'no source url', 'count_pos': 0, 'count_total': 0}
    try:
        with urllib.request.urlopen(_SOURCE_URL, timeout=8) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return {'aircraft': [], 'error': str(e), 'count_pos': 0, 'count_total': 0}

    raw = payload.get('aircraft', []) or []
    out = []
    for a in raw:
        lat, lon = a.get('lat'), a.get('lon')
        if lat is None or lon is None:
            continue
        alt = a.get('alt_baro')
        if isinstance(alt, str):  # tar1090 落地會送 "ground"
            alt = None
        rate = a.get('baro_rate') or a.get('geom_rate')
        emerg = a.get('emergency')
        if emerg in (None, 'none', ''):
            emerg = None
        out.append({
            'hex': (a.get('hex') or '').strip().lower(),
            'flight': (a.get('flight') or '').strip() or None,
            'lat': lat, 'lon': lon, 'alt': alt, 'rate': rate,
            'track': a.get('track'), 'gs': a.get('gs'),
            'squawk': (a.get('squawk') or '').strip() or None,
            'emergency': emerg,
            'category': (a.get('category') or '').strip() or None,
            'seen': a.get('seen'),
        })

    # 由 registry cache 補返機牌 / 機型 / 公司 / 國家 / 航線，click popup 用
    def _clean(v):
        v = (v or '').strip() if isinstance(v, str) else None
        return v if v and v.lower() != 'n/a' else None

    hexes = [o['hex'] for o in out if o['hex']]
    if hexes:
        try:
            with connection.cursor() as cur:
                placeholders = ','.join(['%s'] * len(hexes))
                cur.execute(
                    f"""SELECT icao, registration, country, aircraft_type, operator, from_airport, to_airport
                        FROM aircraft_registry_cache WHERE icao IN ({placeholders})""",
                    hexes,
                )
                reg = {r['icao']: r for r in _dict_cursor(cur)}
            for o in out:
                m = reg.get(o['hex'])
                if m:
                    o['reg'] = _clean(m.get('registration'))
                    o['type'] = _clean(m.get('aircraft_type'))
                    o['operator'] = _clean(m.get('operator'))
                    o['country'] = _clean(m.get('country'))
                    o['from'] = _clean(m.get('from_airport'))
                    o['to'] = _clean(m.get('to_airport'))
        except Exception:
            pass  # registry enrichment optional，DB error 唔 break /map

    # 直升機群集事故偵測（map 即時橫額用；門檻喺 SiteConfig，可 admin 改）。
    # 任何例外都當「冇 cluster」，唔好搞冧 /map。
    heli_cluster = {'active': False}
    try:
        from web.models import SiteConfig
        cfg = SiteConfig.load()
        if cfg.heli_cluster_enabled:
            heli_cluster = detect_heli_cluster(out, cfg.heli_cluster_min, cfg.heli_cluster_radius_km)
            if heli_cluster.get('active'):
                heli_cluster['radius_km'] = cfg.heli_cluster_radius_km
    except Exception:
        heli_cluster = {'active': False}

    result = {
        'aircraft': out,
        'count_pos': len(out),
        'count_total': len(raw),
        'now': payload.get('now'),
        'heli_cluster': heli_cluster,
    }
    _LIVE_CACHE['at'] = now_t
    _LIVE_CACHE['data'] = result
    return result


# 通過履歷可排序欄白名單（key → DB column）
PASS_SORTS = {
    'date': 'first_seen', 'flight': 'flight', 'from': 'from_airport',
    'to': 'to_airport', 'alt': 'max_alt_baro', 'spd': 'max_gs', 'samples': 'samples',
}


def query_aircraft_passes(icao, page=1, page_size=50, sort=''):
    """單機通過履歷 server 分頁（offset/limit + total + sort 白名單）。

    sort：'' / 'key'（asc）/ '-key'（desc），key 喺 PASS_SORTS；預設 first_seen DESC。
    page_size clamp [1,500]。回 {rows, total, page, page_size, total_pages, sort}。
    """
    icao = (icao or '').strip().lower()
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(int(page_size), 500))
    except (TypeError, ValueError):
        page_size = 50
    desc = isinstance(sort, str) and sort.startswith('-')
    key = (sort[1:] if desc else sort) if sort else ''
    if key in PASS_SORTS:
        order = f'{PASS_SORTS[key]} {"DESC" if desc else "ASC"}'
    else:
        order, sort = 'first_seen DESC', ''
    offset = (page - 1) * page_size
    with connection.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS c FROM aircraft_passes WHERE icao = %s', [icao])
        total = _dict_one(cur)['c']
        cur.execute(
            f"""SELECT pass_date, flight, operator, first_seen, last_seen,
                       samples, min_alt_baro, max_alt_baro, min_gs, max_gs,
                       from_airport, to_airport
                FROM aircraft_passes WHERE icao = %s
                ORDER BY {order} LIMIT %s OFFSET %s""",
            [icao, page_size, offset],
        )
        rows = [{
            'pass_date': r['pass_date'],
            'flight': (r['flight'] or '').strip() or None,
            'operator': (r['operator'] or '').strip() or None,
            'first_seen': r['first_seen'],
            'last_seen': r['last_seen'],
            'samples': r['samples'],
            'min_alt': r['min_alt_baro'],
            'max_alt': r['max_alt_baro'],
            'min_gs': r['min_gs'],
            'max_gs': r['max_gs'],
            'from_airport': (r['from_airport'] or '').strip() or None,
            'to_airport': (r['to_airport'] or '').strip() or None,
        } for r in _dict_cursor(cur)]
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {'rows': rows, 'total': total, 'page': page, 'page_size': page_size,
            'total_pages': total_pages, 'sort': sort}


def query_aircraft(icao, page_size=50):
    """單機歷史：registry 資料 + aircraft_passes 聚合 + 每日 histogram + 第一頁 passes。"""
    icao = (icao or '').strip().lower()
    if not icao:
        return None

    with connection.cursor() as cur:
        cur.execute(
            """SELECT icao, registration, country, aircraft_type, operator, operator_country,
                      from_airport, to_airport, fr24_id, lookup_source, last_lookup_at
               FROM aircraft_registry_cache WHERE icao = %s""",
            [icao],
        )
        info = _dict_one(cur)

        cur.execute(
            """SELECT COUNT(*) AS passes,
                      COUNT(DISTINCT pass_date) AS days,
                      MIN(first_seen) AS first_seen,
                      MAX(last_seen) AS last_seen,
                      MAX(max_alt_baro) AS peak_alt,
                      MAX(max_gs) AS max_gs,
                      COALESCE(SUM(samples), 0) AS samples
               FROM aircraft_passes WHERE icao = %s""",
            [icao],
        )
        agg = _dict_one(cur) or {}

        # 揀最常見嘅 category（同一架機通常都係同一個）
        cur.execute(
            """SELECT category, COUNT(*) AS cnt FROM aircraft_passes
               WHERE icao = %s AND category IS NOT NULL AND TRIM(category) <> ''
               GROUP BY category ORDER BY cnt DESC LIMIT 1""",
            [icao],
        )
        cat_row = _dict_one(cur)
        category = cat_row['category'] if cat_row else None

        cur.execute(
            """SELECT pass_date, COUNT(*) AS cnt FROM aircraft_passes WHERE icao = %s
               GROUP BY pass_date ORDER BY pass_date DESC LIMIT 30""",
            [icao],
        )
        daily = [{'day': r['pass_date'], 'count': r['cnt']} for r in _dict_cursor(cur)][::-1]

        # 路線歷史：route_snapshots 按 (flight, from, to) 去重，最近觀測先
        cur.execute(
            """SELECT flight,
                      TRIM(COALESCE(from_airport, '')) AS f,
                      TRIM(COALESCE(to_airport, '')) AS t,
                      MAX(observed_at) AS last_seen, COUNT(*) AS n
               FROM aircraft_route_snapshots
               WHERE icao = %s
               GROUP BY flight, f, t
               ORDER BY last_seen DESC LIMIT 20""",
            [icao],
        )
        route_history = [{
            'flight': (r['flight'] or '').strip() or None,
            'from': r['f'] or None,
            'to': r['t'] or None,
            'last_seen': r['last_seen'],
            'n': r['n'],
        } for r in _dict_cursor(cur)]

        # 仲留住嘅最舊 raw（retention floor）；老過呢個嘅 pass = raw 已 prune，
        # 前端用嚟分清「track/profile 冇點」係 retention 清咗定本身冇位置。
        cur.execute('SELECT MIN(seen_at) AS m FROM sightings_raw')
        raw_since = (_dict_one(cur) or {}).get('m')

    def _c(v):
        v = (v or '').strip() if isinstance(v, str) else v
        return v if v and (not isinstance(v, str) or v.lower() != 'n/a') else None

    passes_pg = query_aircraft_passes(icao, 1, page_size, '')  # 第一頁（免 frontend 多一 request）

    return {
        'icao': icao.upper(),
        'registration': _c(info.get('registration')) if info else None,
        'aircraft_type': _c(info.get('aircraft_type')) if info else None,
        'operator': _c(info.get('operator')) if info else None,
        'operator_country': _c(info.get('operator_country')) if info else None,
        'country': _c(info.get('country')) if info else None,
        'category': category,
        'from': _c(info.get('from_airport')) if info else None,
        'to': _c(info.get('to_airport')) if info else None,
        'lookup_source': _c(info.get('lookup_source')) if info else None,
        'last_lookup_at': info.get('last_lookup_at') if info else None,
        'total_passes': int(agg.get('passes') or 0),
        'days': int(agg.get('days') or 0),
        'first_seen': agg.get('first_seen'),
        'last_seen': agg.get('last_seen'),
        'peak_alt': float(agg['peak_alt']) if agg.get('peak_alt') is not None else None,
        'max_gs': float(agg['max_gs']) if agg.get('max_gs') is not None else None,
        'samples': int(agg.get('samples') or 0),
        'daily': daily,
        'passes': passes_pg['rows'],
        'passes_total': passes_pg['total'],
        'page_size': passes_pg['page_size'],
        'route_history': route_history,
        'raw_since': raw_since,
    }


def query_aircraft_track(icao, from_iso, to_iso):
    """揀指定 pass 嘅 sightings_raw 點，用嚟畫 alt + gs profile chart。"""
    icao = (icao or '').strip().lower()
    if not icao or not from_iso or not to_iso:
        return []
    with connection.cursor() as cur:
        cur.execute(
            """SELECT seen_at, alt_baro, gs, lat, lon FROM sightings_raw
               WHERE icao = %s AND seen_at >= %s AND seen_at <= %s
               ORDER BY seen_at ASC""",
            [icao, from_iso, to_iso],
        )
        return [{
            'ts': r['seen_at'],
            'alt': float(r['alt_baro']) if r['alt_baro'] is not None else None,
            'gs': float(r['gs']) if r['gs'] is not None else None,
            'lat': float(r['lat']) if r['lat'] is not None else None,
            'lon': float(r['lon']) if r['lon'] is not None else None,
        } for r in _dict_cursor(cur)]


# planespotters 相 cache（icao -> (photo|None, fetched_at)）；process-local，避免重複打 planespotters。
_PHOTO_CACHE = {}
_PHOTO_TTL = 86400  # 1 日
_PHOTO_CACHE_MAX = 4096  # cache 上限：防公開 endpoint 被灌大量唯一 icao 谷爆 memory
_ICAO_RE = re.compile(r'[0-9a-f]{6}')


def query_aircraft_photo(icao):
    """planespotters.net 相 metadata（server-side fetch，要自訂 User-Agent —— planespotters
    擋瀏覽器 UA，所以唔可以純 client 直 fetch）。回 {src, link, photographer} | None。
    張相本身由 browser 直接 load planespotters CDN，唔經 / 唔存喺本 server。"""
    icao = (icao or '').strip().lower()
    # 嚴格 ICAO hex（6 位）驗證：公開 endpoint，防 URL injection / 用我 server 做 open
    # proxy 灌 planespotters，又限死 cache key 範圍。
    if not _ICAO_RE.fullmatch(icao):
        return None
    now = time.time()
    hit = _PHOTO_CACHE.get(icao)
    if hit and now - hit[1] < _PHOTO_TTL:
        return hit[0]
    photo = None
    try:
        req = urllib.request.Request(
            f'https://api.planespotters.net/pub/photos/hex/{icao}',
            headers={'User-Agent': 'plane-history/1.0 (+https://flight.connie.hk)'},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.load(resp)
        ph = (data.get('photos') or [None])[0]
        if ph:
            src = (ph.get('thumbnail_large') or ph.get('thumbnail') or {}).get('src')
            if src:
                photo = {'src': src, 'link': ph.get('link'), 'photographer': ph.get('photographer')}
    except Exception:
        photo = None   # planespotters timeout / 死 → 當冇相，唔好爆
    if len(_PHOTO_CACHE) >= _PHOTO_CACHE_MAX:
        _PHOTO_CACHE.pop(next(iter(_PHOTO_CACHE)), None)   # 超上限 → evict 最舊（防 memory 谷爆）
    _PHOTO_CACHE[icao] = (photo, now)
    return photo


def raw_retention_floor_day():
    """仲留住嘅最舊 raw 屬於邊個 JST 日。冇 raw 就 None。

    `sightings_raw` 有 30 日 retention（`src/prune_raw.py`），`aircraft_passes` 就永久留。
    呢個 floor 用嚟分流 `query_rows()`：老過（或者啱啱等於，因為嗰日一定係半截）
    floor 嘅日子改由 passes 砌 row。
    """
    with connection.cursor() as cur:
        cur.execute('SELECT MIN(seen_at) AS m FROM sightings_raw')
        m = (_dict_one(cur) or {}).get('m')
    if not m:
        return None
    try:
        return datetime.fromisoformat(m).astimezone(JST).strftime('%Y-%m-%d')
    except (TypeError, ValueError):
        return None


def _query_rows_from_passes(day_str, sort_key='last_seen', country_filter='',
                            operator_filter='', type_filter='', from_filter='',
                            to_filter='', category_filter=''):
    """`query_rows()` 嘅 retention fallback：由 `aircraft_passes` 砌返同一個 row shape。

    **唔可以用 `pass_date = %s`**：`pass_date` 係 build_passes 由 `first_seen` 嘅 JST 日
    定（`src/build_passes.py:130`），所以跨 JST 午夜嘅 pass 成個計晒落開始嗰日 ——
    架機喺第二日 00:00-00:20 出現過都會漏咗，而開始嗰日又會攞到第二日嘅 last_seen。
    改為同 raw 版一樣夾實個 JST 日窗做**重疊**判斷，membership 就對得返。
    （`first_seen`/`last_seen` 全表都係 UTC ISO，所以字串比較同時序一致。）

    同 raw 版嘅差別：
    - `samples` 係逐個 pass 加埋（SUM），唔係逐條 raw 數；跨午夜嘅 pass 冇逐日拆數，
      所以兩邊日子都會計足個 pass（alt 高低位同理）。每日得 1-2 架，接受。
    - `first_seen`/`last_seen` 一律出 pass 嘅**真實**極值，唔夾落日界。呢兩欄係觀測
      記錄，夾成 00:00:00 / 23:59:59 等於報一個從來冇發生過嘅觀測時間。跨午夜嗰
      1-2 架會喺 D 日表度見到 D±1 嘅時間戳，但時間戳連日期一齊顯示，睇得出係
      跨咗夜，好過砌個假數。
    - 呢啲日子冇 raw，所以撳入去嘅 track / 航跡係空（前端會標「冇航跡」）。
    - operator / country / from / to 優先用 registry cache（同 raw 版一致），
      registry 冇先用 pass 當時記低嘅值 —— 舊 pass 個 registry entry 可能已經冇。
    全部 filter 都行 HAVING：呢度啲欄位係 aggregate alias，擺 WHERE 會 SQL error。
    """
    order_by = ALLOWED_SORTS.get(sort_key, ALLOWED_SORTS['last_seen'])
    start_utc, end_utc = jst_day_utc_bounds(day_str)
    # 重疊：pass 未喺日頭前完 且 未到日尾先開始
    params = [start_utc, end_utc]
    having = []
    for alias, val in [
        ('country', country_filter),
        ('operator', operator_filter),
        ('aircraft_type', type_filter),
        ('from_airport', from_filter),
        ('to_airport', to_filter),
    ]:
        if val:
            having.append(f"COALESCE(NULLIF({alias}, ''), '-') = %s")
            params.append(val)
    if category_filter in CATEGORY_GROUPS:
        if category_filter == 'unknown':
            known = list(_CATEGORY_CODE_TO_GROUP)
            having.append(f"category NOT IN ({', '.join(['%s'] * len(known))})")
            params.extend(known)
        else:
            codes = CATEGORY_GROUPS[category_filter]
            having.append(f"category IN ({', '.join(['%s'] * len(codes))})")
            params.extend(codes)
    having_clause = ('HAVING ' + ' AND '.join(having)) if having else ''

    with connection.cursor() as cur:
        cur.execute(
            f"""SELECT
                  p.icao,
                  COALESCE(MAX(NULLIF(TRIM(p.flight), '')), '') AS flight,
                  COALESCE(MAX(NULLIF(TRIM(p.category), '')), '') AS category,
                  COALESCE(MAX(NULLIF(TRIM(c.registration), '')), '') AS registration,
                  COALESCE(MAX(NULLIF(TRIM(c.aircraft_type), '')), '') AS aircraft_type,
                  COALESCE(MAX(NULLIF(TRIM(c.country), '')),
                           MAX(NULLIF(TRIM(p.country), '')), '') AS country,
                  COALESCE(MAX(NULLIF(TRIM(c.operator), '')),
                           MAX(NULLIF(TRIM(p.operator), '')), '') AS operator,
                  COALESCE(MAX(NULLIF(TRIM(c.from_airport), '')),
                           MAX(NULLIF(TRIM(p.from_airport), '')), '') AS from_airport,
                  COALESCE(MAX(NULLIF(TRIM(c.to_airport), '')),
                           MAX(NULLIF(TRIM(p.to_airport), '')), '') AS to_airport,
                  MIN(p.first_seen) AS first_seen,
                  MAX(p.last_seen) AS last_seen,
                  MIN(p.min_alt_baro) AS min_alt_baro,
                  MAX(p.max_alt_baro) AS max_alt_baro,
                  SUM(p.samples) AS samples
                FROM aircraft_passes p
                LEFT JOIN aircraft_registry_cache c ON c.icao = p.icao
                WHERE p.last_seen >= %s AND p.first_seen < %s
                GROUP BY p.icao
                {having_clause}
                ORDER BY {order_by}""",
            params,
        )
        return [{
            'icao': r['icao'],
            'flight': r['flight'] or '-',
            'operator': r['operator'] or '-',
            'registration': r['registration'] or '-',
            'country': r['country'] or '-',
            'aircraft_type': r['aircraft_type'] or '-',
            'from_airport': r['from_airport'] or '-',
            'to_airport': r['to_airport'] or '-',
            'category': r['category'] or '-',
            'min_alt_baro': int(r['min_alt_baro']) if r['min_alt_baro'] is not None else '-',
            'max_alt_baro': int(r['max_alt_baro']) if r['max_alt_baro'] is not None else '-',
            'samples': int(r['samples'] or 0),
            'first_seen_jst': fmt_ts(r['first_seen']),
            'last_seen_jst': fmt_ts(r['last_seen']),
        } for r in _dict_cursor(cur)]


def query_rows(day_str, sort_key='last_seen', country_filter='', operator_filter='',
               type_filter='', from_filter='', to_filter='', category_filter=''):
    """/details + home today table 用：指定 JST 日嘅 aircraft 聚合（每 ICAO 一行）。

    `category_filter` 收 `CATEGORY_GROUPS` 嘅 group key（例如 'heli'），唔係 raw code。

    日子老過 raw retention 就自動由 `aircraft_passes` 砌（見 `_query_rows_from_passes`），
    唔會好似以前咁交白卷。
    """
    floor = raw_retention_floor_day()
    if floor and day_str <= floor:
        return _query_rows_from_passes(
            day_str, sort_key, country_filter, operator_filter,
            type_filter, from_filter, to_filter, category_filter)
    order_by = ALLOWED_SORTS.get(sort_key, ALLOWED_SORTS['last_seen'])
    start_utc, end_utc = jst_day_utc_bounds(day_str)
    conditions = ['s.seen_at >= %s', 's.seen_at < %s']
    params = [start_utc, end_utc]
    for col, val in [
        ('country', country_filter),
        ('operator', operator_filter),
        ('aircraft_type', type_filter),
        ('from_airport', from_filter),
        ('to_airport', to_filter),
    ]:
        if val:
            conditions.append(f"COALESCE(NULLIF(TRIM(c.{col}), ''), '-') = %s")
            params.append(val)
    where_clause = ' AND '.join(conditions)

    # category 係 aggregate（MAX(...)）出嚟嘅 alias，唔可以放 WHERE，要用 HAVING。
    # 'unknown' = NOT IN 全部認得嘅 code（咁 A0 / '' / D* 唔使逐個列）。
    having_clause = ''
    if category_filter in CATEGORY_GROUPS:
        if category_filter == 'unknown':
            known = list(_CATEGORY_CODE_TO_GROUP)
            having_clause = f"HAVING category NOT IN ({', '.join(['%s'] * len(known))})"
            params.extend(known)
        else:
            codes = CATEGORY_GROUPS[category_filter]
            having_clause = f"HAVING category IN ({', '.join(['%s'] * len(codes))})"
            params.extend(codes)

    with connection.cursor() as cur:
        cur.execute(
            f"""SELECT
                  s.icao,
                  COALESCE(MAX(NULLIF(TRIM(s.flight), '')), '') AS flight,
                  COALESCE(MAX(NULLIF(TRIM(s.category), '')), '') AS category,
                  COALESCE(MAX(NULLIF(TRIM(c.registration), '')), '') AS registration,
                  COALESCE(MAX(NULLIF(TRIM(c.country), '')), '') AS country,
                  COALESCE(MAX(NULLIF(TRIM(c.operator), '')), '') AS operator,
                  COALESCE(MAX(NULLIF(TRIM(c.aircraft_type), '')), '') AS aircraft_type,
                  COALESCE(MAX(NULLIF(TRIM(c.from_airport), '')), '') AS from_airport,
                  COALESCE(MAX(NULLIF(TRIM(c.to_airport), '')), '') AS to_airport,
                  MIN(s.seen_at) AS first_seen,
                  MAX(s.seen_at) AS last_seen,
                  MIN(CASE WHEN s.alt_baro IS NOT NULL THEN s.alt_baro END) AS min_alt_baro,
                  MAX(CASE WHEN s.alt_baro IS NOT NULL THEN s.alt_baro END) AS max_alt_baro,
                  COUNT(*) AS samples
                FROM sightings_raw s
                LEFT JOIN aircraft_registry_cache c ON c.icao = s.icao
                WHERE {where_clause}
                GROUP BY s.icao
                {having_clause}
                ORDER BY {order_by}""",
            params,
        )
        return [{
            'icao': r['icao'],
            'flight': r['flight'] or '-',
            'operator': r['operator'] or '-',
            'registration': r['registration'] or '-',
            'country': r['country'] or '-',
            'aircraft_type': r['aircraft_type'] or '-',
            'from_airport': r['from_airport'] or '-',
            'to_airport': r['to_airport'] or '-',
            'category': r['category'] or '-',
            'min_alt_baro': int(r['min_alt_baro']) if r['min_alt_baro'] is not None else '-',
            'max_alt_baro': int(r['max_alt_baro']) if r['max_alt_baro'] is not None else '-',
            'samples': r['samples'],
            'first_seen_jst': fmt_ts(r['first_seen']),
            'last_seen_jst': fmt_ts(r['last_seen']),
        } for r in _dict_cursor(cur)]


def query_summary(day_str):
    """/ home page 用：指定 JST 日嘅 operator breakdown + total aircraft count。"""
    start_utc, end_utc = jst_day_utc_bounds(day_str)
    with connection.cursor() as cur:
        # GROUP BY 要重複 expression（MySQL only_full_group_by mode 唔接受 alias）
        cur.execute(
            """SELECT
                 COALESCE(NULLIF(TRIM(c.operator), ''), '(unknown)') AS operator,
                 COALESCE(NULLIF(TRIM(c.operator_country), ''), '') AS country,
                 COUNT(DISTINCT s.icao) AS cnt
               FROM sightings_raw s
               LEFT JOIN aircraft_registry_cache c ON c.icao = s.icao
               WHERE s.seen_at >= %s AND s.seen_at < %s
               GROUP BY
                 COALESCE(NULLIF(TRIM(c.operator), ''), '(unknown)'),
                 COALESCE(NULLIF(TRIM(c.operator_country), ''), '')
               ORDER BY cnt DESC, operator ASC""",
            [start_utc, end_utc],
        )
        operators = [
            {'operator': r['operator'], 'country': r['country'], 'count': r['cnt']}
            for r in _dict_cursor(cur)
        ]
        cur.execute(
            'SELECT COUNT(DISTINCT icao) AS t FROM sightings_raw WHERE seen_at >= %s AND seen_at < %s',
            [start_utc, end_utc],
        )
        total = _dict_one(cur)['t']
    return {
        'day': day_str,
        'total_aircraft': total,
        'operators': operators,
    }
