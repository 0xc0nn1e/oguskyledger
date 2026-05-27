"""
plane-history supervisor: 一個 long-run process 入面三條 thread。

- Main thread       : web_app HTTP server（blocking）
- Thread "ingest"   : 每 60 秒 run run_ingest.sh
- Thread "reg"      : 每 180 秒 run src/browser_bulk_backfill.py

設計重點：
- 兩條 worker thread 用 subprocess 起現有 script，避免 import 入嚟之後共享
  module global / pymysql connection / playwright event loop 嘅 thread-safety 問題。
- Pacing 係「上次 start 之後 N 秒」，唔係「上次完成之後 N 秒」，跟返 launchd
  StartInterval 嘅 semantics。如果一次 run 超時，下一次即刻接住（唔 skip）。
- Worker thread 永遠唔會 die：subprocess crash / exception 只 log 一行就繼續。
- Web 喺 main thread。Web 死整個 process 死，由 launchd KeepAlive 拉返起，
  順便 reset 埋兩條 worker，simple is good。
"""

import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "data" / "supervisor.log"

JOBS = [
    {"name": "ingest", "interval": 60, "cmd": ["bash", str(ROOT / "run_ingest.sh")]},
    {"name": "reg", "interval": 180, "cmd": [sys.executable, str(ROOT / "src" / "browser_bulk_backfill.py")]},
]


def log(event, **extra):
    payload = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **extra}
    line = json.dumps(payload, ensure_ascii=False)
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        print(f"supervisor: log write failed: {e}", file=sys.stderr, flush=True)


def run_job(job):
    next_start = time.monotonic()
    while True:
        now = time.monotonic()
        if now < next_start:
            time.sleep(next_start - now)
        start = time.monotonic()
        next_start = start + job["interval"]
        try:
            r = subprocess.run(job["cmd"], cwd=str(ROOT))
            log("job.done", job=job["name"], rc=r.returncode,
                duration_s=round(time.monotonic() - start, 2))
        except Exception as e:
            log("job.error", job=job["name"], error=repr(e),
                duration_s=round(time.monotonic() - start, 2))


def main():
    log("supervisor.start", jobs=[j["name"] for j in JOBS], pid=__import__("os").getpid())

    for job in JOBS:
        threading.Thread(target=run_job, args=(job,), name=job["name"], daemon=True).start()

    sys.path.insert(0, str(ROOT / "src"))
    from web_app import serve

    serve()


if __name__ == "__main__":
    main()
