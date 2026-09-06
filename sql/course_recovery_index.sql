-- ============================================================
-- コース回収率指数（ハイブリッド版）ETL
-- 設計: document/分析レポート/コース回収率指数_設計とバックテストレポート.md
--
-- score = Σ(各ファクターの"全体"単勝回収率 − 全体ベースライン)
--       + (そのコース(場×芝ダ×距離)の全馬平均単勝回収率 − 全体ベースライン)
--
-- 使用ファクター: 脚質・テン指数順位・上がり指数順位・IDM印・情報印・厩舎指数帯・枠番
-- （基準オッズ帯は市場評価との循環を避けるため加点要素に含めない。EX指数/本命指数と同方針）
-- コース側の項は既存 T_COURSE_FACTOR_AGG の baseline 行（factor_type='baseline'）を利用する。
-- ============================================================

-- ============================================================
-- Part 1: テーブル定義
-- ============================================================
CREATE TABLE IF NOT EXISTS T_COURSE_RECOVERY_FACTOR_AGG (
  factor_type       VARCHAR(20)   NOT NULL,
  factor_value      VARCHAR(20)   NOT NULL,
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
  PRIMARY KEY (factor_type, factor_value)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS T_COURSE_RECOVERY_SCORE (
  course_code   CHAR(2)   NOT NULL,
  year_code     CHAR(2)   NOT NULL,
  kai           CHAR(2)   NOT NULL,
  day_code      CHAR(1)   NOT NULL,
  race_num      CHAR(2)   NOT NULL,
  uma_num       TINYINT UNSIGNED NOT NULL,
  score              DECIMAL(7,1),
  score_kyaku        DECIMAL(7,1),
  score_ten          DECIMAL(7,1),
  score_agari        DECIMAL(7,1),
  score_idm          DECIMAL(7,1),
  score_joho         DECIMAL(7,1),
  score_kyusha       DECIMAL(7,1),
  score_waku         DECIMAL(7,1),
  score_course_base  DECIMAL(7,1),
  updated_at    DATETIME  NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (course_code, year_code, kai, day_code, race_num, uma_num)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- Part 2: 全体ファクター集計（コース非条件付け）
-- ============================================================
-- 【重要】TRUNCATE + INSERT ではなく「別名で新規構築→完成後に原子的にRENAMEで差し替え」方式にする。
-- ETL実行中に接続やプロセスが中断した場合でも、ライブテーブルは常に直前の正常なデータを
-- 保持し続け、空のまま壊れた状態で放置されることがない
-- （sql/blinker_index.sqlのETLで実際にTRUNCATE直後の中断により空テーブルのまま
--   放置される事故が複数回発生したため、同種のETL全てにこの対策を適用する）。
DROP TABLE IF EXISTS T_COURSE_RECOVERY_FACTOR_AGG_NEW;
CREATE TABLE T_COURSE_RECOVERY_FACTOR_AGG_NEW LIKE T_COURSE_RECOVERY_FACTOR_AGG;

INSERT INTO T_COURSE_RECOVERY_FACTOR_AGG_NEW
  (factor_type, factor_value, total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT 'baseline', 'all',
  COUNT(*), SUM(fin.f1), SUM(fin.f3), COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1,
  CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1';

INSERT INTO T_COURSE_RECOVERY_FACTOR_AGG_NEW
  (factor_type, factor_value, total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT 'kyaku', k.kyakushitsu,
  COUNT(*), SUM(fin.f1), SUM(fin.f3), COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1,
  CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1' AND k.kyakushitsu IN ('1','2','3','4')
GROUP BY k.kyakushitsu;

INSERT INTO T_COURSE_RECOVERY_FACTOR_AGG_NEW
  (factor_type, factor_value, total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT 'ten_rank',
  CASE WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED)=1 THEN '1'
       WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
       WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
       ELSE '7~' END,
  COUNT(*), SUM(fin.f1), SUM(fin.f3), COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1,
  CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1' AND TRIM(k.ten_index_juni)<>'' AND CAST(TRIM(k.ten_index_juni) AS UNSIGNED)>0
GROUP BY CASE WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED)=1 THEN '1' WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3' WHEN CAST(TRIM(k.ten_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6' ELSE '7~' END;

INSERT INTO T_COURSE_RECOVERY_FACTOR_AGG_NEW
  (factor_type, factor_value, total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT 'agari_rank',
  CASE WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED)=1 THEN '1'
       WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
       WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
       ELSE '7~' END,
  COUNT(*), SUM(fin.f1), SUM(fin.f3), COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1,
  CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1' AND TRIM(k.agari_index_juni)<>'' AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED)>0
GROUP BY CASE WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED)=1 THEN '1' WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3' WHEN CAST(TRIM(k.agari_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6' ELSE '7~' END;

INSERT INTO T_COURSE_RECOVERY_FACTOR_AGG_NEW
  (factor_type, factor_value, total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT 'idm_mark', TRIM(k.in_idm),
  COUNT(*), SUM(fin.f1), SUM(fin.f3), COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1,
  CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1' AND TRIM(k.in_idm) BETWEEN '1' AND '5'
GROUP BY TRIM(k.in_idm);

INSERT INTO T_COURSE_RECOVERY_FACTOR_AGG_NEW
  (factor_type, factor_value, total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT 'joho_mark', TRIM(k.in_joho),
  COUNT(*), SUM(fin.f1), SUM(fin.f3), COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1,
  CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1' AND TRIM(k.in_joho) BETWEEN '1' AND '5'
GROUP BY TRIM(k.in_joho);

INSERT INTO T_COURSE_RECOVERY_FACTOR_AGG_NEW
  (factor_type, factor_value, total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT 'kyusha',
  CASE WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= 20 THEN '20+'
       WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= 10 THEN '10~20'
       WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >=  0 THEN '0~10'
       WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= -10 THEN '-10~0'
       ELSE '-10mi' END,
  COUNT(*), SUM(fin.f1), SUM(fin.f3), COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1,
  CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1' AND TRIM(k.kyusha_index)<>''
GROUP BY CASE WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= 20 THEN '20+' WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= 10 THEN '10~20' WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >=  0 THEN '0~10' WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= -10 THEN '-10~0' ELSE '-10mi' END;

INSERT INTO T_COURSE_RECOVERY_FACTOR_AGG_NEW
  (factor_type, factor_value, total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT 'waku', TRIM(k.waku_num),
  COUNT(*), SUM(fin.f1), SUM(fin.f3), COALESCE(SUM(fin.win_amt),0), COALESCE(SUM(fin.place_amt),0),
  ROUND(SUM(fin.f1)/COUNT(*)*100,1), ROUND(SUM(fin.f3)/COUNT(*)*100,1),
  ROUND(COALESCE(SUM(fin.win_amt),0)/COUNT(*),1), ROUND(COALESCE(SUM(fin.place_amt),0)/COUNT(*),1)
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
INNER JOIN (SELECT course_code,year_code,kai,day_code,race_num,umaban,
  CAST(TRIM(order_of_finish) AS UNSIGNED)=1 AS f1,
  CAST(TRIM(order_of_finish) AS UNSIGNED) BETWEEN 1 AND 3 AS f3,
  CAST(TRIM(win) AS UNSIGNED) AS win_amt, CAST(TRIM(place) AS UNSIGNED) AS place_amt
  FROM T_SED WHERE ijou_kubun IN ('0','')) fin
  ON k.course_code=fin.course_code AND k.year_code=fin.year_code AND k.kai=fin.kai AND k.day_code=fin.day_code AND k.race_num=fin.race_num AND k.uma_num=fin.umaban
WHERE b.tds_code IN ('1','2') AND b.class<>'A1' AND TRIM(k.waku_num) BETWEEN '1' AND '8'
GROUP BY TRIM(k.waku_num);

-- 原子的に差し替え
DROP TABLE IF EXISTS T_COURSE_RECOVERY_FACTOR_AGG_OLD;
RENAME TABLE T_COURSE_RECOVERY_FACTOR_AGG TO T_COURSE_RECOVERY_FACTOR_AGG_OLD, T_COURSE_RECOVERY_FACTOR_AGG_NEW TO T_COURSE_RECOVERY_FACTOR_AGG;
DROP TABLE T_COURSE_RECOVERY_FACTOR_AGG_OLD;

SELECT factor_type, COUNT(*) AS cnt FROM T_COURSE_RECOVERY_FACTOR_AGG GROUP BY factor_type ORDER BY factor_type;

-- ============================================================
-- Part 3: 出走全馬のスコア計算 (T_COURSE_RECOVERY_SCORE)
-- ============================================================
-- 【重要】TRUNCATE + INSERT ではなく別名構築→原子的RENAME方式にする（sql/blinker_index.sqlと同じ理由）。
DROP TABLE IF EXISTS T_COURSE_RECOVERY_SCORE_NEW;
CREATE TABLE T_COURSE_RECOVERY_SCORE_NEW LIKE T_COURSE_RECOVERY_SCORE;

INSERT INTO T_COURSE_RECOVERY_SCORE_NEW
  (course_code, year_code, kai, day_code, race_num, uma_num,
   score, score_kyaku, score_ten, score_agari, score_idm, score_joho, score_kyusha, score_waku, score_course_base)
SELECT
  k.course_code, k.year_code, k.kai, k.day_code, k.race_num, CAST(TRIM(k.uma_num) AS UNSIGNED),
  COALESCE(fk.win_recovery - gbase.v, 0) + COALESCE(ft.win_recovery - gbase.v, 0) + COALESCE(fa.win_recovery - gbase.v, 0)
    + COALESCE(fi.win_recovery - gbase.v, 0) + COALESCE(fj.win_recovery - gbase.v, 0) + COALESCE(fy.win_recovery - gbase.v, 0)
    + COALESCE(fw.win_recovery - gbase.v, 0) + COALESCE(fcb.win_recovery - gbase.v, 0),
  fk.win_recovery - gbase.v, ft.win_recovery - gbase.v, fa.win_recovery - gbase.v, fi.win_recovery - gbase.v,
  fj.win_recovery - gbase.v, fy.win_recovery - gbase.v, fw.win_recovery - gbase.v, fcb.win_recovery - gbase.v
FROM T_KYI k
INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
CROSS JOIN (SELECT win_recovery AS v FROM T_COURSE_RECOVERY_FACTOR_AGG WHERE factor_type='baseline' AND factor_value='all') gbase
-- 各LEFT JOINは該当ファクター値がT_COURSE_RECOVERY_FACTOR_AGGに存在しなければ自動的にNULL
-- （未記入・非対象値のときはCOALESCEで0点扱いとなり、そのままフォールバックになる）
LEFT JOIN T_COURSE_RECOVERY_FACTOR_AGG fk
  ON fk.factor_type='kyaku' AND fk.factor_value = k.kyakushitsu
LEFT JOIN T_COURSE_RECOVERY_FACTOR_AGG ft
  ON ft.factor_type='ten_rank' AND ft.factor_value =
     CASE WHEN TRIM(k.ten_index_juni)<>'' AND CAST(TRIM(k.ten_index_juni) AS UNSIGNED)=1 THEN '1'
          WHEN TRIM(k.ten_index_juni)<>'' AND CAST(TRIM(k.ten_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
          WHEN TRIM(k.ten_index_juni)<>'' AND CAST(TRIM(k.ten_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
          WHEN TRIM(k.ten_index_juni)<>'' AND CAST(TRIM(k.ten_index_juni) AS UNSIGNED) > 0 THEN '7~'
          ELSE NULL END
LEFT JOIN T_COURSE_RECOVERY_FACTOR_AGG fa
  ON fa.factor_type='agari_rank' AND fa.factor_value =
     CASE WHEN TRIM(k.agari_index_juni)<>'' AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED)=1 THEN '1'
          WHEN TRIM(k.agari_index_juni)<>'' AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) BETWEEN 2 AND 3 THEN '2~3'
          WHEN TRIM(k.agari_index_juni)<>'' AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) BETWEEN 4 AND 6 THEN '4~6'
          WHEN TRIM(k.agari_index_juni)<>'' AND CAST(TRIM(k.agari_index_juni) AS UNSIGNED) > 0 THEN '7~'
          ELSE NULL END
LEFT JOIN T_COURSE_RECOVERY_FACTOR_AGG fi
  ON fi.factor_type='idm_mark' AND fi.factor_value = TRIM(k.in_idm) AND TRIM(k.in_idm) BETWEEN '1' AND '5'
LEFT JOIN T_COURSE_RECOVERY_FACTOR_AGG fj
  ON fj.factor_type='joho_mark' AND fj.factor_value = TRIM(k.in_joho) AND TRIM(k.in_joho) BETWEEN '1' AND '5'
LEFT JOIN T_COURSE_RECOVERY_FACTOR_AGG fy
  ON fy.factor_type='kyusha' AND fy.factor_value =
     CASE WHEN TRIM(k.kyusha_index)='' THEN NULL
          WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= 20 THEN '20+'
          WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= 10 THEN '10~20'
          WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >=  0 THEN '0~10'
          WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(6,1)) >= -10 THEN '-10~0'
          ELSE '-10mi' END
LEFT JOIN T_COURSE_RECOVERY_FACTOR_AGG fw
  ON fw.factor_type='waku' AND fw.factor_value = TRIM(k.waku_num) AND TRIM(k.waku_num) BETWEEN '1' AND '8'
LEFT JOIN T_COURSE_FACTOR_AGG fcb
  ON fcb.factor_type='baseline' AND fcb.factor_value='all'
 AND fcb.course_code=b.course_code AND fcb.tds_code=b.tds_code AND fcb.distance=TRIM(b.distance)
WHERE b.tds_code IN ('1','2') AND b.class<>'A1';

-- 原子的に差し替え
DROP TABLE IF EXISTS T_COURSE_RECOVERY_SCORE_OLD;
RENAME TABLE T_COURSE_RECOVERY_SCORE TO T_COURSE_RECOVERY_SCORE_OLD, T_COURSE_RECOVERY_SCORE_NEW TO T_COURSE_RECOVERY_SCORE;
DROP TABLE T_COURSE_RECOVERY_SCORE_OLD;

SELECT COUNT(*) AS score_rows FROM T_COURSE_RECOVERY_SCORE;

-- ============================================================
-- カバレッジ整合性チェック（必ず0件であること）
-- 出走全馬（tds1/2・class<>A1）に対してスコア漏れがないか確認する。
-- 0件でなければ、スコア計算が結果テーブル等に依存してしまい未実施レースの馬が
-- 漏れている典型的なバグを意味する（sql/blinker_index.sqlで実際に発生した前例あり）。
-- ============================================================
SELECT COUNT(*) AS coverage_gap_should_be_zero
FROM T_KYI k
INNER JOIN T_BAC b
  ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
LEFT JOIN T_COURSE_RECOVERY_SCORE crs
  ON  crs.course_code=k.course_code AND crs.year_code=k.year_code AND crs.kai=k.kai
  AND crs.day_code=k.day_code AND crs.race_num=k.race_num AND crs.uma_num=CAST(TRIM(k.uma_num) AS UNSIGNED)
WHERE b.tds_code IN ('1','2') AND b.class <> 'A1' AND crs.score IS NULL;
