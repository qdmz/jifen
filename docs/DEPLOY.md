# 部署手册

> 面向运维：把积分超市跑起来、用域名访问、出问题能查。
> 使用说明见 [USAGE.md](USAGE.md)。

- [1. 环境要求](#1-环境要求)
- [2. Windows 部署（推荐给村级使用）](#2-windows-部署推荐给村级使用)
- [3. 开机自启](#3-开机自启)
- [4. Linux 部署（systemd）](#4-linux-部署systemd)
- [5. 反向代理与 HTTPS](#5-反向代理与-https)
- [6. Cloudflare Tunnel 绑定域名](#6-cloudflare-tunnel-绑定域名)
- [7. 数据模式与迁移](#7-数据模式与迁移)
- [8. 备份、恢复、升级](#8-备份恢复升级)
- [9. 故障排查](#9-故障排查)
- [10. 安全检查清单](#10-安全检查清单)
- [附录 A：田冲村实际部署参数](#附录-a田冲村实际部署参数)

---

## 1. 环境要求

| 项目 | 要求 |
| --- | --- |
| Python | 3.8 及以上（Windows 安装时勾选 **Add Python to PATH**） |
| 磁盘 | 空库约 1 MB；1 万条流水约 5 MB；建议留 1 GB 给备份 |
| 内存 | 30 MB 左右（纯标准库，无依赖） |
| 网络 | 只监听 127.0.0.1，由 Nginx / Cloudflare Tunnel 对外 |
| 系统 | Windows 10/11、Windows Server、任意 Linux、macOS 均可 |

检查：

```bash
python --version
```

---

## 2. Windows 部署（推荐给村级使用）

### 2.1 放代码

建议路径不含空格，例如 `E:\down\jifen-mall`：

```bat
cd /d E:\down
git clone https://github.com/qdmz/jifen-mall.git
cd jifen-mall
```

没有 git 就下载 zip 解压。

### 2.2 配置

复制 `config.example.json` 为 `config.json`，按需修改：

```json
{
  "host": "127.0.0.1",
  "port": 8770,
  "db": "",
  "data_dir": "",
  "admin_password": "换成你自己的初始密码"
}
```

- 只想局域网访问：`"host": "0.0.0.0"`（同时要在防火墙放行端口）
- 想用独立库：`db`、`data_dir` 留空即可（默认 `data/`）
- 想沿用村居系统数据：见 [第 7 节](#7-数据模式与迁移)

### 2.3 启动

| 脚本 | 用途 |
| --- | --- |
| `start.bat` | 后台启动（无窗口），随后打印访问地址 |
| `start_debug.bat` | 前台启动，日志直接刷屏，排错用 |
| `stop.bat` | 停止（会先停守护，否则会被拉起） |
| `watchdog_start.bat` | 启动守护：10 秒探活，挂了自己拉起来 |

首次启动会：

1. 建库 `data\jifen.db`
2. 建管理员 `admin` / 你配置的初始密码（默认 `jifen2026`）
3. 预置 8 件商品、15 条积分规则

验证：

```bat
curl http://127.0.0.1:8770/api/health
```

应返回 `{"status": "ok", ...}`。

> **改了后端代码怎么生效？** 停服务再启（`stop.bat` → `start.bat`）。只改 `web/` 下的 html/css/js 不用重启，但要在地址栏 `?v=` 上变一下版本号，避免浏览器缓存旧文件。

---

## 3. 开机自启

### 3.1 任务计划程序（无需装东西）

1. `Win + R` → `taskschd.msc`
2. 创建基本任务 → 名称「积分超市」
3. 触发器：**登录时**（或「启动时」，需勾选「不管用户是否登录都运行」）
4. 操作：启动程序 `E:\down\jifen-mall\watchdog_start.bat`
5. 勾选「不管用户是否登录都运行」时，起始位置填 `E:\down\jifen-mall`

`watchdog_start.bat` 会拉起守护进程；守护会负责拉起 `app.py`，所以只需要一个自启项。

### 3.2 NSSM 注册为 Windows 服务（更稳，推荐长期）

```bat
nssm install JifenMall "C:\Python312\python.exe" "E:\down\jifen-mall\app.py"
nssm set JifenMall AppDirectory E:\down\jifen-mall
nssm set JifenMall AppStdout E:\down\jifen-mall\logs\stdout.log
nssm set JifenMall AppStderr E:\down\jifen-mall\logs\stderr.log
nssm set JifenMall Start SERVICE_AUTO_START
nssm start JifenMall
```

用服务方式时**不要再开 watchdog**，避免两个进程抢端口（后起的会启动失败退出，无害但日志会吵）。

---

## 4. Linux 部署（systemd）

```bash
sudo useradd -r -s /usr/sbin/nologin jifen || true
sudo mkdir -p /opt/jifen-mall && sudo chown -R jifen:jifen /opt/jifen-mall
sudo -u jifen git clone https://github.com/qdmz/jifen-mall.git /opt/jifen-mall
cd /opt/jifen-mall

# 首次初始化（会建库、建管理员）
sudo -u jifen python3 app.py --port 8770   # 看到「已启动」后 Ctrl+C
```

`/etc/systemd/system/jifen-mall.service`：

```ini
[Unit]
Description=Jifen Mall (village points supermarket)
After=network.target

[Service]
Type=simple
User=jifen
Group=jifen
WorkingDirectory=/opt/jifen-mall
Environment=PYTHONIOENCODING=utf-8
Environment=PYTHONUTF8=1
Environment=JF_PORT=8770
Environment=JF_HOST=127.0.0.1
ExecStart=/usr/bin/python3 /opt/jifen-mall/app.py
Restart=always
RestartSec=3
StandardOutput=append:/opt/jifen-mall/logs/stdout.log
StandardError=append:/opt/jifen-mall/logs/stderr.log

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now jifen-mall
sudo systemctl status jifen-mall
curl http://127.0.0.1:8770/api/health
```

> systemd 已经把守护做掉了，Linux 上**不需要** `watchdog.py`。

---

## 5. 反向代理与 HTTPS

### 5.1 Nginx

```nginx
server {
    listen 80;
    server_name jifen.example.com;
    client_max_body_size 6m;          # 红黑榜图片上限 4MB，留点余量

    location / {
        proxy_pass http://127.0.0.1:8770;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

HTTPS 用 certbot：

```bash
sudo certbot --nginx -d jifen.example.com
```

> `X-Forwarded-Proto` 必须传：程序据此给 Cookie 加 `Secure`。

### 5.2 Caddy（更省事，自动证书）

```
jifen.example.com {
    reverse_proxy 127.0.0.1:8770
    request_body {
        max_size 6MB
    }
}
```

---

## 6. Cloudflare Tunnel 绑定域名

适合**没有公网 IP** 的情况：cloudflared 从内网主动连 Cloudflare，域名解析到隧道，不用开端口。

### 6.1 本地配置型隧道（本项目采用）

一次性创建（已做过可跳过）：

```bash
cloudflared tunnel login                 # 浏览器授权，生成 ~/.cloudflared/cert.pem
cloudflared tunnel create jifen          # 生成隧道 ID + 凭据 json
```

`~/.cloudflared/config.yml`：

```yaml
tunnel: <隧道ID>
credentials-file: C:/Users/<你>/.cloudflared/<隧道ID>.json

ingress:
  - hostname: jifen.example.com
    service: http://127.0.0.1:8770
  - service: http_status:404          # 兜底，必须放最后
```

加 DNS 记录（把子域名指到隧道）：

```bash
cloudflared tunnel route dns <隧道ID> jifen.example.com
```

启动并常驻：

```bash
cloudflared tunnel run <隧道ID>       # 前台测试
cloudflared service install           # 注册为系统服务（Windows 需管理员）
```

验证：

```bash
curl https://jifen.example.com/api/health
```

**多站点共用一条隧道**时，`ingress` 里逐条列 hostname，**顺序从上到下匹配**，最后必须是 `http_status:404`：

```yaml
ingress:
  - hostname: ctyun.example.com
    service: http://127.0.0.1:8000
  - hostname: tianc.example.com
    service: http://127.0.0.1:8765
  - hostname: jifen.example.com
    service: http://127.0.0.1:8770
  - service: http_status:404
```

> Windows 服务方式（`Cloudflared` 服务）读取的是 **`C:\Windows\System32\config\systemprofile\.cloudflared\config.yml`**（LocalSystem 账户的家目录），不是 `C:\Users\你\.cloudflared\`。改完要 `Restart-Service Cloudflared`，且需要管理员权限。

### 6.2 Dashboard 托管型隧道

在 Cloudflare Zero Trust → Networks → Tunnels 里建隧道、装 connector，然后在 **Public Hostname** 加一条：

| 字段 | 值 |
| --- | --- |
| Subdomain | `jifen` |
| Domain | 你的域名 |
| Service | `http://127.0.0.1:8770` |

DNS 会自动生成，无需手工加记录。

### 6.3 常见报错

| 现象 | 原因 / 处理 |
| --- | --- |
| `error 1033` / HTTP 530 | 隧道 connector 不在线：`Get-Service Cloudflared` 看服务，`cloudflared tunnel info <ID>` 看连接 |
| 502 / 521 | 隧道通了但本机服务没起：`curl 127.0.0.1:8770/api/health`，看 `logs/app.log` |
| 404（Cloudflare 页面） | 该 hostname 没在 ingress 里，或兜底规则写在前面把请求吃了 |
| 只改了用户目录 config | 服务读的是 systemprofile 那份，两份都要改 |

---

## 7. 数据模式与迁移

### 7.1 独立库（默认）

```
data/jifen.db      积分账户、流水、订单、商品、规则、案例、家庭档案
data/uploads/jf/   红黑榜图片
data/backups/jf/   后台「立即备份」生成的 JSON
```

与村居管理系统**完全隔离**，适合独立对外、或者以后迁到云服务器。

### 7.2 共享库（过渡期推荐）

如果村里已经有「村居管理系统」在用，两边各存一份积分必然对不上。让独立站直接读写村居库即可：

```json
{
  "port": 8770,
  "db": "E:/down/VillageManagementSystem/village.db",
  "data_dir": "E:/down/VillageManagementSystem"
}
```

`data_dir` 指向村居系统目录，是为了让红黑榜图片（`uploads/jf/`）和备份（`backups/jf/`）两边都能读到。

- 两个进程同时读写 SQLite（WAL 模式）是安全的，写入冲突会排队等待
- 任何一边改数据，另一边刷新就能看到
- 以后要拆开：`python tools/import_from_village.py --src ...village.db --dst data/jifen.db --with-users --with-ledger`，再把 `config.json` 的 `db`/`data_dir` 改回来

### 7.3 从村居系统迁移（一次性）

```bash
python tools/import_from_village.py --src "E:\down\VillageManagementSystem\village.db" --with-users --with-ledger
```

参数：

| 参数 | 说明 |
| --- | --- |
| `--src` | 源库路径 |
| `--dst` | 目标库，默认 `data/jifen.db` |
| `--with-users` | 复制账号表（沿用原账号密码，免建号） |
| `--with-ledger` | 复制户籍台账（用于「从户籍导入」「按户籍地址归户」） |
| `--dry-run` | 只统计条数，不写库 |

复制的是 `jf_*` 全部表；按主键 `INSERT OR REPLACE`，可重复执行。

### 7.4 换机器

1. 停服务
2. 拷整个目录（至少 `data/` + `web/` + `*.py` + `config.json`）
3. 新机器上 `python app.py`，改 `config.json` 里的路径

---

## 8. 备份、恢复、升级

### 8.1 备份

- **后台一键**：数据管理 → 立即备份（保留最近 20 份，路径 `data/backups/jf/`），可下载 JSON
- **文件级**：定期复制 `data/` 目录（最省事，含图片）
- **定时**（Windows）：

```bat
schtasks /create /tn "JifenBackup" /tr "xcopy /Y /I /E E:\down\jifen-mall\data E:\backup\jifen-data-%date:~0,4%%date:~5,2%%date:~8,2%\" /sc daily /st 02:00
```

> 备份前最好看一眼服务是否在写（凌晨跑最稳）。

### 8.2 恢复

后台 → 数据管理 → 选择备份文件 → 恢复。恢复前会自动存一份 `jf_pre_restore_*.json`，反悔可用它再恢复回去。

文件级恢复：停服务 → 用备份覆盖 `data/jifen.db` → 启服务。

### 8.3 升级

```bash
cd /opt/jifen-mall
./stop.bat            # 或 sudo systemctl stop jifen-mall
git pull
python tools/import_from_village.py --src ...   # 只有跨版本需要补数据时才跑
./start.bat
curl http://127.0.0.1:8770/api/health
```

升级前先做一次备份。数据库结构变更是 `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ADD COLUMN` 形式，老库会自动补列，不用手工迁移。

---

## 9. 故障排查

| 现象 | 排查 |
| --- | --- |
| 打不开 / 502 | `curl 127.0.0.1:8770/api/health`；看 `logs/app.log` 最后几行 |
| 启动就退出 | 端口被占：`netstat -ano \| findstr 8770`；或 `logs/initial_admin.txt` 权限问题 |
| 登录一直失败 | 密码错了；`python tools/reset_pwd.py` 重置。注意同 IP 连续 5 次失败会锁 5 分钟 |
| 改了 JS 没生效 | 浏览器缓存：`?v=` 改版本号，或 Ctrl+F5 |
| 红黑榜图片不显示 | `data/uploads/jf/` 里没有文件；共享库模式下确认 `data_dir` 指向村居系统目录 |
| 村民查不到分 | 姓名要一致；同名需选组别；无手机号/身份证的用 6 位积分码（后台账户列表可查） |
| 时间不对 | 服务器时区；流水时间取服务器本地时间 |
| 中文乱码（Windows 控制台） | 启动脚本已设 `PYTHONUTF8=1`；手动跑时先 `chcp 65001` |
| 数据库被锁 `database is locked` | 有别的进程长时间写（如台账导入）；已设 15~30 秒 busy timeout，稍后重试 |

日志位置：

- `logs/app.log`：访问与异常
- `logs/watchdog.log`：守护探活/拉起记录
- `logs/initial_admin.txt`：首次生成的管理员密码（改密码后可删）

---

## 10. 安全检查清单

- [ ] 改掉默认密码，只把账号给需要的人（记账用 `editor`，看数据用 `viewer`）
- [ ] 服务只监听 `127.0.0.1`，对外走 HTTPS
- [ ] `config.json`、`data/` 不要提交到公开仓库（`.gitignore` 已排除）
- [ ] 定期备份，并验证备份能恢复
- [ ] 红黑榜图片不要放身份证、银行卡等敏感照片
- [ ] 户榜/个人榜对外展示时开启姓名脱敏（后台 → 超市设置）
- [ ] 服务器开启自动更新，Python 保持较新版本

---

## 附录 A：田冲村实际部署参数

| 项目 | 值 |
| --- | --- |
| 主机 | 村委会 Windows 11 主机（同时跑村居管理系统） |
| 目录 | `E:\down\jifen-mall` |
| 端口 | `8770`（仅本机） |
| 域名 | `https://jifen.qdmzctyun.dpdns.org` |
| 入口 | 村民端 `/jifen.html`，后台 `/jifen-admin.html` |
| 数据 | 共享库模式：`E:/down/VillageManagementSystem/village.db` |
| 对外通道 | Cloudflare Tunnel `ctyun-sales`（与 tianc / ctyun 两个站共用） |
| 启停 | `start.bat` / `stop.bat`；`watchdog_start.bat` 守护 |
