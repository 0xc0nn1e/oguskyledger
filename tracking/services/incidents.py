"""事故偵測 heuristic —— 直升機異常聚集。

背景：多架直升機喺細範圍內同時出現，通常代表附近有事故 / 災害（火警、交通意外等），
報道機 + 警/消防直升機會聚埋一齊。呢個 module 純計幾何，唔掂 DB / Django，
畀 `query_live`（即時地圖橫額）同 `ingest_pipeline`（push 通知）兩邊共用，
確保 map 同 push 用同一套門檻同邏輯。
"""

from math import asin, cos, radians, sin, sqrt


def _haversine_km(lat1, lon1, lat2, lon2):
    """兩點大圓距離（km）。"""
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def detect_heli_cluster(aircraft, min_n=4, radius_km=8.0):
    """喺即時機群（query_live 嘅 list）搵直升機聚集。

    aircraft：dict list，每個有 `category` / `lat` / `lon` / `hex`（query_live 格式）。
    搵一架直升機，佢 radius_km 內（含自己）有最多直升機；若數量 >= min_n 當 cluster。

    回 {'active': True, 'count': n, 'center': [lat, lon], 'members': [hex, ...]}，
    冇就 {'active': False}。
    """
    try:
        min_n = max(2, int(min_n))
        radius_km = float(radius_km)
    except (TypeError, ValueError):
        min_n, radius_km = 4, 8.0

    helis = [a for a in (aircraft or [])
             if (a.get('category') or '').strip().upper() == 'A7'
             and a.get('lat') is not None and a.get('lon') is not None]
    if len(helis) < min_n:
        return {'active': False}

    best = []
    for h in helis:
        members = [g for g in helis
                   if _haversine_km(h['lat'], h['lon'], g['lat'], g['lon']) <= radius_km]
        if len(members) > len(best):
            best = members

    if len(best) >= min_n:
        lat = sum(m['lat'] for m in best) / len(best)
        lon = sum(m['lon'] for m in best) / len(best)
        return {
            'active': True,
            'count': len(best),
            'center': [round(lat, 4), round(lon, 4)],
            'members': [m.get('hex') for m in best if m.get('hex')],
        }
    return {'active': False}
