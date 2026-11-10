/**
 * 数据层：全部走 WorkBuddy 云服务（云数据库 + 云函数）
 *
 * 对外保留原来的 get/post 路径写法，页面代码不用改：
 *   api.get('/api/jifen/goods')            → 读 jf_goods 表
 *   api.get('/api/jifen/rank', {n: 30})    → 云函数 jf_rank
 *   api.post('/api/jifen/lookup', {...})   → 云函数 jf_lookup（校验姓名 + 手机号/身份证后 6 位/积分码）
 *   api.post('/api/jifen/redeem', {...})   → 云函数 jf_redeem（扣积分、扣库存、生成取货码，在数据库里一次完成）
 *
 * 隐私：积分、流水、订单只由云函数按凭证返回，前端拿不到别人的数据；
 * 客户端也不直接写账户表 —— 改分、兑换只能通过云函数。
 */
const { cloud } = require('./cloud');

const GOOD_COLS = 'id,name,cat,icon,spec,points,stock,sold,limit_per,descr,status,sort';
const CASE_COLS = 'id,kind,title,who,grp,points,descr,happen,img,sort';

/** 把查询 builder 的 { data, error } 压成 data，出错直接抛 */
function db(q) {
  return q.then(function (res) {
    if (res && res.error) throw res.error;
    return (res && res.data) || [];
  });
}

/** 云函数统一返回 { ok:true, ... } 或 { ok:false, error } */
function rpc(name, args) {
  return cloud.database.rpc(name, args || {}).then(function (res) {
    if (res && res.error) throw res.error;
    const d = res ? res.data : null;
    if (d && d.ok === false) {
      const e = new Error(d.error || '请求失败，请稍后再试');
      e.payload = d;
      // 让页面沿用「401 就重新登录」的判断
      if (d.needbind || /过期|重新输入/.test(d.error || '')) e.statusCode = 401;
      throw e;
    }
    return d || {};
  });
}

function settingsOf(rows) {
  const s = {};
  (rows || []).forEach(function (x) { s[x.k] = x.v; });
  return s;
}

function getConfig() {
  return Promise.all([
    db(cloud.database.from('jf_settings').select('k,v')),
    db(cloud.database.from('jf_rules').select('id,name,cat,points,unit,descr,enabled,sort').eq('enabled', true).order('sort')),
    db(cloud.database.from('jf_goods').select('cat').eq('status', '上架'))
  ]).then(function (r) {
    const cats = [];
    (r[2] || []).forEach(function (g) {
      if (g.cat && cats.indexOf(g.cat) < 0) cats.push(g.cat);
    });
    return { settings: settingsOf(r[0]), rules: r[1] || [], cats: cats };
  });
}

function getGoods() {
  return Promise.all([
    db(cloud.database.from('jf_goods').select(GOOD_COLS).eq('status', '上架')
      .order('sort', { ascending: true }).order('points', { ascending: true })),
    db(cloud.database.from('jf_settings').select('k,v'))
  ]).then(function (r) {
    const goods = (r[0] || []).map(function (g) {
      g.desc = g.descr || '';
      g.stock = Number(g.stock || 0);
      g.points = Number(g.points || 0);
      return g;
    });
    return { goods: goods, settings: settingsOf(r[1]) };
  });
}

function getCases(n) {
  return Promise.all([
    db(cloud.database.from('jf_cases').select(CASE_COLS).order('sort', { ascending: true }).limit(n || 60)),
    db(cloud.database.from('jf_settings').select('k,v').in('k', ['case_intro', 'case_black_mask']))
  ]).then(function (r) {
    const cases = (r[0] || []).map(function (c) {
      c.desc = c.descr || '';
      return c;
    });
    return { cases: cases, settings: settingsOf(r[1]) };
  });
}

// ---------------------------------------------------------------- 路由
function get(path, params) {
  const p = String(path || '');
  const q = params || {};
  if (p === '/api/jifen/config') return getConfig();
  if (p === '/api/jifen/goods') return getGoods();
  if (p === '/api/jifen/rank') {
    return rpc('jf_rank', { p_n: Number(q.n) || 20 }).then(function (d) { return { rank: d || [] }; });
  }
  if (p === '/api/jifen/rank_hu') {
    return rpc('jf_rank_hu', { p_n: Number(q.n) || 20 }).then(function (d) { return { rank: d || [] }; });
  }
  if (p === '/api/jifen/cases') return getCases(Number(q.n) || 60);
  if (p === '/api/jifen/me') return rpc('jf_me', { p_token: q.token || '' });
  if (p === '/api/jifen/me_uid') return rpc('jf_me_uid', {});
  if (p === '/api/jifen/myorders') return rpc('jf_myorders', { p_token: q.token || '' });
  return Promise.reject(new Error('接口不存在：' + p));
}

function post(path, data) {
  const p = String(path || '');
  const b = data || {};
  if (p === '/api/jifen/lookup') {
    return rpc('jf_lookup', { p_name: b.name || '', p_cred: b.cred || '', p_grp: b.grp || '' });
  }
  if (p === '/api/jifen/redeem') {
    const items = b.items || [];
    const it = items[0] || {};
    return rpc('jf_redeem', {
      p_token: b.token || '',
      p_gid: it.gid || '',
      p_qty: Number(it.qty) || 1
    });
  }
  return Promise.reject(new Error('接口不存在：' + p));
}

module.exports = {
  getConfig: getConfig,
  getGoods: getGoods,
  getCases: getCases,
  get: get,
  post: post,
  /** 微信登录后按当前身份直接取账户（第一次会提示还没绑定） */
  meByUid: function () { return rpc('jf_me_uid', {}); }
};
