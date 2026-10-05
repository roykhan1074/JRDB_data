# -*- coding: utf-8 -*-
"""
sc の要素の重みを「芝ダ／距離帯／競馬場」ごとに変えると良くなるかを検証する（研究用）。
- 重みは各年 Y について、Y年より前（2021年〜）のデータだけで推定する（walk-forward）
- 区分ごとの重みは全体の重みへ引き寄せて推定（縮小推定）:
    b_seg = argmin |y_seg - X_seg b|^2 + λ |b - b_global|^2
  λ は「頭数換算」。区分の頭数が λ より十分多ければ区分独自の傾向、少なければ全体の重みに近づく
- 目的変数: 複勝払戻 − 同じ年・同じ基準オッズ帯の平均（＝同オッズ帯平均との差）
- 評価: 探索 2022-2023 / 確認 2024-2026。現行 sc≥N と同じ頭数の上位馬で比較
"""
import sys, io, os, json
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
d = pd.DataFrame(json.load(open(os.path.join(ROOT, ".scratch", "sc_wf_wf3.json"))))
d = d[(d.y >= 2021) & (d.shinba == 0) & d.odds.between(1, 999)].copy().reset_index(drop=True)
d["ob"] = pd.cut(d.odds, [1, 2, 3, 5, 10, 15, 30, 50, 1000], right=False).astype(str)
for p in ("win", "place"):
    d[p + "_b"] = d.groupby(["y", "ob"])[p].transform("mean")
    d[p + "_x"] = d[p] - d[p + "_b"]
d["dband"] = pd.cut(d.dist, [0, 1400, 1800, 2200, 9999], labels=["~1400", "1401-1800", "1801-2200", "2201~"]).astype(str)
d["seg_tds"] = d.tds
d["seg_tds_dist"] = d.tds + "_" + d.dband
d["seg_course"] = d.course
d["seg_course_tds"] = d.course + "_" + d.tds

SIG = ["s_idx", "s_combo", "s_kyusha", "s_joho", "s_gap", "s_pace", "s_goal", "s_yaji", "s_oi", "s_down"]
X = pd.get_dummies(d[SIG].astype(str))
X = X[[c for c in X.columns if not c.endswith("_0")]].astype(float)
X["ab"] = d.ab.astype(float)
X["agari1"] = (d.agari == 1).astype(float)
X.insert(0, "const", 1.0)
XA = X.to_numpy(); Y_ = d.place_x.to_numpy()
P = XA.shape[1]


def ridge(A, y, lam, prior):
    I = np.eye(P); I[0, 0] = 0          # 切片は縮めない
    return np.linalg.solve(A.T @ A + lam * I, A.T @ y + lam * I @ prior)


def predict(seg_col, lam_seg, lam_glob=500.0):
    pred = np.full(len(d), np.nan)
    for Yr in range(2022, 2027):
        tr = (d.y < Yr).values; te = (d.y == Yr).values
        bg = ridge(XA[tr], Y_[tr], lam_glob, np.zeros(P))
        if seg_col is None:
            pred[te] = XA[te] @ bg
            continue
        for s in d.loc[te, seg_col].unique():
            ms = tr & (d[seg_col] == s).values
            mt = te & (d[seg_col] == s).values
            b = ridge(XA[ms], Y_[ms], lam_seg, bg) if ms.sum() > 0 else bg
            pred[mt] = XA[mt] @ b
    return pred


models = {
    "現行 sc": d.sc.to_numpy(dtype=float),
    "案1 整理": (d.s_idx + d.s_oi + d.s_goal + d.s_down).to_numpy(dtype=float),
    "全体共通の重み(学習)": predict(None, 0),
}
for seg, lab in [("seg_tds", "芝ダ別"), ("seg_tds_dist", "芝ダ×距離帯別"), ("seg_course", "競馬場別"), ("seg_course_tds", "競馬場×芝ダ別")]:
    for lam in (2000, 10000):
        models[f"{lab} λ={lam}"] = predict(seg, lam)

rng = np.random.default_rng(0)
d["tie"] = rng.random(len(d))
rows = []
for period, years in (("探索2022-23", [2022, 2023]), ("確認2024-26", [2024, 2025, 2026])):
    for N in (4, 6, 7, 8):
        for lab, v in models.items():
            parts = []
            for Yr in years:
                m = (d.y == Yr).values
                k = int((d.sc[m] >= N).sum())
                parts.append(d[m].assign(v=v[m]).sort_values(["v", "tie"], ascending=False).head(k))
            x = pd.concat(parts)
            ps = x.place.sort_values(ascending=False); ws = x.win.sort_values(ascending=False)
            rows.append(dict(期間=period, 基準=f"sc≥{N}相当", 案=lab, 頭数=len(x),
                             複勝差=x.place_x.mean(), 年別=" / ".join(f"{x[x.y == Yr].place_x.mean():+.1f}" for Yr in years),
                             複勝上位10除外差=ps.iloc[10:].sum() / len(x) - x.place_b.mean(),
                             単勝差=x.win_x.mean(), 単勝上位10除外差=ws.iloc[10:].sum() / len(x) - x.win_b.mean(),
                             オッズ中央値=x.odds.median()))
R = pd.DataFrame(rows)
R.to_pickle(os.path.join(ROOT, ".scratch", "sc_segment_result.pkl"))
pd.set_option("display.width", 250)
for (period, base), g in R.groupby(["期間", "基準"], sort=False):
    print(f"\n### {period} {base}")
    print(g.drop(columns=["期間", "基準"]).round(1).to_string(index=False))
