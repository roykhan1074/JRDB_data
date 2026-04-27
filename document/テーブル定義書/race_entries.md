# テーブル定義書: race_entries

## テーブル概要

| 項目 | 内容 |
|------|------|
| テーブル名 | `race_entries` |
| 論理名 | 出走馬情報 |
| エンジン | InnoDB |
| 文字セット | utf8mb4_unicode_ci |
| 説明 | レースへの出走馬ごとの指数・予想情報。KYI（出馬表）ファイルから変換・格納。 |

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
| 6 | `horse_no` | 馬番 | smallint | ✓ | ✓ | | 1〜18 |
| 7 | `pedigree_no` | 血統登録番号 | char(8) | | | m_horses | |
| 8 | `horse_name` | 馬名 | varchar(36) | | | | 全角18文字 |
| 9 | `idm` | IDM | decimal(4,1) | | | | JRDB独自指数 |
| 10 | `jockey_index` | 騎手指数 | decimal(4,1) | | | | |
| 11 | `info_index` | 情報指数 | decimal(4,1) | | | | |
| 12 | `composite_index` | 総合指数 | decimal(4,1) | | | | |
| 13 | `leg_type` | 脚質 | smallint | | | | 1:逃 2:先 3:差 4:追 5:自在 |
| 14 | `distance_aptitude` | 距離適性 | smallint | | | | 1:短距離 2:マイル 3:中距離 4:クラシック 5:長距離 6:障害 |
| 15 | `improvement_level` | 上昇度 | smallint | | | | |
| 16 | `rotation` | ローテーション | smallint | | | | 前走からの間隔（日数） |
| 17 | `base_odds` | 基準単勝オッズ | decimal(4,1) | | | | |
| 18 | `base_popularity` | 基準単勝人気 | smallint | | | | |
| 19 | `base_place_odds` | 基準複勝オッズ | decimal(4,1) | | | | |
| 20 | `base_place_popularity` | 基準複勝人気 | smallint | | | | |
| 21 | `specific_honmei` | 特定本命 | smallint | | | | 印 |
| 22 | `specific_honsho` | 特定対抗 | smallint | | | | 印 |
| 23 | `specific_tanna` | 特定単穴 | smallint | | | | 印 |
| 24 | `specific_sankaku` | 特定連下 | smallint | | | | 印 |
| 25 | `specific_batsu` | 特定×印 | smallint | | | | 印 |
| 26 | `general_honmei` | 総合本命 | smallint | | | | 印 |
| 27 | `general_honsho` | 総合対抗 | smallint | | | | 印 |
| 28 | `general_tanna` | 総合単穴 | smallint | | | | 印 |
| 29 | `general_sankaku` | 総合連下 | smallint | | | | 印 |
| 30 | `general_batsu` | 総合×印 | smallint | | | | 印 |
| 31 | `popularity_index` | 人気指数 | smallint | | | | |
| 32 | `training_index` | 調教指数 | decimal(4,1) | | | | |
| 33 | `stable_index` | 厩舎指数 | decimal(4,1) | | | | |
| 34 | `training_arrow_code` | 調教矢印コード | smallint | | | | |
| 35 | `stable_eval_code` | 厩舎評価コード | smallint | | | | |
| 36 | `jockey_renso_rate` | 騎手連対率 | decimal(3,1) | | | | % |
| 37 | `gekiso_index` | 激走指数 | smallint | | | | |
| 38 | `hoof_code` | 蹄コード | char(2) | | | | |
| 39 | `heavy_aptitude_code` | 重適性コード | smallint | | | | |
| 40 | `class_code` | クラスコード | char(2) | | | | |
| 41 | `blinker` | ブリンカー | char(1) | | | | 0:なし 1:あり |
| 42 | `jockey_name` | 騎手名 | varchar(12) | | | | |
| 43 | `weight_load` | 負担重量 | smallint | | | | 単位:100g |
| 44 | `apprentice_class` | 見習い区分 | smallint | | | | |
| 45 | `trainer_name` | 調教師名 | varchar(12) | | | | |
| 46 | `trainer_affiliation` | 調教師所属 | varchar(4) | | | | |
| 47 | `prev_result_key_1` | 前走1成績キー | char(16) | | | | |
| 48 | `prev_result_key_2` | 前走2成績キー | char(16) | | | | |
| 49 | `prev_result_key_3` | 前走3成績キー | char(16) | | | | |
| 50 | `prev_result_key_4` | 前走4成績キー | char(16) | | | | |
| 51 | `prev_result_key_5` | 前走5成績キー | char(16) | | | | |
| 52 | `prev_race_key_1` | 前走1レースキー | char(8) | | | | |
| 53 | `prev_race_key_2` | 前走2レースキー | char(8) | | | | |
| 54 | `prev_race_key_3` | 前走3レースキー | char(8) | | | | |
| 55 | `prev_race_key_4` | 前走4レースキー | char(8) | | | | |
| 56 | `prev_race_key_5` | 前走5レースキー | char(8) | | | | |
| 57 | `frame_no` | 枠番 | smallint | | | | 1〜8 |
| 58 | `mark_composite` | 印_総合 | smallint | | | | |
| 59 | `mark_idm` | 印_IDM | smallint | | | | |
| 60 | `mark_info` | 印_情報 | smallint | | | | |
| 61 | `mark_jockey` | 印_騎手 | smallint | | | | |
| 62 | `mark_stable` | 印_厩舎 | smallint | | | | |
| 63 | `mark_training` | 印_調教 | smallint | | | | |
| 64 | `mark_gekiso` | 印_激走 | smallint | | | | |
| 65 | `turf_aptitude_code` | 芝適性コード | char(1) | | | | |
| 66 | `dirt_aptitude_code` | ダート適性コード | char(1) | | | | |
| 67 | `jockey_code` | 騎手コード | char(5) | | | m_jockeys | |
| 68 | `trainer_code` | 調教師コード | char(5) | | | m_trainers | |
| 69 | `prize_earned` | 獲得賞金 | int | | | | 万円単位 |
| 70 | `prize_collected` | 収得賞金 | int | | | | 万円単位 |
| 71 | `condition_class` | 条件クラス | smallint | | | | |
| 72 | `ten_index` | テン指数 | decimal(4,1) | | | | 道中前半 |
| 73 | `pace_index` | ペース指数 | decimal(4,1) | | | | |
| 74 | `agari_index` | 上がり指数 | decimal(4,1) | | | | 後半 |
| 75 | `position_index` | 位置取り指数 | decimal(4,1) | | | | |
| 76 | `pace_forecast` | ペース予想 | char(1) | | | | H/M/S |
| 77 | `middle_rank` | 道中順位 | smallint | | | | |
| 78 | `middle_diff` | 道中差 | smallint | | | | |
| 79 | `middle_inner_outer` | 道中内外 | smallint | | | | |
| 80 | `last3f_rank` | 後3F順位 | smallint | | | | |
| 81 | `last3f_diff` | 後3F差 | smallint | | | | |
| 82 | `last3f_inner_outer` | 後3F内外 | smallint | | | | |
| 83 | `goal_rank` | ゴール順位 | smallint | | | | |
| 84 | `goal_diff` | ゴール差 | smallint | | | | |
| 85 | `goal_inner_outer` | ゴール内外 | smallint | | | | |
| 86 | `development_symbol` | 展開記号 | char(1) | | | | |
| 87 | `distance_aptitude2` | 距離適性2 | smallint | | | | |
| 88 | `frame_weight` | 枠確定馬体重 | smallint | | | | kg |
| 89 | `frame_weight_diff` | 枠確定馬体重差 | smallint | | | | kg |
| 90 | `cancellation_flag` | 取消フラグ | smallint | | | | 0:出走 1:取消 |
| 91 | `sex_code` | 性別コード | smallint | | | | |
| 92 | `owner_name` | 馬主名 | varchar(40) | | | | |
| 93 | `owner_assoc_code` | 馬主協会コード | char(2) | | | | |
| 94 | `horse_symbol_code` | 馬記号コード | char(2) | | | | |
| 95 | `gekiso_rank` | 激走順位 | smallint | | | | |
| 96 | `ls_index_rank` | LS指数順位 | smallint | | | | |
| 97 | `ten_index_rank` | テン指数順位 | smallint | | | | |
| 98 | `pace_index_rank` | ペース指数順位 | smallint | | | | |
| 99 | `agari_index_rank` | 上がり指数順位 | smallint | | | | |
| 100 | `position_index_rank` | 位置取り指数順位 | smallint | | | | |
| 101 | `jockey_tansho_rate` | 騎手単勝率 | decimal(3,1) | | | | % |
| 102 | `jockey_3rd_rate` | 騎手3着内率 | decimal(3,1) | | | | % |
| 103 | `transport_class` | 輸送区分 | char(1) | | | | |
| 104 | `running_style` | 走法 | char(8) | | | | |
| 105 | `body_type` | 体型 | char(24) | | | | |
| 106 | `body_type_summary_1` | 体型総合1 | char(3) | | | | |
| 107 | `body_type_summary_2` | 体型総合2 | char(3) | | | | |
| 108 | `body_type_summary_3` | 体型総合3 | char(3) | | | | |
| 109 | `horse_note_1` | 馬特記1 | char(3) | | | | |
| 110 | `horse_note_2` | 馬特記2 | char(3) | | | | |
| 111 | `horse_note_3` | 馬特記3 | char(3) | | | | |
| 112 | `start_index` | スタート指数 | decimal(3,1) | | | | |
| 113 | `slow_start_rate` | 出遅率 | decimal(3,1) | | | | % |
| 114 | `ref_prev_race` | 参考前走 | char(2) | | | | |
| 115 | `ref_prev_jockey_code` | 参考前走騎手コード | char(5) | | | | |
| 116 | `mankken_index` | 万券指数 | smallint | | | | |
| 117 | `mankken_mark` | 万券印 | smallint | | | | |
| 118 | `descent_flag` | 降級フラグ | smallint | | | | |
| 119 | `gekiso_type` | 激走タイプ | char(2) | | | | |
| 120 | `rest_reason_code` | 休養理由コード | char(2) | | | | |
| 121 | `flags` | フラグ | char(16) | | | | |
| 122 | `stable_entry_nth_run` | 入厩何走目 | smallint | | | | |
| 123 | `stable_entry_date` | 入厩年月日 | date | | | | |
| 124 | `days_before_stable_entry` | 入厩前日数 | smallint | | | | |
| 125 | `pasture_destination` | 放牧先 | varchar(50) | | | | |
| 126 | `pasture_rank` | 放牧先ランク | char(1) | | | | |
| 127 | `stable_rank` | 厩舎ランク | smallint | | | | |

---

## インデックス

| インデックス名 | カラム | 種類 |
|--------------|--------|------|
| PRIMARY | `venue_code`, `race_year`, `kai`, `nichi`, `race_no`, `horse_no` | PRIMARY KEY |
| `idx_entries_pedigree` | `pedigree_no` | INDEX |
| `idx_entries_jockey` | `jockey_code` | INDEX |
| `idx_entries_trainer` | `trainer_code` | INDEX |
| `idx_entries_date` | `venue_code`, `race_year`, `nichi` | INDEX |

---

## 外部キー制約

| 制約名 | カラム | 参照テーブル | 参照カラム |
|--------|--------|-------------|-----------|
| `fk_race_entries_races` | `venue_code`, `race_year`, `kai`, `nichi`, `race_no` | `races` | 同左 |
| `fk_race_entries_horses` | `pedigree_no` | `m_horses` | `pedigree_no` |
| `fk_race_entries_jockeys` | `jockey_code` | `m_jockeys` | `jockey_code` |
| `fk_race_entries_trainers` | `trainer_code` | `m_trainers` | `trainer_code` |

---

## 関連テーブル

| テーブル | 関係 | 説明 |
|---------|------|------|
| `races` | N:1 | 開催レース情報 |
| `m_horses` | N:1 | 馬マスタ |
| `m_jockeys` | N:1 | 騎手マスタ |
| `m_trainers` | N:1 | 調教師マスタ |
| `training_analysis` | 1:1 | 調教分析データ |
