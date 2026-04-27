/**
 * データ欠落期間の一括取込スクリプト
 * 実行: npx ts-node src/fill-gaps.ts
 */
import { generateDateRange } from './downloader';
import { runPipeline, PrefixName } from './pipeline';

// 欠落・不足が確認された月（完全 or 重大欠落優先）
const GAP_PERIODS: [string, string][] = [
  // 2020年
  ['20200601', '20200630'], // 2日しかない
  ['20200701', '20200731'], // 2日しかない
  ['20201001', '20201031'], // 1日しかない（秋開催）
  ['20201101', '20201130'], // 6日（要補完）
  // 2021年
  ['20210201', '20210228'], // 完全欠落
  ['20210601', '20210630'], // 1日・SED未ロードあり
  ['20210901', '20210930'], // 2日しかない
  ['20211001', '20211031'], // 4日しかない（秋開催）
  // 2022年
  ['20220101', '20220131'], // 完全欠落
  ['20220401', '20220430'], // SED 36件未ロード
  ['20220501', '20220531'], // 完全欠落
  ['20220801', '20220831'], // 4日・SED 36件未ロード
  ['20220901', '20220930'], // 1日しかない
  ['20221201', '20221231'], // 2日しかない
  // 2023年
  ['20230101', '20230131'], // 5日（要補完）
  ['20230401', '20230430'], // 完全欠落
  ['20230801', '20230831'], // 1日しかない
  ['20231101', '20231130'], // 2日しかない（JC月）
  ['20231201', '20231231'], // 3日しかない
  // 2024年
  ['20240301', '20240331'], // 完全欠落
  ['20240701', '20240731'], // 完全欠落
  ['20241001', '20241031'], // 2日しかない
  ['20241101', '20241130'], // 2日しかない（JC月）
];

const PREFIXES: PrefixName[] = ['BAC', 'KYI', 'CYB', 'SED'];

async function main() {
  // 全処理対象日付を展開
  const allDates: string[] = [];
  for (const [from, to] of GAP_PERIODS) {
    allDates.push(...generateDateRange(from, to));
  }

  // 重複除去・ソート
  const dates = [...new Set(allDates)].sort();

  console.log(`=== データ欠落補完スクリプト ===`);
  console.log(`対象期間: ${GAP_PERIODS.length}期間  総カレンダー日数: ${dates.length}日`);
  console.log(`（非開催日は404スキップされます）\n`);

  let ok = 0, skip = 0, err = 0;

  for (let i = 0; i < dates.length; i++) {
    const date = dates[i];
    const progress = `[${i + 1}/${dates.length}]`;
    try {
      await runPipeline(date, PREFIXES, (msg) => {
        // OK/エラー系のみ表示（スキップは省略）
        if (!msg.includes('skip') && !msg.includes('not found')) {
          console.log(`${progress} ${msg}`);
        }
      });
      ok++;
    } catch (e: any) {
      if (e?.name === 'AbortError' || e?.code === 'ERR_CANCELED') {
        console.log('中断されました');
        break;
      }
      console.error(`${progress} [ERROR] ${date}: ${e.message}`);
      err++;
    }
  }

  console.log(`\n=== 完了 ===`);
  console.log(`処理: ${ok}日  スキップ: ${skip}日  エラー: ${err}日`);
}

main().catch((e) => {
  console.error('致命的エラー:', e);
  process.exit(1);
});
