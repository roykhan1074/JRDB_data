# テーブル定義書 一覧

データベース: `racing`  
最終更新: 2026-04-25

---

## テーブル構成

```
racing DB
├── 正規化テーブル（分析・アプリ用）
│   ├── races               レース基本情報
│   ├── race_entries        出走馬情報
│   ├── race_results        成績データ
│   ├── training_analysis   調教分析
│   ├── m_horses            馬マスタ
│   ├── m_jockeys           騎手マスタ
│   └── m_trainers          調教師マスタ
│
└── JRDBデータRAWテーブル（取込直接格納）
    ├── t_bac               BACレース基本情報
    ├── t_kyi               KYI出馬表
    ├── t_cyb               CYB調教分析
    ├── t_sed               SED成績データ
    ├── t_ukc               UKC馬マスタ
    └── t_srb               SRB成績速報
```

---

## 正規化テーブル

| テーブル名 | 論理名 | 主キー | ソース | 定義書 |
|-----------|--------|--------|--------|--------|
| `races` | レース基本情報 | venue_code + race_year + kai + nichi + race_no | BAC/KYI | [races.md](races.md) |
| `race_entries` | 出走馬情報 | + horse_no | KYI | [race_entries.md](race_entries.md) |
| `race_results` | 成績データ | + horse_no | SED/SRB | [race_results.md](race_results.md) |
| `training_analysis` | 調教分析 | + horse_no | CYB | [training_analysis.md](training_analysis.md) |
| `m_horses` | 馬マスタ | pedigree_no | UKC | [m_horses.md](m_horses.md) |
| `m_jockeys` | 騎手マスタ | jockey_code | KS | [m_jockeys.md](m_jockeys.md) |
| `m_trainers` | 調教師マスタ | trainer_code | CS | [m_trainers.md](m_trainers.md) |

---

## JRDB RAWテーブル

| テーブル名 | 論理名 | ソースファイル | 正規化先 | 定義書 |
|-----------|--------|-------------|---------|--------|
| `t_bac` | BACレース基本情報 | BAC + YYMMDD.txt | `races` | [t_bac.md](t_bac.md) |
| `t_kyi` | KYI出馬表 | KYI + YYMMDD.txt | `race_entries` | [t_kyi.md](t_kyi.md) |
| `t_cyb` | CYB調教分析 | CYB + YYMMDD.txt | `training_analysis` | [t_cyb.md](t_cyb.md) |
| `t_sed` | SED成績データ | SED + YYMMDD.txt | `race_results` | [t_sed.md](t_sed.md) |
| `t_ukc` | UKC馬マスタ | UKC + YYMMDD.txt | `m_horses` | [t_ukc.md](t_ukc.md) |
| `t_srb` | SRB成績速報 | SRB + YYMMDD.txt | `race_results` | [t_srb.md](t_srb.md) |

---

## ER図（主要リレーション）

```
m_horses ──────────────────────────────┐
m_jockeys ──────────────────────────┐  │
m_trainers ──────────────────────┐  │  │
                                 │  │  │
races ──────────────── race_entries ────┤
  │                       │            │
  └──────── race_results  └── training_analysis
```

### 外部キー関係

- `race_entries.venue_code...race_no` → `races`
- `race_entries.pedigree_no` → `m_horses.pedigree_no`
- `race_entries.jockey_code` → `m_jockeys.jockey_code`
- `race_entries.trainer_code` → `m_trainers.trainer_code`
- `race_results.venue_code...race_no` → `races`
- `race_results.jockey_code` → `m_jockeys.jockey_code`
- `race_results.trainer_code` → `m_trainers.trainer_code`
- `training_analysis.venue_code...horse_no` → `race_entries`
