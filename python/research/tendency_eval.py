# -*- coding: utf-8 -*-
"""
tendency_wf.py で作った傾向点 T（毎年その年より前のデータだけで推定）を評価する（研究用）。
- T 単独の上位馬
- sc に T を足した場合（sc + T/4。sc の指数+1 ≒ 複勝+4pt なので、T を sc と同じ目盛りに合わせる）
評価は各年の同オッズ帯平均との差、当たり上位1%除外、レース単位ブートストラップの90%信頼区間
"""
import sys, io, os
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
d = pd.read_pickle(os.path.join(ROOT, ".scratch", "tendency_scored.pkl"))
d = d[d.y >= 2022].copy()
rng = np.random.default_rng(0)
d["tie"] = rng.random(len(d))
YEARS = [2022, 2023, 2024, 2025, 2026]
TS = ["T全期間(芝ダ×距離のみ)", "T全期間(コース+クラス)", "T位置のみコース別", "T位置のみコース別+クラス"]


def trim(x, p, frac=0.01):
    hits = x[p][x[p] > 0].sort_values(ascending=False)
    k = int(len(hits) * frac)
    return (x[p].sum() - hits.iloc[:k].sum()) / len(x) - x[p + "_b"].mean()


def ci(x, p, B=600):
    g = x.groupby("rid"); s = g[p].sum().to_numpy(); sb = g[p + "_b"].sum().to_numpy(); n = g.size().to_numpy()
    idx = rng.integers(0, len(s), size=(B, len(s)))
    v = (s[idx].sum(1) - sb[idx].sum(1)) / n[idx].sum(1)
    return np.percentile(v, 5), np.percentile(v, 95)


def show(lab, x):
    yr = " / ".join(f"{x[x.y == Y].place_x.mean():+.1f}" for Y in YEARS)
    lo, hi = ci(x, "place")
    wl, wh = ci(x, "win")
    print(f"{lab:<34} n={len(x):>6,} | 複勝 差{x.place_x.mean():+5.1f} 年別[{yr}] 1%除外{trim(x, 'place'):+5.1f} CI[{lo:+.1f},{hi:+.1f}]"
          f" | 単勝 差{x.win_x.mean():+5.1f} 1%除外{trim(x, 'win'):+5.1f} CI[{wl:+.1f},{wh:+.1f}] | オッズ中央値{x.odds.median():.1f}")


print("## 1. 傾向点 T 単独（各年の上位 X% の馬）")
for q in (0.05, 0.10, 0.20):
    print(f"--- 上位{int(q * 100)}% ---")
    for t in TS:
        x = d[d.groupby("y")[t].rank(pct=True, ascending=False) <= q]
        show(t, x)

print("\n## 2. sc に傾向点を足す（現行 sc≥N と同じ頭数、年ごとに頭数を合わせる）")
d["案1"] = d.s_idx + d.s_oi + d.s_goal + d.s_down
cands = {"現行 sc": d.sc, "案1 整理": d["案1"]}
for t in TS:
    cands[f"現行sc + {t}/4"] = d.sc + d[t] / 4
    cands[f"案1 + {t}/4"] = d["案1"] + d[t] / 4
for N in (4, 6, 7, 8):
    print(f"--- 現行 sc≥{N} 相当 ---")
    for lab, v in cands.items():
        parts = []
        for Y in YEARS:
            m = d.y == Y
            k = int((d.sc[m] >= N).sum())
            parts.append(d[m].assign(v=v[m]).sort_values(["v", "tie"], ascending=False).head(k))
        show(lab, pd.concat(parts))
