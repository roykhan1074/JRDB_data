# -*- coding: utf-8 -*-
"""障害戦の指数（jump_wf.py の点数方式）の頑健性チェック（研究用）: 同点の乱数30通り・選定しきい値 MIN_EFF の違い。"""
import sys, io, os, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
YEARS = [2022, 2023, 2024, 2025, 2026]
for me in ("3", "4", "5", "6"):
    subprocess.run([sys.executable, os.path.join(ROOT, "python/research/jump_wf.py")], env={**os.environ, "MIN_EFF": me}, stdout=subprocess.DEVNULL, check=True)
    t = pd.read_pickle(os.path.join(ROOT, ".scratch", "jump_scored.pkl"))
    t = t[t.y.isin(YEARS)].copy()
    res = []
    for seed in range(30):
        t["tie"] = np.random.default_rng(seed).random(len(t))
        top = t.sort_values(["rid", "pts", "tie"], ascending=[True, False, False]).groupby("rid").head(1)
        res.append((top.place.mean(), top.win.mean(), top.place_x.mean(), top.top3.mean() * 100, *[top[top.y == Y].place.mean() for Y in YEARS], *[top[top.y == Y].win.mean() for Y in YEARS]))
    a = np.array(res)
    # 同点の1位を全部含める版
    mx = t.groupby("rid").pts.transform("max"); allt = t[t.pts == mx]
    print(f"MIN_EFF={me}: レース内1位(同点は乱数30通り) 複勝{a[:,0].mean():.1f}%(幅{a[:,0].min():.1f}〜{a[:,0].max():.1f}) 単勝{a[:,1].mean():.1f}%(幅{a[:,1].min():.1f}〜{a[:,1].max():.1f}) 差{a[:,2].mean():+.1f} 3着内率{a[:,3].mean():.1f}%"
          f" 年別複勝[{' / '.join(f'{a[:,4+i].mean():.0f}' for i in range(5))}] 年別単勝[{' / '.join(f'{a[:,9+i].mean():.0f}' for i in range(5))}]"
          f" | 同点1位を全部: {len(allt)}頭 複勝{allt.place.mean():.1f}% 単勝{allt.win.mean():.1f}%")
