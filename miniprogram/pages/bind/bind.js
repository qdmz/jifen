const app = getApp();
const api = require('../../utils/api');

Page({
  data: {
    name: '',
    cred: '',
    grp: '',
    cands: [],
    needGrp: false,
    loading: false,
    err: ''
  },

  onInput: function (e) {
    var k = e.currentTarget.dataset.k;
    var d = {};
    d[k] = e.detail.value;
    this.setData(d);
  },

  pickGrp: function (e) {
    this.setData({
      grp: e.currentTarget.dataset.grp,
      needGrp: false,
      cands: []
    });
  },

  submit: function () {
    var self = this;
    var name = (this.data.name || '').trim();
    var cred = (this.data.cred || '').replace(/\s/g, '').toUpperCase();
    if (!name) {
      this.setData({ err: '请填写姓名' });
      return;
    }
    if (!cred) {
      this.setData({ err: '请填写手机号、身份证后 6 位或积分码' });
      return;
    }
    this.setData({ err: '', loading: true });

    api.post('/api/jifen/lookup', {
      name: name,
      cred: cred,
      grp: this.data.grp
    }).then(function (d) {
      app.setToken(d.token, d.account);
      self.setData({ loading: false });
      wx.showToast({ title: '查到了', icon: 'success' });
      setTimeout(function () {
        var pages = getCurrentPages();
        if (pages.length > 1) {
          wx.navigateBack();
        } else {
          wx.switchTab({ url: '/pages/me/me' });
        }
      }, 600);
    }).catch(function (e) {
      self.setData({ loading: false });
      var p = e.payload || {};
      if (p.need === 'grp' && p.candidates) {
        var cs = [];
        for (var i = 0; i < p.candidates.length; i++) {
          var c = p.candidates[i];
          cs.push({
            grp: c.grp,
            n: c.n,
            hu_zhu: c.hu_zhu,
            phone_mask: c.phone_mask
          });
        }
        self.setData({ needGrp: true, cands: cs, err: p.error || '请选择所在村民组' });
        return;
      }
      self.setData({ err: e.message });
    });
  }
});
