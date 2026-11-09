const api = require('./utils/api');
const cfg = require('./utils/config');

App({
  globalData: {
    token: '',
    account: null,
    site: null,
    siteAt: 0
  },

  onLaunch: function () {
    var t = wx.getStorageSync('jf_token');
    if (t) this.globalData.token = t;
  },

  setToken: function (token, account) {
    this.globalData.token = token || '';
    if (token) wx.setStorageSync('jf_token', token);
    if (account) this.globalData.account = account;
  },

  clearToken: function () {
    this.globalData.token = '';
    this.globalData.account = null;
    wx.removeStorageSync('jf_token');
  },

  /** 站点信息（名称/标语/公告等），带缓存 */
  loadSite: function (force) {
    var now = Date.now();
    var g = this.globalData;
    if (!force && g.site && (now - g.siteAt) < cfg.siteCacheMs) {
      return Promise.resolve(g.site);
    }
    return api.get('/api/jifen/config').then(function (d) {
      g.site = d.settings || {};
      g.siteAt = Date.now();
      return g.site;
    });
  },

  /** 拉当前登录账户（token 失效时自动清空） */
  refreshMe: function () {
    var self = this;
    if (!this.globalData.token) return Promise.resolve(null);
    return api.get('/api/jifen/me', { token: this.globalData.token }).then(function (d) {
      self.globalData.account = d.account;
      return d;
    }).catch(function (e) {
      if (e.statusCode === 401) self.clearToken();
      throw e;
    });
  }
});
