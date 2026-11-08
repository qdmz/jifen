#!/bin/sh
# ============================================================
#  积分超市 · 一键安装（Linux / macOS）
#
#    sudo sh install.sh                     默认 8770 端口，装 systemd 并启动
#    sh install.sh --port 8080 --host 0.0.0.0
#    sh install.sh --no-service             不装开机自启
#    sh install.sh --help
#
#  说明文档：docs/INSTALL.md
# ============================================================
set -eu
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo ""
  echo "[x] 没找到 python3。先装："
  echo "    Debian/Ubuntu : sudo apt update && sudo apt install -y python3"
  echo "    CentOS/RHEL   : sudo yum install -y python3"
  echo "    Alpine        : sudo apk add python3"
  echo ""
  exit 1
fi

exec "$PY" tools/setup.py install "$@"
