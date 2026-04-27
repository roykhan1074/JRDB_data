import { downloadJRDB, DownloadResult } from './downloader';
import { convertBAC } from './converters/BACConverter';
import { convertKYI } from './converters/KYIConverter';
import { convertCYB } from './converters/CYBConverter';
import { convertSED } from './converters/SEDConverter';
import { convertUKC } from './converters/UKCConverter';
import { convertSRB } from './converters/SRBConverter';
import { loadCSVFile } from './db/loadCSV';

export type PrefixName = 'BAC' | 'KYI' | 'CYB' | 'SED' | 'UKC' | 'SRB';

// prefix → JRDBグループ名のマッピング
const PREFIX_TO_GROUP: Record<PrefixName, string> = {
  BAC: 'race_before',
  KYI: 'race_before',
  CYB: 'race_before',
  SED: 'race_result',
  UKC: 'horse_master',
  SRB: 'race_result',
};

const CONVERTERS: Record<PrefixName, (ymd: string) => void> = {
  BAC: convertBAC,
  KYI: convertKYI,
  CYB: convertCYB,
  SED: convertSED,
  UKC: convertUKC,
  SRB: convertSRB,
};

export type LogFn = (message: string) => void;

export async function runPipeline(
  date: string,     // YYYYMMDD
  prefixes: PrefixName[],
  log: LogFn,
  signal?: AbortSignal,
): Promise<void> {
  const ymd6 = date.slice(2); // YYMMDD

  // 必要なグループのみダウンロード（重複排除）
  const groups = [...new Set(prefixes.map(p => PREFIX_TO_GROUP[p]))];
  log(`[ダウンロード開始] 日付: ${date}, グループ: ${groups.join(', ')}`);

  await downloadJRDB({
    from: date,
    to:   date,
    groups,
    signal,
    onProgress: (result: DownloadResult) => {
      const suffix = result.message ? ` (${result.message})` : '';
      log(`  [${result.status.toUpperCase()}] ${result.dir} ${result.date}${suffix}`);
    },
  });

  // 変換 & ロード（コンバーターは8桁YYYYMMDD、ローダーは6桁YYMMDDで渡す）
  for (const prefix of prefixes) {
    signal?.throwIfAborted();

    try {
      log(`[変換] ${prefix}${ymd6}.txt → CSV`);
      CONVERTERS[prefix](date); // FixedLengthConverter内部でslice(2)するため8桁を渡す
    } catch (e: any) {
      log(`[変換スキップ] ${prefix}${ymd6}: ${e.message}`);
      continue;
    }

    try {
      log(`[ロード] ${prefix}${ymd6}.csv → T_${prefix}`);
      await loadCSVFile(prefix, ymd6); // loadCSVFileは6桁で受け取る
      log(`[完了] ${prefix}${ymd6}`);
    } catch (e: any) {
      log(`[ロードエラー] ${prefix}${ymd6}: ${e.message}`);
    }
  }

  log('[パイプライン完了]');
}
