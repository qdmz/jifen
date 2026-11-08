# -*- coding: utf-8 -*-
"""生成一套「演示站」数据：12 户 / 30 名村民 / 流水 / 兑换单 / 红黑榜。

适用：对外演示、培训、截图——不含任何真实村民信息。
账号（后台登录）不在这里造，用 `tools/import_from_village.py --only-users` 从村居系统带过来，
或用 `tools/reset_pwd.py` 新建。

用法：
    python tools/seed_demo_site.py            # 重建演示数据（先清空 jf_* 业务数据）
    python tools/seed_demo_site.py --clear    # 只清空
    python tools/seed_demo_site.py --db data/jifen.db
"""
import os
import sys
import argparse
import sqlite3
import secrets
import time
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import jifen                                     # noqa: E402

NOW = time.strftime('%Y-%m-%d %H:%M:%S')

# 6 个村民组 × 2 户；户主 + 成员（姓名全部为演示用虚构姓名）
HOUSES = [
    ('白岩塘组', '张建国', [('李秀英', '配偶'), ('张明', '子')]),
    ('白岩塘组', '王德明', [('刘桂芳', '配偶')]),
    ('白粉墙组', '陈志强', [('杨小梅', '配偶'), ('陈雨', '女')]),
    ('白粉墙组', '赵长福', [('孙玉兰', '配偶')]),
    ('桐木坪组', '周国平', [('吴春花', '配偶'), ('周浩', '子')]),
    ('桐木坪组', '徐建华', [('黄翠平', '配偶')]),
    ('榜上组', '胡明生', [('林秀珍', '配偶')]),
    ('榜上组', '罗大山', [('邓小燕', '配偶'), ('罗宇', '子')]),
    ('楼子屋组', '彭志远', [('曾丽', '配偶')]),
    ('楼子屋组', '唐德贵', [('蒋红梅', '配偶'), ('唐磊', '子')]),
    ('曾家湾组', '谢长发', [('谭小芳', '配偶')]),
    ('曾家湾组', '贺建平', [('廖桂英', '配偶'), ('贺敏', '女')]),
]

# 每条流水的分值（按 jf_rules 里的事由取，取不到就用兜底文案）
EARN_PLAN = [
    ('子女无辍学、考入大专及以上院校', 100),
    ('获评“星级文明户”“最美家庭”', 50),
    ('红白事简办、不铺张浪费', 30),
    ('门前三包、卫生评比优秀', 20),
    ('参加村集体环境整治、义务劳动', 10),
    ('助人为乐、见义勇为、拾金不昧', 10),
    ('参加护林防火、防汛抗旱值守', 10),
    ('参加村民会议、村民代表会议', 5),
    ('按时缴纳城乡居民医保、养老保险', 5),
]

CASES = [
    ('red', '义务清扫村道三个月', '张建国', '白岩塘组', 20,
     '坚持每天清扫自家门前到村口约 300 米路面，带动周边 6 户一起参与，村道环境明显改善。'),
    ('red', '主动照顾独居老人', '陈志强', '白粉墙组', 15,
     '长期为同组独居老人代购米面、送医取药，老人家属于本月送来感谢信。'),
    ('black', '房前屋后乱堆杂物', '（某户）', '桐木坪组', -5,
     '经两次提醒仍未清理，影响邻里通行，限期整改后复查。'),
]


def _uid(p):
    return p + secrets.token_hex(8)


def clear(conn, keep_goods=True):
    for t in ('jf_txns', 'jf_order_items', 'jf_orders', 'jf_accounts', 'jf_cases'):
        conn.execute('DELETE FROM "%s"' % t)
    if not keep_goods:
        conn.execute('DELETE FROM jf_goods')
    conn.commit()


def main():
    ap = argparse.ArgumentParser(description='生成积分超市演示数据')
    ap.add_argument('--db', default=os.environ.get('JF_DB') or os.path.join(ROOT, 'data', 'jifen.db'))
    ap.add_argument('--clear', action='store_true', help='只清空演示数据')
    args = ap.parse_args()

    jifen.set_db(args.db)
    jifen.init()                                  # 建表 + 预置商品/规则（幂等）
    conn = sqlite3.connect(args.db, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        clear(conn)
        if args.clear:
            print('已清空演示数据（账户/流水/订单/红黑榜）')
            return 0

        rules = {r['name']: r['points'] for r in conn.execute("SELECT name,points FROM jf_rules")}
        goods = conn.execute("SELECT * FROM jf_goods WHERE status='上架' ORDER BY sort, points").fetchall()
        if not goods:
            print('没有上架商品，先运行 python app.py 让系统预置商品')
            return 1

        accounts = []                            # (id, name, grp, hu_zhu, seq, phone, code)
        seq_ph = 1
        code_n = 700001
        house_no = 0
        for grp, zhu, members in HOUSES:
            house_no += 1
            people = [(zhu, '户主')] + members
            for i, (nm, rel) in enumerate(people):
                aid = _uid('a_')
                phone = '138%08d' % seq_ph
                seq_ph += 1
                accounts.append({'id': aid, 'name': nm, 'grp': grp, 'hu': grp + '·' + zhu,
                                 'zhu': zhu, 'seq': i + 1, 'phone': phone,
                                 'addr': '%s%d号' % (grp, house_no),
                                 'code': str(code_n), 'points': 0, 'earned': 0, 'spent': 0})
                code_n += 1
        # 「测试」演示账户（不在任何户里，便于单独演示）
        accounts.append({'id': _uid('a_'), 'name': '测试', 'grp': '白岩塘组', 'hu': '白岩塘组·测试',
                         'zhu': '测试', 'seq': 1, 'phone': '13600000000', 'addr': '白岩塘组99号',
                         'code': '888888', 'points': 0, 'earned': 0, 'spent': 0})

        # ---- 加分流水 ----
        txn_rows = []
        for idx, a in enumerate(accounts):
            n = 2 + (idx % 3)                      # 每人 2~4 笔，且总分不低于 160
            bal = 0
            k = 0
            while k < n or bal < 160:
                reason, pts = EARN_PLAN[(idx + k) % len(EARN_PLAN)]
                if reason not in rules:
                    pts = 5
                k += 1
                bal += pts
                stamp = (datetime.datetime(2026, 6, 1) +
                         datetime.timedelta(days=idx * 2 + k * 11, hours=9)).strftime('%Y-%m-%d %H:%M:%S')
                txn_rows.append((_uid('t_'), a['id'], a['name'], a['grp'], 'earn', pts, bal,
                                 reason, '', '村委干部', stamp))
            a['points'] = bal
            a['earned'] = bal

        # ---- 兑换单 ----
        orders = []          # (acc_index, [(goods_index, qty)], status)
        orders.append((0, [(0, 1), (2, 1)], '待领取'))
        orders.append((1, [(1, 1)], '已领取'))
        orders.append((4, [(0, 2)], '待领取'))
        orders.append((6, [(3, 1)], '已取消'))
        order_rows, item_rows, spend_rows = [], [], []
        stock_delta, sold_delta = {}, {}
        cheapest = min(goods, key=lambda x: x['points'])
        for acc_i, items, status in orders:
            a = accounts[acc_i]
            picked = []
            for gi, qty in items:
                g = goods[gi % len(goods)]
                picked.append((g, qty))
            total = sum(g['points'] * q for g, q in picked)
            if total > max(0, a['points'] - 10):          # 余额不足：只留最便宜的一件
                picked = [(cheapest, 1)]
                total = cheapest['points']
            its = []
            for g, qty in picked:
                line = g['points'] * qty
                its.append((_uid('oi_'), None, g['id'], g['name'], g['icon'], qty, line))
                if status != '已取消':
                    stock_delta[g['id']] = stock_delta.get(g['id'], 0) + qty
                    sold_delta[g['id']] = sold_delta.get(g['id'], 0) + qty
            oid = _uid('o_')
            its = [(x[0], oid) + x[2:] for x in its]
            item_rows.extend([(i[0], i[1], i[2], i[3], i[4], i[5], i[6]) for i in its])
            done = NOW if status == '已领取' else ''
            order_rows.append((oid, '%06d' % (100000 + len(order_rows) * 137 % 899999), a['id'],
                               a['name'], a['phone'], a['grp'], total, status, 'online',
                               ','.join('%s×%d' % (i[3], i[5]) for i in its), NOW, done,
                               '村委干部' if status != '待领取' else '', ''))
            label = '兑换：' + '、'.join('%s×%d' % (g['name'], q) for g, q in picked)
            if status == '已取消':
                # 兑换时扣分、取消时退回，净额为 0，流水上留两条痕
                spend_rows.append((a, -total, a['points'] - total, label, 'spend'))
                spend_rows.append((a, total, a['points'], '兑换取消退回', 'refund'))
            else:
                a['points'] -= total
                a['spent'] += total
                spend_rows.append((a, -total, a['points'], label, 'spend'))
        # ---- 写库 ----
        for a in accounts:
            conn.execute("INSERT INTO jf_accounts(id,name,grp,phone,idcard,points,earned,spent,"
                         "status,note,code,hu,hu_zhu,hu_seq,addr,hu_src,hu_lock,created,updated)"
                         " VALUES(?,?,?,?,'',?,?,?,'正常','',?,?,?,?,?,'演示',1,?,?)",
                         (a['id'], a['name'], a['grp'], a['phone'], a['points'], a['earned'],
                          a['spent'], a['code'], a['hu'], a['zhu'], a['seq'], a['addr'], NOW, NOW))
        for a, pts, bal, reason, kind in spend_rows:
            txn_rows.append((_uid('t_'), a['id'], a['name'], a['grp'], kind, pts, bal,
                             reason, '', '村民自助', NOW))
        conn.executemany("INSERT INTO jf_txns(id,acc_id,name,grp,kind,points,balance,reason,ref,operator,created)"
                         " VALUES(?,?,?,?,?,?,?,?,?,?,?)", txn_rows)
        for o in order_rows:
            conn.execute("INSERT INTO jf_orders(id,code,acc_id,name,phone,grp,points,status,src,items,"
                         "created,done_at,operator,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", o)
        conn.executemany("INSERT INTO jf_order_items(id,order_id,gid,gname,icon,qty,points)"
                         " VALUES(?,?,?,?,?,?,?)", item_rows)
        for gid, n in stock_delta.items():
            sold = sold_delta.get(gid, 0)
            conn.execute("UPDATE jf_goods SET stock=MAX(0,stock-?), sold=sold+?, updated=? WHERE id=?",
                         (n, sold, NOW, gid))
        for i, (kind, title, who, grp, pts, desc) in enumerate(CASES):
            conn.execute("INSERT INTO jf_cases(id,kind,title,who,grp,points,desc,img,happen,status,sort,"
                         "created,updated,operator) VALUES(?,?,?,?,?,?,?,'',?,'发布',?,?,?,?)",
                         (_uid('c_'), kind, title, who, grp, pts, desc,
                          '2026-11-0%d' % (3 + i), i, NOW, NOW, '村委干部'))
        conn.commit()

        n_acc = conn.execute("SELECT COUNT(*) FROM jf_accounts").fetchone()[0]
        n_hu = conn.execute("SELECT COUNT(DISTINCT hu) FROM jf_accounts").fetchone()[0]
        n_tx = conn.execute("SELECT COUNT(*) FROM jf_txns").fetchone()[0]
        n_od = conn.execute("SELECT COUNT(*) FROM jf_orders").fetchone()[0]
        print('演示数据已生成：%d 个账户 / %d 户 / %d 条流水 / %d 张兑换单 / %d 条红黑榜'
              % (n_acc, n_hu, n_tx, n_od, len(CASES)))
        print('查分演示：姓名「张建国」+ 手机 13800000001，或 姓名「测试」+ 积分码 888888')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
