# テーブル定義書 一覧

データベース: `racing`  
最終更新: 2026-05-17

---

## テーブル構成

実際に稼働しているテーブル構成。正規化テーブル（races / race_entries 等）は設計のみで未実装。

```
racing DB
├── JRDBデータ RAWテーブル（CSV直接格納・変換処理の出力先）
│   ├── T_BAC               レース基本情報
│   ├── T_KYI               出馬表
│   ├── T_CYB               調教分析
│   ├── T_SED               成績データ
│   ├── T_UKC               馬マスタ
│   └── T_SRB               成績速報
│
├── EX指数テーブル（穴馬激走期待値スコア）
│   ├── T_ANABA_RACE_LOG    穴馬ファクトテーブル（kijun_odds≥10の馬のみ）
│   ├── T_ANABA_FACTOR_AGG  ファクター別集計（EAV形式）
│   └── T_ANABA_SCORE       EX指数（出馬表表示用・全馬対象）
│
├── 分析用集計テーブル
│   ├── T_COMBO_RECOVERY    騎手×調教師コンビ回収率
│   ├── T_KYUSHA_FACTOR_AGG 厩舎ファクター別集計
│   └── T_COURSE_FACTOR_AGG コース別ファクター集計
│
└── 騎手・調教師分析テーブル
    ├── T_KISHU_RACE_LOG    騎手レースログ
    ├── T_KISHU_FACTOR_AGG  騎手ファクター別集計
    ├── T_KYUSHA_RACE_LOG   厩舎レースログ
    └── T_KYUSHA_FACTOR_AGG 厩舎ファクター別集計（上記と同テーブル）
```

---

## JRDBデータ RAWテーブル

| テーブル名 | 論理名 | ソースファイル | 定義書 |
|-----------|--------|-------------|--------|
| `T_BAC` | レース基本情報 | BAC + YYMMDD.txt | [t_bac.md](t_bac.md) |
| `T_KYI` | 出馬表 | KYI + YYMMDD.txt | [t_kyi.md](t_kyi.md)（※旧 t_kyi.md） |
| `T_CYB` | 調教分析 | CYB + YYMMDD.txt | [t_cyb.md](t_cyb.md) |
| `T_SED` | 成績データ | SED + YYMMDD.txt | [t_sed.md](t_sed.md) |
| `T_UKC` | 馬マスタ | UKC + YYMMDD.txt | [t_ukc.md](t_ukc.md) |
| `T_SRB` | 成績速報 | SRB + YYMMDD.txt | [t_srb.md](t_srb.md) |

主キー構造（共通）: `course_code + year_code + kai + day_code + race_num + uma_num`

---

## EX指数テーブル

| テーブル名 | 論理名 | 主キー | ETL |
|-----------|--------|--------|-----|
| `T_ANABA_RACE_LOG` | 穴馬ファクトテーブル | course_code〜uma_num | anaba_index.sql Part2 |
| `T_ANABA_FACTOR_AGG` | ファクター別集計 | factor_type + factor_value + course_code + tds_code + dist_band | anaba_index.sql Part3 |
| `T_ANABA_SCORE` | EX指数（出馬表用） | course_code〜uma_num | anaba_index.sql Part4 |

詳細は [EX指数仕様書](../分析レポート/穴馬指数_仕様書.md) を参照。

---

## 分析用集計テーブル

| テーブル名 | 用途 | 生成元 |
|-----------|------|--------|
| `T_COMBO_RECOVERY` | 騎手×調教師コンビ複勝回収率（出馬表の騎×厩列） | 独自ETL |
| `T_KYUSHA_FACTOR_AGG` | 厩舎ファクター別集計（厩舎指数×オッズ帯など） | kyusha_analysis.sql |
| `T_COURSE_FACTOR_AGG` | コース別ファクター集計（コース別傾向ページ用） | course_etl系SQL |

### T_KYUSHA_FACTOR_AGG の主なインデックス

```sql
PRIMARY KEY (trainer_code, agg_year, factor_type, factor_value)
INDEX idx_kyusha_agg_factor_year  (factor_type, factor_value, agg_year)
INDEX idx_kyusha_anaba_covering   (factor_type, factor_value, trainer_code, total_count, place_payout_sum)
```

`idx_kyusha_anaba_covering` は entries クエリのサブクエリ（穴信頼度集計）をインデックスオンリースキャンで処理するためのカバリングインデックス。

---

## データフロー

```
JRDBサーバー（zip）
  → ダウンロード（download.html / POST /api/run）
  → テキスト変換（src/pipeline.ts）
  → CSV → MySQL UPSERT（T_BAC / T_KYI / T_CYB / T_SED / T_UKC / T_SRB）
  ↓
EX指数 ETL（download.html / POST /api/anaba-etl）
  → anaba_index.sql Part2〜4
  → T_ANABA_RACE_LOG → T_ANABA_FACTOR_AGG → T_ANABA_SCORE
  ↓
出馬表 API（GET /api/races/:key/entries）
  → T_KYI × T_CYB × T_COMBO_RECOVERY × T_KYUSHA_FACTOR_AGG × T_ANABA_SCORE × T_SED
  → JSON → entries.html
```
