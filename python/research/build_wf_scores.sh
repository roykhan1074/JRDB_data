#!/bin/bash
# 研究用: EX指数/本命指数の「直前年までの全データで集計→翌年を採点」版を作る（本番テーブルには触れない）
# 使い方: build_wf_scores.sh {anaba|honmei} {集計最終日YYYYMMDD} {採点開始YYYYMMDD} {採点終了YYYYMMDD} {接尾辞}
# 例: build_wf_scores.sh honmei 20241231 20250101 20251231 Y25  → T_HONMEI_SCORE_Y25 に2025年分
set -e
cd "$(dirname "$0")/../.."
KIND=$1; CUT=$2; FROM=$3; TO=$4; SFX=$5
P="$(grep ^DB_PASS .env | cut -d= -f2)"
if [ "$KIND" = "anaba" ]; then
  SRC=sql/anaba_index.sql; LOG=T_ANABA_RACE_LOG; AGG=T_ANABA_FACTOR_AGG; SC=T_ANABA_SCORE; P3="283,1111p"; P4="1112,1489p"
else
  SRC=sql/honmei_index.sql; LOG=T_HONMEI_RACE_LOG; AGG=T_HONMEI_FACTOR_AGG; SC=T_HONMEI_SCORE; P3="267,1079p"; P4="1080,1449p"
fi
V=V_${KIND^^}_LOG_${SFX}
OUT=.scratch/${KIND}_${SFX}.sql
{
  echo "DROP VIEW IF EXISTS $V; CREATE VIEW $V AS SELECT * FROM $LOG WHERE ymd <= '$CUT';"
  echo "DROP TABLE IF EXISTS ${AGG}_${SFX}; CREATE TABLE ${AGG}_${SFX} LIKE $AGG;"
  echo "DROP TABLE IF EXISTS ${SC}_${SFX}; CREATE TABLE ${SC}_${SFX} LIKE $SC;"
  sed -n "$P3" $SRC | sed -e "s/${AGG}/${AGG}_${SFX}/g" -e "s/FROM ${LOG}/FROM ${V}/g"
  sed -n "$P4" $SRC | sed -e "s/${AGG}/${AGG}_${SFX}/g" -e "s/INSERT INTO ${SC} (/INSERT INTO ${SC}_${SFX} (/" \
    -e "s/^WHERE TRIM(b.tds_code) IN ('1','2')\$/WHERE TRIM(b.tds_code) IN ('1','2') AND b.ymd BETWEEN '$FROM' AND '$TO'/"
} > $OUT
# 置換漏れ（本番テーブルへの書き込み・全期間ログ参照）が無いことを確認してから実行
if tail -n +4 $OUT | grep -qE "INSERT INTO ${SC} \(|INSERT INTO ${AGG}$|INSERT INTO ${AGG} |FROM ${LOG}( |$)"; then echo "置換漏れ: 中止"; exit 1; fi
[ "$(grep -c "b.ymd BETWEEN '$FROM' AND '$TO'" $OUT)" = "1" ] || { echo "採点期間の絞り込み失敗: 中止"; exit 1; }
mysql -u root -p"$P" racing < $OUT 2>&1 | grep -v Warning || true
mysql -u root -p"$P" racing -e "SELECT '${SC}_${SFX}' t, COUNT(*) n, MIN(CONCAT('20',year_code)) FROM ${SC}_${SFX};" 2>/dev/null
