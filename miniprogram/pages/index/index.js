const app = getApp();
const api = require('../../utils/api');

Page({
  data: {
    site: {},
    acc: null,
    hot: [],
    loading: true,
    err: ''
  },

  onShow: function () {
    this.load();
  },

  onPullDownRefresh: function () {
    var self = this;
    this.load().then(function () {
      wx.stopPullDownRefresh();
    });
  },

  load: function () {
    var self = this;
    this.setData({ err: '' });

    var pSite = app.loadSite().then(function (s) {
      self.setData({ site: s || {} });
    }).catch(function (e) {
      self.setData({ err: e.message });
    });

    var pMe = app.refreshMe().then(function (d) {
      self.setData({ acc: d.account });
    }).catch(function () {
      self.setData({ acc: null });
    });

    var pGoods = api.get('/api/jifen/goods').then(function (d) {
      self.setData({ hot: (d.goods || []).slice(0, 3) });
    }).catch(function () { });

    return Promise.all([pSite, pMe, pGoods]).then(function () {
      self.setData({ loading: false });
    });
  },

  goBind: function () {
    wx.navigateTo({ url: '/pages/bind/bind' });
  },

  goGoods: function () {
    wx.switchTab({ url: '/pages/goods/goods' });
  },

  goRank: function () {
    wx.setStorageSync('rank_seg', 'hu');
    wx.switchTab({ url: '/pages/rank/rank' });
  },

  goCase: function () {
    wx.setStorageSync('rank_seg', 'case');
    wx.switchTab({ url: '/pages/rank/rank' });
  }
});
