-- ============================================================
-- T_COURSE_FACTOR_AGG 全量再投入（renso含む）
-- ============================================================
TRUNCATE TABLE T_COURSE_FACTOR_AGG;

-- 共通サブクエリ定義（fin）: f1=1着 f2=2着 f3=3着以内
-- ※ 各 INSERT で inline で使用

-- ── baseline ──────────────────────────────────────────────
INSERT INTO T_COURSE_FACTOR_AGG
  (course_code,tds_code,distance,factor_type,factor_value,
   total_count,win_count,renso_count,place_count,win_payout_sum,place_payout_sum,
   win_rate,renso_rate,place_rate,win_recovery,place_recovery)
SELECT b.course_code, b.tds_code, TRIM(b.distance), 'baseline', 'all',
  COUNT(*), SUM(fin.f1), SUM(fin.f1+fin.f2), SUM(fin.f3),
  COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1),
  ROUND(SUM(fin.f1+fin.f2)/COUNT(*)*100,1),
  ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1),
  ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=2 AS f2,
  CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt,
  CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1'
GROUP BY b.course_code, b.tds_code, TRIM(b.distance);

-- ── 脚質 ──────────────────────────────────────────────────
INSERT INTO T_COURSE_FACTOR_AGG
  (course_code,tds_code,distance,factor_type,factor_value,
   total_count,win_count,renso_count,place_count,win_payout_sum,place_payout_sum,
   win_rate,renso_rate,place_rate,win_recovery,place_recovery)
SELECT b.course_code, b.tds_code, TRIM(b.distance), 'kyaku', k.kyakushitsu,
  COUNT(*), SUM(fin.f1), SUM(fin.f1+fin.f2), SUM(fin.f3),
  COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f1+fin.f2)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1, CAST(TRIM(order_of_finish) AS UNSIGNED)=2 AS f2,
  CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1' AND k.kyakushitsu IN ('1','2','3','4')
GROUP BY b.course_code, b.tds_code, TRIM(b.distance), k.kyakushitsu;

-- ── テン指数順位帯 ────────────────────────────────────────
INSERT INTO T_COURSE_FACTOR_AGG
  (course_code,tds_code,distance,factor_type,factor_value,
   total_count,win_count,renso_count,place_count,win_payout_sum,place_payout_sum,
   win_rate,renso_rate,place_rate,win_recovery,place_recovery)
SELECT b.course_code, b.tds_code, TRIM(b.distance), 'ten_rank',
  CASE WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED)=1 THEN '1'
       WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
       WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
       ELSE '7~' END,
  COUNT(*), SUM(fin.f1), SUM(fin.f1+fin.f2), SUM(fin.f3),
  COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f1+fin.f2)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1, CAST(TRIM(order_of_finish) AS UNSIGNED)=2 AS f2,
  CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1' AND TRIM(k.ten_index_juni)<>'' AND CAST(TRIM(k.ten_index_juni) AS UNSIGNED)>0
GROUP BY b.course_code, b.tds_code, TRIM(b.distance),
  CASE WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED)=1 THEN '1' WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3' WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6' ELSE '7~' END;

-- ── 上がり指数順位帯 ──────────────────────────────────────
INSERT INTO T_COURSE_FACTOR_AGG
  (course_code,tds_code,distance,factor_type,factor_value,
   total_count,win_count,renso_count,place_count,win_payout_sum,place_payout_sum,
   win_rate,renso_rate,place_rate,win_recovery,place_recovery)
SELECT b.course_code, b.tds_code, TRIM(b.distance), 'agari_rank',
  CASE WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED)=1 THEN '1'
       WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
       WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
       ELSE '7~' END,
  COUNT(*), SUM(fin.f1), SUM(fin.f1+fin.f2), SUM(fin.f3),
  COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f1+fin.f2)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1, CAST(TRIM(order_of_finish) AS UNSIGNED)=2 AS f2,
  CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1' AND TRIM(k.agari_index_juni)<>'' AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED)>0
GROUP BY b.course_code, b.tds_code, TRIM(b.distance),
  CASE WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED)=1 THEN '1' WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3' WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6' ELSE '7~' END;

-- ── IDM印 ─────────────────────────────────────────────────
INSERT INTO T_COURSE_FACTOR_AGG
  (course_code,tds_code,distance,factor_type,factor_value,
   total_count,win_count,renso_count,place_count,win_payout_sum,place_payout_sum,
   win_rate,renso_rate,place_rate,win_recovery,place_recovery)
SELECT b.course_code, b.tds_code, TRIM(b.distance), 'idm_mark', TRIM(k.in_idm),
  COUNT(*), SUM(fin.f1), SUM(fin.f1+fin.f2), SUM(fin.f3),
  COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f1+fin.f2)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1, CAST(TRIM(order_of_finish) AS UNSIGNED)=2 AS f2,
  CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1' AND TRIM(k.in_idm) BETWEEN '1' AND '5'
GROUP BY b.course_code, b.tds_code, TRIM(b.distance), TRIM(k.in_idm);

-- ── 情報印 ────────────────────────────────────────────────
INSERT INTO T_COURSE_FACTOR_AGG
  (course_code,tds_code,distance,factor_type,factor_value,
   total_count,win_count,renso_count,place_count,win_payout_sum,place_payout_sum,
   win_rate,renso_rate,place_rate,win_recovery,place_recovery)
SELECT b.course_code, b.tds_code, TRIM(b.distance), 'joho_mark', TRIM(k.in_joho),
  COUNT(*), SUM(fin.f1), SUM(fin.f1+fin.f2), SUM(fin.f3),
  COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f1+fin.f2)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1, CAST(TRIM(order_of_finish) AS UNSIGNED)=2 AS f2,
  CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1' AND TRIM(k.in_joho) BETWEEN '1' AND '5'
GROUP BY b.course_code, b.tds_code, TRIM(b.distance), TRIM(k.in_joho);

-- ── 厩舎指数帯（5段階）────────────────────────────────────
INSERT INTO T_COURSE_FACTOR_AGG
  (course_code,tds_code,distance,factor_type,factor_value,
   total_count,win_count,renso_count,place_count,win_payout_sum,place_payout_sum,
   win_rate,renso_rate,place_rate,win_recovery,place_recovery)
SELECT b.course_code, b.tds_code, TRIM(b.distance), 'kyusha',
  CASE WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= 20 THEN '20+'
       WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= 10 THEN '10~20'
       WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >=  0 THEN '0~10'
       WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= -10 THEN '-10~0'
       ELSE '-10mi' END,
  COUNT(*), SUM(fin.f1), SUM(fin.f1+fin.f2), SUM(fin.f3),
  COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f1+fin.f2)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1, CAST(TRIM(order_of_finish) AS UNSIGNED)=2 AS f2,
  CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1' AND TRIM(k.kyusha_index)<>''
GROUP BY b.course_code, b.tds_code, TRIM(b.distance),
  CASE WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= 20 THEN '20+' WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= 10 THEN '10~20' WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >=  0 THEN '0~10' WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= -10 THEN '-10~0' ELSE '-10mi' END;

-- ── オッズ帯（6段階）────────────────────────────────────
INSERT INTO T_COURSE_FACTOR_AGG
  (course_code,tds_code,distance,factor_type,factor_value,
   total_count,win_count,renso_count,place_count,win_payout_sum,place_payout_sum,
   win_rate,renso_rate,place_rate,win_recovery,place_recovery)
SELECT b.course_code, b.tds_code, TRIM(b.distance), 'odds',
  CASE WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) <  2.0 THEN '~2.0'
       WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) <  4.0 THEN '2.0~4.0'
       WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) <  7.0 THEN '4.0~7.0'
       WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) < 15.0 THEN '7.0~15.0'
       WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) < 30.0 THEN '15.0~30.0'
       ELSE '30.0~' END,
  COUNT(*), SUM(fin.f1), SUM(fin.f1+fin.f2), SUM(fin.f3),
  COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f1+fin.f2)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1, CAST(TRIM(order_of_finish) AS UNSIGNED)=2 AS f2,
  CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1' AND TRIM(k.kijun_odds)<>'' AND CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1))>0
GROUP BY b.course_code, b.tds_code, TRIM(b.distance),
  CASE WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) < 2.0 THEN '~2.0' WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) < 4.0 THEN '2.0~4.0' WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) < 7.0 THEN '4.0~7.0' WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) < 15.0 THEN '7.0~15.0' WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) < 30.0 THEN '15.0~30.0' ELSE '30.0~' END;

SELECT factor_type, COUNT(*) AS cnt FROM T_COURSE_FACTOR_AGG GROUP BY factor_type ORDER BY factor_type;
