# -*- coding: utf-8 -*-
"""停止正在运行的积分超市（读 logs/app.pid / logs/watchdog.pid，不依赖端口扫描或进程名）。

    python tools/stop_app.py             # 先停守护，再停服务
    python tools/stop_app.py --app-only  # 只停服务（守护随后会再把它拉起来）
"""
import os
import sys
import time
import signal
import socket
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PID = os.path.join(ROOT, 'logs', 'app.pid')
WD_PID = os.path.join(ROOT, 'logs', 'watchdog.pid')


def read_pid(path):
    try:
        parts = open(path, encoding='utf-8').read().split()
        return int(parts[0]), (int(parts[1]) if len(parts) > 1 else 0)
    except Exception:
        return 0, 0


def http_ok(port):
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d/api/health' % port, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def port_free(port):
    s = socket.socket()
    s.settimeout(1)
    try:
        return s.connect_ex(('127.0.0.1', port)) != 0
    finally:
        s.close()


def terminate(pid, label, port=0):
    """发终止信号；用「HTTP 还能不能应答 + 端口是否释放」判断结果（Windows 上更可靠）"""
    print('停止%s进程 %d …' % (label, pid))
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        print('  进程不存在或无权终止：%s' % e)
        return False
    for _ in range(20):
        time.sleep(0.25)
        if port:
            if not http_ok(port) and port_free(port):
                return True
        else:
            return True
    return False


def main():
    app_only = '--app-only' in sys.argv
    if not app_only:
        wd, _ = read_pid(WD_PID)
        if wd:
            if terminate(wd, '守护'):
                print('  守护已停（不会再自动拉起）')
            try:
                os.remove(WD_PID)
            except Exception:
                pass
        else:
            print('（守护未在运行）')

    pid, port = read_pid(PID)
    if not pid:
        print('没有找到 logs/app.pid，服务可能未启动。')
        return 0
    ok = terminate(pid, '服务', port)
    try:
        os.remove(PID)
    except Exception:
        pass
    if ok:
        print('已停止。')
        return 0
    print('未能确认停止，请查看 logs/app.log 或手动结束进程 %d' % pid)
    return 1


if __name__ == '__main__':
    sys.exit(main())
