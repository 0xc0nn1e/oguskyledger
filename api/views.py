"""DRF + plain JSON API endpoints。

Today（task #19 第一輪）：
- /api/health    real：service liveness + DB + receiver feed status
- /api/me        real：current logged-in user info
- /api/about     real：receiver status + uptime + records today
- /api/stats     stub
- /api/discover  stub
- /api/live      stub
- /api/aircraft  stub
- /api/aircraft/track  stub
- /api/coverage  stub

Stub 暫時回 200 + {todo: True}，畀 frontend 知道 endpoint 存在。下輪逐個 fill 真實 query。
"""

from django.http import JsonResponse
from rest_framework.decorators import api_view
from rest_framework.response import Response

from tracking.services import queries


# ---------- real endpoints ----------

@api_view(['GET'])
def health(request):
    """Liveness：DB 連到回 200，否則 503。Frontend healthcheck 同 launchd KeepAlive 用。"""
    payload, status_code = queries.query_health()
    return Response(payload, status=status_code)


@api_view(['GET'])
def me(request):
    """Current user info — 對應舊 /api/me。

    舊系統用 cookie session，nav.html JS 由 fetch /api/me 知道應該 show login 定 logout。
    Django built-in `request.user` 已搞掂 session，直接 read。
    """
    if request.user.is_authenticated:
        return Response({
            'username': request.user.username,
            'is_staff': request.user.is_staff,
        })
    return Response({'username': None})


@api_view(['GET'])
def about(request):
    """Receiver status + uptime + records_today — 對應舊 /api/about。"""
    return Response(queries.query_about())


@api_view(['GET'])
def stats(request):
    """/api/stats：7 日 / 24h histogram、heatmap、TOP 10、peak alt、busiest hour。"""
    return Response(queries.query_stats())


@api_view(['GET'])
def discover(request):
    """/api/discover：discovery curve、rare finds、altitude 分佈、全 DB top icao。"""
    return Response(queries.query_discover())


@api_view(['GET'])
def live(request):
    """/api/live：即時 tar1090 aircraft.json + registry enrichment，1 秒 TTL cache。"""
    return Response(queries.query_live())


@api_view(['GET'])
def aircraft(request):
    """/api/aircraft?icao=<hex>：單機歷史（registry + passes 聚合 + per-pass FROM/TO）。"""
    icao = request.GET.get('icao', '')
    payload = queries.query_aircraft(icao)
    if payload is None:
        return Response({'error': 'no_icao'}, status=404)
    return Response(payload)


@api_view(['GET'])
def aircraft_track(request):
    """/api/aircraft/track?icao=&from=&to=：單一 pass 嘅 sightings_raw 軌跡。"""
    icao = request.GET.get('icao', '')
    from_iso = request.GET.get('from', '')
    to_iso = request.GET.get('to', '')
    return Response({'points': queries.query_aircraft_track(icao, from_iso, to_iso)})


@api_view(['GET'])
def today(request):
    """/api/today?day=<JST date>&sort=...&country=...&operator=...：home 同 details 頁用。

    回 rows + filter options（每個 dropdown）+ count。
    """
    from datetime import datetime as _dt
    day = request.GET.get('day') or _dt.now(queries.JST).strftime('%Y-%m-%d')
    sort = request.GET.get('sort', 'last_seen')
    filters = {k: request.GET.get(k, '') for k in
               ('country', 'operator', 'type', 'from', 'to')}
    rows = queries.query_rows(
        day, sort,
        country_filter=filters['country'],
        operator_filter=filters['operator'],
        type_filter=filters['type'],
        from_filter=filters['from'],
        to_filter=filters['to'],
    )
    # 唔加 filter 嘅版本，攞返 dropdown 全部可選值
    all_rows = queries.query_rows(day, sort)
    countries = sorted({r['country'] for r in all_rows if r['country'] != '-'})
    operators = sorted({r['operator'] for r in all_rows if r['operator'] != '-'})
    types = sorted({r['aircraft_type'] for r in all_rows if r['aircraft_type'] != '-'})
    from_airports = sorted({r['from_airport'] for r in all_rows if r['from_airport'] != '-'})
    to_airports = sorted({r['to_airport'] for r in all_rows if r['to_airport'] != '-'})
    return Response({
        'day': day,
        'sort': sort,
        'count': len(rows),
        'countries': countries,
        'operators': operators,
        'types': types,
        'from_airports': from_airports,
        'to_airports': to_airports,
        'filters': filters,
        'rows': rows,
    })


@api_view(['GET'])
def summary(request):
    """/api/summary?day=<JST date>：home page 用嘅 operator breakdown + total。"""
    from datetime import datetime as _dt
    day = request.GET.get('day') or _dt.now(queries.JST).strftime('%Y-%m-%d')
    return Response(queries.query_summary(day))
