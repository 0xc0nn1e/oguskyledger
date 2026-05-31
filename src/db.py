"""
MySQL connection helper for plane-history scripts.

Reads connection info from src/config.json -> mysql block.
"""

import json
from pathlib import Path

import pymysql
import pymysql.cursors

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def _load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def connect(autocommit=False):
    cfg = _load_config()["mysql"]
    return pymysql.connect(
        host=cfg["host"],
        port=int(cfg.get("port", 3306)),
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        charset="utf8mb4",
        autocommit=autocommit,
        # Reasonable defaults for this LAN-only single-machine workload。
        # read_timeout 5 分鐘：build_passes.py 全 sightings_raw scan + DELETE+INSERT
        # 可以跑 1-2 分鐘（~500k rows），30 秒會打斷。
        connect_timeout=10,
        read_timeout=300,
        write_timeout=300,
    )


def dict_cursor(conn):
    """Cursor that returns rows as dicts (drop-in for sqlite3.Row by-key access)."""
    return conn.cursor(pymysql.cursors.DictCursor)


def column_set(conn, table):
    """Return set of column names for a table. Replaces SQLite's PRAGMA table_info()."""
    cur = conn.cursor()
    cur.execute("SHOW COLUMNS FROM " + table)
    cols = {row[0] for row in cur.fetchall()}
    cur.close()
    return cols
