-- ============================================================
-- 展開適合指数（Pace Fit Index）ETL
-- ペース予想(pace_yoso) × テン指数順位 × 上がり指数順位 + コース補正
-- 実行順: Part1 → Part2 → Part3 → Part4
-- Part2〜4 は ON DUPLICATE KEY UPDATE で冪等
-- ============================================================


-- ============================================================
-- Part 1: テーブル定義
-- ============================================================

CREATE TABLE IF NOT EXISTS T_PACEFIT_FACTOR_AGG (
  factor_type       VARCHAR(30)  NOT NULL COMMENT 'ファクター種別',
  factor_value      VARCHAR(40)  NOT NULL COMMENT 'ファクター値',
  course_code       CHAR(2)      NOT NULL DEFAULT '' COMMENT '場コード（空=全体）',
  tds_code          CHAR(1)      NOT NULL DEFAULT '' COMMENT '芝ダ（空=全体）',
  dist_band         VARCHAR(12)  NOT NULL DEFAULT '' COMMENT '距離帯（空=全体）',

  total_count       INT          NOT NULL DEFAULT 0,
  win_payout_sum    BIGINT       NOT NULL DEFAULT 0,
  place_payout_sum  BIGINT       NOT NULL DEFAULT 0,
  win_recovery      DECIMAL(7,1)          COMMENT '単勝回収率（100円あたり）',
  place_recovery    DECIMAL(7,1)          COMMENT '複勝回収率（100円あたり）',

  updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                          ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (factor_type, factor_value, course_code, tds_code, dist_band),
  INDEX idx_pacefit_agg_type (factor_type, course_code, tds_code, dist_band)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='展開適合指数 ファクター別集計（EAV形式）';


CREATE TABLE IF NOT EXISTS T_PACEFIT_SCORE (
  course_code    CHAR(2)       NOT NULL,
  year_code      CHAR(2)       NOT NULL,
  kai            CHAR(1)       NOT NULL,
  day_code       CHAR(1)       NOT NULL,
  race_num       CHAR(2)       NOT NULL,
  uma_num        CHAR(2)       NOT NULL,

  pace_yoso      CHAR(1)                COMMENT 'ペース予想 H/M/S',
  ten_juni       TINYINT UNSIGNED       COMMENT 'テン指数順位',
  agari_juni     TINYINT UNSIGNED       COMMENT '上がり指数順位',
  has_ten_gap    TINYINT(1)   DEFAULT 0 COMMENT 'テン指数ギャップ大フラグ',
  has_agari_gap  TINYINT(1)   DEFAULT 0 COMMENT '上がり指数ギャップ大フラグ',

  overall_score  DECIMAL(7,1)           COMMENT '全体展開適合指数',
  course_score   DECIMAL(7,1)           COMMENT 'コース別展開適合指数',

  score_ten_o    DECIMAL(7,1)           COMMENT 'テン全体スコア',
  score_agari_o  DECIMAL(7,1)           COMMENT '上がり全体スコア',
  score_gap      DECIMAL(7,1)           COMMENT 'ギャップボーナス',
  score_ten_c    DECIMAL(7,1)           COMMENT 'テンコース補正スコア',
  score_agari_c  DECIMAL(7,1)           COMMENT '上がりコース補正スコア',

  updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                       ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (course_code, year_code, kai, day_code, race_num, uma_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='展開適合指数（出馬表表示用）';


-- ============================================================
-- Part 2: 全体ファクター集計
-- ============================================================

-- 2-1. 全体ベースライン
INSERT INTO T_PACEFIT_FACTOR_AGG
  (factor_type, factor_value, total_count, win_payout_sum, place_payout_sum, win_recovery, place_recovery)
SELECT
  'baseline', '',
  COUNT(*),
  SUM(COALESCE(s.win,   0)),
  SUM(COALESCE(s.place, 0)),
  ROUND(SUM(COALESCE(s.win,   0)) / COUNT(*), 1),
  ROUND(SUM(COALESCE(s.place, 0)) / COUNT(*), 1)
FROM T_KYI k
JOIN T_SED s
  ON  s.course_code=k.course_code AND s.year_code=k.year_code
  AND s.kai=k.kai AND s.day_code=k.day_code
  AND s.race_num=k.race_num AND s.umaban=k.uma_num
JOIN T_BAC b
  ON  b.course_code=k.course_code AND b.year_code=k.year_code
  AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
WHERE s.ijou_kubun='0'
  AND s.order_of_finish REGEXP '^[0-9]+$'
  AND CAST(s.order_of_finish AS UNSIGNED) BETWEEN 1 AND 18
  AND k.pace_yoso IN ('H','M','S')
  AND k.ten_index_juni  IS NOT NULL AND TRIM(k.ten_index_juni)  <> ''
  AND k.agari_index_juni IS NOT NULL AND TRIM(k.agari_index_juni) <> ''
  AND b.tds_code IN ('1','2')
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count),
  win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum),
  win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);

-- 2-2. ペース × テン順位帯（全体）
INSERT INTO T_PACEFIT_FACTOR_AGG
  (factor_type, factor_value, total_count, win_payout_sum, place_payout_sum, win_recovery, place_recovery)
SELECT
  'pace_ten',
  CONCAT(k.pace_yoso, '|',
    CASE
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) = 1  THEN '1'
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) = 2  THEN '2'
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) <= 4 THEN '3-4'
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) <= 8 THEN '5-8'
      ELSE '9+'
    END),
  COUNT(*),
  SUM(COALESCE(s.win,   0)),
  SUM(COALESCE(s.place, 0)),
  ROUND(SUM(COALESCE(s.win,   0)) / COUNT(*), 1),
  ROUND(SUM(COALESCE(s.place, 0)) / COUNT(*), 1)
FROM T_KYI k
JOIN T_SED s
  ON  s.course_code=k.course_code AND s.year_code=k.year_code
  AND s.kai=k.kai AND s.day_code=k.day_code
  AND s.race_num=k.race_num AND s.umaban=k.uma_num
JOIN T_BAC b
  ON  b.course_code=k.course_code AND b.year_code=k.year_code
  AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
WHERE s.ijou_kubun='0'
  AND s.order_of_finish REGEXP '^[0-9]+$'
  AND CAST(s.order_of_finish AS UNSIGNED) BETWEEN 1 AND 18
  AND k.pace_yoso IN ('H','M','S')
  AND k.ten_index_juni  IS NOT NULL AND TRIM(k.ten_index_juni)  <> ''
  AND k.agari_index_juni IS NOT NULL AND TRIM(k.agari_index_juni) <> ''
  AND b.tds_code IN ('1','2')
GROUP BY CONCAT(k.pace_yoso, '|',
    CASE
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) = 1  THEN '1'
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) = 2  THEN '2'
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) <= 4 THEN '3-4'
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) <= 8 THEN '5-8'
      ELSE '9+'
    END)
HAVING COUNT(*) >= 30
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count),
  win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum),
  win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);

-- 2-3. ペース × 上がり順位帯（全体）
INSERT INTO T_PACEFIT_FACTOR_AGG
  (factor_type, factor_value, total_count, win_payout_sum, place_payout_sum, win_recovery, place_recovery)
SELECT
  'pace_agari',
  CONCAT(k.pace_yoso, '|',
    CASE
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) = 1  THEN '1'
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) = 2  THEN '2'
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 4 THEN '3-4'
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 8 THEN '5-8'
      ELSE '9+'
    END),
  COUNT(*),
  SUM(COALESCE(s.win,   0)),
  SUM(COALESCE(s.place, 0)),
  ROUND(SUM(COALESCE(s.win,   0)) / COUNT(*), 1),
  ROUND(SUM(COALESCE(s.place, 0)) / COUNT(*), 1)
FROM T_KYI k
JOIN T_SED s
  ON  s.course_code=k.course_code AND s.year_code=k.year_code
  AND s.kai=k.kai AND s.day_code=k.day_code
  AND s.race_num=k.race_num AND s.umaban=k.uma_num
JOIN T_BAC b
  ON  b.course_code=k.course_code AND b.year_code=k.year_code
  AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
WHERE s.ijou_kubun='0'
  AND s.order_of_finish REGEXP '^[0-9]+$'
  AND CAST(s.order_of_finish AS UNSIGNED) BETWEEN 1 AND 18
  AND k.pace_yoso IN ('H','M','S')
  AND k.ten_index_juni  IS NOT NULL AND TRIM(k.ten_index_juni)  <> ''
  AND k.agari_index_juni IS NOT NULL AND TRIM(k.agari_index_juni) <> ''
  AND b.tds_code IN ('1','2')
GROUP BY CONCAT(k.pace_yoso, '|',
    CASE
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) = 1  THEN '1'
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) = 2  THEN '2'
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 4 THEN '3-4'
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 8 THEN '5-8'
      ELSE '9+'
    END)
HAVING COUNT(*) >= 30
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count),
  win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum),
  win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);

-- 2-4. ギャップボーナス: H pace × テン1位 × テンギャップ≥2.0（全体）
INSERT INTO T_PACEFIT_FACTOR_AGG
  (factor_type, factor_value, total_count, win_payout_sum, place_payout_sum, win_recovery, place_recovery)
SELECT
  'gap_ten_h', 'H',
  COUNT(*),
  SUM(COALESCE(s.win,   0)),
  SUM(COALESCE(s.place, 0)),
  ROUND(SUM(COALESCE(s.win,   0)) / COUNT(*), 1),
  ROUND(SUM(COALESCE(s.place, 0)) / COUNT(*), 1)
FROM T_KYI k
JOIN (
  SELECT k2.course_code, k2.year_code, k2.kai, k2.day_code, k2.race_num,
    MAX(CASE WHEN CAST(TRIM(k2.ten_index_juni) AS UNSIGNED) = 1 THEN k2.ten_index END) AS ten1,
    MAX(CASE WHEN CAST(TRIM(k2.ten_index_juni) AS UNSIGNED) = 2 THEN k2.ten_index END) AS ten2
  FROM T_KYI k2
  WHERE k2.ten_index > 0
    AND k2.ten_index_juni IS NOT NULL AND TRIM(k2.ten_index_juni) <> ''
  GROUP BY k2.course_code, k2.year_code, k2.kai, k2.day_code, k2.race_num
) rg ON  rg.course_code=k.course_code AND rg.year_code=k.year_code
     AND rg.kai=k.kai AND rg.day_code=k.day_code AND rg.race_num=k.race_num
JOIN T_SED s
  ON  s.course_code=k.course_code AND s.year_code=k.year_code
  AND s.kai=k.kai AND s.day_code=k.day_code
  AND s.race_num=k.race_num AND s.umaban=k.uma_num
JOIN T_BAC b
  ON  b.course_code=k.course_code AND b.year_code=k.year_code
  AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
WHERE s.ijou_kubun='0'
  AND s.order_of_finish REGEXP '^[0-9]+$'
  AND CAST(s.order_of_finish AS UNSIGNED) BETWEEN 1 AND 18
  AND k.pace_yoso = 'H'
  AND CAST(TRIM(k.ten_index_juni) AS UNSIGNED) = 1
  AND k.ten_index > 0
  AND (rg.ten1 - rg.ten2) >= 2.0
  AND b.tds_code IN ('1','2')
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count),
  win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum),
  win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);

-- 2-5. ギャップボーナス: M pace × 上がり1位 × 上がりギャップ≥2.0（全体）
INSERT INTO T_PACEFIT_FACTOR_AGG
  (factor_type, factor_value, total_count, win_payout_sum, place_payout_sum, win_recovery, place_recovery)
SELECT
  'gap_agari_m', 'M',
  COUNT(*),
  SUM(COALESCE(s.win,   0)),
  SUM(COALESCE(s.place, 0)),
  ROUND(SUM(COALESCE(s.win,   0)) / COUNT(*), 1),
  ROUND(SUM(COALESCE(s.place, 0)) / COUNT(*), 1)
FROM T_KYI k
JOIN (
  SELECT k2.course_code, k2.year_code, k2.kai, k2.day_code, k2.race_num,
    MAX(CASE WHEN CAST(TRIM(k2.agari_index_juni) AS UNSIGNED) = 1 THEN k2.agari_index END) AS agari1,
    MAX(CASE WHEN CAST(TRIM(k2.agari_index_juni) AS UNSIGNED) = 2 THEN k2.agari_index END) AS agari2
  FROM T_KYI k2
  WHERE k2.agari_index > 0
    AND k2.agari_index_juni IS NOT NULL AND TRIM(k2.agari_index_juni) <> ''
  GROUP BY k2.course_code, k2.year_code, k2.kai, k2.day_code, k2.race_num
) rg ON  rg.course_code=k.course_code AND rg.year_code=k.year_code
     AND rg.kai=k.kai AND rg.day_code=k.day_code AND rg.race_num=k.race_num
JOIN T_SED s
  ON  s.course_code=k.course_code AND s.year_code=k.year_code
  AND s.kai=k.kai AND s.day_code=k.day_code
  AND s.race_num=k.race_num AND s.umaban=k.uma_num
JOIN T_BAC b
  ON  b.course_code=k.course_code AND b.year_code=k.year_code
  AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
WHERE s.ijou_kubun='0'
  AND s.order_of_finish REGEXP '^[0-9]+$'
  AND CAST(s.order_of_finish AS UNSIGNED) BETWEEN 1 AND 18
  AND k.pace_yoso = 'M'
  AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) = 1
  AND k.agari_index > 0
  AND (rg.agari1 - rg.agari2) >= 2.0
  AND b.tds_code IN ('1','2')
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count),
  win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum),
  win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ============================================================
-- Part 3: コース別ファクター集計
-- ============================================================

-- 3-1. コース別ベースライン（場×芝ダ×距離帯）
INSERT INTO T_PACEFIT_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_payout_sum, place_payout_sum, win_recovery, place_recovery)
SELECT
  'baseline', '',
  b.course_code, b.tds_code,
  CASE
    WHEN CAST(b.distance AS UNSIGNED) <= 1400 THEN '短~1400'
    WHEN CAST(b.distance AS UNSIGNED) <= 1800 THEN 'マイル'
    WHEN CAST(b.distance AS UNSIGNED) <= 2200 THEN '中距離'
    ELSE '長距離'
  END,
  COUNT(*),
  SUM(COALESCE(s.win,   0)),
  SUM(COALESCE(s.place, 0)),
  ROUND(SUM(COALESCE(s.win,   0)) / COUNT(*), 1),
  ROUND(SUM(COALESCE(s.place, 0)) / COUNT(*), 1)
FROM T_KYI k
JOIN T_SED s
  ON  s.course_code=k.course_code AND s.year_code=k.year_code
  AND s.kai=k.kai AND s.day_code=k.day_code
  AND s.race_num=k.race_num AND s.umaban=k.uma_num
JOIN T_BAC b
  ON  b.course_code=k.course_code AND b.year_code=k.year_code
  AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
WHERE s.ijou_kubun='0'
  AND s.order_of_finish REGEXP '^[0-9]+$'
  AND CAST(s.order_of_finish AS UNSIGNED) BETWEEN 1 AND 18
  AND k.pace_yoso IN ('H','M','S')
  AND k.ten_index_juni  IS NOT NULL AND TRIM(k.ten_index_juni)  <> ''
  AND k.agari_index_juni IS NOT NULL AND TRIM(k.agari_index_juni) <> ''
  AND b.tds_code IN ('1','2')
GROUP BY b.course_code, b.tds_code,
  CASE
    WHEN CAST(b.distance AS UNSIGNED) <= 1400 THEN '短~1400'
    WHEN CAST(b.distance AS UNSIGNED) <= 1800 THEN 'マイル'
    WHEN CAST(b.distance AS UNSIGNED) <= 2200 THEN '中距離'
    ELSE '長距離'
  END
HAVING COUNT(*) >= 50
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count),
  win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum),
  win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);

-- 3-2. コース別 × ペース × テン順位帯
INSERT INTO T_PACEFIT_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_payout_sum, place_payout_sum, win_recovery, place_recovery)
SELECT
  'pace_ten',
  CONCAT(k.pace_yoso, '|',
    CASE
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) = 1  THEN '1'
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) = 2  THEN '2'
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) <= 4 THEN '3-4'
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) <= 8 THEN '5-8'
      ELSE '9+'
    END),
  b.course_code, b.tds_code,
  CASE
    WHEN CAST(b.distance AS UNSIGNED) <= 1400 THEN '短~1400'
    WHEN CAST(b.distance AS UNSIGNED) <= 1800 THEN 'マイル'
    WHEN CAST(b.distance AS UNSIGNED) <= 2200 THEN '中距離'
    ELSE '長距離'
  END,
  COUNT(*),
  SUM(COALESCE(s.win,   0)),
  SUM(COALESCE(s.place, 0)),
  ROUND(SUM(COALESCE(s.win,   0)) / COUNT(*), 1),
  ROUND(SUM(COALESCE(s.place, 0)) / COUNT(*), 1)
FROM T_KYI k
JOIN T_SED s
  ON  s.course_code=k.course_code AND s.year_code=k.year_code
  AND s.kai=k.kai AND s.day_code=k.day_code
  AND s.race_num=k.race_num AND s.umaban=k.uma_num
JOIN T_BAC b
  ON  b.course_code=k.course_code AND b.year_code=k.year_code
  AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
WHERE s.ijou_kubun='0'
  AND s.order_of_finish REGEXP '^[0-9]+$'
  AND CAST(s.order_of_finish AS UNSIGNED) BETWEEN 1 AND 18
  AND k.pace_yoso IN ('H','M','S')
  AND k.ten_index_juni  IS NOT NULL AND TRIM(k.ten_index_juni)  <> ''
  AND k.agari_index_juni IS NOT NULL AND TRIM(k.agari_index_juni) <> ''
  AND b.tds_code IN ('1','2')
GROUP BY CONCAT(k.pace_yoso, '|',
    CASE
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) = 1  THEN '1'
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) = 2  THEN '2'
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) <= 4 THEN '3-4'
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) <= 8 THEN '5-8'
      ELSE '9+'
    END),
  b.course_code, b.tds_code,
  CASE
    WHEN CAST(b.distance AS UNSIGNED) <= 1400 THEN '短~1400'
    WHEN CAST(b.distance AS UNSIGNED) <= 1800 THEN 'マイル'
    WHEN CAST(b.distance AS UNSIGNED) <= 2200 THEN '中距離'
    ELSE '長距離'
  END
HAVING COUNT(*) >= 50
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count),
  win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum),
  win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);

-- 3-3. コース別 × ペース × 上がり順位帯
INSERT INTO T_PACEFIT_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_payout_sum, place_payout_sum, win_recovery, place_recovery)
SELECT
  'pace_agari',
  CONCAT(k.pace_yoso, '|',
    CASE
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) = 1  THEN '1'
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) = 2  THEN '2'
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 4 THEN '3-4'
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 8 THEN '5-8'
      ELSE '9+'
    END),
  b.course_code, b.tds_code,
  CASE
    WHEN CAST(b.distance AS UNSIGNED) <= 1400 THEN '短~1400'
    WHEN CAST(b.distance AS UNSIGNED) <= 1800 THEN 'マイル'
    WHEN CAST(b.distance AS UNSIGNED) <= 2200 THEN '中距離'
    ELSE '長距離'
  END,
  COUNT(*),
  SUM(COALESCE(s.win,   0)),
  SUM(COALESCE(s.place, 0)),
  ROUND(SUM(COALESCE(s.win,   0)) / COUNT(*), 1),
  ROUND(SUM(COALESCE(s.place, 0)) / COUNT(*), 1)
FROM T_KYI k
JOIN T_SED s
  ON  s.course_code=k.course_code AND s.year_code=k.year_code
  AND s.kai=k.kai AND s.day_code=k.day_code
  AND s.race_num=k.race_num AND s.umaban=k.uma_num
JOIN T_BAC b
  ON  b.course_code=k.course_code AND b.year_code=k.year_code
  AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
WHERE s.ijou_kubun='0'
  AND s.order_of_finish REGEXP '^[0-9]+$'
  AND CAST(s.order_of_finish AS UNSIGNED) BETWEEN 1 AND 18
  AND k.pace_yoso IN ('H','M','S')
  AND k.ten_index_juni  IS NOT NULL AND TRIM(k.ten_index_juni)  <> ''
  AND k.agari_index_juni IS NOT NULL AND TRIM(k.agari_index_juni) <> ''
  AND b.tds_code IN ('1','2')
GROUP BY CONCAT(k.pace_yoso, '|',
    CASE
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) = 1  THEN '1'
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) = 2  THEN '2'
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 4 THEN '3-4'
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 8 THEN '5-8'
      ELSE '9+'
    END),
  b.course_code, b.tds_code,
  CASE
    WHEN CAST(b.distance AS UNSIGNED) <= 1400 THEN '短~1400'
    WHEN CAST(b.distance AS UNSIGNED) <= 1800 THEN 'マイル'
    WHEN CAST(b.distance AS UNSIGNED) <= 2200 THEN '中距離'
    ELSE '長距離'
  END
HAVING COUNT(*) >= 50
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count),
  win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum),
  win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ============================================================
-- Part 4: スコア計算（T_PACEFIT_SCORE 投入）
-- ============================================================

INSERT INTO T_PACEFIT_SCORE (
  course_code, year_code, kai, day_code, race_num, uma_num,
  pace_yoso, ten_juni, agari_juni,
  has_ten_gap, has_agari_gap,
  overall_score, course_score,
  score_ten_o, score_agari_o, score_gap,
  score_ten_c, score_agari_c
)
SELECT
  k.course_code, k.year_code, k.kai, k.day_code, k.race_num, k.uma_num,
  k.pace_yoso,
  CAST(TRIM(k.ten_index_juni)   AS UNSIGNED),
  CAST(TRIM(k.agari_index_juni) AS UNSIGNED),

  -- ギャップフラグ
  CASE WHEN k.pace_yoso='H'
            AND CAST(TRIM(k.ten_index_juni) AS UNSIGNED) = 1
            AND k.ten_index > 0
            AND rg.ten2 > 0
            AND (k.ten_index - rg.ten2) >= 2.0
       THEN 1 ELSE 0 END,
  CASE WHEN k.pace_yoso='M'
            AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) = 1
            AND k.agari_index > 0
            AND rg.agari2 > 0
            AND (k.agari_index - rg.agari2) >= 2.0
       THEN 1 ELSE 0 END,

  -- overall_score = テン全体 + 上がり全体 + ギャップボーナス
  ROUND(
    -- テン全体
    COALESCE(f_ten_o.win_recovery, bl_o.win_recovery) - bl_o.win_recovery
    -- 上がり全体
    + COALESCE(f_agari_o.win_recovery, bl_o.win_recovery) - bl_o.win_recovery
    -- ギャップボーナス（H×テン1×gap→ギャップ分の追加回収率 - テン1位の回収率）
    + CASE WHEN k.pace_yoso='H'
                AND CAST(TRIM(k.ten_index_juni) AS UNSIGNED)=1
                AND k.ten_index > 0 AND rg.ten2 > 0
                AND (k.ten_index - rg.ten2) >= 2.0
           THEN COALESCE(f_gap_ten.win_recovery, bl_o.win_recovery)
                - COALESCE(f_ten_o.win_recovery, bl_o.win_recovery)
           ELSE 0 END
    -- ギャップボーナス（M×上がり1×gap）
    + CASE WHEN k.pace_yoso='M'
                AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED)=1
                AND k.agari_index > 0 AND rg.agari2 > 0
                AND (k.agari_index - rg.agari2) >= 2.0
           THEN COALESCE(f_gap_agari.win_recovery, bl_o.win_recovery)
                - COALESCE(f_agari_o.win_recovery, bl_o.win_recovery)
           ELSE 0 END
  , 1),

  -- course_score: コース別があれば使用、なければ全体値で計算
  ROUND(
    -- テンコース補正（コース値ある場合は コース値-コースBL、ない場合は 全体値-全体BL）
    COALESCE(
      f_ten_c.win_recovery - COALESCE(bl_c.win_recovery, bl_o.win_recovery),
      COALESCE(f_ten_o.win_recovery, bl_o.win_recovery) - bl_o.win_recovery
    )
    -- 上がりコース補正
    + COALESCE(
      f_agari_c.win_recovery - COALESCE(bl_c.win_recovery, bl_o.win_recovery),
      COALESCE(f_agari_o.win_recovery, bl_o.win_recovery) - bl_o.win_recovery
    )
    -- ギャップボーナス（course_scoreでも全体値を使用）
    + CASE WHEN k.pace_yoso='H'
                AND CAST(TRIM(k.ten_index_juni) AS UNSIGNED)=1
                AND k.ten_index > 0 AND rg.ten2 > 0
                AND (k.ten_index - rg.ten2) >= 2.0
           THEN COALESCE(f_gap_ten.win_recovery, bl_o.win_recovery)
                - COALESCE(f_ten_o.win_recovery, bl_o.win_recovery)
           ELSE 0 END
    + CASE WHEN k.pace_yoso='M'
                AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED)=1
                AND k.agari_index > 0 AND rg.agari2 > 0
                AND (k.agari_index - rg.agari2) >= 2.0
           THEN COALESCE(f_gap_agari.win_recovery, bl_o.win_recovery)
                - COALESCE(f_agari_o.win_recovery, bl_o.win_recovery)
           ELSE 0 END
  , 1),

  -- 内訳
  ROUND(COALESCE(f_ten_o.win_recovery,   bl_o.win_recovery) - bl_o.win_recovery, 1),
  ROUND(COALESCE(f_agari_o.win_recovery, bl_o.win_recovery) - bl_o.win_recovery, 1),
  ROUND(
    CASE WHEN k.pace_yoso='H' AND CAST(TRIM(k.ten_index_juni) AS UNSIGNED)=1
              AND k.ten_index > 0 AND rg.ten2 > 0 AND (k.ten_index-rg.ten2)>=2.0
         THEN COALESCE(f_gap_ten.win_recovery,   bl_o.win_recovery) - COALESCE(f_ten_o.win_recovery,   bl_o.win_recovery)
         ELSE 0 END
    + CASE WHEN k.pace_yoso='M' AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED)=1
                AND k.agari_index > 0 AND rg.agari2 > 0 AND (k.agari_index-rg.agari2)>=2.0
           THEN COALESCE(f_gap_agari.win_recovery, bl_o.win_recovery) - COALESCE(f_agari_o.win_recovery, bl_o.win_recovery)
           ELSE 0 END
  , 1),
  ROUND(COALESCE(
    f_ten_c.win_recovery - COALESCE(bl_c.win_recovery, bl_o.win_recovery),
    COALESCE(f_ten_o.win_recovery, bl_o.win_recovery) - bl_o.win_recovery
  ), 1),
  ROUND(COALESCE(
    f_agari_c.win_recovery - COALESCE(bl_c.win_recovery, bl_o.win_recovery),
    COALESCE(f_agari_o.win_recovery, bl_o.win_recovery) - bl_o.win_recovery
  ), 1)

FROM T_KYI k
JOIN T_BAC b
  ON  b.course_code=k.course_code AND b.year_code=k.year_code
  AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num

-- レース別ギャップ（テン・上がり指数の1位と2位の差）
LEFT JOIN (
  SELECT k2.course_code, k2.year_code, k2.kai, k2.day_code, k2.race_num,
    MAX(CASE WHEN CAST(TRIM(k2.ten_index_juni)   AS UNSIGNED)=2 THEN k2.ten_index   END) AS ten2,
    MAX(CASE WHEN CAST(TRIM(k2.agari_index_juni) AS UNSIGNED)=2 THEN k2.agari_index END) AS agari2
  FROM T_KYI k2
  WHERE (k2.ten_index > 0 OR k2.agari_index > 0)
    AND k2.ten_index_juni   IS NOT NULL AND TRIM(k2.ten_index_juni)   <> ''
    AND k2.agari_index_juni IS NOT NULL AND TRIM(k2.agari_index_juni) <> ''
  GROUP BY k2.course_code, k2.year_code, k2.kai, k2.day_code, k2.race_num
) rg ON  rg.course_code=k.course_code AND rg.year_code=k.year_code
     AND rg.kai=k.kai AND rg.day_code=k.day_code AND rg.race_num=k.race_num

-- 全体ベースライン
JOIN T_PACEFIT_FACTOR_AGG bl_o
  ON  bl_o.factor_type='baseline' AND bl_o.factor_value=''
  AND bl_o.course_code='' AND bl_o.tds_code='' AND bl_o.dist_band=''

-- コース別ベースライン（なければNULL）
LEFT JOIN T_PACEFIT_FACTOR_AGG bl_c
  ON  bl_c.factor_type='baseline' AND bl_c.factor_value=''
  AND bl_c.course_code=b.course_code AND bl_c.tds_code=b.tds_code
  AND bl_c.dist_band=CASE
    WHEN CAST(b.distance AS UNSIGNED) <= 1400 THEN '短~1400'
    WHEN CAST(b.distance AS UNSIGNED) <= 1800 THEN 'マイル'
    WHEN CAST(b.distance AS UNSIGNED) <= 2200 THEN '中距離'
    ELSE '長距離'
  END

-- テン全体ファクター
LEFT JOIN T_PACEFIT_FACTOR_AGG f_ten_o
  ON  f_ten_o.factor_type='pace_ten'
  AND f_ten_o.factor_value=CONCAT(k.pace_yoso,'|',
    CASE
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED)=1  THEN '1'
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED)=2  THEN '2'
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED)<=4 THEN '3-4'
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED)<=8 THEN '5-8'
      ELSE '9+'
    END)
  AND f_ten_o.course_code='' AND f_ten_o.tds_code='' AND f_ten_o.dist_band=''

-- 上がり全体ファクター
LEFT JOIN T_PACEFIT_FACTOR_AGG f_agari_o
  ON  f_agari_o.factor_type='pace_agari'
  AND f_agari_o.factor_value=CONCAT(k.pace_yoso,'|',
    CASE
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED)=1  THEN '1'
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED)=2  THEN '2'
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED)<=4 THEN '3-4'
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED)<=8 THEN '5-8'
      ELSE '9+'
    END)
  AND f_agari_o.course_code='' AND f_agari_o.tds_code='' AND f_agari_o.dist_band=''

-- テンコース別ファクター（なければNULL→全体値にフォールバック）
LEFT JOIN T_PACEFIT_FACTOR_AGG f_ten_c
  ON  f_ten_c.factor_type='pace_ten'
  AND f_ten_c.factor_value=CONCAT(k.pace_yoso,'|',
    CASE
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED)=1  THEN '1'
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED)=2  THEN '2'
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED)<=4 THEN '3-4'
      WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED)<=8 THEN '5-8'
      ELSE '9+'
    END)
  AND f_ten_c.course_code=b.course_code AND f_ten_c.tds_code=b.tds_code
  AND f_ten_c.dist_band=CASE
    WHEN CAST(b.distance AS UNSIGNED) <= 1400 THEN '短~1400'
    WHEN CAST(b.distance AS UNSIGNED) <= 1800 THEN 'マイル'
    WHEN CAST(b.distance AS UNSIGNED) <= 2200 THEN '中距離'
    ELSE '長距離'
  END

-- 上がりコース別ファクター
LEFT JOIN T_PACEFIT_FACTOR_AGG f_agari_c
  ON  f_agari_c.factor_type='pace_agari'
  AND f_agari_c.factor_value=CONCAT(k.pace_yoso,'|',
    CASE
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED)=1  THEN '1'
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED)=2  THEN '2'
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED)<=4 THEN '3-4'
      WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED)<=8 THEN '5-8'
      ELSE '9+'
    END)
  AND f_agari_c.course_code=b.course_code AND f_agari_c.tds_code=b.tds_code
  AND f_agari_c.dist_band=CASE
    WHEN CAST(b.distance AS UNSIGNED) <= 1400 THEN '短~1400'
    WHEN CAST(b.distance AS UNSIGNED) <= 1800 THEN 'マイル'
    WHEN CAST(b.distance AS UNSIGNED) <= 2200 THEN '中距離'
    ELSE '長距離'
  END

-- ギャップボーナス（H×テン）
LEFT JOIN T_PACEFIT_FACTOR_AGG f_gap_ten
  ON  f_gap_ten.factor_type='gap_ten_h' AND f_gap_ten.factor_value='H'
  AND f_gap_ten.course_code='' AND f_gap_ten.tds_code='' AND f_gap_ten.dist_band=''

-- ギャップボーナス（M×上がり）
LEFT JOIN T_PACEFIT_FACTOR_AGG f_gap_agari
  ON  f_gap_agari.factor_type='gap_agari_m' AND f_gap_agari.factor_value='M'
  AND f_gap_agari.course_code='' AND f_gap_agari.tds_code='' AND f_gap_agari.dist_band=''

WHERE k.pace_yoso IN ('H','M','S')
  AND k.ten_index_juni   IS NOT NULL AND TRIM(k.ten_index_juni)   <> ''
  AND k.agari_index_juni IS NOT NULL AND TRIM(k.agari_index_juni) <> ''
  AND b.tds_code IN ('1','2')

ON DUPLICATE KEY UPDATE
  pace_yoso=VALUES(pace_yoso),
  ten_juni=VALUES(ten_juni),
  agari_juni=VALUES(agari_juni),
  has_ten_gap=VALUES(has_ten_gap),
  has_agari_gap=VALUES(has_agari_gap),
  overall_score=VALUES(overall_score),
  course_score=VALUES(course_score),
  score_ten_o=VALUES(score_ten_o),
  score_agari_o=VALUES(score_agari_o),
  score_gap=VALUES(score_gap),
  score_ten_c=VALUES(score_ten_c),
  score_agari_c=VALUES(score_agari_c);
