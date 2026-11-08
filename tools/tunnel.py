# -*- coding: utf-8 -*-
"""积分超市 · Cloudflare Tunnel 启停（用户级，不需要管理员权限）

    python tools/tunnel.py start            启动隧道（没了就拉起来），并注册登录自启
    python tools/tunnel.py start --no-task  只启动，不注册自启
    python tools/tunnel.py stop             停止
    python tools/tunnel.py status           看状态（本地进程 + 公网 /api/health）
    python tools/tunnel.py run              前台跑（调试用）
    python tools/tunnel.py uninstall-task   删除登录自启

默认隧道配置：%USERPROFILE%\\.cloudflared\\jifen.yml（可用 JF_TUNNEL_CONFIG 覆盖）
默认任务名：JifenTunnel
"""
import os
import sys
import json
import time
import signal
import argparse
import subprocess
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.join(ROOT, 'logs')
PID_FILE = os.path.join(LOGS, 'tunnel.pid')
LOG_FILE = os.path.join(LOGS, 'tunnel.log')
TASK = os.environ.get('JF_TUNNEL_TASK') or 'JifenTunnel'
CONFIG = os.environ.get('JF_TUNNEL_CONFIG') or os.path.join(
    os.path.expanduser('~'), '.cloudflared', 'jifen.yml')
IS_WIN = os.name == 'nt'


def out(m=''):
    try:
        print(m, flush=True)
    except Exception:
        pass


def find_bin():
    cands = [os.environ.get('CLOUDFLARED') or '']
    if IS_WIN:
        cands += [r'C:\Program Files (x86)\cloudflared\cloudflared.exe',
                  r'C:\Program Files\cloudflared\cloudflared.exe']
    import shutil
    w = shutil.which('cloudflared')
    if w:
        cands.append(w)
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return ''


def pyw():
    if IS_WIN:
        c = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
        if os.path.isfile(c):
            return c
    return sys.executable


def read_pid():
    try:
        with open(PID_FILE, 'r', encoding='utf-8') as fh:
            return int(fh.read().split()[0])
    except Exception:
        return 0


def alive(pid):
    if not pid:
        return False
    if IS_WIN:
        try:
            rc = subprocess.run(['tasklist', '/FI', 'PID eq %d' % pid],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception:
            return True                      # 查不了就当作活着，避免重复起进程
        return str(pid).encode() in (rc.stdout or b'')
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def tunnel_host():
    """从 yml 里取第一个 hostname，用于公网探活"""
    try:
        with open(CONFIG, 'r', encoding='utf-8') as fh:
            for line in fh:
                s = line.strip()
                if s.startswith('- hostname:'):
                    return s.split(':', 1)[1].strip()
    except Exception:
        pass
    return ''


def public_health(host='', timeout=8):
    host = host or tunnel_host()
    if not host:
        return None
    # 必须带常规 UA：Cloudflare 会直接 403 掉 python-urllib 的默认 UA
    req = urllib.request.Request('https://%s/api/health' % host,
                                 headers={'User-Agent': 'Mozilla/5.0 (jifen-tunnel-check)',
                                          'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8', 'replace'))
    except Exception:
        return None


def ensure_logs():
    os.makedirs(LOGS, exist_ok=True)


def start(no_task=False):
    ensure_logs()
    b = find_bin()
    if not b:
        out('    × 没找到 cloudflared.exe。先安装：')
        out('      winget install --id Cloudflare.cloudflared    （或到官网下载）')
        return 1
    if not os.path.isfile(CONFIG):
        out('    × 隧道配置不存在：%s' % CONFIG)
        out('      生成方式见 docs/DEPLOY.md 第 6 节（cloudflared tunnel create / route dns）')
        return 1
    pid = read_pid()
    if alive(pid):
        out('    √ 隧道已在运行（PID %d）' % pid)
    else:
        env = dict(os.environ)
        env['PYTHONIOENCODING'] = 'utf-8'
        kw = {'stdout': open(LOG_FILE, 'ab'), 'stderr': subprocess.STDOUT,
              'stdin': subprocess.DEVNULL, 'cwd': ROOT, 'env': env}
        if IS_WIN:
            kw['creationflags'] = 0x00000008 | 0x01000000 | 0x00000200  # DETACHED|BREAKAWAY|NEW_GROUP
        else:
            kw['start_new_session'] = True
        p = subprocess.Popen([b, 'tunnel', '--config', CONFIG, '--no-autoupdate', 'run'], **kw)
        try:
            with open(PID_FILE, 'w', encoding='utf-8') as fh:
                fh.write(str(p.pid))
        except Exception:
            pass
        out('    √ 隧道进程已启动（PID %d），等待连接…' % p.pid)
        for _ in range(20):
            time.sleep(2)
            if public_health():
                break
    h = public_health()
    host = tunnel_host()
    if h:
        out('    √ 公网可用：https://%s  %s' % (host, json.dumps(h, ensure_ascii=False)))
    else:
        out('    ! https://%s 还没通，看日志：%s' % (host or '(未知域名)', os.path.join(LOGS, 'tunnel.log')))
    if no_task:
        out('    · 未注册登录自启（--no-task）')
    else:
        install_task()
    return 0 if h else 1


def install_task():
    if not IS_WIN:
        out('    · Linux 请用 systemd：见 docs/INSTALL.md「隧道常驻」')
        return 0
    tr = '"%s" "%s" run' % (pyw(), os.path.join(ROOT, 'tools', 'tunnel.py'))
    try:
        rc = subprocess.run(['schtasks', '/Create', '/F', '/TN', TASK, '/SC', 'ONLOGON',
                             '/TR', tr, '/RL', 'LIMITED'],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except Exception as e:                   # 权限不足或 schtasks 不可用
        out('    ! 注册自启失败（不影响当前运行）：%s' % e)
        return 0
    if rc.returncode == 0:
        out('    √ 已注册登录自启：任务计划程序 → %s' % TASK)
    else:
        out('    ! 注册自启失败（可忽略，手动运行 start_tunnel.bat 即可）：%s'
            % rc.stdout.decode('utf-8', 'replace').strip()[:200])
    return 0


def uninstall_task():
    if not IS_WIN:
        return 0
    try:
        rc = subprocess.run(['schtasks', '/Delete', '/F', '/TN', TASK],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except Exception as e:
        out('    ! 无法操作任务计划程序：%s' % e)
        return 0
    out('    √ 已删除自启任务 %s' % TASK) if rc.returncode == 0 else out('    · 没有自启任务 %s' % TASK)
    return 0


def stop():
    pid = read_pid()
    if not alive(pid):
        out('    · 隧道未在运行')
        return 0
    try:
        if IS_WIN:
            subprocess.run(['taskkill', '/PID', str(pid), '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.kill(pid, signal.SIGTERM)
        out('    √ 已停止隧道（PID %d）' % pid)
    except Exception as e:
        out('    ! 停止失败：%s' % e)
    try:
        os.remove(PID_FILE)
    except Exception:
        pass
    return 0


def status():
    pid = read_pid()
    host = tunnel_host()
    out('')
    out('隧道配置 : %s' % CONFIG)
    out('cloudflared: %s' % (find_bin() or '未安装'))
    out('本地进程 : %s' % ('PID %d 运行中' % pid if alive(pid) else '未运行'))
    out('公网域名 : https://%s' % (host or '(未配置)'))
    h = public_health()
    out('公网探活 : %s' % ('通 ' + json.dumps(h, ensure_ascii=False) if h else '不通'))
    if IS_WIN:
        try:
            rc = subprocess.run(['schtasks', '/Query', '/TN', TASK],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            out('登录自启 : %s' % ('已注册' if rc.returncode == 0 else '未注册'))
        except Exception:
            out('登录自启 : 无法查询（权限或环境限制）')
    return 0 if h else 1


def run_foreground():
    b = find_bin()
    if not b:
        out('cloudflared 未安装')
        return 1
    return subprocess.call([b, 'tunnel', '--config', CONFIG, '--no-autoupdate', 'run'])


def main():
    ap = argparse.ArgumentParser(description='积分超市 · Cloudflare Tunnel 管理')
    ap.add_argument('action', nargs='?', default='status',
                    choices=['start', 'stop', 'status', 'run', 'install-task', 'uninstall-task'])
    ap.add_argument('--no-task', action='store_true')
    a = ap.parse_args()
    if a.action == 'start':
        return start(no_task=a.no_task)
    if a.action == 'stop':
        return stop()
    if a.action == 'status':
        return status()
    if a.action == 'run':
        return run_foreground()
    if a.action == 'install-task':
        return install_task()
    if a.action == 'uninstall-task':
        return uninstall_task()
    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
