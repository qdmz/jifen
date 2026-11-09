const app = getApp();
const api = require('../../utils/api');

Page({
  data: {
    seg: 'hu',
    hu: [],
    ppl: [],
    cases: [],
    loading: true,
    err: ''
  },

  onShow: function () {
    var seg = wx.getStorageSync('rank_seg') || 'hu';
    wx.removeStorageSync('rank_seg');
    if (seg !== 'hu' && seg !== 'ppl' && seg !== 'case') seg = 'hu';
    this.setData({ seg: seg });
    this.load(seg);
  },

  onPullDownRefresh: function () {
    var self = this;
    this.load(this.data.seg).then(function () {
      wx.stopPullDownRefresh();
    });
  },

  pickSeg: function (e) {
    var seg = e.currentTarget.dataset.seg;
    this.setData({ seg: seg });
    this.load(seg);
  },

  load: function (seg) {
    var self = this;
    this.setData({ err: '' });
    var p;
    if (seg === 'hu') {
      p = api.get('/api/jifen/rank_hu', { n: 30 }).then(function (d) {
        var list = d.rank || [];
        var out = [];
        for (var i = 0; i < list.length; i++) {
          var r = list[i];
          var members = r.members || 1;
          out.push({
            no: r.no,
            name: r.name,
            grp: r.grp,
            members: members,
            points: r.points,
            avg: Math.round((r.points || 0) / members)
          });
        }
        self.setData({ hu: out });
      });
    } else if (seg === 'ppl') {
      p = api.get('/api/jifen/rank', { n: 30 }).then(function (d) {
        self.setData({ ppl: d.rank || [] });
      });
    } else {
      p = api.get('/api/jifen/cases', { n: 60 }).then(function (d) {
        var list = d.cases || [];
        var out = [];
        for (var i = 0; i < list.length; i++) {
          var c = list[i];
          out.push({
            id: c.id,
            kind: c.kind,
            red: c.kind !== 'black',
            title: c.title,
            who: c.who,
            grp: c.grp,
            points: c.points,
            desc: c.desc,
            happen: c.happen,
            img: c.img
          });
        }
        self.setData({ cases: out });
      });
    }
    return p.then(function () {
      self.setData({ loading: false });
    }).catch(function (e) {
      self.setData({ loading: false, err: e.message });
    });
  }
});
