import fs from 'fs';
import path from 'path';
import readline from 'readline';
import { createConnection } from './dbConnection';
import dotenv from 'dotenv';

dotenv.config();

const DATA_DIR = process.env.DATA_DIR ?? './data';
const CSV_DIR  = path.resolve(DATA_DIR, 'csv');

type TableConfig = {
  prefix:  string;
  table:   string;
  schemaFile: string;
};

const TABLE_CONFIG: Record<string, TableConfig> = {
  BAC: { prefix: 'BAC', table: 'T_BAC', schemaFile: 'T_BAC.sql' },
  KYI: { prefix: 'KYI', table: 'T_KYI', schemaFile: 'T_KYI.sql' },
  CYB: { prefix: 'CYB', table: 'T_CYB', schemaFile: 'T_CYB.sql' },
  SED: { prefix: 'SED', table: 'T_SED', schemaFile: 'T_SED.sql' },
  UKC: { prefix: 'UKC', table: 'T_UKC', schemaFile: 'T_UKC.sql' },
  SRB: { prefix: 'SRB', table: 'T_SRB', schemaFile: 'T_SRB.sql' },
};

async function createTableIfNotExists(conn: Awaited<ReturnType<typeof createConnection>>, schemaFile: string) {
  const sqlPath = path.join(__dirname, 'schema', schemaFile);
  if (!fs.existsSync(sqlPath)) {
    throw new Error(`スキーマファイルが見つかりません: ${sqlPath}`);
  }
  const sql = fs.readFileSync(sqlPath, 'utf-8');
  await conn.execute(sql);
}

function parseLine(line: string): string[] {
  const result: string[] = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      inQuotes = !inQuotes;
    } else if (ch === ',' && !inQuotes) {
      result.push(current);
      current = '';
    } else {
      current += ch;
    }
  }
  result.push(current);
  return result;
}

async function loadCSVFile(prefix: string, ymd6: string) {
  const config = TABLE_CONFIG[prefix.toUpperCase()];
  if (!config) throw new Error(`未対応のプレフィックス: ${prefix}`);

  const csvPath = path.join(CSV_DIR, prefix, `${prefix}${ymd6}.csv`);
  if (!fs.existsSync(csvPath)) {
    throw new Error(`CSVファイルが見つかりません: ${csvPath}`);
  }

  const conn = await createConnection();
  try {
    await createTableIfNotExists(conn, config.schemaFile);

    const rl = readline.createInterface({
      input: fs.createReadStream(csvPath, { encoding: 'utf-8' }),
      crlfDelay: Infinity,
    });

    let headers: string[] = [];
    let rowCount = 0;
    const rows: string[][] = [];

    for await (const line of rl) {
      if (!line.trim()) continue;
      if (headers.length === 0) {
        headers = parseLine(line);
        continue;
      }
      rows.push(parseLine(line));
    }

    if (rows.length === 0) {
      console.log(`[${prefix}] ${ymd6}: 0行（スキップ）`);
      return;
    }

    const placeholders = headers.map(() => '?').join(',');
    const colList = headers.map(h => `\`${h}\``).join(',');
    const sql = `INSERT INTO ${config.table} (${colList}) VALUES (${placeholders})
      ON DUPLICATE KEY UPDATE ${headers.map(h => `\`${h}\`=VALUES(\`${h}\`)`).join(',')}`;

    for (const row of rows) {
      const values = headers.map((_, i) => {
        const v = row[i] ?? '';
        return v === '' ? null : v;
      });
      await conn.execute(sql, values);
      rowCount++;
    }

    console.log(`[${prefix}] ${config.table} へ ${rowCount} 行ロード完了（${ymd6}）`);
  } finally {
    await conn.end();
  }
}

async function loadCSVAll(prefix: string) {
  const config = TABLE_CONFIG[prefix.toUpperCase()];
  if (!config) throw new Error(`未対応のプレフィックス: ${prefix}`);

  const dir = path.join(CSV_DIR, prefix);
  if (!fs.existsSync(dir)) throw new Error(`フォルダが見つかりません: ${dir}`);

  const files = fs.readdirSync(dir)
    .filter(f => f.match(new RegExp(`^${prefix}\\d{6}\\.csv$`, 'i')))
    .sort();

  console.log(`[${prefix}] ${files.length} ファイルを処理します`);
  for (const file of files) {
    const ymd6 = file.replace(/^[A-Z]+/i, '').replace('.csv', '');
    await loadCSVFile(prefix, ymd6);
  }
}

export { loadCSVFile, loadCSVAll };

// CLIとして直接実行された場合のみ動作
if (require.main === module) {
  const args = process.argv.slice(2);
  const prefixArg = args[0]?.toUpperCase();
  const ymdArg    = args[1];

  if (!prefixArg) {
    console.error('使用法: ts-node src/db/loadCSV.ts <PREFIX> [YYYMMDD|all]');
    console.error('例: ts-node src/db/loadCSV.ts BAC 200105');
    console.error('例: ts-node src/db/loadCSV.ts BAC all');
    process.exit(1);
  }

  const run = async () => {
    if (!ymdArg || ymdArg === 'all') {
      await loadCSVAll(prefixArg);
    } else {
      const ymd6 = ymdArg.length === 8 ? ymdArg.slice(2) : ymdArg;
      await loadCSVFile(prefixArg, ymd6);
    }
  };

  run().catch(err => { console.error(err); process.exit(1); });
}
