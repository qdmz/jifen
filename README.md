# 积分超市 · 乡村治理积分制系统

一套给村/社区用的**积分制管理 + 积分兑换超市**系统：村民手机查积分、线上兑换、凭取货码到超市领东西；村干部在后台记分、上架商品、核销、看榜单。

纯 **Python 标准库 + SQLite**，无第三方依赖，单机即可跑，也可以挂在 Cloudflare Tunnel / Nginx 后面用域名访问。

- 村民端：`/jifen.html`（手机优先，扫码即用）
- 管理后台：`/jifen-admin.html`（账号密码登录）

> 本项目从「村居管理系统」中抽离而来，可独立部署、独立域名、独立数据库。

---

## 功能一览

### 村民端（公开，无需登录）
| 功能 | 说明 |
| --- | --- |
| 查积分 | 姓名 + **手机号 / 身份证后 6 位 / 6 位积分码** 三选一；同名时按村民组消歧 |
| 我的积分 | 当前余额、累计获得、累计兑换、最近流水 |
| 商品兑换 | 按分类浏览，库存/限兑实时校验，提交后生成 **6 位取货码** |
| 我的兑换 | 查看待领取/已领取/已取消，出示取货码领货 |
| 积分榜 | 个人榜、户榜（户主姓名可脱敏） |
| 红黑榜 | 村里好人好事 / 不文明行为公示，图片可隐藏姓名中间字 |
| 积分规则 | 哪些事加分、加多少，公开透明 |

### 管理后台（admin / editor / viewer 三种角色）
| 模块 | 能力 |
| --- | --- |
| 数据概览 | 账户数、发放/兑换、核销率、库存预警、待领取提醒 |
| 数据大屏 | 按日期区间看出入库、加分事由 Top、组别对比、双榜 |
| 商品管理 | 增删改、上下架、库存、每人限兑、排序 |
| 积分发放 | 按人/按组多选，一次给一批人记分，可套用规则事由 |
| 兑换核销 | 输入取货码核销；也可取消订单（自动退分、回补库存） |
| 积分账户 | 账户增删改、批量导入、积分码补齐、导出登录卡；**按户归集与人工分户调整** |
| 积分流水 | 全量流水查询、按人/事由搜索、导出 CSV |
| 积分规则 | 维护加减分事项（名称、分值、单位、说明） |
| 红黑榜 | 案例发布/下架、上传图片、排序 |
| 数据管理 | 一键备份、下载/恢复、CSV 导出、健康体检 |
| 超市设置 | 超市名称、公告、兑换说明、黑榜脱敏等 |

---

## 技术栈

- Python **3.8+**（只用标准库：`http.server` / `sqlite3` / `hashlib` / `urllib`）
- SQLite（WAL 模式，单文件数据库）
- 前端原生 HTML/CSS/JS，无构建步骤
- 密码：PBKDF2-HMAC-SHA256（12 万轮 + 随机盐），与原村居系统同格式，可直接沿用其账号

---

## 目录结构

```
jifen-mall/
├── app.py                  独立 HTTP 服务：静态文件 + 登录鉴权 + /api/jifen/*
├── jifen.py                业务模块：账户/流水/订单/商品/规则/案例/按户归集
├── watchdog.py             守护进程（可选）：探活失败自动拉起
├── web/
│   ├── jifen.html          村民端
│   ├── jifen-admin.html    管理后台
│   ├── login.html          后台登录
│   └── assets/             css / js
├── tools/
│   ├── import_from_village.py  从村居系统 village.db 迁移积分数据
│   ├── seed_demo.py            生成演示数据（培训/截图用）
│   ├── reset_pwd.py            重置后台账号密码
│   └── stop_app.py             停止服务（按 PID）
├── data/                   运行期数据（数据库/图片/备份，已 gitignore）
├── logs/                   运行日志（已 gitignore）
├── config.example.json     配置示例
├── start.bat / stop.bat    Windows 启停
└── docs/
    ├── DEPLOY.md           部署手册（Windows / Linux / Nginx / Cloudflare Tunnel）
    └── USAGE.md            使用手册（村民端 + 后台逐模块）
```

---

## 快速开始

```bash
git clone https://github.com/qdmz/jifen-mall.git
cd jifen-mall
python app.py
```

打开 http://127.0.0.1:8770/jifen.html 即可看到村民端；后台 http://127.0.0.1:8770/jifen-admin.html

首次启动会自动建库，并创建管理员：

- 用户名 `admin`
- 密码 `jifen2026`（**登录后请立刻在右上角「改密码」修改**）
- 也可以用环境变量 `JF_ADMIN_PASSWORD` 指定初始密码

Windows 用户直接双击 `start.bat`（后台运行）／`start_debug.bat`（前台看日志）／`stop.bat`。

### 从村居管理系统迁移数据

如果已经有 `village.db`（村居系统），一条命令把积分账户、流水、订单、商品、规则、红黑榜搬过来：

```bash
python tools/import_from_village.py --src "E:\down\VillageManagementSystem\village.db" --with-users --with-ledger
```

- `--with-users`：连账号一起搬（沿用原账号密码登录，省得新建）
- `--with-ledger`：搬户籍台账（后台「从户籍导入」「按户籍地址归户」才有数据）
- 可重复执行（按主键覆盖，不会重复）

---

## 配置

复制 `config.example.json` 为 `config.json`（可选，不建也能跑）：

```json
{
  "host": "127.0.0.1",
  "port": 8770,
  "db": "",
  "data_dir": "",
  "admin_password": ""
}
```

| 字段 | 环境变量 | 说明 |
| --- | --- | --- |
| `host` | `JF_HOST` | 监听地址，默认 `127.0.0.1`（只给反代/隧道用）；要局域网直连改 `0.0.0.0` |
| `port` | `JF_PORT` | 端口，默认 `8770` |
| `db` | `JF_DB` | 数据库文件，默认 `data/jifen.db` |
| `data_dir` | `JF_DATA_DIR` | 数据根目录（图片、备份），默认 `./data` |
| `admin_password` | `JF_ADMIN_PASSWORD` | 首次建库时的管理员密码 |

**两种数据模式：**

1. **独立库（默认）**：数据在 `data/jifen.db`，与村居系统互不影响。
2. **共享库**：把 `db` 指向 `...\VillageManagementSystem\village.db`，`data_dir` 指向该目录，两个系统读写同一份积分数据（适合过渡期，避免两套积分对不上）。

详见 [docs/DEPLOY.md](docs/DEPLOY.md#数据模式)。

---

## 常用命令

| 命令 | 作用 |
| --- | --- |
| `python app.py [--port 8770] [--host 0.0.0.0]` | 前台启动 |
| `start.bat` / `stop.bat` | Windows 后台启动 / 停止（stop 会先停守护） |
| `python watchdog.py` | 启动守护（10 秒探活，连续 2 次失败自动拉起） |
| `python watchdog.py --status` | 看服务是否在线 |
| `python tools/reset_pwd.py` | 重置 admin 密码（随机）或 `--user/--pwd` 指定 |
| `python tools/seed_demo.py` | 给「测试」账户造演示数据；`--clear` 清空 |
| `python tools/import_from_village.py --src ...` | 从村居系统迁移数据 |
| `python tools/stop_app.py` | 按 PID 停止（跨平台） |

---

## 接口概览

所有接口都在 `/api/jifen/` 下，返回 JSON（`{"success": true, ...}`）。

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/jifen/config` | 公开 | 超市设置、商品、规则、榜单入口配置 |
| GET | `/api/jifen/goods` | 公开 | 上架商品 |
| POST | `/api/jifen/lookup` | 公开 | 查积分（手机号/身份证后6位/积分码），返回 30 分钟 token |
| POST | `/api/jifen/redeem` | token | 提交兑换 |
| GET | `/api/jifen/me`、`/myorders` | token | 我的积分、我的兑换 |
| GET | `/api/jifen/rank`、`/rank_hu` | 公开 | 个人榜、户榜 |
| GET | `/api/jifen/cases` | 公开 | 红黑榜 |
| * | `/api/jifen/admin/*` | editor/admin | 后台全部接口（商品、发放、核销、账户、分户、备份等） |
| GET | `/api/health` | 公开 | 健康检查 |

鉴权：`POST /api/auth/login`（用户名+密码）→ 写 `jf_sid` Cookie（7 天，HttpOnly）；`/api/auth/me` 取当前用户；`/api/auth/pwd` 改密码。

---

## 安全建议

1. 后台务必改掉默认密码；`viewer` 角色只读，适合给监委会看数据。
2. 生产只监听 `127.0.0.1`，前面挂 Nginx/Caddy 或 Cloudflare Tunnel 做 HTTPS，不要直接把 8770 暴露到公网。
3. 定期备份：后台「数据管理 → 立即备份」，或直接复制 `data/` 目录。
4. 村民端查分有防枚举：同 IP 连续 6 次失败锁 5 分钟；后台登录 5 次失败锁 5 分钟。

---

## 文档

- [部署手册 docs/DEPLOY.md](docs/DEPLOY.md)：Windows 常驻、Linux systemd、Nginx 反代、Cloudflare Tunnel 绑定域名、数据迁移、备份升级、故障排查
- [使用手册 docs/USAGE.md](docs/USAGE.md)：村民端怎么查分兑换、后台每个模块怎么用、积分制落地流程建议
