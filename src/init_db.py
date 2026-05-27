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
      hke_notified_at  VARCHAR(40)
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
      KEY idx_passes_date (pass_date),
      KEY idx_passes_icao_date (icao, pass_date)
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
for stmt in DDL:
    cur.execute(stmt)
conn.close()
print('Initialized MySQL schema (plane_history).')
