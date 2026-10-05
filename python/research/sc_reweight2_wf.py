# -*- coding: utf-8 -*-
"""
sc 改良案（最上位を伸ばす工夫）を「探索期間 2021-2023 → 確認期間 2024-2026」で比較する（研究用）。
各案とも、現行 sc≥N と同じ頭数の上位馬で比べる（年ごとに頭数を合わせる）。
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
hon = d.odds < 10
top_idx = ((hon & (d.hm >= 80)) | (~hon & (d.ex >= 150))).astype(int)

V = {
    "現行": d.sc,
    "案1 整理": d.s_idx + d.s_oi + d.s_goal + d.s_down,
    "案4 案1+指数2倍": 2 * d.s_idx + d.s_oi + d.s_goal + d.s_down,
    "案5 案1+指数最上段": d.s_idx + top_idx + d.s_oi + d.s_goal + d.s_down,
    "案6 案1+上がり1位": d.s_idx + d.s_oi + d.s_goal + d.s_down + (d.agari == 1).astype(int),
    "案7 案4+上がり1位": 2 * d.s_idx + d.s_oi + d.s_goal + d.s_down + (d.agari == 1).astype(int),
    "案8 案5+上がり1位": d.s_idx + top_idx + d.s_oi + d.s_goal + d.s_down + (d.agari == 1).astype(int),
}
rng = np.random.default_rng(0)
d["tie"] = rng.random(len(d))


def pick(v, N, years):
    parts = []
    for Y in years:
        m = d.y == Y
        k = int((d.sc[m] >= N).sum())
        parts.append(d[m].assign(v=v[m]).sort_values(["v", "tie"], ascending=False).head(k))
    return pd.concat(parts)


for period, years in (("探索 2021-2023", [2021, 2022, 2023]), ("確認 2024-2026", [2024, 2025, 2026])):
    print(f"\n======== {period} ========")
    for N in (6, 7, 8):
        print(f"--- 現行 sc≥{N} と同じ頭数 ---")
        for lab, v in V.items():
            x = pick(v, N, years)
            yr = "/".join(f"{x[x.y == Y].place_x.mean():+.1f}" for Y in years)
            ps = x.place.sort_values(ascending=False); ws = x.win.sort_values(ascending=False)
            print(f"{lab:<16} n={len(x):>5,} 複勝{x.place.mean():5.1f}% 差{x.place_x.mean():+5.1f} [{yr}] 上位10除外{ps.iloc[10:].sum()/len(x):5.1f}% "
                  f"| 単勝{x.win.mean():5.1f}% 差{x.win_x.mean():+5.1f} 上位10除外{ws.iloc[10:].sum()/len(x):5.1f}%(平均{x.win_b.mean():.1f}) | オッズ中央値{x.odds.median():.1f}")
