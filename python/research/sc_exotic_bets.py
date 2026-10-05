# -*- coding: utf-8 -*-
"""
sc 上位3頭のボックス、sc1位を軸にした5頭流しの回収率（研究用、先読みなしの sc = sc_wf.js wf4 の出力）。
順位: sc の高い順、同点は基準オッズの低い順。比較として人気順（基準オッズの低い順）で同じ買い方をした場合も出す。
払戻は T_HJC（当たった組み合わせのみ記録）。2022〜2026年、芝ダ、新馬戦除外。
"""
import sys, os, json, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from exotic_wf import load_hjc, parse   # stdout の UTF-8 化もこちらで済む
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
YEARS = [2022, 2023, 2024, 2025, 2026]

d = pd.DataFrame(json.load(open(os.path.join(ROOT, ".scratch", "sc_wf_wf4.json"))))
d = d[(d.y >= 2022) & (d.shinba == 0) & d.odds.between(1, 999)].copy()
um, sp = parse(load_hjc())

recs = []
for rid, g in d.groupby("rid"):
    if rid not in um or len(g) < 7:
        continue
    y = int(g.y.iloc[0])
    by_sc = g.sort_values(["sc", "odds"], ascending=[False, True]).uma.astype(int).tolist()
    by_pop = g.sort_values("odds").uma.astype(int).tolist()
    axis_sc = int(g.sort_values(["sc", "odds"], ascending=[False, True]).sc.iloc[0])
    for order, lab in ((by_sc, "sc"), (by_pop, "人気")):
        top3 = order[:3]
        ax, partners = order[0], order[1:6]
        # 馬連ボックス 3点
        pays = um[rid]
        u_box = sum(v for k, v in pays.items() if k <= set(top3))
        # 三連複ボックス 1点
        s_box = sp.get(rid, {}).get(frozenset(top3), 0)
        # 馬連流し 5点（軸-相手）
        u_nag = sum(v for k, v in pays.items() if ax in k and (set(k) - {ax}) <= set(partners))
        # 三連複 軸1頭流し 10点（軸 + 相手5頭から2頭）
        s_nag = sum(v for k, v in sp.get(rid, {}).items() if ax in k and (set(k) - {ax}) <= set(partners))
        for bet, cost, pay in (("馬連ボックス(3点)", 300, u_box), ("三連複ボックス(1点)", 100, s_box),
                               ("馬連 軸1位→相手5頭(5点)", 500, u_nag), ("三連複 軸1位→相手5頭(10点)", 1000, s_nag)):
            recs.append(dict(rid=rid, y=y, order=lab, bet=bet, cost=cost, pay=pay, axis_sc=axis_sc))
R = pd.DataFrame(recs)


def show(x, lab):
    pays = x.pay[x.pay > 0].sort_values(ascending=False)
    k = int(len(pays) * 0.01)
    rr = x.pay.sum() / x.cost.sum() * 100
    trim = (x.pay.sum() - pays.iloc[:k].sum()) / x.cost.sum() * 100
    yr = " / ".join(f"{x[x.y == Y].pay.sum() / x[x.y == Y].cost.sum() * 100:.0f}" for Y in YEARS)
    print(f"| {lab} | {len(x):,} | {(x.pay > 0).mean() * 100:.1f}% | **{rr:.1f}%** | {yr} | {trim:.1f}% | {pays.mean():,.0f}円 |")


for bet in R.bet.unique():
    print(f"\n### {bet}")
    print("| 選び方 | レース数 | 的中率 | 回収率 | 年別（2022〜2026） | 当たり上位1%除外 | 当たったときの平均払戻 |")
    print("|---|---:|---:|---:|---|---:|---:|")
    for lab, m in (("sc順", (R.order == "sc")), ("人気順（比較）", (R.order == "人気")),
                   ("sc順・軸のsc 7以上", (R.order == "sc") & (R.axis_sc >= 7)),
                   ("sc順・軸のsc 9以上", (R.order == "sc") & (R.axis_sc >= 9))):
        show(R[m & (R.bet == bet)], lab)
