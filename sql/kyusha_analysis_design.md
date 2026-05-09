# 厩舎指数信頼度分析 設計書

## 1. 目的・背景

厩舎指数（`T_KYI.kyusha_index`）は厩舎ごとに「信頼度の差」がある。  
たとえば、指数が高い場合に高回収を示す厩舎もあれば、指数が最高レベルでも回収率が低い厩舎も存在する。  
また穴馬（高オッズ）時に限って指数の信頼度が高い厩舎もある。

本設計では、これらのパターンを厩舎単位で数値化し、出馬表ページへの表示を可能にすることを目的とする。

対応ケース:
| ケース | 内容 |
|---|---|
| A | ある厩舎の指数が20以上の時、高回収 |
| B | ある厩舎の指数が0未満の時、回収率も低い |
| C | ある厩舎の指数が35（最高）でも回収率が低い |
| D | ある厩舎の基準オッズ10倍以上かつ指数0以上の時、高回収（穴馬信頼度が高い） |

---

## 2. テーブル構成

```
T_KYI × T_BAC × T_SED
        ↓ Part 2（ETL）
T_KYUSHA_RACE_LOG（ファクトテーブル）
        ↓ Part 3（集計）
T_KYUSHA_FACTOR_AGG（ファクター別集計テーブル）
        ↓
出馬表ページ API
```

---

## 3. T_KYUSHA_RACE_LOG（ファクトテーブル）

**役割**: 生データの非正規化ログ。1行 = 1頭分の出走記録。  
**意義**: このテーブルがあれば、集計ロジックを変えたい場合も Part3 のみ書き直せば再集計できる。

### 主要カラム

| カラム | 型 | 説明 |
|---|---|---|
| `course_code` 〜 `uma_num` | CHAR | レースキー（主キー） |
| `ymd` | CHAR(8) | 年月日 YYYYMMDD |
| `trainer_code` | CHAR(5) | 調教師コード |
| `trainer_name` | VARCHAR(12) | 調教師名 |
| `kyusha_index` | DECIMAL(5,1) | **厩舎指数（数値変換済み）** T_KYI は CHAR(5) のため変換 |
| `kyusha_hyoka` | CHAR(1) | 厩舎評価コード（A/B/C/D/E） |
| `kijun_odds` | DECIMAL(6,1) | 基準単勝オッズ（穴馬判定用） |
| `kijun_ninki` | SMALLINT | 基準人気順位 |
| `finish_order` | CHAR(2) | 着順（T_SED 未格納時は NULL） |
| `win_payout` / `place_payout` | INT | 単勝・複勝払戻（正常完走以外は 0） |

### インデックス

| インデックス名 | カラム | 用途 |
|---|---|---|
| PRIMARY | `(course_code, year_code, kai, day_code, race_num, uma_num)` | 一意性・UPSERT |
| `idx_kyusha_log_trainer_ymd` | `(trainer_code, ymd)` | 特定厩舎の時系列クエリ |
| `idx_kyusha_log_trainer_code` | `(trainer_code)` | 厩舎単位の全件取得 |
| `idx_kyusha_log_ymd` | `(ymd)` | 日次バッチ差分取得 |

---

## 4. T_KYUSHA_FACTOR_AGG（ファクター別集計テーブル）

**役割**: 厩舎 × 年 × ファクター種別 × ファクター値 の集計済みデータ。  
**意義**: 出馬表 API は `WHERE trainer_code = ?` の 1クエリで返答できる（フルスキャン不要）。  
**形式**: EAV（Entity-Attribute-Value）形式のため、新ファクター追加時にカラム変更が不要。

### 主キー
`(trainer_code, agg_year, factor_type, factor_value)`

### 集計カラム

| カラム | 型 | 説明 |
|---|---|---|
| `total_count` | INT | 出走数（異常区分除外済み） |
| `win_count` | INT | 1着数 |
| `place_count` | INT | 3着以内数 |
| `win_recovery` | DECIMAL(6,1) | **単勝回収率**（メイン表示指標） |
| `place_recovery` | DECIMAL(6,1) | 複勝回収率 |

---

## 5. factor_type 一覧

### 5-1. `kyusha_idx`（厩舎指数帯）

ケース A / B / C に対応。6段階に分割。

**境界値ルール（左閉右開）**: 各帯域は下限値を含み、上限値を含まない。  
例: 指数が `30.0` のとき → `30~40` に入る（`< 30` の条件を超えるため）

| factor_value | 指数の範囲 | 境界値の扱い |
|---|---|---|
| `<-10` | -10 未満 | — |
| `-10~0` | -10 以上 0 未満 | -10は含む、0は含まない |
| `0~10` | 0 以上 10 未満 | 0は含む、10は含まない |
| `10~20` | 10 以上 20 未満 | 10は含む、20は含まない |
| `20~30` | 20 以上 30 未満 | 20は含む、30は含まない |
| `30~40` | 30 以上（最大40） | 30は含む |

出馬表での表示クエリ例:
```sql
SELECT factor_value, win_recovery, place_recovery, total_count
FROM T_KYUSHA_FACTOR_AGG
WHERE trainer_code = '12345'
  AND agg_year IN ('2024', '2025')
  AND factor_type = 'kyusha_idx'
ORDER BY FIELD(factor_value, '<-10', '-10~0', '0~10', '10~20', '20~35', '35~');
```

---

### 5-2. `kyusha_idx_x_odds`（指数符号 × オッズ帯 複合）

ケース D（穴馬での信頼度）に対応。4セルの 2×2 マトリクス。

| factor_value | 意味 |
|---|---|
| `minus_~10` | 指数マイナス × 人気馬（オッズ 10 倍未満） |
| `minus_10~` | 指数マイナス × 穴馬（オッズ 10 倍以上） |
| `plus_~10` | 指数プラス × 人気馬（オッズ 10 倍未満） |
| **`plus_10~`** | **指数プラス × 穴馬（オッズ 10 倍以上）← ケースD の検出セル** |

出馬表での活用: 現在レースの `kyusha_index >= 0 かつ kijun_odds >= 10.0` の場合、  
`factor_value = 'plus_10~'` の `win_recovery` を「穴信頼度スコア」として表示する。

```sql
SELECT win_recovery, place_recovery, total_count
FROM T_KYUSHA_FACTOR_AGG
WHERE trainer_code = '12345'
  AND agg_year IN ('2024', '2025')
  AND factor_type = 'kyusha_idx_x_odds'
  AND factor_value = 'plus_10~';
```

---

## 6. ETL 実行手順

実行ファイル: `sql/kyusha_analysis.sql`

### ステップ1: テーブル作成（初回のみ）
```sql
-- Part 1 を実行
-- T_KYUSHA_RACE_LOG および T_KYUSHA_FACTOR_AGG が存在しない場合のみ作成される
-- (CREATE TABLE IF NOT EXISTS のため再実行は安全)
```

### ステップ2: ファクトテーブルへのデータ格納（Part 2）
```sql
-- T_KYI × T_BAC × T_SED を JOIN して T_KYUSHA_RACE_LOG へ UPSERT
-- ON DUPLICATE KEY UPDATE のため冪等（何度実行しても安全）
-- T_SED が存在しない出走は LEFT JOIN で finish_order = NULL として格納される
```

### ステップ3: 集計テーブルの更新（Part 3）
```sql
-- T_KYUSHA_RACE_LOG から各 factor_type を集計して T_KYUSHA_FACTOR_AGG へ UPSERT
-- 年単位で再計算されるため、過去年のデータが修正された場合も正しく更新される
-- 4種類の INSERT（3-1 〜 3-4）が独立しているため任意の順序で実行可
```

---

## 7. 定期実行のタイミング

| タイミング | 理由 |
|---|---|
| **毎週木曜日**（推奨） | T_SED（成績速報）の正式版（SEC）が木曜日に確定するため |
| レース開催日当日 | T_SED 速報版の格納後に Part2 のみ実行すると当日分を先行格納できる（集計は木曜推奨） |

### MySQL Workbench スケジューラ登録例（参考）
```sql
CREATE EVENT IF NOT EXISTS ev_kyusha_etl
ON SCHEDULE EVERY 1 WEEK
STARTS '2026-05-08 08:00:00'  -- 木曜 8:00
DO
BEGIN
  -- Part 2
  INSERT INTO T_KYUSHA_RACE_LOG (...) SELECT ... ON DUPLICATE KEY UPDATE ...;
  -- Part 3 (3-1 〜 3-4)
  INSERT INTO T_KYUSHA_FACTOR_AGG (...) SELECT ... ON DUPLICATE KEY UPDATE ...;
END;
```

実際の運用では MySQL Event Scheduler よりも OS スケジューラ（Task Scheduler / cron）から  
`mysql -u user -p db < sql/kyusha_analysis.sql` を呼ぶ形が管理しやすい。

---

## 8. 出馬表ページ API への組み込み方針

### 追加するクエリ（`/api/races/:raceKey/entries` の JOIN に追加）

各出走馬行に対して以下の 3 パターンの情報を付与する:

```sql
-- ① 指数帯の回収率（現在の指数が属する帯域の過去統計）
LEFT JOIN T_KYUSHA_FACTOR_AGG kyf_idx
  ON  kyf_idx.trainer_code = k.trainer_code
  AND kyf_idx.agg_year     IN ('2024', '2025')           -- 直近2年
  AND kyf_idx.factor_type  = 'kyusha_idx'
  AND kyf_idx.factor_value = CASE
      WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(5,1)) <  -10 THEN '<-10'
      WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(5,1)) <    0 THEN '-10~0'
      WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(5,1)) <   10 THEN '0~10'
      WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(5,1)) <   20 THEN '10~20'
      WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(5,1)) <   35 THEN '20~35'
      ELSE '35~' END

-- ② 穴信頼度（指数符号 × オッズ帯 の複合）
LEFT JOIN T_KYUSHA_FACTOR_AGG kyf_anaba
  ON  kyf_anaba.trainer_code = k.trainer_code
  AND kyf_anaba.agg_year     IN ('2024', '2025')
  AND kyf_anaba.factor_type  = 'kyusha_idx_x_odds'
  AND kyf_anaba.factor_value = CONCAT(
      CASE WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(5,1)) >= 0 THEN 'plus' ELSE 'minus' END,
      '_',
      CASE WHEN CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1)) >= 10.0 THEN '10~' ELSE '~10' END
  )
```

### フロントエンド表示のガイドライン

- **`total_count < 10`** のセルは「サンプル不足」として `?` 表示推奨
- 回収率 >= 120% かつ total_count >= 15: ハイライト（高信頼シグナル）
- 回収率 <= 60% かつ total_count >= 15: グレーアウト（低信頼シグナル）

---

## 9. 注意事項

| 項目 | 内容 |
|---|---|
| サンプル数 | `total_count` が 10 未満のセルは統計的ノイズが大きい。表示側でフィルタを推奨 |
| 年度サマリ | `agg_year` は集計年。直近 2〜3 年を範囲指定することで過去の傾向変化を除外できる |
| 指数 NULL | `kyusha_index` が NULL のレコードは集計から除外される（T_KYI の不正値・未設定値） |
| 障害レース | Part2 は `tds_code IN ('1','2','3')` で障害を含む。不要なら `IN ('1','2')` に変更 |
| trainer_name の重複 | 同一 `trainer_code` に複数の名前表記がある場合、`MAX(trainer_name)` で最新を採用 |
