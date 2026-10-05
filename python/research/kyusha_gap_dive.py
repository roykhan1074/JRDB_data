# -*- coding: utf-8 -*-
"""
厩舎指数の「人気とのずれ」の深掘り（研究用・DB書き込みなし）。kyusha_multi_screen.py のキャッシュを使う。
- 人気順位 − 厩舎指数順位 のしきい値別、厩舎指数順位 × 基準オッズ帯
- 払戻上位1%除外（基準側も同じく除外）・ブートストラップ95%区間・年別
- sc の既存シグナル「人気順位−IDM順位≥3」との重なり
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kyusha_multi_screen import *  # noqa

d = prep(load())
x = d[(d.y >= 2021)].copy()


def trim_mean(v):
    v = pd.Series(v)
    hits = v[v > 0].sort_values(ascending=False)
    k = int(np.ceil(len(hits) * 0.01))
    return hits.iloc[k:].sum() / len(v) if len(v) else np.nan


for p in ("win", "place"):
    x[p + "_b"] = x.groupby(["y", "ob"])[p].transform("mean")
    x[p + "_bt"] = x.groupby(["y", "ob"])[p].transform(trim_mean)


def stat(m, name):
    s = x[m]
    r = {"条件": name, "n": len(s), "年平均": len(s) / 6, "複勝": s.place.mean(), "複差": s.place.mean() - s.place_b.mean()}
    for Y in YEARS:
        sy = s[s.y == Y]
        r[str(Y)[2:]] = sy.place.mean() - sy.place_b.mean()
    r["複差_1%除外"] = trim_mean(s.place) - s.place_bt.mean()
    dd = (s.place - s.place_b).to_numpy()
    rng = np.random.default_rng(0)
    bs = [dd[rng.integers(0, len(dd), len(dd))].mean() for _ in range(400)]
    r["複95%下"] = np.percentile(bs, 2.5)
    r["単勝"] = s.win.mean(); r["単差"] = s.win.mean() - s.win_b.mean()
    r["単差_1%除外"] = trim_mean(s.win) - s.win_bt.mean()
    r["単+年数"] = sum((s[s.y == Y].win.mean() - s[s.y == Y].win_b.mean()) > 0 for Y in YEARS)
    return r


def table(rows, title):
    print(f"\n### {title}")
    print(pd.DataFrame(rows).round(1).to_string(index=False))


gap = x.ninki - x.ki_rank
table([stat(gap >= g, f"人気順位−厩舎指数順位≥{g}") for g in (2, 3, 4, 5, 6, 8, 10)] +
      [stat((gap >= 3) & (gap <= 4), "=3〜4"), stat((gap >= 5) & (gap <= 7), "=5〜7")], "人気順位 − 厩舎指数順位")

rows = []
for r_ in (1, 2, 3, 5):
    for lo in (10, 15, 20, 30, 50):
        rows.append(stat((x.ki_rank <= r_) & (x.odds >= lo), f"厩舎指数{r_}位以内×{lo}倍以上"))
table(rows, "厩舎指数レース内順位 × 基準オッズ")

rows = []
for lo, hi in ((10, 20), (20, 30), (30, 50), (50, 1000)):
    for r_ in (1, 3):
        rows.append(stat((x.ki_rank <= r_) & x.odds.between(lo, hi, "left"), f"{r_}位以内×{lo}-{hi}倍"))
table(rows, "オッズ帯を区切って")

# 厩舎指数の絶対値との組み合わせ（順位でなく値で見た場合）
rows = []
for kv in (10, 20):
    for lo in (20, 30):
        rows.append(stat((x.ki >= kv) & (x.odds >= lo), f"厩舎指数≥{kv}×{lo}倍以上"))
table(rows, "厩舎指数の値 × 基準オッズ")

# sc 既存シグナル（人気順位−IDM順位≥3）との重なり
ig = x.ninki - x.idm_rank
rows = [stat((gap >= 3) & (ig >= 3), "厩舎ずれ≥3 かつ IDMずれ≥3"),
        stat((gap >= 3) & (ig < 3), "厩舎ずれ≥3 だけ（IDMずれなし）"),
        stat((gap < 3) & (ig >= 3), "IDMずれ≥3 だけ"),
        stat((x.ki_rank <= 3) & (x.odds >= 30) & (ig >= 3), "厩舎3位以内×30倍+ かつ IDMずれ≥3"),
        stat((x.ki_rank <= 3) & (x.odds >= 30) & (ig < 3), "厩舎3位以内×30倍+ だけ")]
table(rows, "sc の『人気順位−IDM順位≥3』との重なり")
print("\n重なり率: 厩舎ずれ≥3 のうち IDMずれ≥3 も満たす割合 = %.1f%%" % (((gap >= 3) & (ig >= 3)).sum() / (gap >= 3).sum() * 100))
