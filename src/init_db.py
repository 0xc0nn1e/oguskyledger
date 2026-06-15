"""
First-time / idempotent schema init for plane-history MySQL DB.

Safe to re-run — uses CREATE TABLE IF NOT EXISTS. Indexes are declared inline
on the table (MySQL doesn't support CREATE INDEX IF NOT EXISTS).
"""

from db import connect

DDL = [
    """
    CREATE TABLE IF NOT EXISTS sightings_raw (
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
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS aircraft_registry_cache (
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
      hke_notified_at  VARCHAR(40),
      hke_push_failed_at VARCHAR(40),
      hke_push_fail_count INT NOT NULL DEFAULT 0
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS push_rules (
      id INT AUTO_INCREMENT PRIMARY KEY,
      label VARCHAR(64) NOT NULL,
      callsign_prefixes VARCHAR(128) NOT NULL,
      match_type VARCHAR(16) NOT NULL DEFAULT 'callsign',
      enabled TINYINT(1) NOT NULL DEFAULT 1
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS push_log (
      id INT AUTO_INCREMENT PRIMARY KEY,
      pushed_at VARCHAR(40) NOT NULL,
      icao VARCHAR(16),
      callsign VARCHAR(32),
      registration VARCHAR(32),
      label VARCHAR(64),
      route VARCHAR(128),
      http_status INT,
      ok TINYINT(1) NOT NULL DEFAULT 0,
      KEY idx_push_log_pushed_at (pushed_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS aircraft_passes (
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
      from_airport VARCHAR(64),
      to_airport   VARCHAR(64),
      KEY idx_passes_date (pass_date),
      KEY idx_passes_icao_date (icao, pass_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS aircraft_route_snapshots (
      snapshot_id    INT AUTO_INCREMENT PRIMARY KEY,
      icao           VARCHAR(16) NOT NULL,
      flight         VARCHAR(32) NOT NULL,
      from_airport   VARCHAR(64),
      to_airport     VARCHAR(64),
      observed_at    VARCHAR(40) NOT NULL,
      KEY idx_snap_icao_flight (icao, flight, observed_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
      username       VARCHAR(64) NOT NULL PRIMARY KEY,
      password_hash  VARCHAR(255) NOT NULL,
      created_at     VARCHAR(40) NOT NULL,
      updated_at     VARCHAR(40) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
      token_hash  VARCHAR(64) NOT NULL PRIMARY KEY,
      username    VARCHAR(64) NOT NULL,
      created_at  VARCHAR(40) NOT NULL,
      expires_at  VARCHAR(40) NOT NULL,
      KEY idx_sessions_username (username),
      KEY idx_sessions_expires (expires_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]


conn = connect(autocommit=True)
cur = conn.cursor()
# 純 schema init（同其他表一樣只 CREATE，唔 seed）。push_rules 嘅預設
# HK Express 由 notifications migration seed（唯一 seed owner）。
for stmt in DDL:
    cur.execute(stmt)
conn.close()
print('Initialized MySQL schema (plane_history).')
