# -*- coding: utf-8 -*-
"""
一変指数の研究用データ構築。
今走: T_KYI + T_CYB（出走前データ）＋ prev_prepped.pkl（今走の結果・前走T_SED・同オッズ帯平均との差）
前走時の出走前データ: 前走の T_KYI + T_CYB（prev1_race_key + 血統登録番号で結合）
いずれもレース前に確定している情報なので先読みにならない（結果は今走の T_SED のみ）。
出力: .scratch/ippen_base.pkl
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
kyi = pd.read_sql("""
  SELECT CONCAT(k.course_code,k.year_code,k.kai,k.day_code,k.race_num) AS rid, CAST(k.uma_num AS UNSIGNED) AS uma,
         TRIM(k.blood_reg_num) AS blood, TRIM(k.prev1_race_key) AS prk,
         k.idm, k.joho_index, k.kyusha_index, k.chokyo_index, k.kishu_index, k.sogo_index, k.gekiso_index,
         TRIM(k.rotation) AS rotation, TRIM(k.joshodo) AS joshodo, TRIM(k.kyuyo_riyuu_code) AS kyuyo,
         TRIM(k.nyukyu_hashiri) AS nyu_n, TRIM(k.nyukyu_nichi_mae) AS nyu_d, TRIM(k.hohbokusaki) AS hob,
         TRIM(k.hohbokusaki_rank) AS hob_r, TRIM(k.kyusha_rank) AS kyu_rank, TRIM(k.yuso_kubun) AS yuso,
         TRIM(k.blinker) AS blinker, TRIM(k.seibetsu_code) AS sex, TRIM(k.trainer_code) AS trainer,
         TRIM(k.umanushi_code) AS owner, k.kishu_tansho_rate AS j_win, k.kishu_3uchi_rate AS j_3in,
         TRIM(k.minarai_kubun) AS minarai, CAST(k.waku_num AS UNSIGNED) AS waku,
         TRIM(k.in_sogo) AS in_sogo, TRIM(k.in_joho) AS in_joho, TRIM(k.in_kyusha) AS in_kyusha, TRIM(k.in_chokyo) AS in_chokyo,
         TRIM(k.chokyo_yajirushi) AS yaji, TRIM(k.kyusha_hyoka) AS kyu_hyoka, TRIM(k.kyakushitsu) AS kya,
         c.oi_index, c.shiage_index, TRIM(c.shiage_index_henka) AS shiage_henka, TRIM(c.chokyo_ryo_hyoka) AS ryo,
         TRIM(c.chokyo_type) AS ctype, TRIM(c.chokyo_course_type) AS ccourse, c.isshuumae_oi_index AS oi_1w,
         TRIM(c.course_saka) AS saka, TRIM(c.course_w) AS cw
  FROM T_KYI k LEFT JOIN T_CYB c ON c.course_code=k.course_code AND c.year_code=k.year_code AND c.kai=k.kai
       AND c.day_code=k.day_code AND c.race_num=k.race_num AND c.uma_num=k.uma_num
""", c)
c.close()
NUMS = ["idm", "joho_index", "kyusha_index", "chokyo_index", "kishu_index", "sogo_index", "gekiso_index",
        "j_win", "j_3in", "oi_index", "shiage_index", "oi_1w"]
for col in NUMS:
    kyi[col] = pd.to_numeric(kyi[col], errors="coerce")
kyi["heads"] = kyi.groupby("rid").uma.transform("size")
print("T_KYI", len(kyi))

prev = kyi.drop(columns=["prk"]).add_prefix("q_").rename(columns={"q_rid": "prk", "q_blood": "blood"})
cur = kyi.merge(prev, on=["prk", "blood"], how="left")
print("前走KYIが見つかった割合", cur.q_uma.notna().mean().round(3))

base = pd.read_pickle(os.path.join(ROOT, ".scratch", "prev_prepped.pkl"))
base = base.drop(columns=[x for x in ("idm",) if x in base.columns])
d = base.merge(cur, on=["rid", "uma"], how="inner")
print("結合後", len(d), "（prev_prepped", len(base), "）")
d.to_pickle(os.path.join(ROOT, ".scratch", "ippen_base.pkl"))
