# -*- coding: utf-8 -*-
"""
「1番人気が崩れそうなレース」だけで買う戦略の検証（研究用・DB書き込みなし）
- 1番人気 = 基準オッズ最小の馬（レース前に分かる）
- 条件はすべてレース前に分かるJRDB値の単純条件（とその2つの組み合わせ）
- 探索: 2020-2023 / 確認: 2024-2026
"""
import sys, io, os, itertools
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np, pandas as pd
import prob_wf as P                       # stdout は prob_wf 側で UTF-8 化済み
from exotic_wf import load_hjc, parse
pd.set_option("display.width", 250)
EXP, CONF = [2020, 2021, 2022, 2023], [2024, 2025, 2026]

RACES_PKL = os.path.join(P.ROOT, ".scratch", "fav_races.pkl")
df = P.prepare(P.fetch()) if not os.path.exists(RACES_PKL) else pd.DataFrame(columns=["shinba", "kijun_odds", "place_pay", "uma_num", "race_id"])
df = df[(df.shinba == 0) & df.kijun_odds.notna()].copy()
df["place_pay"] = df["place_pay"].fillna(0)
df["uma"] = df["uma_num"].astype(int)
df["pop"] = df.groupby("race_id")["kijun_odds"].rank(method="first")
um, sp = parse(load_hjc())

# ---- レース単位の表（1番人気の特徴 + 各買い方の払戻・購入額） ----
rows = []
for rid, g in ([] if os.path.exists(RACES_PKL) else df.groupby("race_id")):
    if len(g) < 8 or rid not in um:
        continue
    g = g.sort_values("pop")
    f = g.iloc[0]
    by_pop = g.set_index("pop")
    def place(pops):
        s = by_pop.loc[[p for p in pops if p in by_pop.index], "place_pay"]
        return s.sum(), len(s) * 100
    def box(pops, size, table):
        nums = [int(by_pop.loc[p, "uma"]) for p in pops if p in by_pop.index]
        combos = [frozenset(c) for c in itertools.combinations(nums, size)]
        return sum(table.get(rid, {}).get(c, 0) for c in combos), len(combos) * 100
    nf = g.iloc[1:]
    idm_top_nf = nf.sort_values("idm", ascending=False).iloc[0]   # 1番人気以外でIDM最上位
    r = dict(race_id=rid, year=int(f.year), heads=len(g), fav_top3=int(f.fin <= 3),
             f_odds=f.kijun_odds, odds2=g.iloc[1].kijun_odds,
             f_idm_rk=f.idm_rk, f_sogo_rk=f.sogo_index_rk, f_joho_rk=f.joho_index_rk, f_kishu_rk=f.kishu_index_rk,
             f_agari=f.agari_index_juni, f_ten=f.ten_index_juni, f_goal=f.goal_juni, f_yaji=str(f.chokyo_yajirushi),
             f_rot=f.rotation, f_waku=f.waku_num, f_chokyo_rk=f.chokyo_index_rk, f_kyusha_rk=f.kyusha_index_rk,
             f_oi_rk=f.oi_index_rk, tds=f.tds_code)
    for name, pops in [("複勝 2番人気", [2]), ("複勝 2-3番人気", [2, 3]), ("複勝 2-5番人気", [2, 3, 4, 5]),
                       ("複勝 3-5番人気", [3, 4, 5])]:
        r[name + "_pay"], r[name + "_cost"] = place(pops)
    r["複勝 1番人気以外のIDM1位_pay"], r["複勝 1番人気以外のIDM1位_cost"] = idm_top_nf.place_pay, 100
    r["複勝 1番人気_pay"], r["複勝 1番人気_cost"] = f.place_pay, 100
    r["馬連 2-4番人気BOX_pay"], r["馬連 2-4番人気BOX_cost"] = box([2, 3, 4], 2, um)
    r["馬連 2-5番人気BOX_pay"], r["馬連 2-5番人気BOX_cost"] = box([2, 3, 4, 5], 2, um)
    r["三連複 2-5番人気BOX_pay"], r["三連複 2-5番人気BOX_cost"] = box([2, 3, 4, 5], 3, sp)
    r["三連複 2-6番人気BOX_pay"], r["三連複 2-6番人気BOX_cost"] = box([2, 3, 4, 5, 6], 3, sp)
    rows.append(r)
if os.path.exists(RACES_PKL):
    R = pd.read_pickle(RACES_PKL)
else:
    R = pd.DataFrame(rows)
    R.to_pickle(RACES_PKL)
STRATS = [c[:-4] for c in R.columns if c.endswith("_pay")]
print(f"レース数 {len(R):,}  1番人気の3着内率 {R.fav_top3.mean()*100:.1f}%")

# ---- 1番人気が崩れそうな単純条件 ----
C = {
    "IDMが1位でない": R.f_idm_rk > 1,
    "IDMが3位以下": R.f_idm_rk >= 3,
    "総合指数が1位でない": R.f_sogo_rk > 1,
    "情報指数が1位でない": R.f_joho_rk > 1,
    "騎手指数が3位以下": R.f_kishu_rk >= 3,
    "上がり指数4位以下": R.f_agari >= 4,
    "テン指数6位以下": R.f_ten >= 6,
    "展開ゴール順位4位以下": R.f_goal >= 4,
    "調教矢印↓": R.f_yaji.isin(["4", "5"]),
    "調教指数3位以下": R.f_chokyo_rk >= 3,
    "追切指数3位以下": R.f_oi_rk >= 3,
    "厩舎指数3位以下": R.f_kyusha_rk >= 3,
    "外枠(7-8枠)": R.f_waku >= 7,
    "1番人気が3倍以上(混戦)": R.f_odds >= 3,
    "1・2番人気のオッズ差が小(1.5倍未満)": R.odds2 / R.f_odds < 1.5,
    "16頭以上": R.heads >= 16,
    "ダート": R.tds == "2",
    "芝": R.tds == "1",
}
items = list(C.items())
conds = items + [((a[0] + " & " + b[0]), a[1] & b[1]) for a, b in itertools.combinations(items, 2)]


def rec(d, s):
    return d[s + "_pay"].sum() / max(d[s + "_cost"].sum(), 1) * 100


out = []
for cname, m in conds:
    d = R[m]
    e = d[d.year.isin(EXP)]
    if len(e) < 400:
        continue
    for s in STRATS:
        per = {y: rec(d[d.year == y], s) for y in EXP + CONF}
        out.append(dict(cond=cname, strat=s, races_exp=len(e), fav崩れ率=(1 - e.fav_top3.mean()) * 100,
                        探索=rec(e, s), 探索最悪年=min(per[y] for y in EXP),
                        確認=rec(d[d.year.isin(CONF)], s), races_conf=int(d.year.isin(CONF).sum()),
                        **{str(y): per[y] for y in EXP + CONF}))
O = pd.DataFrame(out)
O.to_pickle(os.path.join(P.ROOT, ".scratch", "fav_cond_results.pkl"))

print("\n### 参考: 条件なし（全レース）")
for s in STRATS:
    print(f"  {s:<24} 探索 {rec(R[R.year.isin(EXP)], s):5.1f}%  確認 {rec(R[R.year.isin(CONF)], s):5.1f}%")

cols = ["cond", "strat", "fav崩れ率", "2020", "2021", "2022", "2023", "探索", "races_exp", "2024", "2025", "2026", "確認", "races_conf"]
print("\n### 探索期間(2020-23)の最悪年で選んだ上位25 → 確認期間(2024-26)")
print(O.sort_values("探索最悪年", ascending=False).head(25)[cols].round(1).to_string(index=False))
