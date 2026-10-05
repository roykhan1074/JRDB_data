# -*- coding: utf-8 -*-
"""
厩舎ごとの追切指数・仕上指数のクセと成績の関係（研究用・DB書き込みなし）
- 厩舎の「普段の水準」= その年より前の全データでの、その厩舎の馬の追切/仕上指数の平均（先読みなし、100頭以上）
- 比較: レース内順位（現行 調教SPの考え方） vs 厩舎の普段との差 vs 厩舎の普段との差のレース内順位
- 厩舎のタイプ（普段の追切が強い/中/軽い）別に、レース内1位の効き方が違うか
評価: 複勝回収率の「同年・同基準オッズ帯平均との差」(pt)、年別の向き
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "chokyo_sp_eval.py"), encoding="utf-8").read().split("YRS = range")[0])
from kyusha_multi_screen import conn  # noqa

v = d[(d.oi0 > 0) & (d.sh0 > 0)].copy()
names = pd.read_sql("SELECT TRIM(trainer_code) trainer, MAX(TRIM(trainer_name)) name FROM T_KYI GROUP BY 1", conn()).set_index("trainer").name

# 厩舎の普段の水準（その年より前のデータだけ）
ym = v.groupby(["trainer", "y"]).agg(so=("oi0", "sum"), ss=("sh0", "sum"), c=("oi0", "size"),
                                      so2=("oi0", lambda s: (s ** 2).sum()), ss2=("sh0", lambda s: (s ** 2).sum())).reset_index().sort_values(["trainer", "y"])
for col in ("so", "ss", "c", "so2", "ss2"):
    ym["p_" + col] = ym.groupby("trainer")[col].cumsum() - ym[col]
ok = ym.p_c >= 100
ym["t_oi"] = np.where(ok, ym.p_so / ym.p_c, np.nan); ym["t_sh"] = np.where(ok, ym.p_ss / ym.p_c, np.nan)
ym["t_oi_sd"] = np.where(ok, np.sqrt(ym.p_so2 / ym.p_c - ym.t_oi ** 2), np.nan)
ym["t_sh_sd"] = np.where(ok, np.sqrt(ym.p_ss2 / ym.p_c - ym.t_sh ** 2), np.nan)
v = v.merge(ym[["trainer", "y", "t_oi", "t_sh", "t_oi_sd", "t_sh_sd"]], on=["trainer", "y"], how="left")
v["oi_dev"] = v.oi0 - v.t_oi; v["sh_dev"] = v.sh0 - v.t_sh
# 厩舎の普段との差のレース内順位（普段の水準が分かる馬のみで順位付け）
v["oi_dev_rk"] = v.groupby("rid").oi_dev.rank(ascending=False, method="min")
v["sh_dev_rk"] = v.groupby("rid").sh_dev.rank(ascending=False, method="min")
x = v[(v.y >= 2021) & v.t_oi.notna()].copy()
YRS = range(2021, 2027)

# ---- 1. 厩舎ごとの普段の水準（全期間の記述統計）
print("## 1. 厩舎ごとの追切指数・仕上指数の平均（2020〜2026、300頭以上の厩舎）")
tt = v.groupby("trainer").agg(n=("oi0", "size"), 追切平均=("oi0", "mean"), 仕上平均=("sh0", "mean"),
                              追切1位率=("oi_rk", lambda s: (s == 1).mean() * 100), 複勝=("place", "mean"), 複差=("place_x", "mean"), 単差=("win_x", "mean"))
tt = tt[tt.n >= 300]; tt["厩舎"] = tt.index.map(names)
print(f"厩舎数 {len(tt)}、追切平均の分布: 最小{tt.追切平均.min():.1f} / 25%{tt.追切平均.quantile(.25):.1f} / 中央{tt.追切平均.median():.1f} / 75%{tt.追切平均.quantile(.75):.1f} / 最大{tt.追切平均.max():.1f}")
print(f"全馬の追切指数: 平均{v.oi0.mean():.1f} 標準偏差{v.oi0.std():.1f}")
cols = ["厩舎", "n", "追切平均", "仕上平均", "追切1位率", "複勝", "複差", "単差"]
print("\n追切平均が高い10厩舎"); print(tt.sort_values("追切平均", ascending=False)[cols].head(10).round(1).to_string())
print("\n追切平均が低い10厩舎"); print(tt.sort_values("追切平均")[cols].head(10).round(1).to_string())
print(f"\n厩舎の追切平均と複勝の同オッズ差の相関: {tt[['追切平均', '複差']].corr().iloc[0, 1]:+.2f}（厩舎単位）")


def tab(df, col, title, order=None):
    t = df.groupby(col).agg(n=("place", "size"), 単勝=("win", "mean"), 複勝=("place", "mean"), 単差=("win_x", "mean"), 複差=("place_x", "mean"))
    yr = df.groupby([col, "y"]).place_x.mean().unstack()
    t["年別複差"] = yr.apply(lambda r: "/".join(f"{v_:+.0f}" for v_ in r.values), axis=1)
    t["+年"] = (yr > 0).sum(axis=1)
    if order: t = t.reindex([o for o in order if o in t.index])
    print(f"\n### {title}"); print(t.round(1).to_string())


# ---- 2. レース内順位 vs 厩舎の普段との差
rkb = lambda r: np.select([r == 1, r <= 3, r <= 6], ["1位", "2-3位", "4-6位"], "7位~")
devb = lambda s: np.select([s >= 10, s >= 5, s > -5, s > -10], ["+10~", "+5~10", "±5", "-5~-10"], "-10~")
O1 = ["1位", "2-3位", "4-6位", "7位~"]; O2 = ["+10~", "+5~10", "±5", "-5~-10", "-10~"]
print("\n\n## 2. 追切指数: レース内順位 vs 厩舎の普段との差（2021〜2026、新馬除外）")
x["a"] = rkb(x.oi_rk); tab(x, "a", "追切指数のレース内順位（現行の見方）", O1)
x["b"] = devb(x.oi_dev); tab(x, "b", "追切指数 − その厩舎の普段の平均", O2)
x["c"] = rkb(x.oi_dev_rk); tab(x, "c", "『厩舎の普段との差』のレース内順位", O1)
print("\n## 2'. 仕上指数")
x["a"] = rkb(x.sh_rk); tab(x, "a", "仕上指数のレース内順位（現行の見方）", O1)
x["b"] = devb(x.sh_dev); tab(x, "b", "仕上指数 − その厩舎の普段の平均", O2)
x["c"] = rkb(x.sh_dev_rk); tab(x, "c", "『厩舎の普段との差』のレース内順位", O1)

# ---- 3. 厩舎のタイプ別（普段の追切平均の三分位、その年より前の値で分類）
q = x.t_oi.quantile([1 / 3, 2 / 3]).to_numpy()
x["tp"] = np.select([x.t_oi >= q[1], x.t_oi >= q[0]], ["強い追切の厩舎", "中間"], "軽い追切の厩舎")
print(f"\n\n## 3. 厩舎のタイプ別（普段の追切平均: 軽い<{q[0]:.1f}≦中間<{q[1]:.1f}≦強い）× 追切指数のレース内順位")
x["a"] = x.tp + "×" + rkb(x.oi_rk)
tab(x, "a", "厩舎タイプ × 追切レース内順位", [f"{t}×{o}" for t in ("強い追切の厩舎", "中間", "軽い追切の厩舎") for o in O1])
x["b"] = x.tp + "×" + devb(x.oi_dev)
tab(x, "b", "厩舎タイプ × 厩舎の普段との差", [f"{t}×{o}" for t in ("強い追切の厩舎", "中間", "軽い追切の厩舎") for o in O2])
qs = x.t_sh.quantile([1 / 3, 2 / 3]).to_numpy()
x["tps"] = np.select([x.t_sh >= qs[1], x.t_sh >= qs[0]], ["強い仕上の厩舎", "中間", ], "軽い仕上の厩舎")
x["a"] = x.tps + "×" + rkb(x.sh_rk)
tab(x, "a", "厩舎タイプ(仕上) × 仕上レース内順位", [f"{t}×{o}" for t in ("強い仕上の厩舎", "中間", "軽い仕上の厩舎") for o in O1])

# ---- 4. 森秀行厩舎
m = v[v.trainer == "10298"].copy()
print(f"\n\n## 4. 森秀行厩舎（2020〜2026、新馬除外 {len(m)}頭）: 追切平均{m.oi0.mean():.1f}（全馬{v.oi0.mean():.1f}）、仕上平均{m.sh0.mean():.1f}（全馬{v.sh0.mean():.1f}）、追切レース内1位の割合{(m.oi_rk==1).mean()*100:.0f}%（全馬{(v.oi_rk==1).mean()*100:.0f}%）")
m["a"] = rkb(m.oi_rk); tab(m, "a", "森秀行厩舎: 追切のレース内順位", O1)
mm = m[m.t_oi.notna()].copy()
mm["b"] = devb(mm.oi_dev); tab(mm, "b", "森秀行厩舎: 追切 − 厩舎の普段（2021〜）", O2)
mm["b"] = devb(mm.sh_dev); tab(mm, "b", "森秀行厩舎: 仕上 − 厩舎の普段（2021〜）", O2)


# ---- 5. 調教SPを「厩舎の普段との差」で計算した版と比較（2021〜2026、同じ馬・同じしきい値）
print("\n\n## 5. 調教SP: 現行（レース内順位） vs 厩舎の普段との差で計算した版")
w = v[v.y >= 2021].copy()
# 普段の水準が無い厩舎（新規開業など）は生の値で代用
w["oi_a"] = np.where(w.t_oi.notna(), w.oi0 - w.t_oi + 50, w.oi0)
w["sh_a"] = np.where(w.t_sh.notna(), w.sh0 - w.t_sh + 50, w.sh0)
g = w.groupby("rid")
for c in ("oi_a", "sh_a"):
    w[c + "_rk"] = g[c].rank(ascending=False, method="min")
    w[c + "_z"] = (w[c] - g[c].transform("mean")) / g[c].transform(lambda s: s.std(ddof=0)).replace(0, np.nan)
w["sp_adj"] = bonus(w.oi_a_rk) + bonus(w.sh_a_rk) + np.minimum(0, np.round((w.oi_a_z.fillna(0) + w.sh_a_z.fillna(0)))) + w.yjPt + w.hbPt
w["g_adj"] = np.select([w.sp_adj >= 4, w.sp_adj >= 2, w.sp_adj >= -1, w.sp_adj >= -4], ["A", "B", "C", "D"], "E")
for col, lab in (("grade", "現行 調教SP"), ("g_adj", "厩舎の普段との差で計算した調教SP")):
    rows = []
    for gr in "ABCDE":
        s = w[w[col] == gr]
        rows.append({"グレード": gr, "n": len(s), "単勝": s.win.mean(), "複勝": s.place.mean(), "単差": s.win_x.mean(), "複差": s.place_x.mean(),
                     "年別複差": "/".join(f"{s[s.y==Y].place_x.mean():+.0f}" for Y in range(2021, 2027)),
                     "年別 単/複": " ".join(f"{s[s.y==Y].win.mean():.0f}/{s[s.y==Y].place.mean():.0f}" for Y in range(2021, 2027))})
    print(f"\n### {lab}"); print(pd.DataFrame(rows).round(1).to_string(index=False))
print("\nグレードが入れ替わった馬:", int((w.grade != w.g_adj).sum()), "頭 /", len(w))
