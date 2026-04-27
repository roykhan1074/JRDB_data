# テーブル定義書: training_analysis

## テーブル概要

| 項目 | 内容 |
|------|------|
| テーブル名 | `training_analysis` |
| 論理名 | 調教分析 |
| エンジン | InnoDB |
| 文字セット | utf8mb4_unicode_ci |
| 説明 | 出走馬の調教内容・評価情報。CYB（調教分析）ファイルから変換・格納。race_entries と 1:1 対応。 |

## 主キー

`venue_code` + `race_year` + `kai` + `nichi` + `race_no` + `horse_no`

---

## カラム定義

| # | カラム名 | 論理名 | データ型 | NOT NULL | PK | FK | 備考 |
|---|---------|--------|---------|----------|-----|----|------|
| 1 | `venue_code` | 競馬場コード | char(2) | ✓ | ✓ | race_entries | |
| 2 | `race_year` | 年 | char(2) | ✓ | ✓ | race_entries | 西暦下2桁 |
| 3 | `kai` | 回 | smallint | ✓ | ✓ | race_entries | |
| 4 | `nichi` | 日 | char(1) | ✓ | ✓ | race_entries | |
| 5 | `race_no` | レース番号 | smallint | ✓ | ✓ | race_entries | |
| 6 | `horse_no` | 馬番 | smallint | ✓ | ✓ | race_entries | |
| 7 | `training_type` | 調教タイプ | char(2) | | | | |
| 8 | `training_course_type` | 調教コース種別 | char(1) | | | | |
| 9 | `course_slope` | 坂路 | char(2) | | | | 調教本数 |
| 10 | `course_wood` | Wコース | char(2) | | | | 調教本数 |
| 11 | `course_dirt` | ダートコース | char(2) | | | | 調教本数 |
| 12 | `course_turf` | 芝コース | char(2) | | | | 調教本数 |
| 13 | `course_pool` | プール | char(2) | | | | 調教本数 |
| 14 | `course_obstacle` | 障害コース | char(2) | | | | 調教本数 |
| 15 | `course_poly` | ポリトラック | char(2) | | | | 調教本数 |
| 16 | `training_distance` | 調教距離 | char(1) | | | | |
| 17 | `training_focus` | 調教重点 | char(1) | | | | |
| 18 | `oikiri_index` | 追切指数 | smallint | | | | |
| 19 | `finish_index` | 仕上指数 | smallint | | | | |
| 20 | `training_amount_eval` | 調教量評価 | char(1) | | | | A〜E |
| 21 | `finish_index_change` | 仕上指数変化 | char(1) | | | | |
| 22 | `training_comment` | 調教コメント | varchar(40) | | | | JRDBスタッフコメント |
| 23 | `comment_date` | コメント年月日 | date | | | | |
| 24 | `training_eval` | 調教評価 | char(1) | | | | A〜E |
| 25 | `prev_week_oikiri_index` | 一週前追切指数 | smallint | | | | |
| 26 | `prev_week_oikiri_course` | 一週前追切コース | smallint | | | | |

---

## インデックス

| インデックス名 | カラム | 種類 |
|--------------|--------|------|
| PRIMARY | `venue_code`, `race_year`, `kai`, `nichi`, `race_no`, `horse_no` | PRIMARY KEY |
| `idx_training_horse` | `venue_code`, `race_year`, `kai`, `nichi`, `race_no`, `horse_no` | INDEX |

---

## 外部キー制約

| 制約名 | カラム | 参照テーブル | 参照カラム |
|--------|--------|-------------|-----------|
| `fk_training_race_entries` | `venue_code`, `race_year`, `kai`, `nichi`, `race_no`, `horse_no` | `race_entries` | 同左 |
