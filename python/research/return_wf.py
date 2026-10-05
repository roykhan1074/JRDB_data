# -*- coding: utf-8 -*-
"""
回収率を直接目標にしたモデルの walk-forward 検証（研究用・DB書き込みなし）
目的変数 = その馬の 複勝(または単勝) を100円買ったときの払戻額。
予測払戻が大きい上位の馬だけ買ったときの回収率を年ごとに確認する。
"""
import sys, io, os
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
import prob_wf as P

KIND = sys.argv[1] if len(sys.argv) > 1 else "place"   # place / win
PAY = "place_pay" if KIND == "place" else "win_pay"

df = P.prepare(P.fetch())
df = P.add_trailing(df)
df = df[df["shinba"] == 0].copy()            # 新馬戦は除外（上がり1位81.9%の比較対象と同じ母集団）
df[PAY] = df[PAY].fillna(0)
num, cat = P.feature_cols(df)
for c in cat:
    df[c] = df[c].fillna("NA").replace("", "NA").astype("category")
X = num + cat

# 払戻は外れ値（万馬券）が大きいので上限を設けて学習を安定させる（評価は実際の払戻で行う）
CAP = 2000 if KIND == "place" else 5000
out = []
for Y in range(2022, 2027):
    tr, te = df[df.year < Y], df[df.year == Y].copy()
    m = HistGradientBoostingRegressor(loss="squared_error", max_iter=400, max_depth=5, learning_rate=0.04,
                                      min_samples_leaf=500, l2_regularization=1.0,
                                      categorical_features="from_dtype", random_state=42,
                                      early_stopping=True, validation_fraction=0.1, n_iter_no_change=30)
    m.fit(tr[X], tr[PAY].clip(upper=CAP))
    te["pred"] = m.predict(te[X])
    out.append(te)
    print(f"{Y} 学習完了", flush=True)
o = pd.concat(out)
o.to_pickle(os.path.join(P.ROOT, ".scratch", f"ret_{KIND}.pkl"))

years = [2022, 2023, 2024, 2025, 2026]
def line(label, d):
    per = d.groupby("year")[PAY].mean().reindex(years)
    print(f"{label:<34}" + "".join(f"{v:8.1f}" for v in per.values) + f" | 全体 {d[PAY].mean():6.1f}%  n={len(d):,}  的中率{(d[PAY]>0).mean()*100:5.1f}%")

print(f"\n### {'複勝' if KIND=='place' else '単勝'}回収率（2022〜2026、新馬除外）")
print(" " * 34 + "".join(f"{y:>8}" for y in years))
line("全馬", o)
line("上がり指数1位（比較の基準）", o[o.agari_index_juni == 1])
# 予測払戻の上位 X%（年ごとの分位で判定＝その年の中での相対順位）
for q in (0.20, 0.10, 0.05, 0.02, 0.01):
    thr = o.groupby("year")["pred"].transform(lambda s: s.quantile(1 - q))
    line(f"予測払戻 上位{int(q*100)}%", o[o.pred >= thr])
# レース内で予測払戻1位の馬だけ
o["rk"] = o.groupby("race_id")["pred"].rank(ascending=False, method="first")
line("各レースの予測払戻1位", o[o.rk == 1])
line("各レースの予測払戻1位 かつ 上がり1位", o[(o.rk == 1) & (o.agari_index_juni == 1)])
