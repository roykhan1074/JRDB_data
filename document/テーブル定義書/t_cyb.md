# テーブル定義書: t_cyb

## テーブル概要

| 項目 | 内容 |
|------|------|
| テーブル名 | `t_cyb` |
| 論理名 | CYB調教分析（JRDB生テーブル） |
| エンジン | InnoDB |
| 文字セット | utf8mb4 |
| ソースファイル | `CYB` + YYMMDD + `.txt` |
| 説明 | JRDBのCYBファイルを固定長からCSV変換しそのまま格納したRAWテーブル。調教コース・本数・指数を保持。正規化テーブルは `training_analysis`。 |

## 主キー

`course_code` + `year_code` + `kai` + `day_code` + `race_num` + `uma_num`

---

## カラム定義

| # | カラム名 | 論理名 | データ型 | NOT NULL | PK | 備考 |
|---|---------|--------|---------|----------|-----|------|
| 1 | `course_code` | 競馬場コード | char(2) | ✓ | ✓ | |
| 2 | `year_code` | 年 | char(2) | ✓ | ✓ | 西暦下2桁 |
| 3 | `kai` | 回 | char(1) | ✓ | ✓ | |
| 4 | `day_code` | 日 | char(1) | ✓ | ✓ | |
| 5 | `race_num` | R | char(2) | ✓ | ✓ | |
| 6 | `uma_num` | 馬番 | char(2) | ✓ | ✓ | |
| 7 | `chokyo_type` | 調教タイプ | char(2) | | | |
| 8 | `chokyo_course_type` | 調教コース種別 | char(1) | | | |
| 9 | `course_saka` | 坂路本数 | char(2) | | | |
| 10 | `course_w` | Wコース本数 | char(2) | | | |
| 11 | `course_da` | ダート本数 | char(2) | | | |
| 12 | `course_shiba` | 芝本数 | char(2) | | | |
| 13 | `course_pool` | プール本数 | char(2) | | | |
| 14 | `course_sho` | 障害本数 | char(2) | | | |
| 15 | `course_poly` | ポリトラック本数 | char(2) | | | |
| 16 | `chokyo_kyori` | 調教距離 | char(1) | | | |
| 17 | `chokyo_juten` | 調教重点 | char(1) | | | |
| 18 | `oi_index` | 追切指数 | char(3) | | | |
| 19 | `shiage_index` | 仕上指数 | char(3) | | | |
| 20 | `chokyo_ryo_hyoka` | 調教量評価 | char(1) | | | A〜E |
| 21 | `shiage_index_henka` | 仕上指数変化 | char(1) | | | |
| 22 | `chokyo_comment` | 調教コメント | varchar(40) | | | JRDBスタッフコメント |
| 23 | `comment_ymd` | コメント年月日 | char(8) | | | YYYYMMDD |
| 24 | `chokyo_hyoka` | 調教評価 | char(1) | | | A〜E |
| 25 | `isshuumae_oi_index` | 一週前追切指数 | char(3) | | | |
| 26 | `isshuumae_oi_course` | 一週前追切コース | char(2) | | | |
| 27 | `load_file` | ロードファイル | varchar(20) | | | 取込元ファイル名 |
| 28 | `last_update` | 最終更新 | varchar(20) | | | |

---

## インデックス

| インデックス名 | カラム | 種類 |
|--------------|--------|------|
| PRIMARY | `course_code`, `year_code`, `kai`, `day_code`, `race_num`, `uma_num` | PRIMARY KEY |
