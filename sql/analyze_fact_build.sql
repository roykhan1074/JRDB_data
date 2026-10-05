-- src/server.ts の /api/analyze-fact-etl と同じ処理（サーバーを通さず実行する用。別名テーブル→原子的RENAME）
-- 実行: mysql --default-character-set=utf8mb4 -u root -p racing < sql/analyze_fact_build.sql
-- 2026-10-04作成。サーバー経由のETLが実行途中でサーバーごと再起動し、DROP済みでテーブルが空/消失する事故が2回連続で起きたため
SET SESSION wait_timeout = 3600;
DROP TABLE IF EXISTS T_ANALYZE_FACT_NEW;
CREATE TABLE T_ANALYZE_FACT_NEW (
      course_code       CHAR(2)           NOT NULL,
      year_code         CHAR(2)           NOT NULL,
      kai               CHAR(2)           NOT NULL,
      day_code          CHAR(1)           NOT NULL,
      race_num          CHAR(2)           NOT NULL,
      uma_num           TINYINT UNSIGNED  NOT NULL,
      ymd               CHAR(8)           NOT NULL,
      tds_code          CHAR(1)           NOT NULL,
      distance          SMALLINT UNSIGNED NOT NULL DEFAULT 0,
      class_code        CHAR(2)           NOT NULL DEFAULT '',
      waku_num          TINYINT UNSIGNED,
      kijun_odds        DECIMAL(7,1),
      kijun_ninki       TINYINT UNSIGNED,
      in_joho           TINYINT UNSIGNED,
      goal_juni         TINYINT UNSIGNED,
      in_idm            TINYINT UNSIGNED,
      idm               DECIMAL(6,1),
      kyusha_index      DECIMAL(6,1),
      ten_index_juni    TINYINT UNSIGNED,
      agari_index_juni  TINYINT UNSIGNED,
      kishu_name        VARCHAR(20),
      trainer_name      VARCHAR(20),
      umanushi_name     VARCHAR(40),
      kyakushitsu       CHAR(1),
      order_of_finish   TINYINT UNSIGNED,
      win_pay           SMALLINT UNSIGNED,
      place_pay         SMALLINT UNSIGNED,
      oi_index          SMALLINT UNSIGNED,
      shiage_index      SMALLINT UNSIGNED,
      ex_overall        DECIMAL(7,1),
      ex_course         DECIMAL(7,1),
      honmei_overall    DECIMAL(7,1),
      honmei_course     DECIMAL(7,1),
      tenkai_score      DECIMAL(7,1),
      chokyo_sp         TINYINT,
      PRIMARY KEY (course_code, year_code, kai, day_code, race_num, uma_num),
      INDEX idx_af_ymd       (ymd),
      INDEX idx_af_tds_class (tds_code, class_code),
      INDEX idx_af_kishu     (kishu_name(10)),
      INDEX idx_af_trainer   (trainer_name(10))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ROW_FORMAT=COMPACT;
INSERT INTO T_ANALYZE_FACT_NEW
      WITH sp_raw AS (
        SELECT k2.course_code, k2.year_code, k2.kai, k2.day_code, k2.race_num, k2.uma_num,
          CAST(c2.oi_index     AS DECIMAL(6,1)) AS oi_val,
          CAST(c2.shiage_index AS DECIMAL(6,1)) AS shi_val,
          TRIM(k2.chokyo_yajirushi)             AS yj,
          TRIM(k2.hohbokusaki_rank)             AS hb,
          SUM(CASE WHEN CAST(c2.oi_index     AS DECIMAL(6,1)) > 0 THEN 1 ELSE 0 END) OVER w AS oi_cnt,
          SUM(CASE WHEN CAST(c2.shiage_index AS DECIMAL(6,1)) > 0 THEN 1 ELSE 0 END) OVER w AS shi_cnt,
          RANK() OVER (PARTITION BY k2.course_code,k2.year_code,k2.kai,k2.day_code,k2.race_num
                       ORDER BY CASE WHEN CAST(c2.oi_index AS DECIMAL(6,1)) > 0 THEN CAST(c2.oi_index AS DECIMAL(6,1)) END DESC) AS oi_rank,
          RANK() OVER (PARTITION BY k2.course_code,k2.year_code,k2.kai,k2.day_code,k2.race_num
                       ORDER BY CASE WHEN CAST(c2.shiage_index AS DECIMAL(6,1)) > 0 THEN CAST(c2.shiage_index AS DECIMAL(6,1)) END DESC) AS shi_rank,
          AVG(CASE WHEN CAST(c2.oi_index     AS DECIMAL(6,1)) > 0 THEN CAST(c2.oi_index     AS DECIMAL(6,1)) END) OVER w AS oi_avg,
          STDDEV_POP(CASE WHEN CAST(c2.oi_index AS DECIMAL(6,1)) > 0 THEN CAST(c2.oi_index AS DECIMAL(6,1)) END) OVER w AS oi_sd,
          AVG(CASE WHEN CAST(c2.shiage_index AS DECIMAL(6,1)) > 0 THEN CAST(c2.shiage_index AS DECIMAL(6,1)) END) OVER w AS shi_avg,
          STDDEV_POP(CASE WHEN CAST(c2.shiage_index AS DECIMAL(6,1)) > 0 THEN CAST(c2.shiage_index AS DECIMAL(6,1)) END) OVER w AS shi_sd
        FROM T_KYI k2
        LEFT JOIN T_CYB c2
          ON  c2.course_code=k2.course_code AND c2.year_code=k2.year_code
          AND c2.kai=k2.kai AND c2.day_code=k2.day_code AND c2.race_num=k2.race_num AND c2.uma_num=k2.uma_num
        WINDOW w AS (PARTITION BY k2.course_code,k2.year_code,k2.kai,k2.day_code,k2.race_num)
      ),
      sp_cte AS (
        SELECT course_code, year_code, kai, day_code, race_num, uma_num,
          CASE
            WHEN oi_cnt < 2 OR shi_cnt < 2
              OR oi_val IS NULL OR oi_val <= 0
              OR shi_val IS NULL OR shi_val <= 0 THEN NULL
            ELSE
              (CASE oi_rank WHEN 1 THEN 3 WHEN 2 THEN 2 WHEN 3 THEN 1 ELSE 0 END)
             +(CASE shi_rank WHEN 1 THEN 3 WHEN 2 THEN 2 WHEN 3 THEN 1 ELSE 0 END)
             +LEAST(0, ROUND((
                 CASE WHEN oi_sd  > 0 THEN (oi_val  - oi_avg)  / oi_sd  ELSE 0 END
                +CASE WHEN shi_sd > 0 THEN (shi_val - shi_avg) / shi_sd ELSE 0 END
               ) * 1.0, 0))
             +(CASE yj WHEN '4' THEN -2 WHEN '5' THEN -4 ELSE 0 END)
             +(CASE hb WHEN 'E' THEN -4 WHEN 'D' THEN -2 ELSE 0 END)
          END AS sp_score
        FROM sp_raw
      )
      SELECT
        b.course_code, b.year_code, b.kai, b.day_code, b.race_num,
        CAST(TRIM(k.uma_num)            AS UNSIGNED),
        b.ymd, b.tds_code,
        CAST(TRIM(b.distance)           AS UNSIGNED),
        b.`class`,
        CAST(TRIM(k.waku_num)           AS UNSIGNED),
        CAST(k.kijun_odds               AS DECIMAL(7,1)),
        CAST(k.kijun_ninki              AS UNSIGNED),
        CAST(k.in_joho                  AS UNSIGNED),
        CAST(k.goal_juni                AS UNSIGNED),
        CAST(k.in_idm                   AS UNSIGNED),
        CAST(k.idm                      AS DECIMAL(6,1)),
        CAST(k.kyusha_index             AS DECIMAL(6,1)),
        CAST(k.ten_index_juni           AS UNSIGNED),
        CAST(k.agari_index_juni         AS UNSIGNED),
        TRIM(k.kishu_name),
        TRIM(k.trainer_name),
        TRIM(k.umanushi_name),
        k.kyakushitsu,
        CAST(TRIM(fin.order_of_finish)  AS UNSIGNED),
        COALESCE(CAST(TRIM(fin.win)     AS UNSIGNED), 0),
        COALESCE(CAST(TRIM(fin.place)   AS UNSIGNED), 0),
        CAST(c.oi_index                 AS UNSIGNED),
        CAST(c.shiage_index             AS UNSIGNED),
        ans.overall_score, ans.course_score,
        hms.overall_score, hms.course_score,
        pfs.overall_score,
        sp.sp_score
      FROM t_bac b
      INNER JOIN t_kyi k
        ON  b.course_code = k.course_code AND b.year_code = k.year_code
        AND b.kai = k.kai AND b.day_code = k.day_code AND b.race_num = k.race_num
      INNER JOIN t_sed fin
        ON  k.course_code = fin.course_code AND k.year_code = fin.year_code
        AND k.kai = fin.kai AND k.day_code = fin.day_code
        AND k.race_num = fin.race_num AND k.uma_num = fin.umaban
        AND fin.ijou_kubun IN ('0','')
      LEFT JOIN t_cyb c
        ON  k.course_code = c.course_code AND k.year_code = c.year_code
        AND k.kai = c.kai AND k.day_code = c.day_code AND k.race_num = c.race_num AND k.uma_num = c.uma_num
      LEFT JOIN T_ANABA_SCORE ans ON k.course_code=ans.course_code AND k.year_code=ans.year_code AND k.kai=ans.kai AND k.day_code=ans.day_code AND k.race_num=ans.race_num AND k.uma_num=ans.uma_num
      LEFT JOIN T_HONMEI_SCORE hms ON k.course_code=hms.course_code AND k.year_code=hms.year_code AND k.kai=hms.kai AND k.day_code=hms.day_code AND k.race_num=hms.race_num AND k.uma_num=hms.uma_num
      LEFT JOIN T_PACEFIT_SCORE pfs ON k.course_code=pfs.course_code AND k.year_code=pfs.year_code AND k.kai=pfs.kai AND k.day_code=pfs.day_code AND k.race_num=pfs.race_num AND k.uma_num=pfs.uma_num
      LEFT JOIN sp_cte sp
        ON  k.course_code = sp.course_code AND k.year_code = sp.year_code
        AND k.kai = sp.kai AND k.day_code = sp.day_code AND k.race_num = sp.race_num
        AND k.uma_num = sp.uma_num
      WHERE b.`class` <> 'A1';
SELECT COUNT(*) AS new_cnt FROM T_ANALYZE_FACT_NEW;
-- 既存テーブルが無い場合（サーバー経由のETLが DROP 直後に落ちた場合など）にも対応する
CREATE TABLE IF NOT EXISTS T_ANALYZE_FACT LIKE T_ANALYZE_FACT_NEW;
DROP TABLE IF EXISTS T_ANALYZE_FACT_OLD;
RENAME TABLE T_ANALYZE_FACT TO T_ANALYZE_FACT_OLD, T_ANALYZE_FACT_NEW TO T_ANALYZE_FACT;
DROP TABLE T_ANALYZE_FACT_OLD;
-- 実行後はサーバーを再起動すること（分析画面の利用可否フラグ factTableReady が起動時に判定されるため）
