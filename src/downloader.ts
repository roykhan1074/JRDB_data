import axios, { AxiosError } from 'axios';
import fs from 'fs';
import path from 'path';
import AdmZip from 'adm-zip';
import https from 'https';
import {
  JRDB_BASE_URL,
  JRDB_USER,
  JRDB_PASS,
  DATA_DIR,
  FILE_GROUPS,
  DEFAULT_GROUPS,
} from './config';

const httpsAgent = new https.Agent({ rejectUnauthorized: false });

/** yyyymmdd 形式の文字列から Date オブジェクトを生成 */
export function parseDate(ymd: string): Date {
  const y = parseInt(ymd.slice(0, 4), 10);
  const m = parseInt(ymd.slice(4, 6), 10) - 1;
  const d = parseInt(ymd.slice(6, 8), 10);
  return new Date(y, m, d);
}

/** Date オブジェクトを yyyymmdd 形式に変換 */
export function formatDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}${m}${d}`;
}

/** from〜to の全日付を配列で返す（両端含む） */
export function generateDateRange(from: string, to: string): string[] {
  const dates: string[] = [];
  const cur = parseDate(from);
  const end = parseDate(to);
  while (cur <= end) {
    dates.push(formatDate(cur));
    cur.setDate(cur.getDate() + 1);
  }
  return dates;
}

export interface DownloadResult {
  date: string;
  dir: string;
  status: 'ok' | 'skip' | 'error';
  message?: string;
}

async function downloadFile(url: string, destPath: string, signal?: AbortSignal): Promise<void> {
  // JRDBはURLにID:PASSを埋め込む形式
  const authUrl = url.replace('://', `://${JRDB_USER}:${JRDB_PASS}@`);
  const res = await axios.get<ArrayBuffer>(authUrl, {
    responseType: 'arraybuffer',
    timeout: 60_000,
    httpsAgent,
    signal,
  });
  fs.writeFileSync(destPath, Buffer.from(res.data));
}

const ZIP_DIR  = path.join(DATA_DIR, 'zipdata');
const TEXT_DIR = path.join(DATA_DIR, 'text');

function extractTextFiles(zipPath: string): void {
  const zip = new AdmZip(zipPath);
  for (const entry of zip.getEntries()) {
    if (entry.isDirectory) continue;
    const baseName = path.basename(entry.entryName);
    // ファイル名先頭の英字部分のみをプレフィックスとして使用
    // 例: BAC260425.txt → BAC  (.txt の文字を含めないよう先頭マッチ)
    const prefix = (baseName.match(/^[A-Za-z]+/) ?? [''])[0].toUpperCase();
    if (!prefix) continue;
    const subDir = path.join(TEXT_DIR, prefix);
    fs.mkdirSync(subDir, { recursive: true });
    fs.writeFileSync(path.join(subDir, baseName), entry.getData());
  }
}

async function downloadOne(
  ymd: string,
  dir: string,
  signal?: AbortSignal,
): Promise<DownloadResult> {
  const year     = ymd.slice(0, 4);
  const ymd6     = ymd.slice(2);
  const upper    = dir.toUpperCase();
  const fileName = `${upper}${ymd6}.zip`;
  const url      = `${JRDB_BASE_URL}/${dir}/${year}/${fileName}`;
  const zipPath  = path.join(ZIP_DIR, fileName);

  const txtPath = path.join(TEXT_DIR, upper, `${upper}${ymd6}.txt`);

  if (fs.existsSync(zipPath) && fs.existsSync(txtPath)) {
    return { date: ymd, dir, status: 'skip', message: 'already exists' };
  }

  try {
    fs.mkdirSync(ZIP_DIR, { recursive: true });
    fs.mkdirSync(TEXT_DIR, { recursive: true });
    if (!fs.existsSync(zipPath)) {
      await downloadFile(url, zipPath, signal);
    }
    extractTextFiles(zipPath);
    return { date: ymd, dir, status: 'ok' };
  } catch (err) {
    if ((err as any)?.code === 'ERR_CANCELED' || (err as any)?.name === 'AbortError') {
      throw err; // キャンセルは上位に伝播
    }
    const status = (err as AxiosError).response?.status;
    if (status === 404) {
      return { date: ymd, dir, status: 'skip', message: 'not found (404)' };
    }
    const msg = err instanceof Error ? err.message : String(err);
    return { date: ymd, dir, status: 'error', message: msg };
  }
}

export interface DownloadOptions {
  /** yyyymmdd 形式の開始日 */
  from: string;
  /** yyyymmdd 形式の終了日（省略時は from と同日） */
  to?: string;
  /** ダウンロード対象グループ（省略時は全グループ） */
  groups?: string[];
  /** 処理状況を出力するコールバック */
  onProgress?: (result: DownloadResult) => void;
  /** キャンセルシグナル */
  signal?: AbortSignal;
}

/** メインのダウンロード処理 */
export async function downloadJRDB(options: DownloadOptions): Promise<void> {
  const { from, to = from, groups = DEFAULT_GROUPS, onProgress, signal } = options;

  const dates = generateDateRange(from, to);
  const dirs  = groups.flatMap((g) => FILE_GROUPS[g]?.dirs ?? []);

  if (dirs.length === 0) {
    throw new Error(`有効なグループが見つかりません: ${groups.join(', ')}`);
  }

  console.log(`対象日数: ${dates.length}日  ファイル種別: ${dirs.join(', ')}`);
  console.log(`zip格納先: ${ZIP_DIR}`);
  console.log(`text格納先: ${TEXT_DIR}\n`);

  let okCount    = 0;
  let skipCount  = 0;
  let errorCount = 0;

  for (const ymd of dates) {
    for (const dir of dirs) {
      signal?.throwIfAborted();
      const result = await downloadOne(ymd, dir, signal);
      onProgress?.(result);

      if (result.status === 'ok') {
        okCount++;
        console.log(`  [OK]   ${ymd} ${dir}`);
      } else if (result.status === 'skip') {
        skipCount++;
        // 404スキップは頻繁なので詳細ログは省略
      } else {
        errorCount++;
        console.error(`  [ERR]  ${ymd} ${dir}: ${result.message}`);
      }
    }
  }

  console.log(`\n完了 — OK: ${okCount}  スキップ: ${skipCount}  エラー: ${errorCount}`);
}
