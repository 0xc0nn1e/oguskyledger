"""Push 規則 helper — src/ingest.py 同 src/browser_bulk_backfill.py 共用。

push_rules 表正路由 Django migration（notifications app）同 init_db.py 建 + seed。
ensure_push_rules() 淨係 CREATE TABLE IF NOT EXISTS（防 load_enabled_rules
SELECT 唔到表），**唔 seed**——seed（預設 HK Express）係 one-time setup 嘅事，
唔放喺呢個每 cycle 又俾 ingest + backfill 兩個 job 並發 call 嘅 hot path：
  (a) 兩個 process 同時見到「冇表」會 double-seed（競態）；
  (b) 用戶刪晒 rule 之後又會翻生。

Rule = (label, [callsign 前綴...])。callsign 中咗任何一條 enabled rule 嘅前綴
就 match，回個 label 俾 push message 用。
"""


def ensure_push_rules(conn):
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS push_rules (
          id INT AUTO_INCREMENT PRIMARY KEY,
          label VARCHAR(64) NOT NULL,
          callsign_prefixes VARCHAR(128) NOT NULL,
          enabled TINYINT(1) NOT NULL DEFAULT 1
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""
    )
    conn.commit()


def load_enabled_rules(conn):
    """回 [(label, [prefix, ...]), ...]，只係 enabled 嗰啲。"""
    cur = conn.cursor()
    cur.execute("SELECT label, callsign_prefixes FROM push_rules WHERE enabled = 1 ORDER BY id")
    out = []
    for label, prefixes in cur.fetchall():
        plist = [p.strip().upper() for p in (prefixes or '').split(',') if p.strip()]
        if plist:
            out.append((label, plist))
    return out


def match_rule(callsign, rules):
    """callsign 中邊條 rule 就回個 label，冇就 None。"""
    if not callsign:
        return None
    cs = callsign.strip().upper()
    for label, prefixes in rules:
        if any(cs.startswith(p) for p in prefixes):
            return label
    return None
