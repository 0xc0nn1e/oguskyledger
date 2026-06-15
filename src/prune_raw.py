"""Retention：批次刪除超過 RETENTION_DAYS 嘅 sightings_raw。

配合 incremental build_passes（src/build_passes.py REBUILD_DAYS + BUFFER = now-4 日窗）：
舊 pass 已凍結（唔再由 raw 重砌），所以 prune 舊 raw 唔會丟失 pass 歷史。
RETENTION_DAYS **必須遠大於** build_passes 個窗（4 日），令重砌窗永遠有 raw。

每 run 批次刪（避免大 DELETE 長鎖 / binlog 爆），封頂 MAX_DELETE_PER_RUN。
初次 catch-up（清 30 日以外舊資料）分幾個 pipeline cycle 漸進完成；之後 steady-state
每 cycle 只刪啱啱過界嗰幾百行，可忽略。靠 idx_sightings_seen_at index 行得快。

注意：raw 一旦 prune，老過 retention 嘅 aircraft_passes row 仲喺（統計 / 列表齊全），
但揀佢睇 track map / profile 會冇點（query_aircraft_track 靠 sightings_raw）。
"""

import json
from datetime import datetime, timedelta, timezone

from db import connect

RETENTION_DAYS = 30        # 保留幾多日 raw（track map / profile 可回溯範圍）
BATCH = 5000               # 每批刪幾多行（鎖細、commit 之間放鎖）
MAX_DELETE_PER_RUN = 50000  # 每次 run 上限，令初次 catch-up 漸進、唔會一 run 鎖太耐

cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()

conn = connect()
cur = conn.cursor()
deleted = 0
while deleted < MAX_DELETE_PER_RUN:
    cur.execute(f'DELETE FROM sightings_raw WHERE seen_at < %s LIMIT {BATCH}', (cutoff,))
    n = cur.rowcount
    conn.commit()
    deleted += n
    if n < BATCH:
        break
conn.close()
print(json.dumps({'pruned': deleted, 'retention_days': RETENTION_DAYS, 'cutoff': cutoff}, ensure_ascii=False))
