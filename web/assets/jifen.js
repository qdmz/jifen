/* 积分超市 · 村民端 */
(function () {
  'use strict';
  var API = '';
  var S = { cfg: null, goods: [], acc: null, token: '', cat: '全部', cur: null, qty: 1, orders: [] };

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function n(v) { return Number(v || 0).toLocaleString('zh-CN'); }

  var toastTimer = null;
  function toast(msg) {
    var t = $('toast');
    t.textContent = msg;
    t.classList.remove('hide');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.add('hide'); }, 2200);
  }

  function api(path, opt) {
    opt = opt || {};
    return fetch(API + path, {
      method: opt.method || 'GET',
      headers: opt.body ? { 'Content-Type': 'application/json' } : {},
      body: opt.body ? JSON.stringify(opt.body) : undefined,
      credentials: 'same-origin'
    }).then(function (r) {
      return r.json().catch(function () { return { success: false, error: '服务返回异常（' + r.status + '）' }; })
        .then(function (d) { d.__status = r.status; return d; });
    });
  }

  /* ---------------- 启动 ---------------- */
  function boot() {
    api('/api/jifen/goods').then(function (d) {
      if (!d.success) { $('pgrid').innerHTML = '<div class="loading">' + esc(d.error || '加载失败') + '</div>'; return; }
      S.cfg = { settings: d.settings || {} };
      S.goods = d.goods || [];
      applySettings();
      renderCats();
      renderGoods();
      renderNote();
    }).catch(function () {
      $('pgrid').innerHTML = '<div class="loading">网络异常，请下拉刷新重试</div>';
    });
    api('/api/jifen/config').then(function (d) {
      if (!d.success) return;
      S.cfg = { settings: d.settings || {}, rules: d.rules || [], cats: d.cats || [], stats: d.stats || {} };
      applySettings();
      fillGroups(d.groups || []);
      renderRules();
      if (!S.goods.length) { /* 商品走另一个接口 */ }
      loadRank();
    });
    // 恢复上次查询
    try {
      var tk = sessionStorage.getItem('jf_token');
      if (tk) {
        api('/api/jifen/me?token=' + encodeURIComponent(tk)).then(function (d) {
          if (d.success) { S.token = tk; setAcc(d.account, d.pending || []); loadMyOrders(); }
          else sessionStorage.removeItem('jf_token');
        });
      }
    } catch (e) { }
    bindRankSeg();
    bindCaseSeg();
    loadRank();
  }

  /* 站名简称：把「XX村积分超市」里的业态后缀去掉，得到「XX村」，用于卡片落款等 */
  function siteShort() {
    var n = (((S.cfg || {}).settings || {}).market_name || '').trim();
    var s = n.replace(/(积分)?超市$/, '').replace(/积分制$/, '').trim();
    return s ? ('积分制 · ' + s) : '积分制';
  }

  function applySettings() {
    var st = (S.cfg && S.cfg.settings) || {};
    if (st.market_name) { $('mkName').textContent = st.market_name; document.title = st.market_name; }
    if (st.slogan) $('mkSlogan').textContent = st.slogan;
    if (st.address) $('ftAddr').textContent = '📍 ' + st.address;
    if (st.open_time) $('ftOpen').textContent = '🕘 ' + st.open_time;
    if (st.notice) $('ftNotice').textContent = st.notice;
  }

  /* ---------------- 商品 ---------------- */
  function renderCats() {
    var cats = ['全部'];
    S.goods.forEach(function (g) { if (cats.indexOf(g.cat) < 0) cats.push(g.cat); });
    $('cats').innerHTML = cats.map(function (c) {
      return '<button class="cat' + (c === S.cat ? ' on' : '') + '" data-cat="' + esc(c) + '">' + esc(c) + '</button>';
    }).join('');
  }

  function renderGoods() {
    var list = S.goods.filter(function (g) { return S.cat === '全部' || g.cat === S.cat; });
    if (!list.length) { $('pgrid').innerHTML = '<div class="loading">该分类暂无商品</div>'; return; }
    $('pgrid').innerHTML = list.map(function (g) {
      var enough = S.acc && S.acc.points >= g.points;
      var out = g.stock <= 0;
      var tag = out ? '<span class="pd-tag">已兑完</span>'
        : (g.stock <= 5 ? '<span class="pd-tag low">仅剩 ' + g.stock + '</span>' : '');
      var btn = out
        ? '<button class="pd-buy" disabled>已兑完</button>'
        : '<button class="pd-buy' + (enough ? ' on' : '') + '" data-buy="' + esc(g.id) + '">兑换</button>';
      return '<div class="pd' + (out ? ' out' : '') + '">' +
        '<div class="pd-img">' + esc(g.icon) + tag + '</div>' +
        '<div class="pd-body">' +
        '<div class="pd-name">' + esc(g.name) + '</div>' +
        '<div class="pd-spec">' + esc(g.spec || g.cat) + (g.limit_per ? ' · 限兑 ' + g.limit_per + ' 件' : '') + '</div>' +
        '<div class="pd-foot"><div><div class="pd-pt">' + n(g.points) + '<small>分</small></div>' +
        '<div class="pd-stock">库存 ' + n(g.stock) + '</div></div>' + btn + '</div>' +
        '</div></div>';
    }).join('');
  }

  function renderNote() {
    var s = (S.cfg && S.cfg.settings) || {};
    $('goodsNote').innerHTML = '兑换说明：选好物品后点「兑换」，系统生成<strong>取货码</strong>；'
      + '凭码到 ' + esc(s.address || '村委会积分超市') + ' 领取实物。积分不兑现、不转让。'
      + (s.open_time ? '<br>领取时间：' + esc(s.open_time) : '');
  }

  /* ---------------- 查积分 ---------------- */
  function openLookup() {
    $('lookupErr').textContent = '';
    $('grpPick').classList.add('hide');
    $('mLookup').classList.remove('hide');
    setTimeout(function () { $('inName').focus(); }, 200);
  }

  function fillGroups(list) {
    var sel = $('inGrp');
    if (!sel) return;
    var cur = sel.value;
    var h = '<option value="">不确定 / 先不选</option>';
    (list || []).forEach(function (g) {
      h += '<option value="' + esc(g) + '">' + esc(g) + '</option>';
    });
    sel.innerHTML = h;
    if (cur) sel.value = cur;
  }

  function renderGrpPick(list) {
    var box = $('grpPick');
    box.innerHTML = list.map(function (c) {
      var g = c.grp || '';
      var nm = g ? g.replace(/组$/, '') + '组' : '未登记组别';
      return '<button type="button" data-pickgrp="' + esc(g) + '">' + esc(nm) +
        (c.n > 1 ? ' · ' + c.n + ' 人' : '') + '</button>';
    }).join('');
    box.classList.remove('hide');
  }

  function doLookup(grpForce) {
    var name = $('inName').value.trim();
    var cred = $('inPhone').value.trim().replace(/\s/g, '').toUpperCase();
    var grp = (typeof grpForce === 'string' && grpForce)
      ? grpForce : ($('inGrp') ? $('inGrp').value : '');
    var err = $('lookupErr');
    if (!name) { err.textContent = '请输入姓名'; return; }
    if (!/^1\d{10}$/.test(cred) && !/^[\dX]{6}$/.test(cred)) {
      err.textContent = '请输入 11 位手机号、身份证后 6 位，或 6 位积分码'; return;
    }
    err.textContent = '';
    $('grpPick').classList.add('hide');
    var btn = $('btnDoLookup');
    btn.disabled = true; btn.textContent = '查询中…';
    api('/api/jifen/lookup', { method: 'POST', body: { name: name, phone: cred, grp: grp } })
      .then(function (d) {
        btn.disabled = false; btn.textContent = '查 询';
        if (!d.success) {
          if (d.need === 'grp' && (d.candidates || []).length) {
            err.textContent = d.error || '请选择村民组';
            renderGrpPick(d.candidates);
            return;
          }
          err.textContent = d.error || '查询失败'; return;
        }
        S.token = d.token;
        try { sessionStorage.setItem('jf_token', d.token); } catch (e) { }
        setAcc(d.account, d.pending || []);
        closeMask($('mLookup'));
        toast('已登录：' + d.account.name + '，当前 ' + n(d.account.points) + ' 分');
        renderGoods();
        loadMyOrders();
      }).catch(function () {
        btn.disabled = false; btn.textContent = '查 询';
        err.textContent = '网络异常，请重试';
      });
  }

  function setAcc(acc, pending) {
    S.acc = acc;
    $('meEmpty').classList.add('hide');
    $('meBody').classList.remove('hide');
    $('accName').textContent = acc.name;
    $('accGrp').textContent = acc.grp ? acc.grp.replace('组', '') + '组' : '未登记组别';
    $('accGrp').style.display = acc.grp ? '' : 'none';
    $('accPhone').textContent = '手机 ' + (acc.phone_mask || '—');
    var cEl = $('accCode');
    if (cEl) {
      if (acc.code) {
        cEl.textContent = '我的积分码 ' + acc.code + '（忘记手机号时可凭它登录）';
        cEl.classList.remove('hide');
      } else {
        cEl.textContent = '';
        cEl.classList.add('hide');
      }
    }
    $('accPoints').textContent = n(acc.points);
    $('accEarned').textContent = n(acc.earned);
    $('accSpent').textContent = n(acc.spent);
    var pd = (pending || []).length;
    $('accPending').textContent = n(pd);
    var tip = '';
    if (acc.status && acc.status !== '正常') tip = '账户状态：' + acc.status + '，暂不能兑换，请联系村委会。';
    else if (pd > 0) tip = '你有 ' + pd + ' 件兑换待领取，取货码：' + pending.map(function (o) { return o.code; }).join('、');
    $('meTip').innerHTML = tip ? esc(tip) : '';
    $('meTip').style.display = tip ? '' : 'none';
  }

  function switchAcc() {
    S.acc = null; S.token = ''; S.orders = [];
    try { sessionStorage.removeItem('jf_token'); } catch (e) { }
    $('meBody').classList.add('hide');
    $('meEmpty').classList.remove('hide');
    $('myOrders').innerHTML = '<div class="empty-hint">请先查询积分后查看兑换记录</div>';
    renderGoods();
  }

  /* ---------------- 兑换 ---------------- */
  function openRedeem(gid) {
    if (!S.acc || !S.token) { openLookup(); toast('请先查询积分'); return; }
    var g = S.goods.filter(function (x) { return x.id === gid; })[0];
    if (!g) return;
    S.cur = g; S.qty = 1;
    renderRedeem();
    $('mRedeem').classList.remove('hide');
  }

  function maxQty() {
    var g = S.cur;
    if (!g) return 1;
    return Math.max(1, Math.min(20, g.stock, g.limit_per || 999));
  }

  function renderRedeem() {
    var g = S.cur, q = S.qty, total = g.points * q;
    var left = (S.acc.points || 0) - total;
    var short = left < 0;
    $('redeemBody').innerHTML =
      '<div class="rw"><div class="rw-ic">' + esc(g.icon) + '</div>' +
      '<div class="rw-info"><div class="rw-nm">' + esc(g.name) + '</div>' +
      '<div class="rw-sp">' + esc(g.spec || g.cat) + ' · 库存 ' + n(g.stock) + '</div>' +
      '<div class="rw-pt">' + n(g.points) + ' 分 / 件</div></div>' +
      '<div class="qty"><button data-q="-1"' + (q <= 1 ? ' disabled' : '') + '>−</button>' +
      '<input id="qtyIn" value="' + q + '" inputmode="numeric" readonly>' +
      '<button data-q="1"' + (q >= maxQty() ? ' disabled' : '') + '>+</button></div></div>' +
      '<div class="rw-total"><span>合计扣减积分</span><b>' + n(total) + ' 分</b></div>' +
      '<div class="rw-after">当前 ' + n(S.acc.points) + ' 分 → 兑换后 <b>' + n(left) + '</b> 分</div>' +
      (short ? '<div class="rw-warn">积分不足，还差 ' + n(-left) + ' 分。可先参与村集体活动挣积分。</div>' : '') +
      '<button class="btn main block" id="btnDoRedeem"' + (short ? ' disabled' : '') + '>确认兑换</button>' +
      '<p class="fld-tip">兑换后请到积分超市凭取货码领取，积分一经兑换不退。</p>';
    var body = $('redeemBody');
    body.querySelectorAll('[data-q]').forEach(function (b) {
      b.onclick = function () {
        S.qty = Math.min(maxQty(), Math.max(1, S.qty + Number(b.getAttribute('data-q'))));
        renderRedeem();
      };
    });
    var ok = $('btnDoRedeem');
    if (ok) ok.onclick = submitRedeem;
  }

  function submitRedeem() {
    var btn = $('btnDoRedeem');
    btn.disabled = true; btn.textContent = '提交中…';
    api('/api/jifen/redeem', { method: 'POST', body: { token: S.token, items: [{ gid: S.cur.id, qty: S.qty }] } })
      .then(function (d) {
        if (!d.success) {
          btn.disabled = false; btn.textContent = '确认兑换';
          toast(d.error || '兑换失败');
          if (d.__status === 401) { switchAcc(); openLookup(); }
          return;
        }
        closeMask($('mRedeem'));
        showDone(d.order);
        // 本地同步
        S.acc.points = d.order.balance;
        S.acc.spent = (S.acc.spent || 0) + d.order.points;
        $('accPoints').textContent = n(S.acc.points);
        $('accSpent').textContent = n(S.acc.spent);
        var g = S.goods.filter(function (x) { return x.id === S.cur.id; })[0];
        if (g) { g.stock -= S.qty; g.sold += S.qty; }
        renderGoods();
        loadMyOrders();
      }).catch(function () {
        btn.disabled = false; btn.textContent = '确认兑换';
        toast('网络异常，请重试');
      });
  }

  function showDone(o) {
    $('doneCode').textContent = o.code;
    $('doneList').innerHTML = o.items.map(function (i) {
      return esc(i.icon) + ' ' + esc(i.name) + ' × ' + i.qty;
    }).join('<br>') + '<br><span style="color:#6b7280;font-size:11.5px;">合计 ' + n(o.points) + ' 分</span>';
    $('doneBal').innerHTML = '兑换后余额 <b>' + n(o.balance) + '</b> 分';
    $('mDone').classList.remove('hide');
  }

  /* ---------------- 我的兑换 ---------------- */
  function loadMyOrders() {
    if (!S.token) return;
    api('/api/jifen/myorders?token=' + encodeURIComponent(S.token)).then(function (d) {
      if (!d.success) return;
      renderOrders(d.orders || []);
    });
  }

  function renderOrders(list) {
    if (!list.length) {
      $('myOrders').innerHTML = '<div class="empty-hint">还没有兑换记录<br>选一件心仪的物品试试吧</div>';
      return;
    }
    var m = { '待领取': 'wait', '已领取': 'done', '已取消': 'cancel' };
    $('myOrders').innerHTML = list.map(function (o) {
      return '<div class="od"><div class="od-top">' +
        '<span class="od-code">取货码 ' + esc(o.code) + '</span>' +
        '<span class="od-st ' + (m[o.status] || 'wait') + '">' + esc(o.status) + '</span></div>' +
        '<div class="od-items">' + o.items.map(function (i) { return esc(i.icon) + ' ' + esc(i.name) + '×' + i.qty; }).join('　') + '</div>' +
        '<div class="od-foot"><span>' + esc(o.created) + '</span>' +
        '<span class="od-sig">共 <b>' + n(o.points) + '</b> 分</span></div></div>';
    }).join('');
  }

  /* ---------------- 积分榜 ---------------- */
  var rankBy = 'person';

  function loadRank() {
    if (!$('rank')) return;
    var byHouse = rankBy === 'house';
    $('rankHint').textContent = byHouse
      ? '按户积分排序 · 户内成员积分合计 · 户主姓名已脱敏'
      : '按当前积分排序 · 姓名已脱敏';
    api('/api/jifen/' + (byHouse ? 'rank_hu' : 'rank') + '?n=30').then(function (d) {
      if (!d.success) return;
      var list = d.rank || [];
      if (!list.length) {
        $('rank').innerHTML = '<div class="empty-hint">暂无积分记录</div>';
        return;
      }
      $('rank').innerHTML = list.map(function (r) {
        if (byHouse) {
          return '<div class="rk"><span class="rk-no">' + r.no + '</span>' +
            '<span class="rk-nm">' + esc(r.name) + ' 户' +
            (r.grp ? '<i>' + esc(r.grp.replace('组', '')) + '组</i>' : '') +
            '<i>' + n(r.members) + ' 人</i></span>' +
            '<span class="rk-pt">' + n(r.points) + '<small style="font-size:10px;font-weight:600;"> 分</small></span></div>';
        }
        return '<div class="rk"><span class="rk-no">' + r.no + '</span>' +
          '<span class="rk-nm">' + esc(r.name) + (r.grp ? '<i>' + esc(r.grp.replace('组', '')) + '组</i>' : '') + '</span>' +
          '<span class="rk-pt">' + n(r.points) + '<small style="font-size:10px;font-weight:600;"> 分</small></span></div>';
      }).join('');
    });
  }

  /* ---------------- 积分红黑榜 ---------------- */
  var caseKind = 'all';

  function caseCard(c) {
    var red = c.kind !== 'black';
    var pts = Number(c.points || 0);
    var h = '<div class="case-card ' + (red ? 'red' : 'black') + '">';
    if (c.img) {
      h += '<img class="case-img" src="' + esc(c.img) + '" alt="' + esc(c.title) + '" data-lb="' +
        esc(c.img) + '" loading="lazy">';
    }
    h += '<div class="case-bd"><div class="case-top">' +
      '<span class="case-badge ' + (red ? 'red' : 'black') + '">' + (red ? '红榜 · 加分' : '黑榜 · 减分') + '</span>' +
      '<span class="case-t">' + esc(c.title) + '</span>' +
      '<span class="case-pts ' + (pts >= 0 ? 'plus' : 'minus') + '">' +
      (pts > 0 ? '+' : '') + n(pts) + ' 分</span></div>';
    if (c.who || c.grp) {
      h += '<div class="case-who">' + (c.who ? '<b>' + esc(c.who) + '</b>' : '') +
        (c.grp ? '<span>' + esc(c.grp) + '</span>' : '') + '</div>';
    }
    if (c.desc) h += '<div class="case-desc">' + esc(c.desc) + '</div>';
    h += '<div class="case-meta">' + (c.happen ? '<span>📅 ' + esc(c.happen) + '</span>' : '') +
      '<span>' + esc(siteShort()) + '</span></div>';
    return h + '</div></div>';
  }

  function loadCases() {
    if (!$('caseList')) return;
    api('/api/jifen/cases?kind=' + encodeURIComponent(caseKind) + '&n=60').then(function (d) {
      if (!d.success) { $('caseList').innerHTML = '<div class="empty-hint">加载失败</div>'; return; }
      var list = d.cases || [];
      var intro = ((d.settings || {}).case_intro || '').trim();
      if ($('caseHint')) {
        $('caseHint').textContent = caseKind === 'red' ? '红榜 · 加分表扬'
          : (caseKind === 'black' ? '黑榜 · 减分警示' : '红榜表扬先进 · 黑榜警示后进');
      }
      $('caseList').innerHTML = (intro ? '<div class="case-intro">' + esc(intro) + '</div>' : '') +
        (list.length ? list.map(caseCard).join('')
          : '<div class="empty-hint">' +
            (caseKind === 'black' ? '本期暂无减分案例，继续保持 👍' : '暂无公示案例，敬请期待') + '</div>');
    }).catch(function () {
      $('caseList').innerHTML = '<div class="empty-hint">网络异常，请稍后重试</div>';
    });
  }

  function bindCaseSeg() {
    var box = $('caseSeg');
    if (!box) return;
    box.querySelectorAll('button').forEach(function (b) {
      b.onclick = function () {
        caseKind = b.getAttribute('data-ck') || 'all';
        box.querySelectorAll('button').forEach(function (x) { x.classList.toggle('on', x === b); });
        $('caseList').innerHTML = '<div class="loading">加载中…</div>';
        loadCases();
      };
    });
  }

  /* 图片点开看大图 */
  function openLightbox(src) {
    var old = document.getElementById('lbBox');
    if (old) old.remove();
    var d = document.createElement('div');
    d.className = 'lb';
    d.id = 'lbBox';
    d.innerHTML = '<button class="lb-x" aria-label="关闭">×</button><img src="' + esc(src) + '" alt="">';
    d.addEventListener('click', function () { d.remove(); });
    document.body.appendChild(d);
  }

  function bindRankSeg() {
    var box = $('rankSeg');
    if (!box) return;
    box.querySelectorAll('button').forEach(function (b) {
      b.onclick = function () {
        rankBy = b.getAttribute('data-rk') === 'house' ? 'house' : 'person';
        box.querySelectorAll('button').forEach(function (x) { x.classList.toggle('on', x === b); });
        $('rank').innerHTML = '<div class="loading">加载中…</div>';
        loadRank();
      };
    });
  }

  /* ---------------- 规则 ---------------- */
  function renderRules() {
    var rs = (S.cfg && S.cfg.rules) || [];
    if (!rs.length) { $('rules').innerHTML = '<div class="empty-hint">暂无积分规则</div>'; return; }
    var groups = {};
    rs.forEach(function (r) { (groups[r.cat] = groups[r.cat] || []).push(r); });
    var h = '';
    Object.keys(groups).forEach(function (cat) {
      h += '<div class="rule-grp"><h4>▎' + esc(cat) + '</h4>';
      groups[cat].forEach(function (r) {
        h += '<div class="rule"><div class="rule-nm">' + esc(r.name) +
          (r.desc ? '<em>' + esc(r.desc) + '</em>' : '') + '</div>' +
          '<div class="rule-pt">+' + r.points + '<small> 分/' + esc(r.unit) + '</small></div></div>';
      });
      h += '</div>';
    });
    h += '<div class="note">积分由村委会按实际参与情况登记，每季度公示一次。对积分有异议可在公示期内向村委会申请复核。</div>';
    $('rules').innerHTML = h;
  }

  /* ---------------- 交互绑定 ---------------- */
  function closeMask(el) { if (el) el.classList.add('hide'); }

  document.addEventListener('click', function (e) {
    var t = e.target;
    if (t.hasAttribute && t.hasAttribute('data-close')) {
      closeMask(t.closest('.mask'));
      return;
    }
    if (t.classList && t.classList.contains('mask')) { closeMask(t); return; }
    if (t.hasAttribute && t.hasAttribute('data-buy')) { openRedeem(t.getAttribute('data-buy')); return; }
    if (t.hasAttribute && t.hasAttribute('data-pickgrp')) {
      var g = t.getAttribute('data-pickgrp');
      var sel = $('inGrp');
      if (sel && g) {
        var has = false;
        for (var i = 0; i < sel.options.length; i++) { if (sel.options[i].value === g) has = true; }
        if (!has) {
          var o = document.createElement('option'); o.value = g; o.textContent = g;
          sel.appendChild(o);
        }
        sel.value = g;
      }
      doLookup(g);
      return;
    }
    if (t.hasAttribute && t.hasAttribute('data-cat')) {
      S.cat = t.getAttribute('data-cat');
      document.querySelectorAll('.cat').forEach(function (b) { b.classList.toggle('on', b === t); });
      renderGoods();
      return;
    }
    if (t.hasAttribute && t.hasAttribute('data-lb')) {
      openLightbox(t.getAttribute('data-lb'));
      return;
    }
    if (t.hasAttribute && t.hasAttribute('data-tab')) {
      var k = t.getAttribute('data-tab');
      document.querySelectorAll('.tab').forEach(function (b) { b.classList.toggle('on', b === t); });
      document.querySelectorAll('.pane').forEach(function (p) { p.classList.toggle('on', p.id === 'pane-' + k); });
      if (k === 'orders') { S.token ? loadMyOrders() : null; }
      if (k === 'rank') loadRank();
      if (k === 'case') loadCases();
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
  });

  $('btnLookup').onclick = openLookup;
  $('btnDoLookup').onclick = doLookup;
  $('btnSwitch').onclick = switchAcc;
  $('inPhone').addEventListener('keydown', function (e) { if (e.key === 'Enter') doLookup(); });
  $('inName').addEventListener('keydown', function (e) { if (e.key === 'Enter') $('inPhone').focus(); });

  boot();
})();
