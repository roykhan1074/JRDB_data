/**
 * JRDB ダウンローダー CLI
 *
 * 使用例:
 *   # 今日のデータをダウンロード
 *   ts-node src/index.ts --date today
 *
 *   # 指定日のデータをダウンロード
 *   ts-node src/index.ts --date 20260411
 *
 *   # 2020/01/01から今日まで全データをダウンロード
 *   ts-node src/index.ts --from 20200101
 *
 *   # 指定期間のデータをダウンロード
 *   ts-node src/index.ts --from 20240101 --to 20241231
 *
 *   # 特定グループのみダウンロード（カンマ区切り）
 *   ts-node src/index.ts --date 20260411 --groups race_before,race_result
 *
 *   # 利用可能なグループ一覧を表示
 *   ts-node src/index.ts --list-groups
 */

import minimist from 'minimist';
import { downloadJRDB, formatDate } from './downloader';
import { FILE_GROUPS, DEFAULT_GROUPS } from './config';

const args = minimist(process.argv.slice(2), {
  string: ['date', 'from', 'to', 'groups'],
  boolean: ['list-groups', 'help'],
  alias: { h: 'help' },
});

function printHelp(): void {
  console.log(`
JRDB ダウンローダー

オプション:
  --date <yyyymmdd|today>   指定日のデータをダウンロード
  --from <yyyymmdd>         開始日（--to を省略すると今日まで）
  --to   <yyyymmdd>         終了日（--from と併用）
  --groups <group,...>      ダウンロード対象グループ（カンマ区切り）
  --list-groups             利用可能なグループ一覧を表示
  --help, -h                このヘルプを表示

グループ:
${Object.entries(FILE_GROUPS)
  .map(([key, def]) => `  ${key.padEnd(20)} ${def.label}`)
  .join('\n')}

例:
  ts-node src/index.ts --date today
  ts-node src/index.ts --date 20260411
  ts-node src/index.ts --from 20200101
  ts-node src/index.ts --from 20240101 --to 20241231
  ts-node src/index.ts --date 20260411 --groups race_before,race_result
`);
}

function todayYmd(): string {
  return formatDate(new Date());
}

async function main(): Promise<void> {
  if (args.help) {
    printHelp();
    return;
  }

  if (args['list-groups']) {
    console.log('利用可能なグループ:');
    for (const [key, def] of Object.entries(FILE_GROUPS)) {
      console.log(`  ${key.padEnd(20)} ${def.label}  [${def.dirs.join(', ')}]`);
    }
    return;
  }

  const groups: string[] = args.groups
    ? args.groups.split(',').map((g: string) => g.trim())
    : DEFAULT_GROUPS;

  // --date モード（単日 or today）
  if (args.date) {
    const ymd = args.date === 'today' ? todayYmd() : String(args.date);
    if (!/^\d{8}$/.test(ymd)) {
      console.error('--date は yyyymmdd 形式または "today" を指定してください');
      process.exit(1);
    }
    await downloadJRDB({ from: ymd, groups });
    return;
  }

  // --from / --to モード（期間）
  if (args.from) {
    const from = String(args.from);
    const to   = args.to ? String(args.to) : todayYmd();
    if (!/^\d{8}$/.test(from) || !/^\d{8}$/.test(to)) {
      console.error('--from / --to は yyyymmdd 形式で指定してください');
      process.exit(1);
    }
    await downloadJRDB({ from, to, groups });
    return;
  }

  // 引数なし
  printHelp();
}

main().catch((err) => {
  console.error('エラー:', err instanceof Error ? err.message : err);
  process.exit(1);
});
