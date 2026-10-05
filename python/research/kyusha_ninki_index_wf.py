# -*- coding: utf-8 -*-
"""
厩舎穴指数（厩舎指数の帯 × 基準人気の帯）の設計と walk-forward 検証（研究用・DB書き込みなし）
指数 = その区分の「同じ年・同じ基準オッズ帯の平均を上回った複勝払戻」の平均 × n/(n+k)（縮小推定）
毎年 Y について Y年より前の全データで区分表を作り直し、Y年の馬を採点する。新馬は除外。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kyusha_multi_screen import load, prep  # noqa
import numpy as np, pandas as pd
pd.set_option("display.width", 260)

KI_EDGES = [-999, 0, 5, 8, 10, 12, 15, 20, 999]
KI_LAB = ["<0", "0-5", "5-8", "8-10", "10-12", "12-15", "15-20", "20+"]
NK_EDGES = [0, 1, 2, 3, 5, 7, 9, 11, 13, 99]
NK_LAB = ["1", "2", "3", "4-5", "6-7", "8-9", "10-11", "12-13", "14+"]

d = prep(load())
d = d[~d.shinba & d.ninki.notna() & d.ki.notna()].copy()
d["kb"] = pd.cut(d.ki, KI_EDGES, right=False, labels=KI_LAB).astype(str)
d["nb"] = pd.cut(d.ninki, NK_EDGES, labels=NK_LAB).astype(str)


def trim_mean(v):
    v = pd.Series(v); hits = v[v > 0].sort_values(ascending=False)
    k = int(np.ceil(len(hits) * 0.01))
    return hits.iloc[k:].sum() / len(v) if len(v) else np.nan


for p in ("place", "win"):
    d[p + "_b"] = d.groupby(["y", "ob"])[p].transform("mean")
    d[p + "_bt"] = d.groupby(["y", "ob"])[p].transform(trim_mean)
    d[p + "_x"] = d[p] - d[p + "_b"]

YEARS = [2022, 2023, 2024, 2025, 2026]


def score(k):
    parts = []
    for Y in YEARS:
        tr, te = d[d.y < Y], d[d.y == Y].copy()
        g = tr.groupby(["kb", "nb"]).place_x.agg(["mean", "size"])
        g["s"] = g["mean"] * g["size"] / (g["size"] + k)
        te["score"] = pd.MultiIndex.from_frame(te[["kb", "nb"]]).map(g["s"].to_dict().get).astype(float)
        parts.append(te)
    return pd.concat(parts)


BANDS = [("+15以上", 15, 999), ("+8〜15", 8, 15), ("+3〜8", 3, 8), ("−3〜+3", -3, 3), ("−8〜−3", -8, -3), ("−8未満", -999, -8)]
for k in (100, 300):
    t = score(k)
    rows = []
    for name, lo, hi in BANDS:
        x = t[(t.score >= lo) & (t.score < hi)]
        if not len(x):
            continue
        r = {"帯": name, "n": len(x), "年平均": len(x) / 5, "単勝": x.win.mean(), "複勝": x.place.mean(),
             "3着内率": (x.fin <= 3).mean() * 100, "オッズ中央値": x.odds.median(),
             "複差": x.place_x.mean(), "複差1%除外": trim_mean(x.place) - x.place_bt.mean(), "単差": x.win_x.mean()}
        for Y in YEARS:
            r[f"複{str(Y)[2:]}"] = x[x.y == Y].place_x.mean()
        rows.append(r)
    print(f"\n## 縮小 k={k}（2022〜2026、毎年その年より前のデータで区分表を作り直し）")
    print(pd.DataFrame(rows).round(1).to_string(index=False))

# 本番相当（全期間）の区分表 k=300
g = d.groupby(["kb", "nb"]).place_x.agg(["mean", "size"])
g["s"] = g["mean"] * g["size"] / (g["size"] + 300)
print("\n## 全期間（2020〜2026）の区分表 k=300: 指数値")
print(g["s"].unstack().reindex(index=KI_LAB, columns=NK_LAB).round(1).to_string())
print(g["size"].unstack().reindex(index=KI_LAB, columns=NK_LAB).to_string())
