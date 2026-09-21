-- ============================================================
-- 不利巻き返し指数 ETL (T_FURI_SCORE)
-- 設計根拠: 2026-09-12 前走不利度×回収率の多角分析（メモリ: project_prev_furi_recovery_analysis）
--
-- 前提: 前走(T_KYI.prev1_seiseki_key = 血統登録番号8桁+年月日8桁 で T_SED にリンク)で
-- 不利(furi>=1)を受けた馬は次走の回収率が高い。ただし、その効果は
-- 「他のJRDBファクター(EX指数コース・上がり指数順位・仕上指数・情報印)で
-- 既に高評価されている馬」では消える／逆転する（前走好走馬は元々他ファクターも高いはずで、
-- 逆に前走不利で着順が悪化した馬は他ファクターでは見えにくい）。
--
-- score = 該当セグメント(前走不利度×他ファクター高評価フラグ)の単勝回収率 − 全体平均単勝回収率
-- 他ファクターで既に高評価(hot_flag=1)の馬は常にscore=0（このindexは"見過ごされている馬"を
-- 拾うためのものであり、既に評価済みの馬に上乗せする指数ではない）。
-- ============================================================

-- ============================================================
-- Part 1: テーブル定義
-- ============================================================
CREATE TABLE IF NOT EXISTS T_FURI_FACTOR_AGG (
  factor_type      VARCHAR(20)  NOT NULL COMMENT 'baseline / fine(度数×hot) / coarse(あり無し×hot)',
  factor_value     VARCHAR(10)  NOT NULL COMMENT '例: fine="2_h0"(前走不利度2×hotでない), coarse="1_h1"(不利あり×hot)',
  total_count      INT          NOT NULL DEFAULT 0,
  win_count        INT          NOT NULL DEFAULT 0,
  place_count      INT          NOT NULL DEFAULT 0,
  win_payout_sum   BIGINT       NOT NULL DEFAULT 0,
  place_payout_sum BIGINT       NOT NULL DEFAULT 0,
  win_rate         DECIMAL(5,1),
  place_rate       DECIMAL(5,1),
  win_recovery     DECIMAL(6,1),
  place_recovery   DECIMAL(6,1),
  updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (factor_type, factor_value)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS T_FURI_SCORE (
  course_code      CHAR(2)          NOT NULL,
  year_code        CHAR(2)          NOT NULL,
  kai              CHAR(2)          NOT NULL,
  day_code         CHAR(1)          NOT NULL,
  race_num         CHAR(2)          NOT NULL,
  uma_num          TINYINT UNSIGNED NOT NULL,
  prev_furi_degree TINYINT UNSIGNED COMMENT '前走の不利度(0=なし、3=3以上に丸め)',
  prev_furi_phase  CHAR(3)          COMMENT '前走不利のタイミング(前/中/後、複数該当時は後>中>前を優先)',
  is_hot           TINYINT(1)       COMMENT '他指標(EX指数コース≧100/上がり指数1-3位/仕上指数≧70/情報印1-2)で既に高評価か',
  score            DECIMAL(7,1)     COMMENT 'セグメント単勝回収率-全体平均。is_hot=1のときは常に0',
  grade            CHAR(1)          COMMENT 'A:高評価 B:中立 C:効果薄(不利なし or 既に他指標で高評価)',
  updated_at       DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (course_code, year_code, kai, day_code, race_num, uma_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 前走リンク（T_KYI.prev1_seiseki_key = 血統登録番号8桁+年月日8桁）でT_SEDを引く際、
-- blood_num単体にインデックスがないとフルスキャンになり致命的に遅い（243,821件の母集団構築で数分〜停止級）。
-- 冪等に一度だけ作成する（2回目以降のETL実行では既存インデックスをそのまま再利用し、コストは発生しない）。
SET @idx_exists = (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'T_SED' AND INDEX_NAME = 'idx_sed_blood_ymd'
);
SET @ddl_idx = IF(@idx_exists = 0, 'CREATE INDEX idx_sed_blood_ymd ON T_SED(blood_num, ymd)', 'SELECT 1');
PREPARE stmt_idx FROM @ddl_idx;
EXECUTE stmt_idx;
DEALLOCATE PREPARE stmt_idx;

-- ============================================================
-- Part 2: ファクター集計（過去の実績からセグメント別回収率を算出）
-- ============================================================
-- 【重要】TRUNCATE + INSERT ではなく「別名で新規構築→完成後に原子的にRENAMEで差し替え」方式にする
-- （sql/blinker_index.sqlと同じ理由。ETL中断でライブテーブルが壊れて放置される事故を構造的に防ぐ）。
DROP TABLE IF EXISTS T_FURI_FACTOR_AGG_NEW;
CREATE TABLE T_FURI_FACTOR_AGG_NEW LIKE T_FURI_FACTOR_AGG;

DROP TABLE IF EXISTS tmp_fi_base;
CREATE TABLE tmp_fi_base AS
SELECT
  COALESCE(CAST(TRIM(fin.win)   AS UNSIGNED), 0) AS win_pay,
  COALESCE(CAST(TRIM(fin.place) AS UNSIGNED), 0) AS place_pay,
  LEAST(COALESCE(CAST(NULLIF(TRIM(ps.furi), '') AS UNSIGNED), 0), 3) AS trouble_bucket,
  IF(COALESCE(CAST(NULLIF(TRIM(ps.furi), '') AS UNSIGNED), 0) > 0, 1, 0) AS trouble_flag,
  IF(
       (k.kijun_odds >= 10 AND ans.course_score >= 100)
    OR (CAST(NULLIF(TRIM(k.agari_index_juni), '') AS UNSIGNED) BETWEEN 1 AND 3)
    OR (CAST(NULLIF(TRIM(cy.shiage_index), '') AS UNSIGNED) >= 70)
    OR (CAST(NULLIF(TRIM(k.in_joho), '') AS UNSIGNED) BETWEEN 1 AND 2)
  , 1, 0) AS hot_flag
FROM T_KYI k
INNER JOIN T_BAC b
  ON  b.course_code=k.course_code AND b.year_code=k.year_code
  AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN T_SED fin
  ON  fin.course_code=k.course_code AND fin.year_code=k.year_code
  AND fin.kai=k.kai AND fin.day_code=k.day_code
  AND fin.race_num=k.race_num AND fin.umaban=k.uma_num
  AND fin.ijou_kubun IN ('0','')
LEFT JOIN T_SED ps
  ON  ps.blood_num = LEFT(k.prev1_seiseki_key, 8)
  AND ps.ymd       = RIGHT(k.prev1_seiseki_key, 8)
LEFT JOIN T_ANABA_SCORE ans
  ON  ans.course_code=k.course_code AND ans.year_code=k.year_code
  AND ans.kai=k.kai AND ans.day_code=k.day_code AND ans.race_num=k.race_num AND ans.uma_num=k.uma_num
LEFT JOIN T_CYB cy
  ON  cy.course_code=k.course_code AND cy.year_code=k.year_code
  AND cy.kai=k.kai AND cy.day_code=k.day_code AND cy.race_num=k.race_num AND cy.uma_num=k.uma_num
WHERE b.`class` <> 'A1' AND b.tds_code <> '3'
  AND k.prev1_seiseki_key IS NOT NULL AND k.prev1_seiseki_key <> '';

INSERT INTO T_FURI_FACTOR_AGG_NEW
  (factor_type, factor_value, total_count, win_count, place_count, win_payout_sum, place_payout_sum, win_rate, place_rate, win_recovery, place_recovery)
SELECT 'baseline', 'all',
  COUNT(*), SUM(win_pay>0), SUM(place_pay>0), SUM(win_pay), SUM(place_pay),
  ROUND(SUM(win_pay>0)/COUNT(*)*100,1), ROUND(SUM(place_pay>0)/COUNT(*)*100,1),
  ROUND(SUM(win_pay)/COUNT(*),1), ROUND(SUM(place_pay)/COUNT(*),1)
FROM tmp_fi_base;

INSERT INTO T_FURI_FACTOR_AGG_NEW
  (factor_type, factor_value, total_count, win_count, place_count, win_payout_sum, place_payout_sum, win_rate, place_rate, win_recovery, place_recovery)
SELECT 'fine', CONCAT(trouble_bucket, '_h', hot_flag),
  COUNT(*), SUM(win_pay>0), SUM(place_pay>0), SUM(win_pay), SUM(place_pay),
  ROUND(SUM(win_pay>0)/COUNT(*)*100,1), ROUND(SUM(place_pay>0)/COUNT(*)*100,1),
  ROUND(SUM(win_pay)/COUNT(*),1), ROUND(SUM(place_pay)/COUNT(*),1)
FROM tmp_fi_base
GROUP BY trouble_bucket, hot_flag;

INSERT INTO T_FURI_FACTOR_AGG_NEW
  (factor_type, factor_value, total_count, win_count, place_count, win_payout_sum, place_payout_sum, win_rate, place_rate, win_recovery, place_recovery)
SELECT 'coarse', CONCAT(trouble_flag, '_h', hot_flag),
  COUNT(*), SUM(win_pay>0), SUM(place_pay>0), SUM(win_pay), SUM(place_pay),
  ROUND(SUM(win_pay>0)/COUNT(*)*100,1), ROUND(SUM(place_pay>0)/COUNT(*)*100,1),
  ROUND(SUM(win_pay)/COUNT(*),1), ROUND(SUM(place_pay)/COUNT(*),1)
FROM tmp_fi_base
GROUP BY trouble_flag, hot_flag;

DROP TABLE tmp_fi_base;

-- 原子的に差し替え
DROP TABLE IF EXISTS T_FURI_FACTOR_AGG_OLD;
RENAME TABLE T_FURI_FACTOR_AGG TO T_FURI_FACTOR_AGG_OLD, T_FURI_FACTOR_AGG_NEW TO T_FURI_FACTOR_AGG;
DROP TABLE T_FURI_FACTOR_AGG_OLD;

-- ============================================================
-- Part 3: 出走馬のスコア計算
-- ============================================================
-- 【重要】スコア算出対象は「前走の不利度」（前走=既に確定済みの過去レース）と
-- 「今回レースの他ファクター」（EX指数コース・上がり指数順位・仕上指数・情報印。いずれもレース前に判明）のみ。
-- 今回レースのT_SED（着順・払戻）には一切依存しない。T_KYI×T_BACのみで母集団を作るため、
-- 結果未確定の出走予定馬もスコアが漏れない（sql/blinker_index.sqlと同じ理由・同じ対策）。
DROP TABLE IF EXISTS T_FURI_SCORE_NEW;
CREATE TABLE T_FURI_SCORE_NEW LIKE T_FURI_SCORE;

DROP TABLE IF EXISTS tmp_fi_entries;
CREATE TABLE tmp_fi_entries AS
SELECT
  k.course_code, k.year_code, k.kai, k.day_code, k.race_num, k.uma_num,
  LEAST(COALESCE(CAST(NULLIF(TRIM(ps.furi), '') AS UNSIGNED), 0), 3) AS trouble_bucket,
  CASE
    WHEN ps.ushiro_furi IS NOT NULL AND TRIM(ps.ushiro_furi) <> '' THEN '後'
    WHEN ps.naka_furi   IS NOT NULL AND TRIM(ps.naka_furi)   <> '' THEN '中'
    WHEN ps.mae_furi    IS NOT NULL AND TRIM(ps.mae_furi)    <> '' THEN '前'
    ELSE NULL
  END AS trouble_phase,
  IF(
       (k.kijun_odds >= 10 AND ans.course_score >= 100)
    OR (CAST(NULLIF(TRIM(k.agari_index_juni), '') AS UNSIGNED) BETWEEN 1 AND 3)
    OR (CAST(NULLIF(TRIM(cy.shiage_index), '') AS UNSIGNED) >= 70)
    OR (CAST(NULLIF(TRIM(k.in_joho), '') AS UNSIGNED) BETWEEN 1 AND 2)
  , 1, 0) AS hot_flag
FROM T_KYI k
INNER JOIN T_BAC b
  ON  b.course_code=k.course_code AND b.year_code=k.year_code
  AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
LEFT JOIN T_SED ps
  ON  ps.blood_num = LEFT(k.prev1_seiseki_key, 8)
  AND ps.ymd       = RIGHT(k.prev1_seiseki_key, 8)
LEFT JOIN T_ANABA_SCORE ans
  ON  ans.course_code=k.course_code AND ans.year_code=k.year_code
  AND ans.kai=k.kai AND ans.day_code=k.day_code AND ans.race_num=k.race_num AND ans.uma_num=k.uma_num
LEFT JOIN T_CYB cy
  ON  cy.course_code=k.course_code AND cy.year_code=k.year_code
  AND cy.kai=k.kai AND cy.day_code=k.day_code AND cy.race_num=k.race_num AND cy.uma_num=k.uma_num
WHERE b.`class` <> 'A1' AND b.tds_code <> '3'
  AND k.prev1_seiseki_key IS NOT NULL AND k.prev1_seiseki_key <> '';

INSERT INTO T_FURI_SCORE_NEW
  (course_code, year_code, kai, day_code, race_num, uma_num, prev_furi_degree, prev_furi_phase, is_hot, score, grade)
SELECT
  course_code, year_code, kai, day_code, race_num, uma_num,
  trouble_bucket, trouble_phase, hot_flag,
  ROUND(final_score, 1),
  CASE WHEN final_score >= 20 THEN 'A' WHEN final_score > 0 THEN 'B' ELSE 'C' END
FROM (
  -- 【重要】前走不利度(fine=0/1/2/3別)でスコアを分けると、度数2のセグメントだけ
  -- n=639と小さく回収率が逆転する（ノイズの可能性が高い）ため、粒度は「不利あり/なし」の
  -- coarse集計のみを採用する（大サンプルで頑健、blinker指数のscore>=30/<=-16と同じく
  -- 「連続値の解像度は低いがgradeとしては信頼できる」という前例に倣う）。
  -- fine集計はT_FURI_FACTOR_AGGに保持し、将来の度数別チューニング検討用に残す。
  SELECT e.course_code, e.year_code, e.kai, e.day_code, e.race_num, e.uma_num,
    e.trouble_bucket, e.trouble_phase, e.hot_flag,
    CASE
      WHEN e.hot_flag = 1 THEN 0
      WHEN coarse.total_count >= 50 THEN coarse.win_recovery - bl.win_recovery
      ELSE 0
    END AS final_score
  FROM tmp_fi_entries e
  JOIN T_FURI_FACTOR_AGG bl
    ON  bl.factor_type='baseline' AND bl.factor_value='all'
  LEFT JOIN T_FURI_FACTOR_AGG coarse
    ON  coarse.factor_type='coarse' AND coarse.factor_value = CONCAT(IF(e.trouble_bucket>0,1,0), '_h', e.hot_flag)
) x;

DROP TABLE tmp_fi_entries;

-- 原子的に差し替え
DROP TABLE IF EXISTS T_FURI_SCORE_OLD;
RENAME TABLE T_FURI_SCORE TO T_FURI_SCORE_OLD, T_FURI_SCORE_NEW TO T_FURI_SCORE;
DROP TABLE T_FURI_SCORE_OLD;

-- ============================================================
-- 検証用SELECT（mysql CLIで直接実行した場合の確認用）
-- 【重要】"-- Part N:"マーカーではないため、server.ts の splitSqlByParts では
-- Part3に含まれたまま実行される（出力は破棄される）。POST /api/furi-etl 経由では
-- server.ts側で同内容のカバレッジチェックを別途pool.queryで行い、結果を画面に表示する
-- （sql/blinker_index.sqlのカバレッジチェックと同じ方式）。
-- ============================================================
SELECT
  (SELECT COUNT(*) FROM T_KYI k
   INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
   WHERE b.`class` <> 'A1' AND b.tds_code <> '3'
     AND k.prev1_seiseki_key IS NOT NULL AND k.prev1_seiseki_key <> '') AS population,
  (SELECT COUNT(*) FROM T_FURI_SCORE) AS score_rows;

SELECT grade, COUNT(*) AS cnt, ROUND(AVG(score),1) AS avg_score FROM T_FURI_SCORE GROUP BY grade ORDER BY grade;
