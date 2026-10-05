-- ============================================================
-- 騎手×調教師 成績集計（T_COMBO_RECOVERY）の再構築
--
-- 2026-10-04 新規作成。T_COMBO_RECOVERY は 2026-04-30 に一度だけ作られたまま、作成スクリプトも
-- リポジトリに無く更新されていなかった（成績は2026年4月以前のまま）。
-- 利用箇所: sc（注目馬複合シグナル）の「騎手×厩舎」シグナル、複勝妙味シグナルの scCombo、
--           出馬表の騎×厩表示（combo_win_rr / combo_place_rr / combo_n）
--
-- 定義（sc の先読みなし検証 python/research/sc_wf.js で使った「その日より前の累積」と同じ母集団）:
--   対象   : 芝・ダート（tds_code 1/2）の全クラス、着順が付いた馬（取消・除外は対象外）
--   払戻   : 正常に完走した馬（ijou_kubun が '0' か空）の単勝・複勝払戻。それ以外は0円
--   回収率 : 払戻合計 ÷ 頭数（100円あたりの払戻 = %）
-- 出走前のレースには「全期間（今日まで）の成績」を使う。未来の結果は含まれない。
--
-- 書き込みは別名テーブル(_NEW)で構築 → 原子的RENAME（CLAUDE.md「指数/スコアETL実装時の必須チェック」2番）
-- 実行: mysql --default-character-set=utf8mb4 -u root -p racing < sql/combo_recovery.sql
--       または download.html の「sc・複勝妙味の元データを更新する」ボタン
-- ============================================================

DROP TABLE IF EXISTS T_COMBO_RECOVERY_NEW;
CREATE TABLE T_COMBO_RECOVERY_NEW LIKE T_COMBO_RECOVERY;

INSERT INTO T_COMBO_RECOVERY_NEW
  (kishu_code, trainer_code, kishu_name, trainer_name,
   total_count, win_count, place_count, win_payout_sum, place_payout_sum,
   win_rate, place_rate, win_recovery, place_recovery)
SELECT
  x.kishu_code, x.trainer_code, MAX(x.kishu_name), MAX(x.trainer_name),
  COUNT(*),
  SUM(x.fin = 1),
  SUM(x.fin BETWEEN 1 AND 3),
  SUM(x.win_pay),
  SUM(x.place_pay),
  ROUND(SUM(x.fin = 1) / COUNT(*) * 100, 1),
  ROUND(SUM(x.fin BETWEEN 1 AND 3) / COUNT(*) * 100, 1),
  ROUND(SUM(x.win_pay) / COUNT(*), 1),
  ROUND(SUM(x.place_pay) / COUNT(*), 1)
FROM (
  SELECT
    TRIM(k.kishu_code)   AS kishu_code,
    TRIM(k.trainer_code) AS trainer_code,
    TRIM(k.kishu_name)   AS kishu_name,
    TRIM(k.trainer_name) AS trainer_name,
    CAST(TRIM(s.order_of_finish) AS UNSIGNED) AS fin,
    CASE WHEN s.ijou_kubun IN ('0','') THEN COALESCE(CAST(TRIM(s.win)   AS UNSIGNED), 0) ELSE 0 END AS win_pay,
    CASE WHEN s.ijou_kubun IN ('0','') THEN COALESCE(CAST(TRIM(s.place) AS UNSIGNED), 0) ELSE 0 END AS place_pay
  FROM T_KYI k
  INNER JOIN T_BAC b
    ON  b.course_code = k.course_code AND b.year_code = k.year_code
    AND b.kai = k.kai AND b.day_code = k.day_code AND b.race_num = k.race_num
  INNER JOIN T_SED s
    ON  s.course_code = k.course_code AND s.year_code = k.year_code
    AND s.kai = k.kai AND s.day_code = k.day_code
    AND s.race_num = k.race_num AND s.umaban = k.uma_num
  WHERE TRIM(b.tds_code) IN ('1','2')
    AND TRIM(s.order_of_finish) <> ''
    AND CAST(TRIM(s.order_of_finish) AS UNSIGNED) > 0
    AND TRIM(k.kishu_code) <> '' AND TRIM(k.trainer_code) <> ''
) x
GROUP BY x.kishu_code, x.trainer_code;

-- 整合性チェック: 集計の合計頭数 = 対象の頭数（差が0であること）、最新の成績日
SELECT
  (SELECT SUM(total_count) FROM T_COMBO_RECOVERY_NEW) AS combo_total,
  (SELECT COUNT(*) FROM T_KYI k
     INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
     INNER JOIN T_SED s ON s.course_code=k.course_code AND s.year_code=k.year_code AND s.kai=k.kai AND s.day_code=k.day_code AND s.race_num=k.race_num AND s.umaban=k.uma_num
   WHERE TRIM(b.tds_code) IN ('1','2') AND TRIM(s.order_of_finish) <> '' AND CAST(TRIM(s.order_of_finish) AS UNSIGNED) > 0
     AND TRIM(k.kishu_code) <> '' AND TRIM(k.trainer_code) <> '') AS target_total,
  (SELECT MAX(s.ymd) FROM T_SED s) AS latest_result_ymd;

DROP TABLE IF EXISTS T_COMBO_RECOVERY_OLD;
RENAME TABLE T_COMBO_RECOVERY TO T_COMBO_RECOVERY_OLD, T_COMBO_RECOVERY_NEW TO T_COMBO_RECOVERY;
DROP TABLE T_COMBO_RECOVERY_OLD;
