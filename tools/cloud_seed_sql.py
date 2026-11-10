# -*- coding: utf-8 -*-
"""把本地演示库 data/jifen.db 导出成云数据库（PostgreSQL）的种子 SQL

用法：python tools/cloud_seed_sql.py [--db data/jifen.db] [--out tools/_cloud_seed.sql]
输出按表分段，每段一条 INSERT（多值），方便逐条贴进 workbuddy_cloudservice_db_exec_sql。
"""
import argparse
import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def q(v):
    if v is None:
        return 'NULL'
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def mask(p):
    p = str(p or '')
    return p[:3] + '****' + p[-4:] if len(p) == 11 else p


def rows_sql(table, cols, rows):
    if not rows:
        return '-- %s: 无数据' % table
    vals = []
    for r in rows:
        vals.append('(' + ', '.join(q(r[c]) for c in cols) + ')')
    return 'INSERT INTO %s (%s) VALUES\n%s\nON CONFLICT DO NOTHING;' % (
        table, ', '.join(cols), ',\n'.join(vals))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=os.path.join(BASE, 'data', 'jifen.db'))
    ap.add_argument('--out', default=os.path.join(BASE, 'tools', '_cloud_seed.sql'))
    ap.add_argument('--txns', type=int, default=0, help='只导最近 N 条流水，0=全部')
    a = ap.parse_args()

    c = sqlite3.connect(a.db)
    c.row_factory = sqlite3.Row
    parts = []

    # 设置
    rows = [dict(r) for r in c.execute('select k, v from jf_settings')]
    parts.append(('settings', rows_sql('jf_settings', ['k', 'v'], rows)))

    # 商品
    rows = [dict(r) for r in c.execute(
        'select id,name,cat,icon,spec,points,stock,sold,limit_per,desc,status,sort from jf_goods')]
    for r in rows:
        r['descr'] = r.pop('desc')
    parts.append(('goods', rows_sql(
        'jf_goods',
        ['id', 'name', 'cat', 'icon', 'spec', 'points', 'stock', 'sold', 'limit_per', 'descr', 'status', 'sort'],
        rows)))

    # 积分规则
    rows = [dict(r) for r in c.execute(
        'select id,name,cat,points,unit,desc,enabled,sort from jf_rules')]
    for r in rows:
        r['descr'] = r.pop('desc')
        r['enabled'] = 1 if r['enabled'] else 0
    parts.append(('rules', rows_sql(
        'jf_rules', ['id', 'name', 'cat', 'points', 'unit', 'descr', 'enabled', 'sort'], rows)))

    # 红黑榜
    rows = [dict(r) for r in c.execute(
        'select id,kind,title,who,grp,points,desc,happen,img,sort,created from jf_cases')]
    for r in rows:
        r['descr'] = r.pop('desc')
    parts.append(('cases', rows_sql(
        'jf_cases', ['id', 'kind', 'title', 'who', 'grp', 'points', 'descr', 'happen', 'img', 'sort', 'created'],
        rows)))

    # 积分账户（不迁身份证原文，只留空；手机号保留 + 掩码）
    rows = []
    for r in c.execute('select * from jf_accounts'):
        d = dict(r)
        rows.append({
            'id': d['id'], 'name': d['name'], 'grp': d.get('grp') or '',
            'hu_zhu': d.get('hu_zhu') or '', 'phone': d.get('phone') or '',
            'phone_mask': mask(d.get('phone')),
            'code': d.get('code') or '', 'points': d.get('points') or 0,
            'earned': d.get('earned') or 0, 'spent': d.get('spent') or 0,
            'status': d.get('status') or '正常',
        })
    parts.append(('accounts', rows_sql(
        'jf_accounts',
        ['id', 'name', 'grp', 'hu_zhu', 'phone', 'phone_mask', 'code', 'points', 'earned', 'spent', 'status'],
        rows)))

    # 订单
    rows = []
    for r in c.execute('select * from jf_orders'):
        d = dict(r)
        items = d.get('items') or '[]'
        try:
            import json
            arr = json.loads(items)
            txt = '、'.join('%s%s' % (i.get('gname') or i.get('name') or '',
                                     (' x%d' % i['qty']) if i.get('qty', 1) > 1 else '') for i in arr)
        except Exception:
            txt = ''
        rows.append({
            'id': d['id'], 'acc_id': d['acc_id'], 'code': d['code'],
            'items_text': txt or '兑换商品', 'points': d.get('points') or 0,
            'status': d.get('status') or '待领取', 'created': d.get('created'),
        })
    parts.append(('orders', rows_sql(
        'jf_orders', ['id', 'acc_id', 'code', 'items_text', 'points', 'status', 'created'], rows)))

    # 流水
    if a.txns:
        rows = [dict(r) for r in c.execute(
            'select id,acc_id,reason,points,balance,operator,created from jf_txns order by created desc limit ?',
            (a.txns,))][::-1]
    else:
        rows = [dict(r) for r in c.execute(
            'select id,acc_id,reason,points,balance,operator,created from jf_txns order by created')]
    parts.append(('txns', rows_sql(
        'jf_txns', ['id', 'acc_id', 'reason', 'points', 'balance', 'operator', 'created'], rows)))

    with open(a.out, 'w', encoding='utf-8') as fh:
        for name, sql in parts:
            fh.write('-- ==== %s ====\n%s\n\n' % (name, sql))
    print('已生成', a.out, os.path.getsize(a.out), 'bytes')
    for name, sql in parts:
        print('  %-9s %5d 字符' % (name, len(sql)))


if __name__ == '__main__':
    main()
