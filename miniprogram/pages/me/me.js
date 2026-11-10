const app = getApp();
const api = require('../../utils/api');

Page({
  data: {
    acc: null,
    txns: [],
    pending: [],
    orders: [],
    loading: true,
    err: ''
  },

  onShow: function () {
    this.load();
  },

  onPullDownRefresh: function () {
    this.load().then(function () {
      wx.stopPullDownRefresh();
    });
  },

  load: function () {
    var self = this;
    if (!app.globalData.token && !app.globalData.wxUser) {
      // 既没有查询凭证、也没有微信登录态 → 没登录
      this.setData({ acc: null, txns: [], pending: [], orders: [], loading: false });
      return Promise.resolve();
    }
    this.setData({ err: '' });
    var p1 = app.refreshMe().then(function (d) {
      self.setData({
        acc: d.account,
        txns: self.mapTxns(d.txns || []),
        pending: self.mapOrders(d.pending || [])
      });
    });
    var p2 = api.get('/api/jifen/myorders', { token: app.globalData.token }).then(function (d) {
      self.setData({ orders: self.mapOrders(d.orders || []) });
    }).catch(function () { });

    return Promise.all([p1, p2]).then(function () {
      self.setData({ loading: false });
    }).catch(function (e) {
      if (e.statusCode === 401) {
        app.clearToken();
        self.setData({ acc: null, loading: false });
        return;
      }
      self.setData({ err: e.message, loading: false });
    });
  },

  mapTxns: function (list) {
    var out = [];
    for (var i = 0; i < list.length; i++) {
      var t = list[i];
      out.push({
        id: t.id,
        reason: t.reason,
        points: t.points,
        plus: Number(t.points) >= 0,
        balance: t.balance,
        created: String(t.created || '').slice(0, 16),
        operator: t.operator
      });
    }
    return out;
  },

  mapOrders: function (list) {
    var out = [];
    for (var i = 0; i < list.length; i++) {
      var o = list[i];
      out.push({
        id: o.id,
        code: o.code,
        items_text: o.items_text,
        points: o.points,
        status: o.status,
        created: String(o.created || '').slice(0, 16),
        wait: o.status === '待领取'
      });
    }
    return out;
  },

  goBind: function () {
    wx.navigateTo({ url: '/pages/bind/bind' });
  },

  goGoods: function () {
    wx.switchTab({ url: '/pages/goods/goods' });
  },

  copyCode: function (e) {
    var code = e.currentTarget.dataset.code;
    if (!code) return;
    wx.setClipboardData({
      data: String(code),
      success: function () {
        wx.showToast({ title: '取货码已复制', icon: 'none' });
      }
    });
  },

  logout: function () {
    var self = this;
    wx.showModal({
      title: '退出登录',
      content: '退出后需要重新输入姓名和手机号才能查看积分。',
      success: function (r) {
        if (!r.confirm) return;
        self.setData({ txns: [], pending: [], orders: [] });
        app.clearToken();
        self.load();
      }
    });
  }
});
