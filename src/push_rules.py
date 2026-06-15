"""Push 規則 helper — src/ingest.py 同 src/browser_bulk_backfill.py 共用。

push_rules 表正路由 Django migration（notifications app）同 init_db.py 建 + seed。
ensure_push_rules() 淨係 CREATE TABLE IF NOT EXISTS（+ 補 match_type 欄），**唔 seed**
——seed（預設 HK Express）係 one-time setup 嘅事，唔放喺呢個每 cycle 又俾 ingest +
backfill 兩個 job 並發 call 嘅 hot path：
  (a) 兩個 process 同時見到「冇表」會 double-seed（競態）；
  (b) 用戶刪晒 rule 之後又會翻生。

Rule = (label, match_type, [值...])。match_type 話 match 邊個欄：
  callsign / icao / registration / type → startswith（code-like 前綴）
  route（比 from 同 to）/ country → substring（contains）
callsign / icao 由 live feed 直接攞到（平路）；其餘要 aircraft_registry_cache enrichment。
"""


# 平路 match_type：唔使查 registry，live feed 直接有
_CHEAP_TYPES = {'callsign', 'icao'}
# substring（contains）match 嘅 type；其餘用 startswith
_SUBSTR_TYPES = {'route', 'country'}


def ensure_push_rules(conn):
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS push_rules (
          id INT AUTO_INCREMENT PRIMARY KEY,
          label VARCHAR(64) NOT NULL,
          callsign_prefixes VARCHAR(128) NOT NULL,
          match_type VARCHAR(16) NOT NULL DEFAULT 'callsign',
          enabled TINYINT(1) NOT NULL DEFAULT 1
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""
    )
    # 舊 DB 補 match_type 欄（migration / init_db 以外嘅防禦；並發 ALTER 撞欄當已加）
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'push_rules' AND COLUMN_NAME = 'match_type'"
    )
    if cur.fetchone()[0] == 0:
        try:
            cur.execute("ALTER TABLE push_rules ADD COLUMN match_type VARCHAR(16) NOT NULL DEFAULT 'callsign'")
        except Exception:
            pass
    conn.commit()


def ensure_push_log(conn):
    """push_log（每次 push 寫一筆，畀 /push-log/ 頁睇）。CREATE IF NOT EXISTS，
    無 seed、並發安全（同 init_db / notifications migration 三路都會建）。"""
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS push_log (
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
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""
    )
    conn.commit()


def log_push(cur, pushed_at, icao, callsign, registration, label, route, http_status):
    """寫一筆 push 記錄（成敗都寫，ok = 2xx）。唔 commit——交返 caller 同 dedup state 一齊 commit。"""
    cur.execute(
        "INSERT INTO push_log (pushed_at, icao, callsign, registration, label, route, http_status, ok) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (pushed_at, icao, callsign, registration, label, route, http_status,
         1 if (http_status and 200 <= http_status < 300) else 0),
    )


def load_enabled_rules(conn):
    """回 [(label, match_type, [值, ...]), ...]，只係 enabled 嗰啲。"""
    cur = conn.cursor()
    cur.execute("SELECT label, match_type, callsign_prefixes FROM push_rules WHERE enabled = 1 ORDER BY id")
    out = []
    for label, match_type, values in cur.fetchall():
        vlist = [v.strip().upper() for v in (values or '').split(',') if v.strip()]
        if vlist:
            out.append((label, (match_type or 'callsign'), vlist))
    return out


def rules_need_registry(rules):
    """有冇 rule 要查 aircraft_registry_cache 先 match 到（即非 callsign / icao）。"""
    return any(mt not in _CHEAP_TYPES for _, mt, _ in rules)


def match_rule(fields, rules):
    """fields = {callsign, icao, registration, type, from, to, country}。

    中邊條 enabled rule 就回個 label，冇就 None。route 比 from 同 to 兩個。
    """
    for label, match_type, values in rules:
        cands = [fields.get('from'), fields.get('to')] if match_type == 'route' else [fields.get(match_type)]
        substr = match_type in _SUBSTR_TYPES
        for c in cands:
            if not c:
                continue
            cu = str(c).strip().upper()
            if (any(v in cu for v in values) if substr else any(cu.startswith(v) for v in values)):
                return label
    return None
