# -*- coding: utf-8 -*-
"""sc の各シグナルの実力を測る（先読みなし。sc_wf.js wf3 の出力を使用、2021-2026、新馬除外）"""
import sys, io, os, json
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
pd.set_option("display.width", 250)
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
d = pd.DataFrame(json.load(open(os.path.join(ROOT, ".scratch", "sc_wf_wf3.json"))))
d = d[(d.y >= 2021) & (d.shinba == 0) & d.odds.between(1, 999)].copy()
d["ob"] = pd.cut(d.odds, [1, 2, 3, 5, 10, 15, 30, 50, 1000], right=False).astype(str)
for p in ("win", "place"):
    d[p + "_x"] = d[p] - d.groupby(["y", "ob"])[p].transform("mean")   # 同じ年・同じオッズ帯の平均との差
SIG = ["s_idx", "s_combo", "s_kyusha", "s_joho", "s_gap", "s_pace", "s_goal", "s_yaji", "s_oi", "s_down"]
NAME = {"s_idx": "A.指数(EX/本命)", "s_combo": "B.騎手×厩舎", "s_kyusha": "C.厩舎穴", "s_joho": "D.情報指数", "s_gap": "D'.市場過小評価",
        "s_pace": "E.展開", "s_goal": "展開予測≤2", "s_yaji": "調教矢印↑", "s_oi": "追切上位25%", "s_down": "調教矢印↓(−2)"}
YEARS = [2021, 2022, 2023, 2024, 2025, 2026]

print("## 1. 単独で見た効果（そのシグナルの値ごと、複勝の同オッズ平均との差）")
for s in SIG:
    for v, x in d.groupby(s):
        if v == 0 and s != "s_down":
            continue
        yr = " / ".join(f"{x[x.y == y].place_x.mean():+.1f}" for y in YEARS)
        print(f"{NAME[s]:<14} 値{v:+d} n={len(x):>7,} 複勝差{x.place_x.mean():+5.1f} 単勝差{x.win_x.mean():+6.1f} 年別複勝[{yr}]")

print("\n## 2. ほかのシグナルの影響を除いた正味の効果（重回帰、各シグナルの値をダミー変数化、複勝の差を目的変数）")
X = pd.get_dummies(d[SIG].astype(str), drop_first=False)
X = X[[c for c in X.columns if not c.endswith("_0")]].astype(float)   # 0（シグナルなし）を基準
X["ab"] = d["ab"].astype(float)
X.insert(0, "const", 1.0)
rows = {}
for label, mask in [("2021-23", d.y <= 2023), ("2024-26", d.y >= 2024)] + [(str(y), d.y == y) for y in YEARS]:
    Xm, ym = X[mask.values].to_numpy(), d.loc[mask, "place_x"].to_numpy()
    beta, *_ = np.linalg.lstsq(Xm, ym, rcond=None)
    rows[label] = pd.Series(beta, index=X.columns)
B = pd.DataFrame(rows)
B["n(2024-26)"] = X[(d.y >= 2024).values].sum().astype(int)
print(B.round(1).to_string())
