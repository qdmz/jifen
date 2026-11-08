#!/bin/sh
# ============================================================
#  积分超市 · 管理命令（Linux / macOS）
#    ./jifenctl.sh status | start | stop | restart
#    ./jifenctl.sh logs [--lines 100] | backup | init
#    ./jifenctl.sh passwd [--user admin] [--pwd NEW]
#    ./jifenctl.sh uninstall [--purge]
#    ./jifenctl.sh doctor
# ============================================================
set -eu
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "[x] 需要 python3"
  exit 1
fi

exec "$PY" tools/setup.py ctl "$@"
