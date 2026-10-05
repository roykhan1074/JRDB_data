# -*- coding: utf-8 -*-
"""
案1（効かないシグナルを sc から外す）を、毎年選び直す方式で検証する（研究用）。
各年 Y について、Y年より前（2021年〜）のデータで重回帰し、正味の効果が +1pt 未満のシグナル段階を外す。
残したシグナルは元の重み（+1〜+3）のまま。調教矢印↓の減点は常に残す。Y年で答え合わせ。
"""
import sys, io, os, json
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
d = pd.DataFrame(json.load(open(os.path.join(ROOT, ".scratch", "sc_wf_wf3.json"))))
d = d[(d.y >= 2021) & (d.shinba == 0) & d.odds.between(1, 999)].copy().reset_index(drop=True)
d["ob"] = pd.cut(d.odds, [1, 2, 3, 5, 10, 15, 30, 50, 1000], right=False).astype(str)
for p in ("win", "place"):
    d[p + "_b"] = d.groupby(["y", "ob"])[p].transform("mean")
    d[p + "_x"] = d[p] - d[p + "_b"]
SIG = ["s_idx", "s_combo", "s_kyusha", "s_joho", "s_gap", "s_pace", "s_goal", "s_yaji", "s_oi"]
X = pd.get_dummies(d[SIG + ["s_down"]].astype(str))
X = X[[c for c in X.columns if not c.endswith("_0")]].astype(float)
X["ab"] = d.ab.astype(float)
X.insert(0, "const", 1.0)
YEARS = [2022, 2023, 2024, 2025, 2026]
d["wf"] = np.nan
kept_log = {}
for Y in YEARS:
    tr = (d.y < Y).values
    beta, *_ = np.linalg.lstsq(X[tr].to_numpy(), d.loc[tr, "place_x"].to_numpy(), rcond=None)
    B = pd.Series(beta, index=X.columns)
    score = d["s_down"].astype(float).copy()
    kept = []
    for s in SIG:
        for lvl in sorted(d[s].unique()):
            if lvl == 0:
                continue
            col = f"{s}_{lvl}"
            if col in B and B[col] >= 1.0:          # 正味の効果が +1pt 以上の段階だけ残す
                score += np.where(d[s] == lvl, lvl, 0)
                kept.append(f"{s}={lvl}")
    m = (d.y == Y).values
    d.loc[m, "wf"] = score[m]
    kept_log[Y] = kept
print("各年に残ったシグナル（その年より前のデータで判定）")
for Y, k in kept_log.items():
    print(f"  {Y}: {', '.join(k)}")

d["fixed"] = d.s_idx + d.s_oi + d.s_goal + d.s_down
rng = np.random.default_rng(0)
d["tie"] = rng.random(len(d))


def trim(x, p, frac=0.01):
    hits = x[p][x[p] > 0].sort_values(ascending=False)
    k = int(len(hits) * frac)
    return (x[p].sum() - hits.iloc[:k].sum()) / len(x) - x[p + "_b"].mean()


for N in (4, 6, 7, 8):
    print(f"\n--- 現行 sc≥{N} と同じ頭数（2022〜2026） ---")
    for lab, col in (("現行 sc", "sc"), ("案1（固定で決めた版）", "fixed"), ("案1（毎年選び直す版）", "wf")):
        parts = []
        for Y in YEARS:
            m = d.y == Y
            k = int((d.sc[m] >= N).sum())
            parts.append(d[m].sort_values([col, "tie"], ascending=False).head(k))
        x = pd.concat(parts)
        yr = " / ".join(f"{x[x.y == Y].place_x.mean():+.1f}" for Y in YEARS)
        print(f"{lab:<16} n={len(x):,} 複勝{x.place.mean():.1f}% 差{x.place_x.mean():+.1f} 年別[{yr}] 1%除外{trim(x, 'place'):+.1f} "
              f"| 単勝{x.win.mean():.1f}% 差{x.win_x.mean():+.1f} 1%除外{trim(x, 'win'):+.1f} | 3着内率{(x.fin <= 3).mean()*100:.1f}% オッズ中央値{x.odds.median():.1f}")
