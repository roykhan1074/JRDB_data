-- ============================================================
-- 展開シナリオ指数 ETL
-- 定義: 全出走馬を対象に、レース展開（脚質分布）と個馬の脚質の
--       マッチ度から回収率を予測する
-- 実行順: Part1 → Part2 → Part3 → Part4
-- Part2〜4 は差分投入可（ON DUPLICATE KEY UPDATE で冪等）
-- ============================================================


-- ============================================================
-- Part 1: テーブル定義
-- ============================================================

-- ------------------------------------------------------------
-- 1-1. 展開ファクトテーブル（全出走馬）
-- T_KYI × T_BAC × T_SED（結果確定分のみ）を結合した非正規化ログ
-- 脚質不明（0 or 空）の馬は除外
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS T_TENKAI_RACE_LOG (
  course_code    CHAR(2)       NOT NULL COMMENT '場コード',
  year_code      CHAR(2)       NOT NULL COMMENT '年',
  kai            CHAR(1)       NOT NULL COMMENT '回',
  day_code       CHAR(1)       NOT NULL COMMENT '日',
  race_num       CHAR(2)       NOT NULL COMMENT 'R',
  uma_num        CHAR(2)       NOT NULL COMMENT '馬番',
  ymd            CHAR(8)       NOT NULL COMMENT '年月日',

  -- レース条件
  tds_code       CHAR(1)                COMMENT '芝ダ 1:芝 2:ダ',
  distance       CHAR(4)                COMMENT '距離',

  -- この馬の脚質
  kyakushitsu    CHAR(1)                COMMENT '脚質 1:逃 2:先 3:差 4:追',

  -- このレースの展開情報
  heads          TINYINT UNSIGNED       COMMENT '出走頭数',
  nige_count     TINYINT UNSIGNED       COMMENT '逃げ馬数',
  senko_count    TINYINT UNSIGNED       COMMENT '先行馬数',
  front_ratio    DECIMAL(4,3)           COMMENT '(逃げ+先行)/頭数',
  pace_scenario  VARCHAR(15)            COMMENT 'solo_nige / front_heavy / balanced',

  -- 成績
  finish_order   CHAR(2)                COMMENT '着順',
  ijou_kubun     CHAR(1)                COMMENT '異常区分',
  win_payout     INT                    COMMENT '単勝払戻（円）',
  place_payout   INT                    COMMENT '複勝払戻（円）',

  load_date      CHAR(8)       NOT NULL COMMENT 'ロード日',

  PRIMARY KEY (course_code, year_code, kai, day_code, race_num, uma_num),
  INDEX idx_tenkai_log_ymd    (ymd),
  INDEX idx_tenkai_log_course (course_code, tds_code, distance)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='展開シナリオ ファクトテーブル（全出走馬）';


-- ------------------------------------------------------------
-- 1-2. 展開ファクター別集計テーブル（EAV形式）
-- course_code/tds_code/dist_band がすべて '' = 全体集計
-- 値あり = コース別集計
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS T_TENKAI_FACTOR_AGG (
  factor_type       VARCHAR(30)   NOT NULL COMMENT 'ファクター種別',
  factor_value      VARCHAR(40)   NOT NULL COMMENT 'ファクター値',
  course_code       CHAR(2)       NOT NULL DEFAULT '' COMMENT '場コード（空=全体）',
  tds_code          CHAR(1)       NOT NULL DEFAULT '' COMMENT '芝ダ（空=全体）',
  dist_band         VARCHAR(10)   NOT NULL DEFAULT '' COMMENT '距離帯（空=全体）',

  total_count       INT           NOT NULL DEFAULT 0,
  win_count         INT           NOT NULL DEFAULT 0,
  place_count       INT           NOT NULL DEFAULT 0,
  win_payout_sum    BIGINT        NOT NULL DEFAULT 0,
  place_payout_sum  BIGINT        NOT NULL DEFAULT 0,
  win_rate          DECIMAL(5,1)           COMMENT '勝率(%)',
  place_rate        DECIMAL(5,1)           COMMENT '複勝率(%)',
  win_recovery      DECIMAL(6,1)           COMMENT '単勝回収率',
  place_recovery    DECIMAL(6,1)           COMMENT '複勝回収率',

  updated_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                            ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (factor_type, factor_value, course_code, tds_code, dist_band),
  INDEX idx_tenkai_agg_type (factor_type, course_code, tds_code, dist_band)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='展開シナリオ ファクター別集計（EAV）';


-- ------------------------------------------------------------
-- 1-3. 展開シナリオ指数テーブル（出馬表表示用）
-- 出走全馬対象。pace_scenario / nige_count / front_ratio も格納し表示に使う。
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS T_TENKAI_SCORE (
  course_code       CHAR(2)       NOT NULL,
  year_code         CHAR(2)       NOT NULL,
  kai               CHAR(1)       NOT NULL,
  day_code          CHAR(1)       NOT NULL,
  race_num          CHAR(2)       NOT NULL,
  uma_num           CHAR(2)       NOT NULL,

  -- このレースの展開情報（表示・デバッグ用）
  pace_scenario     VARCHAR(15)             COMMENT 'solo_nige / front_heavy / balanced',
  nige_count        TINYINT UNSIGNED        COMMENT '逃げ馬数',
  front_ratio       DECIMAL(4,3)            COMMENT '(逃げ+先行)/頭数',

  -- 指数
  overall_score     DECIMAL(7,1)            COMMENT '全体展開シナリオ指数',
  course_score      DECIMAL(7,1)            COMMENT 'コース別展開シナリオ指数',

  -- 内訳
  score_pace_kyaku  DECIMAL(5,1)            COMMENT '展開×脚質スコア（全体偏差）',
  score_nige_count  DECIMAL(5,1)            COMMENT '逃げ頭数スコア（全体偏差）',

  updated_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                            ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (course_code, year_code, kai, day_code, race_num, uma_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='展開シナリオ指数（出馬表表示用）';


-- ============================================================
-- Part 2: T_TENKAI_RACE_LOG 投入
-- 全出走馬（芝・ダ、新馬除く、脚質確定馬のみ、成績確定済み）を対象
-- サブクエリでレースごとの脚質分布を集計して結合
-- 毎日差分実行可（冪等）
-- ============================================================
INSERT INTO T_TENKAI_RACE_LOG (
  course_code, year_code, kai, day_code, race_num, uma_num,
  ymd, tds_code, distance,
  kyakushitsu,
  heads, nige_count, senko_count, front_ratio, pace_scenario,
  finish_order, ijou_kubun, win_payout, place_payout,
  load_date
)
SELECT
  k.course_code, k.year_code, k.kai, k.day_code, k.race_num, k.uma_num,
  b.ymd,
  b.tds_code,
  b.distance,
  k.kyakushitsu,
  rs.heads,
  rs.nige_count,
  rs.senko_count,
  rs.front_ratio,
  CASE
    WHEN rs.nige_count = 1 AND rs.front_ratio <= 0.40 THEN 'solo_nige'
    WHEN rs.nige_count >= 2 OR  rs.front_ratio >= 0.55  THEN 'front_heavy'
    ELSE 'balanced'
  END AS pace_scenario,
  s.order_of_finish,
  s.ijou_kubun,
  CASE WHEN s.ijou_kubun IN ('0','') THEN COALESCE(CAST(TRIM(s.win)   AS UNSIGNED), 0) ELSE 0 END,
  CASE WHEN s.ijou_kubun IN ('0','') THEN COALESCE(CAST(TRIM(s.place) AS UNSIGNED), 0) ELSE 0 END,
  DATE_FORMAT(NOW(), '%Y%m%d')
FROM T_KYI k
INNER JOIN T_BAC b
  ON  b.course_code = k.course_code AND b.year_code = k.year_code
  AND b.kai = k.kai AND b.day_code = k.day_code AND b.race_num = k.race_num
INNER JOIN (
  -- このレースの脚質分布を集計（脚質確定馬のみカウント）
  SELECT
    course_code, year_code, kai, day_code, race_num,
    COUNT(*) AS heads,
    SUM(CASE WHEN TRIM(kyakushitsu) = '1' THEN 1 ELSE 0 END) AS nige_count,
    SUM(CASE WHEN TRIM(kyakushitsu) = '2' THEN 1 ELSE 0 END) AS senko_count,
    ROUND(
      (SUM(CASE WHEN TRIM(kyakushitsu) = '1' THEN 1 ELSE 0 END) +
       SUM(CASE WHEN TRIM(kyakushitsu) = '2' THEN 1 ELSE 0 END)) / COUNT(*),
    3) AS front_ratio
  FROM T_KYI
  WHERE TRIM(kyakushitsu) IN ('1','2','3','4')
  GROUP BY course_code, year_code, kai, day_code, race_num
) rs
  ON  rs.course_code = k.course_code AND rs.year_code = k.year_code
  AND rs.kai = k.kai AND rs.day_code = k.day_code AND rs.race_num = k.race_num
INNER JOIN T_SED s
  ON  s.course_code = k.course_code AND s.year_code = k.year_code
  AND s.kai = k.kai AND s.day_code = k.day_code
  AND s.race_num = k.race_num AND s.umaban = k.uma_num
WHERE TRIM(b.tds_code) IN ('1','2')
  AND TRIM(b.`class`) <> 'A1'
  AND TRIM(k.kyakushitsu) IN ('1','2','3','4')
  AND s.order_of_finish IS NOT NULL
  AND s.ijou_kubun IN ('0','')
ON DUPLICATE KEY UPDATE
  finish_order  = VALUES(finish_order),
  ijou_kubun    = VALUES(ijou_kubun),
  win_payout    = VALUES(win_payout),
  place_payout  = VALUES(place_payout),
  load_date     = VALUES(load_date);


-- ============================================================
-- Part 3: T_TENKAI_FACTOR_AGG 集計
-- 成績確定・正常完走のレコードのみ対象
-- 全体集計（course_code='' tds_code='' dist_band=''）と
-- コース別集計（course_code/tds_code/dist_band を指定）を両方投入する
-- ============================================================

-- ── ベースライン（全体）────────────────────────────────────────
INSERT INTO T_TENKAI_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'baseline', 'all', '', '', '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)              / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3)  / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_TENKAI_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);

-- ── ベースライン（コース×芝ダ×距離帯別）──────────────────────────
INSERT INTO T_TENKAI_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'baseline', 'all',
  course_code, tds_code,
  CASE
    WHEN CAST(TRIM(distance) AS UNSIGNED) <= 1200 THEN '~1200'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <= 1400 THEN '1201~1400'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <= 1600 THEN '1401~1600'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <= 2000 THEN '1601~2000'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <= 2400 THEN '2001~2400'
    ELSE '2401~'
  END AS dist_band,
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)              / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3)  / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_TENKAI_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(distance) <> ''
GROUP BY course_code, tds_code,
  CASE
    WHEN CAST(TRIM(distance) AS UNSIGNED) <= 1200 THEN '~1200'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <= 1400 THEN '1201~1400'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <= 1600 THEN '1401~1600'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <= 2000 THEN '1601~2000'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <= 2400 THEN '2001~2400'
    ELSE '2401~'
  END
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ── 3-1. 展開×脚質（全体）──────────────────────────────────────
-- factor_value = '{pace_scenario}|{kyakushitsu}'
-- 例: 'front_heavy|3'（ハイペース展開の差し馬）
INSERT INTO T_TENKAI_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'pace_kyaku',
  CONCAT(pace_scenario, '|', TRIM(kyakushitsu)) AS factor_value,
  '', '', '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)              / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3)  / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_TENKAI_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(kyakushitsu) IN ('1','2','3','4')
  AND pace_scenario IS NOT NULL
GROUP BY pace_scenario, TRIM(kyakushitsu)
HAVING COUNT(*) >= 30
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);

-- ── 3-1b. 展開×脚質（コース×芝ダ×距離帯別）──────────────────────
INSERT INTO T_TENKAI_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'pace_kyaku',
  CONCAT(pace_scenario, '|', TRIM(kyakushitsu)) AS factor_value,
  course_code, tds_code,
  CASE
    WHEN CAST(TRIM(distance) AS UNSIGNED) <= 1200 THEN '~1200'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <= 1400 THEN '1201~1400'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <= 1600 THEN '1401~1600'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <= 2000 THEN '1601~2000'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <= 2400 THEN '2001~2400'
    ELSE '2401~'
  END AS dist_band,
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)              / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3)  / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_TENKAI_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(kyakushitsu) IN ('1','2','3','4')
  AND pace_scenario IS NOT NULL
  AND TRIM(distance) <> ''
GROUP BY course_code, tds_code, dist_band, pace_scenario, TRIM(kyakushitsu)
HAVING COUNT(*) >= 20
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ── 3-2. 逃げ頭数帯（全体）──────────────────────────────────────
-- 逃げ馬が0頭/1頭（単騎）/2頭（ハナ争い）/3頭以上（乱ペース）
INSERT INTO T_TENKAI_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'nige_count_band',
  CASE
    WHEN nige_count = 0 THEN '0'
    WHEN nige_count = 1 THEN '1'
    WHEN nige_count = 2 THEN '2'
    ELSE '3+'
  END AS factor_value,
  '', '', '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)              / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3)  / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_TENKAI_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
GROUP BY
  CASE
    WHEN nige_count = 0 THEN '0'
    WHEN nige_count = 1 THEN '1'
    WHEN nige_count = 2 THEN '2'
    ELSE '3+'
  END
HAVING COUNT(*) >= 30
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);

-- ── 3-2b. 逃げ頭数帯（コース×芝ダ別）──────────────────────────
-- 距離帯は分けない（サンプル確保のため）
INSERT INTO T_TENKAI_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'nige_count_band',
  CASE
    WHEN nige_count = 0 THEN '0'
    WHEN nige_count = 1 THEN '1'
    WHEN nige_count = 2 THEN '2'
    ELSE '3+'
  END AS factor_value,
  course_code, tds_code, '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)              / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3)  / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_TENKAI_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
GROUP BY course_code, tds_code,
  CASE
    WHEN nige_count = 0 THEN '0'
    WHEN nige_count = 1 THEN '1'
    WHEN nige_count = 2 THEN '2'
    ELSE '3+'
  END
HAVING COUNT(*) >= 20
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ============================================================
-- Part 4: T_TENKAI_SCORE 計算
--
-- 各ファクターの回収率偏差（factor_recovery - baseline_recovery）を合計して指数化。
-- 全体指数: baseline は course_code='' tds_code='' dist_band='' の 'baseline'/'all'
-- コース別指数: コース別 baseline が存在すれば使用し、なければ全体 baseline にフォールバック
--
-- 対象: T_KYI 全馬（芝・ダ、脚質確定馬のみ）
-- 展開情報: 当日 T_KYI からサブクエリで集計（成績不要）
-- 冪等: ON DUPLICATE KEY UPDATE
-- ============================================================
INSERT INTO T_TENKAI_SCORE (
  course_code, year_code, kai, day_code, race_num, uma_num,
  pace_scenario, nige_count, front_ratio,
  overall_score, course_score,
  score_pace_kyaku, score_nige_count
)
SELECT
  k.course_code, k.year_code, k.kai, k.day_code, k.race_num, k.uma_num,

  -- 展開シナリオ（当日T_KYIから計算）
  CASE
    WHEN rs.nige_count = 1 AND rs.front_ratio <= 0.40 THEN 'solo_nige'
    WHEN rs.nige_count >= 2 OR  rs.front_ratio >= 0.55  THEN 'front_heavy'
    ELSE 'balanced'
  END AS pace_scenario,
  rs.nige_count,
  rs.front_ratio,

  -- ── 全体展開シナリオ指数 ─────────────────────────────────────
  ROUND(
    -- 展開×脚質
    COALESCE(f_pk_o.win_recovery,  bl_o.win_recovery) - bl_o.win_recovery
    -- 逃げ頭数
    + COALESCE(f_nc_o.win_recovery, bl_o.win_recovery) - bl_o.win_recovery
  , 1) AS overall_score,

  -- ── コース別展開シナリオ指数 ──────────────────────────────────
  -- ルール: コース別データがあればコース別ベースラインで差分
  --         フォールバック時は全体偏差をそのまま使用
  ROUND(
    COALESCE(
      f_pk_c.win_recovery - COALESCE(bl_c.win_recovery, bl_o.win_recovery),
      f_pk_o.win_recovery - bl_o.win_recovery,
      0
    )
    + COALESCE(
      f_nc_c.win_recovery - COALESCE(bl_c.win_recovery, bl_o.win_recovery),
      f_nc_o.win_recovery - bl_o.win_recovery,
      0
    )
  , 1) AS course_score,

  -- ── スコア内訳 ────────────────────────────────────────────────
  ROUND(COALESCE(f_pk_o.win_recovery, bl_o.win_recovery) - bl_o.win_recovery, 1),
  ROUND(COALESCE(f_nc_o.win_recovery, bl_o.win_recovery) - bl_o.win_recovery, 1)

FROM T_KYI k
INNER JOIN T_BAC b
  ON  b.course_code=k.course_code AND b.year_code=k.year_code
  AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num

-- 当日レースの脚質分布（T_KYIから集計）
INNER JOIN (
  SELECT
    course_code, year_code, kai, day_code, race_num,
    COUNT(*) AS heads,
    SUM(CASE WHEN TRIM(kyakushitsu) = '1' THEN 1 ELSE 0 END) AS nige_count,
    SUM(CASE WHEN TRIM(kyakushitsu) = '2' THEN 1 ELSE 0 END) AS senko_count,
    ROUND(
      (SUM(CASE WHEN TRIM(kyakushitsu) = '1' THEN 1 ELSE 0 END) +
       SUM(CASE WHEN TRIM(kyakushitsu) = '2' THEN 1 ELSE 0 END)) / COUNT(*),
    3) AS front_ratio
  FROM T_KYI
  WHERE TRIM(kyakushitsu) IN ('1','2','3','4')
  GROUP BY course_code, year_code, kai, day_code, race_num
) rs
  ON  rs.course_code=k.course_code AND rs.year_code=k.year_code
  AND rs.kai=k.kai AND rs.day_code=k.day_code AND rs.race_num=k.race_num

-- 全体ベースライン
CROSS JOIN (
  SELECT win_recovery FROM T_TENKAI_FACTOR_AGG
  WHERE factor_type='baseline' AND factor_value='all'
    AND course_code='' AND tds_code='' AND dist_band=''
) bl_o

-- コース別ベースライン
LEFT JOIN (
  SELECT course_code, tds_code, dist_band, win_recovery
  FROM T_TENKAI_FACTOR_AGG
  WHERE factor_type='baseline' AND factor_value='all' AND course_code<>''
) bl_c
  ON  bl_c.course_code = k.course_code
  AND bl_c.tds_code    = TRIM(b.tds_code)
  AND bl_c.dist_band   = CASE
      WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1200 THEN '~1200'
      WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1400 THEN '1201~1400'
      WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1600 THEN '1401~1600'
      WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 2000 THEN '1601~2000'
      WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 2400 THEN '2001~2400'
      ELSE '2401~' END

-- 展開×脚質（全体）
LEFT JOIN T_TENKAI_FACTOR_AGG f_pk_o
  ON  f_pk_o.factor_type  = 'pace_kyaku'
  AND f_pk_o.course_code  = '' AND f_pk_o.tds_code = '' AND f_pk_o.dist_band = ''
  AND f_pk_o.factor_value = CONCAT(
    CASE
      WHEN rs.nige_count = 1 AND rs.front_ratio <= 0.40 THEN 'solo_nige'
      WHEN rs.nige_count >= 2 OR  rs.front_ratio >= 0.55  THEN 'front_heavy'
      ELSE 'balanced'
    END, '|', TRIM(k.kyakushitsu))

-- 展開×脚質（コース×芝ダ×距離帯別）
LEFT JOIN T_TENKAI_FACTOR_AGG f_pk_c
  ON  f_pk_c.factor_type  = 'pace_kyaku'
  AND f_pk_c.course_code  = k.course_code
  AND f_pk_c.tds_code     = TRIM(b.tds_code)
  AND f_pk_c.dist_band    = CASE
      WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1200 THEN '~1200'
      WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1400 THEN '1201~1400'
      WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1600 THEN '1401~1600'
      WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 2000 THEN '1601~2000'
      WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 2400 THEN '2001~2400'
      ELSE '2401~' END
  AND f_pk_c.factor_value = CONCAT(
    CASE
      WHEN rs.nige_count = 1 AND rs.front_ratio <= 0.40 THEN 'solo_nige'
      WHEN rs.nige_count >= 2 OR  rs.front_ratio >= 0.55  THEN 'front_heavy'
      ELSE 'balanced'
    END, '|', TRIM(k.kyakushitsu))

-- 逃げ頭数帯（全体）
LEFT JOIN T_TENKAI_FACTOR_AGG f_nc_o
  ON  f_nc_o.factor_type  = 'nige_count_band'
  AND f_nc_o.course_code  = '' AND f_nc_o.tds_code = '' AND f_nc_o.dist_band = ''
  AND f_nc_o.factor_value = CASE
      WHEN rs.nige_count = 0 THEN '0'
      WHEN rs.nige_count = 1 THEN '1'
      WHEN rs.nige_count = 2 THEN '2'
      ELSE '3+' END

-- 逃げ頭数帯（コース×芝ダ別）
LEFT JOIN T_TENKAI_FACTOR_AGG f_nc_c
  ON  f_nc_c.factor_type  = 'nige_count_band'
  AND f_nc_c.course_code  = k.course_code
  AND f_nc_c.tds_code     = TRIM(b.tds_code)
  AND f_nc_c.dist_band    = ''
  AND f_nc_c.factor_value = CASE
      WHEN rs.nige_count = 0 THEN '0'
      WHEN rs.nige_count = 1 THEN '1'
      WHEN rs.nige_count = 2 THEN '2'
      ELSE '3+' END

WHERE TRIM(b.tds_code) IN ('1','2')
  AND TRIM(k.kyakushitsu) IN ('1','2','3','4')

ON DUPLICATE KEY UPDATE
  pace_scenario     = VALUES(pace_scenario),
  nige_count        = VALUES(nige_count),
  front_ratio       = VALUES(front_ratio),
  overall_score     = VALUES(overall_score),
  course_score      = VALUES(course_score),
  score_pace_kyaku  = VALUES(score_pace_kyaku),
  score_nige_count  = VALUES(score_nige_count);
