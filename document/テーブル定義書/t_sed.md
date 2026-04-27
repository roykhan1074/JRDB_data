# テーブル定義書: t_sed

## テーブル概要

| 項目 | 内容 |
|------|------|
| テーブル名 | `t_sed` |
| 論理名 | SED成績データ（JRDB生テーブル） |
| エンジン | InnoDB |
| 文字セット | utf8mb4 |
| ソースファイル | `SED` + YYMMDD + `.txt` |
| 説明 | JRDBのSEDファイルを固定長からCSV変換しそのまま格納したRAWテーブル。レース結果の着順・タイム・指数を保持。正規化テーブルは `race_results`。 |

## 主キー

`course_code` + `year_code` + `kai` + `day_code` + `race_num` + `umaban`

---

## カラム定義

| # | カラム名 | 論理名 | データ型 | NOT NULL | PK | 備考 |
|---|---------|--------|---------|----------|-----|------|
| 1 | `course_code` | 競馬場コード | char(2) | ✓ | ✓ | |
| 2 | `year_code` | 年 | char(2) | ✓ | ✓ | 西暦下2桁 |
| 3 | `kai` | 回 | char(1) | ✓ | ✓ | |
| 4 | `day_code` | 日 | char(1) | ✓ | ✓ | |
| 5 | `race_num` | R | char(2) | ✓ | ✓ | |
| 6 | `umaban` | 馬番 | char(2) | ✓ | ✓ | |
| 7 | `blood_num` | 血統登録番号 | char(8) | | | |
| 8 | `ymd` | 年月日 | char(8) | | | YYYYMMDD |
| 9 | `horse_name` | 馬名 | varchar(36) | | | |
| 10 | `distance` | 距離 | char(4) | | | メートル |
| 11 | `tds_code` | 芝ダ障コード | char(1) | | | 1:芝 2:ダ 3:障 |
| 12 | `migihidari` | 右左 | char(1) | | | |
| 13 | `naigai` | 内外 | char(1) | | | |
| 14 | `baba_cond` | 馬場状態 | char(2) | | | 良/稍/重/不 |
| 15 | `syubetsu` | 種別 | char(2) | | | |
| 16 | `class` | 条件 | char(2) | | | |
| 17 | `kigou` | 記号 | char(3) | | | |
| 18 | `weight` | 重量 | char(1) | | | |
| 19 | `grade` | グレード | char(1) | | | |
| 20 | `race_name` | レース名 | varchar(50) | | | |
| 21 | `heads` | 頭数 | char(2) | | | |
| 22 | `race_name_ryaku` | レース名略称 | char(8) | | | |
| 23 | `order_of_finish` | 着順 | char(2) | | | |
| 24 | `ijou_kubun` | 異常区分 | char(1) | | | 0:正常 1:中止 等 |
| 25 | `finish_time` | タイム | char(4) | | | 秒1/10 |
| 26 | `kinryou` | 斤量 | char(3) | | | 100g単位 |
| 27 | `jockey_name` | 騎手名 | varchar(12) | | | |
| 28 | `trainer_name` | 調教師名 | varchar(12) | | | |
| 29 | `win_odds` | 確定単勝オッズ | char(6) | | | |
| 30 | `win_odds_rank` | 確定単勝人気 | char(2) | | | |
| 31 | `idm` | IDM | char(3) | | | |
| 32 | `soten` | 素点 | char(3) | | | |
| 33 | `baba_diff` | 馬場差 | char(3) | | | |
| 34 | `pace` | ペース | char(3) | | | |
| 35 | `deokure` | 出遅 | char(3) | | | |
| 36 | `ichidori` | 位置取り | char(3) | | | |
| 37 | `furi` | 不利 | char(3) | | | |
| 38 | `mae_furi` | 前不利 | char(3) | | | |
| 39 | `naka_furi` | 中不利 | char(3) | | | |
| 40 | `ushiro_furi` | 後不利 | char(3) | | | |
| 41 | `race` | レース | char(3) | | | |
| 42 | `course_posi` | コース取り | char(1) | | | |
| 43 | `up_code` | 上昇度コード | char(1) | | | |
| 44 | `class_code` | クラスコード | char(2) | | | |
| 45 | `batai_code` | 馬体コード | char(1) | | | |
| 46 | `kehai_code` | 気配コード | char(1) | | | |
| 47 | `race_pace` | レースペース | char(1) | | | H/M/S |
| 48 | `horse_pace` | 馬ペース | char(1) | | | H/M/S |
| 49 | `first_half_idx` | テン指数 | char(5) | | | |
| 50 | `latter_half_idx` | 上がり指数 | char(5) | | | |
| 51 | `pace_idx` | ペース指数 | char(5) | | | |
| 52 | `race_pace_idx` | レースP指数 | char(5) | | | |
| 53 | `win_horse_name` | 1(2)着馬名 | varchar(12) | | | |
| 54 | `win_diff` | 1(2)着タイム差 | char(3) | | | |
| 55 | `first_half_time` | 前3F | char(3) | | | 秒 |
| 56 | `latter_half_time` | 後3F | char(3) | | | 秒 |
| 57 | `place_odds` | 確定複勝オッズ下 | char(6) | | | |
| 58 | `win_odds_10` | 10秒前単勝オッズ | char(6) | | | |
| 59 | `place_odds_10` | 10秒前複勝オッズ | char(6) | | | |
| 60 | `corner_1` | コーナー順位1 | char(2) | | | 1コーナー |
| 61 | `corner_2` | コーナー順位2 | char(2) | | | 2コーナー |
| 62 | `corner_3` | コーナー順位3 | char(2) | | | 3コーナー |
| 63 | `corner_4` | コーナー順位4 | char(2) | | | 4コーナー |
| 64 | `first_half_diff` | 前3F先頭差 | char(3) | | | |
| 65 | `latter_half_diff` | 後3F先頭差 | char(3) | | | |
| 66 | `jockey_code` | 騎手コード | char(5) | | | |
| 67 | `trainer_code` | 調教師コード | char(5) | | | |
| 68 | `horse_weight` | 馬体重 | char(3) | | | kg |
| 69 | `horse_weight_diff` | 馬体重増減 | char(3) | | | kg |
| 70 | `weather_code` | 天候コード | char(1) | | | 1:晴 2:曇 3:雨 等 |
| 71 | `course_abcd` | コース | char(1) | | | A/B/C/D |
| 72 | `race_kyakushitsu` | レース脚質 | char(1) | | | |
| 73 | `win` | 単勝払戻 | char(7) | | | 円 |
| 74 | `place` | 複勝払戻 | char(7) | | | 円 |
| 75 | `hon_syoukin` | 本賞金 | char(5) | | | 万円 |
| 76 | `syutoku_syokin` | 収得賞金 | char(5) | | | 万円 |
| 77 | `race_pace_stream` | レースペース流れ | char(2) | | | |
| 78 | `horse_pace_stream` | 馬ペース流れ | char(2) | | | |
| 79 | `corner_4_posi` | 4角コース取り | char(1) | | | |
| 80 | `load_file` | ロードファイル | varchar(20) | | | 取込元ファイル名 |
| 81 | `last_update` | 最終更新 | varchar(20) | | | |

---

## インデックス

| インデックス名 | カラム | 種類 |
|--------------|--------|------|
| PRIMARY | `course_code`, `year_code`, `kai`, `day_code`, `race_num`, `umaban` | PRIMARY KEY |
