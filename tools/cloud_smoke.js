/**
 * 云服务接入冒烟测试（Node 里模拟小程序 wx，跑真实云请求）
 *
 * 用法：node tools/cloud_smoke.js
 * 验证：公开表查询（商品/设置/案例）、云函数（榜单/查分/我的）、RLS 隔离、错误分支。
 */
const https = require('https');
const { URL } = require('url');
const path = require('path');

const store = {};
let lastErr = null;

function doRequest(opts) {
  const u = new URL(opts.url);
  const body = opts.data && typeof opts.data === 'object' ? JSON.stringify(opts.data) : (opts.data || '');
  const headers = Object.assign({ 'content-type': 'application/json' }, opts.header || {});
  const req = https.request({
    hostname: u.hostname,
    port: u.port || 443,
    path: u.pathname + u.search,
    method: opts.method || 'GET',
    headers: headers
  }, (res) => {
    let buf = '';
    res.on('data', (d) => { buf += d; });
    res.on('end', () => {
      let data;
      try { data = JSON.parse(buf); } catch (e) { data = buf; }
      if (res.statusCode >= 400) lastErr = { status: res.statusCode, body: data };
      if (opts.success) opts.success({ statusCode: res.statusCode, data: data, header: res.headers });
      if (opts.complete) opts.complete({});
    });
  });
  req.on('error', (e) => {
    lastErr = { status: 0, body: e.message };
    if (opts.fail) opts.fail({ errMsg: 'request:fail ' + e.message });
    if (opts.complete) opts.complete({});
  });
  if (body && (opts.method || 'GET') !== 'GET') req.write(body);
  req.end();
  return { abort() { req.destroy(); } };
}

global.wx = {
  getStorageSync: (k) => (k in store ? store[k] : ''),
  setStorageSync: (k, v) => { store[k] = v; },
  removeStorageSync: (k) => { delete store[k]; },
  getAccountInfoSync: () => ({ miniProgram: { appId: 'wx367de40d97109686', envVersion: 'develop' } }),
  canIUse: () => true,
  getSystemInfoSync: () => ({ platform: 'devtools' }),
  request: doRequest,
  login: () => {},
  showToast: () => {}
};

const MOD = path.join(__dirname, '..', 'miniprogram', 'node_modules',
  '@tencent-ai', 'workbuddy-cloud-sdk', 'lib', 'miniprogram.cjs');
const sdk = require(MOD);
const { createMiniProgramWorkBuddyCloud } = sdk;

const cfg = require(path.join(__dirname, '..', 'miniprogram', 'utils', 'config.js'));
const cloud = createMiniProgramWorkBuddyCloud({
  endpoint: cfg.cloud.endpoint,
  publishableKey: cfg.cloud.publishableKey,
  wx: global.wx
});

let pass = 0;
let fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('  ✓', name); }
  else { fail++; console.log('  ✗', name, extra === undefined ? '' : JSON.stringify(extra).slice(0, 300)); }
}

(async () => {
  console.log('endpoint =', cfg.cloud.endpoint);

  // 1. 公开表：商品
  const g = await cloud.database.from('jf_goods')
    .select('id,name,points,stock,descr').eq('status', '上架').order('sort', { ascending: true });
  ok('读商品（公开表）', !g.error && Array.isArray(g.data) && g.data.length === 19,
    g.error || { n: g.data && g.data.length });

  // 2. 公开表：设置
  const s = await cloud.database.from('jf_settings').select('k,v');
  const smap = {};
  (s.data || []).forEach((x) => { smap[x.k] = x.v; });
  ok('读站点设置', !s.error && smap.market_name === 'XX村积分超市', s.error || smap);

  // 3. 公开表：案例
  const c = await cloud.database.from('jf_cases').select('id,kind,title,descr').order('sort');
  ok('读红黑榜', !c.error && (c.data || []).length === 3, c.error || { n: c.data && c.data.length });

  // 4. 云函数：个人榜
  const r1 = await cloud.database.rpc('jf_rank', { p_n: 3 });
  ok('云函数 jf_rank', !r1.error && Array.isArray(r1.data) && r1.data.length === 3,
    r1.error || r1.data);

  // 5. 云函数：按户榜
  const r2 = await cloud.database.rpc('jf_rank_hu', { p_n: 3 });
  ok('云函数 jf_rank_hu', !r2.error && Array.isArray(r2.data) && r2.data.length === 3,
    r2.error || r2.data);

  // 6. 云函数：查积分（正确凭证）
  const lk = await cloud.database.rpc('jf_lookup', {
    p_name: '张建国', p_cred: '13800000001', p_grp: ''
  });
  ok('云函数 jf_lookup 命中', !lk.error && lk.data && lk.data.ok === true
    && lk.data.account && lk.data.account.points === 172, lk.error || lk.data);
  const token = lk.data && lk.data.token;

  // 7. 云函数：凭证错误
  const lk2 = await cloud.database.rpc('jf_lookup', {
    p_name: '张建国', p_cred: '13900000000', p_grp: ''
  });
  ok('云函数 jf_lookup 拒绝错误凭证', !lk2.error && lk2.data && lk2.data.ok === false
    && /对不上/.test(lk2.data.error), lk2.error || lk2.data);

  // 8. 云函数：用 token 取我的积分 + 流水
  const me = await cloud.database.rpc('jf_me', { p_token: token });
  ok('云函数 jf_me', !me.error && me.data && me.data.ok === true
    && Array.isArray(me.data.txns) && me.data.account.name === '张建国', me.error || me.data);

  // 9. RLS：个人账户表在未登录时不可读（应返回 0 行或权限错误）
  const acc = await cloud.database.from('jf_accounts').select('id,name,points');
  ok('RLS 保护账户表（未登录拿不到）', !!acc.error || (acc.data || []).length === 0,
    acc.error ? { code: acc.error.code, msg: acc.error.message } : { n: acc.data.length });

  // 10. RLS：流水表同样不可读
  const tx = await cloud.database.from('jf_txns').select('id');
  ok('RLS 保护流水表', !!tx.error || (tx.data || []).length === 0,
    tx.error ? { code: tx.error.code } : { n: tx.data.length });

  // 11. 兑换：库存不足 / 积分不足的分支（用测试账号，改真实数据故选低价商品 + 大数量）
  const lk3 = await cloud.database.rpc('jf_lookup', {
    p_name: '测试', p_cred: '888888', p_grp: ''
  });
  const tk2 = lk3.data && lk3.data.token;
  const rd = await cloud.database.rpc('jf_redeem', { p_token: tk2, p_gid: 'g_7c5ea0f93b6f2584', p_qty: 999 });
  ok('兑换拦截库存不足', !rd.error && rd.data && rd.data.ok === false && /库存不足/.test(rd.data.error),
    rd.error || rd.data);

  // 12. 走真实前端数据层 utils/api.js（页面实际用的那层）
  const api = require(path.join(__dirname, '..', 'miniprogram', 'utils', 'api.js'));
  const goods2 = await api.get('/api/jifen/goods');
  ok('api.get goods 字段映射', goods2.goods.length === 19 && typeof goods2.goods[0].desc === 'string'
    && typeof goods2.goods[0].points === 'number', { n: goods2.goods.length });

  const cfg2 = await api.getConfig();
  ok('api.getConfig', cfg2.settings.market_name === 'XX村积分超市' && cfg2.cats.length >= 1, cfg2.settings);

  const rk = await api.get('/api/jifen/rank', { n: 5 });
  ok('api rank', rk.rank.length === 5 && rk.rank[0].no === 1, rk.rank[0]);

  const lk4 = await api.post('/api/jifen/lookup', { name: '张建国', cred: '13800000001' });
  ok('api lookup', !!lk4.token && lk4.account.points === 172, lk4.account);

  let rejected = false;
  try {
    await api.post('/api/jifen/lookup', { name: '张建国', cred: '13900000000' });
  } catch (e) {
    rejected = /对不上/.test(e.message);
  }
  ok('api lookup 错误分支', rejected);

  const me2 = await api.get('/api/jifen/me', { token: lk4.token });
  ok('api me', me2.account.name === '张建国' && Array.isArray(me2.txns), me2.account);

  const od = await api.get('/api/jifen/myorders', { token: lk4.token });
  ok('api myorders', Array.isArray(od.orders), { n: od.orders && od.orders.length });

  let expired = false;
  try {
    await api.get('/api/jifen/me', { token: 'bogus-token' });
  } catch (e) {
    expired = e.statusCode === 401;
  }
  ok('api 过期凭证给 401', expired);

  console.log('\n通过 %d 项，失败 %d 项', pass, fail);
  if (lastErr) console.log('最后一次 HTTP 错误：', JSON.stringify(lastErr).slice(0, 500));
  process.exit(fail ? 1 : 0);
})().catch((e) => {
  console.error('测试脚本异常：', e && (e.message || e));
  process.exit(2);
});
