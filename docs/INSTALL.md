# 一键安装部署手册

> 拿到项目之后，只跑一个脚本就能用：建库、建管理员、装开机自启、启动、自检，全程不需要 `pip install`。
> 手工部署、Nginx、数据迁移等更细的内容见 [DEPLOY.md](DEPLOY.md)；日常怎么用见 [USAGE.md](USAGE.md)。

---

## 0. 30 秒版

| 系统 | 一条命令 |
| --- | --- |
| **Windows** | 双击 `install.bat`（或在 cmd 里执行 `install.bat`） |
| **Linux / macOS** | `sudo sh install.sh` |

装完打开 `http://127.0.0.1:8770/jifen.html` 就是村民端，`/jifen-admin.html` 是后台。
初始账号 `admin` / `jifen2026`（只在该机器首次安装时生成，写在 `logs/initial_admin.txt`，**登录后立刻改**）。

只有一个前提：**Python 3.8 及以上**。项目纯标准库，不需要任何第三方包。

---

## 1. 前提：装 Python

**Windows**

1. 打开 <https://www.python.org/downloads/windows/> 下载 3.8+ 安装包；
2. 安装第一屏**必须勾选** `Add python.exe to PATH`；
3. 装完**新开**一个 cmd 窗口，执行 `python --version` 能看到版本号即成功。

**Linux / macOS**

```bash
# Debian / Ubuntu
sudo apt update && sudo apt install -y python3
# CentOS / RHEL / Rocky
sudo yum install -y python3        # 或 dnf install -y python3
# Alpine
sudo apk add python3
# macOS：系统自带 python3，没有就 brew install python
```

检查：`python3 --version`（Windows 上是 `python --version`）。

---

## 2. Windows 安装

```bat
cd /d E:\down\jifen
install.bat
```

或者直接双击 `install.bat`。脚本会依次做 6 件事：

| 步骤 | 做什么 |
| --- | --- |
| 1 | 检查 Python 版本（低于 3.8 直接报错退出） |
| 2 | 建目录 `data\`（数据库/图片/备份）、`logs\` |
| 3 | 写 `config.json`（端口、监听地址、数据目录） |
| 4 | 建库 + 建管理员 + 预置 19 件商品/12 条规则，并打印初始密码 |
| 5 | 注册开机自启：任务计划程序 `JifenMall`（登录时启动守护进程，服务挂了自动拉起） |
| 6 | 启动服务并探活 `/api/health` |

**常用参数**

```bat
install.bat --port 8080                 换端口（默认 8770）
install.bat --host 0.0.0.0              允许局域网直连（默认只监听 127.0.0.1）
install.bat --data D:\jifen-data        数据放别的盘（默认项目内 data\）
install.bat --admin-pwd 你的密码        指定初始管理员密码
install.bat --no-service                不装开机自启，只装好并启动
install.bat --no-start                  只安装，先不启动
install.bat --help                      看全部参数
```

装完验证：

```bat
jifenctl.bat status
curl http://127.0.0.1:8770/api/health
```

---

## 3. Linux 安装

```bash
cd /opt/jifen
sudo sh install.sh                       # 默认 8770 + systemd + 开机自启
sudo sh install.sh --port 8080 --host 0.0.0.0
sudo sh install.sh --no-service          # 不装 systemd（自己用 supervisor 管）
```

脚本流程和 Windows 一样，只是第 5 步变成写 systemd 单元：

```ini
# /etc/systemd/system/jifen.service
[Unit]
Description=Jifen Mall (village points supermarket)
After=network.target

[Service]
Type=simple
User=<项目目录的属主>
WorkingDirectory=/opt/jifen
Environment=PYTHONIOENCODING=utf-8
Environment=PYTHONUTF8=1
Environment=JF_PORT=8770
Environment=JF_HOST=127.0.0.1
ExecStart=/usr/bin/python3 /opt/jifen/app.py
Restart=always
RestartSec=3
```

然后 `systemctl daemon-reload && systemctl enable --now jifen`。

> **没有 systemd 的老系统**（如某些精简容器）：脚本会退化成 `crontab @reboot` + `nohup`，并打印提示。也可以自己用 `supervisor`、`pm2` 管。
> **非 root 运行**：脚本没法写 `/etc/systemd/system/`，会打印现成的 `sudo tee ...` 命令，你复制执行一次即可。

验证：

```bash
./jifenctl.sh status
curl http://127.0.0.1:8770/api/health
```

---

## 4. 日常管理

Windows 用 `jifenctl.bat`，Linux 用 `./jifenctl.sh`，命令完全一样：

| 命令 | 作用 |
| --- | --- |
| `status` | 端口、进程、健康检查、自启状态、日志路径 |
| `start` / `stop` / `restart` | 启停（Windows 会连守护一起管） |
| `logs` | 看 `logs/app.log` 最后 40 行（`--lines 200` 可调） |
| `backup` | 在线热备份数据库到 `data/backups/manual/`（不影响读写） |
| `init` | 重新初始化（幂等：建表、补列、补管理员、补商品规则） |
| `passwd` | 重置后台密码，不给 `--pwd` 就随机生成并打印 |
| `doctor` | 体检：Python、端口占用、配置、数据库、自启 |
| `uninstall` | 卸载服务；加 `--purge` 连 `data/ logs/ config.json` 一起删 |

例：

```bat
jifenctl.bat status
jifenctl.bat backup
jifenctl.bat passwd --user admin --pwd Xy123456
jifenctl.bat logs --lines 100
jifenctl.bat doctor
```

Linux 上也可以直接用 systemd：

```bash
systemctl status jifen
journalctl -u jifen -f
```

---

## 5. 换端口 / 搬目录 / 多套并存

- **换端口**：改 `config.json` 里的 `port`，然后 `jifenctl restart`。或者重跑 `install --port 8080`。
- **搬目录**：停服务 → 整个目录拷走 → 新位置跑一次 `install.bat`（会沿用已有 `data\` 与 `config.json`，不会清数据）→ `install --service-only` 重装自启。
- **同机多套**：不同端口 + 不同目录即可。守护进程的单实例锁端口 = 服务端口 + 1000，所以两套互不干扰。
- **数据放 NAS / 别的盘**：`install --data D:\jifen-data`，备份与上传图片都会跟着走。

---

## 6. 对外发布（域名 / HTTPS）

默认只监听 `127.0.0.1`，对外推荐两种方式：

**A. Cloudflare Tunnel（无公网 IP 也能用，本演示站就是这套）**

```bat
:: 一次性：创建隧道并把域名指过来（详见 docs/DEPLOY.md 第 6 节）
cloudflared tunnel create jifen-demo
cloudflared tunnel route dns jifen-demo jifen.example.com
:: 之后日常只要双击这个，会自动注册登录自启（任务计划程序 → JifenTunnel）
start_tunnel.bat
```

```bash
./jifenctl.sh status      # 看进程/端口/自启
```

**B. Nginx 反代 + certbot**

```nginx
server {
    listen 80;
    server_name jifen.example.com;
    client_max_body_size 6m;
    location / {
        proxy_pass http://127.0.0.1:8770;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

> `X-Forwarded-Proto` 必须传：程序据此给登录 Cookie 加 `Secure`。

---

## 7. 离线部署 / 打包分发

在有网的机器上打一个压缩包，拷到目标机器解压即装：

```bash
python tools/make_release.py
# 产物：dist/jifen-1.1.0.zip（Windows）、dist/jifen-1.1.0.tar.gz（Linux）
# 同时打印 sha256，方便核对
```

目标机器：

```bat
:: Windows
tar -xf jifen-1.1.0.zip && cd jifen-1.1.0 && install.bat
```
```bash
# Linux
tar -xzf jifen-1.1.0.tar.gz && cd jifen-1.1.0 && sudo sh install.sh
```

包内不含 `data/`、`logs/`、`config.json`、`.git`，所以不会把别人的数据和密码带出去。

---

## 8. 升级

```bat
:: Windows
stop.bat
:: 覆盖新版本文件（保留 data\ 和 config.json）
install.bat
```

```bash
# Linux
sudo systemctl stop jifen
# 覆盖新版本文件，保留 data/ 与 config.json
sudo sh install.sh
```

数据库结构变更都是 `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ADD COLUMN`，老库自动补列，不需要手工迁移。**升级前先 `jifenctl backup`**。

---

## 9. 卸载

```bat
jifenctl.bat uninstall           :: 停服务 + 删自启，保留数据
jifenctl.bat uninstall --purge   :: 连 data\ logs\ config.json 一起删
```

Linux：

```bash
sudo ./jifenctl.sh uninstall           # 停服务 + 删 systemd 单元
sudo ./jifenctl.sh uninstall --purge    # 连数据一起删
```

---

## 10. 常见问题

| 现象 | 处理 |
| --- | --- |
| `Python 3.8+ was not found` | 按第 1 节装 Python，勾 `Add to PATH`，**新开**窗口再跑 |
| `install.bat` 闪一下就没了 | 在 cmd 里 `cd` 到项目目录再执行，能看到完整报错 |
| 端口被占用（脚本已拦截） | 换端口：`install --port 8771`；或 `netstat -ano \| findstr 8770` 找到占用进程 |
| 装完打不开页面 | `jifenctl status` 看是否在线；`jifenctl logs` 看报错；Windows 防火墙是否拦了端口（仅局域网访问时才需要放行） |
| 忘记后台密码 | `jifenctl passwd --user admin --pwd 新密码`（会清掉所有登录会话） |
| Linux 上 `install.sh` 提示没权限写 systemd | 用 `sudo` 重跑；或按脚本打印的命令手工 `sudo tee` |
| 服务起来又自动退出 | `jifenctl logs`，多半是端口被占或 `data` 目录无写权限 |
| 装了自启但重启后没起来 | Windows：任务计划程序里看 `JifenMall` 是否被禁用；Linux：`systemctl is-enabled jifen` |
| 想在本机再装一套试用 | 换端口 + 换目录，`install --port 8771 --data D:\jifen-test`，两套互不影响 |
