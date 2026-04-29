-- 旧バケットを削除して再集計
DELETE FROM T_COURSE_FACTOR_AGG WHERE factor_type IN ('kyusha','odds');

-- 厩舎指数帯（5段階）
INSERT INTO T_COURSE_FACTOR_AGG
  (course_code,tds_code,distance,factor_type,factor_value,total_count,win_count,place_count,win_payout_sum,place_payout_sum,win_rate,place_rate,win_recovery,place_recovery)
SELECT b.course_code, b.tds_code, TRIM(b.distance), 'kyusha',
  CASE WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= 20 THEN '20+'
       WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= 10 THEN '10~20'
       WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >=  0 THEN '0~10'
       WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= -10 THEN '-10~0'
       ELSE '-10mi' END,
  COUNT(*), SUM(fin.f1), SUM(fin.f3),
  COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1, CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1' AND TRIM(k.kyusha_index)<>''
GROUP BY b.course_code, b.tds_code, TRIM(b.distance),
  CASE WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= 20 THEN '20+'
       WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= 10 THEN '10~20'
       WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >=  0 THEN '0~10'
       WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= -10 THEN '-10~0'
       ELSE '-10mi' END
ON DUPLICATE KEY UPDATE total_count=VALUES(total_count),win_count=VALUES(win_count),place_count=VALUES(place_count),win_payout_sum=VALUES(win_payout_sum),place_payout_sum=VALUES(place_payout_sum),win_rate=VALUES(win_rate),place_rate=VALUES(place_rate),win_recovery=VALUES(win_recovery),place_recovery=VALUES(place_recovery);

-- オッズ帯（6段階）
INSERT INTO T_COURSE_FACTOR_AGG
  (course_code,tds_code,distance,factor_type,factor_value,total_count,win_count,place_count,win_payout_sum,place_payout_sum,win_rate,place_rate,win_recovery,place_recovery)
SELECT b.course_code, b.tds_code, TRIM(b.distance), 'odds',
  CASE WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) <  2.0 THEN '~2.0'
       WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) <  4.0 THEN '2.0~4.0'
       WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) <  7.0 THEN '4.0~7.0'
       WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) < 15.0 THEN '7.0~15.0'
       WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) < 30.0 THEN '15.0~30.0'
       ELSE '30.0~' END,
  COUNT(*), SUM(fin.f1), SUM(fin.f3),
  COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1, CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1' AND TRIM(k.kijun_odds)<>'' AND CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1))>0
GROUP BY b.course_code, b.tds_code, TRIM(b.distance),
  CASE WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) <  2.0 THEN '~2.0'
       WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) <  4.0 THEN '2.0~4.0'
       WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) <  7.0 THEN '4.0~7.0'
       WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) < 15.0 THEN '7.0~15.0'
       WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1)) < 30.0 THEN '15.0~30.0'
       ELSE '30.0~' END
ON DUPLICATE KEY UPDATE total_count=VALUES(total_count),win_count=VALUES(win_count),place_count=VALUES(place_count),win_payout_sum=VALUES(win_payout_sum),place_payout_sum=VALUES(place_payout_sum),win_rate=VALUES(win_rate),place_rate=VALUES(place_rate),win_recovery=VALUES(win_recovery),place_recovery=VALUES(place_recovery);

SELECT factor_type, COUNT(*) AS cnt, SUM(total_count) AS rides
FROM T_COURSE_FACTOR_AGG WHERE factor_type IN ('kyusha','odds') GROUP BY factor_type;
