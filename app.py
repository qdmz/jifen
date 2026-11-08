#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
积分超市 · 独立服务（纯标准库，无第三方依赖）

用法：
    python app.py                 # 默认 127.0.0.1:8770
    JF_PORT=9000 python app.py
    python app.py --port 9000 --host 0.0.0.0

目录约定：
    web/            前端静态文件（村民端 jifen.html、后台 jifen-admin.html、登录页）
    data/           数据库、上传图片、备份（JF_DATA_DIR 可改；JF_DB 可指定单个库文件）
    config.json     可选，覆盖 host / port / db / data_dir

路由：
    GET  /                       → 302 /jifen.html
    GET  /jifen.html             村民端（公开）
    GET  /jifen-admin.html       管理后台（需登录）
    GET  /api/jifen/*            业务接口（jifen.py）
    POST /api/auth/login|logout|pwd
    GET  /api/auth/me
    GET  /api/health
"""
import os
import sys
import json
import time
import hashlib
import mimetypes
import secrets
import sqlite3
import threading
import urllib.parse
import traceback
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, 'web')
LOG_DIR = os.path.join(BASE_DIR, 'logs')

# ---------------------------------------------------------------- 配置
CONFIG = {}


def load_config():
    """config.json（可选）> 环境变量 > 默认值"""
    global CONFIG
    cfg = {}
    p = os.path.join(BASE_DIR, 'config.json')
    if os.path.isfile(p):
        try:
            with open(p, 'r', encoding='utf-8') as fh:
                cfg = json.load(fh) or {}
        except Exception as e:
            print('[CFG] config.json 读取失败，忽略：%s' % e)
    data_dir = (os.environ.get('JF_DATA_DIR') or cfg.get('data_dir')
                or os.path.join(BASE_DIR, 'data'))
    db = os.environ.get('JF_DB') or cfg.get('db') or os.path.join(data_dir, 'jifen.db')
    CONFIG = {
        'host': os.environ.get('JF_HOST') or cfg.get('host') or '127.0.0.1',
        'port': int(os.environ.get('JF_PORT') or cfg.get('port') or 8770),
        'data_dir': data_dir,
        'db': db,
        'admin_password': os.environ.get('JF_ADMIN_PASSWORD') or cfg.get('admin_password') or '',
        'public_base': os.environ.get('JF_PUBLIC_BASE') or cfg.get('public_base') or '',
    }
    return CONFIG


CONFIG = load_config()
for d in (CONFIG['data_dir'], LOG_DIR, os.path.join(CONFIG['data_dir'], 'backups'),
          os.path.join(CONFIG['data_dir'], 'uploads', 'jf')):
    os.makedirs(d, exist_ok=True)

import jifen                                    # noqa: E402  业务模块（依赖上面的目录）

jifen.set_db(CONFIG['db'])
jifen.BACKUP_DIR = os.path.join(CONFIG['data_dir'], 'backups', 'jf')

DB_FILE = CONFIG['db']
AUTH_COOKIE = 'jf_sid'
SESSION_TTL = 7 * 86400                      # 7 天
PBKDF2_ITER = 120000
STATIC_ALLOW_EXT = {'.html', '.htm', '.css', '.js', '.png', '.jpg', '.jpeg', '.webp',
                    '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.txt', '.map'}
# 需要登录才能打开的页面
PROTECTED_PAGES = {'/jifen-admin.html', '/admin.html'}

_LOG_LOCK = threading.Lock()


def log(msg):
    line = '[%s] %s' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg)
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        with _LOG_LOCK:
            with open(os.path.join(LOG_DIR, 'app.log'), 'a', encoding='utf-8') as fh:
                fh.write(line + '\n')
    except Exception:
        pass


# ---------------------------------------------------------------- 数据库 / 鉴权
def db_conn():
    c = sqlite3.connect(DB_FILE, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA busy_timeout=15000')
    return c


def hash_pwd(pw):
    """PBKDF2-HMAC-SHA256（与村居管理系统同格式，可直接沿用其账号表）"""
    salt = secrets.token_hex(8)
    dk = hashlib.pbkdf2_hmac('sha256', str(pw).encode('utf-8'),
                             salt.encode('utf-8'), PBKDF2_ITER)
    return 'pbkdf2$%d$%s$%s' % (PBKDF2_ITER, salt, dk.hex())


def verify_pwd(pw, stored):
    """返回 (是否通过, 是否需要升级为 PBKDF2)"""
    stored = str(stored or '')
    if not stored:
        return False, False
    if stored.startswith('pbkdf2$'):
        try:
            _, it, salt, h = stored.split('$', 3)
            dk = hashlib.pbkdf2_hmac('sha256', str(pw).encode('utf-8'),
                                     salt.encode('utf-8'), int(it))
            return secrets.compare_digest(dk.hex(), h), False
        except Exception:
            return False, False
    # 兼容老格式：sha256(pw)[:32]
    return secrets.compare_digest(hashlib.sha256(str(pw).encode()).hexdigest()[:32], stored), True


def init_auth():
    conn = db_conn()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS app_users ("
                     "id TEXT PRIMARY KEY, username TEXT UNIQUE, pwd TEXT, name TEXT,"
                     " role TEXT, created TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS app_sessions ("
                     "sid TEXT PRIMARY KEY, user_id TEXT, created REAL, seen REAL)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_app_sessions_seen ON app_sessions(seen)")
        conn.commit()
        n = conn.execute("SELECT COUNT(*) c FROM app_users").fetchone()['c']
        if n == 0:
            pw = CONFIG.get('admin_password') or 'jifen2026'
            conn.execute("INSERT INTO app_users(id,username,pwd,name,role,created)"
                         " VALUES(?,?,?,?,?,?)",
                         ('u_admin', 'admin', hash_pwd(pw), '管理员', 'admin',
                          time.strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
            log('[AUTH] 已创建初始管理员 admin / %s （请登录后立即修改密码）' % pw)
            try:
                with open(os.path.join(LOG_DIR, 'initial_admin.txt'), 'w', encoding='utf-8') as fh:
                    fh.write('用户名：admin\n密码：%s\n首次登录后请在后台修改密码。\n' % pw)
            except Exception:
                pass
    finally:
        conn.close()


_COOKIE = {}


def get_cookie(handler, name):
    raw = handler.headers.get('Cookie') or ''
    for part in raw.split(';'):
        k, _, v = part.strip().partition('=')
        if k == name:
            return urllib.parse.unquote(v)
    return ''


def set_cookie(handler, name, value, max_age):
    cookie = '%s=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Lax' % (
        name, urllib.parse.quote(value), max_age)
    if (handler.headers.get('X-Forwarded-Proto') or '').lower() == 'https':
        cookie += '; Secure'
    handler.send_header('Set-Cookie', cookie)


def current_user(handler):
    """按 cookie 查会话（缓存 5 秒，避免每次请求都查库）"""
    sid = get_cookie(handler, AUTH_COOKIE)
    if not sid:
        return None
    now = time.time()
    hit = _COOKIE.get(sid)
    if hit and hit[1] > now:
        return hit[0]
    conn = db_conn()
    try:
        row = conn.execute(
            "SELECT u.id,u.username,u.name,u.role FROM app_sessions s "
            "JOIN app_users u ON u.id=s.user_id WHERE s.sid=?", (sid,)).fetchone()
        if not row:
            return None
        conn.execute("UPDATE app_sessions SET seen=? WHERE sid=?", (now, sid))
        conn.commit()
        user = {'id': row['id'], 'username': row['username'],
                'name': row['name'] or row['username'], 'role': row['role'] or 'admin'}
    finally:
        conn.close()
    if len(_COOKIE) > 5000:
        _COOKIE.clear()
    _COOKIE[sid] = (user, now + 5)
    return user


def drop_session(sid):
    _COOKIE.pop(sid, None)
    conn = db_conn()
    try:
        conn.execute("DELETE FROM app_sessions WHERE sid=?", (sid,))
        conn.commit()
    finally:
        conn.close()


# 登录失败限速：同 IP+用户名 5 次失败锁 5 分钟
_FAIL = {}


def login_blocked(ip, username):
    rec = _FAIL.get('%s|%s' % (ip, username))
    if not rec:
        return 0
    n, until = rec
    if until <= time.time():
        _FAIL.pop('%s|%s' % (ip, username), None)
        return 0
    return int(until - time.time()) if n >= 5 else 0


def login_fail(ip, username):
    key = '%s|%s' % (ip, username)
    n, _ = _FAIL.get(key, (0, 0))
    n += 1
    _FAIL[key] = (n, time.time() + 300)
    if len(_FAIL) > 5000:
        _FAIL.clear()


def login_ok(ip, username):
    _FAIL.pop('%s|%s' % (ip, username), None)


# ---------------------------------------------------------------- 静态文件
def static_path(url_path):
    """URL → web/ 下的真实路径；非法或不在白名单内返回 None"""
    raw = urllib.parse.unquote(url_path.split('?', 1)[0].split('#', 1)[0])
    if '..' in raw.replace('\\', '/').split('/'):
        return None
    if raw in ('', '/'):
        raw = '/jifen.html'
    ext = os.path.splitext(raw)[1].lower()
    if ext not in STATIC_ALLOW_EXT:
        return None
    p = os.path.normpath(os.path.join(WEB_DIR, raw.lstrip('/').replace('/', os.sep)))
    if not p.startswith(WEB_DIR):
        return None
    return p if os.path.isfile(p) else None


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = 'JifenMall/1.0'
    protocol_version = 'HTTP/1.1'

    # ---- 基础输出 ----
    def _headers(self, code, ctype, length, cache='no-store'):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', cache)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('Referrer-Policy', 'same-origin')

    def send_json(self, code, data, extra_headers=None):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self._headers(code, 'application/json; charset=utf-8', len(body))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, code, body, ctype, cache='no-store', extra_headers=None, name=''):
        self._headers(code, ctype, len(body), cache)
        if name:
            self.send_header('Content-Disposition',
                             "inline; filename*=UTF-8''" + urllib.parse.quote(name))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, to):
        self.send_response(302)
        self.send_header('Location', to)
        self.send_header('Content-Length', '0')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()

    def log_message(self, fmt, *args):
        log('%s %s' % (self.client_address[0], fmt % args))

    # ---- 请求入口 ----
    def do_GET(self):
        try:
            self._route('GET')
        except Exception:
            log('GET %s 异常\n%s' % (self.path, traceback.format_exc()))
            try:
                self.send_json(500, {'success': False, 'error': '服务器内部错误'})
            except Exception:
                pass

    def do_POST(self):
        try:
            self._route('POST')
        except Exception:
            log('POST %s 异常\n%s' % (self.path, traceback.format_exc()))
            try:
                self.send_json(500, {'success': False, 'error': '服务器内部错误'})
            except Exception:
                pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Length', '0')
        self.end_headers()

    # ---- 路由 ----
    def _route(self, method):
        path = urllib.parse.urlsplit(self.path).path
        if path in ('', '/'):
            return self.redirect('/jifen.html')
        if path == '/favicon.ico':
            return self.send_bytes(200, b'', 'image/x-icon', 'public, max-age=86400')
        if path == '/api/health':
            return self.send_json(200, {'status': 'ok', 'time': time.strftime('%Y-%m-%d %H:%M:%S'),
                                        'db': os.path.basename(DB_FILE)})
        if path.startswith('/api/auth/'):
            return self._auth_api(path, method)
        if path.startswith('/api/jifen/'):
            return self._jifen_api(path, method)
        if path.startswith('/uploads/jf/'):
            return self._upload(path)
        return self._static(path, method)

    def _static(self, path, method):
        if method != 'GET':
            return self.send_json(405, {'success': False, 'error': '不支持的请求方法'})
        user = current_user(self)
        self._auth = user
        if path in PROTECTED_PAGES and not user:
            return self.redirect('/login.html?next=' + urllib.parse.quote(path))
        if path == '/login.html' and user:
            return self.redirect('/jifen-admin.html')
        p = static_path(path)
        if not p:
            return self.send_bytes(404, '<h1>404 Not Found</h1>'.encode('utf-8'),
                                   'text/html; charset=utf-8')
        ctype = mimetypes.guess_type(p)[0] or 'application/octet-stream'
        if ctype.startswith('text/') or ctype in ('application/javascript', 'application/json'):
            ctype += '; charset=utf-8'
        with open(p, 'rb') as fh:
            body = fh.read()
        cache = 'no-cache' if p.endswith(('.html', '.htm')) else 'public, max-age=3600'
        return self.send_bytes(200, body, ctype, cache)

    def _upload(self, path):
        name = os.path.basename(urllib.parse.unquote(path))
        p = os.path.join(CONFIG['data_dir'], 'uploads', 'jf', name)
        if not name or not os.path.isfile(p):
            return self.send_bytes(404, b'', 'image/png')
        ctype = mimetypes.guess_type(p)[0] or 'application/octet-stream'
        with open(p, 'rb') as fh:
            return self.send_bytes(200, fh.read(), ctype, 'public, max-age=86400')

    def _jifen_api(self, path, method):
        user = current_user(self)
        self._auth = user
        jifen.set_db(DB_FILE)
        if method == 'GET':
            return jifen.handle_get(self, path)
        return jifen.handle_post(self, path)

    # ---- 鉴权接口 ----
    def _auth_api(self, path, method):
        act = path[len('/api/auth/'):]
        if act == 'me' and method == 'GET':
            user = current_user(self)
            if not user:
                return self.send_json(401, {'success': False, 'error': '未登录'})
            return self.send_json(200, {'success': True, 'user': user})
        if act == 'login' and method == 'POST':
            return self._login()
        if act == 'logout' and method == 'POST':
            sid = get_cookie(self, AUTH_COOKIE)
            if sid:
                drop_session(sid)
            body = {'success': True}
            raw = json.dumps(body).encode('utf-8')
            self._headers(200, 'application/json; charset=utf-8', len(raw))
            set_cookie(self, AUTH_COOKIE, '', 0)
            self.end_headers()
            self.wfile.write(raw)
            return
        if act == 'pwd' and method == 'POST':
            return self._change_pwd()
        return self.send_json(404, {'success': False, 'error': '接口不存在'})

    def _login(self):
        try:
            n = int(self.headers.get('Content-Length') or 0)
            data = json.loads(self.rfile.read(n).decode('utf-8', 'replace') or '{}')
        except Exception:
            return self.send_json(400, {'success': False, 'error': '请求格式错误'})
        username = str(data.get('username') or '').strip()
        password = str(data.get('password') or '')
        ip = self.client_address[0]
        wait = login_blocked(ip, username)
        if wait > 0:
            return self.send_json(429, {'success': False,
                                        'error': '尝试过于频繁，请 %d 秒后再试' % wait})
        conn = db_conn()
        try:
            row = conn.execute("SELECT * FROM app_users WHERE username=?", (username,)).fetchone()
            ok, upgrade = verify_pwd(password, row['pwd']) if row else (False, False)
            if not row or not ok:
                login_fail(ip, username)
                return self.send_json(401, {'success': False, 'error': '用户名或密码错误'})
            login_ok(ip, username)
            if upgrade:
                conn.execute("UPDATE app_users SET pwd=? WHERE id=?", (hash_pwd(password), row['id']))
            sid = secrets.token_urlsafe(24)
            now = time.time()
            conn.execute("DELETE FROM app_sessions WHERE seen < ?", (now - SESSION_TTL,))
            conn.execute("INSERT INTO app_sessions(sid,user_id,created,seen) VALUES(?,?,?,?)",
                         (sid, row['id'], now, now))
            conn.commit()
            user = {'id': row['id'], 'username': row['username'],
                    'name': row['name'] or row['username'], 'role': row['role'] or 'admin'}
        finally:
            conn.close()
        raw = json.dumps({'success': True, 'user': user}, ensure_ascii=False).encode('utf-8')
        self._headers(200, 'application/json; charset=utf-8', len(raw))
        set_cookie(self, AUTH_COOKIE, sid, SESSION_TTL)
        self.end_headers()
        self.wfile.write(raw)
        log('[AUTH] %s 登录成功（%s）' % (user['username'], ip))

    def _change_pwd(self):
        user = current_user(self)
        if not user:
            return self.send_json(401, {'success': False, 'error': '请先登录'})
        try:
            n = int(self.headers.get('Content-Length') or 0)
            data = json.loads(self.rfile.read(n).decode('utf-8', 'replace') or '{}')
        except Exception:
            return self.send_json(400, {'success': False, 'error': '请求格式错误'})
        old, new = str(data.get('old') or ''), str(data.get('new') or '')
        if len(new) < 6:
            return self.send_json(400, {'success': False, 'error': '新密码至少 6 位'})
        conn = db_conn()
        try:
            row = conn.execute("SELECT * FROM app_users WHERE id=?", (user['id'],)).fetchone()
            ok, _ = verify_pwd(old, row['pwd']) if row else (False, False)
            if not ok:
                return self.send_json(400, {'success': False, 'error': '原密码不正确'})
            conn.execute("UPDATE app_users SET pwd=? WHERE id=?", (hash_pwd(new), user['id']))
            conn.execute("DELETE FROM app_sessions WHERE user_id=? AND sid<>?",
                         (user['id'], get_cookie(self, AUTH_COOKIE)))
            conn.commit()
        finally:
            conn.close()
        _COOKIE.clear()
        return self.send_json(200, {'success': True, 'message': '密码已修改'})


def main():
    cfg = load_config()
    port, host = cfg['port'], cfg['host']
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a in ('--port', '-p') and i + 1 < len(args):
            port = int(args[i + 1])
        if a in ('--host',) and i + 1 < len(args):
            host = args[i + 1]
    init_auth()
    jifen.init()
    pid_file = os.path.join(LOG_DIR, 'app.pid')
    try:
        with open(pid_file, 'w', encoding='utf-8') as fh:
            fh.write('%d\n%d\n' % (os.getpid(), port))
    except Exception:
        pass
    httpd = ThreadingHTTPServer((host, port), Handler)
    if host in ('0.0.0.0', '::'):
        log('[WARN] 监听 0.0.0.0，局域网内可直接访问；建议用 Cloudflare Tunnel / Nginx 反代并只监听 127.0.0.1')
    log('=' * 56)
    log('积分超市已启动： http://%s:%d  （数据库 %s）' % (host, port, DB_FILE))
    log('村民端 /jifen.html   后台 /jifen-admin.html')
    log('=' * 56)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log('收到 Ctrl+C，服务退出')
    finally:
        httpd.server_close()
        try:
            os.remove(pid_file)
        except Exception:
            pass


if __name__ == '__main__':
    main()
