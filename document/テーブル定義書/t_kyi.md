# テーブル定義書: t_kyi

## テーブル概要

| 項目 | 内容 |
|------|------|
| テーブル名 | `t_kyi` |
| 論理名 | KYI出馬表（JRDB生テーブル） |
| エンジン | InnoDB |
| 文字セット | utf8mb4 |
| ソースファイル | `KYI` + YYMMDD + `.txt` |
| 説明 | JRDBのKYIファイルを固定長からCSV変換しそのまま格納したRAWテーブル。出走馬ごとの各種指数・予想印を保持。正規化テーブルは `race_entries`。 |

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
| 7 | `blood_reg_num` | 血統登録番号 | char(8) | | | |
| 8 | `uma_name` | 馬名 | varchar(36) | | | |
| 9 | `idm` | IDM | char(5) | | | IDM指数 |
| 10 | `kishu_index` | 騎手指数 | char(5) | | | |
| 11 | `joho_index` | 情報指数 | char(5) | | | |
| 12 | `sogo_index` | 総合指数 | char(5) | | | |
| 13 | `kyakushitsu` | 脚質 | char(1) | | | 1:逃 2:先 3:差 4:追 5:自在 |
| 14 | `kyori_tekisei` | 距離適性 | char(1) | | | |
| 15 | `joshodo` | 上昇度 | char(1) | | | |
| 16 | `rotation` | ローテーション | char(3) | | | |
| 17 | `kijun_odds` | 基準単勝オッズ | char(5) | | | |
| 18 | `kijun_ninki` | 基準単勝人気 | char(2) | | | |
| 19 | `kijun_fukusho_odds` | 基準複勝オッズ | char(5) | | | |
| 20 | `kijun_fukusho_ninki` | 基準複勝人気 | char(2) | | | |
| 21 | `tokutei_honmei` | 特定本命 | char(3) | | | 印 |
| 22 | `tokutei_taikou` | 特定対抗 | char(3) | | | 印 |
| 23 | `tokutei_tanana` | 特定単穴 | char(3) | | | 印 |
| 24 | `tokutei_rengai` | 特定連下 | char(3) | | | 印 |
| 25 | `tokutei_batsu` | 特定×印 | char(3) | | | 印 |
| 26 | `sogo_honmei` | 総合本命 | char(3) | | | 印 |
| 27 | `sogo_taikou` | 総合対抗 | char(3) | | | 印 |
| 28 | `sogo_tanana` | 総合単穴 | char(3) | | | 印 |
| 29 | `sogo_rengai` | 総合連下 | char(3) | | | 印 |
| 30 | `sogo_batsu` | 総合×印 | char(3) | | | 印 |
| 31 | `ninki_index` | 人気指数 | char(5) | | | |
| 32 | `chokyo_index` | 調教指数 | char(5) | | | |
| 33 | `kyusha_index` | 厩舎指数 | char(5) | | | |
| 34 | `chokyo_yajirushi` | 調教矢印コード | char(1) | | | |
| 35 | `kyusha_hyoka` | 厩舎評価コード | char(1) | | | |
| 36 | `kishu_renntai_rate` | 騎手連対率 | char(4) | | | % |
| 37 | `gekiso_index` | 激走指数 | char(3) | | | |
| 38 | `hizume_code` | 蹄コード | char(2) | | | |
| 39 | `omo_tekisei` | 重適性コード | char(1) | | | |
| 40 | `class_code` | クラスコード | char(2) | | | |
| 41 | `blinker` | ブリンカー | char(1) | | | |
| 42 | `kishu_name` | 騎手名 | varchar(12) | | | |
| 43 | `futan_juryo` | 負担重量 | char(3) | | | 100g単位 |
| 44 | `minarai_kubun` | 見習い区分 | char(1) | | | |
| 45 | `trainer_name` | 調教師名 | varchar(12) | | | |
| 46 | `trainer_belong` | 調教師所属 | char(4) | | | |
| 47 | `prev1_seiseki_key` | 前走1成績キー | char(16) | | | |
| 48 | `prev2_seiseki_key` | 前走2成績キー | char(16) | | | |
| 49 | `prev3_seiseki_key` | 前走3成績キー | char(16) | | | |
| 50 | `prev4_seiseki_key` | 前走4成績キー | char(16) | | | |
| 51 | `prev5_seiseki_key` | 前走5成績キー | char(16) | | | |
| 52 | `prev1_race_key` | 前走1レースキー | char(8) | | | |
| 53 | `prev2_race_key` | 前走2レースキー | char(8) | | | |
| 54 | `prev3_race_key` | 前走3レースキー | char(8) | | | |
| 55 | `prev4_race_key` | 前走4レースキー | char(8) | | | |
| 56 | `prev5_race_key` | 前走5レースキー | char(8) | | | |
| 57 | `waku_num` | 枠番 | char(1) | | | 1〜8 |
| 58 | `in_sogo` | 印_総合 | char(1) | | | |
| 59 | `in_idm` | 印_IDM | char(1) | | | |
| 60 | `in_joho` | 印_情報 | char(1) | | | |
| 61 | `in_kishu` | 印_騎手 | char(1) | | | |
| 62 | `in_kyusha` | 印_厩舎 | char(1) | | | |
| 63 | `in_chokyo` | 印_調教 | char(1) | | | |
| 64 | `in_gekiso` | 印_激走 | char(1) | | | |
| 65 | `shiba_tekisei` | 芝適性コード | char(1) | | | |
| 66 | `dirt_tekisei` | ダート適性コード | char(1) | | | |
| 67 | `kishu_code` | 騎手コード | char(5) | | | |
| 68 | `trainer_code` | 調教師コード | char(5) | | | |
| 69 | `prize_earned` | 獲得賞金 | char(6) | | | 万円 |
| 70 | `prize_shu` | 収得賞金 | char(5) | | | 万円 |
| 71 | `joken_class` | 条件クラス | char(1) | | | |
| 72 | `ten_index` | テン指数 | char(5) | | | |
| 73 | `pace_index` | ペース指数 | char(5) | | | |
| 74 | `agari_index` | 上がり指数 | char(5) | | | |
| 75 | `ichi_index` | 位置取り指数 | char(5) | | | |
| 76 | `pace_yoso` | ペース予想 | char(1) | | | H/M/S |
| 77 | `michunaka_juni` | 道中順位 | char(2) | | | |
| 78 | `michunaka_sa` | 道中差 | char(2) | | | |
| 79 | `michunaka_naigai` | 道中内外 | char(1) | | | |
| 80 | `ato3f_juni` | 後3F順位 | char(2) | | | ⚠️ **レース中の後3F地点での通過順位（位置取り）**。上がり指数のランクとは別物。上がりの速さランクは `agari_index_juni`（#99）を使うこと |
| 81 | `ato3f_sa` | 後3F差 | char(2) | | | |
| 82 | `ato3f_naigai` | 後3F内外 | char(1) | | | |
| 83 | `goal_juni` | ゴール順位 | char(2) | | | |
| 84 | `goal_sa` | ゴール差 | char(2) | | | |
| 85 | `goal_naigai` | ゴール内外 | char(1) | | | |
| 86 | `tenkai_kigo` | 展開記号 | char(1) | | | |
| 87 | `kyori_tekisei2` | 距離適性2 | char(1) | | | |
| 88 | `waku_weight` | 枠確定馬体重 | char(3) | | | kg |
| 89 | `waku_weight_diff` | 枠確定馬体重差 | char(3) | | | kg |
| 90 | `torikeshi_flag` | 取消フラグ | char(1) | | | |
| 91 | `seibetsu_code` | 性別コード | char(1) | | | |
| 92 | `umanushi_name` | 馬主名 | varchar(40) | | | |
| 93 | `umanushi_code` | 馬主コード | char(2) | | | |
| 94 | `uma_kigo_code` | 馬記号コード | char(2) | | | |
| 95 | `gekiso_juni` | 激走順位 | char(2) | | | |
| 96 | `ls_index_juni` | LS指数順位 | char(2) | | | |
| 97 | `ten_index_juni` | テン指数順位 | char(2) | | | **前半3Fの速さランク**。出馬表の「前3F」表示に使用 |
| 98 | `pace_index_juni` | ペース指数順位 | char(2) | | | |
| 99 | `agari_index_juni` | 上がり指数順位 | char(2) | | | ⚠️ **後半3Fの速さランク**。出馬表の「後3F」表示に使用。`ato3f_juni`（#80）と混同注意 |
| 100 | `ichi_index_juni` | 位置取り指数順位 | char(2) | | | |
| 101 | `kishu_tansho_rate` | 騎手単勝率 | char(4) | | | % |
| 102 | `kishu_3uchi_rate` | 騎手3着内率 | char(4) | | | % |
| 103 | `yuso_kubun` | 輸送区分 | char(1) | | | |
| 104 | `soho` | 走法 | char(8) | | | |
| 105 | `taigata` | 体型 | char(24) | | | |
| 106 | `taigata_sogo1` | 体型総合1 | char(3) | | | |
| 107 | `taigata_sogo2` | 体型総合2 | char(3) | | | |
| 108 | `taigata_sogo3` | 体型総合3 | char(3) | | | |
| 109 | `uma_tokki1` | 馬特記1 | char(3) | | | |
| 110 | `uma_tokki2` | 馬特記2 | char(3) | | | |
| 111 | `uma_tokki3` | 馬特記3 | char(3) | | | |
| 112 | `uma_start_index` | 馬スタート指数 | char(4) | | | |
| 113 | `uma_okure_rate` | 馬出遅率 | char(4) | | | % |
| 114 | `sankosaki_mae` | 参考前走 | char(2) | | | |
| 115 | `sankosaki_kishu_code` | 参考前走騎手コード | char(5) | | | |
| 116 | `manbaken_index` | 万券指数 | char(3) | | | |
| 117 | `manbaken_in` | 万券印 | char(1) | | | |
| 118 | `kokyuu_flag` | 息抜きフラグ | char(1) | | | |
| 119 | `gekiso_type` | 激走タイプ | char(2) | | | |
| 120 | `kyuyo_riyuu_code` | 休養理由コード | char(2) | | | |
| 121 | `flag` | フラグ | char(16) | | | |
| 122 | `nyukyu_hashiri` | 入厩何走目 | char(2) | | | |
| 123 | `nyukyu_ymd` | 入厩年月日 | char(8) | | | YYYYMMDD |
| 124 | `nyukyu_nichi_mae` | 入厩何日前 | char(3) | | | |
| 125 | `hohbokusaki` | 放牧先 | varchar(50) | | | |
| 126 | `hohbokusaki_rank` | 放牧先ランク | char(1) | | | |
| 127 | `kyusha_rank` | 厩舎ランク | char(1) | | | |
| 128 | `load_file` | ロードファイル | varchar(20) | | | 取込元ファイル名 |
| 129 | `last_update` | 最終更新 | varchar(20) | | | |

---

## インデックス

| インデックス名 | カラム | 種類 |
|--------------|--------|------|
| PRIMARY | `course_code`, `year_code`, `kai`, `day_code`, `race_num`, `uma_num` | PRIMARY KEY |

---

## 備考

- 全フィールドが文字列型（JRDB固定長ファイルの仕様上）
- 分析用途には正規化済みの `race_entries` テーブルを使用すること
