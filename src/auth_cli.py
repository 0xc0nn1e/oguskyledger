"""
plane-history account 管理 CLI。

用法：
    python3 src/auth_cli.py create <username>      # 建立新 account（會 prompt 入密碼兩次）
    python3 src/auth_cli.py passwd <username>      # 改密碼（會 prompt 入新密碼兩次）
    python3 src/auth_cli.py list                   # 列出全部 user
    python3 src/auth_cli.py delete <username>      # 刪 user 連 session
"""

import getpass
import sys

import auth
from db import connect


def _prompt_new_password():
    p1 = getpass.getpass("新密碼：")
    p2 = getpass.getpass("確認密碼：")
    if p1 != p2:
        sys.exit("✗ 兩次輸入唔同")
    if len(p1) < 6:
        sys.exit("✗ 密碼至少 6 個字")
    return p1


def cmd_create(username):
    pwd = _prompt_new_password()
    if auth.create_user(username, pwd):
        print(f"✓ 建立 user '{username}'")
    else:
        sys.exit(f"✗ user '{username}' 已經存在")


def cmd_passwd(username):
    pwd = _prompt_new_password()
    if auth.set_password(username, pwd):
        print(f"✓ '{username}' 密碼已更新")
    else:
        sys.exit(f"✗ 搵唔到 user '{username}'")


def cmd_list():
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT username, created_at, updated_at FROM users ORDER BY username")
        rows = cur.fetchall()
    finally:
        conn.close()
    if not rows:
        print("(0 user)")
        return
    print(f"{'username':<20} {'created_at':<28} {'updated_at':<28}")
    for u, c, up in rows:
        print(f"{u:<20} {c:<28} {up:<28}")


def cmd_delete(username):
    conn = connect(autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE username = %s", (username,))
        sessions_deleted = cur.rowcount
        cur.execute("DELETE FROM users WHERE username = %s", (username,))
        if cur.rowcount == 0:
            sys.exit(f"✗ 搵唔到 user '{username}'")
    finally:
        conn.close()
    print(f"✓ 刪除 user '{username}'（順手清咗 {sessions_deleted} 個 session）")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == 'create' and len(args) == 1:
        cmd_create(args[0])
    elif cmd == 'passwd' and len(args) == 1:
        cmd_passwd(args[0])
    elif cmd == 'list' and len(args) == 0:
        cmd_list()
    elif cmd == 'delete' and len(args) == 1:
        cmd_delete(args[0])
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
