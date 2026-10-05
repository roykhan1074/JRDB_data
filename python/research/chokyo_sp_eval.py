# -*- coding: utf-8 -*-
"""
調教SP（entries.html calcChokyoSP）の検証（研究用・DB書き込みなし）
- 出馬表と同じ計算を再現し、グレード別・構成要素別に 実際の単勝/複勝回収率 と 同年・同基準オッズ帯平均との差 を年別に見る
- 入力（追切指数・仕上指数・調教矢印・放牧先ランク）はすべてレース前に確定（固定ルールなので集計テーブル由来の先読みなし）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kyusha_multi_screen import load, prep  # noqa
import numpy as np, pandas as pd
pd.set_option("display.width", 260)

d = prep(load())
d = d[~d.shinba].copy()


def trim_mean(v):
    v = pd.Series(v); hits = v[v > 0].sort_values(ascending=False)
    k = int(np.ceil(len(hits) * 0.01))
    return hits.iloc[k:].sum() / len(v) if len(v) else np.nan


for p in ("place", "win"):
    d[p + "_b"] = d.groupby(["y", "ob"])[p].transform("mean")
    d[p + "_bt"] = d.groupby(["y", "ob"])[p].transform(trim_mean)
    d[p + "_x"] = d[p] - d[p + "_b"]

# --- calcChokyoSP の再現（出馬表は同じレースの出走全馬で計算。ここでは結果のある馬＝ほぼ全馬）
d["oi0"] = d.oi.fillna(0).clip(lower=0)
d["sh0"] = d.shiage.fillna(0).clip(lower=0)
g = d.groupby("rid")
vo = d.oi0.where(d.oi0 > 0); vs = d.sh0.where(d.sh0 > 0)
d["n_vo"] = vo.groupby(d.rid).transform("count"); d["n_vs"] = vs.groupby(d.rid).transform("count")
d["oi_m"] = vo.groupby(d.rid).transform("mean"); d["oi_sd"] = vo.groupby(d.rid).transform(lambda s: s.std(ddof=0))
d["sh_m"] = vs.groupby(d.rid).transform("mean"); d["sh_sd"] = vs.groupby(d.rid).transform(lambda s: s.std(ddof=0))
d["oi_rk"] = vo.groupby(d.rid).rank(ascending=False, method="min")
d["sh_rk"] = vs.groupby(d.rid).rank(ascending=False, method="min")
bonus = lambda r: np.select([r == 1, r == 2, r == 3], [3, 2, 1], 0)
d["rankPt"] = bonus(d.oi_rk) + bonus(d.sh_rk)
oz = np.where(d.oi_sd > 0, (d.oi0 - d.oi_m) / d.oi_sd, 0); sz = np.where(d.sh_sd > 0, (d.sh0 - d.sh_m) / d.sh_sd, 0)
d["zPt"] = np.minimum(0, np.round(oz + sz))   # JS Math.round と0.5の扱いが僅かに違うが影響は無視できる
d["yjPt"] = np.select([d.yaji == "4", d.yaji == "5"], [-2, -4], 0)
d["hbPt"] = np.select([d.hob == "E", d.hob == "D"], [-4, -2], 0)
d["sp"] = d.rankPt + d.zPt + d.yjPt + d.hbPt
valid = (d.oi0 > 0) & (d.sh0 > 0) & (d.n_vo >= 2) & (d.n_vs >= 2)
d["grade"] = np.where(~valid, "なし", np.select([d.sp >= 4, d.sp >= 2, d.sp >= -1, d.sp >= -4], ["A", "B", "C", "D"], "E"))
YRS = range(2020, 2027)


def tab(col, title, x=None, order=None):
    x = d if x is None else x
    rows = []
    for k, s in x.groupby(col):
        r = {"区分": k, "n": len(s), "単勝": s.win.mean(), "複勝": s.place.mean(), "単差": s.win_x.mean(), "複差": s.place_x.mean(),
             "単差1%除外": trim_mean(s.win) - s.win_bt.mean(), "複差1%除外": trim_mean(s.place) - s.place_bt.mean(),
             "オッズ中央": s.odds.median()}
        for Y in YRS:
            r[f"複{str(Y)[2:]}"] = s[s.y == Y].place_x.mean()
        r["複+年"] = sum(s[s.y == Y].place_x.mean() > 0 for Y in YRS)
        r["単+年"] = sum(s[s.y == Y].win_x.mean() > 0 for Y in YRS)
        rows.append(r)
    t = pd.DataFrame(rows)
    if order:
        t["o"] = t["区分"].map({k: i for i, k in enumerate(order)}); t = t.sort_values("o").drop(columns="o")
    print(f"\n### {title}")
    print(t.round(1).to_string(index=False))


tab("grade", "調教SPグレード（2020〜2026、新馬除外）", order=["A", "B", "C", "D", "E", "なし"])
print("\nグレード別 実際の回収率の年別（単勝/複勝）")
for gr in ["A", "B", "C", "D", "E"]:
    s = d[d.grade == gr]
    print(gr, "  ".join(f"{Y}:{s[s.y==Y].win.mean():.0f}/{s[s.y==Y].place.mean():.0f}" for Y in YRS))
v = d[valid].copy()
tab("sp", "調教SPスコア（整数）", v)
v["oi_b"] = np.select([v.oi_rk == 1, v.oi_rk <= 3], ["1位", "2-3位"], "4位~"); tab("oi_b", "追切指数のレース内順位", v)
v["sh_b"] = np.select([v.sh_rk == 1, v.sh_rk <= 3], ["1位", "2-3位"], "4位~"); tab("sh_b", "仕上指数のレース内順位", v)
tab("zPt", "z減点", v)
tab("yaji", "調教矢印", v)
tab("hob", "放牧先ランク", v)
# 調教SP A × オッズ帯（実際の回収率が高い所があるか）
a = v[v.grade == "A"].copy()
a["odds_b"] = pd.cut(a.odds, [1, 3, 5, 10, 20, 50, 1000], right=False).astype(str)
tab("odds_b", "調教SP A × 基準オッズ帯", a)
