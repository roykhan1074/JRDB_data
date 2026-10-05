# -*- coding: utf-8 -*-
"""
本命指数の情報指数帯の不具合修正を検証する（研究用）。
現行（新方式）の情報指数帯は 30/50/70 で区切っているが、実際の値は -1〜6.4 のため全馬がほぼ1区分。
実値に合った区分（-1非開示 / 0 / 0-1 / 1-2 / 2-3 / 3-4 / 4-5 / 5+）に変えて、毎年選び直す方式（walk-forward）で比較する。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import honmei_improve_wf as H

KW = dict(target="place", shrink_k=300, excess=True, use_course=False, chk_mode="fix")


def fixed_joho(d):
    d = d.copy()
    jo = pd.to_numeric(d.joho_index.astype(str).str.strip(), errors="coerce")
    d["f_joho"] = np.select(
        [jo.isna(), jo < -0.5, jo <= 0, jo <= 1, jo <= 2, jo <= 3, jo <= 4, jo <= 5],
        ["NA", "-1", "0", "0-1", "1-2", "2-3", "3-4", "4-5"], default="5+")
    return d


def evaluate(d, label):
    t = pd.concat([H.score_year(d, Y, **KW) for Y in H.TEST_YEARS])
    for p in ("win", "place"):
        t[p + "_b"] = t.groupby(["year", "ob"])[p].transform("mean")
    t["pct"] = t.groupby("year")["score"].rank(pct=True)
    for name, lo, hi in [("上位5%", .95, 1.01), ("上位5-10%", .90, .95), ("上位10-25%", .75, .90), ("下位25%", 0, .25)]:
        x = t[(t.pct > lo) & (t.pct <= hi)]
        hits = x.place[x.place > 0].sort_values(ascending=False); k = int(len(hits) * 0.01)
        yr = " / ".join(f"{(x[x.year == Y].place - x[x.year == Y].place_b).mean():+.1f}" for Y in H.TEST_YEARS)
        print(f"{label:<10} {name:<9} n={len(x):>5,} 複勝{x.place.mean():5.1f}% 差{(x.place - x.place_b).mean():+5.1f} 年別[{yr}] "
              f"1%除外{(x.place.sum() - hits.iloc[:k].sum()) / len(x) - x.place_b.mean():+5.1f} | 単勝{x.win.mean():5.1f}% 差{(x.win - x.win_b).mean():+5.1f}")
    return t


if __name__ == "__main__":
    base = H.prep(H.load())
    print("区分ごとの頭数（修正前）:", base.f_joho.value_counts().to_dict())
    fx = fixed_joho(base)
    print("区分ごとの頭数（修正後）:", fx.f_joho.value_counts().to_dict())
    evaluate(base, "修正前")
    evaluate(fx, "修正後")
