# -*- coding: utf-8 -*-
"""
sc の重み付け直し案を比較（研究用）。
- 案1/案2 は 2021-2023 の重回帰結果（sc_signal_audit.py）だけを見て決めた固定ルール
- 案3 は毎年「その年より前（2021年〜）」のデータだけで回帰して重みを決める
- 評価は 2024-2026。各案とも「現行 sc≥N と同じ頭数の上位馬」で比べる（年ごと）
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
SIG = ["s_idx", "s_combo", "s_kyusha", "s_joho", "s_gap", "s_pace", "s_goal", "s_yaji", "s_oi", "s_down"]

d["v0"] = d.sc
d["v1"] = d.s_idx + d.s_oi + d.s_goal + d.s_down
d["v2"] = d.s_idx + d.s_oi + d.s_goal + 2 * d.s_down + d.ab

X = pd.get_dummies(d[SIG].astype(str))
X = X[[c for c in X.columns if not c.endswith("_0")]].astype(float)
X["ab"] = d.ab.astype(float)
X.insert(0, "const", 1.0)
d["v3"] = np.nan
for Y in (2024, 2025, 2026):
    tr = (d.y < Y).values
    A = X[tr].to_numpy(); yv = d.loc[tr, "place_x"].to_numpy()
    lam = 50.0 * len(A) / 10000          # 軽いリッジ（小サンプルのダミーの暴れを抑える）
    I = np.eye(A.shape[1]); I[0, 0] = 0
    beta = np.linalg.solve(A.T @ A + lam * I, A.T @ yv)
    d.loc[d.y == Y, "v3"] = X[(d.y == Y).values].to_numpy() @ beta

t = d[d.y >= 2024].copy()
rng = np.random.default_rng(0)
t["tie"] = rng.random(len(t))      # 同点の並び順はランダム（整数スコアの同点を公平に扱う）
LAB = {"v0": "現行", "v1": "案1 整理", "v2": "案2 整理+調整", "v3": "案3 学習"}
for N in (4, 6, 7, 8):
    print(f"\n### 現行 sc≥{N} と同じ頭数の上位馬（年ごとに頭数を合わせる）")
    print("案 | 頭数 | 複勝 | 同オッズ平均 | 差 | 年別差(24/25/26) | 上位10件除外 | 単勝 | 単勝差 | 単勝上位10件除外 | 基準オッズ中央値")
    for v in ("v0", "v1", "v2", "v3"):
        parts = []
        for Y in (2024, 2025, 2026):
            ty = t[t.y == Y]
            k = int((ty.v0 >= N).sum())
            parts.append(ty.sort_values([v, "tie"], ascending=False).head(k))
        x = pd.concat(parts)
        yr = "/".join(f"{x[x.y == Y].place_x.mean():+.1f}" for Y in (2024, 2025, 2026))
        ps = x.place.sort_values(ascending=False); ws = x.win.sort_values(ascending=False)
        print(f"{LAB[v]} | {len(x):,} | {x.place.mean():.1f}% | {x.place_b.mean():.1f}% | {x.place_x.mean():+.1f} | {yr} | {ps.iloc[10:].sum()/len(x):.1f}% | "
              f"{x.win.mean():.1f}% | {x.win_x.mean():+.1f} | {ws.iloc[10:].sum()/len(x):.1f}% | {x.odds.median():.1f}")
d[["y", "rid", "uma", "v0", "v1", "v2", "v3"]].to_pickle(os.path.join(ROOT, ".scratch", "sc_reweight.pkl"))
