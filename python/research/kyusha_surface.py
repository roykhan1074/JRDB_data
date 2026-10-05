# -*- coding: utf-8 -*-
"""
厩舎指数シグナルの境目の確認と、下見に使っていない2020年での答え合わせ（研究用）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kyusha_multi_screen import load, prep  # noqa
import numpy as np, pandas as pd
pd.set_option("display.width", 250)

d = prep(load())
d = d[~d.shinba].copy()
for p in ("place", "win"):
    d[p + "_b"] = d.groupby(["y", "ob"])[p].transform("mean")
    d[p + "_x"] = d[p] - d[p + "_b"]

print("## 厩舎指数の値 × 基準オッズ（2020〜2026、新馬除外）: 複勝差 / n")
kb = pd.cut(d.ki, [-99, 0, 5, 10, 15, 20, 99], right=False, labels=["<0", "0-5", "5-10", "10-15", "15-20", "20+"])
obb = pd.cut(d.odds, [10, 15, 20, 30, 50, 100, 1000], right=False, labels=["10-15", "15-20", "20-30", "30-50", "50-100", "100+"])
g = d.groupby([kb, obb]).agg(差=("place_x", "mean"), n=("place", "size"), 単差=("win_x", "mean"))
print(g.差.unstack().round(1).to_string()); print(g.n.unstack().to_string())
print("\n単勝差"); print(g.単差.unstack().round(1).to_string())

print("\n## 厩舎指数のレース内順位 × 基準オッズ: 複勝差 / n")
rb = pd.cut(d.ki_rank, [0, 1, 2, 3, 5, 99], labels=["1位", "2位", "3位", "4-5位", "6位~"])
g = d.groupby([rb, obb]).agg(差=("place_x", "mean"), n=("place", "size"))
print(g.差.unstack().round(1).to_string()); print(g.n.unstack().to_string())

print("\n## 人気順位−厩舎指数順位 × 人気順位−IDM順位: 複勝差 / n")
a = pd.cut(d.ninki - d.ki_rank, [-99, 0, 3, 5, 8, 99], right=False, labels=["<0", "0-2", "3-4", "5-7", "8+"])
b = pd.cut(d.ninki - d.idm_rank, [-99, 0, 3, 5, 8, 99], right=False, labels=["<0", "0-2", "3-4", "5-7", "8+"])
g = d.groupby([a, b]).agg(差=("place_x", "mean"), n=("place", "size"))
print("（行=厩舎のずれ、列=IDMのずれ）"); print(g.差.unstack().round(1).to_string()); print(g.n.unstack().to_string())

print("\n## 2020年だけで答え合わせ（下見は2021〜2026で実施）")
y0 = d[d.y == 2020]
for name, m in [("IDMも厩舎も人気より3上", ((y0.ninki - y0.idm_rank) >= 3) & ((y0.ninki - y0.ki_rank) >= 3)),
                ("IDMだけ人気より3上", ((y0.ninki - y0.idm_rank) >= 3) & ((y0.ninki - y0.ki_rank) < 3)),
                ("厩舎だけ人気より3上", ((y0.ninki - y0.idm_rank) < 3) & ((y0.ninki - y0.ki_rank) >= 3)),
                ("厩舎指数≥10×30倍以上", (y0.ki >= 10) & (y0.odds >= 30)),
                ("厩舎3位以内×30倍以上", (y0.ki_rank <= 3) & (y0.odds >= 30))]:
    s = y0[m]
    print(f"{name}: n={len(s)} 複勝{s.place.mean():.1f}% 差{s.place_x.mean():+.1f} 単勝{s.win.mean():.1f}% 単差{s.win_x.mean():+.1f}")
