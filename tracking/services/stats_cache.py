"""`/api/stats` 同 `/api/discover` 共用嘅持久統計快照。

慢 SQL 淨係由 `refresh_stats_cache` management command 執行；web request 只會讀
`data/stats-cache.json`。用同目錄暫存檔再 `os.replace()`，確保 gunicorn 唔會讀到
寫咗一半嘅 JSON。
"""

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder

from tracking.services import queries


# v2：stats section 加咗 `coverage`（接收範圍極座標圖）。舊 snapshot 冇呢個 key，
# 唔 bump 嘅話 web 會讀住舊檔然後前端攞唔到 coverage —— load_stats_cache() 會
# 憑 version 判定唔相容，逼 /api/stats 回 503 直到 refresh_stats_cache 重新生成。
CACHE_VERSION = 2
CACHE_PATH = Path(settings.BASE_DIR) / 'data' / 'stats-cache.json'

_MEMORY_CACHE = {'mtime_ns': None, 'snapshot': None}


class StatsCacheUnavailable(Exception):
    """統計快照未生成、損壞，或者版本唔相容。"""


def refresh_stats_cache():
    """重新計算兩組統計，再原子取代舊快照；計算失敗會保留舊檔。"""
    started = time.monotonic()
    stats = queries.query_stats()
    # 覆蓋圖要全表掃 sightings_raw 嘅 lat/lon（~0.9 秒 / 296k row），
    # 所以一定要留喺呢個每小時 job，唔好落 request path。
    stats['coverage'] = queries.query_coverage()
    discover = queries.query_discover()
    snapshot = {
        'version': CACHE_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'duration_seconds': round(time.monotonic() - started, 3),
        'stats': stats,
        'discover': discover,
    }

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=CACHE_PATH.parent,
            prefix='.stats-cache-',
            suffix='.tmp',
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
            json.dump(
                snapshot,
                tmp,
                cls=DjangoJSONEncoder,
                ensure_ascii=False,
                separators=(',', ':'),
            )
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, CACHE_PATH)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

    # 同一 process 即刻讀返新 snapshot 時毋須再 parse；mtime 由檔案做真源。
    stat = CACHE_PATH.stat()
    _MEMORY_CACHE.update({'mtime_ns': stat.st_mtime_ns, 'snapshot': snapshot})
    return snapshot


def load_stats_cache():
    """讀取及驗證快照；相同 mtime 會重用 process-local JSON object。"""
    try:
        stat = CACHE_PATH.stat()
    except OSError as exc:
        raise StatsCacheUnavailable('統計 cache 未生成') from exc

    if (
        _MEMORY_CACHE['snapshot'] is not None
        and _MEMORY_CACHE['mtime_ns'] == stat.st_mtime_ns
    ):
        return _MEMORY_CACHE['snapshot']

    try:
        snapshot = json.loads(CACHE_PATH.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise StatsCacheUnavailable('統計 cache 讀取失敗') from exc

    if (
        not isinstance(snapshot, dict)
        or snapshot.get('version') != CACHE_VERSION
        or not isinstance(snapshot.get('stats'), dict)
        or not isinstance(snapshot.get('discover'), dict)
    ):
        raise StatsCacheUnavailable('統計 cache 格式或版本不符')

    _MEMORY_CACHE.update({'mtime_ns': stat.st_mtime_ns, 'snapshot': snapshot})
    return snapshot


def get_stats_section(section):
    """回傳指定 API payload 同快照生成時間。"""
    if section not in {'stats', 'discover'}:
        raise ValueError(f'未知統計 cache section: {section}')
    snapshot = load_stats_cache()
    return snapshot[section], snapshot.get('generated_at', '')
