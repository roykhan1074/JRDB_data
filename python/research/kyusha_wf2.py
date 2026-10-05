# -*- coding: utf-8 -*-
"""
厩指穴信頼ブラッシュアップの続き（研究用・DB書き込みなし）
1. 厩舎指数（JRDB、出走前に確定）そのものの帯・レース内順位が、同オッズ帯平均より上乗せを持つか（年別）
2. 「同じ厩舎指数でも信頼できる調教師がいる」を直接測る:
   調教師ごとに「厩舎指数が高いときの上乗せ」を前年までで集計 → 当年の厩舎指数が高い馬を採点（walk-forward）
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from kyusha_wf import *   # noqa

d = prep(load())
d["rid"] = d.course_code + d.year_code + d.kai + d.day_code + d.race_num
d["ki_rank"] = d.groupby("rid")["ki"].rank(ascending=False, method="min")
d["heads"] = d.groupby("rid")["ki"].transform("size")
d["ki_dev"] = d.ki - d.groupby("rid")["ki"].transform("mean")
t = d[d.year >= 2021].copy()
t["place_b"] = t.groupby(["year", "ob"])["place"].transform("mean")
t["place_bt"] = t.groupby(["year", "ob"])["place"].transform(trim_mean)
YRS = [2021, 2022, 2023, 2024, 2025, 2026]


def tab(t, groups, title):
    rows = []
    for name, m in groups:
        x = t[m]
        r = {"区分": name, "頭数": len(x), "複勝": x.place.mean(), "平均": x.place_b.mean()}
        r["差"] = r["複勝"] - r["平均"]
        for Y in YRS:
            xy = x[x.year == Y]
            r[str(Y)[2:]] = xy.place.mean() - xy.place_b.mean()
        r["上位1%除外差"] = trim_mean(x.place) - x.place_bt.mean()
        rows.append(r)
    print(f"\n## {title}")
    print(pd.DataFrame(rows).round(1).to_string(index=False))


ki = t.ki
tab(t, [("<-10", ki < -10), ("-10~0", ki.between(-10, 0, "left")), ("0~10", ki.between(0, 10, "left")),
        ("10~20", ki.between(10, 20, "left")), ("20~30", ki.between(20, 30, "left")), ("30~", ki >= 30), ("欠損", ki.isna())],
    "厩舎指数の帯（全馬、2021〜2026）")
r = t.ki_rank
tab(t, [("レース内1位", r == 1), ("2〜3位", r.between(2, 3)), ("4〜6位", r.between(4, 6)), ("7位以下", r >= 7)],
    "厩舎指数のレース内順位（全馬）")
a = t[t.odds >= 10]
r = a.ki_rank
tab(a, [("レース内1位", r == 1), ("2〜3位", r.between(2, 3)), ("4〜6位", r.between(4, 6)), ("7位以下", r >= 7)],
    "厩舎指数のレース内順位（基準オッズ10倍以上）")
ki = a.ki
tab(a, [("<0", ki < 0), ("0~10", ki.between(0, 10, "left")), ("10~20", ki.between(10, 20, "left")), ("20~", ki >= 20)],
    "厩舎指数の帯（基準オッズ10倍以上）")

# 2. 調教師ごとの「厩舎指数が高いときの上乗せ」
print("\n## 調教師ごとの『厩舎指数が高いときの上乗せ』（前年まで集計・縮小k=100）→ 当年 厩舎指数≧10 の馬を採点")
for hi in (10, 20):
    parts = []
    for Y in TEST_YEARS:
        tr, te = d[d.year < Y], d[(d.year == Y) & (d.ki >= hi)].copy()
        h = tr[tr.ki >= hi]
        y = h.place - h.groupby("ob")["place"].transform("mean")
        g = y.groupby(h.trainer_code).agg(["mean", "size"])
        s = g["mean"] * g["size"] / (g["size"] + 100)
        te["score"] = te.trainer_code.map(s)
        parts.append(te)
    tt = pd.concat(parts)
    tt["place_b"] = tt.groupby(["year", "ob"])["place"].transform("mean")
    tt["place_bt"] = tt.groupby(["year", "ob"])["place"].transform(trim_mean)
    tt["n"] = 99
    print(f"\n### 厩舎指数≧{hi}（評価 {len(tt):,}頭）")
    print(summarize(tt, f"信頼度(ki≧{hi})", pct_bands)[["帯", "頭数", "複勝", "平均", "差", "22", "23", "24", "25", "26", "上位1%除外差", "95%下", "95%上"]].round(1).to_string(index=False))
