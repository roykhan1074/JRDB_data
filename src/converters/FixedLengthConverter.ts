import fs from 'fs';
import path from 'path';
import iconv from 'iconv-lite';
import { DATA_DIR } from '../config';

export interface FieldDef {
  name: string;
  start: number; // 0-indexed byte offset
  len: number;
}

function escapeCsv(value: string): string {
  if (value.includes(',') || value.includes('"') || value.includes('\n') || value.includes('\r')) {
    return '"' + value.replace(/"/g, '""') + '"';
  }
  return value;
}

function recordToCsvLine(buf: Buffer, fields: readonly FieldDef[], loadFile: string): string {
  const values = fields.map(f => {
    const slice = buf.subarray(f.start, f.start + f.len);
    return escapeCsv(iconv.decode(slice, 'Shift_JIS').trim());
  });
  values.push(escapeCsv(loadFile));
  values.push(''); // last_update
  return values.join(',');
}

export function convertFile(prefix: string, ymd: string, fields: readonly FieldDef[]): void {
  const ymd6     = ymd.slice(2);
  const fileName = `${prefix}${ymd6}`;
  const txtPath  = path.join(DATA_DIR, 'text', prefix, `${fileName}.txt`);
  const csvDir   = path.join(DATA_DIR, 'csv',  prefix);
  const csvPath  = path.join(csvDir,   `${fileName}.csv`);

  if (!fs.existsSync(txtPath)) {
    throw new Error(`ファイルが見つかりません: ${txtPath}`);
  }

  fs.mkdirSync(csvDir, { recursive: true });

  const fileBuffer = fs.readFileSync(txtPath);
  const headers    = [...fields.map(f => f.name), 'load_file', 'last_update'];
  const lines: string[] = [headers.join(',')];

  let offset = 0;
  while (offset < fileBuffer.length) {
    let end = fileBuffer.indexOf(0x0a, offset);
    if (end === -1) end = fileBuffer.length;
    const dataEnd = (end > offset && fileBuffer[end - 1] === 0x0d) ? end - 1 : end;
    if (dataEnd > offset) {
      lines.push(recordToCsvLine(fileBuffer.subarray(offset, dataEnd), fields, fileName));
    }
    offset = end + 1;
  }

  fs.writeFileSync(csvPath, lines.join('\n'), 'utf8');
  console.log(`[${prefix}] ${fileName}.csv 出力完了 (${lines.length - 1} レコード)`);
}

export function convertAll(prefix: string, fields: readonly FieldDef[]): void {
  const textDir = path.join(DATA_DIR, 'text', prefix);
  if (!fs.existsSync(textDir)) {
    throw new Error(`テキストフォルダが見つかりません: ${textDir}`);
  }
  const pattern = new RegExp(`^${prefix}\\d{6}\\.txt$`, 'i');
  const files   = fs.readdirSync(textDir).filter(f => pattern.test(f)).sort();
  console.log(`[${prefix}] ${files.length} ファイルを変換開始`);
  for (const file of files) {
    const ymd6 = file.slice(prefix.length, prefix.length + 6);
    try {
      convertFile(prefix, '20' + ymd6, fields);
    } catch (e) {
      console.error(`[${prefix}] ${file} エラー:`, e instanceof Error ? e.message : e);
    }
  }
}
