# テーブル定義書: t_bac

## テーブル概要

| 項目 | 内容 |
|------|------|
| テーブル名 | `t_bac` |
| 論理名 | BACレース基本情報（JRDB生テーブル） |
| エンジン | InnoDB |
| 文字セット | utf8mb4 |
| ソースファイル | `BAC` + YYMMDD + `.txt` |
| 説明 | JRDBのBACファイルを固定長からCSV変換しそのまま格納したRAWテーブル。全カラムがchar/varchar型。正規化テーブルは `races`。 |

## 主キー

`course_code` + `year_code` + `kai` + `day_code` + `race_num`

---

## カラム定義

| # | カラム名 | 論理名 | データ型 | NOT NULL | PK | 備考 |
|---|---------|--------|---------|----------|-----|------|
| 1 | `course_code` | 競馬場コード | char(2) | ✓ | ✓ | 01〜10 |
| 2 | `year_code` | 年 | char(2) | ✓ | ✓ | 西暦下2桁 |
| 3 | `kai` | 回 | char(1) | ✓ | ✓ | 開催回次 |
| 4 | `day_code` | 日 | char(1) | ✓ | ✓ | 開催日次 |
| 5 | `race_num` | R | char(2) | ✓ | ✓ | レース番号 |
| 6 | `ymd` | 年月日 | char(8) | | | YYYYMMDD |
| 7 | `start_time` | 発走時刻 | char(4) | | | HHMM |
| 8 | `distance` | 距離 | char(4) | | | メートル |
| 9 | `tds_code` | 芝ダ障コード | char(1) | | | 1:芝 2:ダ 3:障 |
| 10 | `migihidari` | 右左 | char(1) | | | 1:右 2:左 3:直 |
| 11 | `naigai` | 内外 | char(1) | | | 内外コース区分 |
| 12 | `syubetsu` | 種別 | char(2) | | | 馬の種別コード |
| 13 | `class` | 条件 | char(2) | | | レース条件コード |
| 14 | `kigou` | 記号 | char(3) | | | レース記号コード |
| 15 | `weight` | 重量 | char(1) | | | 1:馬齢 2:定量 3:別定 4:ハンデ |
| 16 | `grade` | グレード | char(1) | | | 1:G1 2:G2 3:G3 等 |
| 17 | `race_name` | レース名 | varchar(50) | | | |
| 18 | `kaisu` | 回数 | char(8) | | | |
| 19 | `heads` | 頭数 | char(2) | | | |
| 20 | `course_abcd` | コース | char(1) | | | A/B/C/D |
| 21 | `kaisai_kubun` | 開催区分 | char(1) | | | |
| 22 | `race_name_short` | レース名略称 | char(8) | | | 全角4文字 |
| 23 | `race_name_9char` | レース名9文字 | varchar(18) | | | 全角9文字 |
| 24 | `data_kubun` | データ区分 | char(1) | | | 1:確定 2:速報 |
| 25 | `prize_1st` | 1着賞金 | char(5) | | | 万円 |
| 26 | `prize_2nd` | 2着賞金 | char(5) | | | 万円 |
| 27 | `prize_3rd` | 3着賞金 | char(5) | | | 万円 |
| 28 | `prize_4th` | 4着賞金 | char(5) | | | 万円 |
| 29 | `prize_5th` | 5着賞金 | char(5) | | | 万円 |
| 30 | `prize_1st_calc` | 1着算入賞金 | char(5) | | | 万円 |
| 31 | `prize_2nd_calc` | 2着算入賞金 | char(5) | | | 万円 |
| 32 | `baken_flag` | 馬券フラグ | char(16) | | | 投票種別の有無フラグ |
| 33 | `win5_flag` | WIN5フラグ | char(1) | | | WIN5対象レース |
| 34 | `load_file` | ロードファイル | varchar(20) | | | 取込元ファイル名 |
| 35 | `last_update` | 最終更新 | varchar(20) | | | |

---

## インデックス

| インデックス名 | カラム | 種類 |
|--------------|--------|------|
| PRIMARY | `course_code`, `year_code`, `kai`, `day_code`, `race_num` | PRIMARY KEY |

---

## 備考

- 全フィールドが文字列型で格納されている（JRDB固定長ファイルの仕様上）
- 分析用途には正規化済みの `races` テーブルを使用すること
