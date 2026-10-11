# -*- coding: utf-8 -*-
"""
一変指数（プラス要素探し）の拡張データ構築（研究用）。ippen_base.pkl に以下を足す。
- 今走のレース条件（T_BAC: 牝馬限定・重量種別・競走種別・回り・内外）
- 前走/2走前の成績の詳細（T_SED: 上がり3F順位・4角コース取り・ペース・着差・IDMのレース内順位・前走の条件）
- その馬の過去成績（今走より前の T_SED のみ）: 同じ芝ダ・同コース・同距離帯・同じ回りでの出走数と3着内数
- 前走のレースレベル: 前走で一緒に走った馬の「次走」成績（今走の日付より前に走ったものだけ）
すべて今走の発走前に分かる情報。今走の結果は prev_prepped 由来の列（fin/win/place/…）だけ。
出力: .scratch/ippen_base2.pkl
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
bac = pd.read_sql("""SELECT CONCAT(course_code,year_code,kai,day_code,race_num) AS rid, TRIM(kigou) AS kigou, TRIM(weight) AS wtype,
                     TRIM(syubetsu) AS syubetsu, TRIM(migihidari) AS lr, TRIM(naigai) AS naigai FROM T_BAC""", c)
sed = pd.read_sql("""
  SELECT CONCAT(course_code,year_code,kai,day_code,race_num) AS srid, TRIM(blood_num) AS blood, TRIM(ymd) AS ymd,
         TRIM(course_code) AS course, TRIM(tds_code) AS tds, CAST(TRIM(distance) AS UNSIGNED) AS dist, TRIM(migihidari) AS lr,
         TRIM(kigou) AS kigou, TRIM(weight) AS wtype, TRIM(syubetsu) AS syubetsu, TRIM(grade) AS grade, TRIM(`class`) AS cls,
         CAST(TRIM(heads) AS UNSIGNED) AS heads, TRIM(order_of_finish) AS fin, TRIM(ijou_kubun) AS ijou,
         TRIM(latter_half_time) AS l3f, TRIM(first_half_diff) AS f3d, TRIM(latter_half_diff) AS l3d,
         TRIM(course_posi) AS cposi, TRIM(corner_4_posi) AS c4posi, TRIM(corner_4) AS c4, TRIM(race_pace) AS rpace,
         TRIM(horse_pace) AS hpace, TRIM(race_kyakushitsu) AS rkya, TRIM(win_diff) AS wdiff, TRIM(idm) AS idm,
         TRIM(win_odds_rank) AS ninki, TRIM(baba_cond) AS baba
  FROM T_SED""", c)
c.close()
for col in ("fin", "l3f", "f3d", "l3d", "c4", "wdiff", "idm", "ninki"):
    sed[col] = pd.to_numeric(sed[col], errors="coerce")
sed = sed.drop_duplicates(["blood", "ymd"]).sort_values(["blood", "ymd"]).reset_index(drop=True)
ok = sed.ijou.isin(["0", ""]) | sed.ijou.isna()
sed["top3"] = (ok & (sed.fin <= 3)).astype(int)
sed["win1"] = (ok & (sed.fin == 1)).astype(int)
# レース内の順位（上がり3F・IDM）
sed["l3f_rank"] = sed.groupby("srid").l3f.rank(method="min")
sed["idm_rank"] = sed.groupby("srid").idm.rank(method="min", ascending=False)
sed["dband"] = (sed.dist // 200) * 200
# --- その馬の過去成績（そのレースより前）
g = sed.groupby("blood")
sed["n_runs"] = g.cumcount()
sed["n_top3"] = g.top3.cumsum() - sed.top3
for name, keys in {"tds": ["tds"], "ctds": ["course", "tds"], "dist": ["tds", "dband"], "lr": ["lr"], "cdist": ["course", "tds", "dband"]}.items():
    gg = sed.groupby(["blood"] + keys)
    sed[f"h_{name}_n"] = gg.cumcount()
    sed[f"h_{name}_top3"] = gg.top3.cumsum() - sed.top3
# --- 次走（前走レースレベル用）
sed["next_ymd"] = g.ymd.shift(-1)
sed["next_top3"] = g.top3.shift(-1)

base = pd.read_pickle(os.path.join(ROOT, ".scratch", "ippen_base.pkl"))
d = base.merge(bac, on="rid", how="left", suffixes=("", "_bac"))
# 今走の行の過去成績（今走の T_SED 行の累積値 = 今走より前の成績）
hist_cols = ["n_runs", "n_top3"] + [c for c in sed.columns if c.startswith("h_")]
cur = sed[["blood", "ymd"] + hist_cols]
d = d.merge(cur, on=["blood", "ymd"], how="left")
# 前走・2走前の詳細
pcols = ["srid", "course", "tds", "dist", "lr", "kigou", "wtype", "syubetsu", "grade", "cls", "heads", "fin", "l3f_rank", "f3d", "l3d",
         "cposi", "c4posi", "c4", "rpace", "hpace", "rkya", "wdiff", "idm", "idm_rank", "ninki", "baba", "top3"]
s1 = sed[["blood", "ymd"] + pcols].copy(); s1["p1key"] = s1.blood + s1.ymd
d = d.merge(s1.drop(columns=["blood", "ymd"]).add_prefix("x1_").rename(columns={"x1_p1key": "p1key"}), on="p1key", how="left")
s2 = sed[["blood", "ymd", "fin", "top3", "idm", "tds", "dist"]].copy(); s2["p2key"] = s2.blood + s2.ymd
d = d.merge(s2.drop(columns=["blood", "ymd"]).add_prefix("x2_").rename(columns={"x2_p2key": "p2key"}), on="p2key", how="left")
# --- 前走レースレベル: 前走の同走馬（自分以外）のうち、今走の日付より前に次走を走った馬の3着内率
mates = sed[["srid", "blood", "next_ymd", "next_top3"]].dropna(subset=["next_ymd"])
q = d[["rid", "uma", "blood", "ymd", "x1_srid"]].dropna(subset=["x1_srid"])
pairs = q.merge(mates.rename(columns={"srid": "x1_srid", "blood": "m_blood"}), on="x1_srid")
pairs = pairs[(pairs.m_blood != pairs.blood) & (pairs.next_ymd < pairs.ymd)]
lvl = pairs.groupby(["rid", "uma"]).agg(lvl_n=("next_top3", "size"), lvl_top3=("next_top3", "sum")).reset_index()
d = d.merge(lvl, on=["rid", "uma"], how="left")
d["lvl_rate"] = d.lvl_top3 / d.lvl_n
print("rows", len(d), " 前走詳細あり", d.x1_srid.notna().mean().round(3), " レースレベル算出可", (d.lvl_n >= 5).mean().round(3))
d.to_pickle(os.path.join(ROOT, ".scratch", "ippen_base2.pkl"))
