# -*- coding: utf-8 -*-
"""
新馬戦の指数づくり: 研究用データ構築。
今走: 新馬戦（T_BAC.class='A1'、芝ダ）の T_KYI + T_BAC + T_CYB + T_UKC（出走前データ）。結果は今走の T_SED。
その日より前の成績（すべて今走の日付より前の T_SED だけで累積、同じ日のレースは含めない）:
  - 新馬戦での 父・母父・厩舎・騎手・生産者・馬主 別の成績（出走数・3着内数・複勝払戻の合計）
  - 兄姉（同じ母の産駒）の全レースの成績（出走数・3着内数・勝利数・到達した最高クラス）
※ T_SED は 2020-01 以降しか無いので、2020年は累積が少ない。評価は2021年以降。
出力: .scratch/newbie_base.pkl
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
         TRIM(b.tds_code) AS tds, CAST(TRIM(b.distance) AS UNSIGNED) AS dist, TRIM(b.syubetsu) AS syubetsu, TRIM(b.kigou) AS kigou,
         CAST(k.uma_num AS UNSIGNED) AS uma, CAST(k.waku_num AS UNSIGNED) AS waku, TRIM(k.blood_reg_num) AS blood,
         k.idm, k.joho_index, k.kyusha_index, k.chokyo_index, k.gekiso_index, k.sogo_index, k.kishu_index, k.ninki_index,
         k.ten_index, k.agari_index, k.pace_index, k.ichi_index, k.manbaken_index, k.kijun_odds,
         TRIM(k.kyakushitsu) AS kya, TRIM(k.kyori_tekisei) AS kyori_tek, TRIM(k.omo_tekisei) AS omo_tek, TRIM(k.shiba_tekisei) AS shiba_tek,
         TRIM(k.dirt_tekisei) AS dirt_tek, TRIM(k.joshodo) AS joshodo, TRIM(k.chokyo_yajirushi) AS yaji, TRIM(k.kyusha_hyoka) AS kyu_hyoka,
         TRIM(k.hohbokusaki_rank) AS hob_r, TRIM(k.hohbokusaki) AS hob, TRIM(k.nyukyu_nichi_mae) AS nyu_d, TRIM(k.taigata) AS taigata,
         TRIM(k.hizume_code) AS hizume, k.uma_start_index, k.uma_okure_rate, TRIM(k.blinker) AS blinker, TRIM(k.seibetsu_code) AS sex,
         k.futan_juryo, TRIM(k.minarai_kubun) AS minarai, TRIM(k.kishu_code) AS jockey, TRIM(k.trainer_code) AS trainer,
         TRIM(k.trainer_belong) AS belong, TRIM(k.umanushi_code) AS owner, TRIM(k.umanushi_name) AS owner_name,
         TRIM(k.in_sogo) AS in_sogo, TRIM(k.in_joho) AS in_joho, TRIM(k.in_kyusha) AS in_kyusha, TRIM(k.in_chokyo) AS in_chokyo,
         TRIM(k.in_idm) AS in_idm, TRIM(k.in_kishu) AS in_kishu, TRIM(k.in_gekiso) AS in_gekiso, k.kishu_renntai_rate,
         c.oi_index, c.shiage_index, TRIM(c.chokyo_ryo_hyoka) AS ryo, TRIM(c.shiage_index_henka) AS shiage_henka, c.isshuumae_oi_index AS oi_1w,
         TRIM(c.chokyo_type) AS ctype, TRIM(c.chokyo_course_type) AS ccourse, TRIM(c.course_saka) AS c_saka, TRIM(c.course_w) AS c_w,
         TRIM(c.course_poly) AS c_poly, TRIM(c.course_da) AS c_da, TRIM(c.course_shiba) AS c_shiba, TRIM(c.chokyo_juten) AS juten,
         TRIM(s.order_of_finish) AS fin, TRIM(s.ijou_kubun) AS ijou, s.win, s.place,
         TRIM(u.birthdate) AS birth, TRIM(u.chichi_uma_name) AS sire, TRIM(u.haha_uma_name) AS dam, TRIM(u.hahachichi_name) AS damsire,
         TRIM(u.seisansha_name) AS breeder, TRIM(u.chichi_keitou_code) AS sire_line, TRIM(u.hahachichi_keitou_code) AS damsire_line,
         TRIM(u.sanchi_name) AS sanchi
  FROM T_KYI k
  JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
  JOIN T_SED s ON s.course_code=k.course_code AND s.year_code=k.year_code AND s.kai=k.kai AND s.day_code=k.day_code AND s.race_num=k.race_num AND s.umaban=k.uma_num
  LEFT JOIN T_CYB c ON c.course_code=k.course_code AND c.year_code=k.year_code AND c.kai=k.kai AND c.day_code=k.day_code AND c.race_num=k.race_num AND c.uma_num=k.uma_num
  LEFT JOIN T_UKC u ON u.blood_reg_num=k.blood_reg_num
  WHERE TRIM(b.class)='A1' AND b.tds_code IN ('1','2')""", c)
sed = pd.read_sql("""
  SELECT TRIM(s.blood_num) AS blood, TRIM(s.ymd) AS ymd, TRIM(s.class) AS cls, TRIM(s.tds_code) AS tds, TRIM(s.order_of_finish) AS fin,
         TRIM(s.ijou_kubun) AS ijou, TRIM(s.jockey_code) AS jockey, TRIM(s.trainer_code) AS trainer, s.place,
         TRIM(u.chichi_uma_name) AS sire, TRIM(u.haha_uma_name) AS dam, TRIM(u.hahachichi_name) AS damsire, TRIM(u.seisansha_name) AS breeder,
         TRIM(k.umanushi_code) AS owner
  FROM T_SED s LEFT JOIN T_UKC u ON u.blood_reg_num=s.blood_num
  LEFT JOIN T_KYI k ON k.course_code=s.course_code AND k.year_code=s.year_code AND k.kai=s.kai AND k.day_code=s.day_code AND k.race_num=s.race_num AND k.uma_num=s.umaban
  WHERE s.tds_code IN ('1','2')""", c)
c.close()
NUM = ["idm", "joho_index", "kyusha_index", "chokyo_index", "gekiso_index", "sogo_index", "kishu_index", "ninki_index", "ten_index", "agari_index",
       "pace_index", "ichi_index", "manbaken_index", "kijun_odds", "uma_start_index", "uma_okure_rate", "futan_juryo", "kishu_renntai_rate",
       "oi_index", "shiage_index", "oi_1w", "win", "place", "fin"]
for col in NUM:
    cur[col] = pd.to_numeric(cur[col], errors="coerce")
sed["fin"] = pd.to_numeric(sed.fin, errors="coerce"); sed["place"] = pd.to_numeric(sed.place, errors="coerce").fillna(0)
cur = cur[cur.kijun_odds.between(1, 999)].copy()
normal = cur.ijou.isin(["0", ""]) | cur.ijou.isna()
cur["win"] = np.where(normal, cur.win.fillna(0), 0.0)
cur["place"] = np.where(normal, cur.place.fillna(0), 0.0)
cur["top3"] = (normal & (cur.fin <= 3)).astype(int)
cur["y"] = cur.ymd.str[:4].astype(int)
cur["heads"] = cur.groupby("rid").uma.transform("size")
cur["birth_m"] = pd.to_numeric(cur.birth.str[4:6], errors="coerce")
cur["age"] = cur.y - pd.to_numeric(cur.birth.str[:4], errors="coerce")

ok = sed.ijou.isin(["0", ""]) | sed.ijou.isna()
sed["top3"] = (ok & (sed.fin <= 3)).astype(int)
sed["win1"] = (ok & (sed.fin == 1)).astype(int)
sed = sed.drop_duplicates(["blood", "ymd"])


def before_stats(src, key, prefix):
    """key 別に、日ごとに集計して累積し、その日より前（同じ日は含めない）の出走数・3着内数・複勝払戻の合計を返す。"""
    g = src.dropna(subset=[key]).groupby([key, "ymd"]).agg(n=("top3", "size"), t3=("top3", "sum"), w=("win1", "sum"), pl=("place", "sum")).reset_index()
    g = g.sort_values([key, "ymd"])
    for col in ("n", "t3", "w", "pl"):
        g[f"{prefix}_{col}"] = g.groupby(key)[col].cumsum() - g[col]
    return g[[key, "ymd"] + [f"{prefix}_{col}" for col in ("n", "t3", "w", "pl")]]


debut = sed[sed.cls == "A1"]
d = cur
for key, prefix in (("sire", "s"), ("damsire", "ds"), ("trainer", "t"), ("jockey", "j"), ("breeder", "b"), ("owner", "o")):
    d = d.merge(before_stats(debut, key, prefix), on=[key, "ymd"], how="left")   # 今走の行がその日に必ずあるので「前日まで」の累積が付く
# 兄姉（同じ母）の全レース成績: 母ごとの累積（自分は新馬なので、その日より前の母の産駒成績 = 兄姉の成績）
d = d.merge(before_stats(sed, "dam", "sib"), on=["dam", "ymd"], how="left")
CLS = {"A1": 0, "A2": 0, "A3": 0, "05": 1, "10": 2, "16": 3, "OP": 4}
sc = sed.dropna(subset=["dam"]).assign(cv=lambda x: x.cls.map(CLS)).groupby(["dam", "ymd"]).cv.max().reset_index().sort_values(["dam", "ymd"])
sc["sib_cls_max"] = sc.groupby("dam").cv.transform(lambda s: s.shift(1).cummax().ffill())   # その日より前の最大（cummax の欠損は ffill で埋める）
d = d.merge(sc[["dam", "ymd", "sib_cls_max"]], on=["dam", "ymd"], how="left")
miss = d.sib_cls_max.isna() & d.dam.notna()
if miss.any():   # その日に母の産駒の出走が自分だけ…は無い（自分の新馬戦がある）ので通常は欠損しないが念のため
    pass
d.to_pickle(os.path.join(ROOT, ".scratch", "newbie_base.pkl"))
print(len(d), "頭", d.rid.nunique(), "レース", d.y.value_counts().sort_index().to_dict())
print("父の新馬成績が分かる割合(2022以降, 10走以上)", (d[d.y >= 2022].s_n >= 10).mean().round(3), " 兄姉の出走ありの割合", (d[d.y >= 2022].sib_n >= 1).mean().round(3))
