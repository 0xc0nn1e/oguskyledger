"""Read query helpers — 對應舊 src/web_app.py 嘅 query_* 函數。

過渡期：用 Django connection cursor + raw SQL，SQL 直接由舊 web_app.py copy 過嚟。
下輪 refactor：逐個 swap 做 ORM `annotate()` / `aggregate()`，當 learning。

公約：每個 query 回 dict / list[dict]，畀 DRF / view 直接 `JsonResponse(data)`。
"""

import json
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

from django.conf import settings
from django.db import connection


JST = timezone(timedelta(hours=9))


# /details page sort 用嘅 ORDER BY whitelist，唔可以畀 user 直接傳 SQL。
ALLOWED_SORTS = {
    'last_seen': 'last_seen DESC',
    'country': 'country ASC, operator ASC, last_seen DESC',
    'operator': 'operator ASC, country ASC, last_seen DESC',
    'type': 'aircraft_type ASC, operator ASC, last_seen DESC',
}


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
_COVERAGE_CACHE = {'at': 0.0, 'data': None}
_COVERAGE_TTL = 600  # 秒：10 分鐘 cache，coverage 圖唔需要實時

# 由 settings.PLANE_HISTORY 讀 tar1090 source URL + 接收機座標
_SOURCE_URL = (settings.PLANE_HISTORY.get('source') or {}).get('aircraft_json_url')
try:
    _RX_LAT = float((settings.PLANE_HISTORY.get('receiver') or {}).get('lat'))
    _RX_LON = float((settings.PLANE_HISTORY.get('receiver') or {}).get('lon'))
except (TypeError, ValueError):
    _RX_LAT = _RX_LON = None


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
            """SELECT max_alt_baro AS alt, flight FROM aircraft_passes
               WHERE max_alt_baro IS NOT NULL
               ORDER BY max_alt_baro DESC LIMIT 1"""
        )
        row = _dict_one(cur)
        peak_alt = {'alt': row['alt'], 'flight': row['flight']} if row else None

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

    return {
        'histogram': histogram,
        'top_types': top_types,
        'top_ops': top_ops,
        'top_from': top_from,
        'top_to': top_to,
        'db_total': db_total,
        'db_types': db_types,
        'peak_alt': peak_alt,
        'busiest_hour': busiest_hour,
        'hourly': hourly,
        'heatmap': {'max': heat_max, 'cells': heat_cells},
        'top_icao_7d': top_icao_7d,
        'top_icao_db': top_icao_db,
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

    return {
        'discovery_curve': curve,
        'rare_finds': rare,
        'altitude_dist': alt_dist,
        'top_icao_db': top_icao_db,
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

    result = {
        'aircraft': out,
        'count_pos': len(out),
        'count_total': len(raw),
        'now': payload.get('now'),
    }
    _LIVE_CACHE['at'] = now_t
    _LIVE_CACHE['data'] = result
    return result


def query_coverage():
    """近 30 日 sightings_raw 嘅 polar coverage：每 10° 方位最遠距離 + 最遠機體。

    Cache 10 分鐘：coverage 圖唔需要實時，重 SQL（trig + full scan）。
    """
    if _RX_LAT is None or _RX_LON is None:
        return {'error': 'no_receiver_coords'}

    now = time.time()
    if _COVERAGE_CACHE['data'] is not None and (now - _COVERAGE_CACHE['at']) < _COVERAGE_TTL:
        return _COVERAGE_CACHE['data']

    # haversine km + bearing(0-360)。限近 30 日（行 seen_at index）；
    # cap 700 km 隔走亂跳定位（ADS-B line-of-sight 上限 ~400-700 km，再遠多數 bad decode）
    window_days = 30
    since = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
    inner = """
        SELECT
          6371 * 2 * ASIN(LEAST(1, SQRT(
            POWER(SIN(RADIANS(lat - %(rlat)s) / 2), 2) +
            COS(RADIANS(%(rlat)s)) * COS(RADIANS(lat)) *
            POWER(SIN(RADIANS(lon - %(rlon)s) / 2), 2)
          ))) AS dist_km,
          MOD(DEGREES(ATAN2(
            SIN(RADIANS(lon - %(rlon)s)) * COS(RADIANS(lat)),
            COS(RADIANS(%(rlat)s)) * SIN(RADIANS(lat)) -
            SIN(RADIANS(%(rlat)s)) * COS(RADIANS(lat)) * COS(RADIANS(lon - %(rlon)s))
          )) + 360, 360) AS bearing,
          icao
        FROM sightings_raw
        WHERE lat IS NOT NULL AND lon IS NOT NULL AND seen_at >= %(since)s
    """
    params = {'rlat': _RX_LAT, 'rlon': _RX_LON, 'since': since}

    with connection.cursor() as cur:
        cur.execute(f'SELECT icao, dist_km, bearing FROM ({inner}) t WHERE dist_km <= 700', params)
        by_sector = {}
        far = None
        for r in _dict_cursor(cur):
            d = float(r['dist_km'])
            b = float(r['bearing'])
            sec = int(b // 10) % 36
            if d > by_sector.get(sec, 0.0):
                by_sector[sec] = d
            if far is None or d > far['dist_km']:
                far = {'icao': r['icao'], 'dist_km': d, 'bearing': b}

        sectors = [{'deg': i * 10, 'km': round(by_sector.get(i, 0.0), 1)} for i in range(36)]

        far_info = None
        if far:
            cur.execute(
                'SELECT registration, operator FROM aircraft_registry_cache WHERE icao = %s',
                [far['icao']],
            )
            far_info = _dict_one(cur)

        cur.execute(
            'SELECT COUNT(DISTINCT icao) AS c FROM sightings_raw WHERE lat IS NOT NULL AND lon IS NOT NULL'
        )
        aircraft_with_pos = _dict_one(cur)['c']

    max_km = max((s['km'] for s in sectors), default=0.0)
    data = {
        'sectors': sectors,
        'max_km': round(max_km, 1),
        'max_nm': round(max_km / 1.852, 1),
        'window_days': window_days,
        'aircraft_with_pos': aircraft_with_pos,
        'farthest': {
            'icao': far['icao'].upper() if far else None,
            'km': round(float(far['dist_km']), 1) if far else None,
            'bearing': round(float(far['bearing'])) if far else None,
            'registration': (far_info or {}).get('registration') if far_info else None,
            'operator': (far_info or {}).get('operator') if far_info else None,
        } if far else None,
    }
    _COVERAGE_CACHE['at'] = now
    _COVERAGE_CACHE['data'] = data
    return data


def query_aircraft(icao):
    """單機歷史：registry 資料 + aircraft_passes 聚合 + 每日 histogram + passes 列表。"""
    icao = (icao or '').strip().lower()
    if not icao:
        return None

    with connection.cursor() as cur:
        cur.execute(
            """SELECT icao, registration, country, aircraft_type, operator,
                      from_airport, to_airport, fr24_id
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

        cur.execute(
            """SELECT pass_date, flight, operator, first_seen, last_seen,
                      samples, min_alt_baro, max_alt_baro, from_airport, to_airport
               FROM aircraft_passes WHERE icao = %s
               ORDER BY first_seen DESC LIMIT 300""",
            [icao],
        )
        passes = [{
            'pass_date': r['pass_date'],
            'flight': (r['flight'] or '').strip() or None,
            'operator': (r['operator'] or '').strip() or None,
            'first_seen': r['first_seen'],
            'last_seen': r['last_seen'],
            'samples': r['samples'],
            'min_alt': r['min_alt_baro'],
            'max_alt': r['max_alt_baro'],
            'from_airport': (r['from_airport'] or '').strip() or None,
            'to_airport': (r['to_airport'] or '').strip() or None,
        } for r in _dict_cursor(cur)]

    def _c(v):
        v = (v or '').strip() if isinstance(v, str) else v
        return v if v and (not isinstance(v, str) or v.lower() != 'n/a') else None

    return {
        'icao': icao.upper(),
        'registration': _c(info.get('registration')) if info else None,
        'aircraft_type': _c(info.get('aircraft_type')) if info else None,
        'operator': _c(info.get('operator')) if info else None,
        'country': _c(info.get('country')) if info else None,
        'category': category,
        'from': _c(info.get('from_airport')) if info else None,
        'to': _c(info.get('to_airport')) if info else None,
        'total_passes': int(agg.get('passes') or 0),
        'days': int(agg.get('days') or 0),
        'first_seen': agg.get('first_seen'),
        'last_seen': agg.get('last_seen'),
        'peak_alt': float(agg['peak_alt']) if agg.get('peak_alt') is not None else None,
        'max_gs': float(agg['max_gs']) if agg.get('max_gs') is not None else None,
        'samples': int(agg.get('samples') or 0),
        'daily': daily,
        'passes': passes,
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


def query_rows(day_str, sort_key='last_seen', country_filter='', operator_filter='',
               type_filter='', from_filter='', to_filter=''):
    """/details + home today table 用：指定 JST 日嘅 aircraft 聚合（每 ICAO 一行）。"""
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
