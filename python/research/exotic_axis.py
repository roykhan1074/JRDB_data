# -*- coding: utf-8 -*-
"""
軸1頭流し（馬連・三連複）の相手選び検証（研究用・DB書き込みなし）
- 軸・相手の判定はレース前に分かる情報のみ（walk-forward予測・基準オッズ・JRDB指数）
- 探索: 2022-2024 / 確認: 2025-2026（確認期間は条件選びに使わない）
"""
import sys, io, os, itertools
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd
from exotic_wf import load_hjc, parse   # stdout は exotic_wf 側で UTF-8 化済み
pd.set_option("display.width", 250)
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
EXP, CONF = [2022, 2023, 2024], [2025, 2026]

o = pd.read_pickle(os.path.join(ROOT, ".scratch", "ret_place.pkl"))
pp = pd.read_pickle(os.path.join(ROOT, ".scratch", "prob_pred.pkl"))[["race_id", "uma_num", "p_y_win", "p_y_top2", "p_y_top3"]]
o = o.merge(pp, on=["race_id", "uma_num"], how="left")
o["uma"] = o["uma_num"].astype(int)
o["rk"] = o.groupby("race_id")["pred"].rank(ascending=False, method="first")
um, sp = parse(load_hjc())

AXES = {
    "A:モデル1位×上がり2位以内×3倍未満": lambda g: g[(g.rk == 1) & (g.agari_index_juni <= 2) & (g.kijun_odds < 3)],
    "B:モデル1位×3倍未満": lambda g: g[(g.rk == 1) & (g.kijun_odds < 3)],
    "C:モデル1位×上がり3位以内×5倍未満": lambda g: g[(g.rk == 1) & (g.agari_index_juni <= 3) & (g.kijun_odds < 5)],
}
# 相手の並べ方（軸を除く）。filter は相手候補の絞り込み
PARTNERS = {
    "予測払戻順": dict(key="pred", asc=False, flt=None),
    "3着内確率順": dict(key="p_y_top3", asc=False, flt=None),
    "人気順": dict(key="kijun_odds", asc=True, flt=None),
    "予測払戻順(5-30倍のみ)": dict(key="pred", asc=False, flt=lambda g: g.kijun_odds.between(5, 30)),
    "3着内確率順(5-30倍のみ)": dict(key="p_y_top3", asc=False, flt=lambda g: g.kijun_odds.between(5, 30)),
    "予測払戻順(10倍以上)": dict(key="pred", asc=False, flt=lambda g: g.kijun_odds >= 10),
    "3着内確率順(1番人気除く)": dict(key="p_y_top3", asc=False, flt=lambda g: g.kijun_odds.rank(method="first") > 1),
}

recs = []
for rid, g in o.groupby("race_id"):
    if rid not in um:
        continue
    year = int(g.year.iloc[0])
    for an, af in AXES.items():
        ax = af(g)
        if len(ax) != 1:
            continue
        a = int(ax.uma.iloc[0])
        rest = g[g.uma != a]
        for pn, pdef in PARTNERS.items():
            cand = rest if pdef["flt"] is None else rest[pdef["flt"](rest)]
            order = cand.sort_values(pdef["key"], ascending=pdef["asc"]).uma.tolist()
            for N in range(1, 8):
                if len(order) < N:
                    break
                ps = order[:N]
                # 馬連 軸流し
                pay_u = sum(v for k, v in um[rid].items() if a in k and (set(k) - {a}) <= set(ps))
                recs.append((an, pn, "馬連", N, rid, year, N * 100, pay_u))
                # 三連複 軸1頭流し（相手N頭から2頭）
                if N >= 2:
                    cost = N * (N - 1) // 2 * 100
                    pay_s = sum(v for k, v in sp.get(rid, {}).items() if a in k and (set(k) - {a}) <= set(ps))
                    recs.append((an, pn, "三連複", N, rid, year, cost, pay_s))

R = pd.DataFrame(recs, columns=["axis", "partner", "bet", "N", "race_id", "year", "cost", "pay"])
R.to_pickle(os.path.join(ROOT, ".scratch", "axis_recs.pkl"))


def summarize(d):
    per = d.groupby("year").apply(lambda x: x.pay.sum() / x.cost.sum() * 100).reindex(EXP + CONF)
    e, c = d[d.year.isin(EXP)], d[d.year.isin(CONF)]
    cp = c.pay.sort_values(ascending=False)
    return pd.Series({
        **{str(y): per[y] for y in EXP + CONF},
        "探索": e.pay.sum() / e.cost.sum() * 100, "探索最悪年": per[EXP].min(),
        "確認": c.pay.sum() / c.cost.sum() * 100,
        "確認_上位5除外": (cp.iloc[5:].sum()) / c.cost.sum() * 100,
        "レース数_確認": len(c), "的中率_確認": (c.pay > 0).mean() * 100,
    })


S = R.groupby(["bet", "axis", "partner", "N"]).apply(summarize).reset_index()
S.to_pickle(os.path.join(ROOT, ".scratch", "axis_summary.pkl"))
for bet in ["馬連", "三連複"]:
    t = S[S.bet == bet].sort_values("探索最悪年", ascending=False).head(12)
    print(f"\n### {bet}: 探索期間(2022-24)の最悪年で選んだ上位12 → 確認期間(2025-26)")
    print(t.drop(columns="bet").round(1).to_string(index=False))
