#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""积分超市 · 一键安装 / 部署 / 管理（Windows + Linux 共用，纯标准库）

常用：
    python tools/setup.py install                 # 一键安装（写配置 → 建库 → 装自启 → 启动 → 探活）
    python tools/setup.py install --port 8080 --host 0.0.0.0
    python tools/setup.py install --no-service    # 不装开机自启，只装好并启动
    python tools/setup.py ctl start|stop|restart|status|logs|backup|init|passwd|uninstall
    python tools/setup.py doctor                  # 体检：Python / 端口 / 配置 / 数据库 / 服务状态
    python tools/setup.py uninstall [--purge]     # 卸载（--purge 连数据一起删）

设计要点：
    · 只用标准库，装完即可跑，不需要 pip；
    · Windows 自启用「任务计划程序」登入时启动 watchdog（pythonw 无窗口）；
    · Linux 自启用 systemd（无 systemd 时退化为 nohup + crontab @reboot）；
    · 所有路径都相对项目根目录推导，整个目录可以随便挪。
"""
import os
import re
import sys
import json
import time
import glob
import stat
import shutil
import socket
import sqlite3
import argparse
import platform
import subprocess
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, 'app.py')
CONFIG = os.path.join(ROOT, 'config.json')
DATA = os.path.join(ROOT, 'data')
LOGS = os.path.join(ROOT, 'logs')
WIN_TASK = 'JifenMall'
LINUX_UNIT = 'jifen'
UNIT_PATH = '/etc/systemd/system/%s.service' % LINUX_UNIT
IS_WIN = os.name == 'nt'
PY = sys.executable


def _ver():
    try:
        with open(os.path.join(ROOT, 'VERSION'), 'r', encoding='utf-8') as fh:
            return fh.read().strip() or '0.0.0'
    except Exception:
        return '0.0.0'


VERSION = _ver()


# ---------------------------------------------------------------- 输出
def out(msg=''):
    try:
        print(msg, flush=True)
    except Exception:
        print(str(msg).encode('utf-8', 'replace').decode('utf-8', 'replace'), flush=True)


def step(n, msg):
    out('\n[%d] %s' % (n, msg))


def ok(msg):
    out('    √ %s' % msg)


def warn(msg):
    out('    ! %s' % msg)


def die(msg, code=1):
    out('\n    × %s\n' % msg)
    sys.exit(code)


def hr(ch='='):
    out(ch * 64)


def run(cmd, check=True, quiet=True, timeout=180):
    """执行外部命令，返回 (rc, 输出)"""
    try:
        p = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout)
    except FileNotFoundError:
        return 127, '命令不存在：%s' % cmd[0]
    except PermissionError:
        return 13, '权限不足或被安全策略拦截：%s' % cmd[0]
    except OSError as e:
        return 13, '无法执行 %s：%s' % (cmd[0], e)
    except subprocess.TimeoutExpired:
        return 124, '命令超时：%s' % ' '.join(cmd)
    txt = p.stdout.decode('utf-8', 'replace') if p.stdout else ''
    if not quiet and txt:
        out(txt.rstrip())
    if check and p.returncode != 0:
        warn('命令失败(%d)：%s\n%s' % (p.returncode, ' '.join(cmd), txt.strip()))
    return p.returncode, txt


# ---------------------------------------------------------------- 配置
DEFAULT_CFG = {
    '_说明': '安装脚本生成。改端口/路径只需改这里，改完重启服务（jifenctl restart）。',
    'host': '127.0.0.1',
    'port': 8770,
    'db': '',
    'data_dir': '',
    'admin_password': '',
}


def read_cfg():
    cfg = dict(DEFAULT_CFG)
    if os.path.isfile(CONFIG):
        try:
            with open(CONFIG, 'r', encoding='utf-8') as fh:
                cfg.update(json.load(fh) or {})
        except Exception as e:
            warn('config.json 解析失败（将按默认值处理）：%s' % e)
    return cfg


def write_cfg(port=None, host=None, data_dir=None, admin_pwd=None):
    cfg = read_cfg()
    if port:
        cfg['port'] = int(port)
    if host:
        cfg['host'] = host
    if data_dir is not None:
        cfg['data_dir'] = data_dir
    if admin_pwd:
        cfg['admin_password'] = admin_pwd
    if os.path.isfile(CONFIG):
        try:
            shutil.copy2(CONFIG, CONFIG + '.bak')
        except Exception:
            pass
    with open(CONFIG, 'w', encoding='utf-8') as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
        fh.write('\n')
    return cfg


def cfg_port(cfg=None):
    cfg = cfg or read_cfg()
    return int(cfg.get('port') or 8770)


def cfg_host(cfg=None):
    cfg = cfg or read_cfg()
    return cfg.get('host') or '127.0.0.1'


def local_url(port=None):
    port = port or cfg_port()
    h = cfg_host()
    if h in ('0.0.0.0', '::', '::0'):
        h = '127.0.0.1'
    return 'http://%s:%d' % (h, port)


# ---------------------------------------------------------------- 探活
def health(port=None, timeout=3):
    """返回 dict（含 version）或 None"""
    url = local_url(port) + '/api/health'
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8', 'replace'))
    except Exception:
        return None


def wait_health(port=None, seconds=30):
    t0 = time.time()
    while time.time() - t0 < seconds:
        h = health(port)
        if h and h.get('status') == 'ok':
            return h
        time.sleep(1)
    return None


def port_busy(port):
    s = socket.socket()
    s.settimeout(1)
    try:
        return s.connect_ex(('127.0.0.1', int(port))) == 0
    finally:
        s.close()


def port_owner(port):
    """判断端口上是谁：'self' 本目录实例 / 'other' 别的服务（含别的积分超市实例）/ 'free'"""
    if not port_busy(port):
        return 'free'
    pid, _ = read_pid()
    if pid and health(port):
        return 'self'
    if health(port):
        return 'other'      # 有 /api/health 响应但不是本目录起的（多半是另一份部署）
    return 'other'


def read_pid():
    """logs/app.pid → (pid, port)"""
    p = os.path.join(LOGS, 'app.pid')
    try:
        with open(p, 'r', encoding='utf-8') as fh:
            parts = fh.read().split()
        return int(parts[0]), (int(parts[1]) if len(parts) > 1 else 0)
    except Exception:
        return 0, 0


def tail(path, n=40):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as fh:
            lines = fh.readlines()
        return ''.join(lines[-n:]).rstrip()
    except Exception:
        return ''


# ---------------------------------------------------------------- 初始化
def ensure_dirs():
    for d in (DATA, LOGS, os.path.join(DATA, 'backups'), os.path.join(DATA, 'uploads', 'jf')):
        os.makedirs(d, exist_ok=True)


def init_db():
    """调用 app.py --init（建库 / 建管理员 / 预置商品规则），返回输出文本"""
    rc, txt = run([PY, APP, '--init'], check=False, quiet=True, timeout=180)
    return rc, txt


# ---------------------------------------------------------------- 服务：Windows
def win_pythonw():
    cand = os.path.join(os.path.dirname(PY), 'pythonw.exe')
    return cand if os.path.isfile(cand) else PY


def win_service_install():
    """任务计划程序：登入时启动 watchdog（pythonw，无窗口），由它拉 app.py"""
    tr = '"%s" "%s"' % (win_pythonw(), os.path.join(ROOT, 'watchdog.py'))
    rc, txt = run(['schtasks', '/Create', '/F', '/TN', WIN_TASK, '/SC', 'ONLOGON',
                   '/TR', tr, '/RL', 'LIMITED'], check=False)
    return rc == 0, txt.strip()


def win_service_remove():
    rc, txt = run(['schtasks', '/Delete', '/F', '/TN', WIN_TASK], check=False)
    return rc == 0, txt.strip()


def win_service_state():
    rc, txt = run(['schtasks', '/Query', '/TN', WIN_TASK, '/FO', 'LIST'], check=False)
    if rc != 0:
        return '未注册'
    m = re.search(r'(?im)^\s*(状态|Status)\s*[:：]\s*(.+)$', txt)
    return ('已注册 · %s' % m.group(2).strip()) if m else '已注册'


# ---------------------------------------------------------------- 服务：Linux
def linux_owner():
    try:
        import pwd
        return pwd.getpwuid(os.stat(ROOT).st_uid).pw_name
    except Exception:
        return os.environ.get('USER') or 'root'


def linux_unit_text():
    cfg = read_cfg()
    user = linux_owner() if os.geteuid() == 0 else ''
    lines = [
        '[Unit]',
        'Description=Jifen Mall (village points supermarket) v%s' % VERSION,
        'After=network.target',
        '',
        '[Service]',
        'Type=simple',
    ]
    if user:
        lines.append('User=%s' % user)
        lines.append('Group=%s' % user)
    lines += [
        'WorkingDirectory=%s' % ROOT,
        'Environment=PYTHONIOENCODING=utf-8',
        'Environment=PYTHONUTF8=1',
        'Environment=JF_PORT=%d' % cfg_port(cfg),
        'Environment=JF_HOST=%s' % cfg_host(cfg),
        'ExecStart=%s %s' % (PY, APP),
        'Restart=always',
        'RestartSec=3',
        'StandardOutput=append:%s' % os.path.join(LOGS, 'stdout.log'),
        'StandardError=append:%s' % os.path.join(LOGS, 'stderr.log'),
        '',
        '[Install]',
        'WantedBy=multi-user.target',
        '',
    ]
    return '\n'.join(lines)


def have_systemd():
    return os.path.isdir('/run/systemd/system') and shutil.which('systemctl') is not None


def linux_service_install():
    """写 systemd unit 并启用；无 systemd 时退化为 crontab @reboot"""
    if have_systemd() and os.geteuid() == 0:
        with open(UNIT_PATH, 'w', encoding='utf-8') as fh:
            fh.write(linux_unit_text())
        run(['systemctl', 'daemon-reload'], check=False)
        rc, txt = run(['systemctl', 'enable', '--now', LINUX_UNIT], check=False)
        return rc == 0, 'systemd unit 已写入 %s\n%s' % (UNIT_PATH, txt.strip())
    if have_systemd():
        return False, ('没有 root 权限，无法写 %s。请用 sudo 重跑，或手工执行：\n'
                       'sudo tee %s <<\'EOF\'\n%sEOF\n'
                       'sudo systemctl daemon-reload && sudo systemctl enable --now %s'
                       % (UNIT_PATH, UNIT_PATH, linux_unit_text(), LINUX_UNIT))
    # 无 systemd：crontab @reboot + nohup
    line = '@reboot cd %s && %s %s >> %s 2>&1' % (
        ROOT, PY, APP, os.path.join(LOGS, 'stdout.log'))
    if shutil.which('crontab'):
        rc, cur = run(['crontab', '-l'], check=False)
        body = cur if rc == 0 else ''
        if 'jifen-mall' not in body:
            body = body.rstrip('\n') + '\n# jifen-mall\n' + line + '\n'
            p = subprocess.run(['crontab', '-'], input=body.encode('utf-8'))
            return p.returncode == 0, ('无 systemd，已写入 crontab @reboot：\n%s' % line)
    return False, ('当前环境没有 systemd/crontab，请自行用 supervisor、pm2 或 '
                   'nohup %s %s & 常驻' % (PY, APP))


def linux_service_remove():
    if have_systemd() and os.geteuid() == 0:
        run(['systemctl', 'disable', '--now', LINUX_UNIT], check=False)
        try:
            os.remove(UNIT_PATH)
        except Exception:
            pass
        run(['systemctl', 'daemon-reload'], check=False)
        return True, 'systemd unit 已移除'
    if shutil.which('crontab'):
        rc, cur = run(['crontab', '-l'], check=False)
        if rc == 0 and '# jifen-mall' in cur:
            keep, skip = [], False
            for ln in cur.splitlines():
                if ln.strip() == '# jifen-mall':
                    skip = True
                    continue
                if skip:
                    skip = False
                    continue
                keep.append(ln)
            subprocess.run(['crontab', '-'], input=('\n'.join(keep) + '\n').encode('utf-8'))
            return True, 'crontab 条目已移除'
    return False, '未发现可移除的自启配置（可能不是本脚本装的）'


def linux_service_state():
    if have_systemd() and os.path.exists(UNIT_PATH):
        rc, txt = run(['systemctl', 'is-active', LINUX_UNIT], check=False)
        return 'systemd · %s' % txt.strip()
    if shutil.which('crontab'):
        rc, cur = run(['crontab', '-l'], check=False)
        if rc == 0 and '# jifen-mall' in cur:
            return 'crontab @reboot'
    return '未注册'


# ---------------------------------------------------------------- 启停
def start(bg=True):
    """启动服务：Windows 用 pythonw 起 watchdog；Linux 优先 systemctl，否则 nohup"""
    o = port_owner(cfg_port())
    if o == 'self':
        ok('服务已在运行（%s）' % local_url())
        return True
    if o == 'other':
        warn('端口 %d 上已有别的程序在响应，无法启动；改 config.json 的 port 或先停掉它'
             % cfg_port())
        return False
    if not IS_WIN and have_systemd() and os.path.exists(UNIT_PATH):
        rc, txt = run(['systemctl', 'start', LINUX_UNIT], check=False)
        if rc == 0:
            return bool(wait_health(seconds=30))
        warn('systemctl start 失败：%s' % txt.strip())
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    if IS_WIN:
        kw = {'cwd': ROOT, 'env': env, 'close_fds': True,
              'creationflags': 0x00000008 | 0x00000200}
        subprocess.Popen([win_pythonw(), os.path.join(ROOT, 'watchdog.py')], **kw)
    else:
        log = open(os.path.join(LOGS, 'stdout.log'), 'ab')
        subprocess.Popen([PY, APP], cwd=ROOT, env=env, stdout=log, stderr=log,
                         start_new_session=True)
    return bool(wait_health(seconds=30))


def stop():
    rc, txt = run([PY, os.path.join(ROOT, 'tools', 'stop_app.py')], check=False, quiet=False)
    if not IS_WIN and have_systemd() and os.path.exists(UNIT_PATH):
        run(['systemctl', 'stop', LINUX_UNIT], check=False)
    stopped = not health()
    if stopped and rc != 0:
        ok('服务已停止（日志里那条 PID 记录是上一次异常退出的残留，已无视）')
    return rc == 0 or stopped


def restart():
    stop()
    time.sleep(1)
    return start()


# ---------------------------------------------------------------- 备份
def backup():
    cfg = read_cfg()
    db = cfg.get('db') or os.path.join(cfg.get('data_dir') or DATA, 'jifen.db')
    if not os.path.isfile(db):
        warn('数据库不存在：%s' % db)
        return None
    d = os.path.join(cfg.get('data_dir') or DATA, 'backups', 'manual')
    os.makedirs(d, exist_ok=True)
    dest = os.path.join(d, 'jifen-%s.db' % time.strftime('%Y%m%d-%H%M%S'))
    src = sqlite3.connect('file:%s?mode=ro' % db.replace('\\', '/'), uri=True)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return dest


# ---------------------------------------------------------------- 卸载
def uninstall(purge=False):
    out('\n卸载积分超市…')
    try:
        stop()
        ok('服务已停止')
    except Exception as e:
        warn('停止服务失败：%s' % e)
    if IS_WIN:
        done, msg = win_service_remove()
    else:
        done, msg = linux_service_remove()
    ok('自启项已移除') if done else warn('自启项移除未成功：%s' % msg)
    if purge:
        for p in (os.path.join(DATA), os.path.join(LOGS), CONFIG):
            if not os.path.exists(p):
                continue
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    os.remove(p)
                except Exception:
                    pass
        ok('数据与配置已删除（data/ logs/ config.json）')
    else:
        ok('数据保留：data/  logs/  config.json（如需删除加 --purge）')
    out('\n完成。项目文件本身仍在：%s\n' % ROOT)


# ---------------------------------------------------------------- 状态输出
def print_status():
    cfg = read_cfg()
    port = cfg_port(cfg)
    pid, pport = read_pid()
    h = health(port)
    out('')
    hr()
    out('积分超市 v%s   %s' % (VERSION, ROOT))
    hr()
    out('监听        : %s:%d' % (cfg_host(cfg), port))
    out('访问地址    : %s/jifen.html   （后台 %s/jifen-admin.html）'
        % (local_url(port), local_url(port)))
    out('数据库      : %s' % (cfg.get('db') or os.path.join(cfg.get('data_dir') or DATA, 'jifen.db')))
    out('进程        : %s' % ('PID %d' % pid if pid else '未记录'))
    out('健康检查    : %s' % ('在线 · ' + json.dumps(h, ensure_ascii=False) if h else '离线'))
    out('自启        : %s' % (win_service_state() if IS_WIN else linux_service_state()))
    out('日志        : %s' % os.path.join(LOGS, 'app.log'))
    hr()
    return 0 if h else 1


# ---------------------------------------------------------------- 体检
def doctor():
    problems = []
    out('')
    hr()
    out('环境体检 · jifen v%s · %s' % (VERSION, platform.platform()))
    hr()
    out('Python      : %s (%s)' % (platform.python_version(), PY))
    if sys.version_info < (3, 8):
        problems.append('Python 版本低于 3.8')
    out('项目目录    : %s' % ROOT)
    out('配置文件    : %s' % ('存在' if os.path.isfile(CONFIG) else '不存在（用默认值）'))
    cfg = read_cfg()
    port = cfg_port(cfg)
    out('监听        : %s:%d' % (cfg_host(cfg), port))
    dbpath = cfg.get('db') or os.path.join(cfg.get('data_dir') or DATA, 'jifen.db')
    if os.path.isfile(dbpath):
        try:
            c = sqlite3.connect('file:%s?mode=ro' % dbpath.replace('\\', '/'), uri=True)
            accs = c.execute('SELECT COUNT(*) FROM jf_accounts').fetchone()[0]
            users = c.execute('SELECT COUNT(*) FROM app_users').fetchone()[0]
            goods = c.execute('SELECT COUNT(*) FROM jf_goods').fetchone()[0]
            c.close()
            out('数据库      : %s（账户 %d 人 / 商品 %d 件 / 后台账号 %d 个）'
                % (dbpath, accs, goods, users))
            if users == 0:
                problems.append('后台没有任何账号，执行 ctl init 或 ctl passwd 创建')
        except Exception as e:
            problems.append('数据库打不开：%s' % e)
            out('数据库      : 打开失败 %s' % e)
    else:
        out('数据库      : 不存在（首次启动会自动创建）')
    if port_busy(port):
        h = health(port)
        out('端口 %-6d: 已被占用 · %s' % (port, '是本服务' if h else '被其他程序占用'))
        if not h:
            problems.append('端口 %d 被其他程序占用，改 config.json 的 port 或腾出端口' % port)
    else:
        out('端口 %-6d: 空闲' % port)
    out('自启        : %s' % (win_service_state() if IS_WIN else linux_service_state()))
    for f in ('app.py', 'jifen.py', 'web/jifen.html', 'web/jifen-admin.html', 'web/login.html',
              'tools/stop_app.py', 'watchdog.py'):
        if not os.path.exists(os.path.join(ROOT, f)):
            problems.append('缺少文件 %s' % f)
    hr()
    if problems:
        out('发现问题 %d 个：' % len(problems))
        for p in problems:
            out('  · %s' % p)
    else:
        out('一切正常。')
    hr()
    return 0 if not problems else 1


# ---------------------------------------------------------------- 安装
def install(a):
    out('')
    hr()
    out('积分超市 · 一键安装   v%s   (%s)' % (VERSION, 'Windows' if IS_WIN else 'Linux'))
    hr()

    step(1, '检查运行环境')
    if sys.version_info < (3, 8):
        die('需要 Python 3.8 及以上，当前 %s。请升级后重试。' % platform.python_version())
    ok('Python %s（%s）' % (platform.python_version(), PY))
    ok('平台 %s' % platform.platform())
    if IS_WIN and not shutil.which('python') and not shutil.which('py'):
        warn('系统 PATH 里没有 python/py 命令，自启任务里会写死当前解释器路径（不影响运行）')

    step(2, '准备目录')
    ensure_dirs()
    ok('%s' % DATA)
    ok('%s' % LOGS)

    step(3, '写入配置 config.json')
    old = read_cfg() if os.path.isfile(CONFIG) else None
    port = a.port or (old or {}).get('port') or 8770
    host = a.host or (old or {}).get('host') or '127.0.0.1'
    owner = port_owner(port)
    if owner == 'other':
        die('端口 %d 已被别的程序占用（可能是另一份积分超市部署），换个端口重试：'
            'install --port 8771' % port)
    cfg = write_cfg(port=port, host=host,
                    data_dir=(a.data if a.data is not None else (old or {}).get('data_dir', '')),
                    admin_pwd=a.admin_pwd)
    ok('host=%s  port=%s  db=%s' % (cfg['host'], cfg['port'],
                                    cfg.get('db') or cfg.get('data_dir') or './data'))

    step(4, '初始化数据库（建库 / 建管理员 / 预置商品与规则）')
    rc, txt = init_db()
    for line in txt.splitlines():
        if line.strip():
            out('    ' + line.replace(PY, 'python'))
    if rc != 0:
        die('初始化失败（退出码 %d），请看上面的输出或 logs/app.log' % rc)
    ok('数据库就绪')

    if a.no_service:
        step(5, '跳过开机自启（--no-service）')
    else:
        step(5, '注册开机自启')
        if IS_WIN:
            done, msg = win_service_install()
            if done:
                ok('任务计划程序：%s（登入时启动 watchdog，掉线自动拉起）' % WIN_TASK)
            else:
                warn('注册失败，可稍后用管理员 PowerShell 重试：install --service-only\n%s' % msg)
        else:
            done, msg = linux_service_install()
            if done:
                ok(msg.splitlines()[0])
            else:
                warn(msg)

    if a.no_start:
        step(6, '跳过启动（--no-start）')
    else:
        step(6, '启动服务并探活')
        if port_owner(port) == 'self':
            ok('已在运行，无需重复启动')
        else:
            if not start():
                warn('启动后 30 秒内没探到 /api/health，请执行 jifenctl logs 查看原因')
            else:
                ok('服务已启动')

    h = health(port)
    base = local_url(port)
    out('')
    hr()
    out('安装完成' + ('（服务在线）' if h else '（服务未确认在线）'))
    hr()
    out('村民端      : %s/jifen.html' % base)
    out('管理后台    : %s/jifen-admin.html' % base)
    out('数据库      : %s' % (cfg.get('db') or os.path.join(DATA, 'jifen.db')))
    out('日志        : %s' % os.path.join(LOGS, 'app.log'))
    pwfile = os.path.join(LOGS, 'initial_admin.txt')
    if os.path.isfile(pwfile):
        out('')
        out('后台初始账号（首次安装才有，务必登录后改密码）：')
        out(tail(pwfile, 3))
    out('')
    out('常用命令：')
    if IS_WIN:
        out('  jifenctl status        看状态')
        out('  jifenctl restart       重启')
        out('  jifenctl logs          看日志')
        out('  jifenctl backup        备份数据库')
        out('  jifenctl passwd        重置后台密码')
        out('  jifenctl uninstall     卸载（--purge 连数据删）')
    else:
        out('  ./jifenctl.sh status | restart | logs | backup | passwd | uninstall')
        out('  systemctl status %s / journalctl -u %s -f' % (LINUX_UNIT, LINUX_UNIT))
    out('')
    out('对外开放：默认只监听 127.0.0.1，用 Nginx / Cloudflare Tunnel 反代到 %d 端口。' % port)
    hr()
    return 0 if h else 0


# ---------------------------------------------------------------- ctl
def ctl(cmd, a):
    cmd = (cmd or 'status').lower()
    if cmd in ('start',):
        return 0 if start() else 1
    if cmd in ('stop',):
        return 0 if stop() else 1
    if cmd in ('restart', 'reload'):
        return 0 if restart() else 1
    if cmd in ('status', 'st'):
        return print_status()
    if cmd in ('logs', 'log'):
        out('--- logs/app.log（最后 %d 行）---' % (a.lines or 40))
        out(tail(os.path.join(LOGS, 'app.log'), a.lines or 40) or '（空）')
        w = tail(os.path.join(LOGS, 'watchdog.log'), 8)
        if w:
            out('\n--- logs/watchdog.log（最后 8 行）---')
            out(w)
        return 0
    if cmd in ('backup', 'bak'):
        p = backup()
        ok('已备份：%s' % p) if p else None
        return 0 if p else 1
    if cmd in ('init',):
        rc, txt = init_db()
        out(txt.strip())
        return rc
    if cmd in ('passwd', 'password'):
        return reset_password(a)
    if cmd in ('uninstall', 'remove'):
        uninstall(purge=a.purge)
        return 0
    if cmd in ('doctor', 'check'):
        return doctor()
    die('未知命令：%s（可用：start|stop|restart|status|logs|backup|init|passwd|uninstall|doctor）' % cmd)


def reset_password(a):
    import secrets
    user = a.user or 'admin'
    pwd = a.pwd or secrets.token_urlsafe(9)
    rc, txt = run([PY, os.path.join(ROOT, 'tools', 'reset_pwd.py'),
                   '--user', user, '--pwd', pwd], check=False, quiet=True)
    out(txt.strip())
    if rc == 0:
        out('')
        out('新密码：%s   （用户名 %s，已清除全部登录会话）' % (pwd, user))
    return rc


# ---------------------------------------------------------------- CLI
def build_parser():
    p = argparse.ArgumentParser(
        prog='setup.py',
        description='积分超市一键安装/部署/管理（Windows + Linux）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='示例：\n'
               '  python tools/setup.py install\n'
               '  python tools/setup.py install --port 8080 --host 0.0.0.0 --no-service\n'
               '  python tools/setup.py ctl status\n'
               '  python tools/setup.py doctor\n'
               '  python tools/setup.py uninstall --purge\n')
    sub = p.add_subparsers(dest='cmd')

    i = sub.add_parser('install', help='一键安装')
    i.add_argument('--port', type=int, default=None, help='监听端口（默认 8770）')
    i.add_argument('--host', default=None, help='监听地址（默认 127.0.0.1）')
    i.add_argument('--data', default=None, help='数据目录（默认 项目内 data/）')
    i.add_argument('--admin-pwd', default=None, help='初始管理员密码（默认 jifen2026）')
    i.add_argument('--no-service', action='store_true', help='不注册开机自启')
    i.add_argument('--no-start', action='store_true', help='装完不启动')
    i.add_argument('--service-only', action='store_true', help='只补装开机自启并启动')

    c = sub.add_parser('ctl', help='日常管理')
    c.add_argument('action', nargs='?', default='status',
                   help='start|stop|restart|status|logs|backup|init|passwd|uninstall|doctor')
    c.add_argument('--lines', type=int, default=40, help='logs 显示行数')
    c.add_argument('--user', default='admin')
    c.add_argument('--pwd', default='')
    c.add_argument('--purge', action='store_true', help='uninstall 时连数据一起删')

    sub.add_parser('doctor', help='环境体检')

    u = sub.add_parser('uninstall', help='卸载')
    u.add_argument('--purge', action='store_true', help='连 data/ logs/ config.json 一起删')

    sub.add_parser('version', help='看版本')
    return p


def main():
    p = build_parser()
    a = p.parse_args()
    if a.cmd == 'version':
        out('jifen %s' % VERSION)
        return 0
    if a.cmd == 'ctl':
        return ctl(a.action, a)
    if a.cmd == 'doctor':
        return doctor()
    if a.cmd == 'uninstall':
        uninstall(purge=a.purge)
        return 0
    if a.cmd == 'install':
        if getattr(a, 'service_only', False):
            if IS_WIN:
                done, msg = win_service_install()
            else:
                done, msg = linux_service_install()
            ok(msg) if done else warn(msg)
            return 0 if start() else 1
        return install(a)
    p.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
