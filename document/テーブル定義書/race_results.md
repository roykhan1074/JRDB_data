# テーブル定義書: race_results

## テーブル概要

| 項目 | 内容 |
|------|------|
| テーブル名 | `race_results` |
| 論理名 | 成績データ |
| エンジン | InnoDB |
| 文字セット | utf8mb4_unicode_ci |
| 説明 | レース結果の着順・タイム・指数情報。SED（成績データ）・SRB（成績速報）から変換・格納。 |

## 主キー

`venue_code` + `race_year` + `kai` + `nichi` + `race_no` + `horse_no`

---

## カラム定義

| # | カラム名 | 論理名 | データ型 | NOT NULL | PK | FK | 備考 |
|---|---------|--------|---------|----------|-----|----|------|
| 1 | `venue_code` | 競馬場コード | char(2) | ✓ | ✓ | races | |
| 2 | `race_year` | 年 | char(2) | ✓ | ✓ | races | 西暦下2桁 |
| 3 | `kai` | 回 | smallint | ✓ | ✓ | races | |
| 4 | `nichi` | 日 | char(1) | ✓ | ✓ | races | |
| 5 | `race_no` | レース番号 | smallint | ✓ | ✓ | races | |
| 6 | `horse_no` | 馬番 | smallint | ✓ | ✓ | | |
| 7 | `pedigree_no` | 血統登録番号 | char(8) | | | | |
| 8 | `result_date` | 成績年月日 | date | | | | YYYY-MM-DD |
| 9 | `horse_name` | 馬名 | varchar(36) | | | | |
| 10 | `distance` | 距離 | smallint | | | | メートル |
| 11 | `track_code` | 芝ダートコード | smallint | | | | 1:芝 2:ダート 3:障害 |
| 12 | `direction_code` | 右左コード | smallint | | | | |
| 13 | `course_type` | コース種別 | smallint | | | | |
| 14 | `horse_category_code` | 馬の種別コード | char(2) | | | | |
| 15 | `condition_code` | 条件コード | char(2) | | | | |
| 16 | `symbol_code` | 記号コード | char(3) | | | | |
| 17 | `weight_type_code` | 重量種別コード | smallint | | | | |
| 18 | `grade_code` | グレードコード | smallint | | | | |
| 19 | `race_name` | レース名 | varchar(50) | | | | |
| 20 | `entrant_count` | 頭数 | smallint | | | | |
| 21 | `race_name_short` | レース名略称 | varchar(8) | | | | |
| 22 | `finish_order` | 着順 | smallint | | | | 0:中止/失格等 |
| 23 | `abnormal_code` | 異常区分 | char(1) | | | | 0:正常 1:中止 2:失格 等 |
| 24 | `race_time` | タイム | decimal(6,1) | | | | 秒（例: 98.3）|
| 25 | `weight_load` | 負担重量 | smallint | | | | 単位:100g |
| 26 | `jockey_name` | 騎手名 | varchar(12) | | | | |
| 27 | `trainer_name` | 調教師名 | varchar(12) | | | | |
| 28 | `win_odds` | 確定単勝オッズ | decimal(6,1) | | | | |
| 29 | `win_popularity` | 確定単勝人気 | smallint | | | | |
| 30 | `idm` | IDM | decimal(4,1) | | | | |
| 31 | `base_score` | 素点 | decimal(4,1) | | | | |
| 32 | `track_diff` | 馬場差 | decimal(4,1) | | | | |
| 33 | `pace` | ペース | decimal(4,1) | | | | |
| 34 | `slow_start` | 出遅 | decimal(4,1) | | | | |
| 35 | `position_taken` | 位置取り | decimal(4,1) | | | | |
| 36 | `handicap` | 不利 | decimal(4,1) | | | | |
| 37 | `front_handicap` | 前不利 | decimal(4,1) | | | | |
| 38 | `mid_handicap` | 中不利 | decimal(4,1) | | | | |
| 39 | `rear_handicap` | 後不利 | decimal(4,1) | | | | |
| 40 | `race_score` | レース | decimal(4,1) | | | | |
| 41 | `course_taken` | コース取り | smallint | | | | |
| 42 | `improvement_code` | 上昇度コード | smallint | | | | |
| 43 | `result_class_code` | クラスコード | char(2) | | | | |
| 44 | `body_condition_code` | 馬体コード | smallint | | | | |
| 45 | `spirit_code` | 気配コード | smallint | | | | |
| 46 | `race_pace` | レースペース | decimal(4,1) | | | | |
| 47 | `horse_pace` | 馬ペース | decimal(4,1) | | | | |
| 48 | `ten_index` | テン指数 | decimal(4,1) | | | | |
| 49 | `agari_index` | 上がり指数 | decimal(4,1) | | | | |
| 50 | `pace_index` | ペース指数 | decimal(4,1) | | | | |
| 51 | `race_p_index` | レースP指数 | decimal(4,1) | | | | |
| 52 | `top2_horse_name` | 1(2)着馬名 | varchar(36) | | | | |
| 53 | `top2_time_diff` | 1(2)着タイム差 | decimal(4,1) | | | | 秒 |
| 54 | `front3f` | 前3F | decimal(4,1) | | | | 秒 |
| 55 | `rear3f` | 後3F | decimal(4,1) | | | | 秒 |
| 56 | `corner_order_1` | コーナー通過順1 | smallint | | | | 1コーナー通過順位 |
| 57 | `corner_order_2` | コーナー通過順2 | smallint | | | | 2コーナー通過順位 |
| 58 | `corner_order_3` | コーナー通過順3 | smallint | | | | 3コーナー通過順位 |
| 59 | `corner_order_4` | コーナー通過順4 | smallint | | | | 4コーナー通過順位 |
| 60 | `front3f_lead_diff` | 前3F先頭差 | decimal(4,1) | | | | 秒 |
| 61 | `rear3f_lead_diff` | 後3F先頭差 | decimal(4,1) | | | | 秒 |
| 62 | `jockey_code` | 騎手コード | char(5) | | | m_jockeys | |
| 63 | `trainer_code` | 調教師コード | char(5) | | | m_trainers | |
| 64 | `horse_weight` | 馬体重 | smallint | | | | kg |
| 65 | `horse_weight_diff` | 馬体重増減 | smallint | | | | kg |
| 66 | `weather_code` | 天候コード | smallint | | | | 1:晴 2:曇 3:雨 4:小雨 5:雪 6:小雪 |
| 67 | `race_leg_type` | レース脚質 | smallint | | | | |
| 68 | `payout_tansho` | 単勝払戻 | int | | | | 円（100円あたり） |
| 69 | `payout_fukusho` | 複勝払戻 | int | | | | 円（100円あたり） |
| 70 | `prize_main` | 本賞金 | int | | | | 万円単位 |
| 71 | `prize_collected` | 収得賞金 | int | | | | 万円単位 |
| 72 | `race_pace_flow` | レースペース流れ | smallint | | | | |
| 73 | `horse_pace_flow` | 馬ペース流れ | smallint | | | | |
| 74 | `final_corner_course` | 4角コース取り | smallint | | | | |
| 75 | `is_sokuho` | 速報フラグ | tinyint(1) | | | | 1:速報 0:確定 |

---

## インデックス

| インデックス名 | カラム | 種類 |
|--------------|--------|------|
| PRIMARY | `venue_code`, `race_year`, `kai`, `nichi`, `race_no`, `horse_no` | PRIMARY KEY |
| `idx_results_pedigree` | `pedigree_no` | INDEX |
| `idx_results_finish` | `finish_order` | INDEX |
| `idx_results_jockey` | `jockey_code` | INDEX |
| `idx_results_trainer` | `trainer_code` | INDEX |
| `idx_results_sokuho` | `is_sokuho` | INDEX |

---

## 外部キー制約

| 制約名 | カラム | 参照テーブル | 参照カラム |
|--------|--------|-------------|-----------|
| `fk_race_results_races` | `venue_code`, `race_year`, `kai`, `nichi`, `race_no` | `races` | 同左 |
| `fk_race_results_jockeys` | `jockey_code` | `m_jockeys` | `jockey_code` |
| `fk_race_results_trainers` | `trainer_code` | `m_trainers` | `trainer_code` |
