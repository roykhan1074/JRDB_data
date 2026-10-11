---
name: ui-verify
description: 表（table）のレイアウトを Puppeteer で実機検証する。entries.html・watchlist.html・factor-recovery.html 等のテーブルで列の追加/削除/幅変更/非表示、見出しの変更、セル内容（バッジ・色・文字）の変更をしたら、完了報告の前に必ず使う。列数（col/th/td）の一致、見出しの折り返し行数、col指定幅とのずれ、狭い画面での縮小、横スクロール、複数テーブル間の列位置ずれを数値で確認する。
---

# 表レイアウトの実機検証

CLAUDE.md「UI変更時の必須チェック」の手順をスクリプト化したもの。**目視や仕様の記憶で「直った」と判断せず、これを実行してから報告する。**

## 手順

1. サーバーが動いているか確認（`netstat -ano | Select-String ":3000 .*LISTENING"`）。止まっていたら起動する（ユーザーに頼まない）。
2. puppeteer-core を一時インストール（システムの Chrome を使う）:
   ```
   npm install --no-save puppeteer-core
   ```
3. 検証対象の URL を決める。**結果の出ているレースと、長い文字列（外国人騎手名など）を含むデータを選ぶ。** 直近の開催日とレースキーは次で取れる:
   ```
   $env:MYSQL_PWD='dn531016'; mysql -u root racing -e "SELECT MAX(ymd) FROM T_SED; SELECT CONCAT(course_code,year_code,kai,day_code,race_num) k FROM T_BAC WHERE ymd=(SELECT MAX(ymd) FROM T_SED) LIMIT 5"
   ```
   障害戦だけの列（列#10）を触ったら、障害戦（`T_BAC.tds_code='3'`）と平地の両方を `--url` で渡す。
4. 実行（`--url` は複数指定可）:
   ```
   node .claude/skills/ui-verify/verify.js --url "http://localhost:3000/entries.html?key=05264308" --wait "#tbody tr"
   node .claude/skills/ui-verify/verify.js --url "http://localhost:3000/watchlist.html?ymd=20261010" --table "table.wl-table" --wait "table.wl-table tbody tr"
   ```
   オプション: `--widths 1600,700,500`（既定）/ `--table <セレクタ>`（既定 `table`）/ `--wrap <横スクロール要素>`（既定 `.table-wrap`）/ `--shot .scratch/ui-verify`（全画面スクリーンショット保存）
5. 色・バッジなど見た目の変更なら `--shot` を付け、Read で画像を見て確認する。
6. 後片付け: `npm uninstall --no-save puppeteer-core`、`.scratch/ui-verify` を削除。

## 出力の読み方

- **✗ 問題**（終了コード1）: 直してから報告する。
  - 列数不一致（col 数 ≠ 見出しの実効列数（colspan 展開後）≠ td 数）
  - 見出しの折り返し違反（4文字以内が2行以上 / 5文字以上が3行以上）
  - 幅未指定（px 以外）の col
  - 狭い画面で見出し幅が変わった（比例縮小されている）
  - 表示幅が col 合計より狭いのに横スクロールしない
  - 同じページの複数テーブルで列位置がずれている（watchlist のようにレース毎に表を作るページ）
- **△ 警告**: 報告に書く。中身（バッジ+padding、nowrap の長い名前）が col 指定幅より広く、列が広がっている。テーブルが1つなら表示は崩れないが、CLAUDE.md の列マップの幅と実際の幅が違うことになる。複数テーブルのページでは列ずれにつながるので、col 幅を広げるか table の width を col 合計の px に固定する。
  - 2026-10-11 時点の出馬表の既知の警告: 枠 28→34px、騎手 76→94px（長い騎手名のレース）、情報/展開/IDM 印 20→24〜25px。`width:max-content` のため中身に合わせて広がっている。
- 非表示列（`width:0;font-size:0` 方式）は見出しチェックの対象外。

## 報告

「Puppeteerで実機検証済み（URL・画面幅・問題0件／警告の内容）」と書く。検証できなかった項目だけユーザーに確認を頼む。
