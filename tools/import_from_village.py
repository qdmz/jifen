# -*- coding: utf-8 -*-
"""从村居管理系统（village.db）迁移积分超市数据到独立库。

用法：
    python tools/import_from_village.py --src "E:\\down\\VillageManagementSystem\\village.db"
    python tools/import_from_village.py --src ... --dst data/jifen.db --with-users --with-ledger

默认行为：
    · 复制全部 jf_* 表（账户 / 流水 / 订单 / 商品 / 规则 / 设置 / 案例 / 家庭档案）
    · 不复制账号（app_users）——除非加 --with-users，加上后可直接用村居系统的账号密码登录
    · 不复制户籍台账（ledger_rows）——除非加 --with-ledger，加上后「从户籍导入」「按户籍地址归户」可用
覆盖策略：按主键 INSERT OR REPLACE（重复执行不会产生重复数据）。
"""
import os
import sys
import json
import sqlite3
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import jifen                                    # noqa: E402

JF_TABLES = ['jf_accounts', 'jf_txns', 'jf_goods', 'jf_orders', 'jf_order_items',
             'jf_rules', 'jf_settings', 'jf_cases', 'jf_hh']


def table_cols(conn, schema, table):
    return [r[1] for r in conn.execute('PRAGMA %s.table_info(%s)' % (schema, table))]


def copy_table(src, dst, name):
    has_src = src.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    has_dst = dst.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    if not has_src or not has_dst:
        return None
    cols = [c for c in table_cols(src, 'main', name) if c in table_cols(dst, 'main', name)]
    if not cols:
        return 0
    cl = ','.join('"%s"' % c for c in cols)
    before = dst.execute('SELECT COUNT(*) FROM "%s"' % name).fetchone()[0]
    dst.execute('INSERT OR REPLACE INTO "%s" (%s) SELECT %s FROM src."%s"' % (name, cl, cl, name))
    dst.commit()
    after = dst.execute('SELECT COUNT(*) FROM "%s"' % name).fetchone()[0]
    return {'table': name, 'src': src.execute('SELECT COUNT(*) FROM "%s"' % name).fetchone()[0],
            'dst_before': before, 'dst_after': after}


def copy_ledger(src, dst):
    has_src = src.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ledger_rows'").fetchone()
    if not has_src:
        return None
    dst.execute("CREATE TABLE IF NOT EXISTS ledger_rows (lid TEXT, seq INTEGER, data TEXT)")
    dst.commit()
    n_src = src.execute("SELECT COUNT(*) FROM ledger_rows WHERE lid='hukou'").fetchone()[0]
    if not n_src:
        return {'table': 'ledger_rows(hukou)', 'src': 0, 'dst_before': 0, 'dst_after': 0}
    dst.execute("DELETE FROM ledger_rows WHERE lid='hukou'")
    dst.execute("INSERT INTO ledger_rows(lid,seq,data) SELECT lid,seq,data FROM src.ledger_rows"
                " WHERE lid='hukou'")
    dst.commit()
    return {'table': 'ledger_rows(hukou)', 'src': n_src, 'dst_before': 0,
            'dst_after': dst.execute("SELECT COUNT(*) FROM ledger_rows WHERE lid='hukou'").fetchone()[0]}


def main():
    ap = argparse.ArgumentParser(description='从村居系统 village.db 迁移积分超市数据')
    ap.add_argument('--src', required=True, help='源库路径（village.db）')
    ap.add_argument('--dst', default=os.path.join(ROOT, 'data', 'jifen.db'), help='目标库路径')
    ap.add_argument('--with-users', action='store_true', help='同时复制账号表 app_users（沿用村居系统账号密码）')
    ap.add_argument('--only-users', action='store_true', help='只复制账号表（不搬积分数据，配合 tools/seed_demo_site.py 做演示站）')
    ap.add_argument('--with-ledger', action='store_true', help='同时复制户籍台账（ledger_rows 中 lid=hukou）')
    ap.add_argument('--dry-run', action='store_true', help='只统计不写入')
    args = ap.parse_args()

    if not os.path.isfile(args.src):
        print('源库不存在：%s' % args.src)
        return 2
    os.makedirs(os.path.dirname(os.path.abspath(args.dst)), exist_ok=True)
    if os.path.abspath(args.src) == os.path.abspath(args.dst):
        print('源库与目标库相同，无需迁移')
        return 2

    jifen.set_db(args.dst)
    if not args.dry_run:
        jifen.init(seed=False)                   # 目标库只建表，不预置商品/规则（避免和源库重复）
    print('目标库：%s' % args.dst)

    src = sqlite3.connect('file:%s?mode=ro' % args.src.replace('\\', '/'), uri=True, timeout=30)
    dst = sqlite3.connect(args.dst, timeout=30)
    dst.execute("ATTACH DATABASE ? AS src", (args.src,))
    rows = []
    try:
        if args.dry_run:
            for t in ([] if args.only_users else JF_TABLES):
                try:
                    n = src.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
                except sqlite3.OperationalError:
                    continue
                rows.append({'table': t, 'src': n, 'dst_before': 0, 'dst_after': 0})
        else:
            for t in ([] if args.only_users else JF_TABLES):
                r = copy_table(src, dst, t)
                if r:
                    rows.append(r)
            if args.with_users or args.only_users:
                r = copy_table(src, dst, 'app_users')
                if r:
                    rows.append(r)
            if args.with_ledger:
                r = copy_ledger(src, dst)
                if r:
                    rows.append(r)
            # 源库没有商品/规则时，补上默认的一套，保证开箱可用
            if not args.only_users and not dst.execute('SELECT COUNT(*) FROM jf_goods').fetchone()[0]:
                jifen.init(seed=True)
    finally:
        try:
            dst.execute('DETACH DATABASE src')
        except Exception:
            pass
        dst.close()
        src.close()

    print('%-26s %8s %10s %10s' % ('表', '源', '导入前', '导入后'))
    for r in rows:
        print('%-26s %8d %10d %10d' % (r['table'], r['src'], r['dst_before'], r['dst_after']))
    if args.dry_run:
        print('\n（--dry-run 未写入）')
    else:
        print('\n完成。启动：python app.py  （首次启动会自动补齐积分码、按户归集）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
