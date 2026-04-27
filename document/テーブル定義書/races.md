# テーブル定義書: races

## テーブル概要

| 項目 | 内容 |
|------|------|
| テーブル名 | `races` |
| 論理名 | レース基本情報 |
| エンジン | InnoDB |
| 文字セット | utf8mb4_unicode_ci |
| 説明 | 開催レースの基本情報。KYI/BAC から変換・格納する正規化テーブル。 |

## 主キー

`venue_code` + `race_year` + `kai` + `nichi` + `race_no`

---

## カラム定義

| # | カラム名 | 論理名 | データ型 | NOT NULL | PK | 備考 |
|---|---------|--------|---------|----------|-----|------|
| 1 | `venue_code` | 競馬場コード | char(2) | ✓ | ✓ | 01:札幌 02:函館 03:福島 04:新潟 05:東京 06:中山 07:中京 08:京都 09:阪神 10:小倉 |
| 2 | `race_year` | 年 | char(2) | ✓ | ✓ | 西暦下2桁 (例: 26) |
| 3 | `kai` | 回 | smallint | ✓ | ✓ | 開催回次 |
| 4 | `nichi` | 日 | char(1) | ✓ | ✓ | 開催日次 |
| 5 | `race_no` | レース番号 | smallint | ✓ | ✓ | 1〜12 |
| 6 | `race_date` | 開催日付 | date | | | YYYY-MM-DD |
| 7 | `post_time` | 発走時刻 | char(4) | | | HHMM形式 |
| 8 | `distance` | 距離 | smallint | | | メートル単位 |
| 9 | `track_code` | 芝ダートコード | smallint | | | 1:芝 2:ダート 3:障害 |
| 10 | `direction_code` | 右左コード | smallint | | | 1:右 2:左 3:直線 |
| 11 | `course_type` | コース種別 | smallint | | | 内外コース区分 |
| 12 | `horse_category_code` | 馬の種別コード | char(2) | | | 11:サラ系2歳 等 |
| 13 | `condition_code` | 条件コード | char(2) | | | レース条件 |
| 14 | `symbol_code` | 記号コード | char(3) | | | レース記号 |
| 15 | `weight_type_code` | 重量種別コード | smallint | | | 1:馬齢 2:定量 3:別定 4:ハンデ |
| 16 | `grade_code` | グレードコード | smallint | | | 1:G1 2:G2 3:G3 |
| 17 | `race_name` | レース名 | varchar(50) | | | 正式レース名 |
| 18 | `lap_count` | 回数 | varchar(8) | | | 開催回数 |
| 19 | `entrant_count` | 頭数 | smallint | | | 出走頭数 |
| 20 | `course_code` | コース | char(1) | | | A/B/C/D |
| 21 | `holding_type` | 開催区分 | char(1) | | | 開催種別 |
| 22 | `race_name_short` | レース名略称 | varchar(8) | | | 全角4文字 |
| 23 | `race_name_9char` | レース名9文字 | varchar(18) | | | 全角9文字 |
| 24 | `data_type` | データ区分 | char(1) | | | 1:確定 2:速報 |
| 25 | `prize_1st` | 1着賞金 | smallint | | | 万円単位 |
| 26 | `prize_2nd` | 2着賞金 | smallint | | | 万円単位 |
| 27 | `prize_3rd` | 3着賞金 | smallint | | | 万円単位 |
| 28 | `prize_4th` | 4着賞金 | smallint | | | 万円単位 |
| 29 | `prize_5th` | 5着賞金 | smallint | | | 万円単位 |
| 30 | `prize_included_1st` | 1着算入賞金 | smallint | | | 万円単位 |
| 31 | `prize_included_2nd` | 2着算入賞金 | smallint | | | 万円単位 |
| 32 | `ticket_tansho` | 単勝フラグ | smallint | | | 投票有無 |
| 33 | `ticket_fukusho` | 複勝フラグ | smallint | | | 投票有無 |
| 34 | `ticket_wakuren` | 枠連フラグ | smallint | | | 投票有無 |
| 35 | `ticket_umaren` | 馬連フラグ | smallint | | | 投票有無 |
| 36 | `ticket_umatan` | 馬単フラグ | smallint | | | 投票有無 |
| 37 | `ticket_wide` | ワイドフラグ | smallint | | | 投票有無 |
| 38 | `ticket_sanrenpuku` | 3連複フラグ | smallint | | | 投票有無 |
| 39 | `ticket_sanrentan` | 3連単フラグ | smallint | | | 投票有無 |
| 40 | `win5_flag` | WIN5フラグ | smallint | | | WIN5対象レース |

---

## インデックス

| インデックス名 | カラム | 種類 |
|--------------|--------|------|
| PRIMARY | `venue_code`, `race_year`, `kai`, `nichi`, `race_no` | PRIMARY KEY |
| `idx_races_date` | `race_date` | INDEX |
| `idx_races_venue_date` | `venue_code`, `race_date` | INDEX |

---

## 関連テーブル

| テーブル | 関係 | 説明 |
|---------|------|------|
| `race_entries` | 1:N | このレースへの出走馬 |
| `race_results` | 1:N | このレースの着順結果 |
| `training_analysis` | 1:N（race_entries経由） | 調教分析データ |
