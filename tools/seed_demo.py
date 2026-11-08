# -*- coding: utf-8 -*-
"""给「测试」账户生成积分超市全流程演示数据（演示 / 培训用）。

覆盖的完整链路（便于当面演示 / 截图）：
    加分（村委录入）→ 村民查分 → 自助兑换 → 后台核销取货 → 取消兑换并退分

数据固定可重复执行：每次先回补库存、清掉该账户旧流水与订单，再按时间顺序重放，
所以余额、累计获得、累计兑换、库存、销量都是自洽的。

用法：
    python tools/seed_demo.py              # 重建演示数据
    python tools/seed_demo.py --clear      # 只清理（积分归零、删流水订单、回补库存）
    python tools/seed_demo.py --account 测试 --db data/jifen.db --dry-run
"""
import os
import sys
import json
import argparse
import sqlite3
import secrets

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DEFAULT_DB = (os.environ.get('JF_DB') or os.environ.get('VMS_DB')
              or os.path.join(ROOT, 'data', 'jifen.db'))

# ---------------------------------------------------------------- 演示脚本
# (时间, 类型, 说明)  earn=加分；每笔金额按规则表填，balance 由脚本顺推
EARN = [
    ('2026-06-16 09:30:00', 5,   '参加村民会议、村民代表会议', '管理员'),
    ('2026-06-16 09:36:00', 5,   '参与积分制宣传、带头示范', '管理员'),
    ('2026-06-27 15:00:00', 10,  '参加村集体环境整治、义务劳动', '村委干部'),
    ('2026-07-08 10:00:00', 20,  '门前三包、卫生评比优秀', '管理员'),
    ('2026-07-08 10:06:00', 5,   '按时缴纳城乡居民医保、养老保险', '村委干部'),
    ('2026-07-21 19:10:00', 10,  '参加护林防火、防汛抗旱值守', '村委干部'),
    ('2026-08-05 09:40:00', 10,  '助人为乐、见义勇为、拾金不昧', '管理员'),
    ('2026-08-18 16:20:00', 10,  '参加村集体环境整治、义务劳动', '村委干部'),
    ('2026-08-25 11:10:00', 15,  '主动调解邻里纠纷、化解矛盾', '管理员'),
    ('2026-09-06 08:50:00', 30,  '红白事简办、不铺张浪费', '管理员'),
    ('2026-09-18 10:00:00', 5,   '参加村民会议、村民代表会议', '管理员'),
    ('2026-09-28 09:10:00', 100, '子女无辍学、考入大专及以上院校', '村委干部'),
    ('2026-10-08 09:20:00', 50,  '获评“星级文明户”“最美家庭”', '管理员'),
    ('2026-10-20 19:10:00', 10,  '参加护林防火、防汛抗旱值守', '村委干部'),
    ('2026-10-26 15:40:00', 10,  '参加村集体环境整治、义务劳动', '村委干部'),
    ('2026-11-05 09:00:00', 20,  '门前三包、卫生评比优秀', '管理员'),
]

# 兑换单（按时间顺序插入，扣分与流水同步）
# gid 用商品名匹配，避免不同库里 gid 不一致
ORDERS = [
    dict(created='2026-08-25 15:30:00', status='已领取', done_at='2026-08-26 09:12:00',
         src='online', operator='管理员', note='',
         items=[('洗衣粉 500g', 1), ('香皂', 1)]),
    dict(created='2026-10-15 14:20:00', status='已领取', done_at='2026-10-16 10:05:00',
         src='online', operator='村委干部', note='',
         items=[('卷纸（10 卷）', 1)]),
    # 后台代兑后村民没来取，当天取消 → 演示「取消退分」
    dict(created='2026-10-12 10:00:00', status='已取消', done_at='2026-10-12 16:00:00',
         src='offline', operator='管理员', note='村民改约下周再来，先取消',
         items=[('保温杯', 1)]),
    # 留在「待领取」，用于演示后台核销
    dict(created='2026-11-07 10:20:00', status='待领取', done_at='',
         src='online', operator='', note='',
         items=[('大米 5kg', 1)]),
]


def _uid(p):
    return p + secrets.token_hex(8)


def _code(conn):
    for _ in range(50):
        c = str(secrets.randbelow(900000) + 100000)
        if not conn.execute('SELECT 1 FROM jf_orders WHERE code=?', (c,)).fetchone():
            return c
    raise SystemExit('取货码生成失败')


def find_acc(conn, name):
    rows = conn.execute('SELECT * FROM jf_accounts WHERE name=? ORDER BY created', (name,)).fetchall()
    if not rows:
        raise SystemExit('库里没有名为「%s」的账户' % name)
    if len(rows) > 1:
        print('[提示] 有 %d 个「%s」，使用第一个：%s' % (len(rows), name, rows[0]['id']))
    return rows[0]


def restore_stock(conn, acc_id):
    """把该账户未取消订单占用的库存回补（幂等重跑用）"""
    rows = conn.execute(
        "SELECT o.status, oi.gid, oi.qty FROM jf_orders o "
        "JOIN jf_order_items oi ON oi.order_id=o.id WHERE o.acc_id=?", (acc_id,)).fetchall()
    n = 0
    for r in rows:
        if (r['status'] or '') == '已取消':
            continue
        conn.execute('UPDATE jf_goods SET stock = stock + ?, sold = MAX(sold - ?, 0) WHERE id=?',
                     (r['qty'], r['qty'], r['gid']))
        n += r['qty']
    return n


def clear(conn, acc):
    """清空该账户的流水/订单与积分"""
    restore_stock(conn, acc['id'])
    conn.execute("DELETE FROM jf_order_items WHERE order_id IN "
                 "(SELECT id FROM jf_orders WHERE acc_id=?)", (acc['id'],))
    conn.execute('DELETE FROM jf_orders WHERE acc_id=?', (acc['id'],))
    conn.execute('DELETE FROM jf_txns WHERE acc_id=?', (acc['id'],))
    conn.execute("UPDATE jf_accounts SET points=0, earned=0, spent=0, updated=? WHERE id=?",
                 ('2026-11-08 10:35:00', acc['id']))


def goods_index(conn):
    out = {}
    for g in conn.execute('SELECT * FROM jf_goods'):
        out[g['name']] = dict(g)
    return out


def seed(conn, acc, dry=False):
    gmap = goods_index(conn)
    # 省掉 order_items 里引用的商品不存在时直接报错，避免造出脏数据
    for o in ORDERS:
        for nm, _q in o['items']:
            if nm not in gmap:
                raise SystemExit('商品不存在：%s' % nm)

    acc_id, name, grp = acc['id'], acc['name'], acc['grp'] or ''
    bal = 0
    earned = spent = 0
    txns = []          # (time, kind, points, balance, reason, ref, operator)
    orders = []

    # 把加分与兑换排成一条时间线，保证流水顺序与 balance 一致
    line = [('earn', t, pts, reason, op) for (t, pts, reason, op) in EARN]
    line += [('order', o['created'], o, None, None) for o in ORDERS]
    line.sort(key=lambda x: x[1])

    for kind, ts, a, b, c in line:
        if kind == 'earn':
            bal += a
            earned += a
            txns.append((ts, 'earn', a, bal, b, '', c))
            continue
        o = a
        items, total = [], 0
        for nm, qty in o['items']:
            g = gmap[nm]
            sub = int(g['points']) * qty
            total += sub
            items.append({'gid': g['id'], 'name': g['name'], 'icon': g['icon'] or '🎁',
                          'qty': qty, 'points': int(g['points']), 'sub': sub})
        if total > bal:
            raise SystemExit('演示脚本余额不足：%s 需 %d 分，当时只有 %d 分' % (o['created'], total, bal))
        bal -= total
        spent += total
        code = _code(conn) if not dry else '000000'
        oid = 'o_demo_' + secrets.token_hex(6)
        rec = dict(o)
        rec.update(dict(oid=oid, code=code, total=total, items=items))
        orders.append(rec)
        txt = '、'.join('%s×%d' % (i['name'], i['qty']) for i in items)
        txns.append((o['created'], 'spend', -total, bal, '兑换：' + txt, code, o['operator'] or '村民自助'))
        if o['status'] == '已取消':
            bal += total
            spent -= total
            txns.append((o['done_at'], 'refund', total, bal,
                         '兑换取消退回（单号 %s）' % code, code, o['operator'] or '管理员'))

    if dry:
        print('[演练] 加分合计 %d，有效兑换 %d，最终余额 %d，流水 %d 条，订单 %d 张'
              % (earned, spent, bal, len(txns), len(orders)))
        return

    conn.execute('BEGIN IMMEDIATE')
    try:
        restore_stock(conn, acc_id)
        conn.execute("DELETE FROM jf_order_items WHERE order_id IN "
                     "(SELECT id FROM jf_orders WHERE acc_id=?)", (acc_id,))
        conn.execute('DELETE FROM jf_orders WHERE acc_id=?', (acc_id,))
        conn.execute('DELETE FROM jf_txns WHERE acc_id=?', (acc_id,))

        for (ts, kind, pts, balance, reason, ref, op) in txns:
            conn.execute(
                'INSERT INTO jf_txns(id,acc_id,name,grp,kind,points,balance,reason,ref,operator,created)'
                ' VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (_uid('t_'), acc_id, name, grp, kind, pts, balance, reason, ref, op or '管理员', ts))

        for o in orders:
            conn.execute(
                'INSERT INTO jf_orders(id,code,acc_id,name,phone,grp,points,status,src,items,created,'
                'done_at,operator,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (o['oid'], o['code'], acc_id, name, acc['phone'] or '', grp, o['total'],
                 o['status'], o['src'], json.dumps(o['items'], ensure_ascii=False),
                 o['created'], o['done_at'], o['operator'], o['note']))
            for i in o['items']:
                conn.execute('INSERT INTO jf_order_items(id,order_id,gid,gname,icon,qty,points)'
                             ' VALUES(?,?,?,?,?,?,?)',
                             (_uid('oi_'), o['oid'], i['gid'], i['name'], i['icon'], i['qty'],
                              i['points']))
                if o['status'] != '已取消':
                    cur = conn.execute(
                        'UPDATE jf_goods SET stock = stock - ?, sold = sold + ?, updated=? '
                        'WHERE id=? AND stock >= ?',
                        (i['qty'], i['qty'], o['created'], i['gid'], i['qty']))
                    if cur.rowcount != 1:
                        raise RuntimeError('「%s」库存不足，演示数据未生成' % i['name'])

        note = (acc['note'] or '')
        if '演示' not in note:
            note = (note + ' 演示账户，含全流程演示数据').strip()
        conn.execute('UPDATE jf_accounts SET points=?, earned=?, spent=?, note=?, updated=? WHERE id=?',
                     (bal, earned, spent, note, '2026-11-07 10:20:00', acc_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    print('已生成演示数据：账户「%s」(%s)' % (name, grp or '—'))
    print('  加分 %d 分 / 有效兑换 %d 分 / 当前余额 %d 分' % (earned, spent, bal))
    print('  流水 %d 条（加分 %d、兑换 %d、退款 %d）' % (
        len(txns), sum(1 for t in txns if t[1] == 'earn'),
        sum(1 for t in txns if t[1] == 'spend'), sum(1 for t in txns if t[1] == 'refund')))
    print('  订单 %d 张：%s' % (len(orders), '、'.join(
        '%s(%s %d分 码%s)' % (o['items'][0]['name'], o['status'], o['total'], o['code'])
        for o in orders)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=DEFAULT_DB)
    ap.add_argument('--account', default='测试')
    ap.add_argument('--clear', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    conn = sqlite3.connect(args.db, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=15000')
    acc = find_acc(conn, args.account)
    if args.clear:
        conn.execute('BEGIN IMMEDIATE')
        try:
            clear(conn, acc)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        print('已清空「%s」的流水/订单，积分归零，库存已回补' % args.account)
        return
    seed(conn, acc, dry=args.dry_run)


if __name__ == '__main__':
    main()
