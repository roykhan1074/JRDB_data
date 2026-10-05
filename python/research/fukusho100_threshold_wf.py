# -*- coding: utf-8 -*-
"""
複勝妙味シグナル（旧称: 複勝回収率100%超シグナル）の EX/本命指数しきい値を、新方式の指数に合わせて選び直す（研究用）。
毎年 Y について、Y年より前（2021年〜）のデータで最も良いしきい値の組み合わせを選び、Y年で答え合わせする（walk-forward）。
評価値: 複勝sc≥3 × 基準オッズ15〜30倍 の複勝回収率の「同じ年・同じオッズ帯の平均との差」。年平均400頭未満になる組み合わせは選ばない。
EX/本命指数は毎年直前年まで集計し直した値（T_ANABA_SCORE_WF2 / T_HONMEI_SCORE_WF2）、騎手×調教師はその日より前の結果のみ。
"""
import sys, io, os, itertools
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
d = pd.read_pickle(os.path.join(ROOT, ".scratch", "fukusho100_base.pkl"))
d = d[(d.y >= 2021) & d.odds.between(15, 30, inclusive="left") & (d.cls != "A1")].copy()
d["px"] = d.place - d.place_b
# しきい値に依存しない5条件の合計
rest = (((d.combo_n_wf >= 30) & (d.combo_rr_wf >= 100)).astype(int)
        + ((d.oi.fillna(0) >= 70) | (d.shiage.fillna(0) >= 70)).astype(int)
        + d.goal.isin([1, 2]).astype(int) + d.joho_rk.isin([1, 2]).astype(int)
        + ((d.ten == 1) | (d.agari == 1)).astype(int)).to_numpy()
ex = d.ex_wf2.to_numpy(); hm = d.hm_wf2.to_numpy()
GRID = [(e1, e2, h1, h2) for e1, e2, h1, h2 in itertools.product([15, 25, 35, 50], [50, 75, 100, 125], [10, 20, 30], [30, 40, 50, 60]) if e1 < e2 and h1 < h2]


def sel(th):
    e1, e2, h1, h2 = th
    s = rest + ((ex >= e1) | (hm >= h1)).astype(int) + ((ex >= e2) | (hm >= h2)).astype(int)
    return s >= 3


masks = {th: sel(th) for th in GRID}
y = d.y.to_numpy(); px = d.px.to_numpy(); place = d.place.to_numpy(); base = d.place_b.to_numpy(); fin = d.fin.to_numpy()
YEARS = [2022, 2023, 2024, 2025, 2026]
CUR = (15, 50, 10, 30)
picked = np.zeros(len(d), bool); log = []
for Y in YEARS:
    tr = y < Y; nyr = len(set(y[tr]))
    best, bestv = None, -1e9
    for th, m in masks.items():
        mm = m & tr
        if mm.sum() < 400 * nyr:
            continue
        v = px[mm].mean()
        if v > bestv:
            best, bestv = th, v
    log.append((Y, best, bestv))
    picked |= masks[best] & (y == Y)
print("各年に選ばれたしきい値（EX弱, EX強, 本命弱, 本命強）と、その年より前のデータでの差:")
for Y, th, v in log:
    print(f"  {Y}: {th}  学習期間の差 {v:+.1f}")


def show(lab, m):
    x = m & np.isin(y, YEARS)
    hits = np.sort(place[x & (place > 0)])[::-1]; k = int(len(hits) * 0.01)
    yr = " / ".join(f"{place[m & (y == Y)].mean():.0f}" for Y in YEARS)
    yd = " / ".join(f"{px[m & (y == Y)].mean():+.1f}" for Y in YEARS)
    print(f"| {lab} | {x.sum():,} | {(fin[x] <= 3).mean() * 100:.1f}% | **{place[x].mean():.1f}%** | {yr} | {px[x].mean():+.1f} | {yd} | {(place[x].sum() - hits[:k].sum()) / x.sum():.1f}% |")


print("\n### 2022〜2026年（先読みなし）")
print("| しきい値 | 頭数 | 3着内率 | 複勝回収率 | 年別回収率 | 同オッズ平均との差 | 年別の差 | 当たり上位1%除外 |")
print("|---|---:|---:|---:|---|---:|---|---:|")
show("現行 15/50/10/30", masks[CUR])
show("毎年選び直したしきい値", picked)
last = log[-1][1]
show(f"直近の選択 {last} を全年に固定（参考）", masks[last])
