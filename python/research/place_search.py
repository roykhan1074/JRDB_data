# -*- coding: utf-8 -*-
"""
複勝: 「予測払戻」×「上がり指数順位」×「オッズ帯」等の条件探索（研究用）
- 探索: 2022-2024 のみで条件を選ぶ
- 確認: 2025-2026 は探索に使わず、選ばれた条件の答え合わせにのみ使う
"""
import sys, io, os, itertools
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd
pd.set_option("display.width", 220)
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
o = pd.read_pickle(os.path.join(ROOT, ".scratch", "ret_place.pkl"))
o["rk"] = o.groupby("race_id")["pred"].rank(ascending=False, method="first")
o["pq"] = o.groupby("year")["pred"].rank(pct=True)          # その年の中での予測払戻の順位（上位ほど1に近い）
EXP, CONF = [2022, 2023, 2024], [2025, 2026]

conds = {
    "モデル順位": {"全馬": o.rk > 0, "レース内1位": o.rk == 1, "レース内2位以内": o.rk <= 2, "レース内3位以内": o.rk <= 3,
               "上位20%": o.pq >= .8, "上位10%": o.pq >= .9},
    "上がり順位": {"不問": o.agari_index_juni > -1, "1位": o.agari_index_juni == 1, "2位以内": o.agari_index_juni <= 2,
               "3位以内": o.agari_index_juni <= 3},
    "基準オッズ": {"不問": o.kijun_odds > 0, "~3倍": o.kijun_odds < 3, "3-5倍": o.kijun_odds.between(3, 5, "left"),
               "5-10倍": o.kijun_odds.between(5, 10, "left"), "10-20倍": o.kijun_odds.between(10, 20, "left"),
               "20倍~": o.kijun_odds >= 20, "~5倍": o.kijun_odds < 5, "5-20倍": o.kijun_odds.between(5, 20, "left")},
    "芝ダ": {"不問": o.tds_code != "", "芝": o.tds_code == "1", "ダ": o.tds_code == "2"},
}
rows = []
for combo in itertools.product(*[d.items() for d in conds.values()]):
    m = np.logical_and.reduce([c[1].to_numpy() for c in combo])
    d = o[m]
    e = d[d.year.isin(EXP)]
    if len(e) < 300:
        continue
    per = e.groupby("year")["place_pay"].mean().reindex(EXP)
    rows.append(dict(cond=" / ".join(f"{k}:{c[0]}" for k, c in zip(conds.keys(), combo)),
                     n_exp=len(e), exp=e.place_pay.mean(), exp_min=per.min(),
                     **{str(y): per[y] for y in EXP}, mask=m))
R = pd.DataFrame(rows)
print(f"探索した条件数: {len(R)}（探索期間で300頭以上の条件のみ）")

# 選定基準（探索期間のみで判定）: 3年すべての最低値が高い順。平均だけでなく最悪年で選ぶ
top = R.sort_values("exp_min", ascending=False).head(15).copy()
def conf(m):
    d = o[m & o.year.isin(CONF).to_numpy()]
    per = d.groupby("year")["place_pay"].mean().reindex(CONF)
    # 集中度: 確認期間の払戻上位5件を除いた回収率
    pays = d.place_pay.sort_values(ascending=False)
    ex5 = (pays.iloc[5:].sum() / len(d)) if len(d) > 5 else np.nan
    return pd.Series({"2025": per[2025], "2026": per[2026], "確認期間": d.place_pay.mean(), "n_conf": len(d),
                      "上位5件除外": ex5, "的中率": (d.place_pay > 0).mean() * 100})
top = pd.concat([top.drop(columns="mask"), top["mask"].apply(conf)], axis=1)
cols = ["cond", "2022", "2023", "2024", "exp", "n_exp", "2025", "2026", "確認期間", "n_conf", "上位5件除外", "的中率"]
print("\n### 探索期間(2022-24)で最悪年が最も良かった上位15条件 → 確認期間(2025-26)での成績")
print(top[cols].round(1).to_string(index=False))

# 参考: 探索期間の平均で選んだ場合
top2 = R.sort_values("exp", ascending=False).head(10).copy()
top2 = pd.concat([top2.drop(columns="mask"), top2["mask"].apply(conf)], axis=1)
print("\n### 参考: 探索期間の平均回収率で選んだ上位10条件 → 確認期間")
print(top2[cols].round(1).to_string(index=False))
