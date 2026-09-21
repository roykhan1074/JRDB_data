-- ============================================================
-- ブリンカー指数 ETL
-- 設計・バックテスト: document/分析レポート/ブリンカー回収率傾向分析レポート.md
--                     document/指数/ブリンカー指数_仕様書.md
--
-- 対象: T_KYI.blinker IN ('1':初装着, '2':再装着) の馬のみ
-- score = Σ（各ファクターの"そのブリンカー種別内"での単勝回収率 − そのブリンカー種別の平均単勝回収率）
-- ファクター: コース適性(芝ダ×距離帯)・クラス・脚質・性別・ローテーション・枠番・IDM順位・テン指数順位・上がり指数順位
-- 基準オッズは指数に含めない（指数とオッズを独立にクロスチェックできるようにするため。EX指数/本命指数/コース回収率指数と同方針）
--
-- 【重要】バックテストにより、スコアは連続値としては中間帯の解像度が低いことが判明している。
-- 実用上は grade（A/B/C の3段階）を primary な出力として扱うこと（詳細は仕様書参照）。
-- ============================================================

-- ============================================================
-- Part 1: テーブル定義
-- ============================================================
CREATE TABLE IF NOT EXISTS T_BLINKER_FACTOR_AGG (
  blinker_type      VARCHAR(4)    NOT NULL COMMENT '1:初装着 2:再装着 ALL:プール(初+再合算、小標本フォールバック用)',
  factor_type       VARCHAR(20)   NOT NULL,
  factor_value      VARCHAR(10)   NOT NULL,
  total_count       INT           NOT NULL DEFAULT 0,
  win_count         INT           NOT NULL DEFAULT 0,
  place_count       INT           NOT NULL DEFAULT 0,
  win_payout_sum    BIGINT        NOT NULL DEFAULT 0,
  place_payout_sum  BIGINT        NOT NULL DEFAULT 0,
  win_rate          DECIMAL(5,1),
  place_rate        DECIMAL(5,1),
  win_recovery      DECIMAL(6,1),
  place_recovery    DECIMAL(6,1),
  updated_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (blinker_type, factor_type, factor_value)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS T_BLINKER_SCORE (
  course_code    CHAR(2)   NOT NULL,
  year_code      CHAR(2)   NOT NULL,
  kai            CHAR(2)   NOT NULL,
  day_code       CHAR(1)   NOT NULL,
  race_num       CHAR(2)   NOT NULL,
  uma_num        TINYINT UNSIGNED NOT NULL,
  blinker_type   CHAR(1)   NOT NULL COMMENT '1:初装着 2:再装着',
  score              DECIMAL(7,1),
  grade              CHAR(1)   COMMENT 'A:高評価(score>=30) B:中立(-15~29) C:低評価(score<=-16)',
  score_coursefit    DECIMAL(7,1),
  score_class        DECIMAL(7,1),
  score_kyaku        DECIMAL(7,1),
  score_sex          DECIMAL(7,1),
  score_rotation     DECIMAL(7,1),
  score_waku         DECIMAL(7,1),
  score_idm          DECIMAL(7,1),
  score_ten          DECIMAL(7,1),
  score_agari        DECIMAL(7,1),
  updated_at     DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (course_code, year_code, kai, day_code, race_num, uma_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- Part 2: ファクター集計（初装着/再装着別 + プール版）
-- ============================================================
-- 【重要】TRUNCATE + INSERT ではなく「別名で新規構築→完成後に原子的にRENAMEで差し替え」方式にする。
-- ETL実行中に接続やプロセスが（原因を問わず）中断した場合でも、ライブテーブルは
-- 常に直前の正常なデータを保持し続け、空のまま壊れた状態で放置されることがない。
-- （実際にTRUNCATE直後の中断でT_BLINKER_FACTOR_AGGが空になる事故が複数回発生したための対策）
DROP TABLE IF EXISTS T_BLINKER_FACTOR_AGG_NEW;
CREATE TABLE T_BLINKER_FACTOR_AGG_NEW LIKE T_BLINKER_FACTOR_AGG;

DROP TABLE IF EXISTS tmp_bi_base;
CREATE TABLE tmp_bi_base AS
SELECT
  k.course_code, k.year_code, k.kai, k.day_code, k.race_num, k.uma_num,
  k.blinker, b.tds_code, CAST(TRIM(b.distance) AS UNSIGNED) AS distance, b.class,
  k.kyakushitsu, k.seibetsu_code,
  CAST(TRIM(k.waku_num) AS UNSIGNED) AS waku_num,
  CAST(TRIM(k.rotation) AS UNSIGNED) AS rotation,
  CAST(TRIM(k.idm) AS DECIMAL(6,1)) AS idm,
  CAST(TRIM(k.ten_index_juni) AS UNSIGNED) AS ten_index_juni,
  CAST(TRIM(k.agari_index_juni) AS UNSIGNED) AS agari_index_juni,
  CAST(TRIM(fin.order_of_finish) AS UNSIGNED) AS order_of_finish,
  COALESCE(CAST(TRIM(fin.win) AS UNSIGNED),0) AS win_pay,
  COALESCE(CAST(TRIM(fin.place) AS UNSIGNED),0) AS place_pay
FROM T_KYI k
INNER JOIN T_BAC b
  ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN T_SED fin
  ON  fin.course_code=k.course_code AND fin.year_code=k.year_code AND fin.kai=k.kai
  AND fin.day_code=k.day_code AND fin.race_num=k.race_num AND fin.umaban=k.uma_num
  AND fin.ijou_kubun IN ('0','')
WHERE b.tds_code IN ('1','2') AND b.class <> 'A1';

-- レース内IDM順位
DROP TABLE IF EXISTS tmp_bi_idm_rank;
CREATE TABLE tmp_bi_idm_rank AS
SELECT course_code, year_code, kai, day_code, race_num, uma_num,
  RANK() OVER (PARTITION BY course_code, year_code, kai, day_code, race_num ORDER BY idm DESC) AS rnk
FROM tmp_bi_base WHERE idm IS NOT NULL;
CREATE INDEX idx_tbir ON tmp_bi_idm_rank(course_code, year_code, kai, day_code, race_num, uma_num);

ALTER TABLE tmp_bi_base ADD COLUMN idm_race_rank INT;
UPDATE tmp_bi_base t
JOIN tmp_bi_idm_rank r
  ON r.course_code=t.course_code AND r.year_code=t.year_code AND r.kai=t.kai
 AND r.day_code=t.day_code AND r.race_num=t.race_num AND r.uma_num=t.uma_num
SET t.idm_race_rank = r.rnk;
DROP TABLE tmp_bi_idm_rank;

ALTER TABLE tmp_bi_base
  ADD COLUMN v_coursefit VARCHAR(10),
  ADD COLUMN v_class VARCHAR(4),
  ADD COLUMN v_kyaku VARCHAR(2),
  ADD COLUMN v_sex VARCHAR(2),
  ADD COLUMN v_rotation VARCHAR(10),
  ADD COLUMN v_waku VARCHAR(2),
  ADD COLUMN v_idm VARCHAR(4),
  ADD COLUMN v_ten VARCHAR(4),
  ADD COLUMN v_agari VARCHAR(4);

UPDATE tmp_bi_base SET
  v_coursefit = CONCAT(tds_code, '_', CASE WHEN distance<1400 THEN 'S' WHEN distance<1800 THEN 'M' WHEN distance<2200 THEN 'I' ELSE 'L' END),
  v_class = class,
  v_kyaku = CASE WHEN kyakushitsu IN ('1','2','3','4') THEN kyakushitsu ELSE NULL END,
  v_sex = seibetsu_code,
  v_rotation = CASE WHEN rotation IS NULL THEN NULL WHEN rotation<=2 THEN 'R1' WHEN rotation<=8 THEN 'R2' ELSE 'R3' END,
  v_waku = CASE WHEN waku_num BETWEEN 1 AND 8 THEN CAST(waku_num AS CHAR) ELSE NULL END,
  v_idm  = CASE WHEN idm_race_rank IS NULL THEN NULL WHEN idm_race_rank=1 THEN 'I1' WHEN idm_race_rank<=3 THEN 'I2' WHEN idm_race_rank<=6 THEN 'I3' ELSE 'I4' END,
  v_ten  = CASE WHEN ten_index_juni IS NULL OR ten_index_juni=0 THEN NULL WHEN ten_index_juni=1 THEN 'T1' WHEN ten_index_juni<=3 THEN 'T2' WHEN ten_index_juni<=6 THEN 'T3' ELSE 'T4' END,
  v_agari= CASE WHEN agari_index_juni IS NULL OR agari_index_juni=0 THEN NULL WHEN agari_index_juni=1 THEN 'A1' WHEN agari_index_juni<=3 THEN 'A2' WHEN agari_index_juni<=6 THEN 'A3' ELSE 'A4' END;

ALTER TABLE tmp_bi_base CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE INDEX idx_tbb_blinker ON tmp_bi_base(blinker);

-- baseline（初装着/再装着それぞれの母集団平均、プール版）
INSERT INTO T_BLINKER_FACTOR_AGG_NEW (blinker_type, factor_type, factor_value, total_count, win_count, place_count, win_payout_sum, place_payout_sum, win_rate, place_rate, win_recovery, place_recovery)
SELECT blinker, 'baseline', 'all',
  COUNT(*), SUM(order_of_finish=1), SUM(order_of_finish<=3), SUM(win_pay), SUM(place_pay),
  ROUND(AVG(order_of_finish=1)*100,1), ROUND(AVG(order_of_finish<=3)*100,1), ROUND(AVG(win_pay),1), ROUND(AVG(place_pay),1)
FROM tmp_bi_base WHERE blinker IN ('1','2') GROUP BY blinker;

INSERT INTO T_BLINKER_FACTOR_AGG_NEW (blinker_type, factor_type, factor_value, total_count, win_count, place_count, win_payout_sum, place_payout_sum, win_rate, place_rate, win_recovery, place_recovery)
SELECT 'ALL', 'baseline', 'all',
  COUNT(*), SUM(order_of_finish=1), SUM(order_of_finish<=3), SUM(win_pay), SUM(place_pay),
  ROUND(AVG(order_of_finish=1)*100,1), ROUND(AVG(order_of_finish<=3)*100,1), ROUND(AVG(win_pay),1), ROUND(AVG(place_pay),1)
FROM tmp_bi_base WHERE blinker IN ('1','2');

-- 9ファクター × (初装着/再装着/プール)
INSERT INTO T_BLINKER_FACTOR_AGG_NEW (blinker_type, factor_type, factor_value, total_count, win_count, place_count, win_payout_sum, place_payout_sum, win_rate, place_rate, win_recovery, place_recovery)
SELECT btype, factor_type, factor_value,
  COUNT(*), SUM(order_of_finish=1), SUM(order_of_finish<=3), SUM(win_pay), SUM(place_pay),
  ROUND(AVG(order_of_finish=1)*100,1), ROUND(AVG(order_of_finish<=3)*100,1), ROUND(AVG(win_pay),1), ROUND(AVG(place_pay),1)
FROM (
  SELECT blinker btype, 'coursefit' factor_type, v_coursefit factor_value, order_of_finish, win_pay, place_pay FROM tmp_bi_base WHERE blinker IN ('1','2') AND v_coursefit IS NOT NULL
  UNION ALL SELECT 'ALL', 'coursefit', v_coursefit, order_of_finish, win_pay, place_pay FROM tmp_bi_base WHERE blinker IN ('1','2') AND v_coursefit IS NOT NULL
  UNION ALL SELECT blinker, 'class', v_class, order_of_finish, win_pay, place_pay FROM tmp_bi_base WHERE blinker IN ('1','2') AND v_class IS NOT NULL
  UNION ALL SELECT 'ALL', 'class', v_class, order_of_finish, win_pay, place_pay FROM tmp_bi_base WHERE blinker IN ('1','2') AND v_class IS NOT NULL
  UNION ALL SELECT blinker, 'kyaku', v_kyaku, order_of_finish, win_pay, place_pay FROM tmp_bi_base WHERE blinker IN ('1','2') AND v_kyaku IS NOT NULL
  UNION ALL SELECT 'ALL', 'kyaku', v_kyaku, order_of_finish, win_pay, place_pay FROM tmp_bi_base WHERE blinker IN ('1','2') AND v_kyaku IS NOT NULL
  UNION ALL SELECT blinker, 'sex', v_sex, order_of_finish, win_pay, place_pay FROM tmp_bi_base WHERE blinker IN ('1','2') AND v_sex IS NOT NULL
  UNION ALL SELECT 'ALL', 'sex', v_sex, order_of_finish, win_pay, place_pay FROM tmp_bi_base WHERE blinker IN ('1','2') AND v_sex IS NOT NULL
  UNION ALL SELECT blinker, 'rotation', v_rotation, order_of_finish, win_pay, place_pay FROM tmp_bi_base WHERE blinker IN ('1','2') AND v_rotation IS NOT NULL
  UNION ALL SELECT 'ALL', 'rotation', v_rotation, order_of_finish, win_pay, place_pay FROM tmp_bi_base WHERE blinker IN ('1','2') AND v_rotation IS NOT NULL
  UNION ALL SELECT blinker, 'waku', v_waku, order_of_finish, win_pay, place_pay FROM tmp_bi_base WHERE blinker IN ('1','2') AND v_waku IS NOT NULL
  UNION ALL SELECT 'ALL', 'waku', v_waku, order_of_finish, win_pay, place_pay FROM tmp_bi_base WHERE blinker IN ('1','2') AND v_waku IS NOT NULL
  UNION ALL SELECT blinker, 'idm', v_idm, order_of_finish, win_pay, place_pay FROM tmp_bi_base WHERE blinker IN ('1','2') AND v_idm IS NOT NULL
  UNION ALL SELECT 'ALL', 'idm', v_idm, order_of_finish, win_pay, place_pay FROM tmp_bi_base WHERE blinker IN ('1','2') AND v_idm IS NOT NULL
  UNION ALL SELECT blinker, 'ten', v_ten, order_of_finish, win_pay, place_pay FROM tmp_bi_base WHERE blinker IN ('1','2') AND v_ten IS NOT NULL
  UNION ALL SELECT 'ALL', 'ten', v_ten, order_of_finish, win_pay, place_pay FROM tmp_bi_base WHERE blinker IN ('1','2') AND v_ten IS NOT NULL
  UNION ALL SELECT blinker, 'agari', v_agari, order_of_finish, win_pay, place_pay FROM tmp_bi_base WHERE blinker IN ('1','2') AND v_agari IS NOT NULL
  UNION ALL SELECT 'ALL', 'agari', v_agari, order_of_finish, win_pay, place_pay FROM tmp_bi_base WHERE blinker IN ('1','2') AND v_agari IS NOT NULL
) t
GROUP BY btype, factor_type, factor_value;

-- 原子的に差し替え（RENAME TABLEは複数テーブルを1文で同時に改名でき、メタデータ操作のみで一瞬で完了する）
DROP TABLE IF EXISTS T_BLINKER_FACTOR_AGG_OLD;
RENAME TABLE T_BLINKER_FACTOR_AGG TO T_BLINKER_FACTOR_AGG_OLD, T_BLINKER_FACTOR_AGG_NEW TO T_BLINKER_FACTOR_AGG;
DROP TABLE T_BLINKER_FACTOR_AGG_OLD;

SELECT blinker_type, factor_type, COUNT(*) AS cnt FROM T_BLINKER_FACTOR_AGG GROUP BY blinker_type, factor_type ORDER BY blinker_type, factor_type;

DROP TABLE tmp_bi_base;

-- ============================================================
-- Part 3: 出走馬のスコア計算（blinker IN ('1','2') のみ）
-- ============================================================
-- 【重要】スコア算出に使うファクター（コース適性・クラス・脚質・性別・ローテーション・枠番・IDM/テン/上がり順位）は
-- すべてレース前に判明する情報であり、T_SED（着順・払戻）の存在を前提にしてはならない。
-- tmp_bi_base は Part2 のファクター集計（過去の回収率算出）専用で T_SED と INNER JOIN しているため、
-- ここでそのまま使うと「まだ結果が確定していない出走予定馬」がスコア計算から漏れてしまう
-- （出馬表は本来レース前の馬に表示するものなので、これは実用上致命的なバグになる）。
-- そのため、スコア対象の母集団は T_KYI×T_BAC のみで作り直す（T_SED不要）。
-- 【重要】こちらも TRUNCATE + INSERT ではなく別名構築→原子的RENAME方式にする（Part2と同じ理由）。
DROP TABLE IF EXISTS T_BLINKER_SCORE_NEW;
CREATE TABLE T_BLINKER_SCORE_NEW LIKE T_BLINKER_SCORE;

DROP TABLE IF EXISTS tmp_bi_entries;
CREATE TABLE tmp_bi_entries AS
SELECT
  k.course_code, k.year_code, k.kai, k.day_code, k.race_num, k.uma_num, k.blinker,
  b.tds_code, CAST(TRIM(b.distance) AS UNSIGNED) AS distance, b.class,
  k.kyakushitsu, k.seibetsu_code,
  CAST(TRIM(k.waku_num) AS UNSIGNED) AS waku_num,
  CAST(TRIM(k.rotation) AS UNSIGNED) AS rotation,
  CAST(TRIM(k.idm) AS DECIMAL(6,1)) AS idm,
  CAST(TRIM(k.ten_index_juni) AS UNSIGNED) AS ten_index_juni,
  CAST(TRIM(k.agari_index_juni) AS UNSIGNED) AS agari_index_juni
FROM T_KYI k
INNER JOIN T_BAC b
  ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
WHERE b.tds_code IN ('1','2') AND b.class <> 'A1';

DROP TABLE IF EXISTS tmp_bi_entries_idm_rank;
CREATE TABLE tmp_bi_entries_idm_rank AS
SELECT course_code, year_code, kai, day_code, race_num, uma_num,
  RANK() OVER (PARTITION BY course_code, year_code, kai, day_code, race_num ORDER BY idm DESC) AS rnk
FROM tmp_bi_entries WHERE idm IS NOT NULL;
CREATE INDEX idx_tbeir ON tmp_bi_entries_idm_rank(course_code, year_code, kai, day_code, race_num, uma_num);

ALTER TABLE tmp_bi_entries ADD COLUMN idm_race_rank INT;
UPDATE tmp_bi_entries t
JOIN tmp_bi_entries_idm_rank r
  ON r.course_code=t.course_code AND r.year_code=t.year_code AND r.kai=t.kai
 AND r.day_code=t.day_code AND r.race_num=t.race_num AND r.uma_num=t.uma_num
SET t.idm_race_rank = r.rnk;
DROP TABLE tmp_bi_entries_idm_rank;

ALTER TABLE tmp_bi_entries
  ADD COLUMN v_coursefit VARCHAR(10),
  ADD COLUMN v_class VARCHAR(4),
  ADD COLUMN v_kyaku VARCHAR(2),
  ADD COLUMN v_sex VARCHAR(2),
  ADD COLUMN v_rotation VARCHAR(10),
  ADD COLUMN v_waku VARCHAR(2),
  ADD COLUMN v_idm VARCHAR(4),
  ADD COLUMN v_ten VARCHAR(4),
  ADD COLUMN v_agari VARCHAR(4);

UPDATE tmp_bi_entries SET
  v_coursefit = CONCAT(tds_code, '_', CASE WHEN distance<1400 THEN 'S' WHEN distance<1800 THEN 'M' WHEN distance<2200 THEN 'I' ELSE 'L' END),
  v_class = class,
  v_kyaku = CASE WHEN kyakushitsu IN ('1','2','3','4') THEN kyakushitsu ELSE NULL END,
  v_sex = seibetsu_code,
  v_rotation = CASE WHEN rotation IS NULL THEN NULL WHEN rotation<=2 THEN 'R1' WHEN rotation<=8 THEN 'R2' ELSE 'R3' END,
  v_waku = CASE WHEN waku_num BETWEEN 1 AND 8 THEN CAST(waku_num AS CHAR) ELSE NULL END,
  v_idm  = CASE WHEN idm_race_rank IS NULL THEN NULL WHEN idm_race_rank=1 THEN 'I1' WHEN idm_race_rank<=3 THEN 'I2' WHEN idm_race_rank<=6 THEN 'I3' ELSE 'I4' END,
  v_ten  = CASE WHEN ten_index_juni IS NULL OR ten_index_juni=0 THEN NULL WHEN ten_index_juni=1 THEN 'T1' WHEN ten_index_juni<=3 THEN 'T2' WHEN ten_index_juni<=6 THEN 'T3' ELSE 'T4' END,
  v_agari= CASE WHEN agari_index_juni IS NULL OR agari_index_juni=0 THEN NULL WHEN agari_index_juni=1 THEN 'A1' WHEN agari_index_juni<=3 THEN 'A2' WHEN agari_index_juni<=6 THEN 'A3' ELSE 'A4' END;

ALTER TABLE tmp_bi_entries CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE INDEX idx_tbe_blinker ON tmp_bi_entries(blinker);

INSERT INTO T_BLINKER_SCORE_NEW
  (course_code, year_code, kai, day_code, race_num, uma_num, blinker_type,
   score, grade, score_coursefit, score_class, score_kyaku, score_sex, score_rotation, score_waku, score_idm, score_ten, score_agari)
SELECT
  course_code, year_code, kai, day_code, race_num, uma_num, blinker,
  (s_coursefit+s_class+s_kyaku+s_sex+s_rotation+s_waku+s_idm+s_ten+s_agari) AS sc_total,
  CASE WHEN (s_coursefit+s_class+s_kyaku+s_sex+s_rotation+s_waku+s_idm+s_ten+s_agari) >= 30 THEN 'A'
       WHEN (s_coursefit+s_class+s_kyaku+s_sex+s_rotation+s_waku+s_idm+s_ten+s_agari) <= -16 THEN 'C'
       ELSE 'B' END,
  s_coursefit, s_class, s_kyaku, s_sex, s_rotation, s_waku, s_idm, s_ten, s_agari
FROM (
  SELECT a.course_code, a.year_code, a.kai, a.day_code, a.race_num, a.uma_num, a.blinker,
    COALESCE(CASE WHEN fc.total_count>=30  THEN fc.win_recovery  - bl.win_recovery WHEN fcp.total_count  IS NOT NULL THEN fcp.win_recovery  - blp.win_recovery ELSE NULL END, 0) AS s_coursefit,
    COALESCE(CASE WHEN fcl.total_count>=30 THEN fcl.win_recovery - bl.win_recovery WHEN fclp.total_count IS NOT NULL THEN fclp.win_recovery - blp.win_recovery ELSE NULL END, 0) AS s_class,
    COALESCE(CASE WHEN fk.total_count>=30  THEN fk.win_recovery  - bl.win_recovery WHEN fkp.total_count  IS NOT NULL THEN fkp.win_recovery  - blp.win_recovery ELSE NULL END, 0) AS s_kyaku,
    COALESCE(CASE WHEN fs.total_count>=30  THEN fs.win_recovery  - bl.win_recovery WHEN fsp.total_count  IS NOT NULL THEN fsp.win_recovery  - blp.win_recovery ELSE NULL END, 0) AS s_sex,
    COALESCE(CASE WHEN fr.total_count>=30  THEN fr.win_recovery  - bl.win_recovery WHEN frp.total_count  IS NOT NULL THEN frp.win_recovery  - blp.win_recovery ELSE NULL END, 0) AS s_rotation,
    COALESCE(CASE WHEN fw.total_count>=30  THEN fw.win_recovery  - bl.win_recovery WHEN fwp.total_count  IS NOT NULL THEN fwp.win_recovery  - blp.win_recovery ELSE NULL END, 0) AS s_waku,
    COALESCE(CASE WHEN fi.total_count>=30  THEN fi.win_recovery  - bl.win_recovery WHEN fip.total_count  IS NOT NULL THEN fip.win_recovery  - blp.win_recovery ELSE NULL END, 0) AS s_idm,
    COALESCE(CASE WHEN ft.total_count>=30  THEN ft.win_recovery  - bl.win_recovery WHEN ftp.total_count  IS NOT NULL THEN ftp.win_recovery  - blp.win_recovery ELSE NULL END, 0) AS s_ten,
    COALESCE(CASE WHEN fa.total_count>=30  THEN fa.win_recovery  - bl.win_recovery WHEN fap.total_count  IS NOT NULL THEN fap.win_recovery  - blp.win_recovery ELSE NULL END, 0) AS s_agari
  FROM tmp_bi_entries a
  JOIN T_BLINKER_FACTOR_AGG bl  ON bl.blinker_type=a.blinker AND bl.factor_type='baseline' AND bl.factor_value='all'
  JOIN T_BLINKER_FACTOR_AGG blp ON blp.blinker_type='ALL'    AND blp.factor_type='baseline' AND blp.factor_value='all'
  LEFT JOIN T_BLINKER_FACTOR_AGG fc   ON fc.blinker_type=a.blinker  AND fc.factor_type='coursefit'  AND fc.factor_value=a.v_coursefit
  LEFT JOIN T_BLINKER_FACTOR_AGG fcp  ON fcp.blinker_type='ALL'     AND fcp.factor_type='coursefit' AND fcp.factor_value=a.v_coursefit
  LEFT JOIN T_BLINKER_FACTOR_AGG fcl  ON fcl.blinker_type=a.blinker AND fcl.factor_type='class'      AND fcl.factor_value=a.v_class
  LEFT JOIN T_BLINKER_FACTOR_AGG fclp ON fclp.blinker_type='ALL'    AND fclp.factor_type='class'     AND fclp.factor_value=a.v_class
  LEFT JOIN T_BLINKER_FACTOR_AGG fk   ON fk.blinker_type=a.blinker  AND fk.factor_type='kyaku'       AND fk.factor_value=a.v_kyaku
  LEFT JOIN T_BLINKER_FACTOR_AGG fkp  ON fkp.blinker_type='ALL'     AND fkp.factor_type='kyaku'      AND fkp.factor_value=a.v_kyaku
  LEFT JOIN T_BLINKER_FACTOR_AGG fs   ON fs.blinker_type=a.blinker  AND fs.factor_type='sex'         AND fs.factor_value=a.v_sex
  LEFT JOIN T_BLINKER_FACTOR_AGG fsp  ON fsp.blinker_type='ALL'     AND fsp.factor_type='sex'        AND fsp.factor_value=a.v_sex
  LEFT JOIN T_BLINKER_FACTOR_AGG fr   ON fr.blinker_type=a.blinker  AND fr.factor_type='rotation'    AND fr.factor_value=a.v_rotation
  LEFT JOIN T_BLINKER_FACTOR_AGG frp  ON frp.blinker_type='ALL'     AND frp.factor_type='rotation'   AND frp.factor_value=a.v_rotation
  LEFT JOIN T_BLINKER_FACTOR_AGG fw   ON fw.blinker_type=a.blinker  AND fw.factor_type='waku'        AND fw.factor_value=a.v_waku
  LEFT JOIN T_BLINKER_FACTOR_AGG fwp  ON fwp.blinker_type='ALL'     AND fwp.factor_type='waku'       AND fwp.factor_value=a.v_waku
  LEFT JOIN T_BLINKER_FACTOR_AGG fi   ON fi.blinker_type=a.blinker  AND fi.factor_type='idm'         AND fi.factor_value=a.v_idm
  LEFT JOIN T_BLINKER_FACTOR_AGG fip  ON fip.blinker_type='ALL'     AND fip.factor_type='idm'        AND fip.factor_value=a.v_idm
  LEFT JOIN T_BLINKER_FACTOR_AGG ft   ON ft.blinker_type=a.blinker  AND ft.factor_type='ten'         AND ft.factor_value=a.v_ten
  LEFT JOIN T_BLINKER_FACTOR_AGG ftp  ON ftp.blinker_type='ALL'     AND ftp.factor_type='ten'        AND ftp.factor_value=a.v_ten
  LEFT JOIN T_BLINKER_FACTOR_AGG fa   ON fa.blinker_type=a.blinker  AND fa.factor_type='agari'       AND fa.factor_value=a.v_agari
  LEFT JOIN T_BLINKER_FACTOR_AGG fap  ON fap.blinker_type='ALL'     AND fap.factor_type='agari'      AND fap.factor_value=a.v_agari
  WHERE a.blinker IN ('1','2')
) x;

-- 原子的に差し替え
DROP TABLE IF EXISTS T_BLINKER_SCORE_OLD;
RENAME TABLE T_BLINKER_SCORE TO T_BLINKER_SCORE_OLD, T_BLINKER_SCORE_NEW TO T_BLINKER_SCORE;
DROP TABLE T_BLINKER_SCORE_OLD;

DROP TABLE tmp_bi_entries;

SELECT grade, COUNT(*) AS cnt, ROUND(AVG(score),1) AS avg_score FROM T_BLINKER_SCORE GROUP BY grade ORDER BY grade;
SELECT COUNT(*) AS total_score_rows FROM T_BLINKER_SCORE;

-- ============================================================
-- カバレッジ整合性チェック（必ず0件であること）
-- T_KYIでblinker IN ('1','2')な馬なのにT_BLINKER_SCOREに行がない馬を検出する。
-- 0件でなければ「スコア計算が結果テーブル(T_SED)等に依存してしまい、
-- まだ結果が出ていない馬が漏れている」典型的なバグの再発を意味する。
-- 詳細: document/指数/ブリンカー指数_仕様書.md §4.5
-- ============================================================
SELECT COUNT(*) AS coverage_gap_should_be_zero
FROM T_KYI k
INNER JOIN T_BAC b
  ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
LEFT JOIN T_BLINKER_SCORE bls
  ON  bls.course_code=k.course_code AND bls.year_code=k.year_code AND bls.kai=k.kai
  AND bls.day_code=k.day_code AND bls.race_num=k.race_num AND bls.uma_num=k.uma_num
WHERE k.blinker IN ('1','2') AND b.tds_code IN ('1','2') AND b.class <> 'A1' AND bls.grade IS NULL;
