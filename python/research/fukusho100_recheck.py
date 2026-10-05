# -*- coding: utf-8 -*-
"""
複勝回収率100%超シグナル（複勝sc≥3 × 基準オッズ15〜30倍）を、先読みなしで検証し直す（研究用）。
複勝sc = 次の7条件の合計（src/server.ts の /api/watchlist・entries.html と同じ定義）
  scIdx       : EX指数(全体)≥15 または 本命指数(全体)≥10
  scIdxStrong : EX指数(全体)≥50 または 本命指数(全体)≥30
  scCombo     : 騎手×調教師の複勝回収率≥100% かつ 30戦以上
  scChokyo    : 追切指数≥70 または 仕上指数≥70
  scGoal      : 展開予測順位 1〜2位
  scJoho      : 情報指数のレース内順位（0・-1除外の密順位）1〜2位
  scTa        : テン指数順位1位 または 上がり指数順位1位
版:
  先読みあり（本番の値）: 本番 T_ANABA_SCORE / T_HONMEI_SCORE（2026-10-04の新方式）、T_COMBO_RECOVERY（全期間）
  先読みなし（新指数）  : T_ANABA_SCORE_WF2 / T_HONMEI_SCORE_WF2（毎年直前年まで集計）、騎手×調教師はその日より前の結果のみ
  先読みなし（旧指数）  : T_ANABA_SCORE_WF / T_HONMEI_SCORE_WF（旧方式、2024〜2026のみ）、騎手×調教師は同上
"""
import sys, io, os
if (sys.stdout.encoding or "").lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
import numpy as np, pandas as pd, mysql.connector
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
e = {}
for l in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
    l = l.strip()
    if l and "=" in l and not l.startswith("#"):
        k, v = l.split("=", 1); e[k] = v
c = mysql.connector.connect(host=e["DB_HOST"], port=int(e["DB_PORT"]), user=e["DB_USER"], password=e["DB_PASS"], database=e["DB_NAME"])
J = lambda a: f"{a}.course_code=k.course_code AND {a}.year_code=k.year_code AND {a}.kai=k.kai AND {a}.day_code=k.day_code AND {a}.race_num=k.race_num AND {a}.uma_num=k.uma_num"
JB = "b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num"
d = pd.read_sql(f"""
  SELECT b.ymd, CONCAT(k.course_code,k.year_code,k.kai,k.day_code,k.race_num) AS rid, k.uma_num,
         TRIM(k.kishu_code) kishu, TRIM(k.trainer_code) trainer, TRIM(k.kijun_odds) odds, TRIM(k.joho_index) joho,
         TRIM(k.goal_juni) goal, TRIM(k.ten_index_juni) ten, TRIM(k.agari_index_juni) agari,
         TRIM(c.oi_index) oi, TRIM(c.shiage_index) shiage,
         a.overall_score ex_lk, h.overall_score hm_lk, a2.overall_score ex_wf2, h2.overall_score hm_wf2,
         a1.overall_score ex_wf1, h1.overall_score hm_wf1,
         cr.place_recovery combo_rr_lk, cr.total_count combo_n_lk,
         TRIM(s.order_of_finish) fin, TRIM(s.ijou_kubun) ijou, TRIM(s.place) place, TRIM(s.win) win, TRIM(b.`class`) cls
  FROM T_KYI k JOIN T_BAC b ON {JB}
  JOIN T_SED s ON s.course_code=k.course_code AND s.year_code=k.year_code AND s.kai=k.kai AND s.day_code=k.day_code AND s.race_num=k.race_num AND s.umaban=k.uma_num
  LEFT JOIN T_CYB c ON {J('c')}
  LEFT JOIN T_ANABA_SCORE a ON {J('a')}  LEFT JOIN T_HONMEI_SCORE h ON {J('h')}
  LEFT JOIN T_ANABA_SCORE_WF2 a2 ON {J('a2')}  LEFT JOIN T_HONMEI_SCORE_WF2 h2 ON {J('h2')}
  LEFT JOIN T_ANABA_SCORE_WF a1 ON {J('a1')}  LEFT JOIN T_HONMEI_SCORE_WF h1 ON {J('h1')}
  LEFT JOIN T_COMBO_RECOVERY cr ON cr.kishu_code=k.kishu_code AND cr.trainer_code=k.trainer_code
  WHERE TRIM(b.tds_code) IN ('1','2') AND b.ymd >= '20200101'
""", c)
c.close()
num = lambda s: pd.to_numeric(s.astype(str).str.strip(), errors="coerce")
for col in ("odds", "joho", "goal", "ten", "agari", "oi", "shiage", "ex_lk", "hm_lk", "ex_wf2", "hm_wf2", "ex_wf1", "hm_wf1", "combo_rr_lk", "combo_n_lk", "fin", "place", "win"):
    d[col] = num(d[col])
d = d[d.fin.notna() & (d.fin > 0)].copy()
normal = d.ijou.isin(["0", ""])
d["place"] = np.where(normal, d.place.fillna(0), 0.0)
d["win"] = np.where(normal, d.win.fillna(0), 0.0)
d["y"] = d.ymd.str[:4].astype(int)

# 騎手×調教師の複勝回収率を「その日より前の結果だけ」で計算（全オッズの馬、T_COMBO_RECOVERY と同じ母集団）
d = d.sort_values(["ymd", "rid"])
day = d.groupby(["kishu", "trainer", "ymd"]).agg(n=("place", "size"), pay=("place", "sum")).reset_index().sort_values(["kishu", "trainer", "ymd"])
g = day.groupby(["kishu", "trainer"])
day["cn"] = g.n.cumsum() - day.n
day["cpay"] = g.pay.cumsum() - day.pay
d = d.merge(day[["kishu", "trainer", "ymd", "cn", "cpay"]], on=["kishu", "trainer", "ymd"], how="left")
d["combo_n_wf"] = d.cn
d["combo_rr_wf"] = np.where(d.cn > 0, d.cpay / d.cn.replace(0, np.nan), np.nan)

# 情報指数のレース内密順位（0・-1 を除外）
jv = d.joho.where(~d.joho.isin([0, -1]))
d["joho_rk"] = jv.groupby(d.rid).rank(ascending=False, method="dense")


def fsc(ex, hm, combo_rr, combo_n):
    s_idx = ((ex >= 15) | (hm >= 10)).astype(int)
    s_str = ((ex >= 50) | (hm >= 30)).astype(int)
    s_combo = ((combo_n >= 30) & (combo_rr >= 100)).astype(int)
    s_cho = ((d.oi.fillna(0) >= 70) | (d.shiage.fillna(0) >= 70)).astype(int)
    s_goal = d.goal.isin([1, 2]).astype(int)
    s_joho = d.joho_rk.isin([1, 2]).astype(int)
    s_ta = ((d.ten == 1) | (d.agari == 1)).astype(int)
    return s_idx + s_str + s_combo + s_cho + s_goal + s_joho + s_ta


d["fsc_lk"] = fsc(d.ex_lk, d.hm_lk, d.combo_rr_lk, d.combo_n_lk)
d["fsc_wf2"] = fsc(d.ex_wf2, d.hm_wf2, d.combo_rr_wf, d.combo_n_wf)
d["fsc_wf1"] = fsc(d.ex_wf1, d.hm_wf1, d.combo_rr_wf, d.combo_n_wf)
d["ob"] = pd.cut(d.odds, [1, 2, 3, 5, 10, 15, 30, 50, 1000], right=False)
d["place_b"] = d.groupby(["y", "ob"], observed=True).place.transform("mean")
band = d.odds.between(15, 30, inclusive="left") & (d.cls != "A1")


def show(lab, m, years):
    x = d[m & d.y.isin(years)]
    hits = x.place[x.place > 0].sort_values(ascending=False); k = int(len(hits) * 0.01)
    yr = " / ".join(f"{x[x.y == Y].place.mean():.0f}" for Y in years)
    print(f"| {lab} | {len(x):,} | {(x.fin <= 3).mean() * 100:.1f}% | **{x.place.mean():.1f}%** | {yr} | "
          f"{x.place_b.mean():.1f}% | {x.place.mean() - x.place_b.mean():+.1f} | {(x.place.sum() - hits.iloc[:k].sum()) / len(x):.1f}% |")


for years, title in (([2022, 2023, 2024, 2025, 2026], "2022〜2026年"), ([2024, 2025, 2026], "2024〜2026年（旧指数の先読みなし版と比べるため）")):
    print(f"\n### {title}")
    print("| 版 | 頭数 | 3着内率 | 複勝回収率 | 年別 | 同オッズ複勝平均 | 差 | 当たり上位1%除外 |")
    print("|---|---:|---:|---:|---|---:|---:|---:|")
    show("先読みあり（本番の値）", band & (d.fsc_lk >= 3), years)
    show("先読みなし（新指数）", band & (d.fsc_wf2 >= 3), years)
    if years[0] >= 2024:
        show("先読みなし（旧指数）", band & (d.fsc_wf1 >= 3), years)
    show("参考: 15〜30倍の全馬", band, years)
print("\n### 先読みなし（新指数）で、複勝sc のしきい値を変えた場合（2022〜2026年、15〜30倍）")
print("| 条件 | 頭数 | 3着内率 | 複勝回収率 | 年別 | 同オッズ複勝平均 | 差 | 当たり上位1%除外 |")
print("|---|---:|---:|---:|---|---:|---:|---:|")
for t in (2, 3, 4, 5):
    show(f"複勝sc≥{t}", band & (d.fsc_wf2 >= t), [2022, 2023, 2024, 2025, 2026])

d.to_pickle(os.path.join(ROOT, ".scratch", "fukusho100_base.pkl"))
