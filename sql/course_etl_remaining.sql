-- IDM印
INSERT INTO T_COURSE_FACTOR_AGG (course_code,tds_code,distance,factor_type,factor_value,total_count,win_count,place_count,win_payout_sum,place_payout_sum,win_rate,place_rate,win_recovery,place_recovery)
SELECT b.course_code, b.tds_code, TRIM(b.distance), 'idm_mark', TRIM(k.in_idm),
  COUNT(*), SUM(fin.f1), SUM(fin.f3), COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1, CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1' AND TRIM(k.in_idm) BETWEEN '1' AND '5'
GROUP BY b.course_code, b.tds_code, TRIM(b.distance), TRIM(k.in_idm)
ON DUPLICATE KEY UPDATE total_count=VALUES(total_count),win_count=VALUES(win_count),place_count=VALUES(place_count),win_payout_sum=VALUES(win_payout_sum),place_payout_sum=VALUES(place_payout_sum),win_rate=VALUES(win_rate),place_rate=VALUES(place_rate),win_recovery=VALUES(win_recovery),place_recovery=VALUES(place_recovery);

-- 情報印
INSERT INTO T_COURSE_FACTOR_AGG (course_code,tds_code,distance,factor_type,factor_value,total_count,win_count,place_count,win_payout_sum,place_payout_sum,win_rate,place_rate,win_recovery,place_recovery)
SELECT b.course_code, b.tds_code, TRIM(b.distance), 'joho_mark', TRIM(k.in_joho),
  COUNT(*), SUM(fin.f1), SUM(fin.f3), COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1, CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1' AND TRIM(k.in_joho) BETWEEN '1' AND '5'
GROUP BY b.course_code, b.tds_code, TRIM(b.distance), TRIM(k.in_joho)
ON DUPLICATE KEY UPDATE total_count=VALUES(total_count),win_count=VALUES(win_count),place_count=VALUES(place_count),win_payout_sum=VALUES(win_payout_sum),place_payout_sum=VALUES(place_payout_sum),win_rate=VALUES(win_rate),place_rate=VALUES(place_rate),win_recovery=VALUES(win_recovery),place_recovery=VALUES(place_recovery);

-- オッズ帯
INSERT INTO T_COURSE_FACTOR_AGG (course_code,tds_code,distance,factor_type,factor_value,total_count,win_count,place_count,win_payout_sum,place_payout_sum,win_rate,place_rate,win_recovery,place_recovery)
SELECT b.course_code, b.tds_code, TRIM(b.distance), 'odds',
  CASE WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1))<3.0 THEN '~3.0'
       WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1))<5.0 THEN '3.0~5.0'
       WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1))<10.0 THEN '5.0~10.0'
       WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1))<20.0 THEN '10.0~20.0'
       WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1))<50.0 THEN '20.0~50.0'
       ELSE '50.0~' END,
  COUNT(*), SUM(fin.f1), SUM(fin.f3), COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
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
  CASE WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1))<3.0 THEN '~3.0' WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1))<5.0 THEN '3.0~5.0' WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1))<10.0 THEN '5.0~10.0' WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1))<20.0 THEN '10.0~20.0' WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(7,1))<50.0 THEN '20.0~50.0' ELSE '50.0~' END
ON DUPLICATE KEY UPDATE total_count=VALUES(total_count),win_count=VALUES(win_count),place_count=VALUES(place_count),win_payout_sum=VALUES(win_payout_sum),place_payout_sum=VALUES(place_payout_sum),win_rate=VALUES(win_rate),place_rate=VALUES(place_rate),win_recovery=VALUES(win_recovery),place_recovery=VALUES(place_recovery);

-- 厩舎指数帯
INSERT INTO T_COURSE_FACTOR_AGG (course_code,tds_code,distance,factor_type,factor_value,total_count,win_count,place_count,win_payout_sum,place_payout_sum,win_rate,place_rate,win_recovery,place_recovery)
SELECT b.course_code, b.tds_code, TRIM(b.distance), 'kyusha',
  CASE WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1))>=10 THEN 'hi'
       WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1))>=0 THEN 'mid'
       ELSE 'lo' END,
  COUNT(*), SUM(fin.f1), SUM(fin.f3), COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
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
  CASE WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1))>=10 THEN 'hi' WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1))>=0 THEN 'mid' ELSE 'lo' END
ON DUPLICATE KEY UPDATE total_count=VALUES(total_count),win_count=VALUES(win_count),place_count=VALUES(place_count),win_payout_sum=VALUES(win_payout_sum),place_payout_sum=VALUES(place_payout_sum),win_rate=VALUES(win_rate),place_rate=VALUES(place_rate),win_recovery=VALUES(win_recovery),place_recovery=VALUES(place_recovery);

SELECT factor_type, COUNT(*) AS cnt, SUM(total_count) AS rides FROM T_COURSE_FACTOR_AGG GROUP BY factor_type ORDER BY factor_type;
