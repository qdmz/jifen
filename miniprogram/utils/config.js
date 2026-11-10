/**
 * 云服务配置（WorkBuddy Cloud Service）
 *
 * 数据现在存在云端：商品、积分账户、流水、兑换订单、红黑榜、站点设置。
 * 下面几个值来自应用开通云服务时返回的 publicConfig，都是前端可公开的值
 * （publishableKey 只标识是哪个应用，权限由服务端按来源域名校验）。
 *
 * 换成另一个云环境时，只需替换 endpoint 与 publishableKey。
 */
module.exports = {
  cloud: {
    endpoint: 'https://mp-api.app.workbuddy.host',
    publishableKey: 'wbpk_nUNWgcn0HMRtr5AmaWfmcN_oeIkcGUmkhM6E4YbK3uwGRxn0KUAbHSj',
    // 走 WorkBuddy 账号登录时才需要；本小程序用微信登录，留着不影响
    workBuddyOAuthClientId: 'cb_jq6QyEPkOkJXPcpz0JxS_wbapp_nUNWgcn0HMRtr5AmaWfmcN'
  },
  // 站点信息缓存时间（毫秒），避免每次进页面都请求
  siteCacheMs: 10 * 60 * 1000
};
