-- ============================================================
-- 穴馬指数 ETL
-- 定義: kijun_odds >= 10.0 の馬を穴馬とする
-- 実行順: Part1 → Part2 → Part3 → Part4
-- Part2〜4 は差分投入可（ON DUPLICATE KEY UPDATE で冪等）
-- ============================================================


-- ============================================================
-- Part 1: テーブル定義
-- ============================================================

-- ------------------------------------------------------------
-- 1-1. 穴馬ファクトテーブル
-- T_KYI × T_BAC × T_CYB × T_UKC × T_SED を結合した非正規化ログ
-- kijun_odds >= 10.0 の馬のみ格納
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS T_ANABA_RACE_LOG (
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
  gekiso_index           CHAR(3)               COMMENT '激走指数',
  gekiso_juni            CHAR(2)               COMMENT '激走順位',
  manbaken_index         CHAR(3)               COMMENT '万券指数',
  manbaken_in            CHAR(1)               COMMENT '万券印',
  joho_index             CHAR(5)               COMMENT '情報指数',
  chokyo_index           CHAR(5)               COMMENT '調教指数',
  kyusha_index           CHAR(5)               COMMENT '厩舎指数',

  -- 馬質・適性系
  kyakushitsu            CHAR(1)               COMMENT '脚質 1:逃 2:先 3:差 4:追',
  joshodo                CHAR(1)               COMMENT '上昇度',
  kyori_tekisei          CHAR(1)               COMMENT '距離適性',
  omo_tekisei            CHAR(1)               COMMENT '重適正',
  shiba_tekisei          CHAR(1)               COMMENT '芝適性',
  dirt_tekisei           CHAR(1)               COMMENT 'ダ適性',
  hohbokusaki_rank       CHAR(1)               COMMENT '放牧先ランク',
  kyusha_rank            CHAR(1)               COMMENT '厩舎ランク',
  nyukyu_hashiri         CHAR(2)               COMMENT '入厩何走目',

  -- 調教系（T_CYB）
  oi_index               CHAR(3)               COMMENT '追切指数',
  shiage_index           CHAR(3)               COMMENT '仕上指数',
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
  INDEX idx_anaba_log_ymd        (ymd),
  INDEX idx_anaba_log_course_tds (course_code, tds_code, distance)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='穴馬ファクトテーブル（kijun_odds>=10.0）';


-- ------------------------------------------------------------
-- 1-2. 穴馬ファクター別集計テーブル（EAV形式）
-- course_code/tds_code/dist_band がすべて '' = 全体集計
-- 値あり = コース別集計
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS T_ANABA_FACTOR_AGG (
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
  INDEX idx_anaba_agg_type (factor_type, course_code, tds_code, dist_band)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='穴馬ファクター別集計（EAV）';


-- ------------------------------------------------------------
-- 1-3. 穴馬指数テーブル（出馬表表示用）
-- 出走全馬対象。kijun_odds >= 10.0 の馬のみ意味のある値を持つ。
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS T_ANABA_SCORE (
  course_code       CHAR(2)      NOT NULL,
  year_code         CHAR(2)      NOT NULL,
  kai               CHAR(1)      NOT NULL,
  day_code          CHAR(1)      NOT NULL,
  race_num          CHAR(2)      NOT NULL,
  uma_num           CHAR(2)      NOT NULL,

  -- 全体穴馬指数（全データから算出したファクター回収率の偏差合計）
  overall_score     DECIMAL(7,1)          COMMENT '全体穴馬指数',
  -- コース別穴馬指数（場+芝ダ+距離帯ごとのファクター回収率偏差合計）
  course_score      DECIMAL(7,1)          COMMENT 'コース別穴馬指数',

  -- 内訳（デバッグ・説明用）
  score_ten         DECIMAL(5,1)          COMMENT 'テン順位スコア',
  score_agari       DECIMAL(5,1)          COMMENT '上がり順位スコア',
  score_ichi        DECIMAL(5,1)          COMMENT '位置順位スコア',
  score_goal        DECIMAL(5,1)          COMMENT 'ゴール順位スコア',
  score_combo       DECIMAL(5,1)          COMMENT '複合展開スコア',
  score_idm         DECIMAL(5,1)          COMMENT 'IDMスコア',
  score_gekiso      DECIMAL(5,1)          COMMENT '激走指数スコア',
  score_manbaken    DECIMAL(5,1)          COMMENT '万券指数スコア',
  score_chokyo      DECIMAL(5,1)          COMMENT '調教評価スコア',
  score_kyusha      DECIMAL(5,1)          COMMENT '厩舎指数スコア',
  score_kyakushitsu DECIMAL(5,1)          COMMENT '脚質スコア',
  score_joshodo     DECIMAL(5,1)          COMMENT '上昇度スコア',
  score_tekisei     DECIMAL(5,1)          COMMENT '適性スコア',
  score_blood       DECIMAL(5,1)          COMMENT '血統スコア',

  updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                          ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (course_code, year_code, kai, day_code, race_num, uma_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='穴馬指数（出馬表表示用）';


-- ============================================================
-- Part 2: T_ANABA_RACE_LOG 投入
-- kijun_odds >= 10.0 の馬を対象に非正規化ログを作成
-- 芝・ダートのみ（障害除く）、新馬除く
-- 毎日追分実行可（冪等）
-- ============================================================
INSERT INTO T_ANABA_RACE_LOG (
  course_code, year_code, kai, day_code, race_num, uma_num,
  ymd, tds_code, distance, class,
  ten_index_juni, agari_index_juni, ichi_index_juni, goal_juni, michunaka_juni,
  is_dual_top, is_sen_oki, is_hana_iki, is_mid_chaser,
  idm, gekiso_index, gekiso_juni, manbaken_index, manbaken_in,
  joho_index, chokyo_index, kyusha_index,
  kyakushitsu, joshodo, kyori_tekisei, omo_tekisei,
  shiba_tekisei, dirt_tekisei, hohbokusaki_rank, kyusha_rank, nyukyu_hashiri,
  oi_index, shiage_index, chokyo_hyoka,
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
  k.idm, k.gekiso_index, k.gekiso_juni, k.manbaken_index, k.manbaken_in,
  k.joho_index, k.chokyo_index, k.kyusha_index,
  k.kyakushitsu, k.joshodo, k.kyori_tekisei, k.omo_tekisei,
  k.shiba_tekisei, k.dirt_tekisei, k.hohbokusaki_rank, k.kyusha_rank, k.nyukyu_hashiri,
  c.oi_index, c.shiage_index, c.chokyo_hyoka,
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
  AND CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1)) >= 10.0
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
-- Part 3: T_ANABA_FACTOR_AGG 集計
-- 成績が存在し正常完走したレコードのみ対象
-- 全体集計（course_code='' tds_code='' dist_band=''）と
-- コース別集計（course_code/tds_code/dist_band を指定）を両方投入する
-- ============================================================

-- 共通マクロ代わりの注記:
--   fin1 = finish_order が '1'
--   fin3 = finish_order が '1'〜'3'
--   対象条件: finish_order IS NOT NULL AND ijou_kubun IN ('0','')

-- ── ベースライン（全体・全穴馬の回収率）────────────────────────────
-- factor_value = 'all' の1行のみ。他ファクターのスコア計算の基準値になる。
INSERT INTO T_ANABA_FACTOR_AGG
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
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);

-- ── コース別ベースライン ────────────────────────────────────────────
INSERT INTO T_ANABA_FACTOR_AGG
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
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
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


-- ── ヘルパーマクロ（各ファクターで繰り返す集計パターン）────────────
-- 各ブロックは全体集計とコース別集計の2つのINSERTで構成される
-- 全体: course_code='', tds_code='', dist_band=''
-- コース別: 実際の値を使用

-- ── 3-1. テン指数順位 ────────────────────────────────────────────────
INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'ten_rank',
  CASE
    WHEN CAST(TRIM(ten_index_juni) AS UNSIGNED) = 1             THEN '1'
    WHEN CAST(TRIM(ten_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
    WHEN CAST(TRIM(ten_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
    ELSE '7~'
  END AS factor_value,
  '', '', '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(ten_index_juni) <> '' AND CAST(TRIM(ten_index_juni) AS UNSIGNED) > 0
GROUP BY factor_value
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);

INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'ten_rank',
  CASE
    WHEN CAST(TRIM(ten_index_juni) AS UNSIGNED) = 1             THEN '1'
    WHEN CAST(TRIM(ten_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
    WHEN CAST(TRIM(ten_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
    ELSE '7~'
  END AS factor_value,
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
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(ten_index_juni) <> '' AND CAST(TRIM(ten_index_juni) AS UNSIGNED) > 0
  AND TRIM(distance) <> ''
GROUP BY course_code, tds_code, dist_band, factor_value
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ── 3-2. 上がり指数順位 ──────────────────────────────────────────────
INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'agari_rank',
  CASE
    WHEN CAST(TRIM(agari_index_juni) AS UNSIGNED) = 1             THEN '1'
    WHEN CAST(TRIM(agari_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
    WHEN CAST(TRIM(agari_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
    ELSE '7~'
  END AS factor_value,
  '', '', '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(agari_index_juni) <> '' AND CAST(TRIM(agari_index_juni) AS UNSIGNED) > 0
GROUP BY factor_value
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);

INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'agari_rank',
  CASE
    WHEN CAST(TRIM(agari_index_juni) AS UNSIGNED) = 1             THEN '1'
    WHEN CAST(TRIM(agari_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
    WHEN CAST(TRIM(agari_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
    ELSE '7~'
  END AS factor_value,
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
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(agari_index_juni) <> '' AND CAST(TRIM(agari_index_juni) AS UNSIGNED) > 0
  AND TRIM(distance) <> ''
GROUP BY course_code, tds_code, dist_band, factor_value
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ── 3-3. 位置指数順位 ────────────────────────────────────────────────
INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'ichi_rank',
  CASE
    WHEN CAST(TRIM(ichi_index_juni) AS UNSIGNED) = 1             THEN '1'
    WHEN CAST(TRIM(ichi_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
    WHEN CAST(TRIM(ichi_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
    ELSE '7~'
  END AS factor_value,
  '', '', '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(ichi_index_juni) <> '' AND CAST(TRIM(ichi_index_juni) AS UNSIGNED) > 0
GROUP BY factor_value
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);

INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'ichi_rank',
  CASE
    WHEN CAST(TRIM(ichi_index_juni) AS UNSIGNED) = 1             THEN '1'
    WHEN CAST(TRIM(ichi_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
    WHEN CAST(TRIM(ichi_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
    ELSE '7~'
  END AS factor_value,
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
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(ichi_index_juni) <> '' AND CAST(TRIM(ichi_index_juni) AS UNSIGNED) > 0
  AND TRIM(distance) <> ''
GROUP BY course_code, tds_code, dist_band, factor_value
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ── 3-4. ゴール順位 ──────────────────────────────────────────────────
INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'goal_rank',
  CASE
    WHEN CAST(TRIM(goal_juni) AS UNSIGNED) = 1             THEN '1'
    WHEN CAST(TRIM(goal_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
    WHEN CAST(TRIM(goal_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
    ELSE '7~'
  END AS factor_value,
  '', '', '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(goal_juni) <> '' AND CAST(TRIM(goal_juni) AS UNSIGNED) > 0
GROUP BY factor_value
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);

INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'goal_rank',
  CASE
    WHEN CAST(TRIM(goal_juni) AS UNSIGNED) = 1             THEN '1'
    WHEN CAST(TRIM(goal_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
    WHEN CAST(TRIM(goal_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
    ELSE '7~'
  END AS factor_value,
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
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(goal_juni) <> '' AND CAST(TRIM(goal_juni) AS UNSIGNED) > 0
  AND TRIM(distance) <> ''
GROUP BY course_code, tds_code, dist_band, factor_value
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ── 3-5. 複合展開パターン ────────────────────────────────────────────
-- factor_value: 'dual_top' / 'sen_oki' / 'hana_iki' / 'mid_chaser' / 'other'
INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'tenkai_combo',
  CASE
    WHEN is_dual_top   = 1 THEN 'dual_top'
    WHEN is_sen_oki    = 1 THEN 'sen_oki'
    WHEN is_hana_iki   = 1 THEN 'hana_iki'
    WHEN is_mid_chaser = 1 THEN 'mid_chaser'
    ELSE 'other'
  END AS factor_value,
  '', '', '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
GROUP BY factor_value
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);

INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'tenkai_combo',
  CASE
    WHEN is_dual_top   = 1 THEN 'dual_top'
    WHEN is_sen_oki    = 1 THEN 'sen_oki'
    WHEN is_hana_iki   = 1 THEN 'hana_iki'
    WHEN is_mid_chaser = 1 THEN 'mid_chaser'
    ELSE 'other'
  END AS factor_value,
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
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(distance) <> ''
GROUP BY course_code, tds_code, dist_band, factor_value
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ── 3-6. IDM指数帯 ───────────────────────────────────────────────────
INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'idm_band',
  CASE
    WHEN CAST(TRIM(idm) AS DECIMAL(6,1)) <  30 THEN '~30'
    WHEN CAST(TRIM(idm) AS DECIMAL(6,1)) <  40 THEN '30~40'
    WHEN CAST(TRIM(idm) AS DECIMAL(6,1)) <  50 THEN '40~50'
    WHEN CAST(TRIM(idm) AS DECIMAL(6,1)) <  60 THEN '50~60'
    WHEN CAST(TRIM(idm) AS DECIMAL(6,1)) <  70 THEN '60~70'
    ELSE '70~'
  END AS factor_value,
  '', '', '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(idm) <> '' AND CAST(TRIM(idm) AS DECIMAL(6,1)) > 0
GROUP BY factor_value
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ── 3-7. 激走指数帯 ──────────────────────────────────────────────────
INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'gekiso_band',
  CASE
    WHEN CAST(TRIM(gekiso_index) AS UNSIGNED) = 0               THEN '0'
    WHEN CAST(TRIM(gekiso_index) AS UNSIGNED) BETWEEN 1 AND 20  THEN '1~20'
    WHEN CAST(TRIM(gekiso_index) AS UNSIGNED) BETWEEN 21 AND 40 THEN '21~40'
    WHEN CAST(TRIM(gekiso_index) AS UNSIGNED) BETWEEN 41 AND 60 THEN '41~60'
    ELSE '61~'
  END AS factor_value,
  '', '', '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(gekiso_index) <> ''
GROUP BY factor_value
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ── 3-8. 万券指数帯 ──────────────────────────────────────────────────
INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'manbaken_band',
  CASE
    WHEN CAST(TRIM(manbaken_index) AS UNSIGNED) = 0               THEN '0'
    WHEN CAST(TRIM(manbaken_index) AS UNSIGNED) BETWEEN 1 AND 20  THEN '1~20'
    WHEN CAST(TRIM(manbaken_index) AS UNSIGNED) BETWEEN 21 AND 40 THEN '21~40'
    WHEN CAST(TRIM(manbaken_index) AS UNSIGNED) BETWEEN 41 AND 60 THEN '41~60'
    ELSE '61~'
  END AS factor_value,
  '', '', '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(manbaken_index) <> ''
GROUP BY factor_value
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ── 3-9. 調教評価 ────────────────────────────────────────────────────
INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'chokyo_hyoka', TRIM(chokyo_hyoka), '', '', '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(chokyo_hyoka) <> ''
GROUP BY TRIM(chokyo_hyoka)
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ── 3-10. 脚質 ───────────────────────────────────────────────────────
INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'kyakushitsu', TRIM(kyakushitsu), '', '', '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(kyakushitsu) <> ''
GROUP BY TRIM(kyakushitsu)
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ── 3-10b. 脚質（コース×芝ダ別）────────────────────────────────────
-- 逃げ有利/差し有利などコース特性を反映するため course_code + tds_code で集計
-- dist_band='' として距離帯は分割しない（サンプル数確保のため）
INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'kyakushitsu', TRIM(kyakushitsu), course_code, tds_code, '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(kyakushitsu) <> ''
GROUP BY course_code, tds_code, TRIM(kyakushitsu)
HAVING COUNT(*) >= 20
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ── 3-11. 上昇度 ─────────────────────────────────────────────────────
INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'joshodo', TRIM(joshodo), '', '', '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(joshodo) <> ''
GROUP BY TRIM(joshodo)
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ── 3-12. 距離適性 ───────────────────────────────────────────────────
INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'kyori_tekisei', TRIM(kyori_tekisei), '', '', '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(kyori_tekisei) <> ''
GROUP BY TRIM(kyori_tekisei)
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ── 3-13. 父系統コード ───────────────────────────────────────────────
INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'chichi_keitou', TRIM(chichi_keitou_code), '', '', '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(chichi_keitou_code) <> ''
GROUP BY TRIM(chichi_keitou_code)
HAVING COUNT(*) >= 30
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ── 3-14. 母父系統コード ─────────────────────────────────────────────
INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'hahachichi_keitou', TRIM(hahachichi_keitou_code), '', '', '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(hahachichi_keitou_code) <> ''
GROUP BY TRIM(hahachichi_keitou_code)
HAVING COUNT(*) >= 30
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ── 3-13b. 父系統（芝ダ別）──────────────────────────────────────────
-- サンデー系は芝向き、キングカメハメハ系はダート向きなど芝ダで特性が分かれる
-- コース単位ではサンプルが薄くなるため tds_code レベルで集計
INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'chichi_keitou', TRIM(chichi_keitou_code), '', tds_code, '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(chichi_keitou_code) <> '' AND TRIM(tds_code) <> ''
GROUP BY tds_code, TRIM(chichi_keitou_code)
HAVING COUNT(*) >= 20
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ── 3-14b. 母父系統（芝ダ別）────────────────────────────────────────
INSERT INTO T_ANABA_FACTOR_AGG
  (factor_type, factor_value, course_code, tds_code, dist_band,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  'hahachichi_keitou', TRIM(hahachichi_keitou_code), '', tds_code, '',
  COUNT(*),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1),
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3),
  SUM(win_payout), SUM(place_payout),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)             / COUNT(*) * 100, 1),
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(win_payout)   / COUNT(*), 1),
  ROUND(SUM(place_payout) / COUNT(*), 1)
FROM T_ANABA_RACE_LOG
WHERE finish_order IS NOT NULL AND ijou_kubun IN ('0','')
  AND TRIM(hahachichi_keitou_code) <> '' AND TRIM(tds_code) <> ''
GROUP BY tds_code, TRIM(hahachichi_keitou_code)
HAVING COUNT(*) >= 20
ON DUPLICATE KEY UPDATE
  total_count=VALUES(total_count), win_count=VALUES(win_count),
  place_count=VALUES(place_count), win_payout_sum=VALUES(win_payout_sum),
  place_payout_sum=VALUES(place_payout_sum), win_rate=VALUES(win_rate),
  place_rate=VALUES(place_rate), win_recovery=VALUES(win_recovery),
  place_recovery=VALUES(place_recovery);


-- ============================================================
-- Part 4: T_ANABA_SCORE 計算
--
-- 各ファクターの回収率偏差（factor_recovery - baseline_recovery）を合計して指数化。
-- 全体指数: baseline は course_code='' tds_code='' dist_band='' の 'baseline'/'all'
-- コース別指数: コース別 baseline が存在すれば使用し、なければ全体 baseline にフォールバック
--
-- 対象: T_KYI 全馬（kijun_odds の値に関わらず）
--       指数が意味を持つのは kijun_odds >= 10.0 の馬のみ（表示側でフィルタする）
-- 冪等: ON DUPLICATE KEY UPDATE
-- ============================================================
INSERT INTO T_ANABA_SCORE (
  course_code, year_code, kai, day_code, race_num, uma_num,
  overall_score, course_score,
  score_ten, score_agari, score_ichi, score_goal, score_combo,
  score_idm, score_gekiso, score_manbaken, score_chokyo, score_kyusha,
  score_kyakushitsu, score_joshodo, score_tekisei, score_blood
)
SELECT
  k.course_code, k.year_code, k.kai, k.day_code, k.race_num, k.uma_num,

  -- ── 全体穴馬指数 ─────────────────────────────────────────────
  ROUND(
    -- テン順位
    COALESCE(f_ten_o.win_recovery,   bl_o.win_recovery) - bl_o.win_recovery
    -- 上がり順位
    + COALESCE(f_agari_o.win_recovery,  bl_o.win_recovery) - bl_o.win_recovery
    -- 位置順位
    + COALESCE(f_ichi_o.win_recovery,   bl_o.win_recovery) - bl_o.win_recovery
    -- ゴール順位
    + COALESCE(f_goal_o.win_recovery,   bl_o.win_recovery) - bl_o.win_recovery
    -- 複合展開
    + COALESCE(f_combo_o.win_recovery,  bl_o.win_recovery) - bl_o.win_recovery
    -- IDM
    + COALESCE(f_idm_o.win_recovery,    bl_o.win_recovery) - bl_o.win_recovery
    -- 激走指数
    + COALESCE(f_gek_o.win_recovery,    bl_o.win_recovery) - bl_o.win_recovery
    -- 万券指数
    + COALESCE(f_man_o.win_recovery,    bl_o.win_recovery) - bl_o.win_recovery
    -- 調教評価
    + COALESCE(f_chk_o.win_recovery,    bl_o.win_recovery) - bl_o.win_recovery
    -- 脚質
    + COALESCE(f_kya_o.win_recovery,    bl_o.win_recovery) - bl_o.win_recovery
    -- 上昇度
    + COALESCE(f_jos_o.win_recovery,    bl_o.win_recovery) - bl_o.win_recovery
    -- 距離適性
    + COALESCE(f_kyo_o.win_recovery,    bl_o.win_recovery) - bl_o.win_recovery
    -- 父系統
    + COALESCE(f_chi_o.win_recovery,    bl_o.win_recovery) - bl_o.win_recovery
    -- 母父系統
    + COALESCE(f_hah_o.win_recovery,    bl_o.win_recovery) - bl_o.win_recovery
  , 1) AS overall_score,

  -- ── コース別穴馬指数 ──────────────────────────────────────────
  -- ルール: コース別データがある → コースベースラインで差分
  --         フォールバック時   → 全体の偏差をそのまま使用（ベース混在を防ぐ）
  -- NULL 算術: f_ten_c.win_recovery が NULL なら式全体が NULL → COALESCE で次候補へ
  ROUND(
    COALESCE(f_ten_c.win_recovery   - COALESCE(bl_c_raw.win_recovery, bl_o.win_recovery), f_ten_o.win_recovery   - bl_o.win_recovery, 0)
    + COALESCE(f_agari_c.win_recovery - COALESCE(bl_c_raw.win_recovery, bl_o.win_recovery), f_agari_o.win_recovery - bl_o.win_recovery, 0)
    + COALESCE(f_ichi_c.win_recovery  - COALESCE(bl_c_raw.win_recovery, bl_o.win_recovery), f_ichi_o.win_recovery  - bl_o.win_recovery, 0)
    + COALESCE(f_goal_c.win_recovery  - COALESCE(bl_c_raw.win_recovery, bl_o.win_recovery), f_goal_o.win_recovery  - bl_o.win_recovery, 0)
    + COALESCE(f_combo_c.win_recovery - COALESCE(bl_c_raw.win_recovery, bl_o.win_recovery), f_combo_o.win_recovery - bl_o.win_recovery, 0)
    + COALESCE(f_idm_o.win_recovery   - bl_o.win_recovery, 0)
    + COALESCE(f_gek_o.win_recovery   - bl_o.win_recovery, 0)
    + COALESCE(f_man_o.win_recovery   - bl_o.win_recovery, 0)
    + COALESCE(f_chk_o.win_recovery   - bl_o.win_recovery, 0)
    + COALESCE(f_kya_c.win_recovery   - COALESCE(bl_c_raw.win_recovery, bl_o.win_recovery), f_kya_o.win_recovery   - bl_o.win_recovery, 0)
    + COALESCE(f_jos_o.win_recovery   - bl_o.win_recovery, 0)
    + COALESCE(f_kyo_o.win_recovery   - bl_o.win_recovery, 0)
    + COALESCE(f_chi_tds.win_recovery - bl_o.win_recovery, f_chi_o.win_recovery - bl_o.win_recovery, 0)
    + COALESCE(f_hah_tds.win_recovery - bl_o.win_recovery, f_hah_o.win_recovery - bl_o.win_recovery, 0)
  , 1) AS course_score,

  -- ── スコア内訳 ────────────────────────────────────────────────
  ROUND(COALESCE(f_ten_o.win_recovery,   bl_o.win_recovery) - bl_o.win_recovery, 1),
  ROUND(COALESCE(f_agari_o.win_recovery, bl_o.win_recovery) - bl_o.win_recovery, 1),
  ROUND(COALESCE(f_ichi_o.win_recovery,  bl_o.win_recovery) - bl_o.win_recovery, 1),
  ROUND(COALESCE(f_goal_o.win_recovery,  bl_o.win_recovery) - bl_o.win_recovery, 1),
  ROUND(COALESCE(f_combo_o.win_recovery, bl_o.win_recovery) - bl_o.win_recovery, 1),
  ROUND(COALESCE(f_idm_o.win_recovery,   bl_o.win_recovery) - bl_o.win_recovery, 1),
  ROUND(COALESCE(f_gek_o.win_recovery,   bl_o.win_recovery) - bl_o.win_recovery, 1),
  ROUND(COALESCE(f_man_o.win_recovery,   bl_o.win_recovery) - bl_o.win_recovery, 1),
  ROUND(COALESCE(f_chk_o.win_recovery,   bl_o.win_recovery) - bl_o.win_recovery, 1),
  ROUND(COALESCE(f_kya_o.win_recovery,   bl_o.win_recovery) - bl_o.win_recovery, 1),  -- kyusha placeholder
  ROUND(COALESCE(f_kya_o.win_recovery,   bl_o.win_recovery) - bl_o.win_recovery, 1),
  ROUND(COALESCE(f_jos_o.win_recovery,   bl_o.win_recovery) - bl_o.win_recovery, 1),
  ROUND(COALESCE(f_kyo_o.win_recovery,   bl_o.win_recovery) - bl_o.win_recovery, 1),
  ROUND(COALESCE(f_chi_o.win_recovery,   bl_o.win_recovery) - bl_o.win_recovery +
        COALESCE(f_hah_o.win_recovery,   bl_o.win_recovery) - bl_o.win_recovery, 1)

FROM T_KYI k
INNER JOIN T_BAC b
  ON b.course_code=k.course_code AND b.year_code=k.year_code
  AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num

-- ── 全体ベースライン ──────────────────────────────────────────────
CROSS JOIN (
  SELECT win_recovery FROM T_ANABA_FACTOR_AGG
  WHERE factor_type='baseline' AND factor_value='all'
    AND course_code='' AND tds_code='' AND dist_band=''
) bl_o

-- ── コース別ベースライン（なければ全体を流用）──────────────────────
LEFT JOIN (
  SELECT a.course_code, a.tds_code, a.dist_band, a.win_recovery
  FROM T_ANABA_FACTOR_AGG a
  WHERE a.factor_type='baseline' AND a.factor_value='all'
    AND a.course_code <> ''
) bl_c_raw ON bl_c_raw.course_code = k.course_code
          AND bl_c_raw.tds_code  = TRIM(b.tds_code)
          AND bl_c_raw.dist_band = CASE
              WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1200 THEN '~1200'
              WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1400 THEN '1201~1400'
              WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1600 THEN '1401~1600'
              WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 2000 THEN '1601~2000'
              WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 2400 THEN '2001~2400'
              ELSE '2401~' END

-- 以下の全体ファクター JOIN は共通式を使う
-- テン順位（全体）
LEFT JOIN T_ANABA_FACTOR_AGG f_ten_o
  ON f_ten_o.factor_type='ten_rank' AND f_ten_o.course_code='' AND f_ten_o.tds_code='' AND f_ten_o.dist_band=''
  AND f_ten_o.factor_value = CASE
    WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) = 1             THEN '1'
    WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
    WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
    ELSE '7~' END

-- 上がり順位（全体）
LEFT JOIN T_ANABA_FACTOR_AGG f_agari_o
  ON f_agari_o.factor_type='agari_rank' AND f_agari_o.course_code='' AND f_agari_o.tds_code='' AND f_agari_o.dist_band=''
  AND f_agari_o.factor_value = CASE
    WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) = 1             THEN '1'
    WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
    WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
    ELSE '7~' END

-- 位置順位（全体）
LEFT JOIN T_ANABA_FACTOR_AGG f_ichi_o
  ON f_ichi_o.factor_type='ichi_rank' AND f_ichi_o.course_code='' AND f_ichi_o.tds_code='' AND f_ichi_o.dist_band=''
  AND f_ichi_o.factor_value = CASE
    WHEN CAST(TRIM(k.ichi_index_juni) AS UNSIGNED) = 1             THEN '1'
    WHEN CAST(TRIM(k.ichi_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
    WHEN CAST(TRIM(k.ichi_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
    ELSE '7~' END

-- ゴール順位（全体）
LEFT JOIN T_ANABA_FACTOR_AGG f_goal_o
  ON f_goal_o.factor_type='goal_rank' AND f_goal_o.course_code='' AND f_goal_o.tds_code='' AND f_goal_o.dist_band=''
  AND f_goal_o.factor_value = CASE
    WHEN CAST(TRIM(k.goal_juni) AS UNSIGNED) = 1             THEN '1'
    WHEN CAST(TRIM(k.goal_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
    WHEN CAST(TRIM(k.goal_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
    ELSE '7~' END

-- 複合展開（全体）
LEFT JOIN T_ANABA_FACTOR_AGG f_combo_o
  ON f_combo_o.factor_type='tenkai_combo' AND f_combo_o.course_code='' AND f_combo_o.tds_code='' AND f_combo_o.dist_band=''
  AND f_combo_o.factor_value = CASE
    WHEN CAST(TRIM(k.ten_index_juni)   AS UNSIGNED) <= 3 AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 3
         AND TRIM(k.ten_index_juni) <> '' AND TRIM(k.agari_index_juni) <> '' THEN 'dual_top'
    WHEN CAST(TRIM(k.ten_index_juni)   AS UNSIGNED) >= 7 AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 2
         AND TRIM(k.ten_index_juni) <> '' AND TRIM(k.agari_index_juni) <> '' THEN 'sen_oki'
    WHEN CAST(TRIM(k.ten_index_juni)   AS UNSIGNED) <= 2 AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) >= 7
         AND TRIM(k.ten_index_juni) <> '' AND TRIM(k.agari_index_juni) <> '' THEN 'hana_iki'
    WHEN CAST(TRIM(k.ichi_index_juni)  AS UNSIGNED) BETWEEN 3 AND 5 AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 3
         AND TRIM(k.ichi_index_juni) <> '' AND TRIM(k.agari_index_juni) <> '' THEN 'mid_chaser'
    ELSE 'other' END

-- IDM帯（全体）
LEFT JOIN T_ANABA_FACTOR_AGG f_idm_o
  ON f_idm_o.factor_type='idm_band' AND f_idm_o.course_code='' AND f_idm_o.tds_code='' AND f_idm_o.dist_band=''
  AND f_idm_o.factor_value = CASE
    WHEN TRIM(k.idm)='' OR CAST(TRIM(k.idm) AS DECIMAL(6,1)) <= 0 THEN NULL
    WHEN CAST(TRIM(k.idm) AS DECIMAL(6,1)) <  30 THEN '~30'
    WHEN CAST(TRIM(k.idm) AS DECIMAL(6,1)) <  40 THEN '30~40'
    WHEN CAST(TRIM(k.idm) AS DECIMAL(6,1)) <  50 THEN '40~50'
    WHEN CAST(TRIM(k.idm) AS DECIMAL(6,1)) <  60 THEN '50~60'
    WHEN CAST(TRIM(k.idm) AS DECIMAL(6,1)) <  70 THEN '60~70'
    ELSE '70~' END

-- 激走指数帯（全体）
LEFT JOIN T_ANABA_FACTOR_AGG f_gek_o
  ON f_gek_o.factor_type='gekiso_band' AND f_gek_o.course_code='' AND f_gek_o.tds_code='' AND f_gek_o.dist_band=''
  AND f_gek_o.factor_value = CASE
    WHEN TRIM(k.gekiso_index)='' THEN NULL
    WHEN CAST(TRIM(k.gekiso_index) AS UNSIGNED) = 0               THEN '0'
    WHEN CAST(TRIM(k.gekiso_index) AS UNSIGNED) BETWEEN 1 AND 20  THEN '1~20'
    WHEN CAST(TRIM(k.gekiso_index) AS UNSIGNED) BETWEEN 21 AND 40 THEN '21~40'
    WHEN CAST(TRIM(k.gekiso_index) AS UNSIGNED) BETWEEN 41 AND 60 THEN '41~60'
    ELSE '61~' END

-- 万券指数帯（全体）
LEFT JOIN T_ANABA_FACTOR_AGG f_man_o
  ON f_man_o.factor_type='manbaken_band' AND f_man_o.course_code='' AND f_man_o.tds_code='' AND f_man_o.dist_band=''
  AND f_man_o.factor_value = CASE
    WHEN TRIM(k.manbaken_index)='' THEN NULL
    WHEN CAST(TRIM(k.manbaken_index) AS UNSIGNED) = 0               THEN '0'
    WHEN CAST(TRIM(k.manbaken_index) AS UNSIGNED) BETWEEN 1 AND 20  THEN '1~20'
    WHEN CAST(TRIM(k.manbaken_index) AS UNSIGNED) BETWEEN 21 AND 40 THEN '21~40'
    WHEN CAST(TRIM(k.manbaken_index) AS UNSIGNED) BETWEEN 41 AND 60 THEN '41~60'
    ELSE '61~' END

-- 調教評価（全体）
LEFT JOIN T_ANABA_FACTOR_AGG f_chk_o
  ON f_chk_o.factor_type='chokyo_hyoka' AND f_chk_o.course_code='' AND f_chk_o.tds_code='' AND f_chk_o.dist_band=''
  AND f_chk_o.factor_value = TRIM(k.chokyo_yajirushi)

-- 脚質（全体）
LEFT JOIN T_ANABA_FACTOR_AGG f_kya_o
  ON f_kya_o.factor_type='kyakushitsu' AND f_kya_o.course_code='' AND f_kya_o.tds_code='' AND f_kya_o.dist_band=''
  AND f_kya_o.factor_value = TRIM(k.kyakushitsu)

-- 上昇度（全体）
LEFT JOIN T_ANABA_FACTOR_AGG f_jos_o
  ON f_jos_o.factor_type='joshodo' AND f_jos_o.course_code='' AND f_jos_o.tds_code='' AND f_jos_o.dist_band=''
  AND f_jos_o.factor_value = TRIM(k.joshodo)

-- 距離適性（全体）
LEFT JOIN T_ANABA_FACTOR_AGG f_kyo_o
  ON f_kyo_o.factor_type='kyori_tekisei' AND f_kyo_o.course_code='' AND f_kyo_o.tds_code='' AND f_kyo_o.dist_band=''
  AND f_kyo_o.factor_value = TRIM(k.kyori_tekisei)

-- 父系統（全体）
LEFT JOIN T_UKC ukc ON ukc.blood_reg_num = TRIM(k.blood_reg_num)
LEFT JOIN T_ANABA_FACTOR_AGG f_chi_o
  ON f_chi_o.factor_type='chichi_keitou' AND f_chi_o.course_code='' AND f_chi_o.tds_code='' AND f_chi_o.dist_band=''
  AND f_chi_o.factor_value = TRIM(ukc.chichi_keitou_code)

-- 母父系統（全体）
LEFT JOIN T_ANABA_FACTOR_AGG f_hah_o
  ON f_hah_o.factor_type='hahachichi_keitou' AND f_hah_o.course_code='' AND f_hah_o.tds_code='' AND f_hah_o.dist_band=''
  AND f_hah_o.factor_value = TRIM(ukc.hahachichi_keitou_code)

-- 脚質（コース×芝ダ別）
LEFT JOIN T_ANABA_FACTOR_AGG f_kya_c
  ON f_kya_c.factor_type='kyakushitsu'
  AND f_kya_c.course_code=k.course_code AND f_kya_c.tds_code=TRIM(b.tds_code) AND f_kya_c.dist_band=''
  AND f_kya_c.factor_value = TRIM(k.kyakushitsu)

-- 父系統（芝ダ別）
LEFT JOIN T_ANABA_FACTOR_AGG f_chi_tds
  ON f_chi_tds.factor_type='chichi_keitou'
  AND f_chi_tds.course_code='' AND f_chi_tds.tds_code=TRIM(b.tds_code) AND f_chi_tds.dist_band=''
  AND f_chi_tds.factor_value = TRIM(ukc.chichi_keitou_code)

-- 母父系統（芝ダ別）
LEFT JOIN T_ANABA_FACTOR_AGG f_hah_tds
  ON f_hah_tds.factor_type='hahachichi_keitou'
  AND f_hah_tds.course_code='' AND f_hah_tds.tds_code=TRIM(b.tds_code) AND f_hah_tds.dist_band=''
  AND f_hah_tds.factor_value = TRIM(ukc.hahachichi_keitou_code)

-- コース別展開系ファクター（コース+芝ダ+距離帯でルックアップ）

LEFT JOIN T_ANABA_FACTOR_AGG f_ten_c
  ON f_ten_c.factor_type='ten_rank'
  AND f_ten_c.course_code=k.course_code AND f_ten_c.tds_code=TRIM(b.tds_code)
  AND f_ten_c.dist_band = CASE
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1200 THEN '~1200'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1400 THEN '1201~1400'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1600 THEN '1401~1600'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 2000 THEN '1601~2000'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 2400 THEN '2001~2400'
    ELSE '2401~' END
  AND f_ten_c.factor_value = CASE
    WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) = 1             THEN '1'
    WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
    WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
    ELSE '7~' END

LEFT JOIN T_ANABA_FACTOR_AGG f_agari_c
  ON f_agari_c.factor_type='agari_rank'
  AND f_agari_c.course_code=k.course_code AND f_agari_c.tds_code=TRIM(b.tds_code)
  AND f_agari_c.dist_band = CASE
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1200 THEN '~1200'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1400 THEN '1201~1400'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1600 THEN '1401~1600'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 2000 THEN '1601~2000'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 2400 THEN '2001~2400'
    ELSE '2401~' END
  AND f_agari_c.factor_value = CASE
    WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) = 1             THEN '1'
    WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
    WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
    ELSE '7~' END

LEFT JOIN T_ANABA_FACTOR_AGG f_ichi_c
  ON f_ichi_c.factor_type='ichi_rank'
  AND f_ichi_c.course_code=k.course_code AND f_ichi_c.tds_code=TRIM(b.tds_code)
  AND f_ichi_c.dist_band = CASE
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1200 THEN '~1200'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1400 THEN '1201~1400'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1600 THEN '1401~1600'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 2000 THEN '1601~2000'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 2400 THEN '2001~2400'
    ELSE '2401~' END
  AND f_ichi_c.factor_value = CASE
    WHEN CAST(TRIM(k.ichi_index_juni) AS UNSIGNED) = 1             THEN '1'
    WHEN CAST(TRIM(k.ichi_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
    WHEN CAST(TRIM(k.ichi_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
    ELSE '7~' END

LEFT JOIN T_ANABA_FACTOR_AGG f_goal_c
  ON f_goal_c.factor_type='goal_rank'
  AND f_goal_c.course_code=k.course_code AND f_goal_c.tds_code=TRIM(b.tds_code)
  AND f_goal_c.dist_band = CASE
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1200 THEN '~1200'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1400 THEN '1201~1400'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1600 THEN '1401~1600'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 2000 THEN '1601~2000'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 2400 THEN '2001~2400'
    ELSE '2401~' END
  AND f_goal_c.factor_value = CASE
    WHEN CAST(TRIM(k.goal_juni) AS UNSIGNED) = 1             THEN '1'
    WHEN CAST(TRIM(k.goal_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
    WHEN CAST(TRIM(k.goal_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
    ELSE '7~' END

LEFT JOIN T_ANABA_FACTOR_AGG f_combo_c
  ON f_combo_c.factor_type='tenkai_combo'
  AND f_combo_c.course_code=k.course_code AND f_combo_c.tds_code=TRIM(b.tds_code)
  AND f_combo_c.dist_band = CASE
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1200 THEN '~1200'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1400 THEN '1201~1400'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 1600 THEN '1401~1600'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 2000 THEN '1601~2000'
    WHEN CAST(TRIM(b.distance) AS UNSIGNED) <= 2400 THEN '2001~2400'
    ELSE '2401~' END
  AND f_combo_c.factor_value = CASE
    WHEN CAST(TRIM(k.ten_index_juni)   AS UNSIGNED) <= 3 AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 3
         AND TRIM(k.ten_index_juni)<>'' AND TRIM(k.agari_index_juni)<>'' THEN 'dual_top'
    WHEN CAST(TRIM(k.ten_index_juni)   AS UNSIGNED) >= 7 AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 2
         AND TRIM(k.ten_index_juni)<>'' AND TRIM(k.agari_index_juni)<>'' THEN 'sen_oki'
    WHEN CAST(TRIM(k.ten_index_juni)   AS UNSIGNED) <= 2 AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) >= 7
         AND TRIM(k.ten_index_juni)<>'' AND TRIM(k.agari_index_juni)<>'' THEN 'hana_iki'
    WHEN CAST(TRIM(k.ichi_index_juni)  AS UNSIGNED) BETWEEN 3 AND 5 AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) <= 3
         AND TRIM(k.ichi_index_juni)<>'' AND TRIM(k.agari_index_juni)<>'' THEN 'mid_chaser'
    ELSE 'other' END

WHERE TRIM(b.tds_code) IN ('1','2')

ON DUPLICATE KEY UPDATE
  overall_score     = VALUES(overall_score),
  course_score      = VALUES(course_score),
  score_ten         = VALUES(score_ten),
  score_agari       = VALUES(score_agari),
  score_ichi        = VALUES(score_ichi),
  score_goal        = VALUES(score_goal),
  score_combo       = VALUES(score_combo),
  score_idm         = VALUES(score_idm),
  score_gekiso      = VALUES(score_gekiso),
  score_manbaken    = VALUES(score_manbaken),
  score_chokyo      = VALUES(score_chokyo),
  score_kyusha      = VALUES(score_kyusha),
  score_kyakushitsu = VALUES(score_kyakushitsu),
  score_joshodo     = VALUES(score_joshodo),
  score_tekisei     = VALUES(score_tekisei),
  score_blood       = VALUES(score_blood);
