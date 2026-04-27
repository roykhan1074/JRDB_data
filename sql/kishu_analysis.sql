-- ============================================================
-- 騎手分析テーブル定義 & ETL
-- PowerPro スタイル騎手アビリティ画面向けデータ基盤
-- ============================================================
-- 実行順: Part1 → Part2 → Part3
-- Part2,3 は差分投入可。毎日 Part2→Part3 を再実行するだけで最新化される。
-- ============================================================


-- ============================================================
-- Part 1: テーブル定義
-- ============================================================

-- ------------------------------------------------------------
-- 1-1. ファクトテーブル（騎手 × レース 1行）
--
-- T_KYI + T_BAC + T_SED を JOIN した非正規化ログ。
-- このテーブルから任意の集計が導出できる。
-- 今後の拡張（馬齢・前走間隔・馬場状態など）はここに列追加するだけでよい。
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS T_KISHU_RACE_LOG (
  -- ── レースキー（T_KYI / T_BAC / T_SED 共通）──────────────────
  course_code       CHAR(2)      NOT NULL COMMENT '場コード',
  year_code         CHAR(2)      NOT NULL COMMENT '年（西暦下2桁）',
  kai               CHAR(1)      NOT NULL COMMENT '回',
  day_code          CHAR(1)      NOT NULL COMMENT '日（16進）',
  race_num          CHAR(2)      NOT NULL COMMENT 'R',
  uma_num           CHAR(2)      NOT NULL COMMENT '馬番',

  -- ── 日付 ──────────────────────────────────────────────────
  ymd               CHAR(8)      NOT NULL COMMENT '年月日 YYYYMMDD（T_BAC）',

  -- ── 騎手 ──────────────────────────────────────────────────
  kishu_name        VARCHAR(12)  NOT NULL COMMENT '騎手名（T_KYI）',
  kishu_code        CHAR(5)               COMMENT '騎手コード（T_KYI）',

  -- ── 関係者 ────────────────────────────────────────────────
  trainer_name      VARCHAR(12)           COMMENT '調教師名（T_KYI）',
  umanushi_name     VARCHAR(40)           COMMENT '馬主名（T_KYI）',

  -- ── レース条件（T_BAC）────────────────────────────────────
  distance          CHAR(4)               COMMENT '距離（m）',
  tds_code          CHAR(1)               COMMENT '芝ダ障害 1:芝 2:ダ 3:障',
  class             CHAR(2)               COMMENT '条件クラス A1/A3/05/10/16/OP 等',
  heads             CHAR(2)               COMMENT '頭数',

  -- ── ファクター（T_KYI）────────────────────────────────────
  kijun_odds        CHAR(5)               COMMENT '基準単勝オッズ',
  ten_index_juni    CHAR(2)               COMMENT 'テン指数順位',
  agari_index_juni  CHAR(2)               COMMENT '上がり指数順位',

  -- ── 成績（T_SED）─────────────────────────────────────────
  finish_order      CHAR(2)               COMMENT '着順（NULL = 結果未格納）',
  ijou_kubun        CHAR(1)               COMMENT '異常区分 0:正常 1:取消 2:除外 etc.',
  win_payout        INT                   COMMENT '単勝払戻（円/100円ベット）0=対象外',
  place_payout      INT                   COMMENT '複勝払戻（円/100円ベット）0=対象外',

  -- ── メタ ──────────────────────────────────────────────────
  load_date         CHAR(8)      NOT NULL COMMENT 'ロード日 YYYYMMDD',

  PRIMARY KEY (course_code, year_code, kai, day_code, race_num, uma_num),
  INDEX idx_log_kishu_ymd   (kishu_name, ymd),
  INDEX idx_log_kishu_code  (kishu_code, ymd),
  INDEX idx_log_ymd         (ymd)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='騎手成績ログ（分析ファクトテーブル・日次粒度）';


-- ------------------------------------------------------------
-- 1-2. ファクター別集計テーブル（PowerPro 表示用）
--
-- 騎手 × 年 × ファクター種別 × ファクター値 の 1行。
-- EAV 形式のため、新ファクターはテーブル変更なしで追加できる。
--
-- factor_type 一覧（Part3 で INSERT する種別）:
--   course      競馬場（course_code）
--   distance    距離帯（~1200 / 1201~1400 / 1401~1600 / 1601~2000 / 2001~2400 / 2401~）
--   tds         芝ダ（1:芝 / 2:ダ / 3:障）
--   class       条件クラス（A1 / A3 / 05 / 10 / 16 / OP 等）
--   odds        基準オッズ帯（~3.0 / 3.0~5.0 / 5.0~10.0 / 10.0~20.0 / 20.0~50.0 / 50.0~）
--   ten_rank    テン指数順位帯（1 / 2~3 / 4~6 / 7~）
--   agari_rank  上がり指数順位帯（1 / 2~3 / 4~6 / 7~）
--   trainer     調教師名
--   umanushi    馬主名
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS T_KISHU_FACTOR_AGG (
  -- ── 主キー ────────────────────────────────────────────────
  kishu_name        VARCHAR(12)  NOT NULL COMMENT '騎手名',
  kishu_code        CHAR(5)               COMMENT '騎手コード',
  agg_year          CHAR(4)      NOT NULL COMMENT '集計年 YYYY',
  factor_type       VARCHAR(20)  NOT NULL COMMENT 'ファクター種別',
  factor_value      VARCHAR(40)  NOT NULL COMMENT 'ファクター値',

  -- ── 集計カウント ───────────────────────────────────────────
  total_count       INT          NOT NULL DEFAULT 0 COMMENT '出走数（異常除く）',
  win_count         INT          NOT NULL DEFAULT 0 COMMENT '1着数',
  place_count       INT          NOT NULL DEFAULT 0 COMMENT '複勝数（3着以内）',
  win_payout_sum    BIGINT       NOT NULL DEFAULT 0 COMMENT '単勝払戻合計',
  place_payout_sum  BIGINT       NOT NULL DEFAULT 0 COMMENT '複勝払戻合計',

  -- ── 計算値（表示用・再計算可）─────────────────────────────
  win_rate          DECIMAL(5,1)          COMMENT '勝率（%）',
  place_rate        DECIMAL(5,1)          COMMENT '複勝率（%）',
  win_recovery      DECIMAL(6,1)          COMMENT '単勝回収率（円/100円）',
  place_recovery    DECIMAL(6,1)          COMMENT '複勝回収率（円/100円）',

  -- ── メタ ──────────────────────────────────────────────────
  updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                           ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (kishu_name, agg_year, factor_type, factor_value),
  INDEX idx_agg_factor_year  (factor_type, factor_value, agg_year),
  INDEX idx_agg_year_kishu   (agg_year, kishu_name),
  INDEX idx_agg_kishu_code   (kishu_code, agg_year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='騎手ファクター別集計（PowerPro アビリティ画面用）';


-- ============================================================
-- Part 2: T_KISHU_RACE_LOG 投入
--
-- T_KYI × T_BAC × T_SED を JOIN して非正規化ログを作る。
-- T_SED は当日速報後から存在するため LEFT JOIN。
-- 毎日追分実行可（ON DUPLICATE KEY UPDATE で冪等）。
-- ============================================================
INSERT INTO T_KISHU_RACE_LOG (
  course_code, year_code, kai, day_code, race_num, uma_num,
  ymd,
  kishu_name, kishu_code,
  trainer_name, umanushi_name,
  distance, tds_code, class, heads,
  kijun_odds, ten_index_juni, agari_index_juni,
  finish_order, ijou_kubun,
  win_payout, place_payout,
  load_date
)
SELECT
  k.course_code, k.year_code, k.kai, k.day_code, k.race_num, k.uma_num,
  b.ymd,
  k.kishu_name,
  k.kishu_code,
  k.trainer_name,
  k.umanushi_name,
  b.distance,
  b.tds_code,
  b.`class`,
  b.heads,
  k.kijun_odds,
  k.ten_index_juni,
  k.agari_index_juni,
  s.order_of_finish,
  s.ijou_kubun,
  -- 正常完走(0)のみ払戻を格納。取消・除外は0として扱う。
  CASE WHEN s.ijou_kubun IN ('0', '') THEN COALESCE(CAST(TRIM(s.win)   AS UNSIGNED), 0) ELSE 0 END,
  CASE WHEN s.ijou_kubun IN ('0', '') THEN COALESCE(CAST(TRIM(s.place) AS UNSIGNED), 0) ELSE 0 END,
  DATE_FORMAT(NOW(), '%Y%m%d')
FROM T_KYI k
INNER JOIN T_BAC b
  ON  b.course_code = k.course_code
  AND b.year_code   = k.year_code
  AND b.kai         = k.kai
  AND b.day_code    = k.day_code
  AND b.race_num    = k.race_num
LEFT JOIN T_SED s
  ON  s.course_code = k.course_code
  AND s.year_code   = k.year_code
  AND s.kai         = k.kai
  AND s.day_code    = k.day_code
  AND s.race_num    = k.race_num
  AND s.umaban      = k.uma_num
WHERE TRIM(k.kishu_name) <> ''
  AND TRIM(b.tds_code)   IN ('1', '2', '3')  -- 障害含む全レース
ON DUPLICATE KEY UPDATE
  finish_order      = VALUES(finish_order),
  ijou_kubun        = VALUES(ijou_kubun),
  win_payout        = VALUES(win_payout),
  place_payout      = VALUES(place_payout),
  load_date         = VALUES(load_date);


-- ============================================================
-- Part 3: T_KISHU_FACTOR_AGG 集計
--
-- T_KISHU_RACE_LOG から各ファクター別に集計して UPSERT。
-- 集計対象: 成績が存在し異常区分が正常(0 or '')のレコードのみ。
-- 実行順序は問わない（各 factor_type は独立した UPSERT）。
-- ============================================================

-- ── 共通 CTE（集計ベース）────────────────────────────────────────
-- 以下各 INSERT で共通的に使う条件:
--   1. finish_order が NULL でない（T_SED が存在する）
--   2. ijou_kubun IN ('0', '')（正常完走）
-- ────────────────────────────────────────────────────────────────

-- ── 3-1. 競馬場別 ────────────────────────────────────────────────
INSERT INTO T_KISHU_FACTOR_AGG
  (kishu_name, kishu_code, agg_year, factor_type, factor_value,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  kishu_name, kishu_code,
  SUBSTRING(ymd, 1, 4),
  'course',
  course_code,
  COUNT(*)                                                          AS total_count,
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)                    AS win_count,
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3)        AS place_count,
  SUM(win_payout)                                                   AS win_payout_sum,
  SUM(place_payout)                                                 AS place_payout_sum,
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)
        / COUNT(*) * 100, 1)                                        AS win_rate,
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3)
        / COUNT(*) * 100, 1)                                        AS place_rate,
  ROUND(SUM(win_payout)   / COUNT(*), 1)                           AS win_recovery,
  ROUND(SUM(place_payout) / COUNT(*), 1)                           AS place_recovery
FROM T_KISHU_RACE_LOG
WHERE finish_order IS NOT NULL
  AND ijou_kubun IN ('0', '')
  AND TRIM(course_code) <> ''
GROUP BY kishu_name, kishu_code, SUBSTRING(ymd, 1, 4), course_code
ON DUPLICATE KEY UPDATE
  total_count       = VALUES(total_count),
  win_count         = VALUES(win_count),
  place_count       = VALUES(place_count),
  win_payout_sum    = VALUES(win_payout_sum),
  place_payout_sum  = VALUES(place_payout_sum),
  win_rate          = VALUES(win_rate),
  place_rate        = VALUES(place_rate),
  win_recovery      = VALUES(win_recovery),
  place_recovery    = VALUES(place_recovery);


-- ── 3-2. 距離帯別 ────────────────────────────────────────────────
INSERT INTO T_KISHU_FACTOR_AGG
  (kishu_name, kishu_code, agg_year, factor_type, factor_value,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  kishu_name, kishu_code,
  SUBSTRING(ymd, 1, 4),
  'distance',
  CASE
    WHEN CAST(TRIM(distance) AS UNSIGNED) <=  1200 THEN '~1200'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <=  1400 THEN '1201~1400'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <=  1600 THEN '1401~1600'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <=  2000 THEN '1601~2000'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <=  2400 THEN '2001~2400'
    ELSE '2401~'
  END                                                               AS factor_value,
  COUNT(*)                                                          AS total_count,
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)                    AS win_count,
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3)        AS place_count,
  SUM(win_payout)                                                   AS win_payout_sum,
  SUM(place_payout)                                                 AS place_payout_sum,
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)
        / COUNT(*) * 100, 1)                                        AS win_rate,
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3)
        / COUNT(*) * 100, 1)                                        AS place_rate,
  ROUND(SUM(win_payout)   / COUNT(*), 1)                           AS win_recovery,
  ROUND(SUM(place_payout) / COUNT(*), 1)                           AS place_recovery
FROM T_KISHU_RACE_LOG
WHERE finish_order IS NOT NULL
  AND ijou_kubun IN ('0', '')
  AND TRIM(distance) <> ''
GROUP BY kishu_name, kishu_code, SUBSTRING(ymd, 1, 4),
  CASE
    WHEN CAST(TRIM(distance) AS UNSIGNED) <=  1200 THEN '~1200'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <=  1400 THEN '1201~1400'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <=  1600 THEN '1401~1600'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <=  2000 THEN '1601~2000'
    WHEN CAST(TRIM(distance) AS UNSIGNED) <=  2400 THEN '2001~2400'
    ELSE '2401~'
  END
ON DUPLICATE KEY UPDATE
  total_count       = VALUES(total_count),
  win_count         = VALUES(win_count),
  place_count       = VALUES(place_count),
  win_payout_sum    = VALUES(win_payout_sum),
  place_payout_sum  = VALUES(place_payout_sum),
  win_rate          = VALUES(win_rate),
  place_rate        = VALUES(place_rate),
  win_recovery      = VALUES(win_recovery),
  place_recovery    = VALUES(place_recovery);


-- ── 3-3. 芝ダ別 ──────────────────────────────────────────────────
INSERT INTO T_KISHU_FACTOR_AGG
  (kishu_name, kishu_code, agg_year, factor_type, factor_value,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  kishu_name, kishu_code,
  SUBSTRING(ymd, 1, 4),
  'tds',
  TRIM(tds_code),
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1) / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_KISHU_RACE_LOG
WHERE finish_order IS NOT NULL
  AND ijou_kubun IN ('0', '')
  AND TRIM(tds_code) IN ('1', '2', '3')
GROUP BY kishu_name, kishu_code, SUBSTRING(ymd, 1, 4), TRIM(tds_code)
ON DUPLICATE KEY UPDATE
  total_count = VALUES(total_count), win_count = VALUES(win_count),
  place_count = VALUES(place_count), win_payout_sum = VALUES(win_payout_sum),
  place_payout_sum = VALUES(place_payout_sum), win_rate = VALUES(win_rate),
  place_rate = VALUES(place_rate), win_recovery = VALUES(win_recovery),
  place_recovery = VALUES(place_recovery);


-- ── 3-4. 条件クラス別 ────────────────────────────────────────────
INSERT INTO T_KISHU_FACTOR_AGG
  (kishu_name, kishu_code, agg_year, factor_type, factor_value,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  kishu_name, kishu_code,
  SUBSTRING(ymd, 1, 4),
  'class',
  TRIM(class),
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1) / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_KISHU_RACE_LOG
WHERE finish_order IS NOT NULL
  AND ijou_kubun IN ('0', '')
  AND TRIM(class) <> ''
GROUP BY kishu_name, kishu_code, SUBSTRING(ymd, 1, 4), TRIM(class)
ON DUPLICATE KEY UPDATE
  total_count = VALUES(total_count), win_count = VALUES(win_count),
  place_count = VALUES(place_count), win_payout_sum = VALUES(win_payout_sum),
  place_payout_sum = VALUES(place_payout_sum), win_rate = VALUES(win_rate),
  place_rate = VALUES(place_rate), win_recovery = VALUES(win_recovery),
  place_recovery = VALUES(place_recovery);


-- ── 3-5. 基準オッズ帯別 ──────────────────────────────────────────
INSERT INTO T_KISHU_FACTOR_AGG
  (kishu_name, kishu_code, agg_year, factor_type, factor_value,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  kishu_name, kishu_code,
  SUBSTRING(ymd, 1, 4),
  'odds',
  CASE
    WHEN CAST(TRIM(kijun_odds) AS DECIMAL(6,1)) <   3.0 THEN '~3.0'
    WHEN CAST(TRIM(kijun_odds) AS DECIMAL(6,1)) <   5.0 THEN '3.0~5.0'
    WHEN CAST(TRIM(kijun_odds) AS DECIMAL(6,1)) <  10.0 THEN '5.0~10.0'
    WHEN CAST(TRIM(kijun_odds) AS DECIMAL(6,1)) <  20.0 THEN '10.0~20.0'
    WHEN CAST(TRIM(kijun_odds) AS DECIMAL(6,1)) <  50.0 THEN '20.0~50.0'
    ELSE '50.0~'
  END                                                               AS factor_value,
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1) / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_KISHU_RACE_LOG
WHERE finish_order IS NOT NULL
  AND ijou_kubun IN ('0', '')
  AND TRIM(kijun_odds) <> ''
  AND CAST(TRIM(kijun_odds) AS DECIMAL(6,1)) > 0
GROUP BY kishu_name, kishu_code, SUBSTRING(ymd, 1, 4),
  CASE
    WHEN CAST(TRIM(kijun_odds) AS DECIMAL(6,1)) <   3.0 THEN '~3.0'
    WHEN CAST(TRIM(kijun_odds) AS DECIMAL(6,1)) <   5.0 THEN '3.0~5.0'
    WHEN CAST(TRIM(kijun_odds) AS DECIMAL(6,1)) <  10.0 THEN '5.0~10.0'
    WHEN CAST(TRIM(kijun_odds) AS DECIMAL(6,1)) <  20.0 THEN '10.0~20.0'
    WHEN CAST(TRIM(kijun_odds) AS DECIMAL(6,1)) <  50.0 THEN '20.0~50.0'
    ELSE '50.0~'
  END
ON DUPLICATE KEY UPDATE
  total_count = VALUES(total_count), win_count = VALUES(win_count),
  place_count = VALUES(place_count), win_payout_sum = VALUES(win_payout_sum),
  place_payout_sum = VALUES(place_payout_sum), win_rate = VALUES(win_rate),
  place_rate = VALUES(place_rate), win_recovery = VALUES(win_recovery),
  place_recovery = VALUES(place_recovery);


-- ── 3-6. テン指数順位帯別 ────────────────────────────────────────
-- 1位 = 最も速い先行馬。脚質との相関を見るのに有効。
INSERT INTO T_KISHU_FACTOR_AGG
  (kishu_name, kishu_code, agg_year, factor_type, factor_value,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  kishu_name, kishu_code,
  SUBSTRING(ymd, 1, 4),
  'ten_rank',
  CASE
    WHEN CAST(TRIM(ten_index_juni) AS UNSIGNED) = 1               THEN '1'
    WHEN CAST(TRIM(ten_index_juni) AS UNSIGNED) BETWEEN 2 AND 3   THEN '2~3'
    WHEN CAST(TRIM(ten_index_juni) AS UNSIGNED) BETWEEN 4 AND 6   THEN '4~6'
    ELSE '7~'
  END                                                               AS factor_value,
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1) / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_KISHU_RACE_LOG
WHERE finish_order IS NOT NULL
  AND ijou_kubun IN ('0', '')
  AND TRIM(ten_index_juni) <> ''
  AND CAST(TRIM(ten_index_juni) AS UNSIGNED) > 0
GROUP BY kishu_name, kishu_code, SUBSTRING(ymd, 1, 4),
  CASE
    WHEN CAST(TRIM(ten_index_juni) AS UNSIGNED) = 1               THEN '1'
    WHEN CAST(TRIM(ten_index_juni) AS UNSIGNED) BETWEEN 2 AND 3   THEN '2~3'
    WHEN CAST(TRIM(ten_index_juni) AS UNSIGNED) BETWEEN 4 AND 6   THEN '4~6'
    ELSE '7~'
  END
ON DUPLICATE KEY UPDATE
  total_count = VALUES(total_count), win_count = VALUES(win_count),
  place_count = VALUES(place_count), win_payout_sum = VALUES(win_payout_sum),
  place_payout_sum = VALUES(place_payout_sum), win_rate = VALUES(win_rate),
  place_rate = VALUES(place_rate), win_recovery = VALUES(win_recovery),
  place_recovery = VALUES(place_recovery);


-- ── 3-7. 上がり指数順位帯別 ──────────────────────────────────────
-- 1位 = 最も速い末脚。差し・追込型の騎手評価に有効。
INSERT INTO T_KISHU_FACTOR_AGG
  (kishu_name, kishu_code, agg_year, factor_type, factor_value,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  kishu_name, kishu_code,
  SUBSTRING(ymd, 1, 4),
  'agari_rank',
  CASE
    WHEN CAST(TRIM(agari_index_juni) AS UNSIGNED) = 1             THEN '1'
    WHEN CAST(TRIM(agari_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
    WHEN CAST(TRIM(agari_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
    ELSE '7~'
  END                                                               AS factor_value,
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1) / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_KISHU_RACE_LOG
WHERE finish_order IS NOT NULL
  AND ijou_kubun IN ('0', '')
  AND TRIM(agari_index_juni) <> ''
  AND CAST(TRIM(agari_index_juni) AS UNSIGNED) > 0
GROUP BY kishu_name, kishu_code, SUBSTRING(ymd, 1, 4),
  CASE
    WHEN CAST(TRIM(agari_index_juni) AS UNSIGNED) = 1             THEN '1'
    WHEN CAST(TRIM(agari_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
    WHEN CAST(TRIM(agari_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
    ELSE '7~'
  END
ON DUPLICATE KEY UPDATE
  total_count = VALUES(total_count), win_count = VALUES(win_count),
  place_count = VALUES(place_count), win_payout_sum = VALUES(win_payout_sum),
  place_payout_sum = VALUES(place_payout_sum), win_rate = VALUES(win_rate),
  place_rate = VALUES(place_rate), win_recovery = VALUES(win_recovery),
  place_recovery = VALUES(place_recovery);


-- ── 3-8. 調教師別 ────────────────────────────────────────────────
-- 特定の調教師との相性（コンビ成績）を把握する。
-- 出走数が少ないコンビはノイズが多いため、表示側で total_count >= 10 フィルタを推奨。
INSERT INTO T_KISHU_FACTOR_AGG
  (kishu_name, kishu_code, agg_year, factor_type, factor_value,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  kishu_name, kishu_code,
  SUBSTRING(ymd, 1, 4),
  'trainer',
  TRIM(trainer_name),
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1) / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_KISHU_RACE_LOG
WHERE finish_order IS NOT NULL
  AND ijou_kubun IN ('0', '')
  AND TRIM(trainer_name) <> ''
GROUP BY kishu_name, kishu_code, SUBSTRING(ymd, 1, 4), TRIM(trainer_name)
ON DUPLICATE KEY UPDATE
  total_count = VALUES(total_count), win_count = VALUES(win_count),
  place_count = VALUES(place_count), win_payout_sum = VALUES(win_payout_sum),
  place_payout_sum = VALUES(place_payout_sum), win_rate = VALUES(win_rate),
  place_rate = VALUES(place_rate), win_recovery = VALUES(win_recovery),
  place_recovery = VALUES(place_recovery);


-- ── 3-9. 馬主別 ──────────────────────────────────────────────────
-- 特定馬主との組み合わせで回収率が突出するケースを検出する。
-- 出走数が少ない組み合わせはノイズが多いため、total_count >= 10 フィルタを推奨。
INSERT INTO T_KISHU_FACTOR_AGG
  (kishu_name, kishu_code, agg_year, factor_type, factor_value,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  kishu_name, kishu_code,
  SUBSTRING(ymd, 1, 4),
  'umanushi',
  TRIM(umanushi_name),
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1) / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_KISHU_RACE_LOG
WHERE finish_order IS NOT NULL
  AND ijou_kubun IN ('0', '')
  AND TRIM(umanushi_name) <> ''
GROUP BY kishu_name, kishu_code, SUBSTRING(ymd, 1, 4), TRIM(umanushi_name)
ON DUPLICATE KEY UPDATE
  total_count = VALUES(total_count), win_count = VALUES(win_count),
  place_count = VALUES(place_count), win_payout_sum = VALUES(win_payout_sum),
  place_payout_sum = VALUES(place_payout_sum), win_rate = VALUES(win_rate),
  place_rate = VALUES(place_rate), win_recovery = VALUES(win_recovery),
  place_recovery = VALUES(place_recovery);
