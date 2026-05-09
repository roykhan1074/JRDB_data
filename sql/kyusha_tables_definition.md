# テーブル定義書 — 厩舎指数信頼度分析

| 項目 | 内容 |
|---|---|
| 作成日 | 2026-05-06 |
| 対象DB | racing |
| 関連ファイル | `sql/kyusha_analysis.sql`、`sql/kyusha_analysis_design.md` |

---

## テーブル一覧

| テーブル名 | 種別 | 説明 |
|---|---|---|
| [T_KYUSHA_RACE_LOG](#1-t_kyusha_race_log) | ファクトテーブル | 厩舎×レース 1行の非正規化ログ |
| [T_KYUSHA_FACTOR_AGG](#2-t_kyusha_factor_agg) | 集計テーブル | 厩舎×年×ファクター別の集計済みデータ |

---

## 1. T_KYUSHA_RACE_LOG

### 概要

| 項目 | 内容 |
|---|---|
| テーブル名 | T_KYUSHA_RACE_LOG |
| 説明 | 厩舎成績ログ（分析ファクトテーブル） |
| エンジン | InnoDB |
| 文字コード | utf8mb4 |
| 粒度 | 1行 = 1頭分の出走記録（競走取消・除外を含む） |
| 主なソース | T_KYI（出馬表）× T_BAC（レース基本情報）× T_SED（成績） |

### データ概況（2026-05-06 時点）

| 項目 | 値 |
|---|---|
| 総行数 | 290,323 |
| 期間 | 2020-01-05 〜 2026-05-03 |
| 調教師数 | 358 |
| 成績格納済み | 289,811（未格納 512件はレース前または速報待ち） |

### カラム定義

#### レースキー（主キー構成カラム）

| # | カラム名 | 型 | NULL | 説明 |
|---|---|---|---|---|
| 1 | `course_code` | CHAR(2) | NOT NULL | 場コード（例: `05`=東京） |
| 2 | `year_code` | CHAR(2) | NOT NULL | 年（西暦下2桁、例: `26`） |
| 3 | `kai` | CHAR(1) | NOT NULL | 回（例: `1`） |
| 4 | `day_code` | CHAR(1) | NOT NULL | 日（16進数、例: `1`〜`f`） |
| 5 | `race_num` | CHAR(2) | NOT NULL | レース番号（例: `11`） |
| 6 | `uma_num` | CHAR(2) | NOT NULL | 馬番（例: `07`） |

> レースキー6カラムの組み合わせで1頭1レースを一意に識別する。T_KYI / T_BAC / T_SED と共通のキー体系。

#### 日付

| # | カラム名 | 型 | NULL | 説明 |
|---|---|---|---|---|
| 7 | `ymd` | CHAR(8) | NOT NULL | 開催年月日（YYYYMMDD形式、例: `20260503`）。T_BAC から取得。 |

#### 調教師

| # | カラム名 | 型 | NULL | 説明 |
|---|---|---|---|---|
| 8 | `trainer_code` | CHAR(5) | NULL | 調教師コード（例: `01234`）。T_KYI.trainer_code から TRIM して格納。 |
| 9 | `trainer_name` | VARCHAR(12) | NULL | 調教師名（全角6文字以内）。T_KYI.trainer_name から取得。 |

#### 厩舎評価

| # | カラム名 | 型 | NULL | 説明 |
|---|---|---|---|---|
| 10 | `kyusha_index` | DECIMAL(5,1) | NULL | 厩舎指数。T_KYI.kyusha_index（CHAR(5)）を数値変換して格納。変換不可の場合は NULL。範囲: -20.0 〜 40.0。 |
| 11 | `kyusha_hyoka` | CHAR(1) | NULL | 厩舎評価コード。`1`=A(最高) / `2`=B / `3`=C(平均) / `4`=D(低)。T_KYI.kyusha_hyoka から取得。 |

> `kyusha_index` は T_KYI では CHAR(5) で格納されているが、本テーブルでは DECIMAL(5,1) に変換済み。  
> これにより集計クエリで CAST/TRIM が不要になり、帯域判定が型安全に行える。

#### オッズ・人気

| # | カラム名 | 型 | NULL | 説明 |
|---|---|---|---|---|
| 12 | `kijun_odds` | DECIMAL(6,1) | NULL | 基準単勝オッズ。T_KYI.kijun_odds（CHAR(5)）を数値変換。変換不可の場合は NULL。 |
| 13 | `kijun_ninki` | SMALLINT | NULL | 基準人気順位（1〜18）。T_KYI.kijun_ninki（CHAR(2)）を数値変換。変換不可の場合は NULL。 |

#### レース条件

| # | カラム名 | 型 | NULL | 説明 |
|---|---|---|---|---|
| 14 | `distance` | CHAR(4) | NULL | 距離（m単位、例: `1600`）。T_BAC.distance から取得。 |
| 15 | `tds_code` | CHAR(1) | NULL | 芝ダ障害コード。`1`=芝 / `2`=ダート / `3`=障害。T_BAC.tds_code から取得。 |
| 16 | `class` | CHAR(2) | NULL | 条件クラス。`A1`=新馬 / `A3`=未勝利 / `05`=1勝 / `10`=2勝 / `16`=3勝 / `OP`=OP。T_BAC.class から取得。 |
| 17 | `heads` | CHAR(2) | NULL | 頭数（例: `16`）。T_BAC.heads から取得。 |

#### 成績

| # | カラム名 | 型 | NULL | 説明 |
|---|---|---|---|---|
| 18 | `finish_order` | CHAR(2) | NULL | 着順（例: `01`〜`18`）。**T_SED 未格納の場合は NULL**（レース前・速報待ち）。 |
| 19 | `ijou_kubun` | CHAR(1) | NULL | 異常区分。`0` または `''`=正常完走 / `1`=競走取消 / `2`=競走除外 等。T_SED.ijou_kubun から取得。 |
| 20 | `win_payout` | INT | NULL | 単勝払戻（円/100円ベット）。正常完走（`ijou_kubun IN ('0','')` ）以外は `0`。T_SED.win から取得。 |
| 21 | `place_payout` | INT | NULL | 複勝払戻（円/100円ベット）。正常完走以外は `0`。T_SED.place から取得。 |

#### 管理

| # | カラム名 | 型 | NULL | 説明 |
|---|---|---|---|---|
| 22 | `load_date` | CHAR(8) | NOT NULL | 本テーブルへの格納日（YYYYMMDD形式）。定期実行のたびに最新日付で上書きされる。 |

### キー・インデックス定義

| 種別 | インデックス名 | カラム | 用途 |
|---|---|---|---|
| PRIMARY KEY | — | `course_code`, `year_code`, `kai`, `day_code`, `race_num`, `uma_num` | 一意制約・UPSERT（ON DUPLICATE KEY UPDATE）の照合キー |
| INDEX | `idx_kyusha_log_trainer_ymd` | `trainer_code`, `ymd` | 特定厩舎の時系列クエリ（例: 直近2年の実績取得） |
| INDEX | `idx_kyusha_log_trainer_code` | `trainer_code` | 厩舎単位での全件取得 |
| INDEX | `idx_kyusha_log_ymd` | `ymd` | 日次バッチでの差分取得 |

---

## 2. T_KYUSHA_FACTOR_AGG

### 概要

| 項目 | 内容 |
|---|---|
| テーブル名 | T_KYUSHA_FACTOR_AGG |
| 説明 | 厩舎ファクター別集計（出馬表・信頼度スコア表示用） |
| エンジン | InnoDB |
| 文字コード | utf8mb4 |
| 粒度 | 1行 = 調教師 × 集計年 × ファクター種別 × ファクター値 |
| 形式 | EAV（Entity-Attribute-Value）形式。新ファクターをカラム変更なしで追加可能。 |
| 主なソース | T_KYUSHA_RACE_LOG（集計元） |

### データ概況（2026-05-06 時点）

| 項目 | 値 |
|---|---|
| 総行数 | 12,895 |
| 調教師数 | 358 |
| 集計年 | 2020 〜 2026（7年分） |
| factor_type 種類 | 2種 |

### カラム定義

#### 主キー構成カラム

| # | カラム名 | 型 | NULL | 説明 |
|---|---|---|---|---|
| 1 | `trainer_code` | CHAR(5) | NOT NULL | 調教師コード。T_KYUSHA_RACE_LOG.trainer_code と対応。 |
| 2 | `agg_year` | CHAR(4) | NOT NULL | 集計年（YYYY形式、例: `2025`）。T_KYUSHA_RACE_LOG.ymd の先頭4文字から生成。 |
| 3 | `factor_type` | VARCHAR(30) | NOT NULL | ファクター種別（詳細は後述の「factor_type 定義」参照）。 |
| 4 | `factor_value` | VARCHAR(40) | NOT NULL | ファクター値（factor_type ごとに定義された文字列）。 |

#### 調教師情報

| # | カラム名 | 型 | NULL | 説明 |
|---|---|---|---|---|
| 5 | `trainer_name` | VARCHAR(12) | NULL | 調教師名。同一 `trainer_code` に複数の名前表記がある場合は `MAX()` で最新を採用。 |

#### 集計カウント

| # | カラム名 | 型 | NULL | デフォルト | 説明 |
|---|---|---|---|---|---|
| 6 | `total_count` | INT | NOT NULL | 0 | 集計対象の出走数。異常区分（取消・除外等）を除いた正常完走レコードのみをカウント。 |
| 7 | `win_count` | INT | NOT NULL | 0 | 1着回数。 |
| 8 | `place_count` | INT | NOT NULL | 0 | 複勝（3着以内）回数。 |
| 9 | `win_payout_sum` | BIGINT | NOT NULL | 0 | 単勝払戻の合計（円）。`win_recovery` の再計算元として保持。 |
| 10 | `place_payout_sum` | BIGINT | NOT NULL | 0 | 複勝払戻の合計（円）。`place_recovery` の再計算元として保持。 |

> `win_count` / `place_count` / `*_payout_sum` は生カウントを保持しているため、複数年を集約する際も `SUM()` で正確に再集計できる（平均の平均問題が発生しない）。

#### 計算値（表示用）

| # | カラム名 | 型 | NULL | 説明 |
|---|---|---|---|---|
| 11 | `win_rate` | DECIMAL(5,1) | NULL | 勝率（%）。`win_count / total_count × 100`。小数第1位まで。 |
| 12 | `place_rate` | DECIMAL(5,1) | NULL | 複勝率（%）。`place_count / total_count × 100`。小数第1位まで。 |
| 13 | `win_recovery` | DECIMAL(6,1) | NULL | 単勝回収率（円/100円ベット）。`win_payout_sum / total_count`。小数第1位まで。 |
| 14 | `place_recovery` | DECIMAL(6,1) | NULL | 複勝回収率（円/100円ベット）。`place_payout_sum / total_count`。小数第1位まで。 |

> これらは `*_payout_sum` と `total_count` から再計算可能な冗長値。表示パフォーマンスのために事前計算して保持する。

#### 管理

| # | カラム名 | 型 | NULL | 説明 |
|---|---|---|---|---|
| 15 | `updated_at` | DATETIME | NOT NULL | 最終更新日時。`ON UPDATE CURRENT_TIMESTAMP` により UPSERT のたびに自動更新。 |

### キー・インデックス定義

| 種別 | インデックス名 | カラム | 用途 |
|---|---|---|---|
| PRIMARY KEY | — | `trainer_code`, `agg_year`, `factor_type`, `factor_value` | 一意制約・UPSERT の照合キー |
| INDEX | `idx_kyusha_agg_factor_year` | `factor_type`, `factor_value`, `agg_year` | ファクター横断の分析クエリ（例: 全厩舎の `kyusha_idx` 帯域別比較） |
| INDEX | `idx_kyusha_agg_year_trainer` | `agg_year`, `trainer_code` | 年単位での厩舎一覧取得 |
| INDEX | `idx_kyusha_agg_trainer_code` | `trainer_code` | 出馬表API: 特定厩舎の全ファクターを取得 |

### factor_type 定義

#### `kyusha_idx`（厩舎指数帯別）

厩舎指数の帯域ごとに成績を集計。指数と回収率の連動性（信頼度）を可視化するために使用。

**境界値ルール（左閉右開）**: 下限値を含み、上限値を含まない。例: 指数 `30.0` は `30~40` に入る。

| factor_value | 指数の範囲 | 下限 | 上限 |
|---|---|---|---|
| `<-10` | −10 未満 | — | −10（含まない） |
| `-10~0` | −10 以上 0 未満 | −10（含む） | 0（含まない） |
| `0~10` | 0 以上 10 未満 | 0（含む） | 10（含まない） |
| `10~20` | 10 以上 20 未満 | 10（含む） | 20（含まない） |
| `20~30` | 20 以上 30 未満 | 20（含む） | 30（含まない） |
| `30~40` | 30 以上（最大40） | 30（含む） | 40（含む） |

#### `kyusha_idx_x_odds`（指数符号 × オッズ帯 複合）

指数のプラス/マイナスと基準オッズの組み合わせ。穴馬での厩舎指数の有効性を判定するために使用。

| factor_value | 指数の条件 | オッズの条件 | 主な用途 |
|---|---|---|---|
| `minus_~10` | 0 未満（マイナス） | 10.0 倍未満 | — |
| `minus_10~` | 0 未満（マイナス） | 10.0 倍以上 | 穴馬で指数マイナス → 見送り根拠 |
| `plus_~10` | 0 以上（プラス） | 10.0 倍未満 | — |
| `plus_10~` | 0 以上（プラス） | 10.0 倍以上 | **穴馬で指数プラス → 狙い目判定の主要セル** |

> オッズの境界値 `10.0` も左閉右開。`kijun_odds >= 10.0` が `10~` に入る。

---

## テーブル間の関係

```
T_KYI ──┐
T_BAC ──┼──(JOIN)──▶ T_KYUSHA_RACE_LOG ──(集計)──▶ T_KYUSHA_FACTOR_AGG
T_SED ──┘
```

| 関係 | 内容 |
|---|---|
| T_KYI → T_KYUSHA_RACE_LOG | `(course_code, year_code, kai, day_code, race_num, uma_num)` で INNER JOIN |
| T_BAC → T_KYUSHA_RACE_LOG | 同上（レース条件・日付を取得） |
| T_SED → T_KYUSHA_RACE_LOG | 同上で LEFT JOIN（成績未確定の場合は NULL） |
| T_KYUSHA_RACE_LOG → T_KYUSHA_FACTOR_AGG | `trainer_code` × `ymd` で GROUP BY して集計 |

> 外部キー制約は設定していない。T_KYI / T_BAC / T_SED はパイプラインで独立管理されており、本テーブルは分析専用の非正規化コピーとして位置付けるため。

---

## 更新・運用

| 項目 | 内容 |
|---|---|
| 更新頻度 | 毎週木曜日推奨（T_SED 正式版 SEC 確定後） |
| 更新方法 | `sql/kyusha_analysis.sql` の Part2 → Part3 を順に実行 |
| 冪等性 | 両テーブルとも `ON DUPLICATE KEY UPDATE` による UPSERT のため、重複実行しても安全 |
| 初回のみ | Part1（DDL）を実行してテーブルを作成 |
