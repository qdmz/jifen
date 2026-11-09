/**
 * 接口地址配置
 * apiBase：积分超市服务地址（部署说明见 docs/DEPLOY-WECHAT.md）
 * - 开发/体验：可在微信开发者工具「详情 → 本地设置」勾选「不校验合法域名」
 * - 正式发布：必须换成已在「小程序后台 → 开发管理 → 服务器域名」登记过的 HTTPS 域名
 */
module.exports = {
  apiBase: 'https://jifen.qdmzctyun.dpdns.org',
  // 站点信息缓存时间（毫秒），避免每次进页面都请求
  siteCacheMs: 10 * 60 * 1000
};
