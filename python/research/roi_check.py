# -*- coding: utf-8 -*-
"""モデル確率×オッズ（期待値）帯ごとの実際の回収率（walk-forward予測を使用）"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
df = pd.read_pickle(os.path.join(ROOT, ".scratch", sys.argv[1] if len(sys.argv) > 1 else "prob_pred.pkl"))
df = df[df["final_win_odds"].notna()].copy()
df["win_pay"] = df["win_pay"].fillna(0)
df["place_pay"] = df["place_pay"].fillna(0)

# 単勝: 期待値 = 1着確率 × 確定単勝オッズ
df["ev_win"] = df["p_y_win"] * df["final_win_odds"]
# 複勝: 確定複勝オッズは事前に分からないため基準複勝オッズで代用
df["ev_place"] = df["p_y_top3"] * df["kijun_fukusho_odds"]

bins = [0, 0.6, 0.8, 0.9, 1.0, 1.1, 1.2, 1.5, 2.0, 99]
labels = ["~0.6", "0.6-0.8", "0.8-0.9", "0.9-1.0", "1.0-1.1", "1.1-1.2", "1.2-1.5", "1.5-2.0", "2.0+"]
for kind, ev, pay in [("単勝", "ev_win", "win_pay"), ("複勝", "ev_place", "place_pay")]:
    d = df[df[ev].notna()].copy()
    d["b"] = pd.cut(d[ev], bins, labels=labels)
    print(f"\n### {kind}：期待値（予測確率×オッズ）帯ごとの回収率")
    t = d.groupby(["b", "year"], observed=True)[pay].mean().unstack().round(1)
    t["全体"] = d.groupby("b", observed=True)[pay].mean().round(1)
    t["n"] = d.groupby("b", observed=True)[pay].size()
    print(t.to_string())
    hi = d[d[ev] >= 1.0]
    print(f"期待値1.0以上を全部買った場合: 年別 " +
          " / ".join(f"{y}:{hi[hi.year==y][pay].mean():.1f}%" for y in sorted(hi.year.unique())) +
          f"  全体 {hi[pay].mean():.1f}% (n={len(hi)})")
