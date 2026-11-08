/* 积分超市 · 管理后台 */
(function () {
  'use strict';
  var S = {
    goods: [], accounts: [], accTotal: 0, accPage: 1, accSize: 20, accKw: '',
    accView: 'person',          // person = 按人 / house = 按户
    houses: [], houseTotal: 0, unhoused: 0,
    huSel: {}, huMode: 'join', huPick: '', huHits: [],
    orders: [], ordTotal: 0, ordPage: 1, ordSize: 20, ordStatus: '待领取', ordKw: '',
    txns: [], txnTotal: 0, txnPage: 1, txnSize: 20, txnKw: '',
    rules: [], cfg: {}, grantTotal: 0,
    cases: [],
    picked: {},                 // 发放：accId -> true
    grantList: [], grantKw: '',
    dashDays: 30, dash: null, charts: {}, rankView: 'person',
    backups: [], rptFrom: '', rptTo: '', pendingRestore: null
  };

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function n(v) { return Number(v || 0).toLocaleString('zh-CN'); }
  var tTimer = null;
  function toast(msg, isErr) {
    var t = $('toast');
    t.textContent = msg;
    t.className = 'toast' + (isErr ? ' err' : '');
    clearTimeout(tTimer);
    tTimer = setTimeout(function () { t.classList.add('hide'); }, 2600);
  }
  function closeMask() { $('mBox').classList.add('hide'); }

  function api(path, body) {
    var opt = { credentials: 'same-origin', headers: {} };
    if (body !== undefined) {
      opt.method = 'POST';
      opt.headers['Content-Type'] = 'application/json';
      opt.body = JSON.stringify(body);
    }
    return fetch(path, opt).then(function (r) {
      if (r.status === 401) {
        location.href = '/login.html?next=' + encodeURIComponent(location.pathname);
        throw new Error('unauth');
      }
      return r.json().catch(function () { return { success: false, error: '返回异常 ' + r.status }; })
        .then(function (d) { d.__status = r.status; return d; });
    });
  }

  /* ---------------- 弹窗 ---------------- */
  function modal(title, bodyHtml, footHtml, onMount, wide) {
    $('mbTitle').textContent = title;
    $('mbBody').innerHTML = bodyHtml;
    $('mbFoot').innerHTML = footHtml || '<button class="btn ghost" data-close>关闭</button>';
    document.querySelector('#mBox .dlg').classList.toggle('wide', !!wide);
    $('mBox').classList.remove('hide');
    if (onMount) onMount($('mbBody'), $('mbFoot'));
  }

  document.addEventListener('click', function (e) {
    var t = e.target;
    if (t.hasAttribute && t.hasAttribute('data-close')) { closeMask(); return; }
    if (t.id === 'mBox') { closeMask(); return; }
    if (t.hasAttribute && t.hasAttribute('data-go')) {
      switchPanel(t.getAttribute('data-go'));
      return;
    }
  });

  /* ---------------- 导航 ---------------- */
  function switchPanel(p) {
    document.querySelectorAll('.side button').forEach(function (b) {
      b.classList.toggle('on', b.getAttribute('data-p') === p);
    });
    document.querySelectorAll('.panel').forEach(function (x) {
      x.classList.toggle('on', x.id === 'p-' + p);
    });
    if (p === 'ov') loadOverview();
    if (p === 'dash') loadDash();
    if (p === 'data') { loadHealth(); loadBackups(); }
    if (p === 'goods') loadGoods();
    if (p === 'grant') loadGrant();
    if (p === 'verify') { loadVerify(); loadOrderList(); }
    if (p === 'acc') loadAccounts();
    if (p === 'txn') loadTxns();
    if (p === 'rule') loadRules();
    if (p === 'case') loadCases();
    if (p === 'set') loadSettings();
    window.scrollTo(0, 0);
  }
  document.querySelectorAll('.side button').forEach(function (b) {
    b.onclick = function () { switchPanel(b.getAttribute('data-p')); };
  });

  /* ---------------- 概览 ---------------- */
  function kpi(label, val, unit, sub) {
    return '<div class="kpi"><div class="l">' + esc(label) + '</div>' +
      '<div class="v">' + val + (unit ? '<small>' + esc(unit) + '</small>' : '') + '</div>' +
      (sub ? '<div class="s">' + esc(sub) + '</div>' : '') + '</div>';
  }

  function loadOverview() {
    api('/api/jifen/admin/overview').then(function (d) {
      if (!d.success) { toast(d.error || '加载失败', true); return; }
      var s = d.stats;
      $('ovTime').textContent = '数据实时 · ' + new Date().toLocaleString('zh-CN', { hour12: false });
      $('kpis').innerHTML =
        kpi('积分账户', n(s.acc_n), '个', '共发放 ' + n(s.earned_total) + ' 分') +
        kpi('可自助查询', n(s.acc_phone), '人', '已登记手机号，占比 ' +
          (s.acc_n ? Math.round(s.acc_phone * 100 / s.acc_n) : 0) + '%') +
        kpi('积分余额', n(s.acc_points), '分', '已被兑换 ' + n(s.spent_total) + ' 分') +
        kpi('兑换单', n(s.order_n), '笔', '累计兑换 ' + n(s.redeem_points) + ' 分') +
        kpi('待领取', n(s.pending), '笔', '需在核销台处理') +
        kpi('今日新增积分', '+' + n(s.today_earn), '分', '今日兑换 ' + n(s.today_orders) + ' 笔') +
        kpi('上架商品', n(s.goods_n), '种', '库存合计 ' + n(s.stock_total) + ' 件');

      var os = d.recent || [];
      $('ovOrders').innerHTML = os.length ? os.map(function (o) {
        return '<div class="prow" style="cursor:default"><span class="pn">' + esc(o.name) +
          ' <span class="mut" style="font-weight:400">' + esc(o.items_text) + '</span></span>' +
          '<span class="pg">' + esc(o.status) + '</span>' +
          '<span class="pp">-' + n(o.points) + '</span></div>';
      }).join('') : '<div class="empty">暂无兑换记录</div>';

      var ls = d.low_stock || [];
      $('ovStock').innerHTML = ls.length ? ls.map(function (g) {
        return '<div class="prow" style="cursor:default"><span class="pn">' + esc(g.icon) + ' ' + esc(g.name) + '</span>' +
          '<span class="pg">' + esc(g.cat) + '</span>' +
          '<span class="pp" style="color:' + (g.stock <= 0 ? '#b91c1c' : '#b45309') + '">' + g.stock + ' 件</span></div>';
      }).join('') : '<div class="empty">库存充足 👍</div>';
    });
  }

  /* ---------------- 商品 ---------------- */
  function loadGoods(keep) {
    api('/api/jifen/admin/goods').then(function (d) {
      if (!d.success) { toast(d.error || '加载失败', true); return; }
      S.goods = d.goods || [];
      renderGoods();
    });
  }

  function renderGoods() {
    var kw = ($('gsearch').value || '').trim();
    var list = S.goods.filter(function (g) {
      return !kw || g.name.indexOf(kw) >= 0 || g.cat.indexOf(kw) >= 0;
    });
    var h = '<thead><tr><th style="width:60px">图标</th><th>商品名称</th><th>分类</th><th>规格</th>' +
      '<th class="r">所需积分</th><th class="r">库存</th><th class="r">已兑</th><th class="c">限兑</th>' +
      '<th class="c">状态</th><th class="c">操作</th></tr></thead><tbody>';
    if (!list.length) h += '<tr><td colspan="10"><div class="empty">暂无商品</div></td></tr>';
    list.forEach(function (g) {
      h += '<tr><td style="font-size:22px;text-align:center">' + esc(g.icon) + '</td>' +
        '<td class="nm">' + esc(g.name) + '</td>' +
        '<td class="mut">' + esc(g.cat) + '</td>' +
        '<td class="mut">' + esc(g.spec || '—') + '</td>' +
        '<td class="r"><b style="color:#c2410c">' + n(g.points) + '</b></td>' +
        '<td class="r">' + (g.stock <= 0 ? '<span class="tag rest">0</span>'
          : (g.stock <= 5 ? '<span class="tag low">' + g.stock + '</span>' : g.stock)) + '</td>' +
        '<td class="r mut">' + n(g.sold) + '</td>' +
        '<td class="c mut">' + (g.limit_per ? g.limit_per : '不限') + '</td>' +
        '<td class="c"><span class="tag ' + (g.status === '上架' ? 'on' : 'off') + '">' + esc(g.status) + '</span></td>' +
        '<td class="c"><div class="acts" style="justify-content:center">' +
        '<button class="btn sm ghost" data-gedit="' + esc(g.id) + '">编辑</button>' +
        '<button class="btn sm ghost" data-gtoggle="' + esc(g.id) + '">' + (g.status === '上架' ? '下架' : '上架') + '</button>' +
        '<button class="btn sm danger" data-gdel="' + esc(g.id) + '">删除</button></div></td></tr>';
    });
    $('tGoods').innerHTML = h + '</tbody>';
  }

  function goodsForm(id) {
    var g = id ? S.goods.filter(function (x) { return x.id === id; })[0] : null;
    g = g || { name: '', cat: '日用百货', icon: '🎁', spec: '', points: 20, stock: 20, limit_per: 0, desc: '', status: '上架', sort: 0 };
    var cats = ['食品粮油', '日用百货', '清洁洗护', '学习用品', '其他'];
    modal(id ? '编辑商品' : '新增商品',
      '<label class="fld"><span>商品名称 *</span><input id="f_name" value="' + esc(g.name) + '" placeholder="如：洗衣粉 500g"></label>' +
      '<label class="fld"><span>分类</span><select id="f_cat">' + cats.map(function (c) {
        return '<option' + (c === g.cat ? ' selected' : '') + '>' + c + '</option>';
      }).join('') + '</select></label>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">' +
      '<label class="fld"><span>图标（emoji）</span><input id="f_icon" value="' + esc(g.icon) + '" maxlength="4"></label>' +
      '<label class="fld"><span>规格</span><input id="f_spec" value="' + esc(g.spec) + '" placeholder="如 500g/袋"></label>' +
      '</div><div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px">' +
      '<label class="fld"><span>所需积分 *</span><input id="f_points" type="number" min="1" value="' + g.points + '"></label>' +
      '<label class="fld"><span>库存</span><input id="f_stock" type="number" min="0" value="' + g.stock + '"></label>' +
      '<label class="fld"><span>限兑/人</span><input id="f_limit" type="number" min="0" value="' + g.limit_per + '"></label>' +
      '</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">' +
      '<label class="fld"><span>状态</span><select id="f_status"><option' + (g.status === '上架' ? ' selected' : '') + '>上架</option>' +
      '<option' + (g.status !== '上架' ? ' selected' : '') + '>下架</option></select></label>' +
      '<label class="fld"><span>排序（小在前）</span><input id="f_sort" type="number" value="' + (g.sort || 0) + '"></label>' +
      '</div><label class="fld"><span>商品说明</span><input id="f_desc" value="' + esc(g.desc) + '" placeholder="选填"></label>' +
      '<div class="fld-tip" style="text-align:left">限兑填 0 表示不限；留空库存沿用当前值。</div>',
      '<button class="btn ghost" data-close>取消</button><button class="btn primary" id="f_save">保存</button>',
      function () {
        $('f_save').onclick = function () {
          var body = {
            id: id || '', name: $('f_name').value.trim(), cat: $('f_cat').value,
            icon: $('f_icon').value.trim() || '🎁', spec: $('f_spec').value.trim(),
            points: Number($('f_points').value) || 1, stock: Number($('f_stock').value) || 0,
            limit_per: Number($('f_limit').value) || 0, status: $('f_status').value,
            sort: Number($('f_sort').value) || 0, desc: $('f_desc').value.trim()
          };
          if (!body.name) { toast('请填写商品名称', true); return; }
          api('/api/jifen/admin/goods_save', body).then(function (d) {
            if (!d.success) { toast(d.error || '保存失败', true); return; }
            toast('已保存'); closeMask(); loadGoods();
          });
        };
      });
  }

  /* ---------------- 积分发放 ---------------- */
  function loadGrant() {
    api('/api/jifen/admin/rules').then(function (d) {
      if (d.success) {
        S.rules = d.rules || [];
        $('grRule').innerHTML = '<option value="">— 自定义 —</option>' + S.rules.filter(function (r) { return r.enabled; })
          .map(function (r) {
            return '<option value="' + esc(r.id) + '" data-p="' + r.points + '">' + esc(r.name) + '（+' + r.points + ' ' + esc(r.unit) + '）</option>';
          }).join('');
      }
    });
    loadGrantPeople('');
  }

  function loadGrantPeople(kw) {
    S.grantKw = kw;
    return api('/api/jifen/admin/accounts?kw=' + encodeURIComponent(kw) + '&size=200&page=1').then(function (d) {
      if (!d.success) { toast(d.error || '加载失败', true); return; }
      S.grantList = d.accounts || [];
      S.grantTotal = d.total || 0;
      renderGrantPeople(d.total);
    });
  }

  function renderGrantPeople(total) {
    if (!S.grantList.length) {
      $('grPeople').innerHTML = '<div class="empty">没有匹配的账户<br>可先在「积分账户」里新增或从户籍导入</div>';
      $('grQuick').innerHTML = '';
      return;
    }
    var h = S.grantList.map(function (a) {
      return '<label class="prow"><input type="checkbox" data-pick="' + esc(a.id) + '"' +
        (S.picked[a.id] ? ' checked' : '') + '>' +
        '<span class="pn">' + esc(a.name) + '</span>' +
        '<span class="pg">' + esc((a.grp || '未分组').replace('组', '') + '组') + '</span>' +
        '<span class="pp">' + n(a.points) + '</span></label>';
    }).join('');
    if (total > S.grantList.length) {
      h += '<div class="empty" style="padding:12px">共 ' + total + ' 人，此处显示前 ' + S.grantList.length + ' 人，请用搜索缩小范围</div>';
    }
    $('grPeople').innerHTML = h;
    renderQuickGroups();
    syncGrantCount();
  }

  /* 按组快速勾选：点一次把该组在当前列表中的人全部选上 / 取消 */
  function renderQuickGroups() {
    var cnt = {};
    S.grantList.forEach(function (a) { var g = a.grp || '未分组'; cnt[g] = (cnt[g] || 0) + 1; });
    var groups = Object.keys(cnt).sort();
    if (!groups.length) { $('grQuick').innerHTML = ''; return; }
    $('grQuick').innerHTML = groups.map(function (g) {
      return '<button class="chip" data-grp="' + esc(g) + '">' + esc(g.replace('组', '')) + ' ' + cnt[g] + ' 人</button>';
    }).join('') + '<button class="chip" data-grp-clear="1">清空</button>';
  }

  function pickList() { return Object.keys(S.picked).filter(function (k) { return S.picked[k]; }); }

  function syncGrantCount() {
    var ids = pickList();
    var pts = Number($('grPoints').value) || 0;
    $('grCount').textContent = ids.length;
    $('grSum').textContent = n(ids.length * pts);
  }

  function doGrant() {
    var ids = pickList();
    if (!ids.length) { toast('请先勾选发放对象', true); return; }
    var pts = Number($('grPoints').value) || 0;
    if (!pts) { toast('分值不能为 0', true); return; }
    var reason = $('grReason').value.trim();
    var rule = $('grRule').selectedOptions[0];
    if (!reason) reason = rule && rule.value ? rule.textContent.split('（')[0] : '积分发放';
    if (!confirm('确认为 ' + ids.length + ' 人各' + (pts > 0 ? '发放' : '扣减') + ' ' + Math.abs(pts) + ' 分？\n事由：' + reason)) return;
    var btn = $('btnGrant');
    btn.disabled = true; btn.textContent = '提交中…';
    api('/api/jifen/admin/points', { acc_ids: ids, points: pts, reason: reason }).then(function (d) {
      btn.disabled = false; btn.textContent = '确认发放';
      if (!d.success) { toast(d.error || '发放失败', true); return; }
      toast(d.message || '已发放');
      S.picked = {}; $('grAll').checked = false;
      loadGrantPeople(S.grantKw);
    }).catch(function () { btn.disabled = false; btn.textContent = '确认发放'; });
  }

  /* ---------------- 核销 ---------------- */
  function loadVerify() { $('vResult').innerHTML = ''; }

  function findOrder() {
    var code = ($('vCode').value || '').trim();
    if (!code) { toast('请输入取货码', true); return; }
    api('/api/jifen/admin/orders?kw=' + encodeURIComponent(code) + '&size=20&page=1').then(function (d) {
      if (!d.success) { toast(d.error || '查询失败', true); return; }
      var hit = (d.orders || []).filter(function (o) { return o.code === code; })[0];
      if (!hit) {
        $('vResult').innerHTML = '<div class="vcard bad"><div class="vc-top"><span class="vc-code">' + esc(code) +
          '</span><span class="tag rest">未找到</span></div><div class="vc-meta">没有这个取货码的兑换单，请核对后重试。</div></div>';
        return;
      }
      renderVerifyCard(hit);
    });
  }

  function renderVerifyCard(o) {
    var tag = o.status === '待领取' ? 'wait' : (o.status === '已领取' ? 'done' : 'cancel');
    $('vResult').innerHTML = '<div class="vcard ' + (o.status === '待领取' ? 'ok' : '') + '">' +
      '<div class="vc-top"><span class="vc-code">' + esc(o.code) + '</span>' +
      '<span class="tag ' + tag + '">' + esc(o.status) + '</span></div>' +
      '<div class="vc-items">' + o.items.map(function (i) {
        return esc(i.icon) + ' ' + esc(i.name) + ' × <b>' + i.qty + '</b>';
      }).join('<br>') + '</div>' +
      '<div class="vc-meta">兑换人：' + esc(o.name) + '（' + esc(o.grp || '未分组') + '）· ' + esc(o.phone || '无电话') + '<br>' +
      '扣减 ' + n(o.points) + ' 分 · 下单 ' + esc(o.created) +
      (o.done_at ? '<br>领取 ' + esc(o.done_at) + ' · 经办 ' + esc(o.operator) : '') + '</div>' +
      '<div class="acts" style="margin-top:12px">' +
      (o.status === '待领取'
        ? '<button class="btn ok" data-odone="' + esc(o.id) + '">✓ 确认已领取</button>' +
        '<button class="btn danger" data-ocancel="' + esc(o.id) + '">取消并退分</button>'
        : '') +
      '</div></div>';
  }

  function loadOrderList() {
    var q = '/api/jifen/admin/orders?status=' + encodeURIComponent(S.ordStatus) +
      '&kw=' + encodeURIComponent(S.ordKw) + '&page=' + S.ordPage + '&size=' + S.ordSize;
    api(q).then(function (d) {
      if (!d.success) { toast(d.error || '加载失败', true); return; }
      S.orders = d.orders || []; S.ordTotal = d.total || 0;
      renderOrderList();
    });
  }

  function renderOrderList() {
    if (!S.orders.length) { $('orderList').innerHTML = '<div class="empty" style="background:#fff;border:1px solid var(--line);border-radius:12px">暂无兑换单</div>'; $('orderPager').innerHTML = ''; return; }
    $('orderList').innerHTML = '<div class="olist">' + S.orders.map(function (o) {
      var tag = o.status === '待领取' ? 'wait' : (o.status === '已领取' ? 'done' : 'cancel');
      return '<div class="oc"><div class="oc-top">' +
        '<span class="oc-code">' + esc(o.code) + '</span>' +
        '<span class="oc-nm">' + esc(o.name) + '</span>' +
        '<span class="mut" style="font-size:12px">' + esc(o.grp || '') + '</span>' +
        '<span class="tag ' + tag + '">' + esc(o.status) + '</span></div>' +
        '<div class="oc-items">' + o.items.map(function (i) { return esc(i.icon) + ' ' + esc(i.name) + '×' + i.qty; }).join('　') + '</div>' +
        '<div class="oc-foot"><span>' + esc(o.created) + '</span><span>扣 ' + n(o.points) + ' 分</span>' +
        '<span>' + (o.src === 'offline' ? '现场代兑' : '村民自助') + '</span>' +
        '<div class="acts">' + (o.status === '待领取'
          ? '<button class="btn sm ok" data-odone="' + esc(o.id) + '">已领取</button>' +
          '<button class="btn sm danger" data-ocancel="' + esc(o.id) + '">取消</button>'
          : '<button class="btn sm ghost" data-oview="' + esc(o.id) + '">详情</button>') +
        '</div></div></div>';
    }).join('') + '</div>';
    renderPager('orderPager', S.ordPage, S.ordSize, S.ordTotal, function (p) { S.ordPage = p; loadOrderList(); });
  }

  function renderPager(id, page, size, total, go) {
    var pages = Math.max(1, Math.ceil(total / size));
    $(id).innerHTML = '<span>共 ' + n(total) + ' 条 · 第 ' + page + '/' + pages + ' 页</span>' +
      '<button' + (page <= 1 ? ' disabled' : '') + ' data-pg="' + (page - 1) + '">上一页</button>' +
      '<button' + (page >= pages ? ' disabled' : '') + ' data-pg="' + (page + 1) + '">下一页</button>';
    $(id).querySelectorAll('[data-pg]').forEach(function (b) {
      b.onclick = function () { go(Number(b.getAttribute('data-pg'))); };
    });
  }

  /* ---------------- 账户 ---------------- */
  function loadAccounts() {
    if (S.accView === 'house') return loadHouses();
    $('houseHint').innerHTML = '';
    var q = '/api/jifen/admin/accounts?kw=' + encodeURIComponent(S.accKw) +
      '&page=' + S.accPage + '&size=' + S.accSize;
    api(q).then(function (d) {
      if (!d.success) { toast(d.error || '加载失败', true); return; }
      S.accounts = d.accounts || []; S.accTotal = d.total || 0;
      renderAccounts();
    });
  }

  /* ---------------- 按户统计 ---------------- */
  function loadHouses() {
    var q = '/api/jifen/admin/houses?kw=' + encodeURIComponent(S.accKw) +
      '&page=' + S.accPage + '&size=' + S.accSize;
    api(q).then(function (d) {
      if (!d.success) { toast(d.error || '加载失败', true); return; }
      S.houses = d.houses || []; S.houseTotal = d.total || 0; S.unhoused = d.unhoused || 0;
      renderHouses();
    });
  }

  function renderHouses() {
    $('houseHint').innerHTML = '共 <b>' + n(S.houseTotal) + '</b> 户 · 分户依据：家庭成员健康信息表（户主+与户主关系）' +
      '，缺档人员按手机号/户籍地址补 · 户积分 = 户内成员当前积分之和' +
      (S.unhoused ? ' · <span style="color:#b45309">' + n(S.unhoused) + ' 个账户未归户</span>' : '') +
      ' · 分错的可点「分户调整」人工修正' +
      ' <button class="btn sm ghost" data-hexport="1" style="margin-left:8px">导出户表 CSV</button>';
    var h = '<thead><tr><th>户主（推定）</th><th>村民组</th><th>户籍地址</th>' +
      '<th class="r">在册人数</th><th class="r">户积分</th><th class="r">累计获得</th>' +
      '<th class="r">累计兑换</th><th class="c">有积分人数</th><th class="c">操作</th></tr></thead><tbody>';
    if (!S.houses.length) {
      h += '<tr><td colspan="9"><div class="empty">暂无数据<br>先在「按人」视图点「从户籍导入」建立账户</div></td></tr>';
    }
    S.houses.forEach(function (x) {
      h += '<tr><td class="nm">' + esc(x.zhu || '—') +
        (x.wait ? ' <span class="tag wait" title="有 ' + x.wait + ' 人同址多户，自动并入本户，建议核对">待核' + x.wait + '</span>' : '') +
        '</td>' +
        '<td class="mut">' + esc((x.grp || '—').replace('组', '')) + '</td>' +
        '<td class="mut">' + esc(x.addr || '—') + '</td>' +
        '<td class="r mut">' + n(x.members) + '</td>' +
        '<td class="r"><b style="color:#c2410c">' + n(x.points) + '</b></td>' +
        '<td class="r mut">' + n(x.earned) + '</td>' +
        '<td class="r mut">' + n(x.spent) + '</td>' +
        '<td class="c mut">' + n(x.act) + '</td>' +
        '<td class="c"><button class="btn sm ghost" data-hview="' + esc(x.hu) + '">查看成员</button></td></tr>';
    });
    $('tAcc').innerHTML = h + '</tbody>';
    renderPager('accPager', S.accPage, S.accSize, S.houseTotal, function (p) { S.accPage = p; loadHouses(); });
  }

  /* ---------------- 分户核对 ---------------- */
  function huReview() {
    api('/api/jifen/admin/hu_review?n=500').then(function (d) {
      if (!d.success) { toast(d.error || '加载失败', true); return; }
      S.huWait = d.wait || []; S.huSingle = d.single || [];
      var h = '<div class="hint" style="margin:0 0 12px;line-height:1.7">' +
        '自动分户已按健康表「户主 + 与户主关系」完成。<br>' +
        '下面两类建议人工过一眼：<b>' + S.huWait.length + '</b> 人『待核』（同一门牌下有多户，先并入了人数最多的一户）、' +
        '<b>' + S.huSingle.length + '</b> 个『单户口』（户里只有 1 人，可能是漏登记或分错）。</div>';
      h += '<h4 style="margin:14px 0 8px;font-size:13px">一、待核人员</h4>';
      h += '<div class="tbl-wrap" style="max-height:240px"><table class="tbl"><thead><tr>' +
        '<th>姓名</th><th>组别</th><th>已并入</th><th>电话</th><th class="r">积分</th><th class="c">操作</th>' +
        '</tr></thead><tbody>';
      if (!S.huWait.length) h += '<tr><td colspan="6"><div class="empty">没有待核人员</div></td></tr>';
      S.huWait.forEach(function (x) {
        h += '<tr><td class="nm">' + esc(x.name) + '</td><td class="mut">' + esc((x.grp || '').replace('组', '')) + '</td>' +
          '<td class="mut">' + esc(x.zhu || '—') + '</td><td class="mut">' + esc(x.phone || '—') + '</td>' +
          '<td class="r mut">' + n(x.points) + '</td>' +
          '<td class="c"><button class="btn sm ghost" data-hmove="' + esc(x.id) + '" data-hname="' + esc(x.name) + '">调户</button></td></tr>';
      });
      h += '</tbody></table></div>';
      h += '<h4 style="margin:16px 0 8px;font-size:13px">二、单户口</h4>';
      h += '<div class="tbl-wrap" style="max-height:240px"><table class="tbl"><thead><tr>' +
        '<th>户主</th><th>组别</th><th>户籍地址</th><th class="c">操作</th></tr></thead><tbody>';
      if (!S.huSingle.length) h += '<tr><td colspan="4"><div class="empty">没有单户口</div></td></tr>';
      S.huSingle.forEach(function (x) {
        h += '<tr><td class="nm">' + esc(x.zhu || x.name || '—') + '</td>' +
          '<td class="mut">' + esc((x.grp || '').replace('组', '')) + '</td>' +
          '<td class="mut">' + esc(x.addr || '—') + '</td>' +
          '<td class="c"><button class="btn sm ghost" data-hview="' + esc(x.hu) + '">查看</button></td></tr>';
      });
      h += '</tbody></table></div>';
      modal('分户核对', h, '<button class="btn ghost" data-close>关闭</button>', function (body) {
        body.querySelectorAll('[data-hmove]').forEach(function (b) {
          b.onclick = function () { pickHouse(b.getAttribute('data-hmove'), b.getAttribute('data-hname')); };
        });
        body.querySelectorAll('[data-hview]').forEach(function (b) {
          b.onclick = function () { huReviewClose(); houseForm(b.getAttribute('data-hview')); };
        });
      }, true);
    });
  }

  function huReviewClose() { closeMask(); }

  function pickHouse(accId, accName) {
    modal('把「' + accName + '」并入哪一户？',
      '<label class="fld"><span>搜索户主 / 组别 / 地址</span>' +
      '<input id="phKw" placeholder="如：罗仁德 或 白粉墙" autocomplete="off"></label>' +
      '<div id="phList" style="max-height:320px;overflow:auto"></div>',
      '<button class="btn ghost" data-close>取消</button>', function () {
        function search() {
          var kw = $('phKw').value.trim();
          api('/api/jifen/admin/houses?kw=' + encodeURIComponent(kw) + '&page=1&size=40')
            .then(function (d) {
              var list = d.houses || [];
              var h = '';
              list.forEach(function (x) {
                h += '<div data-hu="' + esc(x.hu) + '" style="display:flex;justify-content:space-between;' +
                  'gap:10px;padding:9px 10px;border-bottom:1px solid #f7f3ee;cursor:pointer">' +
                  '<span><b>' + esc(x.zhu || '—') + '</b> <span class="mut">' +
                  esc((x.grp || '').replace('组', '')) + ' · ' + n(x.members) + ' 人</span></span>' +
                  '<span class="mut" style="text-align:right;max-width:52%">' + esc(x.addr || '') + '</span></div>';
              });
              $('phList').innerHTML = h || '<div class="empty">没有匹配的户</div>';
              $('phList').querySelectorAll('[data-hu]').forEach(function (r) {
                r.onclick = function () { doMove(accId, r.getAttribute('data-hu')); };
              });
            });
        }
        var pt = null;
        $('phKw').oninput = function () { clearTimeout(pt); pt = setTimeout(search, 250); };
        search();
        setTimeout(function () { $('phKw').focus(); }, 150);
      }, true);
  }

  function doMove(accId, hu) {
    api('/api/jifen/admin/acct_hu', { id: accId, hu: hu }).then(function (d) {
      if (!d.success) { toast(d.error || '调户失败', true); return; }
      toast('已并入「' + d.zhu + '」户');
      closeMask();
      if (S.accView === 'house') loadHouses(); else loadAccounts();
    });
  }

  /* ---------------- 分户调整（多选 → 并入已有户 / 新建一户 / 移出 / 恢复自动） ---------------- */
  function huAssign(seed) {
    S.huSel = {}; S.huMode = 'join'; S.huPick = ''; S.huHits = [];
    (seed || []).forEach(function (x) {
      if (x && x.id) S.huSel[x.id] = { name: x.name || '', grp: x.grp || '' };
    });
    modal('分户调整',
      '<div class="hint" style="margin:0 0 10px;line-height:1.7">勾选人员 → 选择归到哪一户 → 确认。' +
      '人工调整后这些人会被锁定，自动分户不再覆盖；想交还自动判断就选「恢复自动」。</div>' +
      '<div class="ha-grid">' +
      '<div><div class="ha-h">一、选择人员 <span class="mut" id="haCnt"></span></div>' +
      '<input class="srch" id="haKw" style="width:100%" placeholder="姓名 / 手机 / 组别 / 户主 / 积分码" autocomplete="off">' +
      '<div class="ha-list" id="haList" style="margin-top:8px"><div class="loading">加载中…</div></div>' +
      '<div class="ha-sel" id="haSel"></div></div>' +
      '<div><div class="ha-h">二、归到哪一户</div>' +
      '<div class="seg" id="haMode">' +
      '<button class="on" data-hm="join">并入已有户</button><button data-hm="new">新建一户</button>' +
      '<button data-hm="none">移出本户</button><button data-hm="auto">恢复自动</button></div>' +
      '<div id="haPane" style="margin-top:10px"></div></div></div>',
      '<button class="btn ghost" data-close>取消</button><button class="btn primary" id="haGo">确认调整</button>',
      function () {
        var tm = null;
        $('haKw').oninput = function () { clearTimeout(tm); tm = setTimeout(huSearch, 260); };
        document.querySelectorAll('#haMode button').forEach(function (b) {
          b.onclick = function () {
            S.huMode = b.getAttribute('data-hm');
            document.querySelectorAll('#haMode button').forEach(function (x) {
              x.classList.toggle('on', x === b);
            });
            huPane();
          };
        });
        $('haGo').onclick = huApply;
        huSearch(); huPane();
      }, true);
  }

  function huSearch() {
    var box = $('haList');
    if (!box) return;
    var kw = $('haKw') ? $('haKw').value.trim() : '';
    api('/api/jifen/admin/accounts?kw=' + encodeURIComponent(kw) + '&page=1&size=60').then(function (d) {
      if (!d.success) { box.innerHTML = '<div class="empty">加载失败</div>'; return; }
      S.huHits = d.accounts || [];
      var h = '';
      S.huHits.forEach(function (a) {
        var sel = !!S.huSel[a.id];
        var now = a.hu_zhu
          ? '现属「' + esc(a.hu_zhu) + '」' + (a.hu_src === '人工' ? ' <b style="color:#c2410c">人工</b>' : '')
          : '<span style="color:#b45309">未归户</span>';
        h += '<div class="ha-item' + (sel ? ' on' : '') + '" data-hid="' + esc(a.id) + '">' +
          '<input type="checkbox"' + (sel ? ' checked' : '') + ' style="pointer-events:none">' +
          '<span><span class="nmx">' + esc(a.name) + '</span> <span class="sub">' +
          esc((a.grp || '').replace('组', '') || '组别未填') +
          (a.phone ? ' · ' + esc(a.phone) : '') + '</span></span>' +
          '<span class="sp"></span><span class="sub">' + now + '</span></div>';
      });
      box.innerHTML = h || '<div class="empty">没有匹配的账户</div>';
      box.querySelectorAll('[data-hid]').forEach(function (row) {
        row.onclick = function () {
          var id = row.getAttribute('data-hid');
          var a = S.huHits.filter(function (x) { return x.id === id; })[0] || {};
          if (S.huSel[id]) delete S.huSel[id];
          else S.huSel[id] = { name: a.name || '', grp: a.grp || '' };
          row.querySelector('input').checked = !!S.huSel[id];
          row.classList.toggle('on', !!S.huSel[id]);
          huSelInfo();
        };
      });
      huSelInfo();
    });
  }

  function huSelInfo() {
    var ids = Object.keys(S.huSel);
    var names = ids.slice(0, 12).map(function (i) { return S.huSel[i].name; }).join('、');
    if ($('haCnt')) $('haCnt').textContent = ids.length ? '已选 ' + ids.length + ' 人' : '';
    if (!$('haSel')) return;
    $('haSel').innerHTML = ids.length
      ? '已选 <b style="color:#c2410c">' + ids.length + '</b> 人：' + esc(names) +
        (ids.length > 12 ? ' 等' : '') +
        ' <button class="btn sm ghost" id="haClear" style="margin-left:6px">清空</button>'
      : '还没有选人：在上方搜索后点一下即可勾选（同名的人看组别、电话区分）';
    if ($('haClear')) $('haClear').onclick = function () { S.huSel = {}; huSearch(); };
  }

  function huPane() {
    var p = $('haPane');
    if (!p) return;
    if (S.huMode === 'join') {
      p.innerHTML = '<input class="srch" id="hhKw" style="width:100%" placeholder="搜索户主 / 组别 / 地址" autocomplete="off">' +
        '<div class="ha-list" id="hhList" style="margin-top:8px"><div class="loading">加载中…</div></div>' +
        '<div class="ha-sel">点一下选中目标户（呈橙色即已选中）</div>';
      var tm = null;
      $('hhKw').oninput = function () { clearTimeout(tm); tm = setTimeout(huHouseSearch, 260); };
      huHouseSearch();
    } else if (S.huMode === 'new') {
      var ids = Object.keys(S.huSel);
      var g = ids.length ? (S.huSel[ids[0]].grp || '') : '';
      p.innerHTML = '<label class="fld"><span>新户户主姓名 *</span><input id="haZhu" placeholder="以谁为户主就填谁"></label>' +
        '<label class="fld"><span>村民组 *</span><input id="haGrp" value="' + esc(g) + '" placeholder="如 白岩塘组"></label>' +
        '<div class="hint" style="margin:-4px 0 0;line-height:1.7">户主排本户第 1 位；该组若已有同名户，会直接并入那一户。</div>';
    } else if (S.huMode === 'none') {
      p.innerHTML = '<div class="hint" style="margin:0;line-height:1.8">把选中的人从现在的户里<b>移出</b>，暂不归户。' +
        '他们仍能正常查分、兑换，只是不计入任何一户的合计；之后可再并入正确的户。</div>';
    } else {
      p.innerHTML = '<div class="hint" style="margin:0;line-height:1.8">解除人工锁定，按「健康信息表 → 手机号 → 户籍地址」' +
        '重新自动归户。之前手工指定给这些人的户会被<b>覆盖</b>。</div>';
    }
  }

  function huHouseSearch() {
    var box = $('hhList');
    if (!box) return;
    var kw = $('hhKw') ? $('hhKw').value.trim() : '';
    api('/api/jifen/admin/houses?kw=' + encodeURIComponent(kw) + '&page=1&size=40').then(function (d) {
      var list = d.houses || [];
      var h = '';
      list.forEach(function (x) {
        h += '<div class="ha-item' + (S.huPick === x.hu ? ' on' : '') + '" data-hp="' + esc(x.hu) + '">' +
          '<span><span class="nmx">' + esc(x.zhu || '—') + '</span> <span class="sub">' +
          esc((x.grp || '').replace('组', '')) + ' · ' + n(x.members) + ' 人</span></span>' +
          '<span class="sp"></span><span class="sub" style="text-align:right;max-width:52%">' +
          esc(x.addr || '') + '</span></div>';
      });
      box.innerHTML = h || '<div class="empty">没有匹配的户</div>';
      box.querySelectorAll('[data-hp]').forEach(function (r) {
        r.onclick = function () {
          S.huPick = r.getAttribute('data-hp');
          box.querySelectorAll('[data-hp]').forEach(function (y) { y.classList.toggle('on', y === r); });
        };
      });
    });
  }

  function huApply() {
    var ids = Object.keys(S.huSel);
    if (!ids.length) { toast('请先勾选人员', true); return; }
    var body = { ids: ids, mode: S.huMode };
    if (S.huMode === 'join') {
      if (!S.huPick) { toast('请先选中要并入的户', true); return; }
      body.hu = S.huPick;
    } else if (S.huMode === 'new') {
      body.zhu = $('haZhu').value.trim();
      body.grp = $('haGrp').value.trim();
      if (!body.zhu) { toast('请填写新户户主姓名', true); return; }
    }
    var btn = $('haGo');
    btn.disabled = true;
    api('/api/jifen/admin/hu_assign', body).then(function (d) {
      btn.disabled = false;
      if (!d.success) { toast(d.error || '调整失败', true); return; }
      toast(d.message || '已调整');
      closeMask();
      if (S.accView === 'house') loadHouses(); else loadAccounts();
    }).catch(function () { btn.disabled = false; });
  }

  function houseForm(hu) {
    api('/api/jifen/admin/house?hu=' + encodeURIComponent(hu)).then(function (d) {
      if (!d.success) { toast(d.error || '加载失败', true); return; }
      var h = d.house, t = h.total;
      var rows = h.members.map(function (m) {
        return '<tr><td class="nm">' + esc(m.name) +
          (m.hu_src === '人工' ? ' <span class="tag wait" title="人工指定过归属">人工</span>' : '') + '</td>' +
          '<td class="mut">' + esc(m.phone || '—') + '</td>' +
          '<td class="r"><b style="color:#c2410c">' + n(m.points) + '</b></td>' +
          '<td class="r mut">' + n(m.earned) + '</td>' +
          '<td class="r mut">' + n(m.spent) + '</td>' +
          '<td class="c"><span class="tag ' + (m.status === '正常' ? 'on' : 'off') + '">' + esc(m.status) + '</span></td>' +
          '<td class="c"><button class="btn sm ghost" data-hadj="' + esc(m.id) + '">调出</button></td></tr>';
      }).join('');
      var tx = (h.txns || []).map(function (x) {
        return '<tr><td class="mut">' + esc(x.created) + '</td><td>' + esc(x.name) + '</td>' +
          '<td>' + esc(x.reason || '') + '</td>' +
          '<td class="r" style="color:' + (x.points >= 0 ? '#15803d' : '#b91c1c') + '">' +
          (x.points > 0 ? '+' : '') + n(x.points) + '</td></tr>';
      }).join('');
      modal('户积分明细 · ' + (h.zhu || '') + '（' + (h.addr || '') + '）',
        '<div class="hint" style="margin-bottom:8px;">在册 <b>' + t.members + '</b> 人 · 户积分合计 <b>' +
        n(t.points) + '</b> 分（累计获得 ' + n(t.earned) + '，累计兑换 ' + n(t.spent) + '）</div>' +
        '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>姓名</th><th>电话</th>' +
        '<th class="r">当前积分</th><th class="r">累计获得</th><th class="r">累计兑换</th><th class="c">状态</th>' +
        '<th class="c">操作</th>' +
        '</tr></thead><tbody>' + rows + '</tbody></table></div>' +
        (tx ? '<div style="font-size:13px;font-weight:700;margin:14px 0 8px;">本户最近流水</div>' +
          '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>时间</th><th>姓名</th><th>事由</th>' +
          '<th class="r">变动</th></tr></thead><tbody>' + tx + '</tbody></table></div>' : ''),
        '<button class="btn ghost" data-close>关闭</button>' +
        '<button class="btn primary" id="hfEdit">调整本户成员</button>', function (body) {
          var seed = h.members.map(function (m) {
            return { id: m.id, name: m.name, grp: m.grp || h.grp || '' };
          });
          $('hfEdit').onclick = function () { huAssign(seed); };
          body.querySelectorAll('[data-hadj]').forEach(function (b) {
            b.onclick = function () {
              var m = h.members.filter(function (x) { return x.id === b.getAttribute('data-hadj'); })[0];
              if (m) huAssign([{ id: m.id, name: m.name, grp: m.grp || h.grp || '' }]);
            };
          });
        }, true);
    });
  }

  function renderAccounts() {
    var h = '<thead><tr><th>姓名</th><th>组别</th><th>所属户</th><th>电话</th><th>积分码</th><th class="r">当前积分</th>' +
      '<th class="r">累计获得</th><th class="r">累计兑换</th><th class="c">状态</th><th class="c">操作</th></tr></thead><tbody>';
    if (!S.accounts.length) h += '<tr><td colspan="10"><div class="empty">暂无账户<br>点右上角「从户籍导入」可一键建立全村账户</div></td></tr>';
    S.accounts.forEach(function (a) {
      var huHtml;
      if (a.hu_zhu) {
        huHtml = esc(a.hu_zhu) +
          (a.hu_src === '人工' ? ' <span class="tag wait" title="人工调整过，自动分户不再覆盖">人工</span>'
            : (a.hu_src === '待核' ? ' <span class="tag wait" title="同址多户，自动并入人数最多的一户，建议核对">待核</span>' : ''));
      } else {
        huHtml = '<span style="color:#b45309">未归户</span>';
      }
      h += '<tr><td class="nm">' + esc(a.name) + '</td>' +
        '<td class="mut">' + esc((a.grp || '—').replace('组', '')) + '</td>' +
        '<td class="mut">' + huHtml + '</td>' +
        '<td class="mut">' + esc(a.phone || '—') + '</td>' +
        '<td class="mut">' + (a.code
          ? '<b style="color:#c2410c;letter-spacing:.6px">' + esc(a.code) + '</b>'
          : '<span style="color:#b45309">无码</span>') + '</td>' +
        '<td class="r"><b style="color:#c2410c">' + n(a.points) + '</b></td>' +
        '<td class="r mut">' + n(a.earned) + '</td>' +
        '<td class="r mut">' + n(a.spent) + '</td>' +
        '<td class="c"><span class="tag ' + (a.status === '正常' ? 'on' : 'off') + '">' + esc(a.status) + '</span></td>' +
        '<td class="c"><div class="acts" style="justify-content:center">' +
        '<button class="btn sm ghost" data-adj="' + esc(a.id) + '">分户</button>' +
        '<button class="btn sm ghost" data-aedit="' + esc(a.id) + '">编辑</button>' +
        '<button class="btn sm ghost" data-apts="' + esc(a.id) + '">加减分</button>' +
        '<button class="btn sm danger" data-adel="' + esc(a.id) + '">删除</button>' +
        '</div></td></tr>';
    });
    $('tAcc').innerHTML = h + '</tbody>';
    renderPager('accPager', S.accPage, S.accSize, S.accTotal, function (p) { S.accPage = p; loadAccounts(); });
  }

  function accForm(id) {
    var a = id ? S.accounts.filter(function (x) { return x.id === id; })[0] : null;
    a = a || { name: '', grp: '', phone: '', idcard: '', code: '', status: '正常', note: '' };
    modal(id ? '编辑账户' : '新增积分账户',
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">' +
      '<label class="fld"><span>姓名 *</span><input id="a_name" value="' + esc(a.name) + '"></label>' +
      '<label class="fld"><span>村民组</span><input id="a_grp" value="' + esc(a.grp) + '" placeholder="如 白岩塘组"></label>' +
      '</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">' +
      '<label class="fld"><span>手机号（查积分用）</span><input id="a_phone" value="' + esc(a.phone) + '" maxlength="11"></label>' +
      '<label class="fld"><span>6 位积分码</span><input id="a_code" value="' + esc(a.code || '') + '" maxlength="6" placeholder="留空自动生成"></label>' +
      '</div><label class="fld"><span>身份证号</span><input id="a_idcard" value="' + esc(a.idcard) + '" maxlength="18"></label>' +
      '<div class="hint" style="margin:-6px 0 10px;">积分码用于「没登记手机号、也没有身份证信息」的村民登录：村民端输入<b>姓名 + 积分码</b>即可。一个账户一个码，全村唯一。</div>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">' +
      '<label class="fld"><span>状态</span><select id="a_status"><option' + (a.status === '正常' ? ' selected' : '') + '>正常</option>' +
      '<option' + (a.status !== '正常' ? ' selected' : '') + '>停用</option></select></label>' +
      '<label class="fld"><span>备注</span><input id="a_note" value="' + esc(a.note) + '"></label></div>',
      '<button class="btn ghost" data-close>取消</button><button class="btn primary" id="a_save">保存</button>',
      function () {
        $('a_save').onclick = function () {
          var body = {
            id: id || '', name: $('a_name').value.trim(), grp: $('a_grp').value.trim(),
            phone: $('a_phone').value.trim(), idcard: $('a_idcard').value.trim(),
            code: $('a_code').value.trim(),
            status: $('a_status').value, note: $('a_note').value.trim()
          };
          if (!body.name) { toast('请填写姓名', true); return; }
          if (body.phone && !/^1\d{10}$/.test(body.phone)) { toast('手机号格式不对（11 位）', true); return; }
          if (body.code && !/^\d{6}$/.test(body.code)) { toast('积分码须为 6 位数字', true); return; }
          api('/api/jifen/admin/acct_save', body).then(function (d) {
            if (!d.success) { toast(d.error || '保存失败', true); return; }
            toast('已保存'); closeMask(); loadAccounts();
          });
        };
      });
  }

  function pointsForm(id) {
    var a = S.accounts.filter(function (x) { return x.id === id; })[0];
    if (!a) return;
    modal('调整积分 · ' + a.name,
      '<div style="font-size:13px;color:#6b7280;margin-bottom:12px">当前余额 <b style="color:#c2410c;font-size:16px">' +
      n(a.points) + '</b> 分</div>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">' +
      '<label class="fld"><span>变动分值（正加负减）</span><input id="p_pts" type="number" value="10" step="1"></label>' +
      '<label class="fld"><span>快捷</span><div class="chips"><button class="chip" data-pv="5">+5</button>' +
      '<button class="chip" data-pv="10">+10</button><button class="chip" data-pv="20">+20</button>' +
      '<button class="chip" data-pv="-10">-10</button></div></label></div>' +
      '<label class="fld"><span>事由</span><input id="p_reason" placeholder="如：参加11月环境整治"></label>',
      '<button class="btn ghost" data-close>取消</button><button class="btn primary" id="p_save">确认</button>',
      function () {
        $('mbBody').querySelectorAll('[data-pv]').forEach(function (b) {
          b.onclick = function () { $('p_pts').value = b.getAttribute('data-pv'); };
        });
        $('p_save').onclick = function () {
          var pts = Number($('p_pts').value) || 0;
          if (!pts) { toast('分值不能为 0', true); return; }
          api('/api/jifen/admin/points', {
            acc_ids: [id], points: pts, reason: $('p_reason').value.trim() || '积分调整'
          }).then(function (d) {
            if (!d.success) { toast(d.error || '操作失败', true); return; }
            toast('已' + (pts > 0 ? '发放' : '扣减') + ' ' + Math.abs(pts) + ' 分');
            closeMask(); loadAccounts();
          });
        };
      });
  }

  function importHukou() {
    if (!confirm('将从「户籍人口台账」中状态为「正常」的村民批量建立积分账户（已有同名同手机号的会自动跳过）。\n\n确定继续？')) return;
    var btn = $('btnImport');
    btn.disabled = true; btn.textContent = '导入中…';
    api('/api/jifen/admin/import_hukou', {}).then(function (d) {
      btn.disabled = false; btn.textContent = '从户籍导入';
      if (!d.success) { toast(d.error || '导入失败', true); return; }
      toast(d.message || '导入完成');
      S.accPage = 1; loadAccounts();
    }).catch(function () { btn.disabled = false; btn.textContent = '从户籍导入'; });
  }

  /* ---------------- 流水 ---------------- */
  function loadTxns() {
    var q = '/api/jifen/admin/txns?kw=' + encodeURIComponent(S.txnKw) +
      '&page=' + S.txnPage + '&size=' + S.txnSize;
    api(q).then(function (d) {
      if (!d.success) { toast(d.error || '加载失败', true); return; }
      S.txns = d.txns || []; S.txnTotal = d.total || 0;
      renderTxns();
    });
  }

  var KIND = { earn: '获得', spend: '兑换', adjust: '调整', refund: '退回' };

  function renderTxns() {
    var h = '<thead><tr><th>时间</th><th>姓名</th><th>组别</th><th class="c">类型</th>' +
      '<th class="r">变动</th><th class="r">余额</th><th>事由</th><th>单号</th><th>经办人</th></tr></thead><tbody>';
    if (!S.txns.length) h += '<tr><td colspan="9"><div class="empty">暂无流水</div></td></tr>';
    S.txns.forEach(function (t) {
      var pos = t.points > 0;
      h += '<tr><td class="mut" style="white-space:nowrap">' + esc(t.created) + '</td>' +
        '<td class="nm">' + esc(t.name) + '</td>' +
        '<td class="mut">' + esc((t.grp || '—').replace('组', '')) + '</td>' +
        '<td class="c"><span class="tag ' + (t.kind === 'spend' ? 'cancel' : 'on') + '">' + esc(KIND[t.kind] || t.kind) + '</span></td>' +
        '<td class="r"><b style="color:' + (pos ? '#15803d' : '#b91c1c') + '">' + (pos ? '+' : '') + n(t.points) + '</b></td>' +
        '<td class="r mut">' + n(t.balance) + '</td>' +
        '<td>' + esc(t.reason) + '</td>' +
        '<td class="mut">' + esc(t.ref || '—') + '</td>' +
        '<td class="mut">' + esc(t.operator || '—') + '</td></tr>';
    });
    $('tTxn').innerHTML = h + '</tbody>';
    renderPager('txnPager', S.txnPage, S.txnSize, S.txnTotal, function (p) { S.txnPage = p; loadTxns(); });
  }

  /* ---------------- 规则 ---------------- */
  function loadRules() {
    api('/api/jifen/admin/rules').then(function (d) {
      if (!d.success) { toast(d.error || '加载失败', true); return; }
      S.rules = d.rules || [];
      renderRules();
    });
  }

  function renderRules() {
    var h = '<thead><tr><th>规则名称</th><th>分类</th><th class="r">分值</th><th class="c">单位</th>' +
      '<th>说明</th><th class="c">启用</th><th class="c">操作</th></tr></thead><tbody>';
    if (!S.rules.length) h += '<tr><td colspan="7"><div class="empty">暂无规则</div></td></tr>';
    S.rules.forEach(function (r) {
      h += '<tr><td class="nm">' + esc(r.name) + '</td>' +
        '<td class="mut">' + esc(r.cat) + '</td>' +
        '<td class="r"><b style="color:#c2410c">+' + r.points + '</b></td>' +
        '<td class="c mut">' + esc(r.unit) + '</td>' +
        '<td class="mut">' + esc(r.desc || '—') + '</td>' +
        '<td class="c"><span class="tag ' + (r.enabled ? 'on' : 'off') + '">' + (r.enabled ? '启用' : '停用') + '</span></td>' +
        '<td class="c"><div class="acts" style="justify-content:center">' +
        '<button class="btn sm ghost" data-redit="' + esc(r.id) + '">编辑</button>' +
        '<button class="btn sm danger" data-rdel="' + esc(r.id) + '">删除</button></div></td></tr>';
    });
    $('tRule').innerHTML = h + '</tbody>';
  }

  function ruleForm(id) {
    var r = id ? S.rules.filter(function (x) { return x.id === id; })[0] : null;
    r = r || { name: '', cat: '志愿服务', points: 10, unit: '次', desc: '', enabled: 1, sort: 0 };
    var cats = ['议事参与', '志愿服务', '文明新风', '人居环境', '政策落实', '教育成才', '国防义务', '其他'];
    modal(id ? '编辑规则' : '新增规则',
      '<label class="fld"><span>规则名称 *</span><input id="r_name" value="' + esc(r.name) + '"></label>' +
      '<div style="display:grid;grid-template-columns:1.2fr .8fr .8fr;gap:10px">' +
      '<label class="fld"><span>分类</span><select id="r_cat">' + cats.map(function (c) {
        return '<option' + (c === r.cat ? ' selected' : '') + '>' + c + '</option>';
      }).join('') + '</select></label>' +
      '<label class="fld"><span>分值</span><input id="r_pts" type="number" value="' + r.points + '"></label>' +
      '<label class="fld"><span>单位</span><input id="r_unit" value="' + esc(r.unit) + '" placeholder="次/人/季"></label></div>' +
      '<label class="fld"><span>说明</span><input id="r_desc" value="' + esc(r.desc) + '"></label>' +
      '<label class="fld"><span>启用</span><select id="r_en"><option value="1"' + (r.enabled ? ' selected' : '') + '>启用</option>' +
      '<option value="0"' + (!r.enabled ? ' selected' : '') + '>停用</option></select></label>',
      '<button class="btn ghost" data-close>取消</button><button class="btn primary" id="r_save">保存</button>',
      function () {
        $('r_save').onclick = function () {
          var body = {
            id: id || '', name: $('r_name').value.trim(), cat: $('r_cat').value,
            points: Number($('r_pts').value) || 1, unit: $('r_unit').value.trim() || '次',
            desc: $('r_desc').value.trim(), enabled: $('r_en').value === '1'
          };
          if (!body.name) { toast('请填写规则名称', true); return; }
          api('/api/jifen/admin/rule_save', body).then(function (d) {
            if (!d.success) { toast(d.error || '保存失败', true); return; }
            toast('已保存'); closeMask(); loadRules();
          });
        };
      });
  }

  /* ---------------- 设置 ---------------- */
  /* ---------------- 红黑榜 ---------------- */
  function loadCases() {
    api('/api/jifen/admin/cases').then(function (d) {
      if (!d.success) { toast(d.error || '加载失败', true); return; }
      S.cases = d.cases || [];
      renderCases();
    });
  }

  function renderCases() {
    var list = S.cases || [];
    var red = list.filter(function (c) { return c.kind !== 'black'; }).length;
    var black = list.length - red;
    $('caseStat').innerHTML = '共 <b>' + n(list.length) + '</b> 条 · 红榜 <b style="color:#b91c1c">' + n(red) +
      '</b> 条 · 黑榜 <b style="color:#374151">' + n(black) + '</b> 条 · 村民端只显示「发布」状态的案例';
    var h = '<thead><tr><th style="width:74px;">图片</th><th style="width:74px;" class="c">类型</th>' +
      '<th>标题 / 说明</th><th>对象</th><th class="r">分值</th><th class="c">日期</th>' +
      '<th class="c">状态</th><th class="c">排序</th><th class="c">操作</th></tr></thead><tbody>';
    if (!list.length) {
      h += '<tr><td colspan="9"><div class="empty">暂无案例<br>点右上角「+ 新增案例」发布第一条红榜或黑榜</div></td></tr>';
    }
    list.forEach(function (c) {
      var isRed = c.kind !== 'black';
      h += '<tr>' +
        '<td>' + (c.img
          ? '<img src="' + esc(c.img) + '" style="width:62px;height:44px;object-fit:cover;border-radius:7px;border:1px solid #eee;cursor:zoom-in" data-cimg="' + esc(c.img) + '">'
          : '<span class="mut" style="font-size:12px">无图</span>') + '</td>' +
        '<td class="c"><span class="tag ' + (isRed ? 'on' : 'off') + '">' + (isRed ? '红榜' : '黑榜') + '</span></td>' +
        '<td><div style="font-weight:700">' + esc(c.title) + '</div>' +
        (c.desc ? '<div class="mut" style="font-size:12px;margin-top:2px">' +
          esc(c.desc.length > 40 ? c.desc.slice(0, 40) + '…' : c.desc) + '</div>' : '') + '</td>' +
        '<td class="mut">' + esc((c.who_full || c.who || '—') + (c.grp ? ' · ' + c.grp : '')) + '</td>' +
        '<td class="r"><b style="color:' + (isRed ? '#c2410c' : '#4b5563') + '">' +
        (c.points > 0 ? '+' : '') + n(c.points) + '</b></td>' +
        '<td class="c mut">' + esc(c.happen || '—') + '</td>' +
        '<td class="c"><span class="tag ' + (c.status === '发布' ? 'on' : 'off') + '">' + esc(c.status) + '</span></td>' +
        '<td class="c mut">' + n(c.sort) + '</td>' +
        '<td class="c"><div class="acts" style="justify-content:center">' +
        '<button class="btn sm ghost" data-casedit="' + esc(c.id) + '">编辑</button>' +
        '<button class="btn sm ghost" data-casetoggle="' + esc(c.id) + '">' + (c.status === '发布' ? '下架' : '发布') + '</button>' +
        '<button class="btn sm danger" data-casedel="' + esc(c.id) + '">删除</button>' +
        '</div></td></tr>';
    });
    $('tCase').innerHTML = h + '</tbody>';
  }

  /* 浏览器端压缩：最长边 1280、JPEG 0.82，避免大图拖慢手机端 */
  function compressImage(file, cb) {
    var url = URL.createObjectURL(file);
    var img = new Image();
    img.onload = function () {
      var max = 1280, w = img.naturalWidth, h = img.naturalHeight;
      if (Math.max(w, h) > max) {
        var r = max / Math.max(w, h);
        w = Math.round(w * r); h = Math.round(h * r);
      }
      var cv = document.createElement('canvas');
      cv.width = w; cv.height = h;
      cv.getContext('2d').drawImage(img, 0, 0, w, h);
      URL.revokeObjectURL(url);
      try { cb(cv.toDataURL('image/jpeg', 0.82)); } catch (e) { cb(null); }
    };
    img.onerror = function () { URL.revokeObjectURL(url); cb(null); };
    img.src = url;
  }

  function caseForm(id) {
    var c = id ? (S.cases || []).filter(function (x) { return x.id === id; })[0] : null;
    c = c || { kind: 'red', title: '', who: '', grp: '', points: 0, desc: '', img: '',
               happen: new Date().toISOString().slice(0, 10), status: '发布', sort: 0 };
    var isRed = c.kind !== 'black';
    var cur = { img: c.img || '' };
    modal((id ? '编辑案例' : '新增红黑榜案例'),
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">' +
      '<label class="fld"><span>榜单类型 *</span><select id="c_kind">' +
      '<option value="red"' + (isRed ? ' selected' : '') + '>红榜 · 加分表扬</option>' +
      '<option value="black"' + (isRed ? '' : ' selected') + '>黑榜 · 减分警示</option></select></label>' +
      '<label class="fld"><span>公示日期</span><input id="c_happen" type="date" value="' + esc(c.happen || '') + '"></label>' +
      '</div>' +
      '<label class="fld"><span>案例标题 *（如 主动清理河道垃圾）</span><input id="c_title" maxlength="30" value="' + esc(c.title) + '"></label>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px">' +
      '<label class="fld"><span>姓名 / 户主</span><input id="c_who" value="' + esc(c.who_full || c.who || '') + '"></label>' +
      '<label class="fld"><span>村民组</span><input id="c_grp" value="' + esc(c.grp || '') + '" placeholder="如 白岩塘组"></label>' +
      '<label class="fld"><span>分值（填正数，黑榜自动记减分）</span><input id="c_points" type="number" min="0" value="' +
      Math.abs(c.points || 0) + '"></label></div>' +
      '<label class="fld"><span>说明 / 事由（村民端展示）</span><textarea id="c_desc" maxlength="300">' + esc(c.desc) + '</textarea></label>' +
      '<label class="fld"><span>现场图片（选填，自动压缩到 1280 宽）</span>' +
      '<input type="file" id="c_file" accept="image/*" style="padding:6px;background:#fff">' +
      '<div id="c_thumb" style="margin-top:8px">' +
      (cur.img ? '<img src="' + esc(cur.img) + '" style="max-width:200px;border-radius:8px;border:1px solid #eee">' +
        ' <button class="btn sm danger" id="c_rmimg" type="button">移除图片</button>' : '') +
      '</div></label>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">' +
      '<label class="fld"><span>状态</span><select id="c_status">' +
      '<option' + (c.status === '发布' ? ' selected' : '') + '>发布</option>' +
      '<option' + (c.status !== '发布' ? ' selected' : '') + '>下架</option></select></label>' +
      '<label class="fld"><span>排序（大的在前）</span><input id="c_sort" type="number" value="' + (c.sort || 0) + '"></label>' +
      '</div>',
      '<button class="btn ghost" data-close>取消</button><button class="btn primary" id="c_save">保存</button>',
      function () {
        $('c_file').onchange = function () {
          var f = this.files && this.files[0];
          if (!f) return;
          if (f.size > 8 * 1024 * 1024) { toast('原图请小于 8MB', true); this.value = ''; return; }
          toast('正在处理图片…');
          compressImage(f, function (dataUrl) {
            if (!dataUrl) { toast('图片读取失败', true); return; }
            $('c_thumb').innerHTML = '<span class="mut" style="font-size:12px">上传中…</span>';
            api('/api/jifen/admin/upload', { data: dataUrl }).then(function (d) {
              if (!d.success) { toast(d.error || '上传失败', true); $('c_thumb').innerHTML = ''; return; }
              cur.img = d.url;
              $('c_thumb').innerHTML = '<img src="' + esc(d.url) + '" style="max-width:200px;border-radius:8px;border:1px solid #eee"> ' +
                '<button class="btn sm danger" id="c_rmimg" type="button">移除图片</button>';
              $('c_rmimg').onclick = function () { cur.img = ''; $('c_thumb').innerHTML = ''; };
              toast('图片已上传');
            });
          });
        };
        if ($('c_rmimg')) $('c_rmimg').onclick = function () { cur.img = ''; $('c_thumb').innerHTML = ''; };
        $('c_save').onclick = function () {
          var body = {
            id: id || '', kind: $('c_kind').value, title: $('c_title').value.trim(),
            who: $('c_who').value.trim(), grp: $('c_grp').value.trim(),
            points: $('c_points').value, desc: $('c_desc').value.trim(),
            img: cur.img, happen: $('c_happen').value,
            status: $('c_status').value, sort: $('c_sort').value
          };
          if (!body.title) { toast('请填写案例标题', true); return; }
          api('/api/jifen/admin/case_save', body).then(function (d) {
            if (!d.success) { toast(d.error || '保存失败', true); return; }
            closeMask(); toast('已保存'); loadCases();
          });
        };
      }, true);
  }

  var SET_FIELDS = [
    ['market_name', '超市名称'], ['slogan', '宣传标语'],
    ['address', '领取地址'], ['open_time', '领取时间'],
    ['contact', '联系方式'], ['notice', '兑换须知（多行）'],
    ['case_intro', '红黑榜导语（多行）'], ['case_black_mask', '黑榜姓名是否脱敏']
  ];

  function loadSettings() {
    api('/api/jifen/config').then(function (d) {
      if (!d.success) return;
      S.cfg = d.settings || {};
      var h = SET_FIELDS.map(function (f) {
        var v = S.cfg[f[0]] || '';
        if (f[0] === 'notice' || f[0] === 'case_intro')
          return '<label class="fld"><span>' + f[1] + '</span><textarea id="s_' + f[0] + '">' + esc(v) + '</textarea></label>';
        if (f[0] === 'case_black_mask') {
          var on = String(v || '1') === '1';
          return '<label class="fld"><span>' + f[1] + '</span><select id="s_' + f[0] + '">' +
            '<option value="1"' + (on ? ' selected' : '') + '>脱敏（张*）</option>' +
            '<option value="0"' + (on ? '' : ' selected') + '>全名公示</option></select></label>';
        }
        return '<label class="fld"><span>' + f[1] + '</span><input id="s_' + f[0] + '" value="' + esc(v) + '"></label>';
      }).join('');
      h += '<button class="btn primary" id="s_save">保存设置</button>' +
        '<div class="fld-tip" style="text-align:left">这些内容会显示在村民端页面顶部和底部。</div>';
      $('setForm').innerHTML = h;
      $('s_save').onclick = function () {
        var body = {};
        SET_FIELDS.forEach(function (f) { body[f[0]] = $('s_' + f[0]).value.trim(); });
        api('/api/jifen/admin/settings', body).then(function (d) {
          if (!d.success) { toast(d.error || '保存失败', true); return; }
          S.cfg = body;
          applySite();
          if (S.dash) renderDash(S.dash);
          toast('已保存');
        });
      };
    });
  }

  /* ---------------- 事件委托 ---------------- */
  document.addEventListener('click', function (e) {
    var t = e.target;
    // 按钮统一用 data-xxx 属性承载参数，这里按「加 data- 前缀」取值（兼容老的无前缀写法）
    var g = function (k) {
      if (!t.getAttribute) return null;
      var v = t.getAttribute('data-' + k);
      return v === null ? t.getAttribute(k) : v;
    };

    if (g('rpt')) return downloadReport(g('rpt'));
    if (g('bkdl')) { location.href = '/api/jifen/admin/backup?name=' + encodeURIComponent(g('bkdl')); return; }
    if (g('bkrs')) {
      var bk = S.backups.filter(function (x) { return x.name === g('bkrs'); })[0] || {};
      return restoreDialog('从服务器备份恢复', {
        from: g('bkrs'), name: g('bkrs'), counts: bk.counts || {}, ts: bk.ts || bk.mtime || ''
      });
    }
    if (g('bkdel')) {
      var dn = g('bkdel');
      modal('删除备份', '<div class="bk-warn">确定删除备份 <b>' + esc(dn) + '</b>？删除后不可恢复。</div>',
        '<button class="btn ghost" data-close>取消</button><button class="btn danger" id="bkDelGo">删除</button>',
        function (bd, ft) {
          ft.querySelector('#bkDelGo').onclick = function () {
            api('/api/jifen/admin/backup_del', { name: dn }).then(function (d) {
              closeMask();
              if (d.success) { toast('已删除'); loadBackups(); }
              else toast(d.error || '删除失败', true);
            });
          };
        });
      return;
    }
    if (g('hview')) return houseForm(g('hview'));
    if (g('hexport')) { location.href = '/api/jifen/admin/export?type=houses'; return; }
    if (g('casedit')) return caseForm(g('casedit'));
    if (g('cimg')) { window.open(g('cimg'), '_blank'); return; }
    if (g('casetoggle')) {
      api('/api/jifen/admin/case_toggle', { id: g('casetoggle') }).then(function (d) {
        if (d.success) { toast('已切换为「' + d.status + '」'); loadCases(); }
        else toast(d.error || '操作失败', true);
      });
      return;
    }
    if (g('casedel')) {
      if (!confirm('删除该案例？村民端将立即不再显示，图片文件一并清理。')) return;
      api('/api/jifen/admin/case_del', { id: g('casedel') }).then(function (d) {
        if (d.success) { toast('已删除'); loadCases(); } else toast(d.error || '删除失败', true);
      });
      return;
    }
    if (g('gedit')) return goodsForm(g('gedit'));
    if (g('grp')) {
      // 点击组名：搜索该组全部人员并自动全选
      var grp = g('grp');
      $('grSearch').value = grp;
      loadGrantPeople(grp).then(function () {
        S.grantList.forEach(function (a) { S.picked[a.id] = true; });
        $('grAll').checked = true;
        renderGrantPeople(S.grantTotal);
        toast('已选中 ' + grp + ' 全部 ' + S.grantList.length + ' 人（共 ' + S.grantTotal + ' 人）');
      });
      return;
    }
    if (g('grp-clear')) {
      S.picked = {}; $('grAll').checked = false;
      $('grSearch').value = '';
      loadGrantPeople('');
      return;
    }
    if (g('gtoggle')) {
      var gd = S.goods.filter(function (x) { return x.id === g('gtoggle'); })[0];
      api('/api/jifen/admin/goods_save', {
        id: gd.id, name: gd.name, cat: gd.cat, icon: gd.icon, spec: gd.spec, points: gd.points,
        stock: gd.stock, limit_per: gd.limit_per, desc: gd.desc, sort: gd.sort,
        status: gd.status === '上架' ? '下架' : '上架'
      }).then(function (d) { if (d.success) { toast('已切换'); loadGoods(); } });
      return;
    }
    if (g('gdel')) {
      if (!confirm('删除该商品？已产生的兑换记录不受影响。')) return;
      api('/api/jifen/admin/goods_del', { id: g('gdel') }).then(function (d) {
        if (d.success) { toast('已删除'); loadGoods(); } else toast(d.error || '删除失败', true);
      });
      return;
    }
    if (g('adj')) {
      var ax = S.accounts.filter(function (x) { return x.id === g('adj'); })[0] || {};
      huAssign([{ id: g('adj'), name: ax.name || '', grp: ax.grp || '' }]);
      return;
    }
    if (g('aedit')) return accForm(g('aedit'));
    if (g('apts')) return pointsForm(g('apts'));
    if (g('adel')) {
      if (!confirm('删除该账户？其积分流水会一并删除（有兑换记录的账户不允许删除）。')) return;
      api('/api/jifen/admin/acct_del', { id: g('adel') }).then(function (d) {
        if (d.success) { toast('已删除'); loadAccounts(); } else toast(d.error || '删除失败', true);
      });
      return;
    }
    if (g('redit')) return ruleForm(g('redit'));
    if (g('rdel')) {
      if (!confirm('删除该规则？')) return;
      api('/api/jifen/admin/rule_del', { id: g('rdel') }).then(function (d) {
        if (d.success) { toast('已删除'); loadRules(); } else toast(d.error || '删除失败', true);
      });
      return;
    }
    if (g('odone')) {
      api('/api/jifen/admin/order_done', { id: g('odone') }).then(function (d) {
        if (!d.success) { toast(d.error || '操作失败', true); return; }
        toast('已核销'); $('vResult').innerHTML = ''; $('vCode').value = '';
        loadOrderList(); loadOverview();
      });
      return;
    }
    if (g('ocancel')) {
      if (!confirm('取消该兑换单？积分和库存会退回。')) return;
      api('/api/jifen/admin/order_cancel', { id: g('ocancel') }).then(function (d) {
        if (!d.success) { toast(d.error || '操作失败', true); return; }
        toast('已取消并退回积分'); $('vResult').innerHTML = '';
        loadOrderList();
      });
      return;
    }
    if (g('oview')) {
      var o = S.orders.filter(function (x) { return x.id === g('oview'); })[0];
      if (o) modal('兑换单 ' + o.code,
        '<div class="vc-items">' + o.items.map(function (i) {
          return esc(i.icon) + ' ' + esc(i.name) + ' × ' + i.qty;
        }).join('<br>') + '</div><div class="vc-meta">兑换人：' + esc(o.name) + '<br>扣减 ' + n(o.points) + ' 分<br>' +
        '下单 ' + esc(o.created) + '<br>状态 ' + esc(o.status) + (o.done_at ? ' · ' + esc(o.done_at) : '') +
        '<br>经办 ' + esc(o.operator || '—') + '</div>');
      return;
    }
  });

  document.addEventListener('change', function (e) {
    var t = e.target;
    if (t.hasAttribute && t.hasAttribute('data-pick')) {
      var id = t.getAttribute('data-pick');
      S.picked[id] = t.checked;
      syncGrantCount();
      return;
    }
    if (t.id === 'grAll') {
      S.grantList.forEach(function (a) { S.picked[a.id] = t.checked; });
      $('grPeople').querySelectorAll('[data-pick]').forEach(function (c) { c.checked = t.checked; });
      syncGrantCount();
    }
  });

  /* ================= 数据大屏 ================= */
  var DC = ['#f59e0b', '#38bdf8', '#34d399', '#a78bfa', '#fb7185', '#22d3ee', '#fbbf24'];
  var AXIS = 'rgba(255,255,255,.12)';
  var GRID_LINE = 'rgba(255,255,255,.06)';
  var TXT = '#8ea0bb';
  var TIP = {
    backgroundColor: 'rgba(15,23,42,.94)', borderColor: 'rgba(255,255,255,.14)',
    textStyle: { color: '#e2e8f0', fontSize: 12 }
  };

  function ec(id) {
    if (!window.echarts) return null;
    var el = $(id); if (!el) return null;
    var c = S.charts[id];
    if (!c || c.isDisposed()) { c = window.echarts.init(el); S.charts[id] = c; }
    return c;
  }
  function ecClear(id) {
    var c = S.charts[id];
    if (c && !c.isDisposed()) c.dispose();
    S.charts[id] = null;
    var el = $(id); if (el) el.innerHTML = '';
  }
  function noData(id, msg) {
    ecClear(id);
    var el = $(id); if (el) el.innerHTML = '<div class="dempty">' + esc(msg) + '</div>';
  }
  function grad(c1) {
    if (!window.echarts) return c1;
    return new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
      { offset: 0, color: c1 }, { offset: 1, color: 'rgba(0,0,0,0)' }
    ]);
  }
  function p2(x) { return (x < 10 ? '0' : '') + x; }
  function ymd(d) { return d.getFullYear() + '-' + p2(d.getMonth() + 1) + '-' + p2(d.getDate()); }

  function dkpi(label, val, unit, sub, color) {
    return '<div class="dkpi" style="--c:' + (color || DC[0]) + '">' +
      '<div class="l">' + esc(label) + '</div>' +
      '<div class="v">' + val + (unit ? '<small>' + esc(unit) + '</small>' : '') + '</div>' +
      (sub ? '<div class="s">' + sub + '</div>' : '') + '</div>';
  }

  function loadDash() {
    if (!window.echarts) { toast('图表库未加载，请检查 _shared/js/echarts.min.js', true); return; }
    var days = S.dashDays || 30;
    var now = new Date();
    var to = ymd(now);
    var from = ymd(new Date(now.getTime() - (days - 1) * 86400000));
    $('dashSub').textContent = '数据加载中…';
    api('/api/jifen/admin/stat?from=' + from + '&to=' + to).then(function (d) {
      if (!d.success) { toast(d.error || '统计加载失败', true); return; }
      S.dash = d;
      renderDash(d);
    });
  }

  function renderDash(d) {
    var k = d.kpi || {};
    $('dashSub').innerHTML = '统计区间 <b style="color:#e2e8f0">' + esc(d.range.from) + ' ~ ' +
      esc(d.range.to) + '</b> · 共 ' + d.range.days + ' 天';
    var t = new Date();
    $('dashClock').innerHTML = t.getFullYear() + '-' + p2(t.getMonth() + 1) + '-' + p2(t.getDate()) +
      ' ' + p2(t.getHours()) + ':' + p2(t.getMinutes()) + ':' + p2(t.getSeconds()) +
      '<br>数据更新 <b>实时</b>';

    $('dashKpi').innerHTML =
      dkpi('积分账户', n(k.acc_n), '个', '覆盖 ' + n(k.house_n) + ' 户' +
        (k.unhoused ? ' · 未归户 ' + n(k.unhoused) : ''), DC[0]) +
      dkpi('积分参与率', k.cover + '%', '', n(k.act_n) + ' 人已有积分记录', DC[1]) +
      dkpi('累计发放', n(k.earned_all), '分', '当前余额 ' + n(k.points) + ' 分', DC[2]) +
      dkpi('户均积分', n(k.house_avg), '分', '按 ' + n(k.house_n) + ' 户计', DC[3]) +
      dkpi('区间新增', '+' + n(k.earn), '分', n(k.txn_n) + ' 笔流水', DC[6]) +
      dkpi('区间兑换', '-' + n(k.spend), '分', n(k.order_n) + ' 笔兑换单', DC[4]) +
      dkpi('待领取', n(k.order_pend), '笔', '核销率 ' + k.rate + '%', DC[5]) +
      dkpi('今日新增', '+' + n(k.today_earn), '分', '今日兑换 ' + n(k.today_orders) + ' 笔', '#f97316');

    chartTrend(d);
    chartGrp(d);
    chartCat(d);
    chartStatus(d);
    chartGoods(d);
    renderReason();
    renderRank();

    $('dashFoot').textContent = '数据来源：积分超市业务库 · 生成时间 ' + d.range.from + ' 至 ' +
      d.range.to + ' · ' + new Date().toLocaleString('zh-CN', { hour12: false });
  }

  function chartTrend(d) {
    var daily = d.daily || [];
    var tot = 0;
    daily.forEach(function (x) { tot += x.earn + x.spend + x.orders; });
    if (!tot) return noData('chTrend', '区间内暂无积分流水，发放或兑换积分后这里会出现趋势曲线');
    var c = ec('chTrend'); if (!c) return;
    var days = daily.map(function (x) { return x.d; });
    c.setOption({
      grid: { left: 44, right: 44, top: 30, bottom: 24 },
      tooltip: Object.assign({ trigger: 'axis' }, TIP),
      legend: { data: ['新增积分', '兑换扣减', '兑换单数'], top: 0, right: 0,
        itemWidth: 12, itemHeight: 8, textStyle: { color: TXT, fontSize: 11 } },
      xAxis: { type: 'category', data: days, boundaryGap: false,
        axisLine: { lineStyle: { color: AXIS } }, axisTick: { show: false },
        axisLabel: { color: TXT, fontSize: 10, formatter: function (v) { return v.slice(5); } } },
      yAxis: [
        { type: 'value', splitLine: { lineStyle: { color: GRID_LINE } },
          axisLabel: { color: TXT, fontSize: 10 } },
        { type: 'value', splitLine: { show: false }, axisLabel: { color: TXT, fontSize: 10 } }
      ],
      series: [
        { name: '新增积分', type: 'line', smooth: true, symbol: 'circle', symbolSize: 5,
          data: daily.map(function (x) { return x.earn; }), itemStyle: { color: '#fbbf24' },
          lineStyle: { width: 2.4, color: '#fbbf24' }, areaStyle: { color: grad('rgba(251,191,36,.30)') } },
        { name: '兑换扣减', type: 'line', smooth: true, symbol: 'circle', symbolSize: 5,
          data: daily.map(function (x) { return x.spend; }), itemStyle: { color: '#38bdf8' },
          lineStyle: { width: 2.4, color: '#38bdf8' }, areaStyle: { color: grad('rgba(56,189,248,.22)') } },
        { name: '兑换单数', type: 'bar', yAxisIndex: 1, barWidth: '34%',
          data: daily.map(function (x) { return x.orders; }),
          itemStyle: { color: 'rgba(52,211,153,.36)', borderRadius: [3, 3, 0, 0] } }
      ]
    }, true);
  }

  function chartGrp(d) {
    var g = (d.grp || []).filter(function (x) { return x.points > 0 || x.act > 0; }).slice(0, 10);
    if (!g.length) return noData('chGrp', '暂无积分数据');
    var c = ec('chGrp'); if (!c) return;
    var names = g.map(function (x) { return x.name.replace('组', ''); }).reverse();
    var vals = g.map(function (x) { return x.points; }).reverse();
    c.setOption({
      grid: { left: 62, right: 48, top: 8, bottom: 6 },
      tooltip: Object.assign({ trigger: 'axis', axisPointer: { type: 'shadow' } }, TIP),
      xAxis: { type: 'value', splitLine: { lineStyle: { color: GRID_LINE } },
        axisLabel: { color: TXT, fontSize: 10 } },
      yAxis: { type: 'category', data: names, axisLine: { lineStyle: { color: AXIS } },
        axisTick: { show: false }, axisLabel: { color: '#9aa9c2', fontSize: 11 } },
      series: [{
        type: 'bar', data: vals, barWidth: 11,
        itemStyle: {
          borderRadius: [0, 6, 6, 0],
          color: new window.echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: 'rgba(245,158,11,.45)' }, { offset: 1, color: '#fbbf24' }])
        },
        label: { show: true, position: 'right', color: '#fbbf24', fontSize: 10,
          formatter: function (o) { return o.value ? o.value : ''; } }
      }]
    }, true);
  }

  function chartCat(d) {
    var cats = d.cats || [];
    if (!cats.length) return noData('chCat', '暂无兑换记录');
    var c = ec('chCat'); if (!c) return;
    c.setOption({
      color: DC,
      tooltip: Object.assign({ trigger: 'item', formatter: '{b}<br/>{c} 件（{d}%）' }, TIP),
      legend: { bottom: 0, itemWidth: 9, itemHeight: 9, textStyle: { color: TXT, fontSize: 10 } },
      series: [{
        type: 'pie', radius: ['46%', '70%'], center: ['50%', '46%'],
        data: cats.map(function (x) { return { name: x.name, value: x.qty }; }),
        itemStyle: { borderColor: '#0e1726', borderWidth: 2 },
        label: { show: false }, labelLine: { show: false }
      }]
    }, true);
  }

  function chartStatus(d) {
    var s = d.status || {};
    var total = (s['待领取'] || 0) + (s['已领取'] || 0) + (s['已取消'] || 0);
    if (!total) return noData('chStatus', '区间内暂无兑换单');
    var c = ec('chStatus'); if (!c) return;
    c.setOption({
      color: ['#fbbf24', '#34d399', '#94a3b8'],
      tooltip: Object.assign({ trigger: 'item', formatter: '{b}：{c} 笔（{d}%）' }, TIP),
      legend: { bottom: 0, itemWidth: 9, itemHeight: 9, textStyle: { color: TXT, fontSize: 10 } },
      series: [{
        type: 'pie', radius: ['48%', '72%'], center: ['50%', '45%'],
        data: [
          { name: '待领取', value: s['待领取'] || 0 },
          { name: '已领取', value: s['已领取'] || 0 },
          { name: '已取消', value: s['已取消'] || 0 }
        ],
        itemStyle: { borderColor: '#0e1726', borderWidth: 2 },
        label: { show: true, position: 'center', color: '#fff', fontSize: 18, fontWeight: 700,
          formatter: function () { return total; } },
        emphasis: { label: { show: true } }
      }]
    }, true);
  }

  function chartGoods(d) {
    var g = (d.goods || []).slice(0, 8);
    if (!g.length) return noData('chGoods', '暂无商品兑换记录');
    var c = ec('chGoods'); if (!c) return;
    var names = g.map(function (x) { return x.name.length > 10 ? x.name.slice(0, 10) + '…' : x.name; }).reverse();
    var vals = g.map(function (x) { return x.qty; }).reverse();
    c.setOption({
      grid: { left: 96, right: 40, top: 8, bottom: 6 },
      tooltip: Object.assign({ trigger: 'axis', axisPointer: { type: 'shadow' } }, TIP),
      xAxis: { type: 'value', splitLine: { lineStyle: { color: GRID_LINE } },
        axisLabel: { color: TXT, fontSize: 10 } },
      yAxis: { type: 'category', data: names, axisLine: { lineStyle: { color: AXIS } },
        axisTick: { show: false }, axisLabel: { color: '#9aa9c2', fontSize: 11 } },
      series: [{
        type: 'bar', data: vals, barWidth: 12,
        itemStyle: {
          borderRadius: [0, 6, 6, 0],
          color: new window.echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: 'rgba(56,189,248,.40)' }, { offset: 1, color: '#38bdf8' }])
        },
        label: { show: true, position: 'right', color: '#7dd3fc', fontSize: 10,
          formatter: function (o) { return o.value ? o.value + ' 件' : ''; } }
      }]
    }, true);
  }

  function renderReason() {
    var d = S.dash;
    var list = (d && d.reasons) || [];
    if (!list.length) {
      $('dashReason').innerHTML = '<div class="dempty">区间内暂无加分记录</div>';
      return;
    }
    $('dashReason').innerHTML = list.slice(0, 9).map(function (x, i) {
      return '<div class="dr ' + (i < 3 ? 't' + (i + 1) : '') + '">' +
        '<span class="no">' + (i + 1) + '</span>' +
        '<span class="nm">' + esc(x.name) + '<em>' + n(x.n) + ' 次</em></span>' +
        '<span class="pt">' + n(x.points) + '</span></div>';
    }).join('');
  }

  function renderRank() {
    var d = S.dash;
    if (!d) return;
    var house = S.rankView === 'house';
    var list = house ? (d.top_house || []) : (d.top_person || []);
    if (!list.length) {
      $('dashRank').innerHTML = '<div class="dempty" style="grid-column:span 2">还没有积分记录，发第一笔积分后这里就会出现排行</div>';
      return;
    }
    $('dashRank').innerHTML = list.map(function (x, i) {
      var nm = house ? (x.zhu || '（未登记户主）') : x.name;
      var sub = house ? (x.members + ' 人 · ' + (x.grp || '')) : (x.grp || '');
      return '<div class="dr ' + (i < 3 ? 't' + (i + 1) : '') + '">' +
        '<span class="no">' + (i + 1) + '</span>' +
        '<span class="nm">' + esc(nm) + (sub ? '<em>' + esc(sub) + '</em>' : '') + '</span>' +
        '<span class="pt">' + n(x.points) + '<small style="color:#7f8ea6;font-weight:600;"> 分</small></span></div>';
    }).join('');
  }

  function resizeCharts() {
    Object.keys(S.charts).forEach(function (k) {
      var c = S.charts[k];
      if (c && !c.isDisposed()) c.resize();
    });
  }
  var rzTimer = null;
  window.addEventListener('resize', function () {
    clearTimeout(rzTimer);
    rzTimer = setTimeout(resizeCharts, 180);
  });

  function toggleDashFull() {
    var el = $('dash');
    var on = el.classList.toggle('fs');
    $('btnDashFull').textContent = on ? '✕ 退出全屏' : '⛶ 全屏';
    document.documentElement.style.overflow = on ? 'hidden' : '';
    setTimeout(resizeCharts, 80);
  }
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && $('dash').classList.contains('fs')) toggleDashFull();
  });

  /* ================= 数据管理 ================= */
  var REPORTS = [
    ['summary', '📊', '综合汇总', '账户、发放、兑换、核销率等关键指标一页看清'],
    ['daily', '📅', '按日汇总', '每日新增积分、兑换扣减与单量'],
    ['groups', '🏘️', '按组汇总', '各村民组的账户、户数、积分与参与情况'],
    ['goods', '🎁', '商品兑换汇总', '每件商品的兑换数量、消耗积分与单数'],
    ['txns', '📜', '积分流水明细', '每一笔加分 / 扣分 / 退回记录'],
    ['orders', '🎫', '兑换单明细', '取货码、物品、状态、领取时间与经办人'],
    ['accounts', '👥', '积分账户', '全部账户的余额、累计获得与兑换'],
    ['houses', '🏠', '按户汇总', '户积分、户内人数、组别与地址'],
    ['cases', '📣', '红黑榜案例', '已发布 / 下架的加减分案例清单']
  ];

  function initReportRange() {
    var now = new Date();
    if (!$('rptFrom').value) $('rptFrom').value = ymd(new Date(now.getFullYear(), now.getMonth(), 1));
    if (!$('rptTo').value) $('rptTo').value = ymd(now);
  }

  function renderReports() {
    $('rptGrid').innerHTML = REPORTS.map(function (r) {
      return '<div class="rpt"><div class="ic">' + r[1] + '</div><h4>' + esc(r[2]) + '</h4>' +
        '<p>' + esc(r[3]) + '</p>' +
        '<button class="btn sm ghost" data-rpt="' + r[0] + '">下载 CSV</button></div>';
    }).join('');
  }

  function rptQuery() {
    var f = $('rptFrom').value, t = $('rptTo').value;
    return (f && t) ? ('&from=' + encodeURIComponent(f) + '&to=' + encodeURIComponent(t)) : '';
  }

  function downloadReport(type) {
    var f = $('rptFrom').value, t = $('rptTo').value;
    if ((f && !t) || (!f && t)) { toast('请同时选择开始和结束日期，或点「全部」清空区间', true); return; }
    if (f && t && f > t) { toast('开始日期不能晚于结束日期', true); return; }
    if (type === 'accounts' || type === 'houses') {
      // 账户/户表是时点快照，不需要区间
      location.href = '/api/jifen/admin/export?type=' + type;
    } else {
      location.href = '/api/jifen/admin/export?type=' + type + rptQuery();
    }
    toast('已开始下载，请查看浏览器下载栏');
  }

  function loadHealth() {
    $('healthList').innerHTML = '<div class="loading">体检中…</div>';
    api('/api/jifen/admin/health').then(function (d) {
      if (!d.success) {
        $('healthList').innerHTML = '<div class="empty">' + esc(d.error || '体检失败') + '</div>';
        return;
      }
      $('healthTs').textContent = '检查时间 ' + d.ts;
      $('healthList').innerHTML = (d.items || []).map(function (x) {
        return '<div class="hrow ' + x.level + '"><span class="dot"></span>' +
          '<div><b>' + esc(x.title) + '</b><span class="d">' + esc(x.detail) + '</span></div>' +
          (x.count ? '<span class="cnt">' + n(x.count) + '</span>' : '') + '</div>';
      }).join('');
    });
  }

  function kb(b) {
    b = Number(b || 0);
    return b > 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB';
  }

  function loadBackups() {
    api('/api/jifen/admin/backups').then(function (d) {
      if (!d.success) {
        $('tBackups').innerHTML = '<tbody><tr><td class="empty">' + esc(d.error || '加载失败') + '</td></tr></tbody>';
        return;
      }
      S.backups = d.backups || [];
      $('bkTip').textContent = d.tip || '';
      renderBackups();
    });
  }

  function renderBackups() {
    var h = '<thead><tr><th>备份文件</th><th>备份时间</th><th>内容</th>' +
      '<th class="r">大小</th><th class="c">操作</th></tr></thead><tbody>';
    if (!S.backups.length) {
      h += '<tr><td colspan="5" class="empty">还没有服务器备份，点「立即备份」生成第一份</td></tr>';
    }
    S.backups.forEach(function (b) {
      h += '<tr><td><b>' + esc(b.name) + '</b></td><td>' + esc(b.mtime) + '</td>' +
        '<td class="hint">' + esc(b.summary || '') + '</td><td class="r">' + kb(b.size) + '</td>' +
        '<td class="c"><button class="btn sm ghost" data-bkdl="' + esc(b.name) + '">下载</button> ' +
        '<button class="btn sm ok" data-bkrs="' + esc(b.name) + '">恢复</button> ' +
        '<button class="btn sm danger" data-bkdel="' + esc(b.name) + '">删除</button></td></tr>';
    });
    $('tBackups').innerHTML = h + '</tbody>';
  }

  function doBackupNow() {
    var btn = $('btnBackupNow');
    btn.disabled = true;
    api('/api/jifen/admin/backup_now', {}).then(function (d) {
      btn.disabled = false;
      if (!d.success) { toast(d.error || '备份失败', true); return; }
      toast(d.message || '备份完成');
      loadBackups();
    });
  }

  function countsOf(d) {
    var c = {}, t = d.tables || {};
    Object.keys(t).forEach(function (k) { c[k] = (t[k].rows || []).length; });
    return c;
  }

  function restoreDialog(title, p) {
    var c = p.counts || {};
    var rows = [['积分账户', 'jf_accounts'], ['积分流水', 'jf_txns'], ['兑换单', 'jf_orders'],
      ['兑换明细', 'jf_order_items'], ['商品', 'jf_goods'], ['积分规则', 'jf_rules'],
      ['红黑榜案例', 'jf_cases']];
    var html = '<div class="bk-warn">恢复会改写现有积分数据。系统会在恢复前自动把当前数据另存一份备份（jf_pre_restore_*），需要时可再恢复回来。</div>' +
      '<div class="hint" style="margin-bottom:10px">来源：<b>' + esc(p.from) + '</b>' +
      (p.ts ? ' · 备份时间 ' + esc(p.ts) : '') + '</div>' +
      '<div class="tbl-wrap"><table class="tbl"><thead><tr><th>数据</th><th class="r">条数</th></tr></thead><tbody>' +
      rows.map(function (r) {
        return '<tr><td>' + r[0] + '</td><td class="r">' + n(c[r[1]] || 0) + '</td></tr>';
      }).join('') + '</tbody></table></div>' +
      '<label class="fld" style="margin-top:12px"><span>恢复方式</span>' +
      '<div class="seg" id="rsMode"><button class="on" data-rm="replace">覆盖（先清空）</button>' +
      '<button data-rm="merge">合并（保留现有）</button></div></label>' +
      '<label class="fld"><span>请输入「恢复」二字确认</span>' +
      '<input id="rsConfirm" placeholder="恢复" autocomplete="off"></label>';

    modal(title, html,
      '<button class="btn ghost" data-close>取消</button>' +
      '<button class="btn danger" id="rsGo">确认恢复</button>',
      function (bd, ft) {
        var mode = 'replace';
        bd.querySelectorAll('#rsMode button').forEach(function (b) {
          b.onclick = function () {
            mode = b.getAttribute('data-rm');
            bd.querySelectorAll('#rsMode button').forEach(function (x) {
              x.classList.toggle('on', x === b);
            });
          };
        });
        ft.querySelector('#rsGo').onclick = function () {
          var cf = bd.querySelector('#rsConfirm').value.trim();
          if (cf !== '恢复') { toast('请输入「恢复」二字', true); return; }
          var body = { mode: mode, confirm: cf };
          if (p.name) body.name = p.name;
          else body.data = p.data;
          this.disabled = true;
          var self = this;
          api('/api/jifen/admin/restore', body).then(function (d) {
            if (!d.success) {
              toast(d.error || '恢复失败', true);
              self.disabled = false;
              return;
            }
            closeMask();
            toast(d.message || '恢复完成');
            loadBackups();
            loadHealth();
            loadOverview();
          });
        };
      }, true);
  }

  function onPickBackup(file) {
    if (!file) return;
    if (file.size > 30 * 1024 * 1024) { toast('备份文件超过 30MB，已拒绝', true); return; }
    var rd = new FileReader();
    rd.onload = function () {
      var d;
      try { d = JSON.parse(rd.result); } catch (e) { toast('文件不是有效的 JSON 备份', true); return; }
      if (!d || !d.tables) { toast('备份文件格式不正确（缺少 tables）', true); return; }
      restoreDialog('从文件恢复', {
        from: file.name, data: d, ts: d.ts || '',
        counts: d.counts || countsOf(d)
      });
    };
    rd.readAsText(file, 'utf-8');
  }

  /* ---------------- 绑定 ---------------- */
  function bindAll() {
    var timer = null;
    function debounce(fn, ms) {
      return function () {
        clearTimeout(timer);
        timer = setTimeout(fn, ms || 320);
      };
    }
    $('gsearch').addEventListener('input', debounce(renderGoods));
    document.querySelectorAll('#accView button').forEach(function (b) {
      b.onclick = function () {
        S.accView = b.getAttribute('data-av') === 'house' ? 'house' : 'person';
        document.querySelectorAll('#accView button').forEach(function (x) {
          x.classList.toggle('on', x === b);
        });
        $('aSearch').placeholder = S.accView === 'house'
          ? '户主姓名 / 组别 / 地址' : '姓名 / 手机 / 组别 / 积分码';
        $('btnAddAcc').style.display = S.accView === 'house' ? 'none' : '';
        $('btnImport').style.display = S.accView === 'house' ? 'none' : '';
        $('btnHuCheck').style.display = S.accView === 'house' ? '' : 'none';
        $('btnCards').style.display = S.accView === 'house' ? 'none' : '';
        $('btnCodeFill').style.display = S.accView === 'house' ? 'none' : '';
        S.accPage = 1;
        loadAccounts();
      };
    });
    $('btnAddGoods').onclick = function () { goodsForm(''); };
    $('btnAddAcc').onclick = function () { accForm(''); };
    $('btnImport').onclick = importHukou;
    $('btnCodeFill').onclick = function () {
      if (!confirm('为「没有手机号、还没有积分码」的账户批量生成 6 位登录码？\n（已有积分码的不变，可重复执行）')) return;
      api('/api/jifen/admin/code_fill', { scope: 'missing' }).then(function (d) {
        if (!d.success) { toast(d.error || '生成失败', true); return; }
        toast(d.message || ('已生成 ' + (d.filled || 0) + ' 个积分码'));
        loadAccounts();
      });
    };
    $('btnHuCheck').onclick = huReview;
    $('btnHuAssign').onclick = function () { huAssign([]); };
    $('btnCards').onclick = function () {
      var q = S.accKw ? '?kw=' + encodeURIComponent(S.accKw) : '';
      window.open('/api/jifen/admin/cards' + q, '_blank');
    };
    $('btnAddRule').onclick = function () { ruleForm(''); };
    $('btnAddCase').onclick = function () { caseForm(''); };

    /* ---- 数据大屏 ---- */
    document.querySelectorAll('#dashRange button').forEach(function (b) {
      b.onclick = function () {
        S.dashDays = Number(b.getAttribute('data-dr')) || 30;
        document.querySelectorAll('#dashRange button').forEach(function (x) {
          x.classList.toggle('on', x === b);
        });
        loadDash();
      };
    });
    document.querySelectorAll('#dashRankSeg button').forEach(function (b) {
      b.onclick = function () {
        S.rankView = b.getAttribute('data-rk') === 'house' ? 'house' : 'person';
        document.querySelectorAll('#dashRankSeg button').forEach(function (x) {
          x.classList.toggle('on', x === b);
        });
        renderRank();
      };
    });
    $('btnDashRefresh').onclick = loadDash;
    $('btnDashFull').onclick = toggleDashFull;
    $('dashExit').onclick = toggleDashFull;
    $('btnDashPrint').onclick = function () { window.print(); };

    /* ---- 数据管理 ---- */
    renderReports();
    initReportRange();
    $('btnHealth').onclick = loadHealth;
    document.querySelectorAll('[data-rq]').forEach(function (b) {
      b.onclick = function () {
        var k = b.getAttribute('data-rq');
        var now = new Date();
        if (k === 'month') {
          $('rptFrom').value = ymd(new Date(now.getFullYear(), now.getMonth(), 1));
          $('rptTo').value = ymd(now);
        } else if (k === 'year') {
          $('rptFrom').value = ymd(new Date(now.getFullYear(), 0, 1));
          $('rptTo').value = ymd(now);
        } else {
          $('rptFrom').value = '';
          $('rptTo').value = '';
        }
        toast(k === 'all' ? '已切换为全部历史数据' : '区间已切换，可点报表卡片下载');
      };
    });
    $('btnBackupNow').onclick = doBackupNow;
    $('btnBackupDownload').onclick = function () { location.href = '/api/jifen/admin/backup'; };
    $('btnBackupUpload').onclick = function () { $('bkFile').click(); };
    $('bkFile').onchange = function () { onPickBackup(this.files && this.files[0]); this.value = ''; };

    $('aSearch').addEventListener('input', debounce(function () {
      S.accKw = $('aSearch').value.trim(); S.accPage = 1; loadAccounts();
    }));
    $('tSearch').addEventListener('input', debounce(function () {
      S.txnKw = $('tSearch').value.trim(); S.txnPage = 1; loadTxns();
    }));
    $('oSearch').addEventListener('input', debounce(function () {
      S.ordKw = $('oSearch').value.trim(); S.ordPage = 1; loadOrderList();
    }));
    $('oStatus').onchange = function () {
      S.ordStatus = $('oStatus').value; S.ordPage = 1; loadOrderList();
    };
    $('grSearch').addEventListener('input', debounce(function () {
      loadGrantPeople($('grSearch').value.trim());
    }));
    $('grRule').onchange = function () {
      var o = $('grRule').selectedOptions[0];
      var p = o && o.getAttribute('data-p');
      if (p) $('grPoints').value = p;
      var nm = o && o.value ? o.textContent.split('（')[0] : '';
      if (nm && !$('grReason').value) $('grReason').value = nm;
      syncGrantCount();
    };
    $('grPoints').addEventListener('input', syncGrantCount);
    $('btnGrant').onclick = doGrant;
    $('btnFind').onclick = findOrder;
    $('vCode').addEventListener('keydown', function (e) { if (e.key === 'Enter') findOrder(); });
    $('vCode').addEventListener('input', function () {
      this.value = this.value.replace(/\D/g, '').slice(0, 6);
    });
    $('btnExportTxn').onclick = function () {
      location.href = '/api/jifen/admin/export?type=txns';
    };
  }

  /* ---------------- 登录态相关：改密码 / 退出 ---------------- */
  function bindAuth() {
    if ($('btnPwd')) {
      $('btnPwd').onclick = function (e) {
        e.preventDefault();
        modal('修改密码',
          '<label class="fld"><span>原密码</span><input id="pw_old" type="password" autocomplete="current-password"></label>' +
          '<label class="fld"><span>新密码（至少 6 位）</span><input id="pw_new" type="password" autocomplete="new-password"></label>' +
          '<label class="fld"><span>再输一次新密码</span><input id="pw_new2" type="password" autocomplete="new-password"></label>',
          '<button class="btn ghost" data-close>取消</button><button class="btn primary" id="pw_save">保存</button>',
          function () {
            $('pw_save').onclick = function () {
              var o = $('pw_old').value, n1 = $('pw_new').value, n2 = $('pw_new2').value;
              if (!o) { toast('请输入原密码', true); return; }
              if (n1.length < 6) { toast('新密码至少 6 位', true); return; }
              if (n1 !== n2) { toast('两次新密码不一致', true); return; }
              api('/api/auth/pwd', { old: o, new: n1 }).then(function (d) {
                if (!d.success) { toast(d.error || '修改失败', true); return; }
                toast('密码已修改，请用新密码重新登录');
                setTimeout(function () { location.href = '/login.html'; }, 900);
              });
            };
          });
      };
    }
    if ($('btnLogout')) {
      $('btnLogout').onclick = function (e) {
        e.preventDefault();
        if (!confirm('确定退出登录？')) return;
        api('/api/auth/logout', {}).then(function () { location.href = '/login.html'; })
          .catch(function () { location.href = '/login.html'; });
      };
    }
  }

  /* ---------------- 站点信息（超市名称等，跟随后台「超市设置」） ---------------- */
  function siteName() {
    var n = ((S.cfg || {}).market_name || '').trim();
    return n || '积分超市';
  }

  function applySite() {
    var name = siteName();
    if ($('dashTtl')) $('dashTtl').textContent = name + ' · 运行分析';
    if ($('topTitle')) $('topTitle').textContent = name;
    document.title = name + ' · 管理后台';
  }

  function loadSite() {
    return api('/api/jifen/config').then(function (d) {
      if (d.success) { S.cfg = d.settings || {}; applySite(); }
    }).catch(function () { });
  }

  /* ---------------- 启动 ---------------- */
  api('/api/auth/me').then(function (d) {
    if (!d.success) { location.href = '/login.html?next=' + encodeURIComponent(location.pathname); return; }
    $('whoami').textContent = (d.user.name || d.user.username) + ' · ' + ({ admin: '管理员', editor: '编辑员', viewer: '浏览员' }[d.user.role] || d.user.role);
    if (d.user.role === 'viewer') {
      document.querySelectorAll('.side button').forEach(function (b) {
        if (['grant', 'verify', 'goods', 'acc', 'txn', 'rule', 'case', 'data', 'set'].indexOf(b.getAttribute('data-p')) >= 0) b.style.display = 'none';
      });
    }
    bindAll();
    bindAuth();
    loadSite();
    loadOverview();
  }).catch(function () { });
})();
