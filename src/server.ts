import express from 'express';
import path from 'path';
import { spawn } from 'child_process';
import * as fs from 'fs';
import { runPipeline, PrefixName } from './pipeline';
import { pool } from './db/dbConnection';

// プロセス全体のセーフティネット。
// ETL系エンドポイント（SSEで進捗をres.writeし続ける実装）は、クライアントが途中で
// 切断した後にres.writeを呼ぶと書き込みエラーが発生しうる。個別にtry/catchしていない
// 箇所でこれが未捕捉例外・未処理rejectionになるとNode.jsプロセス自体が終了してしまい、
// 実行中の子プロセス（mysql CLI）も巻き添えで終了し、ETLがTRUNCATE直後の空テーブル状態
// のまま放置される（実際に発生した事故）。開発サーバーが丸ごと落ちることだけは避けるため、
// 最後の砦としてログ出力のみ行い、プロセスは継続させる。
process.on('uncaughtException', (err) => {
  console.error('[uncaughtException] サーバーは継続します:', err);
});
process.on('unhandledRejection', (err) => {
  console.error('[unhandledRejection] サーバーは継続します:', err);
});

const ANABA_SQL_FILE    = path.join(__dirname, '..', 'sql', 'anaba_index.sql');
const TENKAI_SQL_FILE   = path.join(__dirname, '..', 'sql', 'tenkai_index.sql');
const PACEFIT_SQL_FILE  = path.join(__dirname, '..', 'sql', 'pacefit_index.sql');
const HONMEI_SQL_FILE   = path.join(__dirname, '..', 'sql', 'honmei_index.sql');
const COURSE_RECOVERY_SQL_FILE = path.join(__dirname, '..', 'sql', 'course_recovery_index.sql');
const FURI_SQL_FILE    = path.join(__dirname, '..', 'sql', 'furi_index.sql');
const KYUSHA_SQL_FILE   = path.join(__dirname, '..', 'sql', 'kyusha_analysis.sql');

const PART_LABELS: Record<number, string> = {
  1: 'テーブル定義 (CREATE TABLE)',
  2: 'ファクトデータ投入 (T_ANABA_RACE_LOG)',
  3: 'ファクター集計 (T_ANABA_FACTOR_AGG)',
  4: '指数計算 (T_ANABA_SCORE)',
};

const HONMEI_PART_LABELS: Record<number, string> = {
  1: 'テーブル定義 (CREATE TABLE)',
  2: 'ファクトデータ投入 (T_HONMEI_RACE_LOG)',
  3: 'ファクター集計 (T_HONMEI_FACTOR_AGG)',
  4: '指数計算 (T_HONMEI_SCORE)',
};

const TENKAI_PART_LABELS: Record<number, string> = {
  1: 'テーブル定義 (CREATE TABLE)',
  2: 'ファクトデータ投入 (T_TENKAI_RACE_LOG)',
  3: 'ファクター集計 (T_TENKAI_FACTOR_AGG)',
  4: '指数計算 (T_TENKAI_SCORE)',
};

const PACEFIT_PART_LABELS: Record<number, string> = {
  1: 'テーブル定義 (CREATE TABLE)',
  2: '全体ファクター集計 (T_PACEFIT_FACTOR_AGG)',
  3: 'コース別ファクター集計 (T_PACEFIT_FACTOR_AGG)',
  4: '指数計算 (T_PACEFIT_SCORE)',
};

const COURSE_RECOVERY_PART_LABELS: Record<number, string> = {
  1: 'テーブル定義 (CREATE TABLE)',
  2: '全体ファクター集計 (T_COURSE_RECOVERY_FACTOR_AGG)',
  3: '指数計算 (T_COURSE_RECOVERY_SCORE)',
};

const FURI_PART_LABELS: Record<number, string> = {
  1: 'テーブル定義 (CREATE TABLE)',
  2: 'ファクター集計 (T_FURI_FACTOR_AGG)',
  3: '指数計算 (T_FURI_SCORE)',
};

const KYUSHA_PART_LABELS: Record<number, string> = {
  1: 'テーブル定義 (CREATE TABLE)',
  2: 'ファクトデータ投入 (T_KYUSHA_RACE_LOG)',
  3: 'ファクター集計 (T_KYUSHA_FACTOR_AGG)',
};

/** SQLファイルを -- Part N: マーカーで4パートに分割 */
function splitSqlByParts(content: string): string[] {
  const parts: string[] = [];
  const markers = ['-- Part 2:', '-- Part 3:', '-- Part 4:'];
  let remaining = content;
  for (const marker of markers) {
    const markerIdx = remaining.indexOf(marker);
    if (markerIdx === -1) { parts.push(remaining); remaining = ''; break; }
    const beforeMarker = remaining.slice(0, markerIdx);
    const splitPoint = Math.max(0, beforeMarker.lastIndexOf('\n-- ====='));
    parts.push(remaining.slice(0, splitPoint));
    remaining = remaining.slice(splitPoint);
  }
  if (remaining.trim()) parts.push(remaining);
  return parts.filter(p => p.trim().length > 0);
}

/** mysql CLI にSQLを渡して実行。エラー時は reject。 */
function runMysqlSql(sql: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const args = [
      '-h', process.env.DB_HOST ?? 'localhost',
      '-P', String(process.env.DB_PORT ?? '3306'),
      '-u', process.env.DB_USER ?? 'root',
      `-p${process.env.DB_PASS ?? ''}`,
      '--batch',
      '--default-character-set=utf8mb4',
      process.env.DB_NAME ?? 'racing',
    ];
    const proc = spawn('mysql', args, { stdio: ['pipe', 'pipe', 'pipe'] });
    let stderr = '';
    let settled = false;
    // stdoutを読み捨てないと、SELECT結果が多いSQL（診断クエリ等）でOSパイプバッファが
    // 満杯になりmysqlプロセスがwriteでブロックし続け、closeイベントが永久に発火しない
    // （＝ETLがハングしたまま完了報告もエラー報告もされない）事故につながる。
    proc.stdout.on('data', () => { /* 破棄。ログはmysql CLI標準出力を見ない運用のため不要 */ });
    proc.stderr.on('data', (d: Buffer) => {
      const s = d.toString();
      if (!s.includes('[Warning] Using a password')) stderr += s;
    });
    proc.on('error', (err: Error) => {
      if (settled) return;
      settled = true;
      reject(new Error(`mysql起動失敗: ${err.message}`));
    });
    proc.on('close', (code: number | null) => {
      if (settled) return;
      settled = true;
      if (code === 0) resolve();
      else reject(new Error(stderr.trim() || `mysql exit code ${code}`));
    });
    proc.stdin.on('error', () => { /* proc.on('error')側でreject済み */ });
    proc.stdin.write(sql, 'utf8');
    proc.stdin.end();
  });
}

/** ETL多重実行防止用ロック。同じ指数のETLが実行中は次のリクエストを即エラーにする。 */
const etlLocks: Record<string, boolean> = { anaba: false, honmei: false, tenkai: false, pacefit: false, analyzeFact: false, courseRecovery: false, furi: false, kyusha: false, evIndex: false };

const app = express();
const PORT = process.env.PORT ?? 3000;

app.use(express.json());
app.use(express.static(path.join(__dirname, '..', 'public')));

function buildDateRange(from: string, to: string): string[] {
  const dates: string[] = [];
  const start = new Date(`${from.slice(0,4)}-${from.slice(4,6)}-${from.slice(6,8)}`);
  const end   = new Date(`${to.slice(0,4)}-${to.slice(4,6)}-${to.slice(6,8)}`);
  for (const d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    dates.push(d.toISOString().slice(0, 10).replace(/-/g, ''));
  }
  return dates;
}

// SSEでパイプライン進捗をストリーミング
app.post('/api/run', (req, res) => {
  const { dateFrom, dateTo, prefixes } = req.body as {
    dateFrom: string; dateTo: string; prefixes: PrefixName[];
  };

  if (!dateFrom || !/^\d{8}$/.test(dateFrom) || !dateTo || !/^\d{8}$/.test(dateTo)) {
    res.status(400).json({ error: '日付はYYYYMMDD形式で指定してください' });
    return;
  }
  if (dateFrom > dateTo) {
    res.status(400).json({ error: '開始日付は終了日付以前にしてください' });
    return;
  }
  if (!Array.isArray(prefixes) || prefixes.length === 0) {
    res.status(400).json({ error: 'ファイル種別を1つ以上選択してください' });
    return;
  }

  const dates = buildDateRange(dateFrom, dateTo);

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const ac = new AbortController();
  // req.on('close') はリクエストボディ読み込み完了時にも発火するため使わない。
  // res.on('close') はクライアントが切断したとき（または res.end() 後）に発火する。
  res.on('close', () => ac.abort());

  const send = (msg: string) => {
    res.write(`data: ${JSON.stringify({ message: msg })}\n\n`);
  };

  (async () => {
    for (let i = 0; i < dates.length; i++) {
      ac.signal.throwIfAborted();
      const date = dates[i];
      res.write(`data: ${JSON.stringify({ progress: { current: i + 1, total: dates.length, date } })}\n\n`);
      await runPipeline(date, prefixes, send, ac.signal);
    }
    res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
    res.end();
  })().catch((err) => {
    if (ac.signal.aborted) {
      res.write(`data: ${JSON.stringify({ cancelled: true, done: true })}\n\n`);
    } else {
      res.write(`data: ${JSON.stringify({ error: err.message, done: true })}\n\n`);
    }
    res.end();
  });
});

// /api/stats のキャッシュ（DB クエリは重いため 30 秒間メモリに保持）
let statsCache: { data: unknown; expiresAt: number } | null = null;

// テーブルごとの統計情報
const TABLE_META = [
  { table: 'T_BAC', label: 'レース基本情報', prefix: 'BAC', dateCol: 'ymd' },
  { table: 'T_KYI', label: '出馬表',         prefix: 'KYI', dateCol: 'load_date' },
  { table: 'T_CYB', label: '調教分析',        prefix: 'CYB', dateCol: 'load_date' },
  { table: 'T_SED', label: '成績データ',       prefix: 'SED', dateCol: 'ymd' },
  { table: 'T_UKC', label: '馬マスタ',         prefix: 'UKC', dateCol: 'data_ymd' },
  { table: 'T_SRB', label: '成績速報',         prefix: 'SRB', dateCol: 'load_date' },
  { table: 'T_HJC', label: '払戻データ',       prefix: 'HJC', dateCol: 'load_date' },
];

app.get('/api/stats', async (_req, res) => {
  if (statsCache && statsCache.expiresAt > Date.now()) {
    res.json(statsCache.data);
    return;
  }

  const tableNames = TABLE_META.map(m => m.table);

  // information_schema から行数を一括取得（COUNT(*) の全件スキャンを回避）
  const [isRows] = await pool.query<any>(
    `SELECT table_name, table_rows
     FROM information_schema.tables
     WHERE table_schema = DATABASE()
       AND table_name IN (${tableNames.map(() => '?').join(',')})`,
    tableNames
  );
  const rowCountMap: Record<string, number> = {};
  for (const r of isRows) rowCountMap[r.table_name] = Number(r.table_rows);

  // 日付範囲・日数は各テーブルに並列クエリ（インデックスで高速化済み）
  const results = await Promise.all(TABLE_META.map(async (meta) => {
    try {
      const dateExpr = `\`${meta.dateCol}\``;
      const [[dateRow]] = await pool.query<any>(
        `SELECT MIN(${dateExpr}) AS min_date,
                MAX(${dateExpr}) AS max_date,
                COUNT(DISTINCT ${dateExpr}) AS days
         FROM \`${meta.table}\``
      );
      return {
        table:   meta.table,
        label:   meta.label,
        prefix:  meta.prefix,
        total:   rowCountMap[meta.table] ?? 0,
        minDate: dateRow.min_date ?? null,
        maxDate: dateRow.max_date ?? null,
        days:    Number(dateRow.days),
      };
    } catch {
      return { table: meta.table, label: meta.label, prefix: meta.prefix,
               total: rowCountMap[meta.table] ?? 0, minDate: null, maxDate: null, days: 0 };
    }
  }));

  statsCache = { data: results, expiresAt: Date.now() + 30_000 };
  res.json(results);
});

// レース検索: GET /api/races?date=YYYYMMDD[&course=XX]
app.get('/api/races', async (req, res) => {
  const { date, course } = req.query as { date?: string; course?: string };
  if (!date || !/^\d{8}$/.test(date)) {
    res.status(400).json({ error: '日付はYYYYMMDD形式で指定してください' });
    return;
  }
  const params: string[] = [date];
  let sql = `SELECT course_code, year_code, kai, day_code, race_num,
                    race_name, race_name_9char, distance, tds_code,
                    grade, heads, start_time, data_kubun
             FROM T_BAC WHERE ymd = ?`;
  if (course && /^\d{2}$/.test(course)) {
    sql += ' AND course_code = ?';
    params.push(course);
  }
  sql += ' ORDER BY course_code, CAST(race_num AS UNSIGNED)';
  const [rows] = await pool.query<any>(sql, params);
  res.json(rows);
});

// 騎手別 基準人気帯ごと平均着順偏差: GET /api/jockey-ninki-stats
// キャッシュ: yearFrom:yearTo をキーに5分間保持
const ninkiStatsCache = new Map<string, { benchmarks: any; allJockeys: any[]; expiresAt: number }>();

app.get('/api/jockey-ninki-stats', async (req, res) => {
  const yearFrom = String(req.query.yearFrom ?? '22').replace(/^20/, '').slice(-2);
  const yearTo   = String(req.query.yearTo   ?? '26').replace(/^20/, '').slice(-2);
  const minRides = Math.max(1, parseInt(String(req.query.minRides ?? '100')) || 100);

  const BANDS = ['1','2','3','4-6','7-9','10+'];
  const cacheKey = `${yearFrom}:${yearTo}`;
  const cached = ninkiStatsCache.get(cacheKey);

  let benchmarks: Record<string, {cnt:number; avg_order:number}>;
  let allJockeys: any[];

  if (cached && cached.expiresAt > Date.now()) {
    benchmarks  = cached.benchmarks;
    allJockeys  = cached.allJockeys;
  } else {
    // FORCE INDEX で T_KYI のフルスキャンを抑制（year_code範囲→インデックス Range scan）
    const baseFrom = `FROM T_KYI k FORCE INDEX (idx_kyi_year_ninki_kishu)
       JOIN T_SED s
         ON  s.course_code=k.course_code AND s.year_code=k.year_code
         AND s.kai=k.kai AND s.day_code=k.day_code
         AND s.race_num=k.race_num AND s.umaban=k.uma_num
       JOIN T_BAC b
         ON  b.course_code=k.course_code AND b.year_code=k.year_code
         AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
       WHERE k.year_code BETWEEN ? AND ?
         AND k.kijun_ninki != '' AND k.kijun_ninki IS NOT NULL
         AND s.ijou_kubun='0'
         AND CAST(s.order_of_finish AS UNSIGNED) BETWEEN 1 AND 18
         AND b.tds_code IN ('1','2')`;

    // ベンチマーク・騎手クエリを並列実行、GROUP BY は生の kijun_ninki で CASE 式を避ける
    const [[benchRows], [rows]] = await Promise.all([
      pool.query<any>(
        `SELECT CAST(k.kijun_ninki AS UNSIGNED) AS ninki_raw,
           COUNT(*) AS cnt,
           ROUND(AVG(CAST(s.order_of_finish AS UNSIGNED)), 2) AS avg_order
         ${baseFrom}
         GROUP BY ninki_raw`,
        [yearFrom, yearTo]
      ),
      pool.query<any>(
        `SELECT k.kishu_code, ANY_VALUE(k.kishu_name) AS kishu_name,
           CAST(k.kijun_ninki AS UNSIGNED) AS ninki_raw,
           COUNT(*) AS cnt,
           ROUND(AVG(CAST(s.order_of_finish AS UNSIGNED)), 2) AS avg_order
         ${baseFrom}
           AND k.kishu_code != '' AND k.kishu_code IS NOT NULL
         GROUP BY k.kishu_code, ninki_raw`,
        [yearFrom, yearTo]
      ),
    ]);

    // ninki_raw (数値) → バンド文字列への変換
    function rawToBand(raw: number): string {
      if (raw === 1) return '1';
      if (raw === 2) return '2';
      if (raw === 3) return '3';
      if (raw <= 6)  return '4-6';
      if (raw <= 9)  return '7-9';
      return '10+';
    }

    benchmarks = {} as Record<string, {cnt:number; avg_order:number}>;
    for (const b of BANDS) benchmarks[b] = { cnt: 0, avg_order: 0 };
    for (const row of benchRows) {
      const band = rawToBand(Number(row.ninki_raw));
      const existing = benchmarks[band];
      // 重み付き平均で合算（同バンドの複数raw値をまとめる）
      const total = existing.cnt + Number(row.cnt);
      benchmarks[band] = {
        cnt: total,
        avg_order: total > 0
          ? (existing.cnt * existing.avg_order + Number(row.cnt) * Number(row.avg_order)) / total
          : Number(row.avg_order),
      };
    }
    // 小数点2桁に丸め
    for (const b of BANDS) {
      benchmarks[b].avg_order = Math.round(benchmarks[b].avg_order * 100) / 100;
    }

    const map = new Map<string, any>();
    for (const row of rows) {
      if (!map.has(row.kishu_code)) {
        map.set(row.kishu_code, {
          kishu_code: row.kishu_code,
          kishu_name: row.kishu_name,
          total: 0,
          bands: {} as Record<string, {cnt:number; avg_order:number; deviation:number}|null>,
        });
        for (const b of BANDS) map.get(row.kishu_code).bands[b] = null;
      }
      const j = map.get(row.kishu_code);
      const band = rawToBand(Number(row.ninki_raw));
      const cnt = Number(row.cnt);
      const ao  = Number(row.avg_order);
      j.total += cnt;
      // 同バンドの複数rawをまとめる
      const existing = j.bands[band];
      if (existing) {
        const total = existing.cnt + cnt;
        j.bands[band] = { cnt: total, avg_order: (existing.cnt * existing.avg_order + cnt * ao) / total, deviation: 0 };
      } else {
        j.bands[band] = { cnt, avg_order: ao, deviation: 0 };
      }
    }
    // 偏差を計算
    for (const j of map.values()) {
      for (const b of BANDS) {
        const bd = j.bands[b];
        if (!bd) continue;
        const bm = benchmarks[b];
        bd.avg_order  = Math.round(bd.avg_order * 10) / 10;
        bd.deviation  = bm ? Math.round((bd.avg_order - bm.avg_order) * 10) / 10 : null;
      }
    }

    allJockeys = [...map.values()].sort((a, b) => b.total - a.total);
    ninkiStatsCache.set(cacheKey, { benchmarks, allJockeys, expiresAt: Date.now() + 30 * 60 * 1000 });
  }

  const jockeys = allJockeys.filter(j => j.total >= minRides);
  res.json({ benchmarks, jockeys });
});

// レース単体情報: GET /api/races/:raceKey
app.get('/api/races/:raceKey', async (req, res) => {
  const { raceKey } = req.params;
  if (!/^\d{5}[0-9a-f]\d{2}$/i.test(raceKey)) {
    res.status(400).json({ error: '無効なレースキーです' });
    return;
  }
  const course_code = raceKey.slice(0, 2);
  const year_code   = raceKey.slice(2, 4);
  const kai         = raceKey.slice(4, 5);
  const day_code    = raceKey.slice(5, 6);
  const race_num    = raceKey.slice(6, 8);

  const [[race]] = await pool.query<any>(
    `SELECT course_code, year_code, kai, day_code, race_num,
            ymd, race_name, race_name_9char, distance, tds_code,
            grade, \`class\`, heads, start_time, data_kubun, migihidari, naigai
     FROM T_BAC
     WHERE course_code=? AND year_code=? AND kai=? AND day_code=? AND race_num=?`,
    [course_code, year_code, kai, day_code, race_num]
  );
  if (!race) { res.status(404).json({ error: 'レースが見つかりません' }); return; }
  res.json(race);
});

// レース詳細: GET /api/races/:raceKey/entries
// raceKey = course_code(2) + year_code(2) + kai(1) + day_code(1) + race_num(2)
app.get('/api/races/:raceKey/entries', async (req, res) => {
  const { raceKey } = req.params;
  if (!/^\d{5}[0-9a-f]\d{2}$/i.test(raceKey)) {
    res.status(400).json({ error: '無効なレースキーです' });
    return;
  }
  const course_code = raceKey.slice(0, 2);
  const year_code   = raceKey.slice(2, 4);
  const kai         = raceKey.slice(4, 5);
  const day_code    = raceKey.slice(5, 6);
  const race_num    = raceKey.slice(6, 8);

  const [rows] = await pool.query<any>(
    `SELECT k.uma_num, k.waku_num, k.uma_name,
            k.kyakushitsu,
            k.kijun_odds, k.kijun_ninki,
            k.joho_index,
            k.idm,
            k.in_idm,
            k.goal_juni,
            k.kyusha_index,
            k.kishu_name, k.trainer_name,
            k.kishu_code, k.trainer_code,
            k.ten_index_juni, k.agari_index_juni, k.ichi_index_juni, k.blinker,
            k.ten_index, k.agari_index,
            fs.grade AS furi_grade, fs.score AS furi_score,
            fs.prev_furi_degree, fs.prev_furi_phase, fs.is_hot AS furi_is_hot,
            k.chokyo_yajirushi,
            k.nyukyu_nichi_mae,
            k.hohbokusaki_rank,
            k.joken_class,
            c.oi_index, c.shiage_index,
            c.chokyo_ryo_hyoka,
            c.course_saka,
            c.isshuumae_oi_index,
            cr.win_recovery   AS combo_win_rr,
            cr.place_recovery AS combo_place_rr,
            cr.total_count    AS combo_n,
            kya.anaba_place_rr  AS kyusha_anaba_place_rr,
            kya.anaba_win_rr    AS kyusha_anaba_win_rr,
            kya.anaba_win_rate  AS kyusha_anaba_win_rate,
            kya.anaba_place_rate AS kyusha_anaba_place_rate,
            kya.anaba_n         AS kyusha_anaba_n,
            kyn.score          AS kyn_score,
            kyn.ki_band        AS kyn_ki_band,
            kyn.ninki_band     AS kyn_ninki_band,
            kyn.total_count    AS kyn_n,
            kyn.win_recovery   AS kyn_win_rr,
            kyn.place_recovery AS kyn_place_rr,
            kyn.base_place_rr  AS kyn_base_rr,
            kyn.place_excess   AS kyn_excess,
            ans.overall_score AS anaba_overall_score,
            ans.course_score  AS anaba_course_score,
            ans.score_ten, ans.score_agari, ans.score_ichi, ans.score_goal,
            ans.score_combo, ans.score_idm, ans.score_gekiso, ans.score_manbaken,
            ans.score_chokyo, ans.score_kyusha, ans.score_kyakushitsu,
            ans.score_joshodo, ans.score_tekisei, ans.score_blood,
            ans.score_ten_c, ans.score_agari_c, ans.score_ichi_c, ans.score_goal_c,
            ans.score_combo_c, ans.score_kyakushitsu_c, ans.score_blood_c,
            hms.overall_score AS honmei_overall_score,
            hms.course_score  AS honmei_course_score,
            hms.score_ten     AS hms_score_ten,
            hms.score_agari   AS hms_score_agari,
            hms.score_ichi    AS hms_score_ichi,
            hms.score_goal    AS hms_score_goal,
            hms.score_combo   AS hms_score_combo,
            hms.score_idm     AS hms_score_idm,
            hms.score_joho    AS hms_score_joho,
            hms.score_kyusha  AS hms_score_kyusha,
            hms.score_chokyo  AS hms_score_chokyo,
            hms.score_kyakushitsu AS hms_score_kyakushitsu,
            hms.score_joshodo AS hms_score_joshodo,
            hms.score_tekisei AS hms_score_tekisei,
            hms.score_blood   AS hms_score_blood,
            hms.score_ten_c         AS hms_score_ten_c,
            hms.score_agari_c       AS hms_score_agari_c,
            hms.score_ichi_c        AS hms_score_ichi_c,
            hms.score_goal_c        AS hms_score_goal_c,
            hms.score_combo_c       AS hms_score_combo_c,
            hms.score_kyakushitsu_c AS hms_score_kyakushitsu_c,
            hms.score_blood_c       AS hms_score_blood_c,
            pfs.overall_score AS pacefit_score,
            pfs.pace_yoso     AS pacefit_pace,
            evs.pred_place_prob AS ev_pred_place_prob,
            evs.market_place_prob AS ev_market_place_prob,
            evs.ev_index      AS ev_index,
            evs.race_rank     AS ev_race_rank,
            evs.race_rank_from_last AS ev_race_rank_from_last,
            mm.mark           AS my_mark,
            s.order_of_finish AS result_order,
            s.win             AS result_win,
            s.place           AS result_place,
            s.ijou_kubun      AS result_ijou
     FROM T_KYI k
     LEFT JOIN T_CYB c
       ON  c.course_code = k.course_code AND c.year_code = k.year_code
       AND c.kai = k.kai AND c.day_code = k.day_code
       AND c.race_num = k.race_num AND c.uma_num = k.uma_num
     LEFT JOIN T_COMBO_RECOVERY cr
       ON  cr.kishu_code   = k.kishu_code
       AND cr.trainer_code = k.trainer_code
     LEFT JOIN (
       SELECT trainer_code,
              ROUND(SUM(place_payout_sum) / SUM(total_count), 1) AS anaba_place_rr,
              ROUND(SUM(win_payout_sum)   / SUM(total_count), 1) AS anaba_win_rr,
              ROUND(SUM(win_count)   / SUM(total_count) * 100, 1) AS anaba_win_rate,
              ROUND(SUM(place_count) / SUM(total_count) * 100, 1) AS anaba_place_rate,
              SUM(total_count)                                    AS anaba_n
       FROM T_KYUSHA_FACTOR_AGG
       WHERE factor_type = 'kyusha_idx_x_odds'
         AND factor_value = 'plus_15~'
       GROUP BY trainer_code
     ) kya ON kya.trainer_code = k.trainer_code
     -- 厩舎穴指数: 厩舎指数の帯 × 基準人気の帯で区分表を引く（sql/kyusha_ninki_index.sql と同じ区切り）
     LEFT JOIN T_KYUSHA_NINKI_AGG kyn
       ON  TRIM(k.kyusha_index) REGEXP '^-?[0-9]+([.][0-9]+)?$'
       AND TRIM(k.kijun_ninki) REGEXP '^[0-9]+$' AND CAST(TRIM(k.kijun_ninki) AS UNSIGNED) >= 1
       AND kyn.ki_band = CASE WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(5,1)) < 0 THEN '<0'
                              WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(5,1)) < 8 THEN '0-8'
                              WHEN CAST(TRIM(k.kyusha_index) AS DECIMAL(5,1)) < 15 THEN '8-15' ELSE '15+' END
       AND kyn.ninki_band = CASE WHEN CAST(TRIM(k.kijun_ninki) AS UNSIGNED) <= 5 THEN '1-5'
                                 WHEN CAST(TRIM(k.kijun_ninki) AS UNSIGNED) <= 8 THEN '6-8'
                                 WHEN CAST(TRIM(k.kijun_ninki) AS UNSIGNED) <= 10 THEN '9-10' ELSE '11+' END
     LEFT JOIN T_ANABA_SCORE ans
       ON  ans.course_code = k.course_code AND ans.year_code = k.year_code
       AND ans.kai = k.kai AND ans.day_code = k.day_code
       AND ans.race_num = k.race_num AND ans.uma_num = k.uma_num
     LEFT JOIN T_HONMEI_SCORE hms
       ON  hms.course_code = k.course_code AND hms.year_code = k.year_code
       AND hms.kai = k.kai AND hms.day_code = k.day_code
       AND hms.race_num = k.race_num AND hms.uma_num = k.uma_num
     LEFT JOIN T_PACEFIT_SCORE pfs
       ON  pfs.course_code = k.course_code AND pfs.year_code = k.year_code
       AND pfs.kai = k.kai AND pfs.day_code = k.day_code
       AND pfs.race_num = k.race_num AND pfs.uma_num = k.uma_num
     LEFT JOIN T_FURI_SCORE fs
       ON  fs.course_code = k.course_code AND fs.year_code = k.year_code
       AND fs.kai = k.kai AND fs.day_code = k.day_code
       AND fs.race_num = k.race_num AND fs.uma_num = k.uma_num
     LEFT JOIN T_EV_SCORE evs
       ON  evs.course_code = k.course_code AND evs.year_code = k.year_code
       AND evs.kai = k.kai AND evs.day_code = k.day_code
       AND evs.race_num = k.race_num AND evs.uma_num = k.uma_num
     LEFT JOIN T_MY_MARK mm
       ON  mm.course_code = k.course_code AND mm.year_code = k.year_code
       AND mm.kai = k.kai AND mm.day_code = k.day_code
       AND mm.race_num = k.race_num AND mm.uma_num = k.uma_num
     LEFT JOIN T_SED s
       ON  s.course_code = k.course_code AND s.year_code = k.year_code
       AND s.kai = k.kai AND s.day_code = k.day_code
       AND s.race_num = k.race_num AND s.umaban = k.uma_num
     WHERE k.course_code=? AND k.year_code=? AND k.kai=? AND k.day_code=? AND k.race_num=?
     ORDER BY CAST(k.uma_num AS UNSIGNED)`,
    [course_code, year_code, kai, day_code, race_num]
  );
  res.json({ source: 'entries', rows });
});

// 自分の予想印 保存/削除: POST /api/races/:raceKey/marks  body: { uma_num, mark }
// mark が空/null の場合は削除（未設定に戻す）
app.post('/api/races/:raceKey/marks', async (req, res) => {
  const { raceKey } = req.params;
  if (!/^\d{5}[0-9a-f]\d{2}$/i.test(raceKey)) {
    res.status(400).json({ error: '無効なレースキーです' });
    return;
  }
  const { uma_num, mark } = req.body as { uma_num?: string; mark?: string | null };
  if (!uma_num || !/^\d{1,2}$/.test(uma_num)) {
    res.status(400).json({ error: '馬番が不正です' });
    return;
  }
  const course_code = raceKey.slice(0, 2);
  const year_code   = raceKey.slice(2, 4);
  const kai         = raceKey.slice(4, 5);
  const day_code    = raceKey.slice(5, 6);
  const race_num    = raceKey.slice(6, 8);
  const umaNumPadded = uma_num.padStart(2, '0');

  try {
    if (!mark) {
      await pool.query(
        `DELETE FROM T_MY_MARK WHERE course_code=? AND year_code=? AND kai=? AND day_code=? AND race_num=? AND uma_num=?`,
        [course_code, year_code, kai, day_code, race_num, umaNumPadded]
      );
      res.json({ ok: true });
      return;
    }
    if (!/^[1-6]$/.test(mark)) {
      res.status(400).json({ error: '印の値が不正です' });
      return;
    }
    await pool.query(
      `INSERT INTO T_MY_MARK (course_code, year_code, kai, day_code, race_num, uma_num, mark)
       VALUES (?,?,?,?,?,?,?)
       ON DUPLICATE KEY UPDATE mark = VALUES(mark)`,
      [course_code, year_code, kai, day_code, race_num, umaNumPadded, mark]
    );
    res.json({ ok: true });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// ────────────────────────────────────────────────────────────────────────────
// 分析API: POST /api/analyze
// ────────────────────────────────────────────────────────────────────────────

// 集計キーの SELECT / GROUP BY 式のホワイトリスト
// orderSql: ORDER BY 用の数値キャスト式。未指定の場合は groupSql を流用。
const AGGREGATE_MAP: Record<string, { selectSql: string; groupSql: string; orderSql?: string; alias: string }> = {
  ymd:         { alias: '年',           selectSql: "LEFT(b.ymd,4)",   groupSql: "LEFT(b.ymd,4)" },
  course:      { alias: '競馬場',      groupSql: "b.course_code",
                 selectSql: "CASE b.course_code WHEN '01' THEN '札幌' WHEN '02' THEN '函館' WHEN '03' THEN '福島' WHEN '04' THEN '新潟' WHEN '05' THEN '東京' WHEN '06' THEN '中山' WHEN '07' THEN '中京' WHEN '08' THEN '京都' WHEN '09' THEN '阪神' WHEN '10' THEN '小倉' ELSE b.course_code END" },
  tds:         { alias: '芝ダ',        groupSql: "b.tds_code",
                 selectSql: "CASE b.tds_code WHEN '1' THEN '芝' WHEN '2' THEN 'ダート' WHEN '3' THEN '障害' ELSE b.tds_code END" },
  distance:    { alias: '距離',        selectSql: "b.distance",      groupSql: "b.distance",    orderSql: "CAST(b.distance AS UNSIGNED)" },
  class:       { alias: 'クラス',      groupSql: "b.`class`",
                 selectSql: "CASE b.`class` WHEN 'A1' THEN '新馬' WHEN 'A3' THEN '未勝利' WHEN '05' THEN '1勝クラス' WHEN '10' THEN '2勝クラス' WHEN '16' THEN '3勝クラス' WHEN 'OP' THEN 'オープン' ELSE b.`class` END" },
  odds:        { alias: '基準オッズ帯',
                 groupSql: "CASE WHEN k.kijun_odds IS NULL THEN '—' WHEN CAST(k.kijun_odds AS DECIMAL(7,1)) < 2.0 THEN '~1.9' WHEN CAST(k.kijun_odds AS DECIMAL(7,1)) < 3.0 THEN '2.0~2.9' WHEN CAST(k.kijun_odds AS DECIMAL(7,1)) < 5.0 THEN '3.0~4.9' WHEN CAST(k.kijun_odds AS DECIMAL(7,1)) < 10.0 THEN '5.0~9.9' WHEN CAST(k.kijun_odds AS DECIMAL(7,1)) < 20.0 THEN '10.0~19.9' WHEN CAST(k.kijun_odds AS DECIMAL(7,1)) < 50.0 THEN '20.0~49.9' ELSE '50.0~' END",
                 orderSql: "MIN(CAST(k.kijun_odds AS DECIMAL(7,1)))", selectSql: "" },
  odds_rank:   { alias: '基準人気',    selectSql: "k.kijun_ninki",   groupSql: "k.kijun_ninki", orderSql: "CAST(k.kijun_ninki AS UNSIGNED)" },
  wakuban:     { alias: '枠番',        selectSql: "k.waku_num",      groupSql: "k.waku_num",    orderSql: "CAST(k.waku_num AS UNSIGNED)" },
  umaban:      { alias: '馬番',        selectSql: "k.uma_num",       groupSql: "k.uma_num",     orderSql: "CAST(k.uma_num AS UNSIGNED)" },
  info:        { alias: '情報印',      selectSql: "k.in_joho",       groupSql: "k.in_joho",     orderSql: "CAST(k.in_joho AS UNSIGNED)" },
  goal:        { alias: '展開順位',    selectSql: "k.goal_juni",     groupSql: "k.goal_juni",   orderSql: "CAST(k.goal_juni AS UNSIGNED)" },
  idm_mark:    { alias: 'IDM印',       selectSql: "k.in_idm",        groupSql: "k.in_idm",      orderSql: "CAST(k.in_idm AS UNSIGNED)" },
  idm_idx:     { alias: 'IDM指数帯',   groupSql: "CASE WHEN CAST(k.idm AS DECIMAL(6,1)) < 30 THEN '~30' WHEN CAST(k.idm AS DECIMAL(6,1)) < 36 THEN '30~36' WHEN CAST(k.idm AS DECIMAL(6,1)) < 42 THEN '36~42' WHEN CAST(k.idm AS DECIMAL(6,1)) < 48 THEN '42~48' WHEN CAST(k.idm AS DECIMAL(6,1)) < 54 THEN '48~54' WHEN CAST(k.idm AS DECIMAL(6,1)) < 60 THEN '54~60' WHEN CAST(k.idm AS DECIMAL(6,1)) < 66 THEN '60~66' WHEN CAST(k.idm AS DECIMAL(6,1)) < 72 THEN '66~72' WHEN CAST(k.idm AS DECIMAL(6,1)) >= 72 THEN '72~' ELSE 'その他' END",
                 orderSql: "MIN(CAST(k.idm AS DECIMAL(6,1)))", selectSql: "" },
  kyusha_idx:  { alias: '厩舎指数帯',  groupSql: "CASE WHEN CAST(k.kyusha_index AS DECIMAL(6,1)) < -10 THEN '-20~-10' WHEN CAST(k.kyusha_index AS DECIMAL(6,1)) < 0 THEN '-10~0' WHEN CAST(k.kyusha_index AS DECIMAL(6,1)) < 10 THEN '0~10' WHEN CAST(k.kyusha_index AS DECIMAL(6,1)) < 20 THEN '10~20' WHEN CAST(k.kyusha_index AS DECIMAL(6,1)) <= 40 THEN '20~40' ELSE 'その他' END",
                 orderSql: "MIN(CAST(k.kyusha_index AS DECIMAL(6,1)))", selectSql: "" },
  first:       { alias: '前3F順位',    selectSql: "k.ten_index_juni", groupSql: "k.ten_index_juni", orderSql: "CAST(k.ten_index_juni AS UNSIGNED)" },
  latter:      { alias: '後3F順位',    selectSql: "k.agari_index_juni", groupSql: "k.agari_index_juni", orderSql: "CAST(k.agari_index_juni AS UNSIGNED)" },
  jockey:      { alias: '騎手',        selectSql: "k.kishu_name",    groupSql: "k.kishu_name" },
  trainer:     { alias: '調教師',      selectSql: "k.trainer_name",  groupSql: "k.trainer_name" },
  kyakushitsu: { alias: '脚質',        groupSql: "k.kyakushitsu",
                 selectSql: "CASE k.kyakushitsu WHEN '1' THEN '逃げ' WHEN '2' THEN '先行' WHEN '3' THEN '差し' WHEN '4' THEN '追込' ELSE 'その他' END" },
  oikiri:      { alias: '追切指数帯',  groupSql: "CASE WHEN CAST(c.oi_index AS UNSIGNED) < 20 THEN '~20' WHEN CAST(c.oi_index AS UNSIGNED) < 40 THEN '20~40' WHEN CAST(c.oi_index AS UNSIGNED) < 50 THEN '40~50' WHEN CAST(c.oi_index AS UNSIGNED) < 60 THEN '50~60' WHEN CAST(c.oi_index AS UNSIGNED) < 70 THEN '60~70' WHEN CAST(c.oi_index AS UNSIGNED) < 80 THEN '70~80' WHEN CAST(c.oi_index AS UNSIGNED) < 90 THEN '80~90' WHEN CAST(c.oi_index AS UNSIGNED) >= 90 THEN '90~' ELSE 'その他' END",
                 orderSql: "MIN(CAST(c.oi_index AS UNSIGNED))", selectSql: "" },
  shiage:      { alias: '仕上指数帯',  groupSql: "CASE WHEN CAST(c.shiage_index AS UNSIGNED) < 20 THEN '~20' WHEN CAST(c.shiage_index AS UNSIGNED) < 40 THEN '20~40' WHEN CAST(c.shiage_index AS UNSIGNED) < 50 THEN '40~50' WHEN CAST(c.shiage_index AS UNSIGNED) < 60 THEN '50~60' WHEN CAST(c.shiage_index AS UNSIGNED) < 70 THEN '60~70' WHEN CAST(c.shiage_index AS UNSIGNED) < 80 THEN '70~80' WHEN CAST(c.shiage_index AS UNSIGNED) < 90 THEN '80~90' WHEN CAST(c.shiage_index AS UNSIGNED) >= 90 THEN '90~' ELSE 'その他' END",
                 orderSql: "MIN(CAST(c.shiage_index AS UNSIGNED))", selectSql: "" },
  chokyo_sp:   { alias: '調教SP',
                 selectSql: "CASE WHEN sp_cte.sp_score IS NULL THEN '—' WHEN sp_cte.sp_score >= 4 THEN 'A' WHEN sp_cte.sp_score >= 2 THEN 'B' WHEN sp_cte.sp_score >= -1 THEN 'C' WHEN sp_cte.sp_score >= -4 THEN 'D' ELSE 'E' END",
                 groupSql:  "CASE WHEN sp_cte.sp_score IS NULL THEN '—' WHEN sp_cte.sp_score >= 4 THEN 'A' WHEN sp_cte.sp_score >= 2 THEN 'B' WHEN sp_cte.sp_score >= -1 THEN 'C' WHEN sp_cte.sp_score >= -4 THEN 'D' ELSE 'E' END",
                 orderSql:  "MIN(sp_cte.sp_score) DESC" },
  ex_overall:  { alias: 'EX指数全体帯',
                 groupSql: "CASE WHEN ans.overall_score IS NULL THEN '—' WHEN CAST(ans.overall_score AS DECIMAL(7,1)) < 0 THEN '<0' WHEN CAST(ans.overall_score AS DECIMAL(7,1)) < 20 THEN '0~20' WHEN CAST(ans.overall_score AS DECIMAL(7,1)) < 50 THEN '20~50' WHEN CAST(ans.overall_score AS DECIMAL(7,1)) < 100 THEN '50~100' ELSE '100~' END",
                 orderSql: "MIN(CAST(COALESCE(ans.overall_score, -99999) AS DECIMAL(7,1)))", selectSql: "" },
  ex_course:   { alias: 'EX指数コース帯',
                 groupSql: "CASE WHEN ans.course_score IS NULL THEN '—' WHEN CAST(ans.course_score AS DECIMAL(7,1)) < 0 THEN '<0' WHEN CAST(ans.course_score AS DECIMAL(7,1)) < 20 THEN '0~20' WHEN CAST(ans.course_score AS DECIMAL(7,1)) < 50 THEN '20~50' WHEN CAST(ans.course_score AS DECIMAL(7,1)) < 100 THEN '50~100' ELSE '100~' END",
                 orderSql: "MIN(CAST(COALESCE(ans.course_score, -99999) AS DECIMAL(7,1)))", selectSql: "" },
  honmei_overall: { alias: '本命指数全体帯',
                 groupSql: "CASE WHEN hms.overall_score IS NULL THEN '—' WHEN CAST(hms.overall_score AS DECIMAL(7,1)) < 0 THEN '<0' WHEN CAST(hms.overall_score AS DECIMAL(7,1)) < 15 THEN '0~15' WHEN CAST(hms.overall_score AS DECIMAL(7,1)) < 30 THEN '15~30' WHEN CAST(hms.overall_score AS DECIMAL(7,1)) < 50 THEN '30~50' ELSE '50~' END",
                 orderSql: "MIN(CAST(COALESCE(hms.overall_score, -99999) AS DECIMAL(7,1)))", selectSql: "" },
  honmei_course:  { alias: '本命指数コース帯',
                 groupSql: "CASE WHEN hms.course_score IS NULL THEN '—' WHEN CAST(hms.course_score AS DECIMAL(7,1)) < 0 THEN '<0' WHEN CAST(hms.course_score AS DECIMAL(7,1)) < 15 THEN '0~15' WHEN CAST(hms.course_score AS DECIMAL(7,1)) < 30 THEN '15~30' WHEN CAST(hms.course_score AS DECIMAL(7,1)) < 50 THEN '30~50' ELSE '50~' END",
                 orderSql: "MIN(CAST(COALESCE(hms.course_score, -99999) AS DECIMAL(7,1)))", selectSql: "" },
  tenkai:      { alias: '展開指数帯',
                 groupSql: "CASE WHEN pfs.overall_score IS NULL THEN '—' WHEN CAST(pfs.overall_score AS DECIMAL(7,1)) < 0 THEN '<0' WHEN CAST(pfs.overall_score AS DECIMAL(7,1)) < 15 THEN '0~15' WHEN CAST(pfs.overall_score AS DECIMAL(7,1)) < 25 THEN '15~25' ELSE '25~' END",
                 orderSql: "MIN(CAST(COALESCE(pfs.overall_score, -99999) AS DECIMAL(7,1)))", selectSql: "" },
};
// caseベースの集計キーは selectSql と groupSql を同一にする
for (const key of Object.keys(AGGREGATE_MAP)) {
  const entry = AGGREGATE_MAP[key];
  if (!entry.selectSql) entry.selectSql = entry.groupSql;
}

// ── ファクトテーブル用集計マップ（T_ANALYZE_FACT 対応・キャスト不要）
const AGGREGATE_MAP_FACT: Record<string, { selectSql: string; groupSql: string; orderSql?: string; alias: string }> = {
  ymd:         { alias: '年',           selectSql: "LEFT(f.ymd,4)",      groupSql: "LEFT(f.ymd,4)" },
  course:      { alias: '競馬場',      groupSql:  "f.course_code",
                 selectSql: "CASE f.course_code WHEN '01' THEN '札幌' WHEN '02' THEN '函館' WHEN '03' THEN '福島' WHEN '04' THEN '新潟' WHEN '05' THEN '東京' WHEN '06' THEN '中山' WHEN '07' THEN '中京' WHEN '08' THEN '京都' WHEN '09' THEN '阪神' WHEN '10' THEN '小倉' ELSE f.course_code END" },
  tds:         { alias: '芝ダ',        groupSql:  "f.tds_code",
                 selectSql: "CASE f.tds_code WHEN '1' THEN '芝' WHEN '2' THEN 'ダート' WHEN '3' THEN '障害' ELSE f.tds_code END" },
  distance:    { alias: '距離',        selectSql: "f.distance",         groupSql: "f.distance",         orderSql: "f.distance" },
  class:       { alias: 'クラス',      groupSql:  "f.class_code",
                 selectSql: "CASE f.class_code WHEN 'A1' THEN '新馬' WHEN 'A3' THEN '未勝利' WHEN '05' THEN '1勝クラス' WHEN '10' THEN '2勝クラス' WHEN '16' THEN '3勝クラス' WHEN 'OP' THEN 'オープン' ELSE f.class_code END" },
  odds:        { alias: '基準オッズ帯',
                 groupSql: "CASE WHEN f.kijun_odds IS NULL THEN '—' WHEN f.kijun_odds < 2.0 THEN '~1.9' WHEN f.kijun_odds < 3.0 THEN '2.0~2.9' WHEN f.kijun_odds < 5.0 THEN '3.0~4.9' WHEN f.kijun_odds < 10.0 THEN '5.0~9.9' WHEN f.kijun_odds < 20.0 THEN '10.0~19.9' WHEN f.kijun_odds < 50.0 THEN '20.0~49.9' ELSE '50.0~' END",
                 orderSql: "MIN(f.kijun_odds)", selectSql: "" },
  odds_rank:   { alias: '基準人気',    selectSql: "f.kijun_ninki",      groupSql: "f.kijun_ninki",      orderSql: "f.kijun_ninki" },
  wakuban:     { alias: '枠番',        selectSql: "f.waku_num",         groupSql: "f.waku_num",         orderSql: "f.waku_num" },
  umaban:      { alias: '馬番',        selectSql: "f.uma_num",          groupSql: "f.uma_num",          orderSql: "f.uma_num" },
  info:        { alias: '情報印',      selectSql: "f.in_joho",          groupSql: "f.in_joho",          orderSql: "f.in_joho" },
  goal:        { alias: '展開順位',    selectSql: "f.goal_juni",        groupSql: "f.goal_juni",        orderSql: "f.goal_juni" },
  idm_mark:    { alias: 'IDM印',       selectSql: "f.in_idm",           groupSql: "f.in_idm",           orderSql: "f.in_idm" },
  idm_idx:     { alias: 'IDM指数帯',
                 groupSql: "CASE WHEN f.idm < 30 THEN '~30' WHEN f.idm < 36 THEN '30~36' WHEN f.idm < 42 THEN '36~42' WHEN f.idm < 48 THEN '42~48' WHEN f.idm < 54 THEN '48~54' WHEN f.idm < 60 THEN '54~60' WHEN f.idm < 66 THEN '60~66' WHEN f.idm < 72 THEN '66~72' WHEN f.idm >= 72 THEN '72~' ELSE 'その他' END",
                 orderSql: "MIN(f.idm)", selectSql: "" },
  kyusha_idx:  { alias: '厩舎指数帯',
                 groupSql: "CASE WHEN f.kyusha_index < -10 THEN '-20~-10' WHEN f.kyusha_index < 0 THEN '-10~0' WHEN f.kyusha_index < 10 THEN '0~10' WHEN f.kyusha_index < 20 THEN '10~20' WHEN f.kyusha_index <= 40 THEN '20~40' ELSE 'その他' END",
                 orderSql: "MIN(f.kyusha_index)", selectSql: "" },
  first:       { alias: '前3F順位',    selectSql: "f.ten_index_juni",   groupSql: "f.ten_index_juni",   orderSql: "f.ten_index_juni" },
  latter:      { alias: '後3F順位',    selectSql: "f.agari_index_juni", groupSql: "f.agari_index_juni", orderSql: "f.agari_index_juni" },
  jockey:      { alias: '騎手',        selectSql: "f.kishu_name",       groupSql: "f.kishu_name" },
  trainer:     { alias: '調教師',      selectSql: "f.trainer_name",     groupSql: "f.trainer_name" },
  kyakushitsu: { alias: '脚質',        groupSql:  "f.kyakushitsu",
                 selectSql: "CASE f.kyakushitsu WHEN '1' THEN '逃げ' WHEN '2' THEN '先行' WHEN '3' THEN '差し' WHEN '4' THEN '追込' ELSE 'その他' END" },
  oikiri:      { alias: '追切指数帯',
                 groupSql: "CASE WHEN f.oi_index < 20 THEN '~20' WHEN f.oi_index < 40 THEN '20~40' WHEN f.oi_index < 50 THEN '40~50' WHEN f.oi_index < 60 THEN '50~60' WHEN f.oi_index < 70 THEN '60~70' WHEN f.oi_index < 80 THEN '70~80' WHEN f.oi_index < 90 THEN '80~90' WHEN f.oi_index >= 90 THEN '90~' ELSE 'その他' END",
                 orderSql: "MIN(f.oi_index)", selectSql: "" },
  shiage:      { alias: '仕上指数帯',
                 groupSql: "CASE WHEN f.shiage_index < 20 THEN '~20' WHEN f.shiage_index < 40 THEN '20~40' WHEN f.shiage_index < 50 THEN '40~50' WHEN f.shiage_index < 60 THEN '50~60' WHEN f.shiage_index < 70 THEN '60~70' WHEN f.shiage_index < 80 THEN '70~80' WHEN f.shiage_index < 90 THEN '80~90' WHEN f.shiage_index >= 90 THEN '90~' ELSE 'その他' END",
                 orderSql: "MIN(f.shiage_index)", selectSql: "" },
  chokyo_sp:   { alias: '調教SP',
                 selectSql: "CASE WHEN f.chokyo_sp IS NULL THEN '—' WHEN f.chokyo_sp >= 4 THEN 'A' WHEN f.chokyo_sp >= 2 THEN 'B' WHEN f.chokyo_sp >= -1 THEN 'C' WHEN f.chokyo_sp >= -4 THEN 'D' ELSE 'E' END",
                 groupSql:  "CASE WHEN f.chokyo_sp IS NULL THEN '—' WHEN f.chokyo_sp >= 4 THEN 'A' WHEN f.chokyo_sp >= 2 THEN 'B' WHEN f.chokyo_sp >= -1 THEN 'C' WHEN f.chokyo_sp >= -4 THEN 'D' ELSE 'E' END",
                 orderSql:  "MIN(f.chokyo_sp) DESC" },
  ex_overall:  { alias: 'EX指数全体帯',
                 groupSql: "CASE WHEN f.ex_overall IS NULL THEN '—' WHEN f.ex_overall < 0 THEN '<0' WHEN f.ex_overall < 20 THEN '0~20' WHEN f.ex_overall < 50 THEN '20~50' WHEN f.ex_overall < 100 THEN '50~100' ELSE '100~' END",
                 orderSql: "MIN(COALESCE(f.ex_overall, -99999))", selectSql: "" },
  ex_course:   { alias: 'EX指数コース帯',
                 groupSql: "CASE WHEN f.ex_course IS NULL THEN '—' WHEN f.ex_course < 0 THEN '<0' WHEN f.ex_course < 20 THEN '0~20' WHEN f.ex_course < 50 THEN '20~50' WHEN f.ex_course < 100 THEN '50~100' ELSE '100~' END",
                 orderSql: "MIN(COALESCE(f.ex_course, -99999))", selectSql: "" },
  honmei_overall: { alias: '本命指数全体帯',
                 groupSql: "CASE WHEN f.honmei_overall IS NULL THEN '—' WHEN f.honmei_overall < 0 THEN '<0' WHEN f.honmei_overall < 15 THEN '0~15' WHEN f.honmei_overall < 30 THEN '15~30' WHEN f.honmei_overall < 50 THEN '30~50' ELSE '50~' END",
                 orderSql: "MIN(COALESCE(f.honmei_overall, -99999))", selectSql: "" },
  honmei_course:  { alias: '本命指数コース帯',
                 groupSql: "CASE WHEN f.honmei_course IS NULL THEN '—' WHEN f.honmei_course < 0 THEN '<0' WHEN f.honmei_course < 15 THEN '0~15' WHEN f.honmei_course < 30 THEN '15~30' WHEN f.honmei_course < 50 THEN '30~50' ELSE '50~' END",
                 orderSql: "MIN(COALESCE(f.honmei_course, -99999))", selectSql: "" },
  tenkai:      { alias: '展開指数帯',
                 groupSql: "CASE WHEN f.tenkai_score IS NULL THEN '—' WHEN f.tenkai_score < 0 THEN '<0' WHEN f.tenkai_score < 15 THEN '0~15' WHEN f.tenkai_score < 25 THEN '15~25' ELSE '25~' END",
                 orderSql: "MIN(COALESCE(f.tenkai_score, -99999))", selectSql: "" },
};
for (const key of Object.keys(AGGREGATE_MAP_FACT)) {
  const e = AGGREGATE_MAP_FACT[key];
  if (!e.selectSql) e.selectSql = e.groupSql;
}

let factTableReady = false;
async function initFactTableStatus(): Promise<void> {
  try {
    const [rows] = await pool.query<any>('SELECT COUNT(*) AS c FROM T_ANALYZE_FACT');
    factTableReady = Number((rows as any[])[0].c) > 0;
    if (factTableReady) console.log('分析ファクトテーブル: 利用可能');
  } catch { factTableReady = false; }
}

app.post('/api/analyze', async (req, res) => {
  const {
    ymd_from, ymd_to, course, tds, distance_from, distance_to, class: cls,
    odds_from, odds_to, odds_rank_from, odds_rank_to,
    wakuban_from, wakuban_to, umaban_from, umaban_to,
    info_from, info_to, goal_from, goal_to,
    idm_mark_from, idm_mark_to, idm_idx_from, idm_idx_to,
    kyusha_idx_from, kyusha_idx_to,
    first_from, first_to, latter_from, latter_to,
    oikiri_from, oikiri_to, shiage_from, shiage_to,
    chokyo_sp_from, chokyo_sp_to,
    ex_overall_from, ex_overall_to,
    ex_course_from, ex_course_to,
    honmei_overall_from, honmei_overall_to,
    honmei_course_from, honmei_course_to,
    tenkai_from, tenkai_to,
    kishu, trainer, umanushi,
    aggregate_01, aggregate_02, aggregate_03,
  } = req.body as Record<string, string>;

  // ── ファクトテーブル高速パス ──────────────────────────────────────────────
  if (factTableReady) {
    const aggKeys = [aggregate_01, aggregate_02, aggregate_03]
      .filter(k => k && AGGREGATE_MAP_FACT[k]);
    const params: (string | number)[] = [];

    const selectParts = aggKeys.map((k, i) =>
      `(${AGGREGATE_MAP_FACT[k].selectSql}) AS \`agg_key_${i + 1}\``
    );
    selectParts.push(`
      COUNT(*)                                                         AS total_heads,
      SUM(f.order_of_finish = 1)                                       AS first_number,
      SUM(f.order_of_finish = 2)                                       AS second_number,
      SUM(f.order_of_finish = 3)                                       AS third_number,
      SUM(f.order_of_finish >= 4)                                      AS also_ran,
      ROUND(SUM(f.order_of_finish = 1) / COUNT(*) * 100, 1)           AS first_rate,
      ROUND((SUM(f.order_of_finish = 1)
            +SUM(f.order_of_finish = 2)) / COUNT(*) * 100, 1)         AS second_rate,
      ROUND((SUM(f.order_of_finish = 1)
            +SUM(f.order_of_finish = 2)
            +SUM(f.order_of_finish = 3)) / COUNT(*) * 100, 1)         AS third_rate,
      ROUND(COALESCE(SUM(f.win_pay),   0) / COUNT(*), 1)              AS win_recovery_rate,
      ROUND(COALESCE(SUM(f.place_pay), 0) / COUNT(*), 1)              AS place_recovery_rate
    `);

    let sql = `SELECT ${selectParts.join(',\n')}
      FROM T_ANALYZE_FACT f
      WHERE 1=1
    `;

    if (ymd_from && ymd_to)           { sql += ' AND f.ymd BETWEEN ? AND ?';            params.push(ymd_from, ymd_to); }
    if (course && course !== '00')    { sql += ' AND f.course_code = ?';                params.push(course); }
    if (tds && tds !== '00')          { sql += ' AND f.tds_code = ?';                   params.push(tds); }
    else                              { sql += " AND f.tds_code IN ('1','2')"; }
    if (distance_from && distance_to) { sql += ' AND f.distance BETWEEN ? AND ?';       params.push(distance_from, distance_to); }
    if (cls && cls !== '00')          { sql += ' AND f.class_code = ?';                 params.push(cls); }
    else                              { sql += " AND f.class_code <> 'A1'"; }

    if (odds_from && odds_to)             { sql += ' AND f.kijun_odds BETWEEN ? AND ?';        params.push(odds_from, odds_to); }
    if (odds_rank_from && odds_rank_to)   { sql += ' AND f.kijun_ninki BETWEEN ? AND ?';       params.push(odds_rank_from, odds_rank_to); }
    if (wakuban_from && wakuban_to)       { sql += ' AND f.waku_num BETWEEN ? AND ?';          params.push(wakuban_from, wakuban_to); }
    if (umaban_from && umaban_to)         { sql += ' AND f.uma_num BETWEEN ? AND ?';           params.push(umaban_from, umaban_to); }
    if (info_from && info_to)             { sql += ' AND f.in_joho BETWEEN ? AND ?';           params.push(info_from, info_to); }
    if (goal_from && goal_to)             { sql += ' AND f.goal_juni BETWEEN ? AND ?';         params.push(goal_from, goal_to); }
    if (idm_mark_from && idm_mark_to)     { sql += ' AND f.in_idm BETWEEN ? AND ?';            params.push(idm_mark_from, idm_mark_to); }
    if (idm_idx_from && idm_idx_to)       { sql += ' AND f.idm BETWEEN ? AND ?';               params.push(idm_idx_from, idm_idx_to); }
    if (kyusha_idx_from && kyusha_idx_to) { sql += ' AND f.kyusha_index BETWEEN ? AND ?';     params.push(kyusha_idx_from, kyusha_idx_to); }
    if (first_from && first_to)           { sql += ' AND f.ten_index_juni BETWEEN ? AND ?';    params.push(first_from, first_to); }
    if (latter_from && latter_to)         { sql += ' AND f.agari_index_juni BETWEEN ? AND ?';  params.push(latter_from, latter_to); }
    if (oikiri_from && oikiri_to)         { sql += ' AND f.oi_index BETWEEN ? AND ?';          params.push(oikiri_from, oikiri_to); }
    if (shiage_from && shiage_to)         { sql += ' AND f.shiage_index BETWEEN ? AND ?';      params.push(shiage_from, shiage_to); }
    if (ex_overall_from && ex_overall_to) { sql += ' AND f.ex_overall BETWEEN ? AND ?';       params.push(ex_overall_from, ex_overall_to); }
    if (ex_course_from  && ex_course_to)  { sql += ' AND f.ex_course BETWEEN ? AND ?';        params.push(ex_course_from, ex_course_to); }
    if (honmei_overall_from && honmei_overall_to) { sql += ' AND f.honmei_overall BETWEEN ? AND ?'; params.push(honmei_overall_from, honmei_overall_to); }
    if (honmei_course_from  && honmei_course_to)  { sql += ' AND f.honmei_course BETWEEN ? AND ?';  params.push(honmei_course_from, honmei_course_to); }
    if (tenkai_from && tenkai_to)         { sql += ' AND f.tenkai_score BETWEEN ? AND ?';      params.push(tenkai_from, tenkai_to); }
    if (chokyo_sp_from && chokyo_sp_to) {
      const gr = (g: string) => g === 'A' ? 1 : g === 'B' ? 2 : g === 'C' ? 3 : g === 'D' ? 4 : g === 'E' ? 5 : null;
      const sf = gr(chokyo_sp_from), st = gr(chokyo_sp_to);
      if (sf !== null && st !== null) {
        sql += ` AND CASE WHEN f.chokyo_sp >= 4 THEN 1 WHEN f.chokyo_sp >= 2 THEN 2 WHEN f.chokyo_sp >= -1 THEN 3 WHEN f.chokyo_sp >= -4 THEN 4 WHEN f.chokyo_sp IS NOT NULL THEN 5 END BETWEEN ? AND ?`;
        params.push(Math.min(sf, st), Math.max(sf, st));
      }
    }
    if (kishu?.trim())    { sql += ' AND f.kishu_name    LIKE ?'; params.push(`${kishu.trim()}%`); }
    if (trainer?.trim())  { sql += ' AND f.trainer_name  LIKE ?'; params.push(`${trainer.trim()}%`); }
    if (umanushi?.trim()) { sql += ' AND f.umanushi_name LIKE ?'; params.push(`%${umanushi.trim()}%`); }

    if (aggKeys.length > 0) {
      sql += ' GROUP BY ' + aggKeys.map(k => AGGREGATE_MAP_FACT[k].groupSql).join(', ');
      sql += ' ORDER BY ' + aggKeys.map(k => AGGREGATE_MAP_FACT[k].orderSql ?? AGGREGATE_MAP_FACT[k].groupSql).join(', ');
    }
    sql += ' LIMIT 2000';

    try {
      const _t0 = Date.now();
      const [rows] = await pool.query<any>(sql, params);
      const _ms = Date.now() - _t0;
      const aggLabels = aggKeys.map((k, i) => ({ key: `agg_key_${i + 1}`, label: AGGREGATE_MAP_FACT[k].alias }));
      res.json({ aggLabels, rows, _debug: { ms: _ms, usedFact: true } });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
    return;
  }

  // ── フォールバック: 3テーブルJOIN ───────────────────────────────────────

  // 集計キーをホワイトリストで検証
  const aggKeys = [aggregate_01, aggregate_02, aggregate_03]
    .filter(k => k && AGGREGATE_MAP[k]);

  const params: (string | number)[] = [];

  // 集計キーの SELECT 句
  const selectParts = aggKeys.map((k, i) => {
    const alias = `agg_key_${i + 1}`;
    return `(${AGGREGATE_MAP[k].selectSql}) AS \`${alias}\``;
  });

  // 集計統計 — t_sed を直接 INNER JOIN して inline で評価
  // ※ 派生サブクエリ(sedDerived)は全行マテリアライズを起こして低速になるため使わない
  selectParts.push(`
    COUNT(*)                                                                    AS total_heads,
    SUM(CAST(TRIM(fin.order_of_finish) AS UNSIGNED) = 1)                       AS first_number,
    SUM(CAST(TRIM(fin.order_of_finish) AS UNSIGNED) = 2)                       AS second_number,
    SUM(CAST(TRIM(fin.order_of_finish) AS UNSIGNED) = 3)                       AS third_number,
    SUM(CAST(TRIM(fin.order_of_finish) AS UNSIGNED) >= 4)                      AS also_ran,
    ROUND(SUM(CAST(TRIM(fin.order_of_finish) AS UNSIGNED) = 1) / COUNT(*) * 100, 1) AS first_rate,
    ROUND((SUM(CAST(TRIM(fin.order_of_finish) AS UNSIGNED) = 1)
          +SUM(CAST(TRIM(fin.order_of_finish) AS UNSIGNED) = 2)) / COUNT(*) * 100, 1) AS second_rate,
    ROUND((SUM(CAST(TRIM(fin.order_of_finish) AS UNSIGNED) = 1)
          +SUM(CAST(TRIM(fin.order_of_finish) AS UNSIGNED) = 2)
          +SUM(CAST(TRIM(fin.order_of_finish) AS UNSIGNED) = 3)) / COUNT(*) * 100, 1) AS third_rate,
    ROUND(COALESCE(SUM(CAST(TRIM(fin.win)   AS UNSIGNED)), 0) / COUNT(*), 1)   AS win_recovery_rate,
    ROUND(COALESCE(SUM(CAST(TRIM(fin.place) AS UNSIGNED)), 0) / COUNT(*), 1)   AS place_recovery_rate
  `);

  // 日付範囲あり → STRAIGHT_JOIN で idx_bac_ymd を先頭ドライバーに固定
  // 日付範囲なし → STRAIGHT_JOIN 外してオプティマイザに t_kyi 関数インデックスを使わせる
  const hint = (ymd_from && ymd_to) ? 'STRAIGHT_JOIN' : '';

  // 調教SP CTE — chokyo_sp 集計またはフィルター使用時のみ生成
  const needsSpCte = aggKeys.includes('chokyo_sp') || (chokyo_sp_from && chokyo_sp_to);
  const cteParams: (string | number)[] = [];
  let ctePrefix = '';
  if (needsSpCte) {
    // 日付フィルターがあれば CTE 内でも絞り込む（全スキャン防止）
    const cteDateJoin = (ymd_from && ymd_to)
      ? `INNER JOIN t_bac b2 ON b2.course_code=k2.course_code AND b2.year_code=k2.year_code AND b2.kai=k2.kai AND b2.day_code=k2.day_code AND b2.race_num=k2.race_num AND b2.ymd BETWEEN ? AND ?`
      : '';
    if (ymd_from && ymd_to) cteParams.push(ymd_from, ymd_to);

    ctePrefix = `WITH sp_raw AS (
  SELECT k2.course_code, k2.year_code, k2.kai, k2.day_code, k2.race_num, k2.uma_num,
    CAST(c2.oi_index    AS DECIMAL(6,1)) AS oi_val,
    CAST(c2.shiage_index AS DECIMAL(6,1)) AS shi_val,
    TRIM(k2.chokyo_yajirushi) AS yj,
    TRIM(k2.hohbokusaki_rank) AS hb,
    SUM(CASE WHEN CAST(c2.oi_index    AS DECIMAL(6,1)) > 0 THEN 1 ELSE 0 END) OVER w AS oi_cnt,
    SUM(CASE WHEN CAST(c2.shiage_index AS DECIMAL(6,1)) > 0 THEN 1 ELSE 0 END) OVER w AS shi_cnt,
    RANK() OVER (PARTITION BY k2.course_code,k2.year_code,k2.kai,k2.day_code,k2.race_num
                 ORDER BY CASE WHEN CAST(c2.oi_index AS DECIMAL(6,1)) > 0 THEN CAST(c2.oi_index AS DECIMAL(6,1)) END DESC) AS oi_rank,
    RANK() OVER (PARTITION BY k2.course_code,k2.year_code,k2.kai,k2.day_code,k2.race_num
                 ORDER BY CASE WHEN CAST(c2.shiage_index AS DECIMAL(6,1)) > 0 THEN CAST(c2.shiage_index AS DECIMAL(6,1)) END DESC) AS shi_rank,
    AVG(CASE WHEN CAST(c2.oi_index    AS DECIMAL(6,1)) > 0 THEN CAST(c2.oi_index    AS DECIMAL(6,1)) END) OVER w AS oi_avg,
    STDDEV_POP(CASE WHEN CAST(c2.oi_index AS DECIMAL(6,1)) > 0 THEN CAST(c2.oi_index AS DECIMAL(6,1)) END) OVER w AS oi_sd,
    AVG(CASE WHEN CAST(c2.shiage_index AS DECIMAL(6,1)) > 0 THEN CAST(c2.shiage_index AS DECIMAL(6,1)) END) OVER w AS shi_avg,
    STDDEV_POP(CASE WHEN CAST(c2.shiage_index AS DECIMAL(6,1)) > 0 THEN CAST(c2.shiage_index AS DECIMAL(6,1)) END) OVER w AS shi_sd
  FROM T_KYI k2
  LEFT JOIN T_CYB c2 ON c2.course_code=k2.course_code AND c2.year_code=k2.year_code
    AND c2.kai=k2.kai AND c2.day_code=k2.day_code AND c2.race_num=k2.race_num AND c2.uma_num=k2.uma_num
  ${cteDateJoin}
  WINDOW w AS (PARTITION BY k2.course_code,k2.year_code,k2.kai,k2.day_code,k2.race_num)
),
sp_cte AS (
  SELECT course_code, year_code, kai, day_code, race_num, uma_num,
    CASE
      WHEN oi_cnt < 2 OR shi_cnt < 2 OR oi_val IS NULL OR oi_val <= 0 OR shi_val IS NULL OR shi_val <= 0 THEN NULL
      ELSE
        (CASE oi_rank WHEN 1 THEN 3 WHEN 2 THEN 2 WHEN 3 THEN 1 ELSE 0 END)
       +(CASE shi_rank WHEN 1 THEN 3 WHEN 2 THEN 2 WHEN 3 THEN 1 ELSE 0 END)
       +LEAST(0, ROUND((
           CASE WHEN oi_sd  > 0 THEN (oi_val  - oi_avg)  / oi_sd  ELSE 0 END
          +CASE WHEN shi_sd > 0 THEN (shi_val - shi_avg) / shi_sd ELSE 0 END
         ) * 1.0, 0))
       +(CASE yj WHEN '4' THEN -2 WHEN '5' THEN -4 ELSE 0 END)
       +(CASE hb WHEN 'E' THEN -4 WHEN 'D' THEN -2 ELSE 0 END)
    END AS sp_score
  FROM sp_raw
)
`;
  }

  // 使用する機能に応じて JOIN を選択的に追加（不要な JOIN は省いてパフォーマンスを守る）
  const needsCyb = aggKeys.some(k => k === 'oikiri' || k === 'shiage')
    || !!(oikiri_from && oikiri_to)
    || !!(shiage_from && shiage_to);

  const needsAns = aggKeys.some(k => k === 'ex_overall' || k === 'ex_course')
    || !!(ex_overall_from && ex_overall_to)
    || !!(ex_course_from  && ex_course_to);

  const needsHms = aggKeys.some(k => k === 'honmei_overall' || k === 'honmei_course')
    || !!(honmei_overall_from && honmei_overall_to)
    || !!(honmei_course_from  && honmei_course_to);

  const needsPfs = aggKeys.includes('tenkai')
    || !!(tenkai_from && tenkai_to);

  const cybJoin = needsCyb
    ? `LEFT JOIN t_cyb c
      ON  k.course_code = c.course_code AND k.year_code = c.year_code
      AND k.kai = c.kai AND k.day_code = c.day_code
      AND k.race_num = c.race_num AND k.uma_num = c.uma_num`
    : '';

  const ansJoin = needsAns
    ? `LEFT JOIN T_ANABA_SCORE ans
      ON  k.course_code = ans.course_code AND k.year_code = ans.year_code
      AND k.kai = ans.kai AND k.day_code = ans.day_code
      AND k.race_num = ans.race_num AND k.uma_num = ans.uma_num`
    : '';

  const hmsJoin = needsHms
    ? `LEFT JOIN T_HONMEI_SCORE hms
      ON  k.course_code = hms.course_code AND k.year_code = hms.year_code
      AND k.kai = hms.kai AND k.day_code = hms.day_code
      AND k.race_num = hms.race_num AND k.uma_num = hms.uma_num`
    : '';

  const pfsJoin = needsPfs
    ? `LEFT JOIN T_PACEFIT_SCORE pfs
      ON  k.course_code = pfs.course_code AND k.year_code = pfs.year_code
      AND k.kai = pfs.kai AND k.day_code = pfs.day_code
      AND k.race_num = pfs.race_num AND k.uma_num = pfs.uma_num`
    : '';

  const spCteJoin = needsSpCte
    ? `LEFT JOIN sp_cte ON sp_cte.course_code=k.course_code AND sp_cte.year_code=k.year_code
      AND sp_cte.kai=k.kai AND sp_cte.day_code=k.day_code AND sp_cte.race_num=k.race_num AND sp_cte.uma_num=k.uma_num`
    : '';

  let sql = `SELECT ${hint} ${selectParts.join(',\n')}
    FROM t_bac b
    INNER JOIN t_kyi k
      ON  b.course_code = k.course_code AND b.year_code = k.year_code
      AND b.kai = k.kai AND b.day_code = k.day_code AND b.race_num = k.race_num
    INNER JOIN t_sed fin
      ON  k.course_code = fin.course_code AND k.year_code = fin.year_code
      AND k.kai = fin.kai AND k.day_code = fin.day_code
      AND k.race_num = fin.race_num AND k.uma_num = fin.umaban
      AND fin.ijou_kubun IN ('0','')
    ${cybJoin}
    ${ansJoin}
    ${hmsJoin}
    ${pfsJoin}
    ${spCteJoin}
    WHERE 1=1
  `;

  // 条件句（Conditions） — ymd を最初に置くことで idx_bac_ymd を最優先で使わせる
  if (ymd_from && ymd_to)         { sql += ' AND b.ymd BETWEEN ? AND ?';       params.push(ymd_from, ymd_to); }
  if (course && course !== '00')  { sql += ' AND b.course_code = ?';           params.push(course); }
  if (tds && tds !== '00')        { sql += ' AND b.tds_code = ?';              params.push(tds); }
  else                            { sql += " AND b.tds_code IN ('1','2')"; }
  if (distance_from && distance_to) { sql += ' AND b.distance BETWEEN ? AND ?'; params.push(distance_from, distance_to); }
  if (cls && cls !== '00')        { sql += ' AND b.`class` = ?';               params.push(cls); }
  else                            { sql += " AND b.`class` <> 'A1'"; }

  // 条件句（Targets）— CAST型は関数インデックスの式と完全一致させること
  if (odds_from && odds_to)         { sql += ' AND CAST(k.kijun_odds     AS DECIMAL(7,1)) BETWEEN ? AND ?'; params.push(odds_from, odds_to); }
  if (odds_rank_from && odds_rank_to){ sql += ' AND CAST(k.kijun_ninki   AS UNSIGNED)     BETWEEN ? AND ?'; params.push(odds_rank_from, odds_rank_to); }
  if (wakuban_from && wakuban_to)   { sql += ' AND CAST(k.waku_num       AS UNSIGNED)     BETWEEN ? AND ?'; params.push(wakuban_from, wakuban_to); }
  if (umaban_from && umaban_to)     { sql += ' AND CAST(k.uma_num        AS UNSIGNED)     BETWEEN ? AND ?'; params.push(umaban_from, umaban_to); }
  if (info_from && info_to)         { sql += ' AND CAST(k.in_joho        AS UNSIGNED)     BETWEEN ? AND ?'; params.push(info_from, info_to); }
  if (goal_from && goal_to)         { sql += ' AND CAST(k.goal_juni      AS UNSIGNED)     BETWEEN ? AND ?'; params.push(goal_from, goal_to); }
  if (idm_mark_from && idm_mark_to) { sql += ' AND CAST(k.in_idm         AS UNSIGNED)     BETWEEN ? AND ?'; params.push(idm_mark_from, idm_mark_to); }
  if (idm_idx_from && idm_idx_to)   { sql += ' AND CAST(k.idm            AS DECIMAL(6,1)) BETWEEN ? AND ?'; params.push(idm_idx_from, idm_idx_to); }
  if (kyusha_idx_from && kyusha_idx_to){ sql += ' AND CAST(k.kyusha_index AS DECIMAL(6,1)) BETWEEN ? AND ?'; params.push(kyusha_idx_from, kyusha_idx_to); }
  if (first_from && first_to)       { sql += ' AND CAST(k.ten_index_juni AS UNSIGNED)     BETWEEN ? AND ?'; params.push(first_from, first_to); }
  if (latter_from && latter_to)     { sql += ' AND CAST(k.agari_index_juni AS UNSIGNED)   BETWEEN ? AND ?'; params.push(latter_from, latter_to); }
  if (oikiri_from && oikiri_to)     { sql += ' AND CAST(c.oi_index       AS UNSIGNED)     BETWEEN ? AND ?'; params.push(oikiri_from, oikiri_to); }
  if (shiage_from && shiage_to)     { sql += ' AND CAST(c.shiage_index   AS UNSIGNED)     BETWEEN ? AND ?'; params.push(shiage_from, shiage_to); }
  if (ex_overall_from && ex_overall_to) { sql += ' AND CAST(ans.overall_score AS DECIMAL(7,1)) BETWEEN ? AND ?'; params.push(ex_overall_from, ex_overall_to); }
  if (ex_course_from  && ex_course_to)  { sql += ' AND CAST(ans.course_score  AS DECIMAL(7,1)) BETWEEN ? AND ?'; params.push(ex_course_from, ex_course_to); }
  if (honmei_overall_from && honmei_overall_to) { sql += ' AND CAST(hms.overall_score AS DECIMAL(7,1)) BETWEEN ? AND ?'; params.push(honmei_overall_from, honmei_overall_to); }
  if (honmei_course_from  && honmei_course_to)  { sql += ' AND CAST(hms.course_score  AS DECIMAL(7,1)) BETWEEN ? AND ?'; params.push(honmei_course_from, honmei_course_to); }
  if (tenkai_from && tenkai_to)         { sql += ' AND CAST(pfs.overall_score  AS DECIMAL(7,1)) BETWEEN ? AND ?'; params.push(tenkai_from, tenkai_to); }
  if (chokyo_sp_from && chokyo_sp_to) {
    const gr = (g: string) => g === 'A' ? 1 : g === 'B' ? 2 : g === 'C' ? 3 : g === 'D' ? 4 : g === 'E' ? 5 : null;
    const f = gr(chokyo_sp_from), t = gr(chokyo_sp_to);
    if (f !== null && t !== null) {
      sql += ` AND CASE WHEN sp_cte.sp_score >= 4 THEN 1 WHEN sp_cte.sp_score >= 2 THEN 2 WHEN sp_cte.sp_score >= -1 THEN 3 WHEN sp_cte.sp_score >= -4 THEN 4 WHEN sp_cte.sp_score IS NOT NULL THEN 5 END BETWEEN ? AND ?`;
      params.push(Math.min(f, t), Math.max(f, t));
    }
  }

  // 条件句（Targets human）— 騎手・調教師は前方一致、馬主は中間一致
  if (kishu?.trim())    { sql += ' AND k.kishu_name    LIKE ?'; params.push(`${kishu.trim()}%`); }
  if (trainer?.trim())  { sql += ' AND k.trainer_name  LIKE ?'; params.push(`${trainer.trim()}%`); }
  if (umanushi?.trim()) { sql += ' AND k.umanushi_name LIKE ?'; params.push(`%${umanushi.trim()}%`); }

  // GROUP BY
  if (aggKeys.length > 0) {
    sql += ' GROUP BY ' + aggKeys.map(k => AGGREGATE_MAP[k].groupSql).join(', ');
    sql += ' ORDER BY ' + aggKeys.map(k => AGGREGATE_MAP[k].orderSql ?? AGGREGATE_MAP[k].groupSql).join(', ');
  }

  sql += ' LIMIT 2000';

  try {
    const finalSql = ctePrefix ? ctePrefix + sql : sql;
    const allParams = [...cteParams, ...params];
    const _t0 = Date.now();
    const [rows] = await pool.query<any>(finalSql, allParams);
    const _ms = Date.now() - _t0;
    // レスポンスに集計キーのラベルを付与
    const aggLabels = aggKeys.map((k, i) => ({
      key: `agg_key_${i + 1}`,
      label: AGGREGATE_MAP[k].alias,
    }));
    res.json({
      aggLabels, rows,
      _debug: { ms: _ms, needsAns, needsPfs, needsSpCte, sql: finalSql.slice(0, 2000) },
    });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// ────────────────────────────────────────────────────────────────────────────
// 名前サジェスト: GET /api/suggest?type=kishu|trainer|umanushi&q=<前方一致>
app.get('/api/suggest', async (req, res) => {
  const { type, q } = req.query as { type?: string; q?: string };
  if (!q || q.trim().length < 1) { res.json([]); return; }

  const colMap: Record<string, string> = {
    kishu:    'kishu_name',
    trainer:  'trainer_name',
    umanushi: 'umanushi_name',
  };
  const col = colMap[type ?? ''];
  if (!col) { res.status(400).json({ error: '不正なtype' }); return; }

  const isUmanushi = (type === 'umanushi');
  const pattern = isUmanushi ? `%${q.trim()}%` : `${q.trim()}%`;
  const [rows] = await pool.query<any>(
    `SELECT DISTINCT TRIM(\`${col}\`) AS name
     FROM T_KYI
     WHERE \`${col}\` LIKE ?
     ORDER BY name
     LIMIT 20`,
    [pattern]
  );
  res.json((rows as any[]).map((r: any) => r.name));
});


// ────────────────────────────────────────────────────────────────────────────
// コース別傾向API
// ────────────────────────────────────────────────────────────────────────────

// コース一覧: GET /api/courses
app.get('/api/courses', async (_req, res) => {
  const [rows] = await pool.query<any>(
    `SELECT course_code, tds_code, distance, total_count
     FROM T_COURSE_FACTOR_AGG
     WHERE factor_type='baseline' AND total_count >= 100
     ORDER BY course_code, tds_code, CAST(distance AS UNSIGNED)`
  );
  res.json(rows);
});

// コース分析: GET /api/course-analysis?course_code=05&tds_code=1&distance=1600
app.get('/api/course-analysis', async (req, res) => {
  const { course_code, tds_code, distance } = req.query as Record<string, string>;
  if (!course_code || !tds_code || !distance) {
    res.status(400).json({ error: 'course_code, tds_code, distance は必須です' });
    return;
  }
  const [rows] = await pool.query<any>(
    `SELECT factor_type, factor_value, total_count, win_count, renso_count, place_count,
            win_rate, renso_rate, place_rate, win_recovery, place_recovery
     FROM T_COURSE_FACTOR_AGG
     WHERE course_code=? AND tds_code=? AND distance=?
     ORDER BY factor_type, factor_value`,
    [course_code, tds_code, distance.padStart(4, ' ')]
  );
  // distance は TRIM済みなのでそのまま試す
  const data = (rows as any[]).length ? rows : await (async () => {
    const [r2] = await pool.query<any>(
      `SELECT factor_type, factor_value, total_count, win_count, place_count,
              win_rate, place_rate, win_recovery, place_recovery
       FROM T_COURSE_FACTOR_AGG
       WHERE course_code=? AND tds_code=? AND TRIM(distance)=?
       ORDER BY factor_type, factor_value`,
      [course_code, tds_code, distance.trim()]
    );
    return r2;
  })();
  if (!(data as any[]).length) { res.status(404).json({ error: 'データが見つかりません' }); return; }
  // factor_type 別に整理
  const result: Record<string, any[]> = {};
  for (const row of (data as any[])) {
    if (!result[row.factor_type]) result[row.factor_type] = [];
    result[row.factor_type].push(row);
  }
  res.json({ course_code, tds_code, distance: distance.trim(), factors: result });
});

// ────────────────────────────────────────────────────────────────────────────
// 注目馬複合シグナル(sc)の算出: entries.htmlのevaluateRaceSignals()と同一ロジック。
// /api/watchlist・指数帯別回収率(sc)の両方から呼ばれる共通実装（ロジックの重複を避ける）。
// 出典: document/分析レポート/注目馬複合シグナル回収率分析レポート.md
//       document/分析レポート/注目馬複合シグナル_walk-forward検証レポート.md（sc≥6の単勝回収率妥当性を確認）
// ────────────────────────────────────────────────────────────────────────────
interface NotableScRow {
  uma_num: string;
  kijun_odds: any; honmei_course: any; ex_course: any; joho_index: any; idm: any;
  goal_juni: any; ten_index_juni: any; agari_index_juni: any;
  kyakushitsu: any; chokyo_yajirushi: any; oi_index: any; in_idm: any;
  combo_place_rr: any; combo_n: any; kyusha_anaba_place_rr: any; kyusha_anaba_n: any;
  ten_index: any; agari_index: any; kijun_ninki: any;
}

// 2026-10-04追加シグナル（entries.html の evaluateRaceSignals() と同じ定義・しきい値）
// しきい値は 2025年までのデータでの「上位20%の境目」。検証: python/research/sc_gap_wf.py
export const SC_TOP_MIN = 9;   // ウォッチリスト「sc上位」のしきい値（2026-10-05）
export const SC_TEN_LEAD_MIN = 5.7;    // テン指数1位で、2位との差がこれ以上 → +4
export const SC_AGARI_LEAD_MIN = 5.3;  // 上がり指数1位で、2位との差がこれ以上 → +1
export const SC_NINKI_GAP_MIN = 3;     // 人気順位 − IDM順位 がこれ以上 → +2

// レース内で1位の馬だけに「2位との差」を返す（同値1位が複数なら差0）。それ以外・値なしは NaN
function leadMap(vals: number[]): number[] {
  const valid = vals.filter(v => !isNaN(v)).sort((a, b) => b - a);
  if (valid.length < 2) return vals.map(() => NaN);
  const top = valid[0], second = valid[1];
  return vals.map(v => (!isNaN(v) && v === top) ? top - second : NaN);
}

// 穴妙味指数グレード: entries.htmlのanabaMyomiGrade()と同一ロジック
// IDM印なし×基準オッズ15〜30倍で、EX指数(コース)≧100→A、50〜100→B。詳細: document/指数/【廃】穴妙味指数_仕様書.md
function anabaMyomiGrade(anaba: number, inIdm: any, odds: number): 'A' | 'B' | null {
  if (isNaN(anaba) || String(inIdm ?? '').trim() !== '') return null;
  if (isNaN(odds) || odds < 15 || odds > 30) return null;
  if (anaba >= 100) return 'A';
  if (anaba >= 50) return 'B';
  return null;
}

function computeNotableScMap(raceRows: NotableScRow[]): Map<string, number> {
  const horses = raceRows.map(r => {
    const odds = r.kijun_odds === null ? NaN : Number(r.kijun_odds);
    const isHonmei = !isNaN(odds) && odds > 0 && odds < 10;
    const isAnaba = !isNaN(odds) && odds >= 10;
    const honmei = r.honmei_course === null ? NaN : Number(r.honmei_course);
    const anaba = r.ex_course === null ? NaN : Number(r.ex_course);
    const johoRawV = r.joho_index === null ? NaN : Math.trunc(Number(r.joho_index));
    const joho = (isNaN(johoRawV) || johoRawV === -1) ? null : johoRawV;
    const idm = Number(r.idm) || 0;
    const goalJuniV = r.goal_juni === null ? NaN : Number(r.goal_juni);
    const goalJuni = isNaN(goalJuniV) ? 99 : goalJuniV;
    const agariJuniV = r.agari_index_juni === null ? NaN : Number(r.agari_index_juni);
    const agariJuni = isNaN(agariJuniV) ? 99 : agariJuniV;
    const tenJuniV = r.ten_index_juni === null ? NaN : Number(r.ten_index_juni);
    const tenJuni = isNaN(tenJuniV) ? 99 : tenJuniV;
    const style = String(r.kyakushitsu ?? '').trim();
    const yaji = String(r.chokyo_yajirushi ?? '').trim();
    const oiIdx = Number(r.oi_index) || 0;
    const comboPlaceRr = Number(r.combo_place_rr) || 0;
    const comboN = Number(r.combo_n) || 0;
    const kyushaRr = Number(r.kyusha_anaba_place_rr) || 0;
    const kyushaN = Number(r.kyusha_anaba_n) || 0;
    const num = (v: any) => { const s = String(v ?? '').trim(); return s === '' ? NaN : Number(s); };
    const tenIdx = num(r.ten_index);
    const agariIdx = num(r.agari_index);
    const idmV = num(r.idm);
    const ninki = num(r.kijun_ninki);
    return { r, odds, isHonmei, isAnaba, honmei, anaba, joho, idm, goalJuni, agariJuni, tenJuni, style, yaji, oiIdx, comboPlaceRr, comboN, kyushaRr, kyushaN, tenIdx, agariIdx, idmV, ninki };
  });
  const tenLead = leadMap(horses.map(h => h.tenIdx));
  const agariLead = leadMap(horses.map(h => h.agariIdx));
  // IDM のレース内順位（大きい順。同値は同順位＝最小の順位）
  const idmRank = horses.map(h => isNaN(h.idmV) ? NaN : 1 + horses.filter(o => !isNaN(o.idmV) && o.idmV > h.idmV).length);

  const escCnt = horses.filter(h => h.style === '1').length;
  const senCnt = horses.filter(h => h.style === '2').length;
  const frontCnt = escCnt + senCnt;
  const n = horses.length;
  const fastPace = frontCnt >= Math.ceil(n * 0.38);
  const slowPace = escCnt <= 1 && senCnt <= 1;

  const oiSorted = horses.filter(h => h.oiIdx > 0).map(h => h.oiIdx).sort((a, b) => b - a);
  const oiRankOf = (h: typeof horses[number]) => {
    if (h.oiIdx <= 0) return 99;
    const i = oiSorted.indexOf(h.oiIdx);
    return i === -1 ? 99 : i + 1;
  };
  const oiTop25Cutoff = Math.ceil(oiSorted.length * 0.25);

  const validIdms = horses.map(h => h.idm).filter(v => v > 0).sort((a, b) => a - b);
  const idmMedian = validIdms.length > 0 ? validIdms[Math.floor(validIdms.length / 2)] : 0;
  const validGoalCnt = horses.filter(h => h.goalJuni < 90).length;

  const result = new Map<string, number>();
  for (const h of horses) {
    let sc = 0;
    const hasIdxSignal = (h.isHonmei && !isNaN(h.honmei) && h.honmei >= 10) || (h.isAnaba && !isNaN(h.anaba) && h.anaba >= 15);
    const hasAbilityProxy =
      (h.goalJuni < 90 && validGoalCnt > 0 && h.goalJuni <= Math.ceil(validGoalCnt * 0.45)) ||
      (h.idm > 0 && h.idm >= idmMedian);
    const abilityOk = hasIdxSignal || hasAbilityProxy;

    if (h.isHonmei && !isNaN(h.honmei)) {
      if (h.honmei >= 50) sc += 3; else if (h.honmei >= 30) sc += 2; else if (h.honmei >= 10) sc += 1;
    }
    if (h.isAnaba && !isNaN(h.anaba)) {
      if (h.anaba >= 100) sc += 3; else if (h.anaba >= 50) sc += 2; else if (h.anaba >= 15) sc += 1;
    }
    // （穴妙味指数A/Bの加点は 2026-10-04 に削除。entries.html と同じ。詳細: document/指数/sc_注目馬複合シグナル_仕様書.md）
    if (abilityOk) {
      if (h.comboN >= 10 && h.comboPlaceRr >= 130) sc += 3;
      else if (h.comboN >= 7 && h.comboPlaceRr >= 110) sc += 2;
      else if (h.comboN >= 5 && h.comboPlaceRr >= 100) sc += 1;
    }
    if (abilityOk && h.isAnaba) {
      if (h.kyushaN >= 10 && h.kyushaRr >= 130) sc += 3;
      else if (h.kyushaN >= 7 && h.kyushaRr >= 110) sc += 2;
    }
    if (h.joho !== null) {
      const m = abilityOk ? 1 : 0.5;
      if (h.joho >= 7) sc += Math.round(3 * m); else if (h.joho >= 5) sc += Math.round(2 * m); else if (h.joho >= 3) sc += Math.round(1 * m);
      if (h.joho >= 5 && h.odds >= 5) sc += Math.round(2 * m);
    }
    if (abilityOk) {
      if (fastPace && (h.style === '3' || h.style === '4')) {
        if (h.agariJuni <= 2) sc += 2; else if (h.agariJuni <= 4) sc += 1;
      } else if (slowPace && (h.style === '1' || h.style === '2')) {
        if (h.tenJuni <= 2) sc += 2; else if (h.tenJuni <= 4) sc += 1;
      }
    }
    if (h.yaji === '4' || h.yaji === '5') {
      sc -= 2;
    } else if (abilityOk) {
      if (h.yaji === '1') sc += 2; else if (h.yaji === '2') sc += 1;
      const myOiRank = oiRankOf(h);
      if (oiTop25Cutoff > 0 && myOiRank <= oiTop25Cutoff) sc += 1;
    }
    if (abilityOk && h.goalJuni <= 2) sc += 1;

    // 2026-10-04追加: 指数の抜け・市場評価とのずれ（能力フロアに関係なく加点）
    const i = horses.indexOf(h);
    if (tenLead[i] >= SC_TEN_LEAD_MIN) sc += 4;
    if (agariLead[i] >= SC_AGARI_LEAD_MIN) sc += 1;
    if (!isNaN(h.ninki) && !isNaN(idmRank[i]) && h.ninki - idmRank[i] >= SC_NINKI_GAP_MIN) sc += 2;

    result.set(h.r.uma_num, sc);
  }
  return result;
}

// ────────────────────────────────────────────────────────────────────────────
// 指数帯別回収率API: EX指数帯・本命指数帯・厩指穴信頼グレード別の回収率集計
// ────────────────────────────────────────────────────────────────────────────

let factorRecoveryCache: { exIndex: any[]; honmeiIndex: any[]; kyushaTrust: any[]; evIndex: any[]; favoriteReliability: any[]; myomiGrade: any[]; updatedAt: string } | null = null;

// ── 1番人気信頼度（entries.htmlのcalcFavoriteReliabilityを移植）帯別の回収率集計 ──
// IDM・情報指数・展開・調教矢印・追切/仕上指数・テン/上がり指数順位はすべてレース前に判明する
// その場限りの値（過去実績の集計テーブルに依存しない）ため、先読みバイアスの心配がない。
interface FavoriteRow {
  uma_num: string; kijun_ninki: any; idm: any; joho_index: any; goal_juni: any;
  chokyo_yajirushi: any; oi_index: any; shiage_index: any; ten_index_juni: any; agari_index_juni: any;
}
function computeFavoriteGrade(rows: FavoriteRow[]): string | null {
  if (!rows || rows.length < 2) return null;
  const fav = rows.find(r => parseInt(String(r.kijun_ninki ?? '').trim()) === 1);
  if (!fav) return null;

  let score = 0;

  const idmVals = rows.map(r => { const v = parseFloat(String(r.idm ?? '').trim()); return (isNaN(v) || v === 0) ? null : v; });
  const favIdm = parseFloat(String(fav.idm ?? '').trim());
  if (!isNaN(favIdm) && favIdm !== 0) {
    const sorted = idmVals.filter((v): v is number => v !== null).sort((a, b) => b - a);
    const rank = sorted.indexOf(favIdm) + 1;
    const gap = (rank === 1 && sorted.length >= 2) ? favIdm - sorted[1] : 0;
    const pt = rank === 1 ? (gap >= 5 ? 40 : gap >= 3 ? 30 : gap >= 1 ? 20 : 10)
             : rank === 2 ? 0 : rank === 3 ? -10 : -20;
    score += pt;
  }

  const johoVals = rows.map(r => { const v = parseInt(String(r.joho_index ?? '').trim()); return (isNaN(v) || v === -1) ? null : v; });
  const favJoho = parseInt(String(fav.joho_index ?? '').trim());
  if (!isNaN(favJoho) && favJoho !== -1) {
    const sorted = johoVals.filter((v): v is number => v !== null).sort((a, b) => b - a);
    const rank = sorted.indexOf(favJoho) + 1;
    const pt = rank === 1 ? 20 : rank === 2 ? 5 : rank === 3 ? 0 : rank <= 5 ? -5 : -15;
    score += pt;
  }

  const goalVals = rows.map(r => { const v = parseInt(String(r.goal_juni ?? '').trim()); return (isNaN(v) || v === 0) ? null : v; });
  const favGoal = parseInt(String(fav.goal_juni ?? '').trim());
  if (!isNaN(favGoal) && favGoal > 0) {
    const sorted = goalVals.filter((v): v is number => v !== null).sort((a, b) => a - b);
    const rank = sorted.indexOf(favGoal) + 1;
    const pt = rank === 1 ? 15 : rank <= 3 ? 10 : rank <= 5 ? 5 : rank <= 7 ? 0 : -10;
    score += pt;
  }

  const yaji = String(fav.chokyo_yajirushi ?? '').trim();
  const yajiMap: Record<string, number> = { '1': 15, '2': 8, '3': 0, '4': -10, '5': -20 };
  if (yaji in yajiMap) score += yajiMap[yaji];

  const favIdx = rows.indexOf(fav);
  for (const field of ['oi_index', 'shiage_index'] as const) {
    const vals = rows.map(r => { const v = parseInt(String((r as any)[field] ?? '').trim()); return (isNaN(v) || v === 0) ? null : v; });
    const fv = vals[favIdx];
    if (fv === null) continue;
    const sorted = vals.filter((v): v is number => v !== null).sort((a, b) => b - a);
    const rank = sorted.indexOf(fv) + 1;
    const pt = rank === 1 ? 8 : rank <= 3 ? 3 : rank <= 5 ? 0 : -5;
    score += pt;
  }

  const ten = parseInt(String(fav.ten_index_juni ?? '').trim());
  const agari = parseInt(String(fav.agari_index_juni ?? '').trim());
  if (!isNaN(ten) && ten > 0) score += ten === 1 ? 5 : ten <= 3 ? 2 : ten >= 7 ? -3 : 0;
  if (!isNaN(agari) && agari > 0) score += agari === 1 ? 5 : agari <= 3 ? 2 : agari >= 7 ? -3 : 0;

  return score >= 70 ? 'S' : score >= 55 ? 'A' : score >= 25 ? 'B' : score >= 0 ? 'C' : score >= -20 ? 'D' : 'E';
}

async function computeFavoriteRecovery(): Promise<any[]> {
  const [rows] = await pool.query<any>(
    `SELECT k.course_code, k.year_code, k.kai, k.day_code, k.race_num, k.uma_num,
            k.kijun_ninki, k.idm, k.joho_index, k.goal_juni, k.chokyo_yajirushi,
            k.ten_index_juni, k.agari_index_juni,
            c.oi_index, c.shiage_index,
            s.order_of_finish, s.win AS win_pay, s.place AS place_pay, s.ijou_kubun
     FROM T_KYI k
     LEFT JOIN T_CYB c
       ON  c.course_code = k.course_code AND c.year_code = k.year_code
       AND c.kai = k.kai AND c.day_code = k.day_code AND c.race_num = k.race_num AND c.uma_num = k.uma_num
     JOIN T_SED s
       ON  s.course_code = k.course_code AND s.year_code = k.year_code
       AND s.kai = k.kai AND s.day_code = k.day_code AND s.race_num = k.race_num AND s.umaban = k.uma_num
     WHERE s.order_of_finish IS NOT NULL`
  );

  const raceGroups = new Map<string, any[]>();
  for (const r of rows as any[]) {
    const raceKey = `${r.course_code}_${r.year_code}_${r.kai}_${r.day_code}_${r.race_num}`;
    if (!raceGroups.has(raceKey)) raceGroups.set(raceKey, []);
    raceGroups.get(raceKey)!.push(r);
  }

  const gradeOrder = ['S', 'A', 'B', 'C', 'D', 'E'];
  type Bucket = { total: number; win: number; renso: number; place: number; winPay: number; placePay: number };
  const buckets = new Map<string, Bucket>();

  for (const raceRs of raceGroups.values()) {
    const grade = computeFavoriteGrade(raceRs as FavoriteRow[]);
    if (!grade) continue;
    const fav = raceRs.find(r => parseInt(String(r.kijun_ninki ?? '').trim()) === 1)!;
    const finish = parseInt(String(fav.order_of_finish ?? '').trim());
    if (isNaN(finish)) continue;
    const normal = fav.ijou_kubun === '0' || fav.ijou_kubun === '' || fav.ijou_kubun === null;
    const winPay = normal ? (Number(String(fav.win_pay ?? '').trim()) || 0) : 0;
    const placePay = normal ? (Number(String(fav.place_pay ?? '').trim()) || 0) : 0;
    const b = buckets.get(grade) ?? { total: 0, win: 0, renso: 0, place: 0, winPay: 0, placePay: 0 };
    b.total += 1;
    if (finish === 1) b.win += 1;
    if (finish <= 2) b.renso += 1;
    if (finish <= 3) b.place += 1;
    b.winPay += winPay;
    b.placePay += placePay;
    buckets.set(grade, b);
  }

  return gradeOrder
    .filter(g => buckets.has(g))
    .map(g => {
      const bk = buckets.get(g)!;
      return {
        band_key: g, band_label: g,
        total_count: bk.total,
        win_count: bk.win, renso_count: bk.renso, place_count: bk.place,
        win_rate: Math.round(bk.win / bk.total * 1000) / 10,
        renso_rate: Math.round(bk.renso / bk.total * 1000) / 10,
        place_rate: Math.round(bk.place / bk.total * 1000) / 10,
        win_recovery: Math.round(bk.winPay / bk.total * 10) / 10,
        place_recovery: Math.round(bk.placePay / bk.total * 10) / 10,
      };
    });
}

// ── 旧: sc(注目馬複合シグナル)帯別の回収率集計 ──
// 2026-09-27、この生集計はcombo/kyushaの現在値を過去全期間に遡って適用するため先読みバイアスを含むと判明。
// factor-recovery.htmlのsc欄は代わりに「注目馬複合シグナル_walk-forward検証レポート.md」の
// 検証済み数値（静的テーブル）を表示するように変更したため、本関数は現在未使用（削除はせず残置）。
async function computeScRecovery(): Promise<any[]> {
  const [rows] = await pool.query<any>(
    `SELECT k.course_code, k.year_code, k.kai, k.day_code, k.race_num, k.uma_num,
            k.kijun_odds, k.kijun_ninki, k.joho_index, k.idm, k.goal_juni, k.ten_index_juni, k.agari_index_juni,
            k.ten_index, k.agari_index,
            k.kyakushitsu, k.chokyo_yajirushi, k.in_idm,
            c.oi_index,
            cr.place_recovery AS combo_place_rr, cr.total_count AS combo_n,
            kya.anaba_place_rr AS kyusha_anaba_place_rr, kya.anaba_n AS kyusha_anaba_n,
            ans.course_score AS ex_course,
            hms.course_score AS honmei_course,
            s.order_of_finish, s.win AS win_pay, s.place AS place_pay, s.ijou_kubun
     FROM T_KYI k
     JOIN T_BAC b
       ON  b.course_code = k.course_code AND b.year_code = k.year_code
       AND b.kai = k.kai AND b.day_code = k.day_code AND b.race_num = k.race_num
     LEFT JOIN T_CYB c
       ON  c.course_code = k.course_code AND c.year_code = k.year_code
       AND c.kai = k.kai AND c.day_code = k.day_code AND c.race_num = k.race_num AND c.uma_num = k.uma_num
     LEFT JOIN T_COMBO_RECOVERY cr
       ON  cr.kishu_code = k.kishu_code AND cr.trainer_code = k.trainer_code
     LEFT JOIN (
       SELECT trainer_code,
              ROUND(SUM(place_payout_sum) / SUM(total_count), 1) AS anaba_place_rr,
              SUM(total_count)                                    AS anaba_n
       FROM T_KYUSHA_FACTOR_AGG
       WHERE factor_type = 'kyusha_idx_x_odds' AND factor_value = 'plus_15~'
       GROUP BY trainer_code
     ) kya ON kya.trainer_code = k.trainer_code
     LEFT JOIN T_ANABA_SCORE ans
       ON  ans.course_code = k.course_code AND ans.year_code = k.year_code
       AND ans.kai = k.kai AND ans.day_code = k.day_code AND ans.race_num = k.race_num AND ans.uma_num = k.uma_num
     LEFT JOIN T_HONMEI_SCORE hms
       ON  hms.course_code = k.course_code AND hms.year_code = k.year_code
       AND hms.kai = k.kai AND hms.day_code = k.day_code AND hms.race_num = k.race_num AND hms.uma_num = k.uma_num
     JOIN T_SED s
       ON  s.course_code = k.course_code AND s.year_code = k.year_code
       AND s.kai = k.kai AND s.day_code = k.day_code AND s.race_num = k.race_num AND s.umaban = k.uma_num
     WHERE s.order_of_finish IS NOT NULL`
  );

  const raceGroups = new Map<string, any[]>();
  for (const r of rows as any[]) {
    const raceKey = `${r.course_code}_${r.year_code}_${r.kai}_${r.day_code}_${r.race_num}`;
    if (!raceGroups.has(raceKey)) raceGroups.set(raceKey, []);
    raceGroups.get(raceKey)!.push(r);
  }

  const bands: { key: string; label: string; test: (sc: number) => boolean }[] = [
    { key: '1', label: '2以下',              test: sc => sc <= 2 },
    { key: '2', label: '3〜5',               test: sc => sc >= 3 && sc <= 5 },
    { key: '3', label: '6〜7(採用帯)',        test: sc => sc >= 6 && sc <= 7 },
    { key: '4', label: '8以上',               test: sc => sc >= 8 },
  ];
  type Bucket = { total: number; win: number; renso: number; place: number; winPay: number; placePay: number };
  const buckets = new Map<string, Bucket>();

  for (const raceRs of raceGroups.values()) {
    const scMap = computeNotableScMap(raceRs as NotableScRow[]);
    for (const r of raceRs) {
      const sc = scMap.get(r.uma_num) ?? 0;
      const band = bands.find(b => b.test(sc));
      if (!band) continue;
      const finish = parseInt(String(r.order_of_finish ?? '').trim());
      if (isNaN(finish)) continue;
      const normal = r.ijou_kubun === '0' || r.ijou_kubun === '' || r.ijou_kubun === null;
      const winPay = normal ? (Number(r.win_pay) || 0) : 0;
      const placePay = normal ? (Number(r.place_pay) || 0) : 0;
      const b = buckets.get(band.key) ?? { total: 0, win: 0, renso: 0, place: 0, winPay: 0, placePay: 0 };
      b.total += 1;
      if (finish === 1) b.win += 1;
      if (finish <= 2) b.renso += 1;
      if (finish <= 3) b.place += 1;
      b.winPay += winPay;
      b.placePay += placePay;
      buckets.set(band.key, b);
    }
  }

  return bands
    .filter(b => buckets.has(b.key))
    .map(b => {
      const bk = buckets.get(b.key)!;
      return {
        band_key: b.key, band_label: b.label,
        total_count: bk.total,
        win_count: bk.win, renso_count: bk.renso, place_count: bk.place,
        win_rate:   Math.round(bk.win   / bk.total * 1000) / 10,
        renso_rate: Math.round(bk.renso / bk.total * 1000) / 10,
        place_rate: Math.round(bk.place / bk.total * 1000) / 10,
        win_recovery:   Math.round(bk.winPay   / bk.total * 10) / 10,
        place_recovery: Math.round(bk.placePay / bk.total * 10) / 10,
      };
    });
}

async function computeFactorRecovery() {
  const rateSelect = `
    COUNT(*) AS total_count,
    SUM(win_flag)    AS win_count,
    SUM(renso_flag)  AS renso_count,
    SUM(place_flag)  AS place_count,
    ROUND(SUM(win_flag)   / COUNT(*) * 100, 1) AS win_rate,
    ROUND(SUM(renso_flag) / COUNT(*) * 100, 1) AS renso_rate,
    ROUND(SUM(place_flag) / COUNT(*) * 100, 1) AS place_rate,
    ROUND(SUM(win_pay)   / COUNT(*), 1) AS win_recovery,
    ROUND(SUM(place_pay) / COUNT(*), 1) AS place_recovery
  `;

  // ── EX指数帯（穴馬指数・基準オッズ≧10倍の馬のみ対象）──
  const [exRows] = await pool.query<any>(
    `SELECT band_key, band_label, ${rateSelect}
     FROM (
       SELECT
         CASE
           WHEN ex_course < 0    THEN '1'
           WHEN ex_course < 15   THEN '2'
           WHEN ex_course < 50   THEN '3'
           WHEN ex_course < 100  THEN '4'
           ELSE '5'
         END AS band_key,
         CASE
           WHEN ex_course < 0    THEN '0未満'
           WHEN ex_course < 15   THEN '0〜15'
           WHEN ex_course < 50   THEN '15〜50'
           WHEN ex_course < 100  THEN '50〜100'
           ELSE '100以上'
         END AS band_label,
         (order_of_finish = 1)      AS win_flag,
         (order_of_finish <= 2)     AS renso_flag,
         (order_of_finish <= 3)     AS place_flag,
         COALESCE(win_pay, 0)   AS win_pay,
         COALESCE(place_pay, 0) AS place_pay
       FROM T_ANALYZE_FACT
       WHERE ex_course IS NOT NULL AND kijun_odds >= 10.0 AND order_of_finish IS NOT NULL
     ) t
     GROUP BY band_key, band_label
     ORDER BY band_key`
  );

  // ── 本命指数帯（基準オッズ＜10倍の馬のみ対象）──
  const [honmeiRows] = await pool.query<any>(
    `SELECT band_key, band_label, ${rateSelect}
     FROM (
       SELECT
         CASE
           WHEN honmei_course < 0   THEN '1'
           WHEN honmei_course < 10  THEN '2'
           WHEN honmei_course < 30  THEN '3'
           WHEN honmei_course < 50  THEN '4'
           ELSE '5'
         END AS band_key,
         CASE
           WHEN honmei_course < 0   THEN '0未満'
           WHEN honmei_course < 10  THEN '0〜10'
           WHEN honmei_course < 30  THEN '10〜30'
           WHEN honmei_course < 50  THEN '30〜50'
           ELSE '50以上'
         END AS band_label,
         (order_of_finish = 1)      AS win_flag,
         (order_of_finish <= 2)     AS renso_flag,
         (order_of_finish <= 3)     AS place_flag,
         COALESCE(win_pay, 0)   AS win_pay,
         COALESCE(place_pay, 0) AS place_pay
       FROM T_ANALYZE_FACT
       WHERE honmei_course IS NOT NULL AND kijun_odds > 0 AND kijun_odds < 10.0 AND order_of_finish IS NOT NULL
     ) t
     GROUP BY band_key, band_label
     ORDER BY band_key`
  );

  // ── 厩指穴信頼グレード（厩舎指数≧0×基準オッズ≧15倍セグメントでの厩舎別信頼度）──
  // 1) 厩舎ごとに当該セグメントの成績を集計 → 2) 複勝回収率でグレード判定 → 3) グレードごとに再集計
  const [kyushaRows] = await pool.query<any>(
    `WITH trainer_stats AS (
       SELECT trainer_code,
              COUNT(*) AS n,
              SUM(finish_order = '01')                    AS win_flag,
              SUM(finish_order IN ('01','02'))             AS renso_flag,
              SUM(finish_order IN ('01','02','03'))        AS place_flag,
              SUM(CASE WHEN ijou_kubun IN ('0','') THEN COALESCE(win_payout,0)   ELSE 0 END) AS win_pay,
              SUM(CASE WHEN ijou_kubun IN ('0','') THEN COALESCE(place_payout,0) ELSE 0 END) AS place_pay
       FROM T_KYUSHA_RACE_LOG
       WHERE kyusha_index >= 0 AND kijun_odds >= 15
       GROUP BY trainer_code
     ),
     graded AS (
       SELECT *,
         CASE
           WHEN n < 20 THEN NULL
           WHEN (place_pay / n) >= 130 THEN 'S'
           WHEN (place_pay / n) >= 110 THEN 'A'
           WHEN (place_pay / n) >= 100 THEN 'B'
           WHEN (place_pay / n) >= 90  THEN 'C'
           WHEN (place_pay / n) >= 80  THEN 'D'
           WHEN (place_pay / n) >= 60  THEN 'E'
           ELSE 'F'
         END AS grade
       FROM trainer_stats
     )
     SELECT grade AS band_key, grade AS band_label,
            COUNT(*)      AS trainer_count,
            SUM(n)        AS total_count,
            SUM(win_flag)   AS win_count,
            SUM(renso_flag) AS renso_count,
            SUM(place_flag) AS place_count,
            ROUND(SUM(win_flag)   / SUM(n) * 100, 1) AS win_rate,
            ROUND(SUM(renso_flag) / SUM(n) * 100, 1) AS renso_rate,
            ROUND(SUM(place_flag) / SUM(n) * 100, 1) AS place_rate,
            ROUND(SUM(win_pay)   / SUM(n), 1) AS win_recovery,
            ROUND(SUM(place_pay) / SUM(n), 1) AS place_recovery
     FROM graded
     WHERE grade IS NOT NULL
     GROUP BY grade
     ORDER BY FIELD(grade, 'S','A','B','C','D','E','F')`
  );

  // ── 期待値指数帯（T_EV_SCORE.ev_index、entries.htmlのevScoreBgと同じ閾値）──
  // オッズ帯別isotonic較正・センチネル除外済みのため先読みバイアスの懸念なし
  let evIndexRows: any[] = [];
  try {
  [evIndexRows] = await pool.query<any>(
    `SELECT band_key, band_label, ${rateSelect}
     FROM (
       SELECT
         CASE
           WHEN ev.ev_index < -50 THEN '1'
           WHEN ev.ev_index < -5  THEN '2'
           WHEN ev.ev_index < 20  THEN '3'
           ELSE '4'
         END AS band_key,
         CASE
           WHEN ev.ev_index < -50 THEN '-50未満'
           WHEN ev.ev_index < -5  THEN '-50〜-5'
           WHEN ev.ev_index < 20  THEN '-5〜20'
           ELSE '20以上'
         END AS band_label,
         (CAST(s.order_of_finish AS UNSIGNED) = 1)  AS win_flag,
         (CAST(s.order_of_finish AS UNSIGNED) <= 2) AS renso_flag,
         (CAST(s.order_of_finish AS UNSIGNED) <= 3) AS place_flag,
         CASE WHEN s.ijou_kubun IN ('0','') THEN COALESCE(CAST(TRIM(s.win)   AS UNSIGNED), 0) ELSE 0 END AS win_pay,
         CASE WHEN s.ijou_kubun IN ('0','') THEN COALESCE(CAST(TRIM(s.place) AS UNSIGNED), 0) ELSE 0 END AS place_pay
       FROM T_EV_SCORE ev
       JOIN T_SED s
         ON  s.course_code=ev.course_code AND s.year_code=ev.year_code AND s.kai=ev.kai
         AND s.day_code=ev.day_code AND s.race_num=ev.race_num AND s.umaban=ev.uma_num
       WHERE ev.ev_index IS NOT NULL AND s.order_of_finish IS NOT NULL
     ) t
     GROUP BY band_key, band_label
     ORDER BY band_key`
  );
  } catch { /* T_EV_SCORE 未構築の場合は空配列のまま */ }

  // ── 1番人気信頼度グレード別（entries.htmlの本命信頼度バッジと同じ計算式）──
  // 全フィールドがレース前公表値のみで構成されており、過去集計テーブルに依存しないため先読みバイアスなし
  let favoriteReliabilityRows: any[] = [];
  try { favoriteReliabilityRows = await computeFavoriteRecovery(); }
  catch { /* 元テーブル未構築等の場合は空配列のまま */ }

  // ── 穴妙味指数グレード別（entries.html列#25と同じ定義: course_score≧100→A, 50-100→B）──
  // T_ANABA_SCORE.course_score × T_KYI.in_idm IS NULL × 基準オッズ15-30倍のセグメント限定
  let myomiRows: any[] = [];
  try {
  [myomiRows] = await pool.query<any>(
    `SELECT band_key, band_label, ${rateSelect}
     FROM (
       SELECT
         CASE WHEN a.course_score>=100 THEN 'A' ELSE 'B' END AS band_key,
         CASE WHEN a.course_score>=100 THEN 'A' ELSE 'B' END AS band_label,
         (CAST(s.order_of_finish AS UNSIGNED) = 1)  AS win_flag,
         (CAST(s.order_of_finish AS UNSIGNED) <= 2) AS renso_flag,
         (CAST(s.order_of_finish AS UNSIGNED) <= 3) AS place_flag,
         CASE WHEN s.ijou_kubun IN ('0','') THEN COALESCE(CAST(TRIM(s.win)   AS UNSIGNED), 0) ELSE 0 END AS win_pay,
         CASE WHEN s.ijou_kubun IN ('0','') THEN COALESCE(CAST(TRIM(s.place) AS UNSIGNED), 0) ELSE 0 END AS place_pay
       FROM T_ANABA_SCORE a
       JOIN T_KYI k ON k.course_code=a.course_code AND k.year_code=a.year_code AND k.kai=a.kai
         AND k.day_code=a.day_code AND k.race_num=a.race_num AND k.uma_num=a.uma_num
       JOIN T_SED s ON s.course_code=a.course_code AND s.year_code=a.year_code AND s.kai=a.kai
         AND s.day_code=a.day_code AND s.race_num=a.race_num AND s.umaban=a.uma_num
       WHERE a.course_score>=50 AND k.in_idm IS NULL AND s.order_of_finish IS NOT NULL
         AND TRIM(k.kijun_odds)<>'' AND CAST(TRIM(k.kijun_odds) AS DECIMAL(6,1)) BETWEEN 15 AND 30
     ) t
     GROUP BY band_key, band_label
     ORDER BY band_key`
  );
  } catch { /* T_ANABA_SCORE 未構築の場合は空配列のまま */ }

  return {
    exIndex: exRows as any[],
    honmeiIndex: honmeiRows as any[],
    kyushaTrust: kyushaRows as any[],
    evIndex: evIndexRows as any[],
    favoriteReliability: favoriteReliabilityRows,
    myomiGrade: myomiRows as any[],
    updatedAt: new Date().toISOString(),
  };
}

// GET /api/factor-recovery: キャッシュがあれば即返す（初回のみDB集計、数秒かかる）
app.get('/api/factor-recovery', async (_req, res) => {
  if (!factorRecoveryCache) {
    factorRecoveryCache = await computeFactorRecovery();
  }
  res.json(factorRecoveryCache);
});

// POST /api/factor-recovery/refresh: 明示的に再集計（新データ取込後に押す想定）
app.post('/api/factor-recovery/refresh', async (_req, res) => {
  factorRecoveryCache = await computeFactorRecovery();
  trainerGradeCache = null; // ウォッチリストの厩指穴信頼グレードも合わせて再計算させる
  res.json(factorRecoveryCache);
});

// ────────────────────────────────────────────────────────────────────────────
// ウォッチリスト: 指定開催日で「一番人気以外の本命指数(コース)50以上」「EX指数(コース)50以上」
// 「厩指穴信頼ランクS〜C」のいずれかに該当する馬を抽出する
// ────────────────────────────────────────────────────────────────────────────

let trainerGradeCache: Record<string, string> | null = null;

async function getTrainerGradeMap(): Promise<Record<string, string>> {
  if (trainerGradeCache) return trainerGradeCache;
  const [rows] = await pool.query<any>(
    `WITH trainer_stats AS (
       SELECT trainer_code,
              COUNT(*) AS n,
              SUM(CASE WHEN ijou_kubun IN ('0','') THEN COALESCE(place_payout,0) ELSE 0 END) AS place_pay
       FROM T_KYUSHA_RACE_LOG
       WHERE kyusha_index >= 0 AND kijun_odds >= 15
       GROUP BY trainer_code
     )
     SELECT trainer_code,
       CASE
         WHEN (place_pay / n) >= 130 THEN 'S'
         WHEN (place_pay / n) >= 110 THEN 'A'
         WHEN (place_pay / n) >= 100 THEN 'B'
         WHEN (place_pay / n) >= 90  THEN 'C'
         WHEN (place_pay / n) >= 80  THEN 'D'
         WHEN (place_pay / n) >= 60  THEN 'E'
         ELSE 'F'
       END AS grade
     FROM trainer_stats
     WHERE n >= 20`
  );
  const map: Record<string, string> = {};
  for (const r of rows as any[]) map[r.trainer_code] = r.grade;
  trainerGradeCache = map;
  return map;
}

// GET /api/watchlist?ymd=YYYYMMDD
app.get('/api/watchlist', async (req, res) => {
  const { ymd } = req.query as Record<string, string>;
  if (!ymd || !/^\d{8}$/.test(ymd)) {
    res.status(400).json({ error: 'ymd は YYYYMMDD 形式で指定してください' });
    return;
  }

  const gradeMap = await getTrainerGradeMap();

  const [rows] = await pool.query<any>(
    `SELECT b.course_code, b.year_code, b.kai, b.day_code, b.race_num,
            b.race_name, b.race_name_9char, b.start_time, b.distance, b.tds_code, b.heads, b.grade AS race_grade,
            k.uma_num, k.waku_num, k.uma_name, k.kishu_name, k.trainer_name, k.trainer_code,
            k.kijun_odds, k.kijun_ninki, k.kyusha_index,
            k.joho_index, k.idm, k.goal_juni, k.ten_index_juni, k.agari_index_juni,
            k.ten_index, k.agari_index,
            k.kyakushitsu, k.chokyo_yajirushi, k.in_idm,
            c.oi_index, c.shiage_index,
            cr.place_recovery AS combo_place_rr, cr.total_count AS combo_n,
            kya.anaba_place_rr AS kyusha_anaba_place_rr, kya.anaba_n AS kyusha_anaba_n,
            ans.course_score  AS ex_course,
            ans.overall_score AS ex_overall,
            hms.course_score  AS honmei_course,
            hms.overall_score AS honmei_overall,
            s.order_of_finish, s.win AS win_pay, s.place AS place_pay, s.ijou_kubun
     FROM T_BAC b
     JOIN T_KYI k
       ON  k.course_code = b.course_code AND k.year_code = b.year_code
       AND k.kai = b.kai AND k.day_code = b.day_code AND k.race_num = b.race_num
     LEFT JOIN T_CYB c
       ON  c.course_code = k.course_code AND c.year_code = k.year_code
       AND c.kai = k.kai AND c.day_code = k.day_code
       AND c.race_num = k.race_num AND c.uma_num = k.uma_num
     LEFT JOIN T_COMBO_RECOVERY cr
       ON  cr.kishu_code   = k.kishu_code
       AND cr.trainer_code = k.trainer_code
     LEFT JOIN (
       SELECT trainer_code,
              ROUND(SUM(place_payout_sum) / SUM(total_count), 1) AS anaba_place_rr,
              SUM(total_count)                                    AS anaba_n
       FROM T_KYUSHA_FACTOR_AGG
       WHERE factor_type = 'kyusha_idx_x_odds'
         AND factor_value = 'plus_15~'
       GROUP BY trainer_code
     ) kya ON kya.trainer_code = k.trainer_code
     LEFT JOIN T_ANABA_SCORE ans
       ON  ans.course_code = k.course_code AND ans.year_code = k.year_code
       AND ans.kai = k.kai AND ans.day_code = k.day_code
       AND ans.race_num = k.race_num AND ans.uma_num = k.uma_num
     LEFT JOIN T_HONMEI_SCORE hms
       ON  hms.course_code = k.course_code AND hms.year_code = k.year_code
       AND hms.kai = k.kai AND hms.day_code = k.day_code
       AND hms.race_num = k.race_num AND hms.uma_num = k.uma_num
     LEFT JOIN T_SED s
       ON  s.course_code = k.course_code AND s.year_code = k.year_code
       AND s.kai = k.kai AND s.day_code = k.day_code
       AND s.race_num = k.race_num AND s.umaban = k.uma_num
     WHERE b.ymd = ?
       AND b.tds_code <> '3'        -- 障害戦: EX指数/本命指数が構造的に未計算（芝ダ限定パイプライン）
       AND b.\`class\` <> 'A1'      -- 新馬戦: 過去走なしで指数の予測力が消失（回収率検証済み）
     ORDER BY CAST(b.course_code AS UNSIGNED), CAST(b.race_num AS UNSIGNED), CAST(k.uma_num AS UNSIGNED)`,
    [ymd]
  );

  // 情報指数のレース内順位（denseRank・降順）を先に算出する。0/NULL/-1(非開示)は対象外。
  // entries.html の denseRanks() と同じロジック（複勝妙味シグナルの情報印1〜2位判定に使用）。
  const johoValsByRace = new Map<string, Set<number>>();
  for (const r of rows as any[]) {
    const raceKey = `${r.course_code}_${r.kai}_${r.day_code}_${r.race_num}`;
    const v = r.joho_index === null ? NaN : Number(r.joho_index);
    if (!isNaN(v) && v !== 0 && v !== -1) {
      if (!johoValsByRace.has(raceKey)) johoValsByRace.set(raceKey, new Set());
      johoValsByRace.get(raceKey)!.add(v);
    }
  }
  const johoRankLookup = new Map<string, Map<number, number>>();
  for (const [raceKey, valSet] of johoValsByRace) {
    const uniqueVals = [...valSet].sort((a, b) => b - a);
    const rankMap = new Map<number, number>();
    uniqueVals.forEach((v, i) => rankMap.set(v, i + 1));
    johoRankLookup.set(raceKey, rankMap);
  }

  // ── 注目馬複合シグナル(sc): computeNotableScMap()（entries.htmlのevaluateRaceSignals()と同一ロジック）を
  //    レース単位で呼び出す。出典: document/分析レポート/注目馬複合シグナル_walk-forward検証レポート.md
  const notableScByKey = new Map<string, number>();
  {
    const raceRows = new Map<string, any[]>();
    for (const r of rows as any[]) {
      const raceKey = `${r.course_code}_${r.kai}_${r.day_code}_${r.race_num}`;
      if (!raceRows.has(raceKey)) raceRows.set(raceKey, []);
      raceRows.get(raceKey)!.push(r);
    }
    for (const [raceKey, raceRs] of raceRows) {
      const scMap = computeNotableScMap(raceRs as NotableScRow[]);
      for (const [umaNum, sc] of scMap) notableScByKey.set(`${raceKey}_${umaNum}`, sc);
    }
  }

  const result = (rows as any[])
    .map(r => {
      const honmei = r.honmei_course === null ? null : Number(r.honmei_course);
      const ex = r.ex_course === null ? null : Number(r.ex_course);
      const ninki = r.kijun_ninki === null ? null : Number(r.kijun_ninki);
      const odds = r.kijun_odds === null ? null : Number(r.kijun_odds);
      const kyushaIndex = r.kyusha_index === null ? null : Number(r.kyusha_index);

      // 本命指数はオッズ<10倍、EX指数はオッズ≧10倍の馬にのみ意味を持つ（entries.htmlのisHonmei/isAnabaと同じゲート）
      const isHonmei = odds !== null && odds > 0 && odds < 10;
      const isAnaba = odds !== null && odds >= 10;
      // 本命指数(コース)≧50×非1番人気トリガー
      // 2026-09-27、無効化。walk-forward検証（学習2020-2023/検証2024-2026）で単勝回収率75.4%→76.9%→
      // 81.7%と3年間すべて100%を大きく下回ったまま安定して低空飛行と判明（複勝回収率も77.2〜81.8%）。
      // EX指数・厩指穴信頼・ブリンカー指数（2026-10-05廃止）と同型の「全期間集計では良さそうでも真のholdoutで崩壊」パターン。
      // 変数・APIフィールドは残置。
      const matchHonmei = false;
      // EX指数(コース)≧100トリガー
      // 2026-09-27、無効化。旧コメントは「2026-09-06確認・複勝100.1%」としていたが、その後の正式な
      // walk-forward検証（学習2020-2023/検証2024-2026）でこの帯は実測76.4%まで崩壊すると判明済み
      // （CLAUDE.md「指数/スコアETL実装時の必須チェック」4番）。矛盾したまま放置され、以前実際に
      // このトリガーで実損失が出た事故があった。変数・APIフィールドは残置。
      const matchEx = false;

      // 厩指穴信頼グレードS〜Bトリガー
      // 2026-09-27、無効化。ホールドアウト検証でグレード順序自体が崩壊（Bグレードの実測がC/D/Eより
      // 低い）と既に判明済みだったにもかかわらずトリガーが生きたままだった。entries.html側は
      // 同日「穴妙味指数」に置き換え済み。変数・APIフィールドは残置。
      const inKyushaSegment = odds !== null && odds >= 15 && kyushaIndex !== null && kyushaIndex >= 0;
      const kyushaGrade = inKyushaSegment ? (gradeMap[r.trainer_code] ?? null) : null;
      const matchKyusha = false;

      // ── 複勝妙味シグナル（複勝sc≥3 × 基準オッズ15〜30倍）───────────────
      // 2026-10-04: 旧称「複勝回収率100%超シグナル」。先読みなしの検証で100%超は成り立たなかったため改称し、EX指数のしきい値を新方式の指数に合わせて 15/50→35/125 に変更（本命指数 10/30 は据え置き）。根拠: python/research/fukusho100_threshold_wf.py、document/指数/複勝妙味シグナル_仕様書.md
      // entries.html と同一ロジック・しきい値（変数名・APIフィールド名 match_fukusho100 は互換のため据え置き）
      const exOverall = r.ex_overall === null ? null : Number(r.ex_overall);
      const honmeiOverall = r.honmei_overall === null ? null : Number(r.honmei_overall);
      const comboRr = r.combo_place_rr === null ? null : Number(r.combo_place_rr);
      const comboN = r.combo_n === null ? 0 : Number(r.combo_n);
      const oiIdx = r.oi_index === null ? 0 : Number(r.oi_index);
      const shiageIdx = r.shiage_index === null ? 0 : Number(r.shiage_index);
      const goalJuni = r.goal_juni === null ? NaN : Number(r.goal_juni);
      const tenJuni = r.ten_index_juni === null ? NaN : Number(r.ten_index_juni);
      const agariJuni = r.agari_index_juni === null ? NaN : Number(r.agari_index_juni);
      const johoRaw = r.joho_index === null ? NaN : Number(r.joho_index);
      const raceKey = `${r.course_code}_${r.kai}_${r.day_code}_${r.race_num}`;
      const johoRank = (!isNaN(johoRaw) && johoRaw !== 0 && johoRaw !== -1)
        ? (johoRankLookup.get(raceKey)?.get(johoRaw) ?? null) : null;

      const scIdx = ((exOverall !== null && exOverall >= 35) || (honmeiOverall !== null && honmeiOverall >= 10)) ? 1 : 0;
      const scIdxStrong = ((exOverall !== null && exOverall >= 125) || (honmeiOverall !== null && honmeiOverall >= 30)) ? 1 : 0;
      const scCombo = (comboN >= 30 && comboRr !== null && comboRr >= 100) ? 1 : 0;
      const scChokyo = (oiIdx >= 70 || shiageIdx >= 70) ? 1 : 0;
      const scGoal = (!isNaN(goalJuni) && (goalJuni === 1 || goalJuni === 2)) ? 1 : 0;
      const scJoho = (johoRank !== null && (johoRank === 1 || johoRank === 2)) ? 1 : 0;
      const scTa = (tenJuni === 1 || agariJuni === 1) ? 1 : 0;
      const fukushoSc = scIdx + scIdxStrong + scCombo + scChokyo + scGoal + scJoho + scTa;
      const matchFukusho100 = fukushoSc >= 3 && odds !== null && odds >= 15 && odds < 30;

      // 注目馬複合シグナル(sc≥6)トリガー
      // 2026-10-04、無効化（ユーザー判断）。旧根拠「4期間すべて単勝100%超」は EX指数・本命指数が全期間集計
      // （先読みあり）のままの検証だった。先読みをすべて除き毎年直前年まで集計し直した検証では sc≥6 の単勝は
      // 同オッズ帯平均と同じ（76.5% vs 76.5%）。scの値自体は「注目sc」列の表示用に引き続き返す。
      // 詳細: document/指数/sc_注目馬複合シグナル_仕様書.md
      const notableSc = notableScByKey.get(`${raceKey}_${r.uma_num}`) ?? 0;
      const matchNotable = false;

      // sc上位（sc≥9）トリガー: 2026-10-05 追加（ユーザー判断）。sc は出馬表の列#8・推奨買い目と同じ値。
      // 先読みなしの検証（2022〜2026、新馬除外）で複勝91.8%（年別 97/90/90/91/90%）、同じオッズ帯の平均+13.9pt、
      // 単勝101.5%（払戻上位1%除外で79.5%＝高配当頼み）。年513頭・1開催日約5頭。根拠: document/指数/sc_注目馬複合シグナル_仕様書.md
      const matchScTop = notableSc >= SC_TOP_MIN;

      // 穴妙味指数A/B（entries.htmlのanabaMyomiGrade()と同一ロジック）
      // 2026-10-05、ユーザー判断で廃止（false固定）。先読みを除くと A 単勝82.5% / B 73.1% で同オッズ帯平均（77.4%）並み。
      // 変数・APIフィールドは残置。詳細: document/指数/【廃】穴妙味指数_仕様書.md
      const myomiGrade = anabaMyomiGrade(ex ?? NaN, r.in_idm, odds ?? NaN);
      const matchMyomi = false;

      if (!matchHonmei && !matchEx && !matchKyusha && !matchFukusho100 && !matchNotable && !matchMyomi && !matchScTop) return null;

      return {
        course_code: r.course_code, year_code: r.year_code, kai: r.kai, day_code: r.day_code, race_num: r.race_num,
        race_name: r.race_name, race_name_9char: r.race_name_9char, start_time: r.start_time,
        distance: r.distance, tds_code: r.tds_code, heads: r.heads, race_grade: r.race_grade,
        uma_num: r.uma_num, waku_num: r.waku_num, uma_name: r.uma_name,
        kishu_name: r.kishu_name, trainer_name: r.trainer_name,
        kijun_odds: r.kijun_odds, kijun_ninki: r.kijun_ninki,
        ex_course: ex, honmei_course: honmei, kyusha_grade: kyushaGrade,
        match_honmei: matchHonmei, match_ex: matchEx, match_kyusha: matchKyusha,
        match_fukusho100: matchFukusho100, fukusho_sc: fukushoSc,
        match_notable: matchNotable, notable_sc: notableSc, match_sc_top: matchScTop,
        match_myomi: matchMyomi, myomi_grade: myomiGrade,
        order_of_finish: r.order_of_finish, win_pay: r.win_pay, place_pay: r.place_pay, ijou_kubun: r.ijou_kubun,
      };
    })
    .filter((r): r is NonNullable<typeof r> => r !== null);

  res.json({ ymd, rows: result });
});

// ────────────────────────────────────────────────────────────────────────────
// 穴馬指数 ETL: POST /api/anaba-etl
// anaba_index.sql を4パートに分割して順次実行。SSEで進捗を返す。
// ────────────────────────────────────────────────────────────────────────────
app.post('/api/anaba-etl', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const send = (msg: string, extra?: object) =>
    res.write(`data: ${JSON.stringify({ message: msg, ...extra })}\n\n`);

  if (etlLocks.anaba) {
    send('エラー: EX指数ETLは既に実行中です。完了までお待ちください', { error: true, done: true });
    res.end(); return;
  }
  etlLocks.anaba = true;

  (async () => {
    try {
      if (!fs.existsSync(ANABA_SQL_FILE)) {
        send('エラー: sql/anaba_index.sql が見つかりません', { error: true, done: true });
        res.end(); return;
      }
      const sql = fs.readFileSync(ANABA_SQL_FILE, 'utf-8');
      const parts = splitSqlByParts(sql);

      for (let i = 0; i < parts.length; i++) {
        const partNum = i + 1;
        const label = PART_LABELS[partNum] ?? `Part${partNum}`;
        send(`[Part${partNum}] ${label} 開始...`);

        // Part 4 (指数計算) は長時間かかるためハートビートを定期送信
        let heartbeat: NodeJS.Timeout | undefined;
        if (partNum === 4) {
          let elapsed = 0;
          heartbeat = setInterval(() => {
            elapsed += 15;
            send(`[Part4] 指数計算中... (${elapsed}秒経過)`);
          }, 15_000);
        }

        try {
          await runMysqlSql(parts[i]);
          if (heartbeat) clearInterval(heartbeat);
          send(`[Part${partNum}] ${label} 完了`);
        } catch (err: any) {
          if (heartbeat) clearInterval(heartbeat);
          send(`[Part${partNum}] エラー: ${err.message}`, { error: true, done: true });
          res.end(); return;
        }
      }

      // 件数確認
      try {
        const [[row]] = await pool.query<any>(
          'SELECT COUNT(*) AS cnt FROM T_ANABA_SCORE'
        );
        send(`完了: T_ANABA_SCORE ${Number(row.cnt).toLocaleString()} 件`);
      } catch { /* 無視 */ }

      res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
      res.end();
    } finally {
      etlLocks.anaba = false;
    }
  })().catch((err) => {
    res.write(`data: ${JSON.stringify({ error: err.message, done: true })}\n\n`);
    res.end();
  });
});

// ────────────────────────────────────────────────────────────────────────────
// 本命指数 ETL: POST /api/honmei-etl
// honmei_index.sql を4パートに分割して順次実行。SSEで進捗を返す。
// ────────────────────────────────────────────────────────────────────────────
app.post('/api/honmei-etl', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const send = (msg: string, extra?: object) =>
    res.write(`data: ${JSON.stringify({ message: msg, ...extra })}\n\n`);

  if (etlLocks.honmei) {
    send('エラー: 本命指数ETLは既に実行中です。完了までお待ちください', { error: true, done: true });
    res.end(); return;
  }
  etlLocks.honmei = true;

  (async () => {
    try {
      if (!fs.existsSync(HONMEI_SQL_FILE)) {
        send('エラー: sql/honmei_index.sql が見つかりません', { error: true, done: true });
        res.end(); return;
      }
      const sql = fs.readFileSync(HONMEI_SQL_FILE, 'utf-8');
      const parts = splitSqlByParts(sql);

      for (let i = 0; i < parts.length; i++) {
        const partNum = i + 1;
        const label = HONMEI_PART_LABELS[partNum] ?? `Part${partNum}`;
        send(`[Part${partNum}] ${label} 開始...`);

        let heartbeat: NodeJS.Timeout | undefined;
        if (partNum === 4) {
          let elapsed = 0;
          heartbeat = setInterval(() => {
            elapsed += 15;
            send(`[Part4] 指数計算中... (${elapsed}秒経過)`);
          }, 15_000);
        }

        try {
          await runMysqlSql(parts[i]);
          if (heartbeat) clearInterval(heartbeat);
          send(`[Part${partNum}] ${label} 完了`);
        } catch (err: any) {
          if (heartbeat) clearInterval(heartbeat);
          send(`[Part${partNum}] エラー: ${err.message}`, { error: true, done: true });
          res.end(); return;
        }
      }

      try {
        const [[row]] = await pool.query<any>(
          'SELECT COUNT(*) AS cnt FROM T_HONMEI_SCORE'
        );
        send(`完了: T_HONMEI_SCORE ${Number(row.cnt).toLocaleString()} 件`);
      } catch { /* 無視 */ }

      res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
      res.end();
    } finally {
      etlLocks.honmei = false;
    }
  })().catch((err) => {
    res.write(`data: ${JSON.stringify({ error: err.message, done: true })}\n\n`);
    res.end();
  });
});

// ────────────────────────────────────────────────────────────────────────────
// EX指数・本命指数 まとめ更新: POST /api/anaba-honmei-etl
// 2026-09-27追加。両方とも推奨買い目・穴妙味指数(entries.html列#25)が日々内部参照するため、
// 個別更新を忘れると新しいレース日のスコアが丸ごと欠落する事故が発生した（同日発覚）。
// 個別に更新する必要のあるケースが実運用上ないため、1ボタンで両方を順に実行する形にまとめた。
// ────────────────────────────────────────────────────────────────────────────
app.post('/api/anaba-honmei-etl', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const send = (msg: string, extra?: object) =>
    res.write(`data: ${JSON.stringify({ message: msg, ...extra })}\n\n`);

  if (etlLocks.anaba || etlLocks.honmei) {
    send('エラー: EX指数・本命指数ETLは既に実行中です。完了までお待ちください', { error: true, done: true });
    res.end(); return;
  }
  etlLocks.anaba = true;
  etlLocks.honmei = true;

  const runOne = async (
    label: string, sqlFile: string, partLabels: Record<number, string>, countTable: string
  ): Promise<boolean> => {
    if (!fs.existsSync(sqlFile)) {
      send(`エラー: ${sqlFile} が見つかりません`, { error: true, done: true });
      res.end(); return false;
    }
    send(`=== ${label} 開始 ===`);
    const sql = fs.readFileSync(sqlFile, 'utf-8');
    const parts = splitSqlByParts(sql);

    for (let i = 0; i < parts.length; i++) {
      const partNum = i + 1;
      const partLabel = partLabels[partNum] ?? `Part${partNum}`;
      send(`[${label} Part${partNum}] ${partLabel} 開始...`);

      // 2026-09-27追加: 全パートで10秒毎にハートビートを送る。
      // Part2以降、無音のまま数十秒〜数分続くSSEストリームが、この環境のプロキシ/ポート
      // フォワーディングのアイドルタイムアウトに巻き込まれてサーバーごと再起動される事故が
      // 複数回連続で再現したため（Part4のみハートビートがあったのが原因）。
      let elapsed = 0;
      const heartbeat = setInterval(() => {
        elapsed += 10;
        send(`[${label} Part${partNum}] 実行中... (${elapsed}秒経過)`);
      }, 10_000);

      try {
        await runMysqlSql(parts[i]);
        clearInterval(heartbeat);
        send(`[${label} Part${partNum}] ${partLabel} 完了`);
      } catch (err: any) {
        clearInterval(heartbeat);
        send(`[${label} Part${partNum}] エラー: ${err.message}`, { error: true, done: true });
        res.end(); return false;
      }
    }

    try {
      const [[row]] = await pool.query<any>(`SELECT COUNT(*) AS cnt FROM ${countTable}`);
      send(`${label} 完了: ${countTable} ${Number(row.cnt).toLocaleString()} 件`);
    } catch { /* 無視 */ }
    return true;
  };

  (async () => {
    try {
      const okAnaba = await runOne('EX指数', ANABA_SQL_FILE, PART_LABELS, 'T_ANABA_SCORE');
      if (!okAnaba) return;
      const okHonmei = await runOne('本命指数', HONMEI_SQL_FILE, HONMEI_PART_LABELS, 'T_HONMEI_SCORE');
      if (!okHonmei) return;

      res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
      res.end();
    } finally {
      etlLocks.anaba = false;
      etlLocks.honmei = false;
    }
  })().catch((err) => {
    res.write(`data: ${JSON.stringify({ error: err.message, done: true })}\n\n`);
    res.end();
  });
});

// ────────────────────────────────────────────────────────────────────────────
// 展開シナリオ指数 ETL: POST /api/tenkai-etl
// tenkai_index.sql を4パートに分割して順次実行。SSEで進捗を返す。
// ────────────────────────────────────────────────────────────────────────────
app.post('/api/tenkai-etl', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const send = (msg: string, extra?: object) =>
    res.write(`data: ${JSON.stringify({ message: msg, ...extra })}\n\n`);

  if (etlLocks.tenkai) {
    send('エラー: 展開シナリオ指数ETLは既に実行中です。完了までお待ちください', { error: true, done: true });
    res.end(); return;
  }
  etlLocks.tenkai = true;

  (async () => {
    try {
      if (!fs.existsSync(TENKAI_SQL_FILE)) {
        send('エラー: sql/tenkai_index.sql が見つかりません', { error: true, done: true });
        res.end(); return;
      }
      const sql = fs.readFileSync(TENKAI_SQL_FILE, 'utf-8');
      const parts = splitSqlByParts(sql);

      for (let i = 0; i < parts.length; i++) {
        const partNum = i + 1;
        const label = TENKAI_PART_LABELS[partNum] ?? `Part${partNum}`;
        send(`[Part${partNum}] ${label} 開始...`);

        let heartbeat: NodeJS.Timeout | undefined;
        if (partNum >= 3) {
          let elapsed = 0;
          heartbeat = setInterval(() => {
            elapsed += 15;
            send(`[Part${partNum}] 処理中... (${elapsed}秒経過)`);
          }, 15_000);
        }

        try {
          await runMysqlSql(parts[i]);
          if (heartbeat) clearInterval(heartbeat);
          send(`[Part${partNum}] ${label} 完了`);
        } catch (err: any) {
          if (heartbeat) clearInterval(heartbeat);
          send(`[Part${partNum}] エラー: ${err.message}`, { error: true, done: true });
          res.end(); return;
        }
      }

      try {
        const [[row]] = await pool.query<any>(
          'SELECT COUNT(*) AS cnt FROM T_TENKAI_SCORE'
        );
        send(`完了: T_TENKAI_SCORE ${Number(row.cnt).toLocaleString()} 件`);
      } catch { /* 無視 */ }

      res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
      res.end();
    } finally {
      etlLocks.tenkai = false;
    }
  })().catch((err) => {
    res.write(`data: ${JSON.stringify({ error: err.message, done: true })}\n\n`);
    res.end();
  });
});

// ────────────────────────────────────────────────────────────────────────────
// 展開適合指数 ETL: POST /api/pacefit-etl
// pacefit_index.sql を4パートに分割して順次実行。SSEで進捗を返す。
// ────────────────────────────────────────────────────────────────────────────
app.post('/api/pacefit-etl', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const send = (msg: string, extra?: object) =>
    res.write(`data: ${JSON.stringify({ message: msg, ...extra })}\n\n`);

  if (etlLocks.pacefit) {
    send('エラー: 展開適合指数ETLは既に実行中です。完了までお待ちください', { error: true, done: true });
    res.end(); return;
  }
  etlLocks.pacefit = true;

  (async () => {
    try {
      if (!fs.existsSync(PACEFIT_SQL_FILE)) {
        send('エラー: sql/pacefit_index.sql が見つかりません', { error: true, done: true });
        res.end(); return;
      }
      const sql = fs.readFileSync(PACEFIT_SQL_FILE, 'utf-8');
      const parts = splitSqlByParts(sql);

      for (let i = 0; i < parts.length; i++) {
        const partNum = i + 1;
        const label = PACEFIT_PART_LABELS[partNum] ?? `Part${partNum}`;
        send(`[Part${partNum}] ${label} 開始...`);

        let heartbeat: NodeJS.Timeout | undefined;
        if (partNum >= 3) {
          let elapsed = 0;
          heartbeat = setInterval(() => {
            elapsed += 15;
            send(`[Part${partNum}] 処理中... (${elapsed}秒経過)`);
          }, 15_000);
        }

        try {
          await runMysqlSql(parts[i]);
          if (heartbeat) clearInterval(heartbeat);
          send(`[Part${partNum}] ${label} 完了`);
        } catch (err: any) {
          if (heartbeat) clearInterval(heartbeat);
          send(`[Part${partNum}] エラー: ${err.message}`, { error: true, done: true });
          res.end(); return;
        }
      }

      try {
        const [[row]] = await pool.query<any>(
          'SELECT COUNT(*) AS cnt FROM T_PACEFIT_SCORE'
        );
        send(`完了: T_PACEFIT_SCORE ${Number(row.cnt).toLocaleString()} 件`);
      } catch { /* 無視 */ }

      res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
      res.end();
    } finally {
      etlLocks.pacefit = false;
    }
  })().catch((err) => {
    res.write(`data: ${JSON.stringify({ error: err.message, done: true })}\n\n`);
    res.end();
  });
});

// ────────────────────────────────────────────────────────────────────────────
// コース回収率指数 ETL: POST /api/course-recovery-etl
// course_recovery_index.sql を3パートに分割して順次実行。SSEで進捗を返す。
// 事前に T_COURSE_FACTOR_AGG（course.htmlのETL）が構築済みである必要がある。
// ────────────────────────────────────────────────────────────────────────────
app.post('/api/course-recovery-etl', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const send = (msg: string, extra?: object) =>
    res.write(`data: ${JSON.stringify({ message: msg, ...extra })}\n\n`);

  if (etlLocks.courseRecovery) {
    send('エラー: コース回収率指数ETLは既に実行中です。完了までお待ちください', { error: true, done: true });
    res.end(); return;
  }
  etlLocks.courseRecovery = true;

  (async () => {
    try {
      const [[cfaRow]] = await pool.query<any>(
        `SELECT COUNT(*) AS cnt FROM T_COURSE_FACTOR_AGG WHERE factor_type='baseline'`
      );
      if (!Number(cfaRow.cnt)) {
        send('エラー: T_COURSE_FACTOR_AGG が未構築です。先に course.html 側のコース別集計ETLを実行してください', { error: true, done: true });
        res.end(); return;
      }

      if (!fs.existsSync(COURSE_RECOVERY_SQL_FILE)) {
        send('エラー: sql/course_recovery_index.sql が見つかりません', { error: true, done: true });
        res.end(); return;
      }
      const sql = fs.readFileSync(COURSE_RECOVERY_SQL_FILE, 'utf-8');
      const parts = splitSqlByParts(sql);

      for (let i = 0; i < parts.length; i++) {
        const partNum = i + 1;
        const label = COURSE_RECOVERY_PART_LABELS[partNum] ?? `Part${partNum}`;
        send(`[Part${partNum}] ${label} 開始...`);

        let heartbeat: NodeJS.Timeout | undefined;
        if (partNum >= 3) {
          let elapsed = 0;
          heartbeat = setInterval(() => {
            elapsed += 15;
            send(`[Part${partNum}] 処理中... (${elapsed}秒経過)`);
          }, 15_000);
        }

        try {
          await runMysqlSql(parts[i]);
          if (heartbeat) clearInterval(heartbeat);
          send(`[Part${partNum}] ${label} 完了`);
        } catch (err: any) {
          if (heartbeat) clearInterval(heartbeat);
          send(`[Part${partNum}] エラー: ${err.message}`, { error: true, done: true });
          res.end(); return;
        }
      }

      try {
        const [[row]] = await pool.query<any>(
          'SELECT COUNT(*) AS cnt FROM T_COURSE_RECOVERY_SCORE'
        );
        send(`完了: T_COURSE_RECOVERY_SCORE ${Number(row.cnt).toLocaleString()} 件`);
      } catch { /* 無視 */ }

      // カバレッジ整合性チェック: 出走全馬（tds1/2・class<>A1）に対してスコア漏れがないか
      // （ブリンカー指数で「スコア計算がT_SEDに依存し未実施レースの馬が漏れる」バグが発生した教訓を踏まえ、
      //   同種の指数ETLすべてに同じ自動チェックを入れる）
      try {
        const [[gapRow]] = await pool.query<any>(
          `SELECT COUNT(*) AS gap
           FROM T_KYI k
           INNER JOIN T_BAC b
             ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
           LEFT JOIN T_COURSE_RECOVERY_SCORE crs
             ON  crs.course_code=k.course_code AND crs.year_code=k.year_code AND crs.kai=k.kai
             AND crs.day_code=k.day_code AND crs.race_num=k.race_num AND crs.uma_num=CAST(TRIM(k.uma_num) AS UNSIGNED)
           WHERE b.tds_code IN ('1','2') AND b.class <> 'A1' AND crs.score IS NULL`
        );
        const gap = Number(gapRow.gap);
        if (gap > 0) {
          send(`⚠ カバレッジ異常: 出走馬のうちスコア未計算が ${gap.toLocaleString()} 件あります（本来は0件のはず。sql/course_recovery_index.sql のPart3を確認してください）`, { error: true });
        } else {
          send('カバレッジチェックOK: スコア未計算の漏れなし');
        }
      } catch { /* 無視 */ }

      res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
      res.end();
    } finally {
      etlLocks.courseRecovery = false;
    }
  })().catch((err) => {
    res.write(`data: ${JSON.stringify({ error: err.message, done: true })}\n\n`);
    res.end();
  });
});

// ────────────────────────────────────────────────────────────────────────────
// 不利巻き返し指数 ETL: POST /api/furi-etl
// furi_index.sql を3パートに分割して順次実行。SSEで進捗を返す。
// 設計: メモリ project_furi_index / project_prev_furi_recovery_analysis
// ────────────────────────────────────────────────────────────────────────────
app.post('/api/furi-etl', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const send = (msg: string, extra?: object) =>
    res.write(`data: ${JSON.stringify({ message: msg, ...extra })}\n\n`);

  if (etlLocks.furi) {
    send('エラー: 不利巻き返し指数ETLは既に実行中です。完了までお待ちください', { error: true, done: true });
    res.end(); return;
  }
  etlLocks.furi = true;

  (async () => {
    try {
      if (!fs.existsSync(FURI_SQL_FILE)) {
        send('エラー: sql/furi_index.sql が見つかりません', { error: true, done: true });
        res.end(); return;
      }
      const sql = fs.readFileSync(FURI_SQL_FILE, 'utf-8');
      const parts = splitSqlByParts(sql);

      for (let i = 0; i < parts.length; i++) {
        const partNum = i + 1;
        const label = FURI_PART_LABELS[partNum] ?? `Part${partNum}`;
        send(`[Part${partNum}] ${label} 開始...`);

        let heartbeat: NodeJS.Timeout | undefined;
        if (partNum >= 2) {
          let elapsed = 0;
          heartbeat = setInterval(() => {
            elapsed += 15;
            send(`[Part${partNum}] 処理中... (${elapsed}秒経過)`);
          }, 15_000);
        }

        try {
          await runMysqlSql(parts[i]);
          if (heartbeat) clearInterval(heartbeat);
          send(`[Part${partNum}] ${label} 完了`);
        } catch (err: any) {
          if (heartbeat) clearInterval(heartbeat);
          send(`[Part${partNum}] エラー: ${err.message}`, { error: true, done: true });
          res.end(); return;
        }
      }

      try {
        const [[row]] = await pool.query<any>(
          'SELECT COUNT(*) AS cnt FROM T_FURI_SCORE'
        );
        send(`完了: T_FURI_SCORE ${Number(row.cnt).toLocaleString()} 件`);
      } catch { /* 無視 */ }

      // カバレッジ整合性チェック: 前走リンクを持つ対象母集団でスコアが漏れていないか
      try {
        const [[gapRow]] = await pool.query<any>(
          `SELECT COUNT(*) AS gap
           FROM T_KYI k
           INNER JOIN T_BAC b
             ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
           LEFT JOIN T_FURI_SCORE fs
             ON  fs.course_code=k.course_code AND fs.year_code=k.year_code AND fs.kai=k.kai
             AND fs.day_code=k.day_code AND fs.race_num=k.race_num AND fs.uma_num=k.uma_num
           WHERE b.\`class\` <> 'A1' AND b.tds_code <> '3'
             AND k.prev1_seiseki_key IS NOT NULL AND k.prev1_seiseki_key <> ''
             AND fs.grade IS NULL`
        );
        const gap = Number(gapRow.gap);
        if (gap > 0) {
          send(`⚠ カバレッジ異常: 対象馬のうちスコア未計算が ${gap.toLocaleString()} 件あります（本来は0件のはず。sql/furi_index.sql のPart3を確認してください）`, { error: true });
        } else {
          send('カバレッジチェックOK: スコア未計算の漏れなし');
        }
      } catch { /* 無視 */ }

      res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
      res.end();
    } finally {
      etlLocks.furi = false;
    }
  })().catch((err) => {
    res.write(`data: ${JSON.stringify({ error: err.message, done: true })}\n\n`);
    res.end();
  });
});

// ────────────────────────────────────────────────────────────────────────────
// 厩指穴信頼グレード ETL: POST /api/kyusha-etl
// kyusha_analysis.sql を3パートに分割して順次実行。SSEで進捗を返す。
// 他の指数と異なり馬ごとのスコアテーブルは持たず、T_KYUSHA_FACTOR_AGG（調教師別集計）を
// getTrainerGradeMap()・computeFactorRecovery()がクエリ時にS〜F判定するため、
// 完了後はその2つのメモリキャッシュをクリアしてグレードを即時反映させる。
// 設計: document/指数/【廃】厩指穴信頼_仕様書.md
// ────────────────────────────────────────────────────────────────────────────
app.post('/api/kyusha-etl', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const send = (msg: string, extra?: object) =>
    res.write(`data: ${JSON.stringify({ message: msg, ...extra })}\n\n`);

  if (etlLocks.kyusha) {
    send('エラー: 厩指穴信頼ETLは既に実行中です。完了までお待ちください', { error: true, done: true });
    res.end(); return;
  }
  etlLocks.kyusha = true;

  (async () => {
    try {
      if (!fs.existsSync(KYUSHA_SQL_FILE)) {
        send('エラー: sql/kyusha_analysis.sql が見つかりません', { error: true, done: true });
        res.end(); return;
      }
      const sql = fs.readFileSync(KYUSHA_SQL_FILE, 'utf-8');
      const parts = splitSqlByParts(sql);

      for (let i = 0; i < parts.length; i++) {
        const partNum = i + 1;
        const label = KYUSHA_PART_LABELS[partNum] ?? `Part${partNum}`;
        send(`[Part${partNum}] ${label} 開始...`);

        let heartbeat: NodeJS.Timeout | undefined;
        if (partNum >= 2) {
          let elapsed = 0;
          heartbeat = setInterval(() => {
            elapsed += 15;
            send(`[Part${partNum}] 処理中... (${elapsed}秒経過)`);
          }, 15_000);
        }

        try {
          await runMysqlSql(parts[i]);
          if (heartbeat) clearInterval(heartbeat);
          send(`[Part${partNum}] ${label} 完了`);
        } catch (err: any) {
          if (heartbeat) clearInterval(heartbeat);
          send(`[Part${partNum}] エラー: ${err.message}`, { error: true, done: true });
          res.end(); return;
        }
      }

      try {
        const [[row]] = await pool.query<any>(
          'SELECT COUNT(*) AS cnt FROM T_KYUSHA_FACTOR_AGG'
        );
        send(`完了: T_KYUSHA_FACTOR_AGG ${Number(row.cnt).toLocaleString()} 件`);
      } catch { /* 無視 */ }

      // 厩指穴信頼グレードは馬ごとの事前計算スコアではなく、getTrainerGradeMap()・
      // computeFactorRecovery()がT_KYUSHA_FACTOR_AGGをクエリ時に集計してS〜F判定する方式。
      // メモリキャッシュを持っているため、ETL後はここでクリアして即座に反映させる。
      trainerGradeCache = null;
      factorRecoveryCache = null;
      send('厩指穴信頼グレードのキャッシュをクリアしました（出馬表・ウォッチリストに即時反映されます）');

      res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
      res.end();
    } finally {
      etlLocks.kyusha = false;
    }
  })().catch((err) => {
    res.write(`data: ${JSON.stringify({ error: err.message, done: true })}\n\n`);
    res.end();
  });
});

// ────────────────────────────────────────────────────────────────────────────
// sc・複勝妙味の元データ ETL: POST /api/sc-base-etl
// 2026-10-04 新設。sc（注目馬複合シグナル）と複勝妙味シグナルは出馬表・ウォッチリストを開いたときに
// その場で計算するため専用のスコアテーブルは無いが、次の2つの集計を元データとして参照する:
//   1. 騎手×調教師の成績 T_COMBO_RECOVERY（sql/combo_recovery.sql。以前は作成スクリプトが無く2026-04-30から未更新だった）
//   2. 厩舎の穴馬成績 T_KYUSHA_FACTOR_AGG（sql/kyusha_analysis.sql。旧「厩指穴信頼」ETL。ボタンが非表示になっていた）
// 2026-10-05 追加: 3. 厩舎穴指数の区分表 T_KYUSHA_NINKI_AGG（sql/kyusha_ninki_index.sql。出馬表 列#25）
// 成績（T_SED）を取り込んだあとに実行する。
// ────────────────────────────────────────────────────────────────────────────
const COMBO_SQL_FILE = path.join(__dirname, '..', 'sql', 'combo_recovery.sql');
const KYUSHA_NINKI_SQL_FILE = path.join(__dirname, '..', 'sql', 'kyusha_ninki_index.sql');
etlLocks.scBase = false;

app.post('/api/sc-base-etl', (_req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const send = (msg: string, extra?: object) =>
    res.write(`data: ${JSON.stringify({ message: msg, ...extra })}\n\n`);

  if (etlLocks.scBase || etlLocks.kyusha) {
    send('エラー: sc・複勝妙味の元データETLは既に実行中です。完了までお待ちください', { error: true, done: true });
    res.end(); return;
  }
  etlLocks.scBase = true;
  etlLocks.kyusha = true;

  // 無音のまま数十秒続くと接続が切られることがあるため、10秒ごとに経過を送る（anaba-honmei-etl と同じ対策）
  const runWithHeartbeat = async (label: string, sql: string) => {
    let elapsed = 0;
    const hb = setInterval(() => { elapsed += 10; send(`[${label}] 実行中... (${elapsed}秒経過)`); }, 10_000);
    try { await runMysqlSql(sql); } finally { clearInterval(hb); }
  };

  (async () => {
    try {
      for (const f of [COMBO_SQL_FILE, KYUSHA_SQL_FILE, KYUSHA_NINKI_SQL_FILE]) {
        if (!fs.existsSync(f)) { send(`エラー: ${f} が見つかりません`, { error: true, done: true }); res.end(); return; }
      }
      send('[1/3] 騎手×調教師の成績（T_COMBO_RECOVERY）を再集計 開始...');
      try {
        await runWithHeartbeat('1/3 騎手×調教師', fs.readFileSync(COMBO_SQL_FILE, 'utf-8'));
      } catch (err: any) {
        send(`[1/3] エラー: ${err.message}`, { error: true, done: true }); res.end(); return;
      }
      const [[c]] = await pool.query<any>('SELECT COUNT(*) AS pairs, SUM(total_count) AS total FROM T_COMBO_RECOVERY');
      const [[t]] = await pool.query<any>(
        `SELECT COUNT(*) AS cnt FROM T_KYI k
           INNER JOIN T_BAC b ON b.course_code=k.course_code AND b.year_code=k.year_code AND b.kai=k.kai AND b.day_code=k.day_code AND b.race_num=k.race_num
           INNER JOIN T_SED s ON s.course_code=k.course_code AND s.year_code=k.year_code AND s.kai=k.kai AND s.day_code=k.day_code AND s.race_num=k.race_num AND s.umaban=k.uma_num
         WHERE TRIM(b.tds_code) IN ('1','2') AND TRIM(s.order_of_finish) <> '' AND CAST(TRIM(s.order_of_finish) AS UNSIGNED) > 0
           AND TRIM(k.kishu_code) <> '' AND TRIM(k.trainer_code) <> ''`);
      const gap = Number(t.cnt) - Number(c.total);
      send(`[1/3] 完了: 騎手×調教師 ${Number(c.pairs).toLocaleString()} 組、合計 ${Number(c.total).toLocaleString()} 頭`
        + (gap === 0 ? '（対象頭数と一致）' : ` ⚠ 対象頭数との差 ${gap.toLocaleString()} 頭`), gap === 0 ? undefined : { error: true });

      const parts = splitSqlByParts(fs.readFileSync(KYUSHA_SQL_FILE, 'utf-8'));
      for (let i = 0; i < parts.length; i++) {
        const label = `2/3 厩舎の穴馬成績 Part${i + 1}`;
        send(`[${label}] ${KYUSHA_PART_LABELS[i + 1] ?? ''} 開始...`);
        try {
          await runWithHeartbeat(label, parts[i]);
        } catch (err: any) {
          send(`[${label}] エラー: ${err.message}`, { error: true, done: true }); res.end(); return;
        }
        send(`[${label}] 完了`);
      }
      const [[k]] = await pool.query<any>('SELECT COUNT(*) AS cnt FROM T_KYUSHA_FACTOR_AGG');
      send(`[2/3] 完了: T_KYUSHA_FACTOR_AGG ${Number(k.cnt).toLocaleString()} 件`);

      send('[3/3] 厩舎穴指数の区分表（T_KYUSHA_NINKI_AGG）を再集計 開始...');
      try {
        await runWithHeartbeat('3/3 厩舎穴指数', fs.readFileSync(KYUSHA_NINKI_SQL_FILE, 'utf-8'));
      } catch (err: any) {
        send(`[3/3] エラー: ${err.message}`, { error: true, done: true }); res.end(); return;
      }
      const [[kn]] = await pool.query<any>('SELECT COUNT(*) AS cells, SUM(total_count) AS total, MAX(to_ymd) AS to_ymd FROM T_KYUSHA_NINKI_AGG');
      send(`[3/3] 完了: 厩舎穴指数 ${kn.cells} 区分、${Number(kn.total).toLocaleString()} 頭（成績は ${kn.to_ymd} まで）`
        + (Number(kn.cells) === 16 ? '' : ' ⚠ 区分数が16ではありません'), Number(kn.cells) === 16 ? undefined : { error: true });

      trainerGradeCache = null;
      factorRecoveryCache = null;
      send('完了: キャッシュをクリアしました。出馬表・ウォッチリストを開き直すと新しい集計で sc・複勝妙味・厩舎穴指数が表示されます');
      res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
      res.end();
    } finally {
      etlLocks.scBase = false;
      etlLocks.kyusha = false;
    }
  })().catch((err) => {
    res.write(`data: ${JSON.stringify({ error: err.message, done: true })}\n\n`);
    res.end();
  });
});

// ────────────────────────────────────────────────────────────────────────────
// 期待値指数 ETL: POST /api/ev-index-etl
// python/ev_index_etl.py を実行し、進捗をSSEで返す。
// ────────────────────────────────────────────────────────────────────────────
const EV_INDEX_PY_SCRIPT = path.join(__dirname, '..', 'python', 'ev_index_etl.py');
const PYTHON_EXE = process.env.PYTHON_EXE
  ?? 'C:\\Users\\roykh\\AppData\\Local\\Programs\\Python\\Python312\\python.exe';

app.post('/api/ev-index-etl', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const send = (msg: string, extra?: object) =>
    res.write(`data: ${JSON.stringify({ message: msg, ...extra })}\n\n`);

  if (etlLocks.evIndex) {
    send('エラー: 期待値指数ETLは既に実行中です。完了までお待ちください', { error: true, done: true });
    res.end(); return;
  }
  if (!fs.existsSync(EV_INDEX_PY_SCRIPT)) {
    send('エラー: python/ev_index_etl.py が見つかりません', { error: true, done: true });
    res.end(); return;
  }
  etlLocks.evIndex = true;

  const proc = spawn(PYTHON_EXE, [EV_INDEX_PY_SCRIPT], { stdio: ['ignore', 'pipe', 'pipe'] });
  let buf = '';
  const flushLines = (chunk: Buffer, isErr: boolean) => {
    buf += chunk.toString('utf-8');
    const lines = buf.split(/\r?\n/);
    buf = lines.pop() ?? '';
    for (const line of lines) {
      if (line.trim()) send(isErr ? `[stderr] ${line}` : line);
    }
  };
  proc.stdout.on('data', (d: Buffer) => flushLines(d, false));
  proc.stderr.on('data', (d: Buffer) => flushLines(d, true));
  proc.on('close', (code) => {
    etlLocks.evIndex = false;
    if (code === 0) {
      send('期待値指数ETLが完了しました', { done: true });
    } else {
      send(`エラー: Pythonプロセスが異常終了しました (code=${code})`, { error: true, done: true });
    }
    res.end();
  });
  proc.on('error', (err) => {
    etlLocks.evIndex = false;
    send(`エラー: Pythonプロセスの起動に失敗しました: ${err.message}`, { error: true, done: true });
    res.end();
  });
});

// ────────────────────────────────────────────────────────────────────────────
// 分析ファクトテーブル: ステータス確認 + ETL
// ────────────────────────────────────────────────────────────────────────────

app.get('/api/analyze-fact-status', (_req, res) => {
  res.json({ ready: factTableReady });
});

app.post('/api/analyze-fact-etl', (_req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  const send = (msg: string, extra?: object) =>
    res.write(`data: ${JSON.stringify({ message: msg, ...extra })}\n\n`);

  if (etlLocks.analyzeFact) {
    send('エラー: 分析ファクトテーブルETLは既に実行中です。完了までお待ちください', { error: true, done: true });
    res.end(); return;
  }
  etlLocks.analyzeFact = true;

  (async () => {
   try {
    // Step1: DDL
    send('[Step1] テーブル定義中...');
    await pool.query('DROP TABLE IF EXISTS T_ANALYZE_FACT');
    await pool.query(`CREATE TABLE T_ANALYZE_FACT (
      course_code       CHAR(2)           NOT NULL,
      year_code         CHAR(2)           NOT NULL,
      kai               CHAR(2)           NOT NULL,
      day_code          CHAR(1)           NOT NULL,
      race_num          CHAR(2)           NOT NULL,
      uma_num           TINYINT UNSIGNED  NOT NULL,
      ymd               CHAR(8)           NOT NULL,
      tds_code          CHAR(1)           NOT NULL,
      distance          SMALLINT UNSIGNED NOT NULL DEFAULT 0,
      class_code        CHAR(2)           NOT NULL DEFAULT '',
      waku_num          TINYINT UNSIGNED,
      kijun_odds        DECIMAL(7,1),
      kijun_ninki       TINYINT UNSIGNED,
      in_joho           TINYINT UNSIGNED,
      goal_juni         TINYINT UNSIGNED,
      in_idm            TINYINT UNSIGNED,
      idm               DECIMAL(6,1),
      kyusha_index      DECIMAL(6,1),
      ten_index_juni    TINYINT UNSIGNED,
      agari_index_juni  TINYINT UNSIGNED,
      kishu_name        VARCHAR(20),
      trainer_name      VARCHAR(20),
      umanushi_name     VARCHAR(40),
      kyakushitsu       CHAR(1),
      order_of_finish   TINYINT UNSIGNED,
      win_pay           SMALLINT UNSIGNED,
      place_pay         SMALLINT UNSIGNED,
      oi_index          SMALLINT UNSIGNED,
      shiage_index      SMALLINT UNSIGNED,
      ex_overall        DECIMAL(7,1),
      ex_course         DECIMAL(7,1),
      honmei_overall    DECIMAL(7,1),
      honmei_course     DECIMAL(7,1),
      tenkai_score      DECIMAL(7,1),
      chokyo_sp         TINYINT,
      PRIMARY KEY (course_code, year_code, kai, day_code, race_num, uma_num),
      INDEX idx_af_ymd       (ymd),
      INDEX idx_af_tds_class (tds_code, class_code),
      INDEX idx_af_kishu     (kishu_name(10)),
      INDEX idx_af_trainer   (trainer_name(10))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 ROW_FORMAT=COMPACT`);
    send('[Step1] 完了');
    factTableReady = false;

    // Step2: 依存テーブル確認
    send('[Step2] 依存テーブルを確認中...');
    const [tblRows] = await pool.query<any>(
      `SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
       WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME IN ('T_ANABA_SCORE','T_HONMEI_SCORE','T_PACEFIT_SCORE')`
    );
    const existingTbls = new Set((tblRows as any[]).map((r: any) => (r.TABLE_NAME as string).toLowerCase()));
    const hasAnaba   = existingTbls.has('t_anaba_score');
    const hasHonmei  = existingTbls.has('t_honmei_score');
    const hasPacefit = existingTbls.has('t_pacefit_score');
    send(`[Step2] T_ANABA_SCORE=${hasAnaba ? '有' : '無'}, T_HONMEI_SCORE=${hasHonmei ? '有' : '無'}, T_PACEFIT_SCORE=${hasPacefit ? '有' : '無'}`);

    // Step3: INSERT（数分かかる）
    send('[Step3] データ挿入開始（数分かかります）...');
    const ansJoinEtl   = hasAnaba   ? `LEFT JOIN T_ANABA_SCORE ans ON k.course_code=ans.course_code AND k.year_code=ans.year_code AND k.kai=ans.kai AND k.day_code=ans.day_code AND k.race_num=ans.race_num AND k.uma_num=ans.uma_num` : '';
    const hmsJoinEtl   = hasHonmei  ? `LEFT JOIN T_HONMEI_SCORE hms ON k.course_code=hms.course_code AND k.year_code=hms.year_code AND k.kai=hms.kai AND k.day_code=hms.day_code AND k.race_num=hms.race_num AND k.uma_num=hms.uma_num` : '';
    const pfsJoinEtl   = hasPacefit ? `LEFT JOIN T_PACEFIT_SCORE pfs ON k.course_code=pfs.course_code AND k.year_code=pfs.year_code AND k.kai=pfs.kai AND k.day_code=pfs.day_code AND k.race_num=pfs.race_num AND k.uma_num=pfs.uma_num` : '';
    const ansSelectEtl = hasAnaba   ? 'ans.overall_score, ans.course_score' : 'NULL, NULL';
    const hmsSelectEtl = hasHonmei  ? 'hms.overall_score, hms.course_score' : 'NULL, NULL';
    const pfsSelectEtl = hasPacefit ? 'pfs.overall_score'                  : 'NULL';

    const etlSql = `
      INSERT INTO T_ANALYZE_FACT
      WITH sp_raw AS (
        SELECT k2.course_code, k2.year_code, k2.kai, k2.day_code, k2.race_num, k2.uma_num,
          CAST(c2.oi_index     AS DECIMAL(6,1)) AS oi_val,
          CAST(c2.shiage_index AS DECIMAL(6,1)) AS shi_val,
          TRIM(k2.chokyo_yajirushi)             AS yj,
          TRIM(k2.hohbokusaki_rank)             AS hb,
          SUM(CASE WHEN CAST(c2.oi_index     AS DECIMAL(6,1)) > 0 THEN 1 ELSE 0 END) OVER w AS oi_cnt,
          SUM(CASE WHEN CAST(c2.shiage_index AS DECIMAL(6,1)) > 0 THEN 1 ELSE 0 END) OVER w AS shi_cnt,
          RANK() OVER (PARTITION BY k2.course_code,k2.year_code,k2.kai,k2.day_code,k2.race_num
                       ORDER BY CASE WHEN CAST(c2.oi_index AS DECIMAL(6,1)) > 0 THEN CAST(c2.oi_index AS DECIMAL(6,1)) END DESC) AS oi_rank,
          RANK() OVER (PARTITION BY k2.course_code,k2.year_code,k2.kai,k2.day_code,k2.race_num
                       ORDER BY CASE WHEN CAST(c2.shiage_index AS DECIMAL(6,1)) > 0 THEN CAST(c2.shiage_index AS DECIMAL(6,1)) END DESC) AS shi_rank,
          AVG(CASE WHEN CAST(c2.oi_index     AS DECIMAL(6,1)) > 0 THEN CAST(c2.oi_index     AS DECIMAL(6,1)) END) OVER w AS oi_avg,
          STDDEV_POP(CASE WHEN CAST(c2.oi_index AS DECIMAL(6,1)) > 0 THEN CAST(c2.oi_index AS DECIMAL(6,1)) END) OVER w AS oi_sd,
          AVG(CASE WHEN CAST(c2.shiage_index AS DECIMAL(6,1)) > 0 THEN CAST(c2.shiage_index AS DECIMAL(6,1)) END) OVER w AS shi_avg,
          STDDEV_POP(CASE WHEN CAST(c2.shiage_index AS DECIMAL(6,1)) > 0 THEN CAST(c2.shiage_index AS DECIMAL(6,1)) END) OVER w AS shi_sd
        FROM T_KYI k2
        LEFT JOIN T_CYB c2
          ON  c2.course_code=k2.course_code AND c2.year_code=k2.year_code
          AND c2.kai=k2.kai AND c2.day_code=k2.day_code AND c2.race_num=k2.race_num AND c2.uma_num=k2.uma_num
        WINDOW w AS (PARTITION BY k2.course_code,k2.year_code,k2.kai,k2.day_code,k2.race_num)
      ),
      sp_cte AS (
        SELECT course_code, year_code, kai, day_code, race_num, uma_num,
          CASE
            WHEN oi_cnt < 2 OR shi_cnt < 2
              OR oi_val IS NULL OR oi_val <= 0
              OR shi_val IS NULL OR shi_val <= 0 THEN NULL
            ELSE
              (CASE oi_rank WHEN 1 THEN 3 WHEN 2 THEN 2 WHEN 3 THEN 1 ELSE 0 END)
             +(CASE shi_rank WHEN 1 THEN 3 WHEN 2 THEN 2 WHEN 3 THEN 1 ELSE 0 END)
             +LEAST(0, ROUND((
                 CASE WHEN oi_sd  > 0 THEN (oi_val  - oi_avg)  / oi_sd  ELSE 0 END
                +CASE WHEN shi_sd > 0 THEN (shi_val - shi_avg) / shi_sd ELSE 0 END
               ) * 1.0, 0))
             +(CASE yj WHEN '4' THEN -2 WHEN '5' THEN -4 ELSE 0 END)
             +(CASE hb WHEN 'E' THEN -4 WHEN 'D' THEN -2 ELSE 0 END)
          END AS sp_score
        FROM sp_raw
      )
      SELECT
        b.course_code, b.year_code, b.kai, b.day_code, b.race_num,
        CAST(TRIM(k.uma_num)            AS UNSIGNED),
        b.ymd, b.tds_code,
        CAST(TRIM(b.distance)           AS UNSIGNED),
        b.\`class\`,
        CAST(TRIM(k.waku_num)           AS UNSIGNED),
        CAST(k.kijun_odds               AS DECIMAL(7,1)),
        CAST(k.kijun_ninki              AS UNSIGNED),
        CAST(k.in_joho                  AS UNSIGNED),
        CAST(k.goal_juni                AS UNSIGNED),
        CAST(k.in_idm                   AS UNSIGNED),
        CAST(k.idm                      AS DECIMAL(6,1)),
        CAST(k.kyusha_index             AS DECIMAL(6,1)),
        CAST(k.ten_index_juni           AS UNSIGNED),
        CAST(k.agari_index_juni         AS UNSIGNED),
        TRIM(k.kishu_name),
        TRIM(k.trainer_name),
        TRIM(k.umanushi_name),
        k.kyakushitsu,
        CAST(TRIM(fin.order_of_finish)  AS UNSIGNED),
        COALESCE(CAST(TRIM(fin.win)     AS UNSIGNED), 0),
        COALESCE(CAST(TRIM(fin.place)   AS UNSIGNED), 0),
        CAST(c.oi_index                 AS UNSIGNED),
        CAST(c.shiage_index             AS UNSIGNED),
        ${ansSelectEtl},
        ${hmsSelectEtl},
        ${pfsSelectEtl},
        sp.sp_score
      FROM t_bac b
      INNER JOIN t_kyi k
        ON  b.course_code = k.course_code AND b.year_code = k.year_code
        AND b.kai = k.kai AND b.day_code = k.day_code AND b.race_num = k.race_num
      INNER JOIN t_sed fin
        ON  k.course_code = fin.course_code AND k.year_code = fin.year_code
        AND k.kai = fin.kai AND k.day_code = fin.day_code
        AND k.race_num = fin.race_num AND k.uma_num = fin.umaban
        AND fin.ijou_kubun IN ('0','')
      LEFT JOIN t_cyb c
        ON  k.course_code = c.course_code AND k.year_code = c.year_code
        AND k.kai = c.kai AND k.day_code = c.day_code AND k.race_num = c.race_num AND k.uma_num = c.uma_num
      ${ansJoinEtl}
      ${hmsJoinEtl}
      ${pfsJoinEtl}
      LEFT JOIN sp_cte sp
        ON  k.course_code = sp.course_code AND k.year_code = sp.year_code
        AND k.kai = sp.kai AND k.day_code = sp.day_code AND k.race_num = sp.race_num
        AND k.uma_num = sp.uma_num
      WHERE b.\`class\` <> 'A1'
    `;

    const conn = await (pool as any).getConnection();
    let hb3: NodeJS.Timeout | undefined;
    try {
      await conn.query('SET SESSION wait_timeout = 3600');
      let elapsed = 0;
      hb3 = setInterval(() => {
        elapsed += 10;
        send(`[Step3] 挿入中... (${elapsed}秒経過)`);
      }, 10_000);
      await conn.query(etlSql);
      clearInterval(hb3);
      hb3 = undefined;
    } finally {
      if (hb3) clearInterval(hb3);
      conn.release();
    }

    const [[cntRow]] = await pool.query<any>('SELECT COUNT(*) AS cnt FROM T_ANALYZE_FACT');
    send(`[Step3] 完了: ${Number(cntRow.cnt).toLocaleString()} 件を挿入`);

    factTableReady = true;
    res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
    res.end();
   } finally {
     etlLocks.analyzeFact = false;
   }
  })().catch((err: any) => {
    send(`エラー: ${err.message}`, { error: true, done: true });
    res.end();
  });
});

app.listen(PORT, () => {
  console.log(`サーバー起動: http://localhost:${PORT}`);
  // 本命指数テーブルが未作成の場合は空テーブルを作成（entries API の LEFT JOIN が失敗しないようにする）
  pool.query(
    `CREATE TABLE IF NOT EXISTS T_HONMEI_SCORE (
      course_code CHAR(2) NOT NULL, year_code CHAR(2) NOT NULL,
      kai CHAR(1) NOT NULL, day_code CHAR(1) NOT NULL,
      race_num CHAR(2) NOT NULL, uma_num CHAR(2) NOT NULL,
      overall_score DECIMAL(7,1) DEFAULT NULL,
      course_score  DECIMAL(7,1) DEFAULT NULL,
      score_ten DECIMAL(5,1) DEFAULT NULL, score_agari DECIMAL(5,1) DEFAULT NULL,
      score_ichi DECIMAL(5,1) DEFAULT NULL, score_goal DECIMAL(5,1) DEFAULT NULL,
      score_combo DECIMAL(5,1) DEFAULT NULL, score_idm DECIMAL(5,1) DEFAULT NULL,
      score_joho DECIMAL(5,1) DEFAULT NULL, score_kyusha DECIMAL(5,1) DEFAULT NULL,
      score_chokyo DECIMAL(5,1) DEFAULT NULL, score_kyakushitsu DECIMAL(5,1) DEFAULT NULL,
      score_joshodo DECIMAL(5,1) DEFAULT NULL, score_tekisei DECIMAL(5,1) DEFAULT NULL,
      score_blood DECIMAL(5,1) DEFAULT NULL,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (course_code, year_code, kai, day_code, race_num, uma_num)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`
  ).catch(() => {});
  // 自分の予想印テーブルが未作成の場合は作成（entries API の LEFT JOIN が失敗しないようにする）
  pool.query(
    `CREATE TABLE IF NOT EXISTS T_MY_MARK (
      course_code CHAR(2) NOT NULL, year_code CHAR(2) NOT NULL,
      kai CHAR(1) NOT NULL, day_code CHAR(1) NOT NULL,
      race_num CHAR(2) NOT NULL, uma_num CHAR(2) NOT NULL,
      mark CHAR(1) NOT NULL COMMENT '自分の予想印(1=◎ 2=○ 3=▲ 4=注 5=△ 6=▽)',
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (course_code, year_code, kai, day_code, race_num, uma_num)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='自分の予想印（ユーザー入力・分析用）'`
  ).catch(() => {});
  // デフォルト年範囲のキャッシュを起動直後にバックグラウンドで生成
  setTimeout(() => {
    fetch(`http://localhost:${PORT}/api/jockey-ninki-stats?yearFrom=2020&yearTo=2026&minRides=1`)
      .then(() => console.log('騎手統計キャッシュ: 準備完了'))
      .catch(() => {});
  }, 500);
  initFactTableStatus().catch(() => {});
});
