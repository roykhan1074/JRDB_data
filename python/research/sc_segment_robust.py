# -*- coding: utf-8 -*-
"""
sc_segment_wf.py の比較を、より公平な頑健性指標で見直す（研究用）。
- 「上位10件除外」は当たりの数が少ない（人気薄を選ぶ）案ほど不利なので、
  当たりの数に比例した除外（当たり払戻の上位 1% / 3% / 5% を除外）に変える
- ブートストラップ（レース単位で再抽出）で、同オッズ帯平均との差の 90% 信頼区間を出す
"""
import sys, io, os, json
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
sys.argv = [sys.argv[0]]
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
exec(open(os.path.join(os.path.dirname(__file__), "sc_segment_wf.py"), encoding="utf-8").read().split("rng = np.random.default_rng(0)")[0])

rng = np.random.default_rng(0)
d["tie"] = rng.random(len(d))
KEEP = ["現行 sc", "案1 整理", "全体共通の重み(学習)", "芝ダ別 λ=10000", "芝ダ×距離帯別 λ=2000", "芝ダ×距離帯別 λ=10000", "競馬場別 λ=10000", "競馬場×芝ダ別 λ=2000"]


def trimmed(x, p, frac):
    hits = x[p][x[p] > 0].sort_values(ascending=False)
    k = int(np.floor(len(hits) * frac))
    return (x[p].sum() - hits.iloc[:k].sum()) / len(x) - x[p + "_b"].mean(), len(hits)


def boot_ci(x, p, B=1000):
    g = x.groupby("rid")
    s = g[p].sum().to_numpy(); sb = g[p + "_b"].sum().to_numpy(); n = g.size().to_numpy()
    idx = rng.integers(0, len(s), size=(B, len(s)))
    diff = (s[idx].sum(1) - sb[idx].sum(1)) / n[idx].sum(1)
    return np.percentile(diff, 5), np.percentile(diff, 95)


for period, years in (("探索2022-23", [2022, 2023]), ("確認2024-26", [2024, 2025, 2026])):
    for N in (7, 8):
        print(f"\n### {period} 現行 sc≥{N} と同じ頭数")
        print("案 | 頭数 | 券種 | 当たり数 | 差 | 当たり上位1%除外 | 3%除外 | 5%除外 | 90%信頼区間 | オッズ中央値")
        for lab in KEEP:
            v = models[lab]
            parts = []
            for Yr in years:
                m = (d.y == Yr).values
                k = int((d.sc[m] >= N).sum())
                parts.append(d[m].assign(v=v[m]).sort_values(["v", "tie"], ascending=False).head(k))
            x = pd.concat(parts)
            for p, nm in (("place", "複勝"), ("win", "単勝")):
                full = x[p].mean() - x[p + "_b"].mean()
                t1, nh = trimmed(x, p, 0.01); t3, _ = trimmed(x, p, 0.03); t5, _ = trimmed(x, p, 0.05)
                lo, hi = boot_ci(x, p)
                print(f"{lab} | {len(x):,} | {nm} | {nh} | {full:+.1f} | {t1:+.1f} | {t3:+.1f} | {t5:+.1f} | [{lo:+.1f}, {hi:+.1f}] | {x.odds.median():.1f}")
