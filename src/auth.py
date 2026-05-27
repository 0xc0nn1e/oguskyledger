"""
Login / session helpers for plane-history web.

- 密碼用 hashlib.pbkdf2_hmac('sha256', ...) 存，格式 `pbkdf2_sha256$<iter>$<salt_hex>$<hash_hex>`。
- Session token 用 secrets.token_urlsafe(32) 生，cookie 攞 raw token，DB 只存 sha256(token)。
  咁就算 DB 被偷都唔可以直接拎 cookie 用。
- 純 stdlib（hashlib / secrets / hmac）+ pymysql via db.py。
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from db import connect, dict_cursor

PBKDF2_ITER = 200_000
SESSION_TTL = timedelta(days=30)
COOKIE_NAME = 'ph_session'


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------- 密碼 ----------

def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, PBKDF2_ITER)
    return f"pbkdf2_sha256${PBKDF2_ITER}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        algo, iter_s, salt_hex, hash_hex = stored.split('$')
    except ValueError:
        return False
    if algo != 'pbkdf2_sha256':
        return False
    try:
        iterations = int(iter_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return hmac.compare_digest(digest, expected)


# ---------- User CRUD ----------

def create_user(username, password):
    """Returns True if created, False if username already exists."""
    conn = connect(autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            return False
        now = _now_iso()
        cur.execute(
            "INSERT INTO users (username, password_hash, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s)",
            (username, hash_password(password), now, now),
        )
        return True
    finally:
        conn.close()


def set_password(username, new_password):
    """Returns True if updated, False if user doesn't exist."""
    conn = connect(autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET password_hash = %s, updated_at = %s WHERE username = %s",
            (hash_password(new_password), _now_iso(), username),
        )
        return cur.rowcount > 0
    finally:
        conn.close()


def authenticate(username, password):
    """Return True if (username, password) matches."""
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        if not row:
            # 仍然 run 一次 pbkdf2，timing 唔好洩漏 username 存唔存在
            verify_password(password, f"pbkdf2_sha256${PBKDF2_ITER}$00$00")
            return False
        return verify_password(password, row[0])
    finally:
        conn.close()


# ---------- Sessions ----------

def _hash_token(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def create_session(username):
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = now + SESSION_TTL
    conn = connect(autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO sessions (token_hash, username, created_at, expires_at) "
            "VALUES (%s, %s, %s, %s)",
            (_hash_token(token), username, now.isoformat(), expires.isoformat()),
        )
    finally:
        conn.close()
    return token, expires


def lookup_session(token):
    """Return username if token still valid, else None. Sweeps expired rows lazily."""
    if not token:
        return None
    conn = connect(autocommit=True)
    try:
        cur = dict_cursor(conn)
        cur.execute(
            "SELECT username, expires_at FROM sessions WHERE token_hash = %s",
            (_hash_token(token),),
        )
        row = cur.fetchone()
        if not row:
            return None
        if row['expires_at'] < _now_iso():
            # Expired — clean up
            cur.execute("DELETE FROM sessions WHERE token_hash = %s", (_hash_token(token),))
            return None
        return row['username']
    finally:
        conn.close()


def delete_session(token):
    if not token:
        return
    conn = connect(autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE token_hash = %s", (_hash_token(token),))
    finally:
        conn.close()


def purge_expired_sessions():
    conn = connect(autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE expires_at < %s", (_now_iso(),))
        return cur.rowcount
    finally:
        conn.close()
