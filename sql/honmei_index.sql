-- ============================================================
-- 本命指数 ETL
-- 定義: kijun_odds > 0 AND kijun_odds < 10.0 の馬を本命サイドとする
-- 実行順: Part1 → Part2 → Part3 → Part4
-- Part2 は差分投入可（ON DUPLICATE KEY UPDATE で冪等）。Part3/Part4 は別名テーブルで全件再構築→原子的RENAME。
-- 2026-10-04 方式変更: ファクター効果を「同じ基準オッズ帯の平均複勝払戻を上回った分」で測り、
--   縮小推定(k=300)・コース別細分化なし。詳細は document/指数/本命指数_仕様書.md
-- ============================================================


-- ============================================================
-- Part 1: テーブル定義
-- ============================================================

-- ------------------------------------------------------------
-- 1-1. 本命ファクトテーブル
-- T_KYI × T_BAC × T_CYB × T_UKC × T_SED を結合した非正規化ログ
-- kijun_odds > 0 AND kijun_odds < 10.0 の馬のみ格納
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS T_HONMEI_RACE_LOG (
  course_code            CHAR(2)      NOT NULL COMMENT '場コード',
  year_code              CHAR(2)      NOT NULL COMMENT '年',
  kai                    CHAR(1)      NOT NULL COMMENT '回',
  day_code               CHAR(1)      NOT NULL COMMENT '日',
  race_num               CHAR(2)      NOT NULL COMMENT 'R',
  uma_num                CHAR(2)      NOT NULL COMMENT '馬番',
  ymd                    CHAR(8)      NOT NULL COMMENT '年月日',

  -- レース条件
  tds_code               CHAR(1)               COMMENT '芝ダ 1:芝 2:ダ',
  distance               CHAR(4)               COMMENT '距離',
  class                  CHAR(2)               COMMENT '条件クラス',

  -- 展開系指数順位（予想）
  ten_index_juni         CHAR(2)               COMMENT 'テン指数順位',
  agari_index_juni       CHAR(2)               COMMENT '上がり指数順位',
  ichi_index_juni        CHAR(2)               COMMENT '位置指数順位',
  goal_juni              CHAR(2)               COMMENT 'ゴール順位',
  michunaka_juni         CHAR(2)               COMMENT '道中順位',

  -- 複合展開フラグ（計算済み）
  is_dual_top            TINYINT               COMMENT 'テン≤3 AND 上がり≤3（万能型）',
  is_sen_oki             TINYINT               COMMENT 'テン≥7 AND 上がり≤2（後方一気）',
  is_hana_iki            TINYINT               COMMENT 'テン≤2 AND 上がり≥7（逃げ残り）',
  is_mid_chaser          TINYINT               COMMENT '位置3〜5 AND 上がり≤3（好位差し）',

  -- 指数系
  idm                    CHAR(5)               COMMENT 'IDM',
  joho_index             CHAR(5)               COMMENT '情報指数',
  kyusha_index           CHAR(5)               COMMENT '厩舎指数',
  chokyo_index           CHAR(5)               COMMENT '調教指数',

  -- 馬質・適性系
  kyakushitsu            CHAR(1)               COMMENT '脚質 1:逃 2:先 3:差 4:追',
  joshodo                CHAR(1)               COMMENT '上昇度',
  kyori_tekisei          CHAR(1)               COMMENT '距離適性',

  -- 調教系（T_CYB）
  chokyo_hyoka           CHAR(1)               COMMENT '調教評価 A〜E',

  -- 血統系（T_UKC）
  chichi_keitou_code     CHAR(4)               COMMENT '父系統コード',
  hahachichi_keitou_code CHAR(4)               COMMENT '母父系統コード',

  -- 成績（T_SED）
  finish_order           CHAR(2)               COMMENT '着順',
  ijou_kubun             CHAR(1)               COMMENT '異常区分',
  win_payout             INT                   COMMENT '単勝払戻（円）',
  place_payout           INT                   COMMENT '複勝払戻（円）',

  load_date              CHAR(8)      NOT NULL COMMENT 'ロード日',

  PRIMARY KEY (course_code, year_code, kai, day_code, race_num, uma_num),
  INDEX idx_honmei_log_ymd        (ymd),
  INDEX idx_honmei_log_course_tds (course_code, tds_code, distance)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='本命ファクトテーブル（kijun_odds<10.0）';


-- ------------------------------------------------------------
-- 1-2. 本命ファクター別集計テーブル（EAV形式）
-- course_code/tds_code/dist_band がすべて '' = 全体集計
-- 値あり = コース別集計
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS T_HONMEI_FACTOR_AGG (
  factor_type       VARCHAR(30)  NOT NULL COMMENT 'ファクター種別',
  factor_value      VARCHAR(40)  NOT NULL COMMENT 'ファクター値',
  course_code       CHAR(2)      NOT NULL DEFAULT '' COMMENT '場コード（空=全体）',
  tds_code          CHAR(1)      NOT NULL DEFAULT '' COMMENT '芝ダ（空=全体）',
  dist_band         VARCHAR(10)  NOT NULL DEFAULT '' COMMENT '距離帯（空=全体）',

  total_count       INT          NOT NULL DEFAULT 0,
  win_count         INT          NOT NULL DEFAULT 0,
  place_count       INT          NOT NULL DEFAULT 0,
  win_payout_sum    BIGINT       NOT NULL DEFAULT 0,
  place_payout_sum  BIGINT       NOT NULL DEFAULT 0,
  win_rate          DECIMAL(5,1)          COMMENT '勝率(%)',
  place_rate        DECIMAL(5,1)          COMMENT '複勝率(%)',
  win_recovery      DECIMAL(6,1)          COMMENT '単勝回収率',
  place_recovery    DECIMAL(6,1)          COMMENT '複勝回収率',

  updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                          ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (factor_type, factor_value, course_code, tds_code, dist_band),
  INDEX idx_honmei_agg_type (factor_type, course_code, tds_code, dist_band)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='本命ファクター別集計（EAV）';


-- ------------------------------------------------------------
-- 1-3. 本命指数テーブル（出馬表表示用）
-- 出走全馬対象。kijun_odds < 10.0 の馬のみ意味のある値を持つ。
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS T_HONMEI_SCORE (
  course_code       CHAR(2)      NOT NULL,
  year_code         CHAR(2)      NOT NULL,
  kai               CHAR(1)      NOT NULL,
  day_code          CHAR(1)      NOT NULL,
  race_num          CHAR(2)      NOT NULL,
  uma_num           CHAR(2)      NOT NULL,

  -- 全体本命指数（全データから算出したファクター回収率の偏差合計）
  overall_score     DECIMAL(7,1)          COMMENT '全体本命指数',
  -- コース別本命指数（場+芝ダ+距離帯ごとのファクター回収率偏差合計）
  course_score      DECIMAL(7,1)          COMMENT 'コース別本命指数',

  -- 内訳（デバッグ・説明用）
  score_ten         DECIMAL(5,1)          COMMENT 'テン順位スコア',
  score_agari       DECIMAL(5,1)          COMMENT '上がり順位スコア',
  score_ichi        DECIMAL(5,1)          COMMENT '位置順位スコア',
  score_goal        DECIMAL(5,1)          COMMENT 'ゴール順位スコア',
  score_combo       DECIMAL(5,1)          COMMENT '複合展開スコア',
  score_idm         DECIMAL(5,1)          COMMENT 'IDMスコア',
  score_joho        DECIMAL(5,1)          COMMENT '情報指数スコア',
  score_kyusha      DECIMAL(5,1)          COMMENT '厩舎指数スコア',
  score_chokyo      DECIMAL(5,1)          COMMENT '調教評価スコア',
  score_kyakushitsu DECIMAL(5,1)          COMMENT '脚質スコア',
  score_joshodo     DECIMAL(5,1)          COMMENT '上昇度スコア',
  score_tekisei     DECIMAL(5,1)          COMMENT '適性スコア',
  score_blood       DECIMAL(5,1)          COMMENT '血統スコア',

  -- コース別内訳（course_scoreに対応。コース別データがある5ファクターのみ別列を持つ。
  -- 残り6ファクター(idm/joho/kyusha/chokyo/joshodo/tekisei)はコース別データが存在せず
  -- overall_scoreと同値のため、上のscore_*列をそのまま流用する）
  score_ten_c         DECIMAL(5,1)        COMMENT 'テン順位スコア(コース別)',
  score_agari_c       DECIMAL(5,1)        COMMENT '上がり順位スコア(コース別)',
  score_ichi_c        DECIMAL(5,1)        COMMENT '位置順位スコア(コース別)',
  score_goal_c        DECIMAL(5,1)        COMMENT 'ゴール順位スコア(コース別)',
  score_combo_c       DECIMAL(5,1)        COMMENT '複合展開スコア(コース別)',
  score_kyakushitsu_c DECIMAL(5,1)        COMMENT '脚質スコア(コース別)',
  score_blood_c       DECIMAL(5,1)        COMMENT '血統スコア(コース別)',

  updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                          ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (course_code, year_code, kai, day_code, race_num, uma_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='本命指数（出馬表表示用）';

-- 既存テーブルへのマイグレーション（新規列を追加）
-- MySQLの ALTER TABLE ... ADD COLUMN に IF NOT EXISTS 構文は存在しない（MariaDB専用）ため、
-- INFORMATION_SCHEMA を見て未追加の列だけ動的SQLで追加する（再実行しても安全）。
DELIMITER $$
CREATE PROCEDURE IF NOT EXISTS sp_add_col_if_missing(
  IN p_table VARCHAR(64), IN p_column VARCHAR(64), IN p_def VARCHAR(255)
)
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = p_table AND COLUMN_NAME = p_column
  ) THEN
    SET @ddl = CONCAT('ALTER TABLE ', p_table, ' ADD COLUMN ', p_column, ' ', p_def);
    PREPARE stmt FROM @ddl;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;
  END IF;
END$$
DELIMITER ;

CALL sp_add_col_if_missing('T_HONMEI_SCORE', 'score_ten_c',         "DECIMAL(5,1) COMMENT 'テン順位スコア(コース別)'");
CALL sp_add_col_if_missing('T_HONMEI_SCORE', 'score_agari_c',       "DECIMAL(5,1) COMMENT '上がり順位スコア(コース別)'");
CALL sp_add_col_if_missing('T_HONMEI_SCORE', 'score_ichi_c',        "DECIMAL(5,1) COMMENT '位置順位スコア(コース別)'");
CALL sp_add_col_if_missing('T_HONMEI_SCORE', 'score_goal_c',        "DECIMAL(5,1) COMMENT 'ゴール順位スコア(コース別)'");
CALL sp_add_col_if_missing('T_HONMEI_SCORE', 'score_combo_c',       "DECIMAL(5,1) COMMENT '複合展開スコア(コース別)'");
CALL sp_add_col_if_missing('T_HONMEI_SCORE', 'score_kyakushitsu_c', "DECIMAL(5,1) COMMENT '脚質スコア(コース別)'");
CALL sp_add_col_if_missing('T_HONMEI_SCORE', 'score_blood_c',       "DECIMAL(5,1) COMMENT '血統スコア(コース別)'");
CALL sp_add_col_if_missing('T_HONMEI_FACTOR_AGG', 'excess_dev',    "DECIMAL(8,3) COMMENT '同オッズ帯平均複勝払戻との差の平均×n/(n+300)（2026-10-04新方式）'");

DROP PROCEDURE IF EXISTS sp_add_col_if_missing;


-- ============================================================
-- Part 2: T_HONMEI_RACE_LOG 投入
-- kijun_odds > 0 AND kijun_odds < 10.0 の馬を対象に非正規化ログを作成
-- 芝・ダートのみ（障害除く）、新馬除く
-- 毎日追分実行可（冪等）
-- ============================================================
INSERT INTO T_HONMEI_RACE_LOG (
  course_code, year_code, kai, day_code, race_num, uma_num,
  ymd, tds_code, distance, class,
  ten_index_juni, agari_index_juni, ichi_index_juni, goal_juni, michunaka_juni,
  is_dual_top, is_sen_oki, is_hana_iki, is_mid_chaser,
  idm, joho_index, kyusha_index, chokyo_index,
  kyakushitsu, joshodo, kyori_tekisei,
  chokyo_hyoka,
  chichi_keitou_code, hahachichi_keitou_code,
  finish_order, ijou_kubun, win_payout, place_payout,
  load_date
)
SELECT
  k.course_code, k.year_code, k.kai, k.day_code, k.race_num, k.uma_num,
  b.ymd,
  b.tds_code,
  b.distance,
  b.`class`,
  k.ten_index_juni, k.agari_index_juni, k.ichi_index_juni, k.goal_juni, k.michunaka_juni,
  -- 複合展開フラグ
  (CAST(TRIM(k.ten_index_juni)   AS UNSIGNED) <= 3
   AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 3
   AND TRIM(k.ten_index_juni) <> '' AND TRIM(k.agari_index_juni) <> '')   AS is_dual_top,
  (CAST(TRIM(k.ten_index_juni)   AS UNSIGNED) >= 7
   AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 2
   AND TRIM(k.ten_index_juni) <> '' AND TRIM(k.agari_index_juni) <> '')   AS is_sen_oki,
  (CAST(TRIM(k.ten_index_juni)   AS UNSIGNED) <= 2
   AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) >= 7
   AND TRIM(k.ten_index_juni) <> '' AND TRIM(k.agari_index_juni) <> '')   AS is_hana_iki,
  (CAST(TRIM(k.ichi_index_juni)  AS UNSIGNED) BETWEEN 3 AND 5
   AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 3
   AND TRIM(k.ichi_index_juni) <> '' AND TRIM(k.agari_index_juni) <> '')  AS is_mid_chaser,
  k.idm, k.joho_index, k.kyusha_index, k.chokyo_index,
  k.kyakushitsu, k.joshodo, k.kyori_tekisei,
  c.chokyo_hyoka,
  u.chichi_keitou_code, u.hahachichi_keitou_code,
  s.order_of_finish, s.ijou_kubun,
  CASE WHEN s.ijou_kubun IN ('0','') THEN COALESCE(CAST(TRIM(s.win)   AS UNSIGNED), 0) ELSE 0 END,
  CASE WHEN s.ijou_kubun IN ('0','') THEN COALESCE(CAST(TRIM(s.place) AS UNSIGNED), 0) ELSE 0 END,
  DATE_FORMAT(NOW(), '%Y%m%d')
FROM T_KYI k
INNER JOIN T_BAC b
  ON  b.course_code = k.course_code AND b.year_code = k.year_code
  AND b.kai = k.kai AND b.day_code = k.day_code AND b.race_num = k.race_num
LEFT JOIN T_CYB c
  ON  c.course_code = k.course_code AND c.year_code = k.year_code
  AND c.kai = k.kai AND c.day_code = k.day_code
  AND c.race_num = k.race_num AND c.uma_num = k.uma_num
LEFT JOIN T_UKC u ON u.blood_reg_num = TRIM(k.blood_reg_num)
LEFT JOIN T_SED s
  ON  s.course_code = k.course_code AND s.year_code = k.year_code
  AND s.kai = k.kai AND s.day_code = k.day_code
  AND s.race_num = k.race_num AND s.umaban = k.uma_num
WHERE TRIM(b.tds_code) IN ('1', '2')
  AND TRIM(b.`class`) <> 'A1'
  AND TRIM(k.kijun_odds) <> ''
  AND CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1)) > 0
  AND CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1)) < 10.0
ON DUPLICATE KEY UPDATE
  finish_order           = VALUES(finish_order),
  ijou_kubun             = VALUES(ijou_kubun),
  win_payout             = VALUES(win_payout),
  place_payout           = VALUES(place_payout),
  is_dual_top            = VALUES(is_dual_top),
  is_sen_oki             = VALUES(is_sen_oki),
  is_hana_iki            = VALUES(is_hana_iki),
  is_mid_chaser          = VALUES(is_mid_chaser),
  load_date              = VALUES(load_date);


-- ============================================================
-- Part 3: T_HONMEI_FACTOR_AGG 集計（2026-10-04 方式変更）
--
-- 【新方式】各ファクター値について「同じ基準オッズ帯の馬の平均複勝払戻を、どれだけ上回ったか」
--   (excess) の平均を求め、サンプル数で縮小推定した値を excess_dev に保存する。
--     excess  = 複勝払戻 − 同じオッズ帯(~1.5/1.5-2/2-2.5/2.5-3/3-4/4-5/5-7/7-10倍)の平均複勝払戻
--     excess_dev = AVG(excess) × n / (n + 300)
--   旧方式（単勝回収率の偏差・コース×芝ダ×距離帯の細分化）は walk-forward 検証で
--   上位帯の複勝上乗せがほぼ無かったため廃止。根拠: python/research/honmei_improve_wf.py、
--   document/指数/本命指数_仕様書.md。
--   調教ファクターは旧方式で「集計=T_CYB.chokyo_hyoka／採点=T_KYI.chokyo_yajirushi」と
--   別項目を照合していた不具合があったため、集計・採点とも chokyo_yajirushi に統一。
--
-- 書き込みは別名テーブル(_NEW)で構築 → 原子的RENAME（CLAUDE.md「指数/スコアETL実装時の必須チェック」2番）
-- ============================================================

DROP TABLE IF EXISTS T_HONMEI_HM_WORK;
CREATE TABLE T_HONMEI_HM_WORK AS
SELECT
  w.*,
  w.place_payout - AVG(w.place_payout) OVER (PARTITION BY w.odds_band) AS excess
FROM (
  SELECT
    CAST(TRIM(l.finish_order) AS UNSIGNED) AS fin,
    l.win_payout, l.place_payout,
    CASE
      WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1)) < 1.5 THEN '0-1.5'
      WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1)) < 2   THEN '1.5-2'
      WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1)) < 2.5 THEN '2-2.5'
      WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1)) < 3   THEN '2.5-3'
      WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1)) < 4   THEN '3-4'
      WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1)) < 5   THEN '4-5'
      WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1)) < 7   THEN '5-7'
      ELSE '7-10'
    END AS odds_band,
    -- 順位系: 1 / 2~3 / 4~6 / 7~ / NA(空欄・0)
    CASE WHEN CAST(TRIM(l.ten_index_juni) AS UNSIGNED) = 1 THEN '1'
         WHEN CAST(TRIM(l.ten_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
         WHEN CAST(TRIM(l.ten_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
         WHEN CAST(TRIM(l.ten_index_juni) AS UNSIGNED) >= 7 THEN '7~' ELSE 'NA' END AS fv_ten,
    CASE WHEN CAST(TRIM(l.agari_index_juni) AS UNSIGNED) = 1 THEN '1'
         WHEN CAST(TRIM(l.agari_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
         WHEN CAST(TRIM(l.agari_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
         WHEN CAST(TRIM(l.agari_index_juni) AS UNSIGNED) >= 7 THEN '7~' ELSE 'NA' END AS fv_agari,
    CASE WHEN CAST(TRIM(l.ichi_index_juni) AS UNSIGNED) = 1 THEN '1'
         WHEN CAST(TRIM(l.ichi_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
         WHEN CAST(TRIM(l.ichi_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
         WHEN CAST(TRIM(l.ichi_index_juni) AS UNSIGNED) >= 7 THEN '7~' ELSE 'NA' END AS fv_ichi,
    CASE WHEN CAST(TRIM(l.goal_juni) AS UNSIGNED) = 1 THEN '1'
         WHEN CAST(TRIM(l.goal_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
         WHEN CAST(TRIM(l.goal_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
         WHEN CAST(TRIM(l.goal_juni) AS UNSIGNED) >= 7 THEN '7~' ELSE 'NA' END AS fv_goal,
    CASE WHEN l.is_dual_top = 1 THEN 'dual_top' WHEN l.is_sen_oki = 1 THEN 'sen_oki'
         WHEN l.is_hana_iki = 1 THEN 'hana_iki' WHEN l.is_mid_chaser = 1 THEN 'mid_chaser'
         ELSE 'other' END AS fv_combo,
    CASE WHEN TRIM(l.idm) = '' OR l.idm IS NULL OR CAST(TRIM(l.idm) AS DECIMAL(6,1)) <= 0 THEN 'NA'
         WHEN CAST(TRIM(l.idm) AS DECIMAL(6,1)) < 30 THEN '~30'
         WHEN CAST(TRIM(l.idm) AS DECIMAL(6,1)) < 40 THEN '30~40'
         WHEN CAST(TRIM(l.idm) AS DECIMAL(6,1)) < 50 THEN '40~50'
         WHEN CAST(TRIM(l.idm) AS DECIMAL(6,1)) < 60 THEN '50~60'
         WHEN CAST(TRIM(l.idm) AS DECIMAL(6,1)) < 70 THEN '60~70' ELSE '70~' END AS fv_idm,
    CASE WHEN l.joho_index IS NULL OR TRIM(l.joho_index) = '' OR CAST(TRIM(l.joho_index) AS DECIMAL(6,1)) < 0 THEN 'NA'
         WHEN CAST(TRIM(l.joho_index) AS DECIMAL(6,1)) < 30 THEN '~30'
         WHEN CAST(TRIM(l.joho_index) AS DECIMAL(6,1)) < 50 THEN '30~50'
         WHEN CAST(TRIM(l.joho_index) AS DECIMAL(6,1)) < 70 THEN '50~70' ELSE '70~' END AS fv_joho,
    CASE WHEN l.kyusha_index IS NULL OR TRIM(l.kyusha_index) = '' OR CAST(TRIM(l.kyusha_index) AS DECIMAL(6,1)) <= 0 THEN 'NA'
         WHEN CAST(TRIM(l.kyusha_index) AS DECIMAL(6,1)) < 20 THEN '~20'
         WHEN CAST(TRIM(l.kyusha_index) AS DECIMAL(6,1)) < 30 THEN '20~30'
         WHEN CAST(TRIM(l.kyusha_index) AS DECIMAL(6,1)) < 40 THEN '30~40' ELSE '40~' END AS fv_kyu,
    COALESCE(NULLIF(TRIM(k.chokyo_yajirushi), ''), 'NA')        AS fv_chk,
    COALESCE(NULLIF(TRIM(l.kyakushitsu), ''), 'NA')             AS fv_kya,
    COALESCE(NULLIF(TRIM(l.joshodo), ''), 'NA')                 AS fv_jos,
    COALESCE(NULLIF(TRIM(l.kyori_tekisei), ''), 'NA')           AS fv_kyo,
    COALESCE(NULLIF(TRIM(l.chichi_keitou_code), ''), 'NA')      AS fv_chi,
    COALESCE(NULLIF(TRIM(l.hahachichi_keitou_code), ''), 'NA')  AS fv_hah
  FROM T_HONMEI_RACE_LOG l
  INNER JOIN T_KYI k
    ON  k.course_code = l.course_code AND k.year_code = l.year_code AND k.kai = l.kai
    AND k.day_code = l.day_code AND k.race_num = l.race_num AND k.uma_num = l.uma_num
  WHERE l.finish_order IS NOT NULL AND l.ijou_kubun IN ('0','')
    AND TRIM(k.kijun_odds) <> ''
    AND CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1)) > 0
    AND CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1)) < 10
) w;

DROP TABLE IF EXISTS T_HONMEI_FACTOR_AGG_NEW;
CREATE TABLE T_HONMEI_FACTOR_AGG_NEW LIKE T_HONMEI_FACTOR_AGG;

INSERT INTO T_HONMEI_FACTOR_AGG_NEW
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery, excess_dev)
SELECT ft, fv, '', '', '',
  COUNT(*), SUM(fin = 1), SUM(fin BETWEEN 1 AND 3), SUM(win_payout), SUM(place_payout),
  ROUND(SUM(fin = 1) / COUNT(*) * 100, 1), ROUND(SUM(fin BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout) / COUNT(*), 1), ROUND(SUM(place_payout) / COUNT(*), 1),
  ROUND(AVG(excess) * COUNT(*) / (COUNT(*) + 300), 3)
FROM (
            SELECT 'ten_rank'          AS ft, fv_ten   AS fv, fin, win_payout, place_payout, excess FROM T_HONMEI_HM_WORK
  UNION ALL SELECT 'agari_rank',             fv_agari,      fin, win_payout, place_payout, excess FROM T_HONMEI_HM_WORK
  UNION ALL SELECT 'ichi_rank',              fv_ichi,       fin, win_payout, place_payout, excess FROM T_HONMEI_HM_WORK
  UNION ALL SELECT 'goal_rank',              fv_goal,       fin, win_payout, place_payout, excess FROM T_HONMEI_HM_WORK
  UNION ALL SELECT 'tenkai_combo',           fv_combo,      fin, win_payout, place_payout, excess FROM T_HONMEI_HM_WORK
  UNION ALL SELECT 'idm_band',               fv_idm,        fin, win_payout, place_payout, excess FROM T_HONMEI_HM_WORK
  UNION ALL SELECT 'joho_band',              fv_joho,        fin, win_payout, place_payout, excess FROM T_HONMEI_HM_WORK
  UNION ALL SELECT 'kyusha_band',            fv_kyu,        fin, win_payout, place_payout, excess FROM T_HONMEI_HM_WORK
  UNION ALL SELECT 'chokyo_yajirushi',       fv_chk,        fin, win_payout, place_payout, excess FROM T_HONMEI_HM_WORK
  UNION ALL SELECT 'kyakushitsu',            fv_kya,        fin, win_payout, place_payout, excess FROM T_HONMEI_HM_WORK
  UNION ALL SELECT 'joshodo',                fv_jos,        fin, win_payout, place_payout, excess FROM T_HONMEI_HM_WORK
  UNION ALL SELECT 'kyori_tekisei',          fv_kyo,        fin, win_payout, place_payout, excess FROM T_HONMEI_HM_WORK
  UNION ALL SELECT 'chichi_keitou',          fv_chi,        fin, win_payout, place_payout, excess FROM T_HONMEI_HM_WORK
  UNION ALL SELECT 'hahachichi_keitou',      fv_hah,        fin, win_payout, place_payout, excess FROM T_HONMEI_HM_WORK
) u
GROUP BY ft, fv;

-- 参考用の全体ベースライン行（新方式のスコア計算には使わない。excess の全体平均は定義上0）
INSERT INTO T_HONMEI_FACTOR_AGG_NEW
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery, excess_dev)
SELECT 'baseline', 'all', '', '', '',
  COUNT(*), SUM(fin = 1), SUM(fin BETWEEN 1 AND 3), SUM(win_payout), SUM(place_payout),
  ROUND(SUM(fin = 1) / COUNT(*) * 100, 1), ROUND(SUM(fin BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout) / COUNT(*), 1), ROUND(SUM(place_payout) / COUNT(*), 1), 0
FROM T_HONMEI_HM_WORK;

DROP TABLE IF EXISTS T_HONMEI_FACTOR_AGG_OLD;
RENAME TABLE T_HONMEI_FACTOR_AGG TO T_HONMEI_FACTOR_AGG_OLD, T_HONMEI_FACTOR_AGG_NEW TO T_HONMEI_FACTOR_AGG;
DROP TABLE T_HONMEI_FACTOR_AGG_OLD;
DROP TABLE IF EXISTS T_HONMEI_HM_WORK;


-- ============================================================
-- Part 4: T_HONMEI_SCORE 計算（2026-10-04 方式変更）
--
-- 生スコア(raw) = 14ファクターの excess_dev の合計（該当値が無いファクターは0）
-- 表示スコア    = raw を旧本命指数と同じ目盛りに換算した値（折れ線換算）
--   換算点: raw 0.19→0 / 2.61→10 / 6.56→30 / 9.73→50（両端は隣の区間の傾きで延長）
--   換算点は「2024-2026年に旧本命指数がその値以上だった馬の割合」と新スコアで同じ割合になる値。
--   これにより sc・推奨印の軸候補・分析画面等のしきい値（0/10/30/50）が「同じ割合の上位馬」を指す。
-- overall_score と course_score は同じ値（新方式はコース別の細分化を行わない）。
-- score_* 列は各ファクターの excess_dev（換算前の生の値）。合計は raw と一致し、表示スコアとは一致しない。
-- 対象: T_KYI 全馬（芝ダ。結果テーブルには依存しない＝出走前レースにも付与される）
-- 書き込みは別名テーブル(_NEW)で構築 → 原子的RENAME
-- ============================================================
DROP TABLE IF EXISTS T_HONMEI_SCORE_NEW;
CREATE TABLE T_HONMEI_SCORE_NEW LIKE T_HONMEI_SCORE;

INSERT INTO T_HONMEI_SCORE_NEW (
  course_code, year_code, kai, day_code, race_num, uma_num,
  overall_score, course_score,
  score_ten, score_agari, score_ichi, score_goal, score_combo,
  score_idm, score_joho, score_kyusha, score_chokyo,
  score_kyakushitsu, score_joshodo, score_tekisei, score_blood,
  score_ten_c, score_agari_c, score_ichi_c, score_goal_c, score_combo_c,
  score_kyakushitsu_c, score_blood_c
)
SELECT
  r.course_code, r.year_code, r.kai, r.day_code, r.race_num, r.uma_num,
  ROUND(CASE
    WHEN r.raw < 2.61 THEN (r.raw - 0.19) * (10 / 2.42)
    WHEN r.raw < 6.56 THEN 10 + (r.raw - 2.61) * (20 / 3.95)
    WHEN r.raw < 9.73 THEN 30 + (r.raw - 6.56) * (20 / 3.17)
    ELSE 50 + (r.raw - 9.73) * (20 / 3.17)
  END, 1) AS overall_score,
  ROUND(CASE
    WHEN r.raw < 2.61 THEN (r.raw - 0.19) * (10 / 2.42)
    WHEN r.raw < 6.56 THEN 10 + (r.raw - 2.61) * (20 / 3.95)
    WHEN r.raw < 9.73 THEN 30 + (r.raw - 6.56) * (20 / 3.17)
    ELSE 50 + (r.raw - 9.73) * (20 / 3.17)
  END, 1) AS course_score,
  ROUND(r.d_ten, 1), ROUND(r.d_agari, 1), ROUND(r.d_ichi, 1), ROUND(r.d_goal, 1), ROUND(r.d_combo, 1),
  ROUND(r.d_idm, 1), ROUND(r.d_joho, 1), ROUND(r.d_kyu, 1), ROUND(r.d_chk, 1),
  ROUND(r.d_kya, 1), ROUND(r.d_jos, 1), ROUND(r.d_kyo, 1), ROUND(r.d_chi + r.d_hah, 1),
  ROUND(r.d_ten, 1), ROUND(r.d_agari, 1), ROUND(r.d_ichi, 1), ROUND(r.d_goal, 1), ROUND(r.d_combo, 1),
  ROUND(r.d_kya, 1), ROUND(r.d_chi + r.d_hah, 1)
FROM (
  SELECT x.*,
    x.d_ten + x.d_agari + x.d_ichi + x.d_goal + x.d_combo + x.d_idm + x.d_joho + x.d_kyu
      + x.d_chk + x.d_kya + x.d_jos + x.d_kyo + x.d_chi + x.d_hah AS raw
  FROM (
    SELECT s.course_code, s.year_code, s.kai, s.day_code, s.race_num, s.uma_num,
      COALESCE(a1.excess_dev, 0)  AS d_ten,   COALESCE(a2.excess_dev, 0)  AS d_agari,
      COALESCE(a3.excess_dev, 0)  AS d_ichi,  COALESCE(a4.excess_dev, 0)  AS d_goal,
      COALESCE(a5.excess_dev, 0)  AS d_combo, COALESCE(a6.excess_dev, 0)  AS d_idm,
      COALESCE(a7.excess_dev, 0)  AS d_joho,  COALESCE(a8.excess_dev, 0)  AS d_kyu,
      COALESCE(a9.excess_dev, 0)  AS d_chk,   COALESCE(a10.excess_dev, 0) AS d_kya,
      COALESCE(a11.excess_dev, 0) AS d_jos,   COALESCE(a12.excess_dev, 0) AS d_kyo,
      COALESCE(a13.excess_dev, 0) AS d_chi,   COALESCE(a14.excess_dev, 0) AS d_hah
    FROM (
      SELECT k.course_code, k.year_code, k.kai, k.day_code, k.race_num, k.uma_num,
        CASE WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) = 1 THEN '1'
             WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
             WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
             WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) >= 7 THEN '7~' ELSE 'NA' END AS fv_ten,
        CASE WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) = 1 THEN '1'
             WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
             WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
             WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) >= 7 THEN '7~' ELSE 'NA' END AS fv_agari,
        CASE WHEN CAST(TRIM(k.ichi_index_juni) AS UNSIGNED) = 1 THEN '1'
             WHEN CAST(TRIM(k.ichi_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
             WHEN CAST(TRIM(k.ichi_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
             WHEN CAST(TRIM(k.ichi_index_juni) AS UNSIGNED) >= 7 THEN '7~' ELSE 'NA' END AS fv_ichi,
        CASE WHEN CAST(TRIM(k.goal_juni) AS UNSIGNED) = 1 THEN '1'
             WHEN CAST(TRIM(k.goal_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
             WHEN CAST(TRIM(k.goal_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
             WHEN CAST(TRIM(k.goal_juni) AS UNSIGNED) >= 7 THEN '7~' ELSE 'NA' END AS fv_goal,
        -- 複合展開（Part2 の is_* フラグと同じ定義）
        CASE
          WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) <= 3 AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 3
               AND TRIM(k.ten_index_juni) <> '' AND TRIM(k.agari_index_juni) <> '' THEN 'dual_top'
          WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) >= 7 AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 2
               AND TRIM(k.ten_index_juni) <> '' AND TRIM(k.agari_index_juni) <> '' THEN 'sen_oki'
          WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) <= 2 AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) >= 7
               AND TRIM(k.ten_index_juni) <> '' AND TRIM(k.agari_index_juni) <> '' THEN 'hana_iki'
          WHEN CAST(TRIM(k.ichi_index_juni) AS UNSIGNED) BETWEEN 3 AND 5 AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 3
               AND TRIM(k.ichi_index_juni) <> '' AND TRIM(k.agari_index_juni) <> '' THEN 'mid_chaser'
          ELSE 'other' END AS fv_combo,
        CASE WHEN TRIM(k.idm) = '' OR k.idm IS NULL OR CAST(TRIM(k.idm) AS DECIMAL(6,1)) <= 0 THEN 'NA'
             WHEN CAST(TRIM(k.idm) AS DECIMAL(6,1)) < 30 THEN '~30'
             WHEN CAST(TRIM(k.idm) AS DECIMAL(6,1)) < 40 THEN '30~40'
             WHEN CAST(TRIM(k.idm) AS DECIMAL(6,1)) < 50 THEN '40~50'
             WHEN CAST(TRIM(k.idm) AS DECIMAL(6,1)) < 60 THEN '50~60'
             WHEN CAST(TRIM(k.idm) AS DECIMAL(6,1)) < 70 THEN '60~70' ELSE '70~' END AS fv_idm,
        CASE WHEN k.joho_index IS NULL OR TRIM(k.joho_index) = '' OR CAST(TRIM(k.joho_index) AS DECIMAL(6,1)) < 0 THEN 'NA'
             WHEN CAST(TRIM(k.joho_index) AS DECIMAL(6,1)) < 30 THEN '~30'
             WHEN CAST(TRIM(k.joho_index) AS DECIMAL(6,1)) < 50 THEN '30~50'
             WHEN CAST(TRIM(k.joho_index) AS DECIMAL(6,1)) < 70 THEN '50~70' ELSE '70~' END AS fv_joho,
        CASE WHEN k.kyusha_index IS NULL OR TRIM(k.kyusha_index) = '' OR CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) <= 0 THEN 'NA'
             WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) < 20 THEN '~20'
             WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) < 30 THEN '20~30'
             WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) < 40 THEN '30~40' ELSE '40~' END AS fv_kyu,
        COALESCE(NULLIF(TRIM(k.chokyo_yajirushi), ''), 'NA')          AS fv_chk,
        COALESCE(NULLIF(TRIM(k.kyakushitsu), ''), 'NA')               AS fv_kya,
        COALESCE(NULLIF(TRIM(k.joshodo), ''), 'NA')                   AS fv_jos,
        COALESCE(NULLIF(TRIM(k.kyori_tekisei), ''), 'NA')             AS fv_kyo,
        COALESCE(NULLIF(TRIM(u.chichi_keitou_code), ''), 'NA')        AS fv_chi,
        COALESCE(NULLIF(TRIM(u.hahachichi_keitou_code), ''), 'NA')    AS fv_hah
      FROM T_KYI k
      INNER JOIN T_BAC b
        ON  b.course_code = k.course_code AND b.year_code = k.year_code
        AND b.kai = k.kai AND b.day_code = k.day_code AND b.race_num = k.race_num
      LEFT JOIN T_UKC u ON u.blood_reg_num = TRIM(k.blood_reg_num)
      WHERE TRIM(b.tds_code) IN ('1','2')
    ) s
    LEFT JOIN T_HONMEI_FACTOR_AGG a1  ON a1.factor_type  = 'ten_rank'          AND a1.factor_value  = s.fv_ten
    LEFT JOIN T_HONMEI_FACTOR_AGG a2  ON a2.factor_type  = 'agari_rank'        AND a2.factor_value  = s.fv_agari
    LEFT JOIN T_HONMEI_FACTOR_AGG a3  ON a3.factor_type  = 'ichi_rank'         AND a3.factor_value  = s.fv_ichi
    LEFT JOIN T_HONMEI_FACTOR_AGG a4  ON a4.factor_type  = 'goal_rank'         AND a4.factor_value  = s.fv_goal
    LEFT JOIN T_HONMEI_FACTOR_AGG a5  ON a5.factor_type  = 'tenkai_combo'      AND a5.factor_value  = s.fv_combo
    LEFT JOIN T_HONMEI_FACTOR_AGG a6  ON a6.factor_type  = 'idm_band'          AND a6.factor_value  = s.fv_idm
    LEFT JOIN T_HONMEI_FACTOR_AGG a7  ON a7.factor_type  = 'joho_band'         AND a7.factor_value  = s.fv_joho
    LEFT JOIN T_HONMEI_FACTOR_AGG a8  ON a8.factor_type  = 'kyusha_band'       AND a8.factor_value  = s.fv_kyu
    LEFT JOIN T_HONMEI_FACTOR_AGG a9  ON a9.factor_type  = 'chokyo_yajirushi'  AND a9.factor_value  = s.fv_chk
    LEFT JOIN T_HONMEI_FACTOR_AGG a10 ON a10.factor_type = 'kyakushitsu'       AND a10.factor_value = s.fv_kya
    LEFT JOIN T_HONMEI_FACTOR_AGG a11 ON a11.factor_type = 'joshodo'           AND a11.factor_value = s.fv_jos
    LEFT JOIN T_HONMEI_FACTOR_AGG a12 ON a12.factor_type = 'kyori_tekisei'     AND a12.factor_value = s.fv_kyo
    LEFT JOIN T_HONMEI_FACTOR_AGG a13 ON a13.factor_type = 'chichi_keitou'     AND a13.factor_value = s.fv_chi
    LEFT JOIN T_HONMEI_FACTOR_AGG a14 ON a14.factor_type = 'hahachichi_keitou' AND a14.factor_value = s.fv_hah
  ) x
) r;

-- カバレッジ整合性チェック（芝ダの出走予定馬全頭に行があるか。差が0件であること）
SELECT
  (SELECT COUNT(*) FROM T_KYI k INNER JOIN T_BAC b
     ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai
    AND b.day_code=k.day_code AND b.race_num=k.race_num
   WHERE TRIM(b.tds_code) IN ('1','2')) AS target_cnt,
  (SELECT COUNT(*) FROM T_HONMEI_SCORE_NEW) AS scored_cnt;

DROP TABLE IF EXISTS T_HONMEI_SCORE_OLD;
RENAME TABLE T_HONMEI_SCORE TO T_HONMEI_SCORE_OLD, T_HONMEI_SCORE_NEW TO T_HONMEI_SCORE;
DROP TABLE T_HONMEI_SCORE_OLD;
