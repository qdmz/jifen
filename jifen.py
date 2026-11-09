#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
积分超市（乡村治理积分制）· 业务模块
-------------------------------------------------
由 app.py 挂载：
    GET  /api/jifen/*             公开（商品、规则、积分榜、查分、我的兑换）
    POST /api/jifen/lookup        姓名/身份证后6位/积分码 查积分（发短期 token）
    POST /api/jifen/redeem        在线提交兑换（凭 token）
    *    /api/jifen/admin/*       需登录且角色为 admin / editor
数据表：jf_accounts / jf_txns / jf_goods / jf_orders / jf_order_items / jf_rules
        jf_settings / jf_cases / jf_hh（家庭成员档案，用于按户归集）
数据目录：默认 ./data（环境变量 JF_DATA_DIR / JF_DB 可覆盖）
"""
import os, re, json, time, secrets, sqlite3, urllib.parse
import csv, io, base64, datetime, shutil
from collections import Counter, defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('JF_DATA_DIR') or os.path.join(BASE_DIR, 'data')
SQLITE_FILE = os.environ.get('JF_DB') or os.path.join(DATA_DIR, 'jifen.db')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')

TOKEN_TTL = 1800            # 查分 token 有效期 30 分钟
PAGE_SIZE = 20
MAX_QTY = 20                # 单次单件最大兑换数量


# ---------------------------------------------------------------- 基础工具
def _now():
    return time.strftime('%Y-%m-%d %H:%M:%S')


def _uid(p=''):
    return p + secrets.token_hex(8)


_DB_FILE = SQLITE_FILE


def set_db(path):
    """允许 server.py 覆盖数据库路径（测试实例会指向 village.db 的副本）"""
    global _DB_FILE
    _DB_FILE = path


def _conn():
    c = sqlite3.connect(_DB_FILE, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA busy_timeout=30000')
    return c


def _int(v, d=0):
    try:
        n = int(float(str(v).strip()))
        return n
    except Exception:
        return d


def _s(v, n=200):
    return str(v if v is not None else '').strip()[:n]


# ---------------------------------------------------------------- 初始化
DDL = [
    """CREATE TABLE IF NOT EXISTS jf_accounts(
        id TEXT PRIMARY KEY, name TEXT NOT NULL, grp TEXT DEFAULT '', phone TEXT DEFAULT '',
        idcard TEXT DEFAULT '', points INTEGER DEFAULT 0, earned INTEGER DEFAULT 0,
        spent INTEGER DEFAULT 0, status TEXT DEFAULT '正常', note TEXT DEFAULT '',
        created TEXT, updated TEXT)""",
    "CREATE INDEX IF NOT EXISTS ix_jf_acc_name ON jf_accounts(name)",
    "CREATE INDEX IF NOT EXISTS ix_jf_acc_grp ON jf_accounts(grp)",
    """CREATE TABLE IF NOT EXISTS jf_txns(
        id TEXT PRIMARY KEY, acc_id TEXT, name TEXT, grp TEXT, kind TEXT, points INTEGER,
        balance INTEGER, reason TEXT, ref TEXT, operator TEXT, created TEXT)""",
    "CREATE INDEX IF NOT EXISTS ix_jf_txn_acc ON jf_txns(acc_id, created)",
    """CREATE TABLE IF NOT EXISTS jf_goods(
        id TEXT PRIMARY KEY, name TEXT, cat TEXT, icon TEXT, spec TEXT, points INTEGER,
        stock INTEGER, sold INTEGER DEFAULT 0, limit_per INTEGER DEFAULT 0,
        desc TEXT, status TEXT DEFAULT '上架', sort INTEGER DEFAULT 0,
        created TEXT, updated TEXT)""",
    """CREATE TABLE IF NOT EXISTS jf_orders(
        id TEXT PRIMARY KEY, code TEXT UNIQUE, acc_id TEXT, name TEXT, phone TEXT, grp TEXT,
        points INTEGER, status TEXT DEFAULT '待领取', src TEXT DEFAULT 'online',
        items TEXT, created TEXT, done_at TEXT, operator TEXT, note TEXT)""",
    "CREATE INDEX IF NOT EXISTS ix_jf_order_acc ON jf_orders(acc_id, created)",
    "CREATE INDEX IF NOT EXISTS ix_jf_order_status ON jf_orders(status)",
    """CREATE TABLE IF NOT EXISTS jf_order_items(
        id TEXT PRIMARY KEY, order_id TEXT, gid TEXT, gname TEXT, icon TEXT,
        qty INTEGER, points INTEGER)""",
    "CREATE INDEX IF NOT EXISTS ix_jf_oi_order ON jf_order_items(order_id)",
    "CREATE INDEX IF NOT EXISTS ix_jf_oi_gid ON jf_order_items(gid)",
    """CREATE TABLE IF NOT EXISTS jf_rules(
        id TEXT PRIMARY KEY, name TEXT, cat TEXT, points INTEGER, unit TEXT,
        desc TEXT, enabled INTEGER DEFAULT 1, sort INTEGER DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS jf_settings(
        k TEXT PRIMARY KEY, v TEXT)""",
    """CREATE TABLE IF NOT EXISTS jf_hh(
        idcard TEXT PRIMARY KEY, name TEXT, grp TEXT, hu_zhu TEXT, rel TEXT,
        phone TEXT, src TEXT, updated TEXT)""",
    "CREATE INDEX IF NOT EXISTS ix_jf_hh_nm ON jf_hh(name, grp)",
    "CREATE INDEX IF NOT EXISTS ix_jf_hh_zhu ON jf_hh(hu_zhu, grp)",
    """CREATE TABLE IF NOT EXISTS jf_cases(
        id TEXT PRIMARY KEY, kind TEXT DEFAULT 'red', title TEXT, who TEXT, grp TEXT,
        points INTEGER DEFAULT 0, desc TEXT, img TEXT, happen TEXT,
        status TEXT DEFAULT '发布', sort INTEGER DEFAULT 0,
        created TEXT, updated TEXT, operator TEXT)""",
    "CREATE INDEX IF NOT EXISTS ix_jf_case_kind ON jf_cases(kind, status, sort)",
]

SEED_GOODS = [
    ('洗衣粉 500g', '清洁洗护', '🧴', '500g/袋', 30, 60, 0, 3),
    ('洗衣液 2kg', '清洁洗护', '🫧', '2kg/瓶', 60, 30, 0, 2),
    ('洗洁精 500ml', '清洁洗护', '🧽', '500ml/瓶', 25, 50, 0, 3),
    ('香皂', '清洁洗护', '🧼', '块', 10, 100, 0, 5),
    ('牙膏', '清洁洗护', '🪥', '支', 20, 60, 0, 3),
    ('毛巾', '日用百货', '🧻', '条', 25, 60, 0, 3),
    ('卷纸（10 卷）', '日用百货', '🧾', '提', 35, 40, 0, 2),
    ('雨伞', '日用百货', '☂️', '把', 50, 25, 0, 2),
    ('手电筒', '日用百货', '🔦', '支', 45, 20, 0, 2),
    ('雨衣', '日用百货', '🧥', '件', 55, 20, 0, 2),
    ('保温杯', '日用百货', '🥤', '个', 90, 15, 0, 1),
    ('食盐 400g', '食品粮油', '🧂', '袋', 8, 80, 0, 5),
    ('生抽 500ml', '食品粮油', '🥫', '瓶', 25, 40, 0, 3),
    ('大米 5kg', '食品粮油', '🍚', '袋', 120, 20, 0, 2),
    ('大米 10kg', '食品粮油', '🌾', '袋', 220, 10, 0, 1),
    ('菜籽油 5L', '食品粮油', '🛢️', '桶', 180, 10, 0, 1),
    ('书包', '学习用品', '🎒', '个', 150, 10, 0, 1),
    ('文具套装', '学习用品', '✏️', '套', 60, 20, 0, 2),
    ('笔记本 + 中性笔', '学习用品', '📒', '套', 30, 30, 0, 3),
]

SEED_RULES = [
    ('参加村民会议、村民代表会议', '议事参与', 5, '次', '按时到场并签到，每次 5 分'),
    ('参加村集体环境整治、义务劳动', '志愿服务', 10, '次', '按村委会通知参加，每次 10 分'),
    ('参加护林防火、防汛抗旱值守', '志愿服务', 10, '次', '按排班到岗，每次 10 分'),
    ('获评“星级文明户”“最美家庭”', '文明新风', 50, '次', '县级以上表彰另计'),
    ('门前三包、卫生评比优秀', '人居环境', 20, '季', '每季度评比一次，优秀户 20 分'),
    ('主动调解邻里纠纷、化解矛盾', '文明新风', 15, '次', '经村委会确认有效'),
    ('红白事简办、不铺张浪费', '文明新风', 30, '次', '报备并按村规民约办理'),
    ('助人为乐、见义勇为、拾金不昧', '文明新风', 10, '次', '经村委会核实'),
    ('按时缴纳城乡居民医保、养老保险', '政策落实', 5, '人', '按参保人数计分'),
    ('子女无辍学、考入大专及以上院校', '教育成才', 100, '人', '凭录取通知书'),
    ('应征入伍', '国防义务', 100, '人', '凭入伍通知书'),
    ('参与积分制宣传、带头示范', '议事参与', 5, '次', '每季度不超过 4 次'),
]

DEFAULT_SETTINGS = {
    'market_name': '积分超市',
    'slogan': '小积分 · 大文明  人人参与 · 共建家园',
    'address': '村委会一楼积分超市',
    'open_time': '每周一、三、五  9:00—17:00',
    'contact': '村委会  0851-xxxxxxx',
    'notice': '积分按户累计、按人记账；兑换后请凭取货码到村委会一楼积分超市领取实物。积分不兑现、不转让，年度结余可结转。',
    'case_intro': '红榜表扬先进、黑榜警示后进，用身边事教育身边人。',
    'case_black_mask': '1',      # 黑榜是否隐藏姓名中间字（1=脱敏，0=全名公示）
}


def init(seed=True):
    """建表 + 首次写入预置商品/规则（幂等）。seed=False 时只建表不预置（迁移数据用）"""
    conn = _conn()
    try:
        for sql in DDL:
            conn.execute(sql)
        # 归户字段（2026-11-07 新增，老库自动补列）
        cols = {r['name'] for r in conn.execute('PRAGMA table_info(jf_accounts)')}
        for col, ddl in (('hu', "ALTER TABLE jf_accounts ADD COLUMN hu TEXT DEFAULT ''"),
                         ('hu_zhu', "ALTER TABLE jf_accounts ADD COLUMN hu_zhu TEXT DEFAULT ''"),
                         ('hu_seq', 'ALTER TABLE jf_accounts ADD COLUMN hu_seq INTEGER DEFAULT 0'),
                         ('addr', "ALTER TABLE jf_accounts ADD COLUMN addr TEXT DEFAULT ''"),
                         ('hu_src', "ALTER TABLE jf_accounts ADD COLUMN hu_src TEXT DEFAULT ''"),
                         ('hu_lock', 'ALTER TABLE jf_accounts ADD COLUMN hu_lock INTEGER DEFAULT 0'),
                         ('code', "ALTER TABLE jf_accounts ADD COLUMN code TEXT DEFAULT ''")):
            if col not in cols:
                conn.execute(ddl)
                print('[JF] 账户表已补列 %s' % col)
        conn.execute('CREATE INDEX IF NOT EXISTS ix_jf_acc_hu ON jf_accounts(hu)')
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_jf_acc_code ON jf_accounts(code) "
                     "WHERE code<>''")
        conn.commit()
        # 每个账户配一个 6 位积分码（没手机号 / 没身份证时的兜底登录凭证）
        miss = conn.execute("SELECT COUNT(*) c FROM jf_accounts "
                            "WHERE code IS NULL OR code=''").fetchone()['c']
        if miss:
            taken = _code_taken(conn)
            for r in conn.execute("SELECT id FROM jf_accounts "
                                  "WHERE code IS NULL OR code=''").fetchall():
                conn.execute("UPDATE jf_accounts SET code=? WHERE id=?",
                             (_new_code(conn, taken), r['id']))
            conn.commit()
            print('[JF] 已为 %d 个账户生成积分码（登录用）' % miss)
        try:
            r = _sync_hu(conn, force=True)
            if r['acc']:
                print('[JF] 按户籍地址归户：%d 个账户 → %d 户，未归户 %d 个'
                      % (r['acc'], r['hu'], r['miss']))
        except Exception as e:
            print('[JF] 归户失败（不影响使用）:', e)
        if seed and conn.execute("SELECT COUNT(*) c FROM jf_goods").fetchone()['c'] == 0:
            for i, (nm, cat, ic, spec, pts, st, lp, srt) in enumerate(SEED_GOODS):
                conn.execute(
                    "INSERT INTO jf_goods(id,name,cat,icon,spec,points,stock,sold,limit_per,desc,status,sort,created,updated)"
                    " VALUES(?,?,?,?,?,?,?,0,?,'', '上架',?,?,?)",
                    (_uid('g_'), nm, cat, ic, spec, pts, st, lp, srt, _now(), _now()))
            print('[JF] 已预置 %d 件积分商品' % len(SEED_GOODS))
        if seed and conn.execute("SELECT COUNT(*) c FROM jf_rules").fetchone()['c'] == 0:
            for i, (nm, cat, pts, unit, desc) in enumerate(SEED_RULES):
                conn.execute("INSERT INTO jf_rules(id,name,cat,points,unit,desc,enabled,sort) VALUES(?,?,?,?,?,?,1,?)",
                             (_uid('r_'), nm, cat, pts, unit, desc, i))
            print('[JF] 已预置 %d 条积分规则' % len(SEED_RULES))
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO jf_settings(k,v) VALUES(?,?)", (k, v))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- 会话 token
_TOKENS = {}       # token -> {'acc': id, 'exp': ts}


def _issue_token(acc_id):
    now = time.time()
    for k in [k for k, v in _TOKENS.items() if v['exp'] < now]:      # 顺手清理
        _TOKENS.pop(k, None)
    tk = secrets.token_urlsafe(18)
    _TOKENS[tk] = {'acc': acc_id, 'exp': now + TOKEN_TTL}
    return tk


def _token_acc(tk):
    rec = _TOKENS.get(str(tk or ''))
    if not rec:
        return None
    if rec['exp'] < time.time():
        _TOKENS.pop(tk, None)
        return None
    return rec['acc']


# ---------------------------------------------------------------- 公共读取
def _settings(conn):
    d = dict(DEFAULT_SETTINGS)
    for r in conn.execute("SELECT k,v FROM jf_settings"):
        d[r['k']] = r['v']
    return d


def _goods(conn, admin=False):
    sql = "SELECT * FROM jf_goods"
    if not admin:
        sql += " WHERE status = '上架' ORDER BY points"
    else:
        sql += " ORDER BY cat, points"
    out = []
    for r in conn.execute(sql):
        out.append({
            'id': r['id'], 'name': r['name'], 'cat': r['cat'], 'icon': r['icon'] or '🎁',
            'spec': r['spec'] or '', 'points': r['points'], 'stock': r['stock'],
            'sold': r['sold'] or 0, 'limit_per': r['limit_per'] or 0,
            'desc': r['desc'] or '', 'status': r['status'], 'sort': r['sort'] or 0,
        })
    return out


def _rules(conn, admin=False):
    sql = "SELECT * FROM jf_rules" + ("" if admin else " WHERE enabled = 1") + " ORDER BY sort, id"
    return [{'id': r['id'], 'name': r['name'], 'cat': r['cat'], 'points': r['points'],
             'unit': r['unit'] or '次', 'desc': r['desc'] or '', 'enabled': r['enabled'],
             'sort': r['sort'] or 0} for r in conn.execute(sql)]


def _mask_name(n):
    n = str(n or '')
    if len(n) <= 1:
        return n
    if len(n) == 2:
        return n[0] + '*'
    return n[0] + '*' * (len(n) - 2) + n[-1]


# ---------------------------------------------------------------- 积分红黑榜
UPLOAD_DIR = os.path.join(DATA_DIR, 'uploads', 'jf')
UPLOAD_MAX = 4 * 1024 * 1024          # 单张图片解码后上限 4MB
_IMG_EXT = {'jpeg': 'jpg', 'jpg': 'jpg', 'png': 'png', 'webp': 'webp'}


def _ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def _case_json(r, settings=None):
    """红黑榜案例对外结构；黑榜按设置隐藏姓名中间字"""
    settings = settings or {}
    name = r['who'] or ''
    mask = str(settings.get('case_black_mask', '1')) == '1'
    show = _mask_name(name) if (r['kind'] == 'black' and mask) else name
    return {
        'id': r['id'], 'kind': r['kind'], 'title': r['title'] or '',
        'who': show, 'who_full': name, 'grp': r['grp'] or '',
        'points': r['points'] or 0, 'desc': r['desc'] or '',
        'img': r['img'] or '', 'happen': r['happen'] or '',
        'status': r['status'] or '发布', 'sort': r['sort'] or 0,
        'created': r['created'] or '', 'operator': r['operator'] or '',
    }


def _cases(conn, kind='', admin=False, limit=100):
    where, args = [], []
    if not admin:
        where.append("status='发布'")
    if kind in ('red', 'black'):
        where.append('kind=?')
        args.append(kind)
    w = ('WHERE ' + ' AND '.join(where)) if where else ''
    sql = ("SELECT * FROM jf_cases " + w +
           " ORDER BY sort DESC, COALESCE(NULLIF(happen,''), created) DESC, created DESC LIMIT ?")
    rows = conn.execute(sql, args + [limit]).fetchall()
    st = _settings(conn)
    return [_case_json(r, st) for r in rows]


def _save_upload(data_url, name_hint=''):
    """保存 dataURL 图片到 uploads/jf/，返回可访问的相对路径"""
    m = re.match(r'^data:image/(jpeg|jpg|png|webp);base64,(.+)$', str(data_url or ''), re.S)
    if not m:
        raise BizError('图片格式不支持，请上传 JPG / PNG / WebP')
    ext = _IMG_EXT[m.group(1)]
    try:
        raw = base64.b64decode(m.group(2), validate=False)
    except Exception:
        raise BizError('图片数据损坏，请重新选择')
    if not raw:
        raise BizError('图片为空')
    if len(raw) > UPLOAD_MAX:
        raise BizError('图片超过 %.1f MB，请压缩后再传' % (UPLOAD_MAX / 1048576.0))
    _ensure_upload_dir()
    fn = '%s_%s.%s' % (time.strftime('%Y%m%d_%H%M%S'), secrets.token_hex(4), ext)
    with open(os.path.join(UPLOAD_DIR, fn), 'wb') as fh:
        fh.write(raw)
    return '/uploads/jf/' + fn


def _drop_upload(url):
    """删除案例时顺手清理图片（仅限本模块目录内的文件）"""
    u = str(url or '')
    if not u.startswith('/uploads/jf/'):
        return
    p = os.path.join(UPLOAD_DIR, os.path.basename(u))
    try:
        if os.path.isfile(p):
            os.remove(p)
    except OSError:
        pass


def _acc_public(r):
    """对外展示的账户信息：手机号脱敏，返回余额与累计"""
    ph = str(r['phone'] or '')
    return {
        'id': r['id'], 'name': r['name'], 'grp': r['grp'] or '', 'phone': r['phone'] or '',
        'phone_mask': (ph[:3] + '****' + ph[-4:]) if len(ph) >= 8 else ph,
        'points': r['points'] or 0, 'earned': r['earned'] or 0, 'spent': r['spent'] or 0,
        'status': r['status'] or '正常',
    }


def _code_taken(conn):
    """已占用的 6 位号：已有积分码 + 所有人身份证后 6 位（防止两种凭证撞车）"""
    taken = {str(r['code']) for r in conn.execute("SELECT code FROM jf_accounts WHERE code<>''")}
    taken |= {str(r['idcard'] or '')[-6:].upper()
              for r in conn.execute("SELECT idcard FROM jf_accounts WHERE idcard<>''")}
    return taken


def _new_code(conn, taken=None):
    """生成 6 位积分码（无手机/无身份证时的兜底登录凭证）"""
    if taken is None:
        taken = _code_taken(conn)
    for _ in range(500):
        c = '%06d' % (100000 + secrets.randbelow(900000))
        if c not in taken:
            taken.add(c)
            return c
    n = 100001
    while str(n) in taken:
        n += 1
    taken.add(str(n))
    return str(n)


def _acc_admin(r):
    """管理端账户视图：含身份证与登录码，仅供后台接口使用"""
    d = _acc_public(r)
    idc = str(r['idcard'] or '')
    d.update({
        'idcard': idc,
        'idcard_mask': (idc[:6] + '********' + idc[-4:]) if len(idc) >= 15 else idc,
        'code': str(r['code'] or ''),
        'hu': str(r['hu'] or '') if 'hu' in r.keys() else '',
        'hu_zhu': str(r['hu_zhu'] or '') if 'hu_zhu' in r.keys() else '',
        'hu_src': str(r['hu_src'] or '') if 'hu_src' in r.keys() else '',
    })
    return d


# 村民端查分限速：同 IP 连续失败 6 次锁 5 分钟（6 位码空间不大，必须防枚举）
_LOOKUP_FAIL = {}


def client_ip(handler):
    """真实客户端 IP：经 Cloudflare Tunnel / Nginx 反代时取请求头，否则用 socket 地址。
    不处理这一层，所有访客都会被当成 127.0.0.1，一个人输错就锁住全村。"""
    h = getattr(handler, 'headers', None)
    if h is not None:
        for k in ('CF-Connecting-IP', 'X-Real-IP', 'X-Forwarded-For'):
            try:
                v = h.get(k)
            except Exception:
                v = None
            if not v:
                continue
            v = str(v).split(',')[0].strip()
            if v:
                return v
    addr = getattr(handler, 'client_address', None) or ('',)
    return addr[0]


def _lookup_locked(ip):
    rec = _LOOKUP_FAIL.get(str(ip or ''))
    return bool(rec and rec[1] > time.time())


def _lookup_fail(ip):
    ip = str(ip or '')
    if not ip:
        return
    now = time.time()
    rec = _LOOKUP_FAIL.get(ip) or [0, 0]
    if rec[1] and rec[1] <= now:
        rec = [0, 0]
    rec[0] += 1
    if rec[0] >= 6:
        rec = [0, now + 300]
        print('[JF] 查分锁定 IP %s 5 分钟（连续失败 6 次）' % ip)
    _LOOKUP_FAIL[ip] = rec
    if len(_LOOKUP_FAIL) > 5000:
        for k, v in list(_LOOKUP_FAIL.items()):
            if not v[1] and v[0] == 0:
                _LOOKUP_FAIL.pop(k, None)


def _lookup_clear(ip):
    _LOOKUP_FAIL.pop(str(ip or ''), None)


def _group_list(conn):
    """村民组列表（登录时区分同名村民用），按名称归并后去重、去空"""
    rows = conn.execute("SELECT grp FROM jf_accounts WHERE status='正常' AND grp<>''").fetchall()
    gs = {_norm_grp(r['grp']) for r in rows}
    gs.discard('')
    return sorted(gs)


def _rank(conn, limit=20):
    rows = conn.execute(
        "SELECT name, grp, points, earned FROM jf_accounts WHERE status='正常' AND points > 0 "
        "ORDER BY points DESC, earned DESC, name LIMIT ?", (limit,)).fetchall()
    out = []
    for i, r in enumerate(rows, 1):
        out.append({'no': i, 'name': _mask_name(r['name']), 'grp': r['grp'] or '',
                    'points': r['points'], 'earned': r['earned'] or 0})
    return out


def _txn_json(r):
    return {'id': r['id'], 'acc_id': r['acc_id'], 'name': r['name'], 'grp': r['grp'] or '',
            'kind': r['kind'], 'points': r['points'], 'balance': r['balance'],
            'reason': r['reason'] or '', 'ref': r['ref'] or '', 'operator': r['operator'] or '',
            'created': r['created']}


def _order_json(conn, r, with_items=True):
    d = {'id': r['id'], 'code': r['code'], 'acc_id': r['acc_id'], 'name': r['name'],
         'phone': r['phone'] or '', 'grp': r['grp'] or '', 'points': r['points'],
         'status': r['status'], 'src': r['src'] or 'online', 'created': r['created'],
         'done_at': r['done_at'] or '', 'operator': r['operator'] or '', 'note': r['note'] or ''}
    if with_items:
        its = conn.execute("SELECT gid,gname,icon,qty,points FROM jf_order_items WHERE order_id=?",
                           (r['id'],)).fetchall()
        d['items'] = [{'gid': x['gid'], 'name': x['gname'], 'icon': x['icon'] or '🎁',
                       'qty': x['qty'], 'points': x['points']} for x in its]
        d['items_text'] = '、'.join('%s×%d' % (x['gname'], x['qty']) for x in its)
    return d


# ---------------------------------------------------------------- 兑换核心
class BizError(Exception):
    pass


def _do_redeem(conn, acc_id, items, src='online', note='', operator=''):
    """在一个事务里完成：校验 → 扣分 → 减库存 → 生成订单 + 流水"""
    acc = conn.execute("SELECT * FROM jf_accounts WHERE id=?", (acc_id,)).fetchone()
    if not acc:
        raise BizError('积分账户不存在')
    if (acc['status'] or '正常') != '正常':
        raise BizError('该账户状态为「%s」，暂不能兑换' % acc['status'])

    norm = []
    total = 0
    for it in items or []:
        gid = _s(it.get('gid'))
        qty = _int(it.get('qty'), 0)
        if not gid or qty <= 0:
            continue
        if qty > MAX_QTY:
            raise BizError('单件商品一次最多兑换 %d 件' % MAX_QTY)
        g = conn.execute("SELECT * FROM jf_goods WHERE id=?", (gid,)).fetchone()
        if not g:
            raise BizError('商品不存在或已下架')
        if (g['status'] or '') != '上架':
            raise BizError('「%s」已下架' % g['name'])
        if (g['stock'] or 0) < qty:
            raise BizError('「%s」库存不足（剩 %d 件）' % (g['name'], g['stock'] or 0))
        if (g['limit_per'] or 0) > 0:
            done = conn.execute(
                "SELECT COALESCE(SUM(oi.qty),0) q FROM jf_order_items oi "
                "JOIN jf_orders o ON o.id = oi.order_id "
                "WHERE oi.gid=? AND o.acc_id=? AND o.status <> '已取消'", (gid, acc_id)).fetchone()['q']
            if done + qty > g['limit_per']:
                raise BizError('「%s」每人限兑 %d 件，已兑 %d 件' % (g['name'], g['limit_per'], done))
        sub = g['points'] * qty
        total += sub
        norm.append({'gid': gid, 'name': g['name'], 'icon': g['icon'] or '🎁',
                     'qty': qty, 'points': g['points'], 'sub': sub})
    if not norm:
        raise BizError('请选择要兑换的商品')
    if total > (acc['points'] or 0):
        raise BizError('积分不足：需 %d 分，当前 %d 分' % (total, acc['points'] or 0))

    code = None
    for _ in range(20):
        c = str(secrets.randbelow(900000) + 100000)
        if not conn.execute("SELECT 1 FROM jf_orders WHERE code=?", (c,)).fetchone():
            code = c
            break
    if not code:
        raise BizError('取货码生成失败，请重试')

    oid = _uid('o_')
    now = _now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        # 条件更新，防止并发超兑
        cur = conn.execute(
            "UPDATE jf_accounts SET points = points - ?, spent = spent + ?, updated=? "
            "WHERE id=? AND points >= ?", (total, total, now, acc_id, total))
        if cur.rowcount != 1:
            raise BizError('积分不足，请刷新后重试')
        for it in norm:
            cur = conn.execute(
                "UPDATE jf_goods SET stock = stock - ?, sold = sold + ?, updated=? "
                "WHERE id=? AND stock >= ?", (it['qty'], it['qty'], now, it['gid'], it['qty']))
            if cur.rowcount != 1:
                raise BizError('「%s」库存不足，请刷新后重试' % it['name'])
            conn.execute("INSERT INTO jf_order_items(id,order_id,gid,gname,icon,qty,points) VALUES(?,?,?,?,?,?,?)",
                         (_uid('oi_'), oid, it['gid'], it['name'], it['icon'], it['qty'], it['points']))
        bal = conn.execute("SELECT points FROM jf_accounts WHERE id=?", (acc_id,)).fetchone()['points']
        conn.execute(
            "INSERT INTO jf_orders(id,code,acc_id,name,phone,grp,points,status,src,items,created,operator,note)"
            " VALUES(?,?,?,?,?,?,?,'待领取',?,?,?,?,?)",
            (oid, code, acc_id, acc['name'], acc['phone'] or '', acc['grp'] or '', total, src,
             json.dumps(norm, ensure_ascii=False), now, operator, note))
        conn.execute(
            "INSERT INTO jf_txns(id,acc_id,name,grp,kind,points,balance,reason,ref,operator,created)"
            " VALUES(?,?,?,?,'spend',?,?,?,?,?,?)",
            (_uid('t_'), acc_id, acc['name'], acc['grp'] or '', -total, bal,
             '兑换：' + '、'.join('%s×%d' % (i['name'], i['qty']) for i in norm),
             code, operator or '村民自助', now))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {'id': oid, 'code': code, 'points': total, 'balance': bal,
            'items': norm, 'status': '待领取', 'created': now}


def _add_points(conn, acc_id, pts, reason, kind='earn', operator='', ref=''):
    """发放/扣减积分（pts 为实数，正负均可）"""
    acc = conn.execute("SELECT * FROM jf_accounts WHERE id=?", (acc_id,)).fetchone()
    if not acc:
        raise BizError('账户不存在')
    now = _now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        cur = conn.execute(
            "UPDATE jf_accounts SET points = points + ?, earned = earned + ?, updated=? WHERE id=?",
            (pts, max(pts, 0), now, acc_id)) if pts >= 0 else conn.execute(
            "UPDATE jf_accounts SET points = points + ?, spent = spent + ?, updated=? WHERE id=? AND points + ? >= 0",
            (pts, -pts, now, acc_id, pts))
        if cur.rowcount != 1:
            raise BizError('积分不足，无法扣减')
        bal = conn.execute("SELECT points FROM jf_accounts WHERE id=?", (acc_id,)).fetchone()['points']
        conn.execute(
            "INSERT INTO jf_txns(id,acc_id,name,grp,kind,points,balance,reason,ref,operator,created)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (_uid('t_'), acc_id, acc['name'], acc['grp'] or '', kind, pts, bal, reason, ref, operator, now))
        conn.commit()
        return bal
    except Exception:
        conn.rollback()
        raise


def _cancel_order(conn, oid, operator=''):
    r = conn.execute("SELECT * FROM jf_orders WHERE id=?", (oid,)).fetchone()
    if not r:
        raise BizError('兑换单不存在')
    if r['status'] != '待领取':
        raise BizError('只有「待领取」的单可以取消')
    its = conn.execute("SELECT * FROM jf_order_items WHERE order_id=?", (oid,)).fetchall()
    now = _now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("UPDATE jf_orders SET status='已取消', done_at=?, operator=? WHERE id=?", (now, operator, oid))
        for it in its:
            conn.execute("UPDATE jf_goods SET stock = stock + ?, sold = MAX(sold - ?, 0) WHERE id=?",
                         (it['qty'], it['qty'], it['gid']))
        conn.execute("UPDATE jf_accounts SET points = points + ?, spent = MAX(spent - ?, 0), updated=? WHERE id=?",
                     (r['points'], r['points'], now, r['acc_id']))
        bal = conn.execute("SELECT points FROM jf_accounts WHERE id=?", (r['acc_id'],)).fetchone()['points']
        conn.execute(
            "INSERT INTO jf_txns(id,acc_id,name,grp,kind,points,balance,reason,ref,operator,created)"
            " VALUES(?,?,?,?,'refund',?,?,?,?,?,?)",
            (_uid('t_'), r['acc_id'], r['name'], r['grp'] or '', r['points'], bal,
             '兑换取消退回（单号 %s）' % r['code'], r['code'], operator, now))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return True


# ---------------------------------------------------------------- 请求辅助
def _q(handler):
    return urllib.parse.parse_qs(urllib.parse.urlsplit(handler.path).query)


def _qv(handler, k, d=''):
    v = _q(handler).get(k)
    return v[0] if v else d


def _body(handler):
    n = _int(handler.headers.get('Content-Length') or 0, 0)
    if n <= 0:
        return {}
    raw = handler.rfile.read(n).decode('utf-8', 'replace')
    return json.loads(raw) if raw.strip() else {}


def _ok(handler, **kw):
    d = {'success': True}
    d.update(kw)
    handler.send_json(200, d)


def _err(handler, msg, code=400):
    handler.send_json(code, {'success': False, 'error': str(msg)})


def _is_editor(handler):
    u = getattr(handler, '_auth', None)
    return bool(u and u.get('role') in ('admin', 'editor'))


def _is_admin(handler):
    u = getattr(handler, '_auth', None)
    return bool(u and u.get('role') == 'admin')


def _require_admin(handler):
    if _is_admin(handler):
        return True
    _err(handler, '备份恢复需要管理员权限', 403)
    return False


def _require_editor(handler):
    if _is_editor(handler):
        return True
    _err(handler, '需要管理员或编辑员权限', 403)
    return False


def _json_out(handler, name, obj):
    """以附件形式下发 JSON（备份文件）"""
    data = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Disposition',
                        "attachment; filename*=UTF-8''" + urllib.parse.quote(name))
    handler.send_header('Content-Length', str(len(data)))
    handler.send_header('Cache-Control', 'no-store')
    handler.end_headers()
    handler.wfile.write(data)


def _csv_out(handler, name, header, rows):
    buf = io.StringIO()
    buf.write('\ufeff')
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow(['\'%s' % c if str(c)[:1] in ('=', '+', '-', '@') else c for c in r])
    data = buf.getvalue().encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type', 'text/csv; charset=utf-8')
    handler.send_header('Content-Disposition',
                        "attachment; filename*=UTF-8''" + urllib.parse.quote(name))
    handler.send_header('Content-Length', str(len(data)))
    handler.send_header('Cache-Control', 'no-store')
    handler.end_headers()
    handler.wfile.write(data)


# ---------------------------------------------------------------- GET
def handle_get(handler, p):
    q = _q(handler)
    conn = _conn()
    try:
        if p == '/api/jifen/config':
            return _ok(handler, settings=_settings(conn), rules=_rules(conn),
                       cats=sorted({g['cat'] for g in _goods(conn)}),
                       stats=_stats(conn), groups=_group_list(conn))
        if p == '/api/jifen/goods':
            return _ok(handler, goods=_goods(conn), settings=_settings(conn))
        if p == '/api/jifen/rank':
            return _ok(handler, rank=_rank(conn, _int(_qv(handler, 'n', '20'), 20)))
        if p == '/api/jifen/rank_hu':
            _sync_hu(conn)
            return _ok(handler, rank=_rank_hu(conn, _int(_qv(handler, 'n', '20'), 20)))
        if p == '/api/jifen/cases':
            kind = _s(_qv(handler, 'kind'))
            st = _settings(conn)
            return _ok(handler, cases=_cases(conn, kind, admin=False,
                                             limit=min(200, _int(_qv(handler, 'n', '60'), 60))),
                       settings={'case_intro': st.get('case_intro', ''),
                                 'case_black_mask': st.get('case_black_mask', '1')})
        if p == '/api/jifen/me':
            acc_id = _token_acc(_qv(handler, 'token'))
            if not acc_id:
                return _err(handler, '查询已过期', 401)
            row = conn.execute("SELECT * FROM jf_accounts WHERE id=?", (acc_id,)).fetchone()
            if not row:
                return _err(handler, '账户不存在', 404)
            tx = conn.execute("SELECT * FROM jf_txns WHERE acc_id=? ORDER BY created DESC LIMIT 8",
                              (acc_id,)).fetchall()
            od = conn.execute("SELECT * FROM jf_orders WHERE acc_id=? AND status='待领取' ORDER BY created DESC LIMIT 5",
                              (acc_id,)).fetchall()
            acc = _acc_public(row)
            acc['code'] = str(row['code'] or '')
            return _ok(handler, account=acc,
                       txns=[_txn_json(r) for r in tx], pending=[_order_json(conn, r) for r in od])
        if p == '/api/jifen/myorders':
            acc_id = _token_acc(_qv(handler, 'token'))
            if not acc_id:
                return _err(handler, '查询已过期，请重新输入姓名和手机号', 401)
            rows = conn.execute("SELECT * FROM jf_orders WHERE acc_id=? ORDER BY created DESC LIMIT 50",
                                (acc_id,)).fetchall()
            return _ok(handler, orders=[_order_json(conn, r) for r in rows])

        # ---------- 管理端 ----------
        if p == '/api/jifen/admin/overview':
            if not _require_editor(handler):
                return
            return _ok(handler, stats=_stats(conn), recent=_recent_orders(conn, 8),
                       low_stock=[g for g in _goods(conn, True) if g['stock'] <= 5][:8])
        if p == '/api/jifen/admin/stat':
            if not _require_editor(handler):
                return
            dfrom, dto = _date_range(handler, _int(_qv(handler, 'days', '30'), 30))
            return _ok(handler, **_dash(conn, dfrom, dto))
        if p == '/api/jifen/admin/health':
            if not _require_editor(handler):
                return
            return _ok(handler, **_health(conn))
        if p == '/api/jifen/admin/backup':
            if not _require_admin(handler):
                return
            name = _s(_qv(handler, 'name'), 120)
            if name:
                try:
                    d = _load_backup_file(name)
                except BizError as e:
                    return _err(handler, str(e), 404)
                except Exception as e:
                    return _err(handler, '备份文件读取失败：%s' % e, 500)
                return _json_out(handler, os.path.basename(name), d)
            d = _dump(conn)
            return _json_out(handler, '积分超市备份_%s.json' % time.strftime('%Y%m%d_%H%M%S'), d)
        if p == '/api/jifen/admin/backups':
            if not _require_admin(handler):
                return
            return _ok(handler, backups=_backup_list(),
                       tip='备份文件保存在服务器 backups/jf/ 目录，常规备份保留最近 %d 份' % BACKUP_KEEP)
        if p == '/api/jifen/admin/goods':
            if not _require_editor(handler):
                return
            return _ok(handler, goods=_goods(conn, True))
        if p == '/api/jifen/admin/accounts':
            if not _require_editor(handler):
                return
            kw = _s(_qv(handler, 'kw'))
            page = max(1, _int(_qv(handler, 'page', '1'), 1))
            size = min(200, max(5, _int(_qv(handler, 'size', str(PAGE_SIZE)), PAGE_SIZE)))
            where, args = [], []
            if kw:
                where.append("(name LIKE ? OR phone LIKE ? OR grp LIKE ? OR idcard LIKE ? OR code LIKE ?"
                             " OR hu LIKE ? OR hu_zhu LIKE ?)")
                args += ['%' + kw + '%'] * 7
            w = ('WHERE ' + ' AND '.join(where)) if where else ''
            total = conn.execute("SELECT COUNT(*) c FROM jf_accounts " + w, args).fetchone()['c']
            rows = conn.execute("SELECT * FROM jf_accounts " + w + " ORDER BY points DESC, name LIMIT ? OFFSET ?",
                                args + [size, (page - 1) * size]).fetchall()
            return _ok(handler, total=total, page=page, size=size,
                       accounts=[_acc_admin(r) for r in rows])
        if p == '/api/jifen/admin/houses':
            if not _require_editor(handler):
                return
            _sync_hu(conn)
            kw = _s(_qv(handler, 'kw'))
            page = max(1, _int(_qv(handler, 'page', '1'), 1))
            size = min(200, max(5, _int(_qv(handler, 'size', str(PAGE_SIZE)), PAGE_SIZE)))
            total, houses = _house_list(conn, kw, page, size)
            return _ok(handler, total=total, page=page, size=size, houses=houses,
                       unhoused=_unhoused(conn))
        if p == '/api/jifen/admin/hu_review':
            if not _require_editor(handler):
                return
            _sync_hu(conn)
            d = _hu_review(conn, min(500, max(20, _int(_qv(handler, 'n', '200'), 200))))
            return _ok(handler, **d)
        if p == '/api/jifen/admin/house':
            if not _require_editor(handler):
                return
            hu = _qv(handler, 'hu')
            d = _house_detail(conn, hu) if hu else None
            if not d:
                return _err(handler, '未找到该户的积分账户', 404)
            return _ok(handler, house=d)
        if p == '/api/jifen/admin/orders':
            if not _require_editor(handler):
                return
            st = _s(_qv(handler, 'status'))
            kw = _s(_qv(handler, 'kw'))
            page = max(1, _int(_qv(handler, 'page', '1'), 1))
            size = min(200, max(5, _int(_qv(handler, 'size', '20'), 20)))
            where, args = [], []
            if st and st != '全部':
                where.append("status=?"); args.append(st)
            if kw:
                where.append("(name LIKE ? OR code LIKE ? OR phone LIKE ?)")
                args += ['%' + kw + '%'] * 3
            w = ('WHERE ' + ' AND '.join(where)) if where else ''
            total = conn.execute("SELECT COUNT(*) c FROM jf_orders " + w, args).fetchone()['c']
            rows = conn.execute("SELECT * FROM jf_orders " + w +
                                " ORDER BY CASE status WHEN '待领取' THEN 0 ELSE 1 END, created DESC LIMIT ? OFFSET ?",
                                args + [size, (page - 1) * size]).fetchall()
            return _ok(handler, total=total, page=page, size=size,
                       orders=[_order_json(conn, r) for r in rows])
        if p == '/api/jifen/admin/txns':
            if not _require_editor(handler):
                return
            kw = _s(_qv(handler, 'kw'))
            page = max(1, _int(_qv(handler, 'page', '1'), 1))
            size = min(200, max(5, _int(_qv(handler, 'size', '20'), 20)))
            where, args = [], []
            if kw:
                where.append("(name LIKE ? OR reason LIKE ? OR ref LIKE ?)")
                args += ['%' + kw + '%'] * 3
            w = ('WHERE ' + ' AND '.join(where)) if where else ''
            total = conn.execute("SELECT COUNT(*) c FROM jf_txns " + w, args).fetchone()['c']
            rows = conn.execute("SELECT * FROM jf_txns " + w + " ORDER BY created DESC LIMIT ? OFFSET ?",
                                args + [size, (page - 1) * size]).fetchall()
            return _ok(handler, total=total, page=page, size=size,
                       txns=[_txn_json(r) for r in rows])
        if p == '/api/jifen/admin/rules':
            if not _require_editor(handler):
                return
            return _ok(handler, rules=_rules(conn, True))
        if p == '/api/jifen/admin/cases':
            if not _require_editor(handler):
                return
            return _ok(handler, cases=_cases(conn, _s(_qv(handler, 'kind')), admin=True, limit=200))
        if p == '/api/jifen/admin/cards':
            # 积分登录卡：姓名 / 组别 / 6 位积分码，导出后可直接打印发给村民
            if not _require_editor(handler):
                return
            kw = _s(_qv(handler, 'kw'))
            where, args = [], []
            if kw:
                where.append("(name LIKE ? OR grp LIKE ? OR code LIKE ?)")
                args += ['%' + kw + '%'] * 3
            w = ('WHERE ' + ' AND '.join(where)) if where else ''
            rows = conn.execute("SELECT name, grp, phone, code FROM jf_accounts " + w +
                                " ORDER BY grp, name", args).fetchall()
            out = []
            for i, r in enumerate(rows, 1):
                out.append([i, r['name'], r['grp'] or '', r['code'] or '', r['phone'] or '',
                            '有手机号' if r['phone'] else ('用积分码' if r['code'] else '缺凭证')])
            return _csv_out(handler, '积分登录卡_%s.csv' % time.strftime('%Y%m%d'),
                            ['序号', '姓名', '村民组', '积分码', '手机号', '登录方式'], out)
        if p == '/api/jifen/admin/export':
            if not _require_editor(handler):
                return
            kind = _qv(handler, 'type', 'txns')
            # 可选日期区间（不传 = 全部）
            dfrom = _s(_qv(handler, 'from'), 10)
            dto = _s(_qv(handler, 'to'), 10)
            use_rng = bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', dfrom or '')
                           and re.fullmatch(r'\d{4}-\d{2}-\d{2}', dto or ''))
            if use_rng and dfrom > dto:
                dfrom, dto = dto, dfrom
            rng = (dfrom + ' 00:00:00', dto + ' 23:59:59') if use_rng else ()
            tag = ('_%s至%s' % (dfrom.replace('-', ''), dto.replace('-', ''))) if use_rng else ''
            stamp = time.strftime('%Y%m%d')

            if kind == 'summary':
                df, dt = (dfrom, dto) if use_rng else (datetime.date.today().isoformat(),
                                                       datetime.date.today().isoformat())
                if not use_rng:
                    # 无区间时：以全部历史汇总（区间取最早流水日 → 今天）
                    first = conn.execute("SELECT MIN(substr(created,1,10)) d FROM jf_txns").fetchone()['d']
                    df = first or dt
                k = _dash(conn, df, dt, with_daily=False)['kpi']
                body = [
                    ['统计区间', '%s 至 %s' % (df, dt)],
                    ['积分账户数（个）', k['acc_n']],
                    ['按户统计户数（户）', k['house_n']],
                    ['未归户账户（个）', k['unhoused']],
                    ['有积分记录人数（人）', k['act_n']],
                    ['积分覆盖率（%）', k['cover']],
                    ['当前积分余额（分）', k['points']],
                    ['累计发放积分（分）', k['earned_all']],
                    ['累计兑换积分（分）', k['spent_all']],
                    ['户均积分（分）', k['house_avg']],
                    ['区间新增积分（分）', k['earn']],
                    ['区间兑换扣减（分）', k['spend']],
                    ['区间流水笔数（笔）', k['txn_n']],
                    ['区间兑换单数（笔）', k['order_n']],
                    ['区间已核销（笔）', k['order_done']],
                    ['区间待领取（笔）', k['order_pend']],
                    ['区间已取消（笔）', k['order_cancel']],
                    ['核销率（%）', k['rate']],
                    ['今日新增积分（分）', k['today_earn']],
                    ['今日兑换单（笔）', k['today_orders']],
                ]
                return _csv_out(handler, '积分超市汇总%s_%s.csv' % (tag, stamp), ['指标', '数值'], body)

            if kind == 'daily':
                df, dt = (dfrom, dto) if use_rng else (
                    (conn.execute("SELECT MIN(substr(created,1,10)) d FROM jf_txns").fetchone()['d']
                     or datetime.date.today().isoformat()), datetime.date.today().isoformat())
                daily = _dash(conn, df, dt)['daily']
                return _csv_out(handler, '积分按日汇总%s_%s.csv' % (tag, stamp),
                                ['日期', '新增积分', '兑换扣减', '流水笔数', '兑换单数'],
                                [[x['d'], x['earn'], x['spend'], x['txn'], x['orders']] for x in daily])

            if kind == 'groups':
                grp = _dash(conn, dfrom if use_rng else '2000-01-01',
                            dto if use_rng else datetime.date.today().isoformat(),
                            with_daily=False)['grp']
                return _csv_out(handler, '积分按组汇总%s_%s.csv' % (tag, stamp),
                                ['村民组', '账户数', '户数', '当前积分', '累计获得', '累计兑换', '有积分人数'],
                                [[g['name'], g['acc'], g['hu'], g['points'], g['earned'],
                                  g['spent'], g['act']] for g in grp])

            if kind == 'goods':
                w = " WHERE o.created BETWEEN ? AND ? AND o.status<>'已取消'" if use_rng else \
                    " WHERE o.status<>'已取消'"
                rows = conn.execute(
                    "SELECT i.gname, COALESCE(g.cat,'其他') cat, COALESCE(SUM(i.qty),0) qty,"
                    " COALESCE(SUM(i.qty*i.points),0) pts, COUNT(DISTINCT i.order_id) orders"
                    " FROM jf_order_items i JOIN jf_orders o ON o.id=i.order_id"
                    " LEFT JOIN jf_goods g ON g.id=i.gid" + w +
                    " GROUP BY i.gname ORDER BY qty DESC, pts DESC", rng).fetchall()
                return _csv_out(handler, '积分商品兑换汇总%s_%s.csv' % (tag, stamp),
                                ['商品', '分类', '兑换数量', '消耗积分', '兑换单数'],
                                [[r['gname'], r['cat'], r['qty'], r['pts'], r['orders']] for r in rows])

            if kind == 'houses':
                _sync_hu(conn)
                total, houses = _house_list(conn, '', 1, 100000)
                return _csv_out(handler, '积分户表%s_%s.csv' % (tag, stamp),
                                ['户主（推定）', '村民组', '户籍地址', '在册人数', '户积分', '户累计获得', '户累计兑换', '有积分人数'],
                                [[h['zhu'], h['grp'], h['addr'], h['members'], h['points'],
                                  h['earned'], h['spent'], h['act']] for h in houses])
            if kind == 'orders':
                w = " WHERE created BETWEEN ? AND ?" if use_rng else ""
                rows = conn.execute("SELECT * FROM jf_orders" + w + " ORDER BY created DESC", rng).fetchall()
                data = [[r['code'], r['name'], r['grp'], r['phone'], _order_json(conn, r)['items_text'],
                         r['points'], r['status'], r['src'], r['created'], r['done_at'], r['operator']]
                        for r in rows]
                return _csv_out(handler, '积分兑换单%s_%s.csv' % (tag, stamp),
                                ['取货码', '姓名', '组别', '电话', '兑换物品', '扣减积分', '状态', '来源', '下单时间', '领取时间', '经办人'], data)
            if kind == 'accounts':
                rows = conn.execute("SELECT * FROM jf_accounts ORDER BY points DESC").fetchall()
                return _csv_out(handler, '积分账户_%s.csv' % stamp,
                                ['姓名', '组别', '电话', '身份证', '当前积分', '累计获得', '累计兑换', '状态', '备注'],
                                [[r['name'], r['grp'], r['phone'], r['idcard'], r['points'], r['earned'],
                                  r['spent'], r['status'], r['note']] for r in rows])
            if kind == 'cases':
                rows = conn.execute("SELECT * FROM jf_cases ORDER BY kind, sort DESC, happen DESC").fetchall()
                return _csv_out(handler, '积分红黑榜案例_%s.csv' % stamp,
                                ['榜单', '标题', '对象', '村民组', '分值', '公示日期', '说明', '状态', '排序'],
                                [['红榜' if r['kind'] == 'red' else '黑榜', r['title'], r['who'],
                                  r['grp'], r['points'], r['happen'], r['desc'], r['status'], r['sort']]
                                 for r in rows])
            w = " WHERE created BETWEEN ? AND ?" if use_rng else ""
            rows = conn.execute("SELECT * FROM jf_txns" + w + " ORDER BY created DESC", rng).fetchall()
            return _csv_out(handler, '积分流水%s_%s.csv' % (tag, stamp),
                            ['时间', '姓名', '组别', '类型', '变动', '余额', '事由', '单号', '经办人'],
                            [[r['created'], r['name'], r['grp'],
                              {'earn': '获得', 'spend': '兑换', 'adjust': '调整', 'refund': '退回'}.get(r['kind'], r['kind']),
                              r['points'], r['balance'], r['reason'], r['ref'], r['operator']] for r in rows])
        return _err(handler, '接口不存在', 404)
    finally:
        conn.close()


def _stats(conn):
    a = conn.execute("SELECT COUNT(*) c, COALESCE(SUM(points),0) p, COALESCE(SUM(earned),0) e, "
                     "COALESCE(SUM(spent),0) s FROM jf_accounts WHERE status='正常'").fetchone()
    o = conn.execute("SELECT COUNT(*) c, COALESCE(SUM(points),0) p FROM jf_orders WHERE status<>'已取消'").fetchone()
    pend = conn.execute("SELECT COUNT(*) c FROM jf_orders WHERE status='待领取'").fetchone()['c']
    today = time.strftime('%Y-%m-%d')
    t_o = conn.execute("SELECT COUNT(*) c FROM jf_orders WHERE created LIKE ? AND status<>'已取消'",
                       (today + '%',)).fetchone()['c']
    t_t = conn.execute("SELECT COALESCE(SUM(points),0) p FROM jf_txns WHERE created LIKE ? AND points>0",
                       (today + '%',)).fetchone()['p']
    g = conn.execute("SELECT COUNT(*) c, COALESCE(SUM(stock),0) s FROM jf_goods WHERE status='上架'").fetchone()
    ph = conn.execute("SELECT COUNT(*) c FROM jf_accounts WHERE status='正常' AND phone<>''").fetchone()['c']
    hu_n = conn.execute("SELECT COUNT(DISTINCT hu) c FROM jf_accounts WHERE status='正常' AND hu<>''").fetchone()['c']
    return {
        'acc_n': a['c'], 'acc_phone': ph, 'house_n': hu_n,
        'acc_points': a['p'], 'earned_total': a['e'], 'spent_total': a['s'],
        'order_n': o['c'], 'redeem_points': o['p'], 'pending': pend,
        'today_orders': t_o, 'today_earn': t_t,
        'goods_n': g['c'], 'stock_total': g['s'],
        'market': _settings(conn).get('market_name', ''),
    }


def _recent_orders(conn, n=8):
    rows = conn.execute("SELECT * FROM jf_orders ORDER BY created DESC LIMIT ?", (n,)).fetchall()
    return [_order_json(conn, r) for r in rows]


# ---------------------------------------------------------------- 统计分析 / 数据大屏
def _date_range(handler, default_days=30):
    """解析 from/to（YYYY-MM-DD），缺省为「近 N 天」，最多回看 400 天"""
    dfrom = _s(_qv(handler, 'from'), 10)
    dto = _s(_qv(handler, 'to'), 10)
    today = datetime.date.today()
    try:
        end = datetime.date.fromisoformat(dto) if re.fullmatch(r'\d{4}-\d{2}-\d{2}', dto) else today
    except ValueError:
        end = today
    try:
        start = datetime.date.fromisoformat(dfrom) if re.fullmatch(r'\d{4}-\d{2}-\d{2}', dfrom) else None
    except ValueError:
        start = None
    if start is None:
        start = end - datetime.timedelta(days=max(1, default_days) - 1)
    if start > end:
        start, end = end, start
    if (end - start).days > 400:
        start = end - datetime.timedelta(days=400)
    return start.isoformat(), end.isoformat()


def _dash(conn, dfrom, dto, with_daily=True):
    """数据大屏聚合：KPI + 按日趋势 + 组别分布 + 商品/分类排行 + 个人/户榜 + 事由"""
    _sync_hu(conn)
    rng = (dfrom + ' 00:00:00', dto + ' 23:59:59')
    day_n = (datetime.date.fromisoformat(dto) - datetime.date.fromisoformat(dfrom)).days + 1

    a = conn.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(points),0) p, COALESCE(SUM(earned),0) e,"
        " COALESCE(SUM(spent),0) s,"
        " COALESCE(SUM(CASE WHEN earned>0 OR spent>0 THEN 1 ELSE 0 END),0) act,"
        " COALESCE(SUM(CASE WHEN phone<>'' THEN 1 ELSE 0 END),0) ph"
        " FROM jf_accounts WHERE status='正常'").fetchone()
    hu_n = conn.execute("SELECT COUNT(DISTINCT hu) c FROM jf_accounts WHERE status='正常' AND hu<>''").fetchone()['c']
    unhoused = _unhoused(conn)

    t = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN points>0 THEN points ELSE 0 END),0) earn,"
        " COALESCE(SUM(CASE WHEN points<0 THEN -points ELSE 0 END),0) spend,"
        " COUNT(*) n,"
        " COALESCE(SUM(CASE WHEN kind='earn' THEN 1 ELSE 0 END),0) earn_n,"
        " COALESCE(SUM(CASE WHEN kind='spend' THEN 1 ELSE 0 END),0) spend_n"
        " FROM jf_txns WHERE created BETWEEN ? AND ?", rng).fetchone()
    o = conn.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(points),0) p,"
        " COALESCE(SUM(CASE WHEN status='已领取' THEN 1 ELSE 0 END),0) done,"
        " COALESCE(SUM(CASE WHEN status='待领取' THEN 1 ELSE 0 END),0) pend,"
        " COALESCE(SUM(CASE WHEN status='已取消' THEN 1 ELSE 0 END),0) cancel"
        " FROM jf_orders WHERE created BETWEEN ? AND ?", rng).fetchone()
    valid_ord = (o['c'] or 0) - (o['cancel'] or 0)

    today = time.strftime('%Y-%m-%d')
    td = conn.execute("SELECT COALESCE(SUM(CASE WHEN points>0 THEN points ELSE 0 END),0) e FROM jf_txns"
                      " WHERE created LIKE ?", (today + '%',)).fetchone()['e']
    tdo = conn.execute("SELECT COUNT(*) c FROM jf_orders WHERE created LIKE ? AND status<>'已取消'",
                       (today + '%',)).fetchone()['c']

    # ---- 按日趋势 ----
    dm = {}
    for r in conn.execute(
            "SELECT substr(created,1,10) d,"
            " COALESCE(SUM(CASE WHEN points>0 THEN points ELSE 0 END),0) earn,"
            " COALESCE(SUM(CASE WHEN points<0 THEN -points ELSE 0 END),0) spend,"
            " COUNT(*) n FROM jf_txns WHERE created BETWEEN ? AND ? GROUP BY d", rng):
        dm[r['d']] = {'earn': r['earn'], 'spend': r['spend'], 'txn': r['n'], 'orders': 0}
    for r in conn.execute(
            "SELECT substr(created,1,10) d, COUNT(*) c FROM jf_orders"
            " WHERE created BETWEEN ? AND ? AND status<>'已取消' GROUP BY d", rng):
        dm.setdefault(r['d'], {'earn': 0, 'spend': 0, 'txn': 0, 'orders': 0})['orders'] = r['c']
    daily, cur, end_d = [], datetime.date.fromisoformat(dfrom), datetime.date.fromisoformat(dto)
    while with_daily and cur <= end_d:
        k = cur.isoformat()
        x = dm.get(k) or {}
        daily.append({'d': k, 'earn': x.get('earn', 0), 'spend': x.get('spend', 0),
                      'txn': x.get('txn', 0), 'orders': x.get('orders', 0)})
        cur += datetime.timedelta(days=1)

    # ---- 组别分布 ----
    grp, gsum = [], {}
    for r in conn.execute(
            "SELECT grp, COUNT(*) acc, COUNT(DISTINCT CASE WHEN hu<>'' THEN hu END) hu,"
            " COALESCE(SUM(points),0) p, COALESCE(SUM(earned),0) e, COALESCE(SUM(spent),0) s,"
            " COALESCE(SUM(CASE WHEN earned>0 OR spent>0 THEN 1 ELSE 0 END),0) act"
            " FROM jf_accounts WHERE status='正常' GROUP BY grp ORDER BY p DESC"):
        k = _norm_grp(r['grp']) or '未标注'
        g = gsum.setdefault(k, {'name': k, 'acc': 0, 'hu': 0, 'points': 0, 'earned': 0,
                                'spent': 0, 'act': 0})
        g['acc'] += r['acc'] or 0
        g['hu'] += r['hu'] or 0
        g['points'] += r['p'] or 0
        g['earned'] += r['e'] or 0
        g['spent'] += r['s'] or 0
        g['act'] += r['act'] or 0
    grp = sorted(gsum.values(), key=lambda x: -x['points'])

    # ---- 商品 / 分类兑换排行（不含已取消单）----
    goods, cats, cmap = [], [], {}
    for r in conn.execute(
            "SELECT i.gname, COALESCE(g.cat,'其他') cat, COALESCE(SUM(i.qty),0) qty,"
            " COALESCE(SUM(i.qty*i.points),0) pts, COUNT(DISTINCT i.order_id) orders"
            " FROM jf_order_items i JOIN jf_orders o ON o.id=i.order_id"
            " LEFT JOIN jf_goods g ON g.id=i.gid"
            " WHERE o.created BETWEEN ? AND ? AND o.status<>'已取消'"
            " GROUP BY i.gname ORDER BY qty DESC, pts DESC", rng):
        goods.append({'name': r['gname'] or '（已删除商品）', 'cat': r['cat'],
                      'qty': r['qty'], 'points': r['pts'], 'orders': r['orders']})
        c = cmap.setdefault(r['cat'], {'name': r['cat'], 'qty': 0, 'points': 0})
        c['qty'] += r['qty'] or 0
        c['points'] += r['pts'] or 0
    cats = sorted(cmap.values(), key=lambda x: -x['qty'])

    # ---- 加分事由 TOP ----
    reasons = [{'name': r['reason'] or '（未填写事由）', 'n': r['n'], 'points': r['p']}
               for r in conn.execute(
                   "SELECT reason, COUNT(*) n, COALESCE(SUM(points),0) p FROM jf_txns"
                   " WHERE kind='earn' AND points>0 AND created BETWEEN ? AND ?"
                   " GROUP BY reason ORDER BY p DESC, n DESC LIMIT 12", rng)]

    # ---- 个人 / 户 榜（当前积分，附区间获得）----
    earn_map = {r['acc_id']: r['e'] for r in conn.execute(
        "SELECT acc_id, COALESCE(SUM(CASE WHEN points>0 THEN points ELSE 0 END),0) e"
        " FROM jf_txns WHERE created BETWEEN ? AND ? GROUP BY acc_id", rng)}
    top_person = []
    for r in conn.execute(
            "SELECT id, name, grp, points, earned, spent, hu_zhu FROM jf_accounts"
            " WHERE status='正常' AND (points>0 OR earned>0 OR spent>0)"
            " ORDER BY points DESC, earned DESC LIMIT 10"):
        top_person.append({'name': r['name'], 'grp': _norm_grp(r['grp']), 'zhu': r['hu_zhu'] or '',
                           'points': r['points'] or 0, 'earned': r['earned'] or 0,
                           'spent': r['spent'] or 0, 'range': earn_map.get(r['id'], 0)})
    top_house = []
    for r in conn.execute(
            "SELECT hu, MAX(hu_zhu) zhu, MAX(grp) grp, COUNT(*) n, COALESCE(SUM(points),0) p,"
            " COALESCE(SUM(earned),0) e FROM jf_accounts WHERE status='正常' AND hu<>''"
            " GROUP BY hu HAVING SUM(points)>0 ORDER BY p DESC, e DESC LIMIT 10"):
        top_house.append({'zhu': r['zhu'] or '', 'addr': _hu_addr(r['hu']),
                          'grp': _norm_grp(r['grp']), 'members': r['n'],
                          'points': r['p'] or 0, 'earned': r['e'] or 0})

    cover = round(a['act'] * 100.0 / a['c'], 1) if a['c'] else 0
    rate = round((o['done'] or 0) * 100.0 / valid_ord, 1) if valid_ord else 0
    return {
        'range': {'from': dfrom, 'to': dto, 'days': day_n},
        'kpi': {
            'acc_n': a['c'], 'house_n': hu_n, 'unhoused': unhoused,
            'act_n': a['act'], 'cover': cover,
            'points': a['p'], 'earned_all': a['e'], 'spent_all': a['s'],
            'house_avg': round(a['p'] * 1.0 / hu_n, 0) if hu_n else 0,
            'earn': t['earn'], 'spend': t['spend'], 'txn_n': t['n'],
            'earn_n': t['earn_n'], 'spend_n': t['spend_n'],
            'order_n': o['c'], 'order_done': o['done'], 'order_pend': o['pend'],
            'order_cancel': o['cancel'], 'redeem_pts': o['p'], 'rate': rate,
            'today_earn': td, 'today_orders': tdo,
        },
        'daily': daily, 'grp': grp, 'goods': goods[:12], 'cats': cats,
        'reasons': reasons, 'top_person': top_person, 'top_house': top_house,
        'status': {'待领取': o['pend'] or 0, '已领取': o['done'] or 0, '已取消': o['cancel'] or 0},
    }


# ---------------------------------------------------------------- 数据体检
def _health(conn):
    """检查常见的脏数据 / 异常，返回 [{level,title,detail,count}]"""
    items = []

    def add(level, title, detail, count=0):
        items.append({'level': level, 'title': title, 'detail': detail, 'count': count})

    bad_bal = conn.execute(
        "SELECT COUNT(*) c FROM jf_accounts a WHERE a.points <> COALESCE("
        "(SELECT SUM(points) FROM jf_txns t WHERE t.acc_id=a.id),0)").fetchone()['c']
    if bad_bal:
        add('error', '余额与流水不一致', '%d 个账户的当前积分 ≠ 流水合计（多为早期导入时带了初始分）' % bad_bal, bad_bal)
    else:
        add('ok', '余额与流水一致', '所有账户的当前积分均等于流水合计', 0)

    dup_id = conn.execute("SELECT COUNT(*) c FROM (SELECT idcard FROM jf_accounts"
                          " WHERE idcard<>'' GROUP BY idcard HAVING COUNT(*)>1)").fetchone()['c']
    if dup_id:
        add('warn', '身份证重复', '%d 个身份证号被多个账户占用，建议核对后合并' % dup_id, dup_id)
    else:
        add('ok', '身份证无重复', '未发现重复身份证号', 0)

    dup_np = conn.execute("SELECT COUNT(*) c FROM (SELECT name,phone FROM jf_accounts"
                          " WHERE phone<>'' GROUP BY name,phone HAVING COUNT(*)>1)").fetchone()['c']
    if dup_np:
        add('warn', '同名同手机号', '%d 组同名同手机号的账户，查分时可能混淆，建议核对' % dup_np, dup_np)
    else:
        add('ok', '姓名手机号唯一', '未发现同名同手机号的账户', 0)

    noph = conn.execute("SELECT COUNT(*) c FROM jf_accounts WHERE status='正常' AND phone=''").fetchone()['c']
    add('info' if noph else 'ok', '未登记手机号',
        ('%d 名村民没有手机号，无法自助查分（可用身份证后 6 位查询）' % noph) if noph
        else '所有在册村民都有手机号或可用身份证后 6 位查询', noph)

    un = _unhoused(conn)
    add('info' if un else 'ok', '未归户账户',
        ('%d 个账户未匹配到户籍地址（手工新增 / 外嫁 / 外地户），按户统计未包含' % un) if un
        else '全部账户均已按户籍地址归户', un)

    neg = conn.execute("SELECT COUNT(*) c FROM jf_goods WHERE stock<0").fetchone()['c']
    if neg:
        add('error', '商品库存为负', '%d 个商品库存小于 0，请核对出入库' % neg, neg)
    zero = conn.execute("SELECT COUNT(*) c FROM jf_goods WHERE status='上架' AND stock<=0").fetchone()['c']
    add('warn' if zero else 'ok', '上架商品无库存',
        ('%d 个上架商品库存为 0，村民兑换会被拒绝' % zero) if zero else '上架商品均有库存', zero)

    stale = conn.execute("SELECT COUNT(*) c FROM jf_orders WHERE status='待领取'"
                         " AND created < datetime('now','localtime','-7 day')").fetchone()['c']
    add('warn' if stale else 'ok', '超 7 天未领取',
        ('%d 笔兑换单超过 7 天仍未领取，建议提醒村民或取消退分' % stale) if stale
        else '没有长期未领取的兑换单', stale)

    miss_img = 0
    for r in conn.execute("SELECT img FROM jf_cases WHERE img<>''"):
        u = str(r['img'] or '')
        p = os.path.join(DATA_DIR, u.lstrip('/').replace('/', os.sep))
        if not os.path.exists(p):
            miss_img += 1
    add('warn' if miss_img else 'ok', '红黑榜图片',
        ('%d 张案例图片文件缺失，村民端会显示占位' % miss_img) if miss_img else '案例图片均存在', miss_img)

    ncase = conn.execute("SELECT COUNT(*) c FROM jf_cases").fetchone()['c']
    add('info' if ncase else 'info', '红黑榜案例', '当前共 %d 条案例（含下架）' % ncase, ncase)
    return {'items': items, 'ts': _now()}


# ---------------------------------------------------------------- 备份 / 恢复
JF_TABLES = ['jf_accounts', 'jf_txns', 'jf_goods', 'jf_orders', 'jf_order_items',
             'jf_rules', 'jf_settings', 'jf_cases']
BACKUP_KEEP = 20          # 常规备份保留份数
PRE_RESTORE_KEEP = 10     # 恢复前自动存档保留份数


def _dump(conn):
    """导出积分模块全量数据（按列名存，便于跨版本恢复）"""
    d = {'app': 'village-jifen', 'version': 1, 'ts': _now(), 'tables': {}}
    for t in JF_TABLES:
        cols = [r[1] for r in conn.execute('PRAGMA table_info(%s)' % t)]
        rows = conn.execute('SELECT * FROM %s' % t).fetchall()
        d['tables'][t] = {'cols': cols, 'rows': [list(r) for r in rows]}
    d['counts'] = {t: len(d['tables'][t]['rows']) for t in JF_TABLES}
    return d


def _restore(conn, data, mode='replace'):
    """从备份对象恢复。mode=replace 覆盖（先清空），merge 合并（同主键覆盖）"""
    if not isinstance(data, dict) or not isinstance(data.get('tables'), dict):
        raise BizError('备份文件格式不正确（缺少 tables 字段）')
    tabs = data['tables']
    if mode not in ('replace', 'merge'):
        mode = 'replace'
    stats = {}
    conn.execute('BEGIN IMMEDIATE')
    try:
        if mode == 'replace':
            for t in reversed(JF_TABLES):
                conn.execute('DELETE FROM %s' % t)
        for t in JF_TABLES:
            info = tabs.get(t) or {}
            cols = list(info.get('cols') or [])
            rows = list(info.get('rows') or [])
            real = [r[1] for r in conn.execute('PRAGMA table_info(%s)' % t)]
            use = [c for c in cols if c in real]
            if not use or not rows:
                stats[t] = 0
                continue
            idx = [cols.index(c) for c in use]
            sql = 'INSERT OR REPLACE INTO %s(%s) VALUES(%s)' % (
                t, ','.join(use), ','.join('?' * len(use)))
            payload = []
            for row in rows:
                try:
                    payload.append([row[i] for i in idx])
                except Exception:
                    continue
            conn.executemany(sql, payload)
            stats[t] = len(payload)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    _HU_SYNC['ts'] = 0
    return stats


def _backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    return BACKUP_DIR


def _backup_write(conn, prefix='jf_backup'):
    d = _dump(conn)
    name = '%s_%s.json' % (prefix, time.strftime('%Y%m%d_%H%M%S'))
    path = os.path.join(_backup_dir(), name)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(d, fh, ensure_ascii=False, separators=(',', ':'))
    os.replace(tmp, path)
    _backup_prune()
    return name, d


def _backup_prune():
    try:
        files = sorted((f for f in os.listdir(BACKUP_DIR) if f.endswith('.json')), reverse=True)
    except OSError:
        return
    for pref, keep in (('jf_backup_', BACKUP_KEEP), ('jf_pre_restore_', PRE_RESTORE_KEEP)):
        same = [f for f in files if f.startswith(pref)]
        for f in same[keep:]:
            try:
                os.remove(os.path.join(BACKUP_DIR, f))
            except OSError:
                pass


def _backup_list():
    out = []
    try:
        names = sorted(os.listdir(BACKUP_DIR), reverse=True)
    except OSError:
        return out
    for f in names:
        if not f.endswith('.json'):
            continue
        p = os.path.join(BACKUP_DIR, f)
        try:
            st = os.stat(p)
        except OSError:
            continue
        item = {'name': f, 'size': st.st_size, 'mtime': time.strftime('%Y-%m-%d %H:%M:%S',
                                                                     time.localtime(st.st_mtime)),
                'counts': {}, 'ts': ''}
        # 只读前 4KB 不现实（counts 在文件尾），文件通常 <2MB，直接解析
        try:
            with open(p, 'r', encoding='utf-8') as fh:
                d = json.load(fh)
            item['counts'] = d.get('counts') or {}
            item['ts'] = d.get('ts') or ''
            item['summary'] = '账户 %d · 流水 %d · 兑换单 %d · 案例 %d' % (
                item['counts'].get('jf_accounts', 0), item['counts'].get('jf_txns', 0),
                item['counts'].get('jf_orders', 0), item['counts'].get('jf_cases', 0))
        except Exception:
            item['summary'] = '文件读取失败'
        out.append(item)
    return out[:60]


def _load_backup_file(name):
    name = os.path.basename(str(name or ''))
    if not name.endswith('.json') or '/' in name or '\\' in name:
        raise BizError('备份文件名不合法')
    path = os.path.join(BACKUP_DIR, name)
    if not os.path.isfile(path):
        raise BizError('备份文件不存在')
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)


# ---------------------------------------------------------------- POST
def handle_post(handler, p):
    try:
        body = _body(handler)
    except Exception:
        return _err(handler, '请求格式错误')
    conn = _conn()
    try:
        # ---------- 公开：查积分 ----------
        if p == '/api/jifen/lookup':
            ip = client_ip(handler)
            if _lookup_locked(ip):
                return _err(handler, '尝试次数过多，请 5 分钟后再试，或直接到村委会查询', 429)
            name = _s(body.get('name'), 40)
            cred = _s(body.get('phone') or body.get('cred'), 20).replace(' ', '').upper()
            grp_in = _s(body.get('grp'), 40)
            if not name:
                return _err(handler, '请输入姓名')
            # 三种凭证：11 位手机号 / 身份证后 6 位 / 6 位积分码（村委会发放）
            if re.fullmatch(r'1\d{10}', cred):
                what = '手机号'
            elif re.fullmatch(r'[\dX]{6}', cred):
                what = '身份证后 6 位或积分码'
            else:
                return _err(handler, '请输入 11 位手机号、身份证后 6 位，或村委会发放的 6 位积分码')
            rows = conn.execute("SELECT * FROM jf_accounts WHERE name=? AND status='正常'",
                                (name,)).fetchall()
            if re.fullmatch(r'1\d{10}', cred):
                hit = [r for r in rows if str(r['phone'] or '') == cred]
            else:
                hit = [r for r in rows if str(r['idcard'] or '').upper().endswith(cred)
                       or str(r['code'] or '').upper() == cred]
            if grp_in:
                g = _norm_grp(grp_in)
                hit = [r for r in hit if _norm_grp(r['grp'] or '') == g]
            if not hit:
                _lookup_fail(ip)
                if rows and not grp_in:
                    return _err(handler, '姓名查到了，但%s对不上。可换身份证后 6 位 / 积分码再试，'
                                         '或到村委会核对登记信息' % what, 404)
                return _err(handler, '未查到该姓名与%s匹配的积分账户，请到村委会核对登记信息' % what, 404)
            if len(hit) > 1:
                groups = sorted({_norm_grp(r['grp'] or '') for r in hit})
                if len(groups) > 1:
                    cands = []
                    for g in groups:
                        sub = [r for r in hit if _norm_grp(r['grp'] or '') == g]
                        cands.append({'grp': g, 'n': len(sub), 'hu_zhu': sub[0]['hu_zhu'] or '',
                                      'phone_mask': _acc_public(sub[0])['phone_mask']})
                    handler.send_json(409, {
                        'success': False, 'need': 'grp', 'candidates': cands,
                        'error': '村里有 %d 位「%s」，为避免看错人，请选择所在村民组' % (len(hit), name)})
                    return
                _lookup_fail(ip)
                return _err(handler, '同组有 %d 位「%s」，无法凭%s区分。请改用 6 位积分码，'
                                     '或到村委会查询' % (len(hit), name, what), 409)
            _lookup_clear(ip)
            row = hit[0]
            acc = _acc_public(row)
            # 已通过凭证验明本人，回显积分码方便他下次登录 / 告知家人
            acc['code'] = str(row['code'] or '')
            tk = _issue_token(row['id'])
            tx = conn.execute("SELECT * FROM jf_txns WHERE acc_id=? ORDER BY created DESC LIMIT 8",
                              (row['id'],)).fetchall()
            od = conn.execute("SELECT * FROM jf_orders WHERE acc_id=? AND status='待领取' ORDER BY created DESC LIMIT 5",
                              (row['id'],)).fetchall()
            return _ok(handler, account=acc, token=tk, ttl=TOKEN_TTL,
                       txns=[_txn_json(r) for r in tx], pending=[_order_json(conn, r) for r in od])

        # ---------- 公开：自助兑换 ----------
        if p == '/api/jifen/redeem':
            acc_id = _token_acc(body.get('token'))
            if not acc_id:
                return _err(handler, '查询已过期，请重新输入姓名和手机号后再兑换', 401)
            try:
                r = _do_redeem(conn, acc_id, body.get('items'), src='online',
                               note=_s(body.get('note'), 200), operator='村民自助')
            except BizError as e:
                return _err(handler, str(e))
            return _ok(handler, order=r, message='兑换成功，请凭取货码到积分超市领取')

        # ---------- 管理端 ----------
        if not p.startswith('/api/jifen/admin/'):
            return _err(handler, '接口不存在', 404)
        if not _require_editor(handler):
            return
        me = getattr(handler, '_auth', {}) or {}
        op = me.get('name') or me.get('username') or '管理员'
        act = p[len('/api/jifen/admin/'):]

        if act == 'goods_save':
            gid = _s(body.get('id'))
            fields = {
                'name': _s(body.get('name'), 60), 'cat': _s(body.get('cat'), 20) or '其他',
                'icon': _s(body.get('icon'), 8) or '🎁', 'spec': _s(body.get('spec'), 40),
                'points': max(1, _int(body.get('points'), 10)),
                'stock': max(0, _int(body.get('stock'), 0)),
                'limit_per': max(0, _int(body.get('limit_per'), 0)),
                'desc': _s(body.get('desc'), 300),
                'status': '上架' if _s(body.get('status')) == '上架' else '下架',
                'sort': _int(body.get('sort'), 0),
            }
            if not fields['name']:
                return _err(handler, '商品名称不能为空')
            if gid:
                conn.execute("UPDATE jf_goods SET name=?,cat=?,icon=?,spec=?,points=?,stock=?,limit_per=?,"
                             "desc=?,status=?,sort=?,updated=? WHERE id=?",
                             (fields['name'], fields['cat'], fields['icon'], fields['spec'], fields['points'],
                              fields['stock'], fields['limit_per'], fields['desc'], fields['status'],
                              fields['sort'], _now(), gid))
            else:
                gid = _uid('g_')
                conn.execute("INSERT INTO jf_goods(id,name,cat,icon,spec,points,stock,sold,limit_per,desc,status,sort,created,updated)"
                             " VALUES(?,?,?,?,?,?,?,0,?,?,?,?,?,?)",
                             (gid, fields['name'], fields['cat'], fields['icon'], fields['spec'],
                              fields['points'], fields['stock'], fields['limit_per'], fields['desc'],
                              fields['status'], fields['sort'], _now(), _now()))
            conn.commit()
            return _ok(handler, id=gid)

        if act == 'goods_del':
            conn.execute("DELETE FROM jf_goods WHERE id=?", (_s(body.get('id')),))
            conn.commit()
            return _ok(handler)

        if act == 'acct_save':
            aid = _s(body.get('id'))
            name = _s(body.get('name'), 40)
            if not name:
                return _err(handler, '姓名不能为空')
            code = _s(body.get('code'), 10).upper()
            if code and not re.fullmatch(r'\d{6}', code):
                return _err(handler, '积分码须为 6 位数字（如 382915）')
            if code:
                dupc = conn.execute("SELECT id FROM jf_accounts WHERE code=? AND id<>?",
                                    (code, aid or '')).fetchone()
                if dupc:
                    return _err(handler, '积分码 %s 已被其他账户占用，请换一个' % code)
            vals = (name, _s(body.get('grp'), 40), _s(body.get('phone'), 20),
                    _s(body.get('idcard'), 30), _s(body.get('status'), 10) or '正常',
                    _s(body.get('note'), 200))
            if aid:
                old = conn.execute("SELECT code FROM jf_accounts WHERE id=?", (aid,)).fetchone()
                if not code:
                    code = str((old['code'] if old else '') or '') or _new_code(conn)
                conn.execute("UPDATE jf_accounts SET name=?,grp=?,phone=?,idcard=?,status=?,note=?,"
                             "code=?,updated=? WHERE id=?",
                             vals + (code, _now(), aid))
            else:
                dup = conn.execute("SELECT 1 FROM jf_accounts WHERE name=? AND phone=?", (name, vals[2])).fetchone()
                if dup:
                    return _err(handler, '同姓名同手机号的账户已存在')
                aid = _uid('a_')
                if not code:
                    code = _new_code(conn)
                conn.execute("INSERT INTO jf_accounts(id,name,grp,phone,idcard,points,earned,spent,"
                             "status,note,code,created,updated) VALUES(?,?,?,?,?,0,0,0,?,?,?,?,?)",
                             (aid, name, vals[1], vals[2], vals[3], vals[4], vals[5], code, _now(), _now()))
            conn.commit()
            return _ok(handler, id=aid, code=code)

        if act == 'acct_hu':
            # 人工调户：把某个账户并入指定户（hu_lock=1，重算时不再自动改）
            aid = _s(body.get('id'))
            row = conn.execute("SELECT * FROM jf_accounts WHERE id=?", (aid,)).fetchone()
            if not row:
                return _err(handler, '账户不存在', 404)
            if body.get('reset'):
                conn.execute("UPDATE jf_accounts SET hu_lock=0, hu_src='' WHERE id=?", (aid,))
                conn.commit()
                _sync_hu(conn, force=True)
                return _ok(handler)
            hu = _s(body.get('hu'), 60)
            if not hu:
                return _err(handler, '请选择要并入的户')
            n = conn.execute("SELECT COUNT(*) c FROM jf_accounts WHERE hu=? AND status='正常'",
                             (hu,)).fetchone()['c']
            if not n:
                return _err(handler, '未找到该户，请先刷新户列表')
            zhu = hu.split('·')[-1]
            seq = (conn.execute("SELECT COALESCE(MAX(hu_seq),0) m FROM jf_accounts WHERE hu=?",
                                (hu,)).fetchone()['m'] or 0) + 1
            conn.execute("UPDATE jf_accounts SET hu=?,hu_zhu=?,hu_seq=?,hu_src='人工',hu_lock=1,"
                         "updated=? WHERE id=?", (hu, zhu, seq, _now(), aid))
            conn.commit()
            return _ok(handler, hu=hu, zhu=zhu, seq=seq)

        if act == 'hu_assign':
            # 人工批量归户（多选）：并入已有户 / 新建一户 / 移出本户 / 恢复自动分户
            try:
                r = _hu_assign(conn, body.get('ids') or [], _s(body.get('mode')) or 'join',
                               body.get('hu') or '', body.get('zhu') or '', body.get('grp') or '')
            except BizError as e:
                return _err(handler, str(e))
            print('[JF] 人工归户 mode=%s 人数=%s 户=%s 操作人=%s'
                  % (r.get('mode'), r.get('affected'), r.get('hu') or '-', op))
            return _ok(handler, **r)

        if act == 'acct_del':
            aid = _s(body.get('id'))
            n = conn.execute("SELECT COUNT(*) c FROM jf_orders WHERE acc_id=?", (aid,)).fetchone()['c']
            if n:
                return _err(handler, '该账户已有 %d 笔兑换记录，不能删除；可改为「停用」' % n)
            conn.execute("DELETE FROM jf_accounts WHERE id=?", (aid,))
            conn.execute("DELETE FROM jf_txns WHERE acc_id=?", (aid,))
            conn.commit()
            return _ok(handler)

        if act == 'code_fill':
            # 批量为没有积分码的账户生成（scope=missing 只补没有手机号的人）
            scope = _s(body.get('scope')) or 'missing'
            rows = conn.execute("SELECT id, phone, code FROM jf_accounts "
                                "WHERE code IS NULL OR code=''").fetchall()
            if scope == 'missing':
                rows = [r for r in rows if not str(r['phone'] or '').strip()]
            taken = _code_taken(conn)
            n = 0
            for r in rows:
                conn.execute("UPDATE jf_accounts SET code=?, updated=? WHERE id=?",
                             (_new_code(conn, taken), _now(), r['id']))
                n += 1
            conn.commit()
            rest = conn.execute("SELECT COUNT(*) c FROM jf_accounts "
                                "WHERE code IS NULL OR code=''").fetchone()['c']
            return _ok(handler, filled=n, rest=rest,
                       message='已生成 %d 个积分码' % n + ('，仍有 %d 个账户无码' % rest if rest else ''))

        if act == 'points':
            ids = body.get('acc_ids') or []
            if isinstance(ids, str):
                ids = [ids]
            pts = _int(body.get('points'), 0)
            reason = _s(body.get('reason'), 120) or '积分调整'
            kind = 'adjust' if pts < 0 else 'earn'
            if not ids:
                return _err(handler, '请选择要发放的对象')
            if pts == 0:
                return _err(handler, '积分分值不能为 0')
            done, fails = 0, []
            for aid in ids:
                try:
                    _add_points(conn, aid, pts, reason, kind, op)
                    done += 1
                except BizError as e:
                    fails.append(str(e))
            return _ok(handler, done=done, fails=fails[:5], message='已为 %d 人%s %d 分' % (done, '发放' if pts > 0 else '扣减', abs(pts)))

        if act == 'redeem':
            soc = body.get('acc_ids') or ([body.get('acc_id')] if body.get('acc_id') else [])
            items = body.get('items')
            if not items and body.get('gid'):
                items = [{'gid': body.get('gid'), 'qty': _int(body.get('qty'), 1)}]
            if not soc:
                return _err(handler, '请选择兑换人')
            res, fails = [], []
            for aid in soc:
                try:
                    res.append(_do_redeem(conn, aid, items, src='offline',
                                          note=_s(body.get('note'), 200), operator=op))
                except BizError as e:
                    fails.append('%s：%s' % (aid, str(e)))
            if not res:
                return _err(handler, fails[0] if fails else '兑换失败')
            return _ok(handler, orders=res, fails=fails[:5], message='兑换成功，取货码 %s' % res[0]['code'])

        if act == 'order_done':
            r = conn.execute("SELECT * FROM jf_orders WHERE id=?", (_s(body.get('id')),)).fetchone()
            if not r:
                return _err(handler, '兑换单不存在')
            if r['status'] != '待领取':
                return _err(handler, '该单状态为「%s」，不能核销' % r['status'])
            conn.execute("UPDATE jf_orders SET status='已领取', done_at=?, operator=? WHERE id=?",
                         (_now(), op, r['id']))
            conn.commit()
            return _ok(handler, message='已核销，物品已交付')

        if act == 'order_cancel':
            try:
                _cancel_order(conn, _s(body.get('id')), op)
            except BizError as e:
                return _err(handler, str(e))
            return _ok(handler, message='已取消，积分和库存已退回')

        if act == 'rule_save':
            rid = _s(body.get('id'))
            name = _s(body.get('name'), 80)
            if not name:
                return _err(handler, '规则名称不能为空')
            v = (name, _s(body.get('cat'), 20) or '其他', _int(body.get('points'), 5),
                 _s(body.get('unit'), 10) or '次', _s(body.get('desc'), 200),
                 1 if body.get('enabled', True) in (True, 1, '1', 'true') else 0,
                 _int(body.get('sort'), 0))
            if rid:
                conn.execute("UPDATE jf_rules SET name=?,cat=?,points=?,unit=?,desc=?,enabled=?,sort=? WHERE id=?", v + (rid,))
            else:
                rid = _uid('r_')
                conn.execute("INSERT INTO jf_rules(id,name,cat,points,unit,desc,enabled,sort) VALUES(?,?,?,?,?,?,?,?)", (_uid('r_'),) + v)
            conn.commit()
            return _ok(handler, id=rid)

        if act == 'rule_del':
            conn.execute("DELETE FROM jf_rules WHERE id=?", (_s(body.get('id')),))
            conn.commit()
            return _ok(handler)

        if act == 'settings':
            for k in DEFAULT_SETTINGS:
                if k in body:
                    conn.execute("INSERT INTO jf_settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                                 (k, _s(body.get(k), 400)))
            conn.commit()
            return _ok(handler)

        if act == 'import_hukou':
            return _import_hukou(handler, conn)

        if act == 'hu_sync':
            r = _sync_hu(conn, force=True)
            return _ok(handler, message='已按户籍地址重新归户：%d 户、更新 %d 个账户、未归户 %d 个'
                       % (r['hu'], r['acc'], r['miss']), **r)

        # ---------- 数据备份 / 恢复（仅管理员） ----------
        if act == 'backup_now':
            if not _require_admin(handler):
                return
            name, d = _backup_write(conn, 'jf_backup')
            return _ok(handler, name=name, counts=d.get('counts') or {},
                       message='已备份到服务器：%s' % name)

        if act == 'backup_del':
            if not _require_admin(handler):
                return
            name = os.path.basename(_s(body.get('name'), 120))
            p = os.path.join(BACKUP_DIR, name)
            if not name.endswith('.json') or not os.path.isfile(p):
                return _err(handler, '备份文件不存在', 404)
            os.remove(p)
            return _ok(handler, message='已删除备份 %s' % name)

        if act == 'restore':
            if not _require_admin(handler):
                return
            if _s(body.get('confirm')) != '恢复':
                return _err(handler, '请输入「恢复」二字确认操作')
            mode = 'merge' if _s(body.get('mode')) == 'merge' else 'replace'
            src_name = _s(body.get('name'), 120)
            if src_name:
                try:
                    data = _load_backup_file(src_name)
                except BizError as e:
                    return _err(handler, str(e))
            else:
                data = body.get('data')
            if not isinstance(data, dict):
                return _err(handler, '请选择备份文件')
            # 恢复前自动存档，便于反悔
            pre = ''
            try:
                pre, _ = _backup_write(conn, 'jf_pre_restore')
            except Exception as e:
                print('[JF] 恢复前存档失败:', e)
            try:
                stats = _restore(conn, data, mode)
            except BizError as e:
                return _err(handler, str(e))
            except Exception as e:
                return _err(handler, '恢复失败：%s' % e, 500)
            tot = sum(stats.values())
            return _ok(handler, stats=stats, pre_backup=pre,
                       message='%s恢复完成，共写入 %d 条记录%s' % (
                           '覆盖' if mode == 'replace' else '合并', tot,
                           ('；恢复前数据已存档为 %s' % pre) if pre else ''))

        # ---------- 红黑榜案例 ----------
        if act == 'upload':
            try:
                url = _save_upload(body.get('data'), body.get('name'))
            except BizError as e:
                return _err(handler, str(e))
            return _ok(handler, url=url)

        if act == 'case_save':
            cid = _s(body.get('id'))
            kind = 'black' if _s(body.get('kind')) == 'black' else 'red'
            title = _s(body.get('title'), 60)
            if not title:
                return _err(handler, '请填写案例标题')
            pts = abs(_int(body.get('points'), 0))
            pts = -pts if kind == 'black' else pts
            fields = (kind, title, _s(body.get('who'), 40), _s(body.get('grp'), 20), pts,
                      _s(body.get('desc'), 500), _s(body.get('img'), 200),
                      _s(body.get('happen'), 10),
                      '下架' if _s(body.get('status')) == '下架' else '发布',
                      _int(body.get('sort'), 0))
            if cid:
                conn.execute("UPDATE jf_cases SET kind=?,title=?,who=?,grp=?,points=?,desc=?,img=?,"
                             "happen=?,status=?,sort=?,updated=?,operator=? WHERE id=?",
                             fields + (_now(), op, cid))
            else:
                cid = _uid('c_')
                conn.execute("INSERT INTO jf_cases(id,kind,title,who,grp,points,desc,img,happen,"
                             "status,sort,created,updated,operator) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                             (cid,) + fields + (_now(), _now(), op))
            conn.commit()
            return _ok(handler, id=cid)

        if act == 'case_del':
            cid = _s(body.get('id'))
            r = conn.execute("SELECT img FROM jf_cases WHERE id=?", (cid,)).fetchone()
            if not r:
                return _err(handler, '案例不存在', 404)
            conn.execute("DELETE FROM jf_cases WHERE id=?", (cid,))
            conn.commit()
            _drop_upload(r['img'])
            return _ok(handler)

        if act == 'case_toggle':
            cid = _s(body.get('id'))
            r = conn.execute("SELECT status FROM jf_cases WHERE id=?", (cid,)).fetchone()
            if not r:
                return _err(handler, '案例不存在', 404)
            new = '下架' if (r['status'] or '发布') == '发布' else '发布'
            conn.execute("UPDATE jf_cases SET status=?, updated=? WHERE id=?", (new, _now(), cid))
            conn.commit()
            return _ok(handler, status=new)

        return _err(handler, '操作不存在', 404)
    finally:
        conn.close()


# 村民组地址归并（与村情一口清同一套口径）
_GRP_MERGE = {'磨勾冲': '磨沟冲', '磨匀冲': '磨沟冲', '磨冲': '磨沟冲', '沙坪': '沙坪江'}


def _norm_grp(g):
    g = str(g or '').strip()
    if not g:
        return ''
    # 去掉「XX镇XX村」前缀（台账地址里常见）；按「村」字锚定，换村也能用
    if '村' in g:
        g = g.split('村')[-1].strip()
        if not g:
            return ''
    for bad, good in _GRP_MERGE.items():
        if g == bad or g == bad + '组':
            return good + '组'
    # 「中田冲」与「中田冲组」视为同一组
    if not g.endswith('组'):
        g += '组'
    return g


_PHONE_IDX = {'mtime': 0, 'by_id': {}}


def _phone_by_id():
    """读取驻村资料生成的「身份证 → 手机号」索引（tools/build_phone_index.py 产出），按 mtime 缓存"""
    p = os.path.join(BASE_DIR, 'tools', '_phone_index.json')
    try:
        m = os.path.getmtime(p)
    except OSError:
        return {}
    if _PHONE_IDX['mtime'] != m:
        try:
            with open(p, 'r', encoding='utf-8') as fh:
                d = json.load(fh)
            idx = {}
            for idc, ph in (d.get('by_id') or {}).items():
                if not ph:
                    continue
                for k in ph.keys():
                    k = str(k).strip()
                    if re.fullmatch(r'1\d{10}', k):
                        idx[str(idc).strip().upper()] = k
                        break
            _PHONE_IDX['by_id'] = idx
            _PHONE_IDX['mtime'] = m
            print('[JF] 电话索引已加载 %d 条' % len(idx))
        except Exception as e:
            print('[JF] 电话索引读取失败:', e)
    return _PHONE_IDX['by_id']


# ---------------------------------------------------------------- 按户归集
# 分户依据（2026-11-08 起，按可信度排序）：
#   1. 家庭成员健康信息表（表 jf_hh）：直接给出「户主 + 与户主关系 + 电话」，最准；
#   2. 手机号：同一手机号只对应一户时并入（家里共用一部手机的情况）；
#   3. 户籍地址：同址只有一户时并入；同址多户时按同姓唯一并入；
#   4. 仍判不出 → 按户籍地址自成一户，并标「待核」，后台可人工调户。
# 户键 hu = 「村民组·户主」，例：白粉墙组·罗仁德
_HU_SYNC = {'ts': 0, 'sig': None}
_HU_PREFIX = re.compile(r'^.*?村')


def _hu_addr(hu):
    """户键 → 显示：老数据（完整地址）截短；新数据（组·户主）原样返回"""
    s = _HU_PREFIX.sub('', str(hu or '')).strip()
    return s or str(hu or '')


def _hu_key(zhu, grp):
    """户主 + 组 → 户键"""
    zhu = _s(zhu, 40)
    return (_norm_grp(grp) + '·' + zhu) if zhu else ''


def _hk_index(conn):
    """户籍台账（状态正常）索引：身份证 → 记录、姓名 → 记录、地址 → 户主（序号最小者，推定）
    独立部署时可能没有 ledger_rows（台账由村居系统归集），此时返回空索引。"""
    try:
        rows = conn.execute("SELECT data FROM ledger_rows WHERE lid='hukou' ORDER BY seq").fetchall()
    except sqlite3.OperationalError:
        return {}, {}, {}
    by_id, by_name, heads = {}, {}, {}
    for i, r in enumerate(rows):
        try:
            d = json.loads(r['data'])
        except Exception:
            continue
        if len(d) < 9:
            continue
        name = _s(d[2], 40)
        addr = _s(d[7], 160).strip()
        if not name or not addr:
            continue
        if _s(d[8], 10) not in ('', '正常'):
            continue
        m = re.search(r'村(.+?组)', addr)
        grp = _norm_grp(m.group(1)) if m else ''
        rec = (addr, i, name, grp)
        idc = _s(d[1], 30).upper()
        if idc:
            by_id[idc] = rec
        by_name.setdefault(name, []).append(rec)
        h = heads.get(addr)
        if h is None or i < h[0]:
            heads[addr] = (i, name, grp)
    return by_id, by_name, heads


def _hh_index(conn):
    """健康档案分户索引：证件 → 户键、(姓名,组) → [户键]、电话 → {户键}"""
    by_id, by_nm, tel2hh = {}, {}, {}
    for r in conn.execute("SELECT idcard,name,grp,hu_zhu,phone FROM jf_hh WHERE hu_zhu<>''"):
        zhu = _s(r['hu_zhu'], 40)
        if not zhu:
            continue
        k = (zhu, _norm_grp(r['grp']))
        idc = _s(r['idcard'], 30).upper()
        if len(idc) == 18:
            by_id[idc] = k
        by_nm.setdefault((_s(r['name'], 40), k[1]), []).append(k)
        ph = _s(r['phone'], 20)
        if ph:
            tel2hh.setdefault(ph, set()).add(k)
    return by_id, by_nm, tel2hh


def _sync_hu(conn, force=False):
    """把积分账户归户，写 hu / hu_zhu / hu_seq / hu_src / addr。
    人工调过（hu_lock=1）的账户不动。数据没变且 5 分钟内不重算。"""
    now = time.time()
    sr = conn.execute("SELECT COUNT(*) c, COALESCE(MAX(updated),'') u FROM jf_hh").fetchone()
    sig = (sr['c'], sr['u'])
    if not force and _HU_SYNC['sig'] == sig and now - _HU_SYNC['ts'] < 300:
        return {'acc': 0, 'hu': 0, 'miss': 0, 'wait': 0, 'skip': True}

    hh_id, hh_nm, hh_tel = _hh_index(conn)
    hk_id, hk_nm, hk_heads = _hk_index(conn)
    accs = conn.execute("SELECT id,name,grp,idcard,phone,hu,hu_zhu,hu_seq,hu_src,hu_lock,addr"
                        " FROM jf_accounts").fetchall()

    def addr_of(a):
        ad = _s(a['addr'], 160)
        if not ad:
            rec = hk_id.get(_s(a['idcard'], 30).upper())
            ad = rec[0] if rec else ''
        return ad

    res, src = {}, {}
    # ---- 1~3 级：健康表（证件 → 姓名+组 → 同名+电话 → 同电话）
    for a in accs:
        idc = _s(a['idcard'], 30).upper()
        nm = _s(a['name'], 40)
        grp = _norm_grp(a['grp'])
        ph = _s(a['phone'], 20)
        if a['hu_lock'] and a['hu_zhu']:
            res[a['id']] = (_s(a['hu_zhu'], 40),
                            _norm_grp((a['hu'] or '').split('·')[0]))
            src[a['id']] = '人工'
            continue
        k = hh_id.get(idc) if len(idc) == 18 else None
        if k:
            res[a['id']] = k
            src[a['id']] = '健康表'
            continue
        cand = hh_nm.get((nm, grp)) or []
        if len(cand) == 1:
            res[a['id']] = cand[0]
            src[a['id']] = '健康表'
            continue
        if len(cand) > 1 and ph:
            c2 = [x for x in cand if x in (hh_tel.get(ph) or set())]
            if len(c2) == 1:
                res[a['id']] = c2[0]
                src[a['id']] = '同名+电话'
                continue
        if ph:
            hs = hh_tel.get(ph) or set()
            if len(hs) == 1:
                res[a['id']] = list(hs)[0]
                src[a['id']] = '同电话'

    # ---- 4 级：户籍地址（同址已归户的唯一/同姓唯一者）
    a2h, a2n = {}, {}
    for a in accs:
        k = res.get(a['id'])
        if not k:
            continue
        ad = addr_of(a)
        if ad:
            a2h.setdefault(ad, {}).setdefault(k, 0)
            a2h[ad][k] += 1
            a2n[ad] = a2n.get(ad, 0) + 1
    # 宽松地址：把「4号附1号」并入「4号」，同一栋房算一户
    def relax(ad):
        return re.sub(r'附\d*号?$', '', ad or '')

    a2h_r = {}
    for ad, hs in a2h.items():
        k = relax(ad)
        a2h_r.setdefault(k, {}).update(hs)

    rest = [a for a in accs if a['id'] not in res]
    for a in list(rest):
        ad = addr_of(a)
        if ad and not (a2h.get(ad) or {}):
            hs0 = a2h_r.get(relax(ad))
            if hs0 and len(hs0) == 1:
                res[a['id']] = list(hs0)[0]
                src[a['id']] = '户籍地址'
                rest.remove(a)
    for a in list(rest):
        ad = addr_of(a)
        hs = list((a2h.get(ad) or {}).keys()) if ad else []
        if len(hs) == 1:
            res[a['id']] = hs[0]
            src[a['id']] = '户籍地址'
            rest.remove(a)
        elif len(hs) > 1:
            sx = _s(a['name'], 40)[:1]
            same = [k for k in hs if (k[0] or '')[:1] == sx and k[1] == _norm_grp(a['grp'])]
            if len(same) == 1:
                res[a['id']] = same[0]
                src[a['id']] = '户籍地址'
                rest.remove(a)

    # ---- 5 级：同址多户且判不出 → 并入同址人数最多的一户，标「待核」
    for a in list(rest):
        ad = addr_of(a)
        hs = a2h.get(ad) or {}
        if len(hs) > 1:
            best = sorted(hs.items(), key=lambda kv: (-kv[1], kv[0][0]))[0][0]
            res[a['id']] = best
            src[a['id']] = '待核'
            rest.remove(a)

    # ---- 6 级：剩下的人按户籍地址自成一户（同址即同户）
    by_addr = {}
    for a in rest:
        by_addr.setdefault(addr_of(a) or ('#' + a['id']), []).append(a)
    for ad, ms in by_addr.items():
        ms.sort(key=lambda x: hk_id.get(_s(x['idcard'], 30).upper(), (None, 10 ** 9))[1])
        head = ms[0]
        k = (_s(head['name'], 40), _norm_grp(head['grp']))
        for m in ms:
            res[m['id']] = k
            src[m['id']] = '地址新户'

    # ---- 写库（组内序号：户主第一，其余按户籍顺序）
    groups = {}
    for a in accs:
        k = res.get(a['id'])
        if k:
            groups.setdefault(k, []).append(a)
    upd = []
    for k, ms in groups.items():
        zhu, grp = k
        ad = ''
        for m in ms:
            ad = ad or addr_of(m)
        ms.sort(key=lambda x: (0 if _s(x['name'], 40) == zhu else 1,
                               hk_id.get(_s(x['idcard'], 30).upper(), (None, 10 ** 9))[1]))
        hu = _hu_key(zhu, grp)
        for i, m in enumerate(ms, 1):
            if (m['hu'] or '') == hu and (m['hu_zhu'] or '') == zhu \
                    and (m['hu_src'] or '') == src[m['id']] and (m['addr'] or '') == ad \
                    and (m['hu_seq'] or 0) == i:
                continue
            upd.append((hu, zhu, i, ad, src[m['id']], m['id']))
    if upd:
        conn.executemany("UPDATE jf_accounts SET hu=?, hu_zhu=?, hu_seq=?, addr=?, hu_src=?"
                         " WHERE id=?", upd)
        conn.commit()
    _HU_SYNC['ts'] = now
    _HU_SYNC['sig'] = sig
    hus = conn.execute("SELECT COUNT(DISTINCT hu) c FROM jf_accounts "
                       "WHERE hu<>'' AND status='正常'").fetchone()['c']
    wait = sum(1 for a in accs if src.get(a['id']) == '待核')
    return {'acc': len(upd), 'hu': hus, 'miss': sum(1 for a in accs if a['id'] not in res),
            'wait': wait, 'src': dict(Counter(src.values()))}


def _house_list(conn, kw='', page=1, size=20):
    """按户聚合：户积分 = 户内成员当前积分之和（分户见 _sync_hu 说明）"""
    where = ["status='正常'", "hu<>''"]
    args = []
    if kw:
        where.append("(hu LIKE ? OR hu_zhu LIKE ? OR grp LIKE ? OR addr LIKE ? OR hu IN "
                     "(SELECT hu FROM jf_accounts WHERE name LIKE ? AND hu<>''))")
        args += ['%' + kw + '%'] * 5
    w = 'WHERE ' + ' AND '.join(where)
    total = conn.execute("SELECT COUNT(*) c FROM (SELECT hu FROM jf_accounts " + w + " GROUP BY hu)",
                         args).fetchone()['c']
    agg = conn.execute(
        "SELECT hu, MAX(hu_zhu) zhu, SUBSTR(hu,1,INSTR(hu,'·')-1) grp, MAX(addr) addr, COUNT(*) n, "
        "COALESCE(SUM(points),0) p, COALESCE(SUM(earned),0) e, COALESCE(SUM(spent),0) s, "
        "SUM(CASE WHEN earned>0 OR spent>0 THEN 1 ELSE 0 END) act, "
        "SUM(CASE WHEN hu_src='待核' THEN 1 ELSE 0 END) wait "
        "FROM jf_accounts " + w + " GROUP BY hu ORDER BY p DESC, n DESC LIMIT ? OFFSET ?",
        args + [size, (page - 1) * size]).fetchall()
    out = []
    for r in agg:
        out.append({'hu': r['hu'], 'addr': _hu_addr(r['addr'] or r['hu']), 'zhu': r['zhu'] or '',
                    'grp': r['grp'] or '', 'members': r['n'], 'act': r['act'] or 0,
                    'wait': r['wait'] or 0,
                    'points': r['p'] or 0, 'earned': r['e'] or 0, 'spent': r['s'] or 0})
    return total, out


def _hu_assign(conn, ids, mode='join', hu='', zhu='', grp=''):
    """人工批量归户（后台「分户调整」用）。
    mode=join 并入已有户 / new 以「组·户主」新建一户 / none 移出本户暂不归户 /
    auto 解除人工锁定并立即按健康表重算。
    人工结果的 hu_lock=1，自动重算不会再覆盖；均返回受影响人数与提示语。"""
    ids = [_s(x, 40) for x in (ids or []) if _s(x, 40)]
    if not ids:
        raise BizError('请先勾选要调整的人员')
    if len(ids) > 300:
        raise BizError('一次最多调整 300 人，请分批操作')
    ph = ','.join('?' * len(ids))
    rows = conn.execute("SELECT id,name,grp,hu,hu_zhu FROM jf_accounts WHERE id IN (%s)" % ph,
                        ids).fetchall()
    if not rows:
        raise BizError('账户不存在，请刷新后重试')
    now = _now()

    if mode == 'auto':
        conn.execute("UPDATE jf_accounts SET hu_lock=0, hu_src='' WHERE id IN (%s)" % ph, ids)
        conn.commit()
        _sync_hu(conn, force=True)
        return {'mode': 'auto', 'affected': len(rows), 'hu': '', 'zhu': '',
                'message': '已恢复自动分户（%d 人按健康表/电话/户籍地址重新归户）' % len(rows)}

    if mode == 'none':
        conn.execute("UPDATE jf_accounts SET hu='',hu_zhu='',hu_seq=0,hu_src='人工',"
                     "hu_lock=1,updated=? WHERE id IN (%s)" % ph, [now] + ids)
        conn.commit()
        return {'mode': 'none', 'affected': len(rows), 'hu': '', 'zhu': '',
                'message': '已把 %d 人移出本户，暂不归户（之后可再并入正确户）' % len(rows)}

    if mode == 'new':
        zhu = _s(zhu, 40)
        if not zhu:
            raise BizError('请填写新户的户主姓名')
        g = _norm_grp(_s(grp, 40)) or \
            _norm_grp(next((_s(r['grp']) for r in rows if _s(r['grp'])), ''))
        if not g:
            raise BizError('请填写新户所属的村民组')
        hu = _hu_key(zhu, g)
        if len(hu) > 60:
            raise BizError('户主姓名或组别过长')
    else:
        hu = _s(hu, 60)
        if not hu:
            raise BizError('请选择要并入的户')
        if not conn.execute("SELECT 1 FROM jf_accounts WHERE hu=? LIMIT 1", (hu,)).fetchone():
            raise BizError('未找到该户，请刷新户列表')
        zhu = hu.split('·')[-1]

    seq = (conn.execute("SELECT COALESCE(MAX(hu_seq),0) m FROM jf_accounts WHERE hu=?",
                        (hu,)).fetchone()['m'] or 0)
    rows = sorted(rows, key=lambda r: 0 if _s(r['name']) == zhu else 1)
    upd, seen = [], set()
    for r in rows:
        if r['id'] in seen:
            continue
        seen.add(r['id'])
        seq += 1
        upd.append((hu, zhu, seq, '人工', 1, now, r['id']))
    conn.executemany("UPDATE jf_accounts SET hu=?,hu_zhu=?,hu_seq=?,hu_src=?,hu_lock=?,"
                     "updated=? WHERE id=?", upd)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) c FROM jf_accounts WHERE hu=? AND status='正常'",
                     (hu,)).fetchone()['c']
    return {'mode': mode, 'affected': len(upd), 'hu': hu, 'zhu': zhu, 'members': n,
            'message': '已把 %d 人归入「%s」户（本户现有 %d 人）' % (len(upd), zhu, n)}


def _house_detail(conn, hu):
    mem = conn.execute("SELECT * FROM jf_accounts WHERE hu=? ORDER BY points DESC, hu_seq, name",
                       (hu,)).fetchall()
    if not mem:
        return None
    tot = {'members': len(mem), 'points': 0, 'earned': 0, 'spent': 0}
    for m in mem:
        tot['points'] += m['points'] or 0
        tot['earned'] += m['earned'] or 0
        tot['spent'] += m['spent'] or 0
    tx = conn.execute("SELECT t.* FROM jf_txns t JOIN jf_accounts a ON a.id=t.acc_id "
                      "WHERE a.hu=? ORDER BY t.created DESC LIMIT 30", (hu,)).fetchall()
    return {'hu': hu, 'addr': _hu_addr(mem[0]['addr'] or hu), 'zhu': (mem[0]['hu_zhu'] or ''),
            'grp': (mem[0]['grp'] or ''), 'total': tot,
            'members': [dict(_acc_public(m), hu_src=(m['hu_src'] or ''),
                             hu_lock=1 if m['hu_lock'] else 0) for m in mem],
            'txns': [_txn_json(t) for t in tx]}


def _unhoused(conn):
    """没有归户的账户数（正常状态）"""
    return conn.execute("SELECT COUNT(*) c FROM jf_accounts "
                        "WHERE status='正常' AND hu=''").fetchone()['c']


def _hu_review(conn, limit=200):
    """分户待核清单：待核账户 + 只有 1 人的户（便于人工核对）"""
    rows = conn.execute(
        "SELECT id,name,grp,hu,hu_zhu,hu_src,phone,points FROM jf_accounts "
        "WHERE status='正常' AND hu_src='待核' ORDER BY grp, hu_zhu, name LIMIT ?",
        (limit,)).fetchall()
    wait = [{'id': r['id'], 'name': r['name'], 'grp': r['grp'] or '', 'hu': r['hu'] or '',
             'zhu': r['hu_zhu'] or '', 'phone': r['phone'] or '', 'points': r['points'] or 0}
            for r in rows]
    one = conn.execute(
        "SELECT hu, MAX(hu_zhu) zhu, MAX(grp) grp, MAX(addr) addr, MAX(name) nm, COUNT(*) n "
        "FROM jf_accounts WHERE status='正常' AND hu<>'' GROUP BY hu HAVING n=1 "
        "ORDER BY grp, zhu LIMIT ?", (limit,)).fetchall()
    single = [{'hu': r['hu'], 'zhu': r['zhu'] or '', 'grp': r['grp'] or '',
               'addr': _hu_addr(r['addr'] or r['hu']), 'name': r['nm'] or ''} for r in one]
    return {'wait': wait, 'single': single}


def _rank_hu(conn, limit=20):
    """户积分榜（对外，户主姓名脱敏）"""
    rows = conn.execute(
        "SELECT hu, MAX(hu_zhu) zhu, SUBSTR(hu,1,INSTR(hu,'·')-1) grp, MAX(addr) addr, COUNT(*) n, "
        "COALESCE(SUM(points),0) p, COALESCE(SUM(earned),0) e "
        "FROM jf_accounts WHERE status='正常' AND hu<>'' "
        "GROUP BY hu HAVING SUM(points) > 0 ORDER BY p DESC, e DESC, zhu LIMIT ?",
        (limit,)).fetchall()
    return [{'no': i, 'name': _mask_name(r['zhu'] or ''), 'grp': r['grp'] or '',
             'addr': _hu_addr(r['addr'] or r['hu']), 'members': r['n'],
             'points': r['p'] or 0, 'earned': r['e'] or 0}
            for i, r in enumerate(rows, 1)]


def _import_hukou_impl(conn):
    """从户籍台账（状态=正常）批量建立积分账户；同时用资料索引补全手机号。返回结果 dict"""
    try:
        rows = conn.execute("SELECT data FROM ledger_rows WHERE lid='hukou' ORDER BY seq").fetchall()
    except sqlite3.OperationalError:
        raise BizError('当前数据库没有户籍台账（ledger_rows），请改用「新增账户」或导入备份')
    pid = _phone_by_id()
    added = skipped = filled = 0
    for r in rows:
        try:
            d = json.loads(r['data'])
        except Exception:
            continue
        if len(d) < 9:
            continue
        name = _s(d[2], 40)
        if not name:
            continue
        status = _s(d[8], 10) if len(d) > 8 else ''
        if status and status != '正常':
            continue
        phone = _s(d[9] if len(d) > 9 else '', 20)
        if not re.fullmatch(r'1\d{10}', phone):
            phone = ''
        grp = _s(d[7], 40)
        m = re.search(r'村(.+?组)', grp)
        grp = _norm_grp(m.group(1) if m else grp)
        idc = _s(d[1], 30)
        if not phone and idc:
            phone = pid.get(idc.upper(), '')
        dup = None
        if idc and len(idc) >= 15:
            dup = conn.execute("SELECT * FROM jf_accounts WHERE idcard=? AND idcard<>''", (idc,)).fetchone()
        if not dup and phone:
            dup = conn.execute("SELECT * FROM jf_accounts WHERE name=? AND phone=?", (name, phone)).fetchone()
        if not dup and not phone and not idc:
            dup = conn.execute("SELECT * FROM jf_accounts WHERE name=? AND phone='' AND grp=?",
                               (name, grp)).fetchone()
        if dup:
            if idc and len(idc) >= 15 and (dup['idcard'] or '') and dup['idcard'] != idc:
                # 同名同电话但身份证不同 → 是另一个同名村民（多为共用家庭电话）
                # 照样建户，但电话留空（避免查分时同名同号撞车），用身份证后 6 位可查
                conn.execute("INSERT INTO jf_accounts(id,name,grp,phone,idcard,points,earned,spent,status,note,created,updated)"
                             " VALUES(?,?,?,?,?,0,0,0,'正常','同名同电话待核对',?,?)",
                             (_uid('a_'), name, grp, '', idc, _now(), _now()))
                added += 1
                continue
            # 已有账户：手机号为空而索引里有值时补上（不清空、不覆盖人工填写）
            if phone and not (dup['phone'] or ''):
                conn.execute("UPDATE jf_accounts SET phone=?, updated=? WHERE id=?", (phone, _now(), dup['id']))
                filled += 1
            else:
                skipped += 1
            continue
        conn.execute("INSERT INTO jf_accounts(id,name,grp,phone,idcard,points,earned,spent,status,note,created,updated)"
                     " VALUES(?,?,?,?,?,0,0,0,'正常','户籍导入',?,?)",
                     (_uid('a_'), name, grp, phone, idc, _now(), _now()))
        added += 1
    # 新账户一律带 6 位积分码：没有手机号、也没有身份证的人也能登录
    taken = _code_taken(conn)
    for r in conn.execute("SELECT id FROM jf_accounts WHERE code IS NULL OR code=''").fetchall():
        conn.execute("UPDATE jf_accounts SET code=? WHERE id=?", (_new_code(conn, taken), r['id']))
    conn.commit()
    _sync_hu(conn, force=True)
    total = conn.execute("SELECT COUNT(*) c FROM jf_accounts").fetchone()['c']
    with_ph = conn.execute("SELECT COUNT(*) c FROM jf_accounts WHERE phone<>''").fetchone()['c']
    return {'added': added, 'skipped': skipped, 'filled': filled, 'total': total, 'with_phone': with_ph}


def _import_hukou(handler, conn):
    r = _import_hukou_impl(conn)
    return _ok(handler, message='新增 %d 个账户、补全 %d 个手机号，跳过 %d 个重复；当前共 %d 个账户，其中 %d 个有手机号'
               % (r['added'], r['filled'], r['skipped'], r['total'], r['with_phone']), **r)
