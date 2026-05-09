# RACE INSIGHT - JRDB データ分析サイト

## サイトの起動方法

プロジェクトディレクトリ (`c:\Git\JRDB_data`) で以下のコマンドを実行してください。

```powershell
npm run dev
```

起動後、ブラウザで以下のURLにアクセス：

```
http://localhost:3000
```

> **注意:** 起動前に `.env` ファイルにDB接続情報が設定されていることを確認してください。

### その他の起動オプション

| コマンド | 内容 |
|---|---|
| `npm run dev` | 開発用サーバー起動（サイト表示用） |
| `npm start` | データダウンロード用スクリプト起動 |
| `npm run download:today` | 今日分のデータをダウンロード |

---

## データ取込の手順

管理画面 (`http://localhost:3000/download.html`) から対象期間とファイル種別を選択して実行します。

### ファイル種別

| プレフィックス | 内容 | 備考 |
|---|---|---|
| BAC | レース基本情報 | レース当日朝5時頃に配信 |
| KYI | 出馬表 | レース当日朝5時頃に配信 |
| CYB | 調教分析 | レース当日朝5時頃に配信 |
| SED | 成績データ | レース終了後に配信 |
| UKC | 馬マスタ | 随時更新 |
| SRB | 成績速報 | レース終了後に配信 |

### 注意事項

- SED・SRB はレース終了後でないとJRDB側にデータがない（404スキップになるのは正常）
- G1などの特別レースデータは前日に先行配信されることがある
- 前日に取り込んだデータが不完全な場合は、対象日のzip/txt/CSVを削除してから再実行する

### 古いデータの再取込手順

1. 対象日のファイルを削除

```powershell
# ZIPファイル
rm data/zipdata/BAC{YYMMDD}.zip  # 例: BAC260503.zip
# TXTファイル
rm data/text/BAC/BAC{YYMMDD}.txt
# ...（KYI, CYB, SED, UKC, SRB も同様）
```

2. DBから対象日のレコードを削除

```sql
DELETE FROM T_BAC WHERE ymd = 'YYYYMMDD';
DELETE FROM T_KYI WHERE load_date = 'YYYYMMDD';
DELETE FROM T_CYB WHERE load_date = 'YYYYMMDD';
```

3. 管理画面から再取込を実行

---

## .env 設定例

```env
JRDB_BASE_URL=http://www.jrdb.com/member/datazip
JRDB_USER=（JRDBユーザーID）
JRDB_PASS=（JRDBパスワード）
DATA_DIR=./data
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASS=（MySQLパスワード）
DB_NAME=racing
```
