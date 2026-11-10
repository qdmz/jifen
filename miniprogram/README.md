# 积分超市 · 微信小程序（云服务版）

原生小程序，数据全部走 **WorkBuddy 云服务**（云数据库 + 云函数），不再依赖自建 Python 服务，
因此不用备案域名、不用公网隧道，装好开发者工具就能跑。

## 导入

1. 安装微信开发者工具：<https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html>
2. 导入项目，目录选本文件夹（`miniprogram/`）
   - AppID 已在 `project.config.json` 里：`wx367de40d97109686`
3. 确认 `project.config.json` 里 `setting.nodeModules` 为 `true`（已设好），依赖产物在
   `miniprogram_npm/` 里，**不需要**再点「构建 npm」

## 云端结构

| 表 / 函数 | 用途 |
|---|---|
| `jf_goods` / `jf_settings` / `jf_rules` / `jf_cases` | 商品、站点设置、积分规则、红黑榜（公开可读） |
| `jf_accounts` / `jf_txns` / `jf_orders` | 积分账户、流水、兑换订单（只有本人能读，靠 RLS 隔离） |
| `jf_lookup(name, cred, grp)` | 校验「姓名 + 手机号/身份证后 6 位/积分码」，发 12 小时凭证 |
| `jf_me(token)` / `jf_myorders(token)` | 我的积分 / 我的兑换单（传空 token 时按微信登录身份取） |
| `jf_redeem(token, gid, qty)` | 兑换：校验积分和库存 → 扣减 → 生成 6 位取货码，在数据库里一次完成 |
| `jf_rank(n)` / `jf_rank_hu(n)` | 个人榜 / 按户榜（只返回姓名、组、积分） |
| `jf_me_uid()` | 微信登录后按当前身份直接取账户 |

客户端**只读公开表 + 调云函数**，不直接改账户表；改分、兑换只能通过云函数，越权改分请求会被拒绝。

## 登录

两种，任意一种都能用：

1. **姓名 + 凭证**（默认）：手机号 / 身份证后 6 位 / 积分码三选一，云函数校验后发 12 小时凭证，
   存在 `wx.setStorageSync('jf_token')`。
2. **微信登录**（`bind` 页第二个按钮）：`wx.login` → 云会话，之后查一次积分就把这个微信和积分账户绑定，
   下次进来不用再输。绑定时只写 `owner_id`，不覆盖任何积分数据。

## 改配置

只有 `utils/config.js` 一处，就是开通云服务时拿到的 `publicConfig`：

```js
module.exports = {
  cloud: {
    endpoint: 'https://mp-api.app.workbuddy.host',
    publishableKey: 'wbpk_...',
    workBuddyOAuthClientId: 'cb_...'
  },
  siteCacheMs: 10 * 60 * 1000
};
```

这三个值是前端可公开的标识，不含任何密钥；换云环境时整体替换。

## 目录

```
miniprogram/
├── app.js / app.json / app.wxss     全局入口（云登录态恢复、站点缓存）
├── project.config.json              AppID、编译配置
├── utils/cloud.js                   ★ 云客户端（全局唯一，含请求诊断）
├── utils/api.js                     ★ 数据层（表查询 + 云函数，保留原 get/post 写法）
├── utils/config.js                  ★ 云环境配置
├── utils/workbuddy-cloud-diagnostics.js   云请求失败时在 vConsole 打日志
├── miniprogram_npm/                 云 SDK 构建产物
├── assets/tabbar/                   tabBar 图标（8 张 PNG）
└── pages/
    ├── index/   首页：站名、我的积分卡、须知、热门商品
    ├── goods/   兑换：分类、库存、确认弹窗、取货码
    ├── rank/    家庭榜 / 个人榜 / 红黑榜
    ├── me/      余额、积分码、待领取、流水、兑换单
    └── bind/    姓名 + 凭证查询 / 微信登录绑定
```

## 自测

```bash
node ../tools/cloud_smoke.js
```

在 Node 里模拟小程序运行环境，直接打真实云端接口，覆盖：公开表读取、榜单、查分、错误凭证、
过期凭证、RLS 隔离（未登录读不到别人的账户和流水）、库存不足拦截。

## 发布

云服务版不需要服务器域名备案，直接上传体验版即可试用。
正式发布仍需在小程序后台补名称、头像、类目与用户隐私保护指引，详见
[../docs/DEPLOY-WECHAT.md](../docs/DEPLOY-WECHAT.md)。
