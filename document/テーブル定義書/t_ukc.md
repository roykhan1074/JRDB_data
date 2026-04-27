# テーブル定義書: t_ukc

## テーブル概要

| 項目 | 内容 |
|------|------|
| テーブル名 | `t_ukc` |
| 論理名 | UKC馬マスタ（JRDB生テーブル） |
| エンジン | InnoDB |
| 文字セット | utf8mb4 |
| ソースファイル | `UKC` + YYMMDD + `.txt` |
| 説明 | JRDBのUKCファイルを固定長からCSV変換しそのまま格納したRAWテーブル。競走馬の血統・所有者情報を保持。正規化テーブルは `m_horses`。 |

## 主キー

`blood_reg_num`

---

## カラム定義

| # | カラム名 | 論理名 | データ型 | NOT NULL | PK | 備考 |
|---|---------|--------|---------|----------|-----|------|
| 1 | `blood_reg_num` | 血統登録番号 | char(8) | ✓ | ✓ | JRA血統登録番号 |
| 2 | `uma_name` | 馬名 | varchar(36) | | | 全角18文字 |
| 3 | `seibetsu_code` | 性別コード | char(1) | | | 1:牡 2:牝 3:騸 |
| 4 | `moke_code` | 毛色コード | char(2) | | | |
| 5 | `uma_kigo_code` | 馬記号コード | char(2) | | | |
| 6 | `chichi_uma_name` | 父馬名 | varchar(36) | | | |
| 7 | `haha_uma_name` | 母馬名 | varchar(36) | | | |
| 8 | `hahachichi_name` | 母父馬名 | varchar(36) | | | |
| 9 | `birthdate` | 生年月日 | char(8) | | | YYYYMMDD |
| 10 | `chichi_birth_year` | 父生年 | char(4) | | | YYYY |
| 11 | `haha_birth_year` | 母生年 | char(4) | | | YYYY |
| 12 | `hahachichi_birth_year` | 母父生年 | char(4) | | | YYYY |
| 13 | `umanushi_name` | 馬主名 | varchar(40) | | | |
| 14 | `umanushi_code` | 馬主コード | char(2) | | | |
| 15 | `seisansha_name` | 生産者名 | varchar(40) | | | |
| 16 | `sanchi_name` | 産地名 | char(8) | | | |
| 17 | `massho_flag` | 登録抹消フラグ | char(1) | | | 0:現役 1:抹消 |
| 18 | `data_ymd` | データ年月日 | char(8) | | | YYYYMMDD |
| 19 | `chichi_keitou_code` | 父系統コード | char(4) | | | |
| 20 | `hahachichi_keitou_code` | 母父系統コード | char(4) | | | |
| 21 | `load_file` | ロードファイル | varchar(20) | | | 取込元ファイル名 |
| 22 | `last_update` | 最終更新 | varchar(20) | | | |

---

## インデックス

| インデックス名 | カラム | 種類 |
|--------------|--------|------|
| PRIMARY | `blood_reg_num` | PRIMARY KEY |
