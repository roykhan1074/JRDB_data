-- ============================================================
-- 厩舎指数信頼度分析 テーブル定義 & ETL
-- 出馬表ページ「厩舎指数の信頼度スコア」表示向けデータ基盤
-- ============================================================
-- 実行順: Part1 → Part2 → Part3
-- Part2, Part3 は差分投入可。毎週 Part2 → Part3 を再実行するだけで最新化される。
-- 推奨タイミング: 木曜日（T_SED 正式版 SEC 更新後）
-- ============================================================


-- ============================================================
-- Part 1: テーブル定義
-- ============================================================

-- ------------------------------------------------------------
-- 1-1. ファクトテーブル（厩舎 × レース 1行）
--
-- T_KYI + T_BAC + T_SED を JOIN した非正規化ログ。
-- 騎手分析の T_KISHU_RACE_LOG に対応する厩舎版。
--
-- 設計上のポイント:
--   - kyusha_index を DECIMAL 型で格納（T_KYI の CHAR(5) から変換）
--     → Part3 集計クエリで CAST/TRIM が不要になり、帯域判定が型安全
--   - 1行 = 1頭分の出走記録。取消・除外は ijou_kubun で識別。
--   - T_SED 未格納時（レース前）は finish_order が NULL になる。
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS T_KYUSHA_RACE_LOG (
  -- ── レースキー（T_KYI / T_BAC / T_SED 共通）──────────────────
  course_code       CHAR(2)        NOT NULL COMMENT '場コード',
  year_code         CHAR(2)        NOT NULL COMMENT '年（西暦下2桁）',
  kai               CHAR(1)        NOT NULL COMMENT '回',
  day_code          CHAR(1)        NOT NULL COMMENT '日（16進）',
  race_num          CHAR(2)        NOT NULL COMMENT 'R',
  uma_num           CHAR(2)        NOT NULL COMMENT '馬番',

  -- ── 日付 ──────────────────────────────────────────────────
  ymd               CHAR(8)        NOT NULL COMMENT '年月日 YYYYMMDD（T_BAC）',

  -- ── 調教師 ────────────────────────────────────────────────
  trainer_code      CHAR(5)                 COMMENT '調教師コード（T_KYI）',
  trainer_name      VARCHAR(12)             COMMENT '調教師名（T_KYI）',

  -- ── 厩舎評価（T_KYI）──────────────────────────────────────
  kyusha_index      DECIMAL(5,1)            COMMENT '厩舎指数（数値変換済み・NULL=無効値）',
  kyusha_hyoka      CHAR(1)                 COMMENT '厩舎評価コード A/B/C/D/E（T_KYI）',

  -- ── オッズ・人気（穴信頼度の判定に使用）─────────────────────
  kijun_odds        DECIMAL(6,1)            COMMENT '基準単勝オッズ（T_KYI）',
  kijun_ninki       SMALLINT                COMMENT '基準人気順位（T_KYI）',

  -- ── レース条件（T_BAC）────────────────────────────────────
  distance          CHAR(4)                 COMMENT '距離（m）',
  tds_code          CHAR(1)                 COMMENT '芝ダ障害 1:芝 2:ダ 3:障',
  class             CHAR(2)                 COMMENT '条件クラス A1/A3/05/10/16/OP 等',
  heads             CHAR(2)                 COMMENT '頭数',

  -- ── 成績（T_SED）─────────────────────────────────────────
  finish_order      CHAR(2)                 COMMENT '着順（NULL = 結果未格納）',
  ijou_kubun        CHAR(1)                 COMMENT '異常区分 0:正常 1:取消 2:除外 etc.',
  win_payout        INT                     COMMENT '単勝払戻（円/100円ベット）0=対象外',
  place_payout      INT                     COMMENT '複勝払戻（円/100円ベット）0=対象外',

  -- ── メタ ──────────────────────────────────────────────────
  load_date         CHAR(8)        NOT NULL COMMENT 'ロード日 YYYYMMDD',

  PRIMARY KEY (course_code, year_code, kai, day_code, race_num, uma_num),
  INDEX idx_kyusha_log_trainer_ymd  (trainer_code, ymd),
  INDEX idx_kyusha_log_trainer_code (trainer_code),
  INDEX idx_kyusha_log_ymd          (ymd)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='厩舎成績ログ（分析ファクトテーブル・日次粒度）';


-- ------------------------------------------------------------
-- 1-2. ファクター別集計テーブル（出馬表表示用）
--
-- 調教師 × 年 × ファクター種別 × ファクター値 の 1行。
-- EAV 形式のため、新ファクターはテーブル変更なしで追加できる。
--
-- factor_type 一覧（Part3 で INSERT する種別）:
--   kyusha_idx        厩舎指数帯（6段階: <-10 / -10~0 / 0~10 / 10~20 / 20~30 / 30~40）
--   kyusha_idx_x_odds 指数プラマイ × オッズ帯（4セル複合: 穴信頼度の判定用）
--
-- 出馬表での活用例:
--   SELECT win_recovery, total_count
--   FROM T_KYUSHA_FACTOR_AGG
--   WHERE trainer_code = '12345'
--     AND agg_year IN ('2024','2025')
--     AND factor_type = 'kyusha_idx'
--   ORDER BY field(factor_value,'<-10','-10~0','0~10','10~20','20~35','35~');
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS T_KYUSHA_FACTOR_AGG (
  -- ── 主キー ────────────────────────────────────────────────
  trainer_code      CHAR(5)        NOT NULL COMMENT '調教師コード',
  trainer_name      VARCHAR(12)             COMMENT '調教師名',
  agg_year          CHAR(4)        NOT NULL COMMENT '集計年 YYYY',
  factor_type       VARCHAR(30)    NOT NULL COMMENT 'ファクター種別',
  factor_value      VARCHAR(40)    NOT NULL COMMENT 'ファクター値',

  -- ── 集計カウント ───────────────────────────────────────────
  total_count       INT            NOT NULL DEFAULT 0 COMMENT '出走数（異常除く）',
  win_count         INT            NOT NULL DEFAULT 0 COMMENT '1着数',
  place_count       INT            NOT NULL DEFAULT 0 COMMENT '複勝数（3着以内）',
  win_payout_sum    BIGINT         NOT NULL DEFAULT 0 COMMENT '単勝払戻合計',
  place_payout_sum  BIGINT         NOT NULL DEFAULT 0 COMMENT '複勝払戻合計',

  -- ── 計算値（表示用・再計算可）─────────────────────────────
  win_rate          DECIMAL(5,1)            COMMENT '勝率（%）',
  place_rate        DECIMAL(5,1)            COMMENT '複勝率（%）',
  win_recovery      DECIMAL(6,1)            COMMENT '単勝回収率（円/100円）',
  place_recovery    DECIMAL(6,1)            COMMENT '複勝回収率（円/100円）',

  -- ── メタ ──────────────────────────────────────────────────
  updated_at        DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP
                                            ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (trainer_code, agg_year, factor_type, factor_value),
  INDEX idx_kyusha_agg_factor_year  (factor_type, factor_value, agg_year),
  INDEX idx_kyusha_agg_year_trainer (agg_year, trainer_code),
  INDEX idx_kyusha_agg_trainer_code (trainer_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='厩舎ファクター別集計（出馬表・信頼度スコア表示用）';


-- ============================================================
-- Part 2: T_KYUSHA_RACE_LOG 投入
--
-- T_KYI × T_BAC × T_SED を JOIN して非正規化ログを作る。
-- T_SED は当日速報後から存在するため LEFT JOIN。
-- 毎回差分投入可（ON DUPLICATE KEY UPDATE で冪等）。
--
-- 変換ルール:
--   kyusha_index: TRIM後に数値パターンの場合のみ DECIMAL 変換。不正値は NULL。
--   kijun_odds  : 同上
--   kijun_ninki : TRIM後に数値パターンの場合のみ UNSIGNED 変換。不正値は NULL。
--   win/place   : 異常区分が正常(0 or '')の場合のみ払戻を格納。それ以外は 0。
-- ============================================================
INSERT INTO T_KYUSHA_RACE_LOG (
  course_code, year_code, kai, day_code, race_num, uma_num,
  ymd,
  trainer_code, trainer_name,
  kyusha_index, kyusha_hyoka,
  kijun_odds, kijun_ninki,
  distance, tds_code, class, heads,
  finish_order, ijou_kubun,
  win_payout, place_payout,
  load_date
)
SELECT
  k.course_code, k.year_code, k.kai, k.day_code, k.race_num, k.uma_num,
  b.ymd,
  TRIM(k.trainer_code),
  TRIM(k.trainer_name),
  -- 厩舎指数: 数値パターンのみ変換
  CASE WHEN TRIM(k.kyusha_index) REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
       THEN CAST(TRIM(k.kyusha_index) AS DECIMAL(5,1))
       ELSE NULL END,
  k.kyusha_hyoka,
  -- 基準オッズ: 数値パターンのみ変換
  CASE WHEN TRIM(k.kijun_odds) REGEXP '^[0-9]+(\\.[0-9]+)?$'
       THEN CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1))
       ELSE NULL END,
  -- 基準人気: 数値パターンのみ変換
  CASE WHEN TRIM(k.kijun_ninki) REGEXP '^[0-9]+$'
       THEN CAST(TRIM(k.kijun_ninki) AS UNSIGNED)
       ELSE NULL END,
  b.distance,
  b.tds_code,
  b.`class`,
  b.heads,
  s.order_of_finish,
  s.ijou_kubun,
  -- 正常完走のみ払戻を格納
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
WHERE TRIM(k.trainer_code) <> ''
  AND TRIM(b.tds_code) IN ('1', '2', '3')
ON DUPLICATE KEY UPDATE
  ymd           = VALUES(ymd),
  trainer_name  = VALUES(trainer_name),
  kyusha_index  = VALUES(kyusha_index),
  kyusha_hyoka  = VALUES(kyusha_hyoka),
  kijun_odds    = VALUES(kijun_odds),
  kijun_ninki   = VALUES(kijun_ninki),
  finish_order  = VALUES(finish_order),
  ijou_kubun    = VALUES(ijou_kubun),
  win_payout    = VALUES(win_payout),
  place_payout  = VALUES(place_payout),
  load_date     = VALUES(load_date);


-- ============================================================
-- Part 3: T_KYUSHA_FACTOR_AGG 集計
--
-- T_KYUSHA_RACE_LOG から各ファクター別に集計して UPSERT。
-- 集計対象: 成績が存在し異常区分が正常(0 or '')のレコードのみ。
--
-- 実行前提: Part2 が完了していること。
-- 実行順序: 各 factor_type は独立しているため任意順でよい。
-- ============================================================

-- ── 3-1. 厩舎指数帯別 ────────────────────────────────────────
-- 帯域定義（6段階）※厩舎指数の最大値は40:
--   <-10   … 大きくマイナス（状態不良の強いサイン）
--   -10~0  … 軽微なマイナス
--   0~10   … ほぼ平均
--   10~20  … やや良好
--   20~30  … 良好（20以上30未満: 30はこの帯域に含まない）
--   30~40  … 最高指数（30以上: 境界値30はこの帯域に含む）
--
-- 境界値ルール（左閉右開: 各帯域は下限を含み上限を含まない）:
--   値が30のとき → '30~40' に入る（WHEN kyusha_index < 30 を超えるため）
-- ───────────────────────────────────────────────────────────
INSERT INTO T_KYUSHA_FACTOR_AGG
  (trainer_code, trainer_name, agg_year, factor_type, factor_value,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  trainer_code,
  MAX(trainer_name),
  SUBSTRING(ymd, 1, 4),
  'kyusha_idx',
  CASE
    WHEN kyusha_index <  -10 THEN '<-10'
    WHEN kyusha_index <    0 THEN '-10~0'
    WHEN kyusha_index <   10 THEN '0~10'
    WHEN kyusha_index <   20 THEN '10~20'
    WHEN kyusha_index <   30 THEN '20~30'
    ELSE '30~40'
  END                                                                 AS factor_value,
  COUNT(*)                                                            AS total_count,
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)                      AS win_count,
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3)          AS place_count,
  SUM(win_payout)                                                     AS win_payout_sum,
  SUM(place_payout)                                                   AS place_payout_sum,
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)
        / COUNT(*) * 100, 1)                                          AS win_rate,
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3)
        / COUNT(*) * 100, 1)                                          AS place_rate,
  ROUND(SUM(win_payout)   / COUNT(*), 1)                             AS win_recovery,
  ROUND(SUM(place_payout) / COUNT(*), 1)                             AS place_recovery
FROM T_KYUSHA_RACE_LOG
WHERE finish_order IS NOT NULL
  AND ijou_kubun IN ('0', '')
  AND kyusha_index IS NOT NULL
GROUP BY
  trainer_code,
  SUBSTRING(ymd, 1, 4),
  CASE
    WHEN kyusha_index <  -10 THEN '<-10'
    WHEN kyusha_index <    0 THEN '-10~0'
    WHEN kyusha_index <   10 THEN '0~10'
    WHEN kyusha_index <   20 THEN '10~20'
    WHEN kyusha_index <   30 THEN '20~30'
    ELSE '30~40'
  END
ON DUPLICATE KEY UPDATE
  trainer_name     = VALUES(trainer_name),
  total_count      = VALUES(total_count),
  win_count        = VALUES(win_count),
  place_count      = VALUES(place_count),
  win_payout_sum   = VALUES(win_payout_sum),
  place_payout_sum = VALUES(place_payout_sum),
  win_rate         = VALUES(win_rate),
  place_rate       = VALUES(place_rate),
  win_recovery     = VALUES(win_recovery),
  place_recovery   = VALUES(place_recovery);


-- ── 3-2. 厩舎指数符号 × 基準オッズ帯 複合 ──────────────────────
-- 4セルの複合ファクター（穴馬信頼度の検出用）:
--   minus_~15   … 指数マイナス × 人気馬（オッズ15倍未満）
--   minus_15~   … 指数マイナス × 穴馬（オッズ15倍以上）
--   plus_~15    … 指数プラス  × 人気馬（オッズ15倍未満）
--   plus_15~    … 指数プラス  × 穴馬（オッズ15倍以上）← ケースD の検出セル
-- ───────────────────────────────────────────────────────────

-- 旧しきい値（10倍）のデータを削除
DELETE FROM T_KYUSHA_FACTOR_AGG
WHERE factor_type = 'kyusha_idx_x_odds'
  AND factor_value IN ('minus_~10', 'minus_10~', 'plus_~10', 'plus_10~');

INSERT INTO T_KYUSHA_FACTOR_AGG
  (trainer_code, trainer_name, agg_year, factor_type, factor_value,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  trainer_code,
  MAX(trainer_name),
  SUBSTRING(ymd, 1, 4),
  'kyusha_idx_x_odds',
  CONCAT(
    CASE WHEN kyusha_index >= 0 THEN 'plus' ELSE 'minus' END,
    '_',
    CASE WHEN kijun_odds >= 15.0 THEN '15~' ELSE '~15' END
  )                                                                   AS factor_value,
  COUNT(*)                                                            AS total_count,
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)                      AS win_count,
  SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3)          AS place_count,
  SUM(win_payout)                                                     AS win_payout_sum,
  SUM(place_payout)                                                   AS place_payout_sum,
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) = 1)
        / COUNT(*) * 100, 1)                                          AS win_rate,
  ROUND(SUM(CAST(TRIM(finish_order) AS UNSIGNED) BETWEEN 1 AND 3)
        / COUNT(*) * 100, 1)                                          AS place_rate,
  ROUND(SUM(win_payout)   / COUNT(*), 1)                             AS win_recovery,
  ROUND(SUM(place_payout) / COUNT(*), 1)                             AS place_recovery
FROM T_KYUSHA_RACE_LOG
WHERE finish_order IS NOT NULL
  AND ijou_kubun IN ('0', '')
  AND kyusha_index IS NOT NULL
  AND kijun_odds IS NOT NULL
  AND kijun_odds > 0
GROUP BY
  trainer_code,
  SUBSTRING(ymd, 1, 4),
  CONCAT(
    CASE WHEN kyusha_index >= 0 THEN 'plus' ELSE 'minus' END,
    '_',
    CASE WHEN kijun_odds >= 15.0 THEN '15~' ELSE '~15' END
  )
ON DUPLICATE KEY UPDATE
  trainer_name     = VALUES(trainer_name),
  total_count      = VALUES(total_count),
  win_count        = VALUES(win_count),
  place_count      = VALUES(place_count),
  win_payout_sum   = VALUES(win_payout_sum),
  place_payout_sum = VALUES(place_payout_sum),
  win_rate         = VALUES(win_rate),
  place_rate       = VALUES(place_rate),
  win_recovery     = VALUES(win_recovery),
  place_recovery   = VALUES(place_recovery);



