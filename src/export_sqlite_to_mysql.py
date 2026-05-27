#!/usr/bin/env python3
"""
匯出 data/plane_history.sqlite3 做一個可以直接 source 入 MySQL 嘅 .sql dump。

用法：
    python3 src/export_sqlite_to_mysql.py
    mysql -u plane_history -p plane_history < data/plane_history_mysql.sql

備註：
- 假設 MySQL sql_mode 冇開 NO_BACKSLASH_ESCAPES（MySQL 8 default 冇）。
- Timestamp column 保留 VARCHAR（ISO string），咁 Python code 唔使改 datetime 處理。
- raw_json 用 LONGTEXT。
- AUTO_INCREMENT 會跟住明確寫入嘅 id / pass_id 自動推到 max+1。
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQLITE_PATH = ROOT / "data" / "plane_history.sqlite3"
OUTPUT_PATH = ROOT / "data" / "plane_history_mysql.sql"
BATCH_SIZE = 500

DDL = """\
SET NAMES utf8mb4;
SET autocommit = 0;
SET unique_checks = 0;
SET foreign_key_checks = 0;

DROP TABLE IF EXISTS sightings_raw;
CREATE TABLE sightings_raw (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  seen_at         VARCHAR(40) NOT NULL,
  receiver_name   VARCHAR(128) NOT NULL,
  source_name     VARCHAR(128) NOT NULL,
  icao            VARCHAR(16) NOT NULL,
  flight          VARCHAR(32),
  category        VARCHAR(16),
  alt_baro        DOUBLE,
  alt_geom        DOUBLE,
  gs              DOUBLE,
  track           DOUBLE,
  lat             DOUBLE,
  lon             DOUBLE,
  raw_json        LONGTEXT NOT NULL,
  KEY idx_sightings_seen_at (seen_at),
  KEY idx_sightings_icao_seen_at (icao, seen_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS aircraft_registry_cache;
CREATE TABLE aircraft_registry_cache (
  icao             VARCHAR(16) NOT NULL PRIMARY KEY,
  registration     VARCHAR(32),
  country          VARCHAR(64),
  lookup_source    VARCHAR(64),
  last_lookup_at   VARCHAR(40) NOT NULL,
  operator         VARCHAR(255),
  operator_country VARCHAR(64),
  aircraft_type    VARCHAR(16),
  fr24_id          VARCHAR(64),
  from_airport     VARCHAR(64),
  to_airport       VARCHAR(64),
  hke_notified_at  VARCHAR(40)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DROP TABLE IF EXISTS aircraft_passes;
CREATE TABLE aircraft_passes (
  pass_id      INT AUTO_INCREMENT PRIMARY KEY,
  pass_date    VARCHAR(16) NOT NULL,
  icao         VARCHAR(16) NOT NULL,
  flight       VARCHAR(32),
  operator     VARCHAR(255),
  country      VARCHAR(64),
  category     VARCHAR(16),
  first_seen   VARCHAR(40) NOT NULL,
  last_seen    VARCHAR(40) NOT NULL,
  samples      INT NOT NULL,
  min_alt_baro DOUBLE,
  max_alt_baro DOUBLE,
  min_gs       DOUBLE,
  max_gs       DOUBLE,
  KEY idx_passes_date (pass_date),
  KEY idx_passes_icao_date (icao, pass_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

START TRANSACTION;
"""

FOOTER = """\
COMMIT;
SET unique_checks = 1;
SET foreign_key_checks = 1;
"""

TABLES = [
    (
        "sightings_raw",
        [
            ("id", "int"), ("seen_at", "str"), ("receiver_name", "str"),
            ("source_name", "str"), ("icao", "str"), ("flight", "str"),
            ("category", "str"), ("alt_baro", "num"), ("alt_geom", "num"),
            ("gs", "num"), ("track", "num"), ("lat", "num"), ("lon", "num"),
            ("raw_json", "str"),
        ],
    ),
    (
        "aircraft_registry_cache",
        [
            ("icao", "str"), ("registration", "str"), ("country", "str"),
            ("lookup_source", "str"), ("last_lookup_at", "str"),
            ("operator", "str"), ("operator_country", "str"),
            ("aircraft_type", "str"), ("fr24_id", "str"),
            ("from_airport", "str"), ("to_airport", "str"),
            ("hke_notified_at", "str"),
        ],
    ),
    (
        "aircraft_passes",
        [
            ("pass_id", "int"), ("pass_date", "str"), ("icao", "str"),
            ("flight", "str"), ("operator", "str"), ("country", "str"),
            ("category", "str"), ("first_seen", "str"), ("last_seen", "str"),
            ("samples", "int"), ("min_alt_baro", "num"), ("max_alt_baro", "num"),
            ("min_gs", "num"), ("max_gs", "num"),
        ],
    ),
]


def escape_str(s):
    s = s.replace("\\", "\\\\")
    s = s.replace("'", "\\'")
    s = s.replace("\0", "\\0")
    s = s.replace("\n", "\\n")
    s = s.replace("\r", "\\r")
    s = s.replace("\x1a", "\\Z")
    return "'" + s + "'"


def fmt(v, kind):
    if v is None:
        return "NULL"
    if kind == "num":
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return repr(v)
        try:
            return repr(float(v))
        except (TypeError, ValueError):
            # SQLite stored a non-numeric string (e.g. tar1090 "ground")
            return "NULL"
    if kind == "int":
        if isinstance(v, bool):
            return "1" if v else "0"
        try:
            return str(int(v))
        except (TypeError, ValueError):
            return "NULL"
    return escape_str(str(v))


def dump_table(out, conn, table, columns):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM " + table)
    total = cur.fetchone()[0]
    sys.stderr.write("  " + table + ": " + str(total) + " rows\n")
    if total == 0:
        return

    cols_sql = ", ".join(name for name, _ in columns)
    kinds = [kind for _, kind in columns]
    cur.execute("SELECT " + cols_sql + " FROM " + table)

    batch = []
    written = 0
    insert_prefix = "INSERT INTO " + table + " (" + cols_sql + ") VALUES\n"

    for row in cur:
        batch.append("(" + ",".join(fmt(v, k) for v, k in zip(row, kinds)) + ")")
        if len(batch) >= BATCH_SIZE:
            out.write(insert_prefix)
            out.write(",\n".join(batch))
            out.write(";\n")
            written += len(batch)
            batch = []
            if written % 20000 == 0:
                sys.stderr.write("    " + str(written) + "/" + str(total) + "\n")
    if batch:
        out.write(insert_prefix)
        out.write(",\n".join(batch))
        out.write(";\n")
        written += len(batch)
    sys.stderr.write("    " + str(written) + "/" + str(total) + " done\n")


def main():
    if not SQLITE_PATH.exists():
        sys.stderr.write("找唔到 " + str(SQLITE_PATH) + "\n")
        sys.exit(1)

    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.text_factory = str

    with open(OUTPUT_PATH, "w", encoding="utf-8") as out:
        out.write(DDL)
        for table, columns in TABLES:
            sys.stderr.write("匯出 " + table + "…\n")
            dump_table(out, conn, table, columns)
        out.write(FOOTER)

    conn.close()
    size_mb = OUTPUT_PATH.stat().st_size / (1024 * 1024)
    sys.stderr.write("\n寫到 " + str(OUTPUT_PATH) + " (" + ("%.1f" % size_mb) + " MB)\n")


if __name__ == "__main__":
    main()
