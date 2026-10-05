# -*- coding: utf-8 -*-
"""
厩舎指数10以上 × 基準人気（回収率分析ページと同じ切り口）の検証（研究用）
- 実際の単勝/複勝回収率、同年・同基準オッズ帯平均との差、同じ人気で厩舎指数10未満の馬との比較
- 年別（2020〜2026）、払戻上位1%除外（基準側も同様）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kyusha_multi_screen import load, prep  # noqa
import numpy as np, pandas as pd
pd.set_option("display.width", 260)

d = prep(load())
d = d[~d.shinba & d.ninki.notna()].copy()


def trim_mean(v):
    v = pd.Series(v); hits = v[v > 0].sort_values(ascending=False)
    k = int(np.ceil(len(hits) * 0.01))
    return hits.iloc[k:].sum() / len(v) if len(v) else np.nan


for p in ("place", "win"):
    d[p + "_b"] = d.groupby(["y", "ob"])[p].transform("mean")
    d[p + "_bt"] = d.groupby(["y", "ob"])[p].transform(trim_mean)
    d[p + "_x"] = d[p] - d[p + "_b"]
d["nb"] = pd.cut(d.ninki, [0, 1, 2, 3, 5, 7, 9, 12, 99], labels=["1", "2", "3", "4-5", "6-7", "8-9", "10-12", "13~"])
YRS = range(2020, 2027)


def table(m, title):
    rows = []
    for nb, x in d[m].groupby("nb"):
        o = d[~m & (d.nb == nb)]
        r = {"人気": nb, "n": len(x), "単勝": x.win.mean(), "複勝": x.place.mean(),
             "単差": x.win_x.mean(), "複差": x.place_x.mean(),
             "単差1%除外": trim_mean(x.win) - x.win_bt.mean(), "複差1%除外": trim_mean(x.place) - x.place_bt.mean(),
             "同人気の他馬 単勝": o.win.mean(), "同人気の他馬 複勝": o.place.mean()}
        for Y in YRS:
            r[f"複{str(Y)[2:]}"] = x[x.y == Y].place_x.mean()
        r["単+年"] = sum(x[x.y == Y].win_x.mean() > 0 for Y in YRS)
        r["複+年"] = sum(x[x.y == Y].place_x.mean() > 0 for Y in YRS)
        rows.append(r)
    print(f"\n### {title}")
    print(pd.DataFrame(rows).round(1).to_string(index=False))


table(d.ki >= 10, "厩舎指数10以上 × 基準人気（2020〜2026、新馬除外）")
table(d.ki.between(10, 20, "left"), "厩舎指数10〜20")
table(d.ki >= 20, "厩舎指数20以上")
# 下位人気をまとめて
for lo in (6, 8, 10):
    x = d[(d.ki >= 10) & (d.ninki >= lo)]
    print(f"\n厩舎指数10以上×{lo}番人気以下: n={len(x)} 単勝{x.win.mean():.1f}% 複勝{x.place.mean():.1f}% "
          f"単差{x.win_x.mean():+.1f} 複差{x.place_x.mean():+.1f} 単差1%除外{trim_mean(x.win)-x.win_bt.mean():+.1f} 複差1%除外{trim_mean(x.place)-x.place_bt.mean():+.1f}")
    print("  年別 単勝/複勝: " + "  ".join(f"{Y}:{x[x.y==Y].win.mean():.0f}/{x[x.y==Y].place.mean():.0f}(n={int((x.y==Y).sum())})" for Y in YRS))
    print("  年別 複差: " + " ".join(f"{x[x.y==Y].place_x.mean():+.1f}" for Y in YRS) + " ｜ 単差: " + " ".join(f"{x[x.y==Y].win_x.mean():+.1f}" for Y in YRS))
