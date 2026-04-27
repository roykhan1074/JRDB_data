# テーブル定義書: m_horses

## テーブル概要

| 項目 | 内容 |
|------|------|
| テーブル名 | `m_horses` |
| 論理名 | 馬マスタ |
| エンジン | InnoDB |
| 文字セット | utf8mb4_unicode_ci |
| 説明 | 競走馬の基本情報マスタ。UKC（馬マスタ）ファイルから変換・格納。 |

## 主キー

`pedigree_no`

---

## カラム定義

| # | カラム名 | 論理名 | データ型 | NOT NULL | PK | 備考 |
|---|---------|--------|---------|----------|-----|------|
| 1 | `pedigree_no` | 血統登録番号 | char(8) | ✓ | ✓ | JRA血統登録番号 |
| 2 | `horse_name` | 馬名 | varchar(36) | ✓ | | 全角18文字 |
| 3 | `sex_code` | 性別コード | smallint | | | 1:牡 2:牝 3:騸 |
| 4 | `coat_color_code` | 毛色コード | char(2) | | | 01:栗毛 02:鹿毛 等 |
| 5 | `horse_symbol_code` | 馬記号コード | char(2) | | | 特殊記号 |
| 6 | `sire_name` | 父馬名 | varchar(36) | | | 全角18文字 |
| 7 | `dam_name` | 母馬名 | varchar(36) | | | 全角18文字 |
| 8 | `broodmare_sire_name` | 母父馬名 | varchar(36) | | | 全角18文字 |
| 9 | `birthdate` | 生年月日 | date | | | YYYY-MM-DD |
| 10 | `sire_birth_year` | 父生年 | smallint | | | YYYY |
| 11 | `dam_birth_year` | 母生年 | smallint | | | YYYY |
| 12 | `bms_birth_year` | 母父生年 | smallint | | | YYYY |
| 13 | `owner_name` | 馬主名 | varchar(40) | | | 全角20文字 |
| 14 | `owner_assoc_code` | 馬主協会コード | char(2) | | | |
| 15 | `breeder_name` | 生産者名 | varchar(40) | | | 全角20文字 |
| 16 | `production_area` | 産地名 | varchar(8) | | | 全角4文字 |
| 17 | `deregistration_flag` | 登録抹消フラグ | smallint | | | 0:現役 1:抹消 |
| 18 | `data_date` | データ年月日 | date | | | このレコードの基準日 |
| 19 | `sire_bloodline_code` | 父系統コード | char(4) | | | 血統系統 |
| 20 | `bms_bloodline_code` | 母父系統コード | char(4) | | | 血統系統 |

---

## インデックス

| インデックス名 | カラム | 種類 |
|--------------|--------|------|
| PRIMARY | `pedigree_no` | PRIMARY KEY |

---

## 関連テーブル

| テーブル | 関係 | 説明 |
|---------|------|------|
| `race_entries` | 1:N | この馬の出走記録 |
