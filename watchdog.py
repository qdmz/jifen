# -*- coding: utf-8 -*-
"""积分超市守护进程（可选）：每 10 秒探一次 /api/health，连续 2 次失败自动拉起 app.py。

用法：
    pythonw watchdog.py            # 后台守护（Windows 无窗口）
    python watchdog.py --once      # 只检查一次，不常驻
    python watchdog.py --status    # 看服务是否在线
日志：logs/watchdog.log
"""
import os
import sys
import json
import time
import socket
import subprocess
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, 'logs', 'watchdog.log')
PID_FILE = os.path.join(ROOT, 'logs', 'watchdog.pid')
LOCK_PORT = 8799
INTERVAL = 10


def log(msg):
    line = '[%s] %s' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg)
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, 'a', encoding='utf-8') as fh:
            fh.write(line + '\n')
    except Exception:
        pass


def read_cfg():
    port, host = 8770, '127.0.0.1'
    p = os.path.join(ROOT, 'config.json')
    if os.path.isfile(p):
        try:
            cfg = json.load(open(p, encoding='utf-8'))
            port = int(cfg.get('port') or port)
            host = cfg.get('host') or host
        except Exception as e:
            log('config.json 解析失败：%s' % e)
    port = int(os.environ.get('JF_PORT') or port)
    return ('127.0.0.1' if host in ('0.0.0.0', '::') else host), port


def healthy(host, port):
    try:
        with urllib.request.urlopen('http://%s:%d/api/health' % (host, port), timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def pythonw():
    exe = sys.executable
    cand = os.path.join(os.path.dirname(exe), 'pythonw.exe')
    return cand if os.path.isfile(cand) else exe


def start_app():
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    kw = {'cwd': ROOT, 'env': env, 'close_fds': True}
    if os.name == 'nt':
        kw['creationflags'] = 0x00000008 | 0x00000200      # DETACHED_PROCESS | NEW_PROCESS_GROUP
    subprocess.Popen([pythonw(), os.path.join(ROOT, 'app.py')], **kw)
    log('已拉起 app.py（pythonw）')


def single_instance():
    s = socket.socket()
    try:
        s.bind(('127.0.0.1', LOCK_PORT))
        s.listen(1)
        return s
    except OSError:
        s.close()
        return None


def main():
    host, port = read_cfg()
    args = sys.argv[1:]
    if '--status' in args:
        ok = healthy(host, port)
        print('服务 %s:%d %s' % (host, port, '在线 ✅' if ok else '离线 ❌'))
        return 0 if ok else 1
    if '--once' in args:
        if healthy(host, port):
            print('在线')
            return 0
        start_app()
        return 0

    lock = single_instance()
    if not lock:
        log('已有守护进程在运行（锁 127.0.0.1:%d），退出' % LOCK_PORT)
        return 0
    with open(PID_FILE, 'w', encoding='utf-8') as fh:
        fh.write(str(os.getpid()))
    log('守护启动：探活 http://%s:%d/api/health（每 %d 秒）' % (host, port, INTERVAL))
    fails = 0
    while True:
        if healthy(host, port):
            if fails:
                log('服务已恢复')
            fails = 0
        else:
            fails += 1
            log('健康检查失败（连续 %d 次）' % fails)
            if fails >= 2:
                start_app()
                fails = 0
                time.sleep(8)
        time.sleep(INTERVAL)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log('守护退出')
