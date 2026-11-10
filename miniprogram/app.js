const api = require('./utils/api');
const cfg = require('./utils/config');
const { cloud } = require('./utils/cloud');

App({
  globalData: {
    token: '',        // 姓名 + 凭证查询后拿到的短期凭证（12 小时）
    account: null,
    site: null,
    siteAt: 0,
    authReady: null,  // 云登录态恢复
    wxUser: null      // 微信登录成功后的用户
  },

  onLaunch: function () {
    var self = this;
    var t = wx.getStorageSync('jf_token');
    if (t) this.globalData.token = t;

    // 恢复云登录态：用微信登录过一次后，SDK 会自己在本地保存会话
    this.globalData.authReady = cloud.auth.getSession().then(function (r) {
      var s = r && r.data;
      if (s && s.user) self.globalData.wxUser = s.user;
      return s || null;
    }).catch(function () {
      return null;
    });
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

  /** 微信登录：拿到云会话，之后查积分会自动把这个微信和积分账户绑定 */
  loginByWechat: function () {
    var self = this;
    return new Promise(function (resolve, reject) {
      wx.login({
        success: function (res) {
          if (!res.code) {
            reject(new Error('微信登录失败，请重试'));
            return;
          }
          var appid = wx.getAccountInfoSync().miniProgram.appId;
          cloud.auth.signInWithWechat(res.code, appid).then(function (r) {
            if (r && r.error) {
              reject(new Error(r.error.message || '微信登录没成功，请稍后再试'));
              return;
            }
            self.globalData.wxUser = (r.data && r.data.user) || {};
            resolve(r.data);
          }).catch(function () {
            reject(new Error('微信登录失败，请检查网络后重试'));
          });
        },
        fail: function (e) {
          reject(new Error((e && e.errMsg) || '微信登录失败'));
        }
      });
    });
  },

  /** 站点信息（名称/标语/公告等），带缓存 */
  loadSite: function (force) {
    var now = Date.now();
    var g = this.globalData;
    if (!force && g.site && (now - g.siteAt) < cfg.siteCacheMs) {
      return Promise.resolve(g.site);
    }
    return api.getConfig().then(function (d) {
      g.site = d.settings || {};
      g.siteAt = Date.now();
      return g.site;
    });
  },

  /** 拉当前账户：先用凭证 token，没有就看这个微信是否已绑定 */
  refreshMe: function () {
    var self = this;
    var keep = function (d) {
      self.globalData.account = d.account;
      return d;
    };
    if (this.globalData.token) {
      return api.get('/api/jifen/me', { token: this.globalData.token }).then(keep).catch(function (e) {
        if (e.statusCode === 401) self.clearToken();
        throw e;
      });
    }
    return (this.globalData.authReady || Promise.resolve(null)).then(function () {
      if (!self.globalData.wxUser) return null;
      return api.meByUid().then(keep).catch(function (e) {
        throw e;
      });
    });
  }
});
