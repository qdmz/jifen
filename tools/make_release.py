# -*- coding: utf-8 -*-
"""打发布包：把项目打成一个可以直接分发的 zip（Windows）和 tar.gz（Linux）。

    python tools/make_release.py                 # 输出到 dist/
    python tools/make_release.py --out D:/pkgs
    python tools/make_release.py --no-zip

产物结构：
    jifen-1.1.0/
        install.bat / install.sh / jifenctl.* / app.py / jifen.py / web/ ...
        docs/ tools/ VERSION

不打包：data/ logs/ dist/ config.json .git/ __pycache__/ 以及任何 *.db *.log
（所以不会把别人的数据、密码、日志带出去）
"""
import os
import sys
import hashlib
import argparse
import tarfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {'.git', 'data', 'logs', 'dist', '__pycache__', '.idea', '.vscode',
             'node_modules', '.pytest_cache', '.mypy_cache'}
SKIP_FILES = {'config.json'}
SKIP_EXT = {'.pyc', '.pyo', '.db', '.db-wal', '.db-shm', '.log', '.zip', '.tar.gz'}


def version():
    try:
        with open(os.path.join(ROOT, 'VERSION'), 'r', encoding='utf-8') as fh:
            return fh.read().strip() or '0.0.0'
    except Exception:
        return '0.0.0'


def collect():
    """返回 [(绝对路径, 包内相对路径)]"""
    out = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f in SKIP_FILES:
                continue
            if any(f.endswith(e) for e in SKIP_EXT):
                continue
            if f.startswith('~$') or f.endswith('.bak'):
                continue
            p = os.path.join(base, f)
            rel = os.path.relpath(p, ROOT).replace('\\', '/')
            out.append((p, rel))
    out.sort(key=lambda x: x[1])
    return out


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def human(n):
    for u in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or u == 'GB':
            return '%.1f %s' % (n, u) if u != 'B' else '%d B' % n
        n /= 1024.0


def main():
    ap = argparse.ArgumentParser(description='打发布包（zip + tar.gz）')
    ap.add_argument('--out', default=os.path.join(ROOT, 'dist'))
    ap.add_argument('--no-zip', action='store_true')
    ap.add_argument('--no-tar', action='store_true')
    a = ap.parse_args()

    ver = version()
    top = 'jifen-%s' % ver
    os.makedirs(a.out, exist_ok=True)
    files = collect()
    if not files:
        print('没有可打包的文件')
        return 1

    required = ['app.py', 'jifen.py', 'install.bat', 'install.sh',
                'jifenctl.bat', 'jifenctl.sh', 'web/jifen.html', 'web/jifen-admin.html',
                'web/_shared/js/echarts.min.js']
    have = {rel for _, rel in files}
    missing = [r for r in required if r not in have]
    if missing:
        print('缺少必需文件：%s' % ', '.join(missing))
        return 1

    results = []
    if not a.no_zip:
        p = os.path.join(a.out, '%s.zip' % top)
        with zipfile.ZipFile(p, 'w', zipfile.ZIP_DEFLATED) as z:
            for src, rel in files:
                z.write(src, '%s/%s' % (top, rel))
        results.append(p)
    if not a.no_tar:
        p = os.path.join(a.out, '%s.tar.gz' % top)
        with tarfile.open(p, 'w:gz') as t:
            for src, rel in files:
                t.add(src, arcname='%s/%s' % (top, rel))
        results.append(p)

    print('')
    print('版本 %s ｜ %d 个文件' % (ver, len(files)))
    for p in results:
        print('  %-52s %8s  sha256=%s' % (p, human(os.path.getsize(p)), sha256(p)[:16] + '…'))
    print('')
    print('分发后：')
    print('  Windows : 解压 → 双击 install.bat')
    print('  Linux   : 解压 → cd %s → sudo sh install.sh' % top)
    return 0


if __name__ == '__main__':
    sys.exit(main() or 0)
