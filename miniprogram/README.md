# 积分超市 · 微信小程序

原生小程序（无 npm、无第三方框架），对接本仓库同一个后端服务（`app.py`）。

## 导入

1. 安装微信开发者工具：<https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html>
2. 导入项目，目录选本文件夹（`miniprogram/`）
   - AppID 已在 `project.config.json` 里：`wx367de40d97109686`
3. 「详情 → 本地设置」勾选**不校验合法域名**（开发/体验阶段必须勾，正式发布前改成备案域名）

## 改接口地址

只改一个文件 `utils/config.js`：

```js
module.exports = {
  apiBase: 'https://jifen.qdmzctyun.dpdns.org',  // 换成你的域名
  siteCacheMs: 10 * 60 * 1000
};
```

- 体验版：用现在的隧道域名即可（勾了「不校验域名」）
- 正式版：必须是**已 ICP 备案**的 HTTPS 域名，并在小程序后台「开发设置 → 服务器域名」登记

## 目录

```
miniprogram/
├── app.js / app.json / app.wxss     全局入口与样式
├── project.config.json              AppID、编译配置
├── utils/api.js                     请求封装（wx.request + 统一错误）
├── utils/config.js                  ★ 接口地址
├── assets/tabbar/                   tabBar 图标（8 张 PNG）
└── pages/
    ├── index/   首页：站名、我的积分卡、须知、热门商品
    ├── goods/   兑换：分类、库存、确认弹窗、取货码
    ├── rank/    家庭榜 / 个人榜 / 红黑榜
    ├── me/      余额、积分码、待领取、流水、兑换单
    └── bind/    姓名 + 手机号/身份证后6位/积分码 查询绑定
```

## 登录方式

复用 H5 的「姓名 + 凭证」登录：后端返回 token，小程序存 `wx.setStorageSync('jf_token')`，之后所有请求带 token。
只要后端账户数据一致，H5 和小程序看到的是同一份积分。

## 发布

完整清单（含备案域名、类目、隐私指引）见 [../docs/DEPLOY-WECHAT.md](../docs/DEPLOY-WECHAT.md)。
