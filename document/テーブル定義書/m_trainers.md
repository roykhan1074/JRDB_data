# テーブル定義書: m_trainers

## テーブル概要

| 項目 | 内容 |
|------|------|
| テーブル名 | `m_trainers` |
| 論理名 | 調教師マスタ |
| エンジン | InnoDB |
| 文字セット | utf8mb4_unicode_ci |
| 説明 | 調教師の基本情報・成績マスタ。CS（調教師データ）ファイルから変換・格納。 |

## 主キー

`trainer_code`

---

## カラム定義

| # | カラム名 | 論理名 | データ型 | NOT NULL | PK | 備考 |
|---|---------|--------|---------|----------|-----|------|
| 1 | `trainer_code` | 調教師コード | char(5) | ✓ | ✓ | JRA調教師コード（5桁） |
| 2 | `deregistration_flag` | 登録抹消フラグ | smallint | | | 0:現役 1:抹消 |
| 3 | `deregistration_date` | 登録抹消年月日 | date | | | 抹消日 |
| 4 | `trainer_name` | 調教師名 | varchar(12) | ✓ | | 全角6文字 |
| 5 | `trainer_kana` | 調教師カナ | varchar(30) | | | 全角15文字 |
| 6 | `trainer_name_short` | 調教師名略称 | varchar(6) | | | 全角3文字 |
| 7 | `affiliation_code` | 所属コード | smallint | | | 1:関東 2:関西 3:他 |
| 8 | `affiliation_area` | 所属地域名 | varchar(4) | | | 全角2文字（地方の場合） |
| 9 | `birthdate` | 生年月日 | date | | | YYYY-MM-DD |
| 10 | `first_license_year` | 初免許年 | smallint | | | YYYY |
| 11 | `comment` | コメント | varchar(40) | | | JRDBスタッフの厩舎見解 |
| 12 | `comment_date` | コメント入力年月日 | date | | | |
| 13 | `this_year_leading` | 今年リーディング | smallint | | | 年間リーディング順位 |
| 14 | `this_year_flat_1st` | 今年平地1着 | smallint | | | |
| 15 | `this_year_flat_2nd` | 今年平地2着 | smallint | | | |
| 16 | `this_year_flat_3rd` | 今年平地3着 | smallint | | | |
| 17 | `this_year_flat_other` | 今年平地着外 | smallint | | | |
| 18 | `this_year_obstacle_1st` | 今年障害1着 | smallint | | | |
| 19 | `this_year_obstacle_2nd` | 今年障害2着 | smallint | | | |
| 20 | `this_year_obstacle_3rd` | 今年障害3着 | smallint | | | |
| 21 | `this_year_obstacle_other` | 今年障害着外 | smallint | | | |
| 22 | `this_year_special_wins` | 今年特別勝利数 | smallint | | | |
| 23 | `this_year_stakes_wins` | 今年重賞勝利数 | smallint | | | |
| 24 | `last_year_leading` | 昨年リーディング | smallint | | | |
| 25 | `last_year_flat_1st` | 昨年平地1着 | smallint | | | |
| 26 | `last_year_flat_2nd` | 昨年平地2着 | smallint | | | |
| 27 | `last_year_flat_3rd` | 昨年平地3着 | smallint | | | |
| 28 | `last_year_flat_other` | 昨年平地着外 | smallint | | | |
| 29 | `last_year_obstacle_1st` | 昨年障害1着 | smallint | | | |
| 30 | `last_year_obstacle_2nd` | 昨年障害2着 | smallint | | | |
| 31 | `last_year_obstacle_3rd` | 昨年障害3着 | smallint | | | |
| 32 | `last_year_obstacle_other` | 昨年障害着外 | smallint | | | |
| 33 | `last_year_special_wins` | 昨年特別勝利数 | smallint | | | |
| 34 | `last_year_stakes_wins` | 昨年重賞勝利数 | smallint | | | |
| 35 | `total_flat_1st` | 通算平地1着 | int | | | |
| 36 | `total_flat_2nd` | 通算平地2着 | int | | | |
| 37 | `total_flat_3rd` | 通算平地3着 | int | | | |
| 38 | `total_flat_other` | 通算平地着外 | int | | | |
| 39 | `total_obstacle_1st` | 通算障害1着 | int | | | |
| 40 | `total_obstacle_2nd` | 通算障害2着 | int | | | |
| 41 | `total_obstacle_3rd` | 通算障害3着 | int | | | |
| 42 | `total_obstacle_other` | 通算障害着外 | int | | | |
| 43 | `data_date` | データ年月日 | date | | | このレコードの基準日 |

---

## インデックス

| インデックス名 | カラム | 種類 |
|--------------|--------|------|
| PRIMARY | `trainer_code` | PRIMARY KEY |

---

## 関連テーブル

| テーブル | 関係 | 説明 |
|---------|------|------|
| `race_entries` | 1:N | この調教師の出走記録 |
| `race_results` | 1:N | この調教師の成績記録 |
