# -*- coding: utf-8 -*-
"""
一変指数: 勾配ブースティング版の walk-forward 検証（研究用）。
毎年 Y について、Y年より前の穴馬（基準オッズ10倍以上）で
  (a) 一変の区分 + 基準オッズ → 3着内の確率 p_full
  (b) 基準オッズだけ          → 3着内の確率 p_odds
を学習し、Y年の馬に「p_full − p_odds」（オッズから見込まれる3着内率に対する上乗せ）を付ける。
上乗せの帯ごとに単勝・複勝回収率を見る。区分の作り方は ippen_wf.groups と同じ（すべてレース前に確定する値）。
"""
import sys, io, os
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
pd.set_option("display.width", 250)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ippen_screen import load
from ippen_wf import groups, YEARS
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
MINLEAF = int(os.environ.get("MINLEAF", "400"))

d = load()
d = d[d["前走あり"] & d.q_uma.notna() & (d.odds >= 10)].reset_index(drop=True)
G = groups(d)
X = pd.DataFrame({g: G[g].astype("category").cat.codes for g in G.columns})
# 数値の変化量もそのまま入れる（区分の境目に縛られないように）
for name, s in {"厩舎指数差": d.kyusha_index - d.q_kyusha_index, "調教指数差": d.chokyo_index - d.q_chokyo_index,
                "追切指数差": d.oi_index - d.q_oi_index, "仕上指数差": d.shiage_index - d.q_shiage_index,
                "IDM差": d.idm - d.q_idm, "距離差": d.dist - d.p_dist,
                "間隔週": pd.to_numeric(d.rotation, errors="coerce"), "入厩日数": pd.to_numeric(d.nyu_d, errors="coerce"),
                "前走着順": d.p_fin, "前走着差": d.p_diff}.items():
    X[name] = s.to_numpy()
X["log_odds"] = np.log(d.odds)
cat_mask = [c in G.columns for c in X.columns]
y = (d.fin <= 3).astype(int).to_numpy()
d["p_full"] = np.nan; d["p_odds"] = np.nan
for Y in YEARS:
    tr = (d.y < Y).to_numpy(); te = (d.y == Y).to_numpy()
    m1 = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, min_samples_leaf=MINLEAF, l2_regularization=1.0,
                                        categorical_features=cat_mask, random_state=0).fit(X[tr], y[tr])
    m0 = HistGradientBoostingClassifier(max_iter=100, learning_rate=0.05, min_samples_leaf=MINLEAF, random_state=0).fit(X.loc[tr, ["log_odds"]], y[tr])
    d.loc[te, "p_full"] = m1.predict_proba(X[te])[:, 1]
    d.loc[te, "p_odds"] = m0.predict_proba(X.loc[te, ["log_odds"]])[:, 1]
    print(Y, "学習", tr.sum(), "予測", te.sum(), flush=True)
d["edge"] = d.p_full - d.p_odds
d.to_pickle(os.path.join(ROOT, ".scratch", f"ippen_gbm_scored_{MINLEAF}.pkl"))

t = d[d.y.isin(YEARS)].copy()
t["pct"] = t.groupby("y").edge.rank(pct=True)
print("\n較正の確認（予測3着内率の帯 → 実測）")
print(t.groupby(pd.cut(t.p_full, [0, .05, .1, .15, .2, .3, 1])).agg(n=("fin", "size"), 予測=("p_full", "mean"), 実測=("fin", lambda s: (s <= 3).mean())).round(3).to_string())
bands = [("上位1%", .99, 1.01), ("上位1〜5%", .95, .99), ("上位5〜10%", .90, .95), ("上位10〜25%", .75, .90), ("中位", .25, .75), ("下位25%", 0, .25)]
rows = []
for lab, lo, hi in bands:
    s = t[(t.pct > lo) & (t.pct <= hi)]
    hit = s[s.place > 0].place.sort_values(ascending=False); k = max(1, round(len(hit) * .01))
    whit = s[s.win > 0].win.sort_values(ascending=False); kw = max(1, round(len(whit) * .01))
    r = dict(帯=lab, n=len(s), オッズ中央=s.odds.median(), 三着内率=(s.fin <= 3).mean() * 100, 予測上乗せ=s.edge.mean() * 100,
             複勝=s.place.mean(), 複差=s.place_x.mean(), 複除外=(s.place.sum() - hit.head(k).sum()) / len(s),
             単勝=s.win.mean(), 単差=s.win_x.mean(), 単除外=(s.win.sum() - whit.head(kw).sum()) / len(s))
    for Y in YEARS:
        r[f"複差{Y % 100}"] = s[s.y == Y].place_x.mean()
    rows.append(r)
print(f"\n## 穴馬 一変上乗せ（GBM, min_leaf={MINLEAF}）の帯別成績 2022-2026")
print(pd.DataFrame(rows).round(1).to_string(index=False))
