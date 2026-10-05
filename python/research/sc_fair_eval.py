# -*- coding: utf-8 -*-
"""
複合シグナル sc を「同じオッズ帯の馬の平均より回収率を押し上げているか」で評価（研究用）
入力: .scratch/sc_wf_{mode}.json（sc_wf.js の出力）
実行: python sc_fair_eval.py {lk|ho|ho25} {開始年}
"""
import sys, io, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
MODE = sys.argv[1] if len(sys.argv) > 1 else "lk"
Y0 = int(sys.argv[2]) if len(sys.argv) > 2 else 2024
d = pd.DataFrame(json.load(open(os.path.join(ROOT, ".scratch", f"sc_wf_{MODE}.json"))))
d = d[(d.y >= Y0) & (d.shinba == 0) & d.odds.between(1, 999)].copy()
d["ob"] = pd.cut(d.odds, [1, 2, 3, 5, 10, 15, 30, 50, 1000], right=False)
for p in ("win", "place"):
    d[p + "_base"] = d.groupby("ob", observed=True)[p].transform("mean")
years = sorted(d.y.unique())
d["band"] = pd.cut(d.sc, [-99, 0, 2, 4, 5, 6, 7, 8, 99], right=False,
                   labels=["0未満", "0-1", "2-3", "4", "5", "6", "7", "8以上"])
print(f"### 複合シグナル sc（EX指数={MODE}、{Y0}年以降、新馬除外）：同じオッズ帯の平均との差")
print("sc | 頭数 | 単勝 | 同オッズ平均 | 差 | 複勝 | 同オッズ平均 | 差 | 単勝 年別")
for b, x in d.groupby("band", observed=True):
    yr = " / ".join(f"{y}:{x[x.y == y].win.mean():.0f}" for y in years)
    print(f"{b} | {len(x):,} | {x.win.mean():.1f}% | {x.win_base.mean():.1f}% | {x.win.mean()-x.win_base.mean():+.1f} | "
          f"{x.place.mean():.1f}% | {x.place_base.mean():.1f}% | {x.place.mean()-x.place_base.mean():+.1f} | {yr}")
x = d[d.sc >= 6]
print(f"\nsc≥6 合計: 頭数{len(x):,} 単勝{x.win.mean():.1f}%（同オッズ平均{x.win_base.mean():.1f}%、差{x.win.mean()-x.win_base.mean():+.1f}）"
      f" 複勝{x.place.mean():.1f}%（同{x.place_base.mean():.1f}%、差{x.place.mean()-x.place_base.mean():+.1f}）")
