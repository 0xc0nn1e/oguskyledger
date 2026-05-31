"""Subprocess runner — wrap 舊 src/*.py script，畀 management command 用。

過渡期方案：舊 stdlib script 用 `from db import connect` 等 relative import，
直接 import 入 Django process 會撞 PyMySQL connection pool（settings.DATABASES
已經 connect 緊一條），又會被 module-level cache 鎖住唔可以 re-run。
最 safe 嘅做法係 subprocess shell out — 同 supervisor.py 嗰套 pattern 一樣。

第二期可以將舊 logic refactor 入 tracking/services/ 同 enrichment/services/
做 import 模式，然後砍呢個 runner。
"""

import subprocess
import sys
from pathlib import Path

from django.conf import settings


def run_script(script_name, args=None, timeout=None):
    """跑 src/<script_name>，回 subprocess.CompletedProcess。

    cwd 設喺 project root，跟舊 supervisor.py 同 run_ingest.sh 嘅 pattern。
    PYTHONPATH 加 src/ 等舊 script 嘅 `from db import connect` 行得返。
    用 venv Python（sys.executable），有 PyMySQL / playwright 等依賴。
    """
    base = Path(settings.BASE_DIR)
    script_path = base / 'src' / script_name
    cmd = [sys.executable, str(script_path)]
    if args:
        cmd.extend(args)
    env = {**__import__('os').environ, 'PYTHONPATH': str(base / 'src')}
    return subprocess.run(cmd, cwd=str(base), env=env, timeout=timeout)
