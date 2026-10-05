# -*- coding: utf-8 -*-
"""
モデル確率 × 確定オッズ確率 のブレンド検証（研究用）
p ∝ exp(a*log(p_model) + b*log(p_market)) をレース内で正規化（条件付きロジット）。
a,b は「その年より前」の out-of-sample 予測だけでフィットする（walk-forward）。
ブレンドが確定オッズ単独より LogLoss で毎年勝てば、モデルは市場が織り込んでいない情報を持つ。
"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
df = pd.read_pickle(os.path.join(ROOT, ".scratch", "prob_pred_fund.pkl"))
df = df[df["mkt_final"].notna() & (df["mkt_final"] > 0)].copy()
df["lp_m"] = np.log(df["p_y_win"].clip(1e-6))
df["lp_k"] = np.log(df["mkt_final"].clip(1e-6))


def blend(d, a, b):
    z = a * d["lp_m"] + b * d["lp_k"]
    z = z - z.groupby(d["race_id"]).transform("max")
    e = np.exp(z)
    return e / e.groupby(d["race_id"]).transform("sum")


def ll(y, p):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def fit(d):
    # 勝ち馬の対数尤度（条件付きロジット）を最大化
    def nll(w):
        p = blend(d, w[0], w[1])
        return -np.log(p[d["y_win"] == 1].clip(1e-12)).mean()
    return minimize(nll, [0.3, 0.9], method="Nelder-Mead", options=dict(xatol=1e-3, fatol=1e-6)).x


rows = []
for Y in range(2023, 2027):
    tr = df[df["year"] < Y]
    te = df[df["year"] == Y].copy()
    a, b = fit(tr)
    te["p_blend"] = blend(te, a, b)
    rows.append((Y, len(te), a, b, ll(te["y_win"], te["mkt_final"]), ll(te["y_win"], te["p_blend"])))
    te.to_pickle(os.path.join(ROOT, ".scratch", f"blendf_{Y}.pkl"))
    print(f"{Y}: a(モデル)={a:.3f} b(オッズ)={b:.3f}  LogLoss 確定オッズ={rows[-1][4]:.5f} ブレンド={rows[-1][5]:.5f} 差={rows[-1][4]-rows[-1][5]:+.5f}")
