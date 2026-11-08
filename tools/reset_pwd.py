# -*- coding: utf-8 -*-
"""重置/新建后台账号（忘记密码时用）。

用法：
    python tools/reset_pwd.py                      # 重置 admin 为随机密码并打印
    python tools/reset_pwd.py --user admin --pwd 123456
    python tools/reset_pwd.py --list               # 只看有哪些账号
    python tools/reset_pwd.py --db data/jifen.db
"""
import os
import sys
import argparse
import sqlite3
import secrets

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import app                                    # noqa: E402


def main():
    ap = argparse.ArgumentParser(description='重置积分超市后台账号密码')
    ap.add_argument('--db', default='', help='数据库路径（默认取 config.json / data/jifen.db）')
    ap.add_argument('--user', default='admin')
    ap.add_argument('--pwd', default='')
    ap.add_argument('--list', action='store_true')
    args = ap.parse_args()

    if args.db:
        app.DB_FILE = os.path.abspath(args.db)
    conn = app.db_conn()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS app_users (id TEXT PRIMARY KEY, username TEXT UNIQUE,"
                     " pwd TEXT, name TEXT, role TEXT, created TEXT)")
        conn.commit()
        if args.list:
            for r in conn.execute("SELECT username,name,role,created FROM app_users ORDER BY role"):
                print('%-16s %-12s %-8s %s' % (r['username'], r['name'], r['role'], r['created']))
            return 0
        pwd = args.pwd or secrets.token_urlsafe(9)
        row = conn.execute("SELECT * FROM app_users WHERE username=?", (args.user,)).fetchone()
        if row:
            conn.execute("UPDATE app_users SET pwd=? WHERE id=?", (app.hash_pwd(pwd), row['id']))
        else:
            conn.execute("INSERT INTO app_users(id,username,pwd,name,role,created) VALUES(?,?,?,?,?,?)",
                         ('u_' + secrets.token_hex(4), args.user, app.hash_pwd(pwd),
                          args.user, 'admin',
                          __import__('time').strftime('%Y-%m-%d %H:%M:%S')))
        conn.execute("DELETE FROM app_sessions")
        conn.commit()
    finally:
        conn.close()
    print('账号：%s' % args.user)
    print('密码：%s' % pwd)
    print('（已清除全部登录会话，请用新密码重新登录）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
