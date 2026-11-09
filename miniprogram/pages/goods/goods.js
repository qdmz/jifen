const app = getApp();
const api = require('../../utils/api');

Page({
  data: {
    cats: ['全部'],
    cat: '全部',
    goods: [],
    shown: [],
    acc: null,
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
    this.setData({ err: '' });
    var pMe = app.refreshMe().then(function (d) {
      self.setData({ acc: d.account });
    }).catch(function () {
      self.setData({ acc: null });
    });
    var pGoods = api.get('/api/jifen/goods').then(function (d) {
      var goods = d.goods || [];
      var cats = ['全部'];
      for (var i = 0; i < goods.length; i++) {
        if (cats.indexOf(goods[i].cat) < 0 && goods[i].cat) cats.push(goods[i].cat);
      }
      self.setData({ goods: goods, cats: cats });
      self.apply();
    }).catch(function (e) {
      self.setData({ err: e.message });
    });
    return Promise.all([pMe, pGoods]).then(function () {
      self.setData({ loading: false });
    });
  },

  apply: function () {
    var cat = this.data.cat;
    var acc = this.data.acc;
    var balance = acc ? Number(acc.points || 0) : 0;
    var out = [];
    var goods = this.data.goods;
    for (var i = 0; i < goods.length; i++) {
      var g = goods[i];
      if (cat !== '全部' && g.cat !== cat) continue;
      out.push({
        id: g.id,
        name: g.name,
        cat: g.cat,
        icon: g.icon,
        spec: g.spec,
        points: g.points,
        stock: g.stock,
        desc: g.desc,
        soldout: Number(g.stock || 0) <= 0,
        lack: acc ? balance < Number(g.points || 0) : false,
        limit_per: g.limit_per || 0
      });
    }
    this.setData({ shown: out });
  },

  pickCat: function (e) {
    this.setData({ cat: e.currentTarget.dataset.cat });
    this.apply();
  },

  goBindTap: function () {
    wx.navigateTo({ url: '/pages/bind/bind' });
  },

  exchange: function (e) {
    var self = this;
    var gid = e.currentTarget.dataset.id;
    var g = null;
    for (var i = 0; i < this.data.goods.length; i++) {
      if (this.data.goods[i].id === gid) { g = this.data.goods[i]; break; }
    }
    if (!g) return;

    if (!app.globalData.token) {
      wx.showModal({
        title: '先查一下积分',
        content: '兑换需要先确认你的积分账户，是否现在去查？',
        confirmText: '去查积分',
        success: function (r) {
          if (r.confirm) wx.navigateTo({ url: '/pages/bind/bind' });
        }
      });
      return;
    }
    if (Number(g.stock || 0) <= 0) {
      wx.showToast({ title: '这件已经换完了', icon: 'none' });
      return;
    }
    var acc = this.data.acc;
    if (acc && Number(acc.points || 0) < Number(g.points || 0)) {
      wx.showToast({ title: '积分不足，还差 ' + (Number(g.points) - Number(acc.points)) + ' 分', icon: 'none' });
      return;
    }

    wx.showModal({
      title: '确认兑换',
      content: '用 ' + g.points + ' 分兑换「' + g.name + '」？兑换后请凭取货码到积分超市领取。',
      confirmText: '确认兑换',
      success: function (r) {
        if (!r.confirm) return;
        wx.showLoading({ title: '兑换中', mask: true });
        api.post('/api/jifen/redeem', {
          token: app.globalData.token,
          items: [{ gid: g.id, qty: 1 }]
        }).then(function (d) {
          wx.hideLoading();
          var code = (d.order && d.order.code) || '';
          wx.showModal({
            title: '兑换成功',
            content: '取货码 ' + code + '\n请到积分超市领取实物',
            showCancel: false,
            confirmText: '知道了'
          });
          self.load();
        }).catch(function (err) {
          wx.hideLoading();
          if (err.statusCode === 401) {
            app.clearToken();
            wx.showModal({
              title: '需要重新登录',
              content: '登录状态已过期，请重新查一次积分。',
              confirmText: '去查积分',
              success: function (r2) {
                if (r2.confirm) wx.navigateTo({ url: '/pages/bind/bind' });
              }
            });
            return;
          }
          wx.showToast({ title: err.message, icon: 'none', duration: 2500 });
        });
      }
    });
  }
});
