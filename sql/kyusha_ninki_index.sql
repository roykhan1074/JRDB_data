-- ============================================================
-- 厩舎穴指数（厩舎指数の帯 × 基準人気の帯）の区分表 T_KYUSHA_NINKI_AGG を作る
--
-- 2026-10-05 新規作成。仕様の正典: document/指数/【廃】厩舎穴指数_仕様書.md
-- 出馬表（entries.html 列#25「厩舎穴」）は、出走馬の厩舎指数・基準人気（どちらも T_KYI、レース前に確定）から
-- 区分を決め、この表の score を表示する。スコア計算は結果テーブルに依存しない（表を引くだけ）。
--
-- 区分: 厩舎指数 <0 / 0-8 / 8-15 / 15+（下限を含む）× 基準人気 1-5 / 6-8 / 9-10 / 11+
-- 対象: 芝・ダート、新馬戦(class A1)除外、着順あり、基準オッズ 1以上999未満、厩舎指数・基準人気が数値
-- 払戻: 正常完走（ijou_kubun '0' か空）の単勝・複勝払戻。それ以外は0円
-- 指数: その区分の「同じ年・同じ基準オッズ帯の平均を上回った複勝払戻」の平均 × n/(n+300)（縮小推定）
--       基準オッズ帯: 1,2,3,5,7,10,15,20,30,50,100,1000 倍で区切る
--
-- 書き込みは別名テーブル(_NEW)で構築 → 原子的RENAME（CLAUDE.md「指数/スコアETL実装時の必須チェック」2番）
-- 実行: mysql --default-character-set=utf8mb4 -u root -p racing < sql/kyusha_ninki_index.sql
--       または download.html の「sc・複勝妙味・厩舎穴指数の元データを更新する」ボタン
-- ============================================================

CREATE TABLE IF NOT EXISTS T_KYUSHA_NINKI_AGG (
  ki_band          VARCHAR(8)    NOT NULL COMMENT '厩舎指数の帯 <0/0-8/8-15/15+',
  ninki_band       VARCHAR(8)    NOT NULL COMMENT '基準人気の帯 1-5/6-8/9-10/11+',
  total_count      INT           NOT NULL COMMENT '頭数',
  place_count      INT           NOT NULL COMMENT '3着内数',
  win_recovery     DECIMAL(6,1)           COMMENT '単勝回収率(%)',
  place_recovery   DECIMAL(6,1)           COMMENT '複勝回収率(%)',
  base_place_rr    DECIMAL(6,1)           COMMENT '同じ年・同じ基準オッズ帯の平均複勝回収率(%)（頭数加重）',
  place_excess     DECIMAL(6,1)           COMMENT '同オッズ帯平均との差の平均(pt)',
  score            DECIMAL(6,1)           COMMENT '厩舎穴指数 = place_excess × n/(n+300)',
  from_ymd         CHAR(8)                COMMENT '集計期間の開始日',
  to_ymd           CHAR(8)                COMMENT '集計期間の終了日',
  updated_at       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (ki_band, ninki_band)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='厩舎穴指数 区分表';

DROP TABLE IF EXISTS T_KYUSHA_NINKI_WORK;
CREATE TABLE T_KYUSHA_NINKI_WORK AS
SELECT
  x.ymd,
  SUBSTRING(x.ymd, 1, 4) AS y,
  CASE WHEN x.odds < 2 THEN 1 WHEN x.odds < 3 THEN 2 WHEN x.odds < 5 THEN 3 WHEN x.odds < 7 THEN 4
       WHEN x.odds < 10 THEN 5 WHEN x.odds < 15 THEN 6 WHEN x.odds < 20 THEN 7 WHEN x.odds < 30 THEN 8
       WHEN x.odds < 50 THEN 9 WHEN x.odds < 100 THEN 10 ELSE 11 END AS ob,
  CASE WHEN x.ki < 0 THEN '<0' WHEN x.ki < 8 THEN '0-8' WHEN x.ki < 15 THEN '8-15' ELSE '15+' END AS ki_band,
  CASE WHEN x.ninki <= 5 THEN '1-5' WHEN x.ninki <= 8 THEN '6-8' WHEN x.ninki <= 10 THEN '9-10' ELSE '11+' END AS ninki_band,
  x.fin, x.win_pay, x.place_pay
FROM (
  SELECT
    b.ymd,
    CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1))   AS odds,
    CAST(TRIM(k.kyusha_index) AS DECIMAL(5,1)) AS ki,
    CAST(TRIM(k.kijun_ninki) AS UNSIGNED)      AS ninki,
    CAST(TRIM(s.order_of_finish) AS UNSIGNED)  AS fin,
    CASE WHEN TRIM(s.ijou_kubun) IN ('0','')
         THEN COALESCE(CAST(NULLIF(TRIM(s.win),'')   AS UNSIGNED), 0) ELSE 0 END AS win_pay,
    CASE WHEN TRIM(s.ijou_kubun) IN ('0','')
         THEN COALESCE(CAST(NULLIF(TRIM(s.place),'') AS UNSIGNED), 0) ELSE 0 END AS place_pay
  FROM T_KYI k
  INNER JOIN T_BAC b
    ON  b.course_code = k.course_code AND b.year_code = k.year_code
    AND b.kai = k.kai AND b.day_code = k.day_code AND b.race_num = k.race_num
  INNER JOIN T_SED s
    ON  s.course_code = k.course_code AND s.year_code = k.year_code
    AND s.kai = k.kai AND s.day_code = k.day_code
    AND s.race_num = k.race_num AND s.umaban = k.uma_num
  WHERE TRIM(b.tds_code) IN ('1','2')
    AND TRIM(b.`class`) <> 'A1'
    AND TRIM(s.order_of_finish) REGEXP '^[0-9]+$' AND CAST(TRIM(s.order_of_finish) AS UNSIGNED) > 0
    AND TRIM(k.kijun_odds) REGEXP '^[0-9]+(\\.[0-9]+)?$'
    AND CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1)) >= 1 AND CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1)) < 999
    AND TRIM(k.kyusha_index) REGEXP '^-?[0-9]+(\\.[0-9]+)?$'
    AND TRIM(k.kijun_ninki) REGEXP '^[0-9]+$' AND CAST(TRIM(k.kijun_ninki) AS UNSIGNED) >= 1
) x;

DROP TABLE IF EXISTS T_KYUSHA_NINKI_BASE;
CREATE TABLE T_KYUSHA_NINKI_BASE AS
SELECT y, ob, AVG(place_pay) AS base_place FROM T_KYUSHA_NINKI_WORK GROUP BY y, ob;

DROP TABLE IF EXISTS T_KYUSHA_NINKI_AGG_NEW;
CREATE TABLE T_KYUSHA_NINKI_AGG_NEW LIKE T_KYUSHA_NINKI_AGG;

INSERT INTO T_KYUSHA_NINKI_AGG_NEW
  (ki_band, ninki_band, total_count, place_count, win_recovery, place_recovery,
   base_place_rr, place_excess, score, from_ymd, to_ymd)
SELECT
  w.ki_band, w.ninki_band,
  COUNT(*),
  SUM(w.fin BETWEEN 1 AND 3),
  ROUND(AVG(w.win_pay), 1),
  ROUND(AVG(w.place_pay), 1),
  ROUND(AVG(bs.base_place), 1),
  ROUND(AVG(w.place_pay - bs.base_place), 1),
  ROUND(AVG(w.place_pay - bs.base_place) * COUNT(*) / (COUNT(*) + 300), 1),
  MIN(w.ymd), MAX(w.ymd)
FROM T_KYUSHA_NINKI_WORK w
INNER JOIN T_KYUSHA_NINKI_BASE bs ON bs.y = w.y AND bs.ob = w.ob
GROUP BY w.ki_band, w.ninki_band;

-- 整合性チェック: 区分表の合計頭数 = 対象頭数、区分数 = 16
SELECT
  (SELECT SUM(total_count) FROM T_KYUSHA_NINKI_AGG_NEW) AS agg_total,
  (SELECT COUNT(*) FROM T_KYUSHA_NINKI_WORK)            AS target_total,
  (SELECT COUNT(*) FROM T_KYUSHA_NINKI_AGG_NEW)         AS cells,
  (SELECT MAX(ymd) FROM T_KYUSHA_NINKI_WORK)            AS latest_result_ymd;

DROP TABLE IF EXISTS T_KYUSHA_NINKI_AGG_OLD;
RENAME TABLE T_KYUSHA_NINKI_AGG TO T_KYUSHA_NINKI_AGG_OLD, T_KYUSHA_NINKI_AGG_NEW TO T_KYUSHA_NINKI_AGG;
DROP TABLE T_KYUSHA_NINKI_AGG_OLD;
DROP TABLE IF EXISTS T_KYUSHA_NINKI_WORK;
DROP TABLE IF EXISTS T_KYUSHA_NINKI_BASE;
