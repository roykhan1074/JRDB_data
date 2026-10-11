# -*- coding: utf-8 -*-
"""
障害戦の指数づくり: 研究用データ構築。
今走: T_KYI + T_BAC（tds_code='3'）+ T_CYB（出走前データ）、結果は今走の T_SED。
過去成績: T_SED（全レース、今走の日付より前のものだけ）から、馬・騎手・調教師の障害/平地の成績を作る。
  ※ T_SED は 2020-01 以降しか無いので、2020年の馬は経験が少なく数えられる。評価は2021年以降を主に見る。
年齢: T_UKC.birthdate。
出力: .scratch/jump_base.pkl
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
cur = pd.read_sql("""
  SELECT CONCAT(k.course_code,k.year_code,k.kai,k.day_code,k.race_num) AS rid, TRIM(b.ymd) AS ymd, TRIM(k.course_code) AS course,
         CAST(TRIM(b.distance) AS UNSIGNED) AS dist, TRIM(b.class) AS cls, TRIM(b.grade) AS grade, TRIM(b.weight) AS wtype,
         CAST(k.uma_num AS UNSIGNED) AS uma, CAST(k.waku_num AS UNSIGNED) AS waku, TRIM(k.blood_reg_num) AS blood,
         k.idm, k.joho_index, k.kyusha_index, k.chokyo_index, k.gekiso_index, k.sogo_index, k.kishu_index, k.ninki_index,
         k.kijun_odds, k.kijun_fukusho_odds, TRIM(k.kyakushitsu) AS kya, TRIM(k.kyori_tekisei) AS kyori_tek, TRIM(k.omo_tekisei) AS omo_tek,
         TRIM(k.joshodo) AS joshodo, TRIM(k.rotation) AS rotation, TRIM(k.chokyo_yajirushi) AS yaji, TRIM(k.kyusha_hyoka) AS kyu_hyoka,
         TRIM(k.hohbokusaki_rank) AS hob_r, TRIM(k.nyukyu_hashiri) AS nyu_n, TRIM(k.blinker) AS blinker, TRIM(k.seibetsu_code) AS sex,
         k.futan_juryo, TRIM(k.minarai_kubun) AS minarai, TRIM(k.kishu_code) AS jockey, TRIM(k.trainer_code) AS trainer,
         TRIM(k.in_sogo) AS in_sogo, TRIM(k.in_joho) AS in_joho, TRIM(k.in_kyusha) AS in_kyusha, TRIM(k.in_chokyo) AS in_chokyo,
         TRIM(k.in_gekiso) AS in_gekiso, k.gekiso_juni, k.kishu_renntai_rate, TRIM(k.taigata) AS taigata, TRIM(k.hizume_code) AS hizume,
         k.uma_start_index, k.uma_okure_rate, TRIM(k.prev1_seiseki_key) AS p1key,
         c.oi_index, c.shiage_index, TRIM(c.chokyo_ryo_hyoka) AS ryo, TRIM(c.shiage_index_henka) AS shiage_henka,
         TRIM(c.course_sho) AS c_sho, TRIM(c.course_saka) AS c_saka, TRIM(c.course_w) AS c_w, TRIM(c.chokyo_type) AS ctype,
         TRIM(s.order_of_finish) AS fin, TRIM(s.ijou_kubun) AS ijou, s.win, s.place, TRIM(s.horse_weight) AS bw,
         TRIM(u.birthdate) AS birth, TRIM(u.chichi_keitou_code) AS sire_line
  FROM T_KYI k
  JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
  JOIN T_SED s ON s.course_code=k.course_code AND s.year_code=k.year_code AND s.kai=k.kai AND s.day_code=k.day_code AND s.race_num=k.race_num AND s.umaban=k.uma_num
  LEFT JOIN T_CYB c ON c.course_code=k.course_code AND c.year_code=k.year_code AND c.kai=k.kai AND c.day_code=k.day_code AND c.race_num=k.race_num AND c.uma_num=k.uma_num
  LEFT JOIN T_UKC u ON u.blood_reg_num=k.blood_reg_num
  WHERE b.tds_code='3'""", c)
sed = pd.read_sql("""
  SELECT CONCAT(course_code,year_code,kai,day_code,race_num) AS srid, TRIM(blood_num) AS blood, TRIM(ymd) AS ymd, TRIM(tds_code) AS tds,
         TRIM(course_code) AS course, CAST(TRIM(distance) AS UNSIGNED) AS dist, TRIM(class) AS cls, TRIM(order_of_finish) AS fin,
         TRIM(ijou_kubun) AS ijou, TRIM(jockey_code) AS jockey, TRIM(trainer_code) AS trainer, TRIM(idm) AS idm, TRIM(win_diff) AS wdiff,
         CAST(TRIM(heads) AS UNSIGNED) AS heads, TRIM(win_odds_rank) AS ninki, place
  FROM T_SED""", c)
c.close()
for col in ("idm", "joho_index", "kyusha_index", "chokyo_index", "gekiso_index", "sogo_index", "kishu_index", "ninki_index", "kijun_odds",
            "kijun_fukusho_odds", "futan_juryo", "gekiso_juni", "kishu_renntai_rate", "uma_start_index", "uma_okure_rate", "oi_index",
            "shiage_index", "win", "place", "fin"):
    cur[col] = pd.to_numeric(cur[col], errors="coerce")
for col in ("fin", "idm", "wdiff", "ninki", "place"):
    sed[col] = pd.to_numeric(sed[col], errors="coerce")
cur = cur[cur.kijun_odds.between(1, 999)].copy()
normal = cur.ijou.isin(["0", ""]) | cur.ijou.isna()
cur["win"] = np.where(normal, cur.win.fillna(0), 0.0)
cur["place"] = np.where(normal, cur.place.fillna(0), 0.0)
cur["top3"] = (normal & (cur.fin <= 3)).astype(int)
cur["chushi"] = (cur.ijou == "3").astype(int)       # 競走中止（落馬など）
cur["y"] = cur.ymd.str[:4].astype(int)
cur["heads"] = cur.groupby("rid").uma.transform("size")
cur["age"] = cur.y - pd.to_numeric(cur.birth.str[:4], errors="coerce")

# --- T_SED の過去成績（その日より前）
sed = sed.drop_duplicates(["blood", "ymd"]).sort_values(["blood", "ymd"]).reset_index(drop=True)
ok = sed.ijou.isin(["0", ""]) | sed.ijou.isna()
sed["top3"] = (ok & (sed.fin <= 3)).astype(int)
sed["win1"] = (ok & (sed.fin == 1)).astype(int)
sed["chushi"] = (sed.ijou == "3").astype(int)
sed["jump"] = (sed.tds == "3").astype(int)
g = sed.groupby("blood")
for k in ("jump", "top3", "win1", "chushi"):
    sed[f"c_{k}"] = g[k].cumsum() - sed[k]
for k in ("top3", "win1", "chushi"):
    x = sed[k] * sed.jump
    sed[f"cj_{k}"] = x.groupby(sed.blood).cumsum() - x
sed["c_runs"] = g.cumcount()
sed["c_flat"] = sed.c_runs - sed.c_jump
xf = sed.top3 * (1 - sed.jump); sed["cf_top3"] = xf.groupby(sed.blood).cumsum() - xf
xw = sed.win1 * (1 - sed.jump); sed["cf_win1"] = xw.groupby(sed.blood).cumsum() - xw
# 平地での最高クラス（未勝利=0,1勝=1,2勝=2,3勝=3,OP=4）: 前のレースまでの最大
CLS = {"A1": 0, "A2": 0, "A3": 0, "05": 1, "10": 2, "16": 3, "OP": 4}
sed["flat_cls"] = np.where(sed.jump == 0, sed.cls.map(CLS), np.nan)
# 2026-10-12 修正: cummax は欠損の位置を欠損のまま残すため、ffill で「それまでの最大」を埋める（以前は前走が障害だと欠損になっていた）
sed["flat_cls_max"] = sed.groupby("blood").flat_cls.transform(lambda s: s.shift(1).cummax().ffill())
# 障害の前走・平地の前走
sed["prev_tds"] = g.tds.shift(1); sed["prev_fin"] = g.fin.shift(1); sed["prev_ijou"] = g.ijou.shift(1)
sed["prev_ymd"] = g.ymd.shift(1); sed["prev_course"] = g.course.shift(1); sed["prev_dist"] = g.dist.shift(1)
sed["prev_wdiff"] = g.wdiff.shift(1); sed["prev_idm"] = g.idm.shift(1); sed["prev_cls"] = g.cls.shift(1)
sed["prev2_tds"] = g.tds.shift(2); sed["prev2_fin"] = g.fin.shift(2)
# 同じ障害コース（競馬場）での実績
x = sed.top3 * sed.jump
sed["cjc_top3"] = x.groupby([sed.blood, sed.course]).cumsum() - x
xx = sed.jump; sed["cjc_n"] = xx.groupby([sed.blood, sed.course]).cumsum() - xx
# 障害での最高IDM（前走まで）
sed["jidm"] = np.where(sed.jump == 1, sed.idm, np.nan)
sed["jidm_max"] = sed.groupby("blood").jidm.transform(lambda s: s.shift(1).cummax().ffill())
sed["jidm_last"] = sed.groupby("blood").jidm.transform(lambda s: s.shift(1).ffill())
hist = sed.drop(columns=["srid", "tds", "course", "dist", "cls", "fin", "ijou", "jockey", "trainer", "idm", "wdiff", "heads", "ninki",
                         "place", "top3", "win1", "chushi", "jump", "flat_cls", "jidm"])
d = cur.merge(hist, on=["blood", "ymd"], how="left")

# --- 騎手・調教師の障害成績（その日より前、日単位で累積して同日分は含めない）
def person_stats(key):
    j = sed[sed.jump == 1].groupby([key, "ymd"]).agg(n=("top3", "size"), t3=("top3", "sum"), w=("win1", "sum"), ch=("chushi", "sum"),
                                                     pl=("place", lambda s: s.fillna(0).sum())).reset_index()
    j = j.sort_values([key, "ymd"])
    for col in ("n", "t3", "w", "ch", "pl"):
        j[f"{key}_{col}"] = j.groupby(key)[col].cumsum() - j[col]
    return j[[key, "ymd"] + [f"{key}_{col}" for col in ("n", "t3", "w", "ch", "pl")]]

for key in ("jockey", "trainer"):
    st = person_stats(key)
    d = d.merge(st, on=[key, "ymd"], how="left")   # 当日の行は「前日まで」の累積
    # 当日に障害の騎乗が無い日の値は無いので、直前の値で補う
    miss = d[f"{key}_n"].isna()
    if miss.any():
        st2 = st.sort_values("ymd")
        left = d.loc[miss, [key, "ymd"]].reset_index(); left["yi"] = left.ymd.astype(int); left = left.sort_values("yi")
        right = st2.copy(); right["yi2"] = right.ymd.astype(int); right = right.drop(columns="ymd").sort_values("yi2")
        left[key] = left[key].astype(object); right[key] = right[key].astype(object)
        fill = pd.merge_asof(left, right, left_on="yi", right_on="yi2", by=key, allow_exact_matches=False)
        for col in ("n", "t3", "w", "ch", "pl"):
            d.loc[fill["index"].values, f"{key}_{col}"] = fill[f"{key}_{col}"].values
d.to_pickle(os.path.join(ROOT, ".scratch", "jump_base.pkl"))
print(len(d), "頭", d.rid.nunique(), "レース", d.y.value_counts().sort_index().to_dict())
print("障害の過去出走数の分布(2022以降)", d[d.y >= 2022].c_jump.clip(0, 10).value_counts().sort_index().to_dict())
print("騎手の障害騎乗数が分かる割合", d.jockey_n.notna().mean().round(3))
