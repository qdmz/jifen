const cfg = require('./config');

function qs(data) {
  var parts = [];
  var keys = Object.keys(data || {});
  for (var i = 0; i < keys.length; i++) {
    var k = keys[i];
    var v = data[k];
    if (v === undefined || v === null || v === '') continue;
    parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(v));
  }
  return parts.join('&');
}

function request(path, method, data) {
  return new Promise(function (resolve, reject) {
    wx.request({
      url: cfg.apiBase + path,
      method: method || 'GET',
      data: data || {},
      header: { 'content-type': 'application/json' },
      timeout: 15000,
      success: function (res) {
        var d = res.data || {};
        if (res.statusCode === 200 && d.success) {
          resolve(d);
          return;
        }
        var e = new Error(d.error || ('请求失败（' + res.statusCode + '）'));
        e.statusCode = res.statusCode;
        e.payload = d;
        reject(e);
      },
      fail: function () {
        reject(new Error('网络不通，请检查手机网络后重试'));
      }
    });
  });
}

module.exports = {
  request: request,
  get: function (path, params) {
    var q = qs(params);
    return request(path + (q ? ('?' + q) : ''), 'GET');
  },
  post: function (path, data) {
    return request(path, 'POST', data);
  }
};
