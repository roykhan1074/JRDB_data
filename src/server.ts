import express from 'express';
import path from 'path';
import { spawn } from 'child_process';
import * as fs from 'fs';
import { runPipeline, PrefixName } from './pipeline';
import { pool } from './db/dbConnection';

const ANABA_SQL_FILE    = path.join(__dirname, '..', 'sql', 'anaba_index.sql');
const TENKAI_SQL_FILE   = path.join(__dirname, '..', 'sql', 'tenkai_index.sql');
const PACEFIT_SQL_FILE  = path.join(__dirname, '..', 'sql', 'pacefit_index.sql');

const PART_LABELS: Record<number, string> = {
  1: 'テーブル定義 (CREATE TABLE)',
  2: 'ファクトデータ投入 (T_ANABA_RACE_LOG)',
  3: 'ファクター集計 (T_ANABA_FACTOR_AGG)',
  4: '指数計算 (T_ANABA_SCORE)',
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
      process.env.DB_NAME ?? 'racing',
    ];
    const proc = spawn('mysql', args, { stdio: ['pipe', 'pipe', 'pipe'] });
    let stderr = '';
    proc.stderr.on('data', (d: Buffer) => {
      const s = d.toString();
      if (!s.includes('[Warning] Using a password')) stderr += s;
    });
    proc.on('close', (code: number | null) => {
      if (code === 0) resolve();
      else reject(new Error(stderr.trim() || `mysql exit code ${code}`));
    });
    proc.stdin.write(sql, 'utf8');
    proc.stdin.end();
  });
}

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
            k.goal_juni,
            k.kyusha_index,
            k.kishu_name, k.trainer_name,
            k.kishu_code, k.trainer_code,
            k.ten_index_juni, k.agari_index_juni, k.ichi_index_juni, k.blinker,
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
            kya.anaba_n         AS kyusha_anaba_n,
            ans.overall_score AS anaba_overall_score,
            ans.course_score  AS anaba_course_score,
            ans.score_ten, ans.score_agari, ans.score_ichi, ans.score_goal,
            ans.score_combo, ans.score_idm, ans.score_gekiso, ans.score_manbaken,
            ans.score_chokyo, ans.score_joshodo, ans.score_tekisei, ans.score_blood,
            pfs.overall_score AS pacefit_score,
            pfs.pace_yoso     AS pacefit_pace,
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
     LEFT JOIN T_PACEFIT_SCORE pfs
       ON  pfs.course_code = k.course_code AND pfs.year_code = k.year_code
       AND pfs.kai = k.kai AND pfs.day_code = k.day_code
       AND pfs.race_num = k.race_num AND pfs.uma_num = k.uma_num
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

  (async () => {
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

  (async () => {
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

  (async () => {
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
  })().catch((err) => {
    res.write(`data: ${JSON.stringify({ error: err.message, done: true })}\n\n`);
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

  (async () => {
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
       AND TABLE_NAME IN ('T_ANABA_SCORE','T_PACEFIT_SCORE')`
    );
    const existingTbls = new Set((tblRows as any[]).map((r: any) => (r.TABLE_NAME as string).toLowerCase()));
    const hasAnaba   = existingTbls.has('t_anaba_score');
    const hasPacefit = existingTbls.has('t_pacefit_score');
    send(`[Step2] T_ANABA_SCORE=${hasAnaba ? '有' : '無'}, T_PACEFIT_SCORE=${hasPacefit ? '有' : '無'}`);

    // Step3: INSERT（数分かかる）
    send('[Step3] データ挿入開始（数分かかります）...');
    const ansJoinEtl   = hasAnaba   ? `LEFT JOIN T_ANABA_SCORE ans ON k.course_code=ans.course_code AND k.year_code=ans.year_code AND k.kai=ans.kai AND k.day_code=ans.day_code AND k.race_num=ans.race_num AND k.uma_num=ans.uma_num` : '';
    const pfsJoinEtl   = hasPacefit ? `LEFT JOIN T_PACEFIT_SCORE pfs ON k.course_code=pfs.course_code AND k.year_code=pfs.year_code AND k.kai=pfs.kai AND k.day_code=pfs.day_code AND k.race_num=pfs.race_num AND k.uma_num=pfs.uma_num` : '';
    const ansSelectEtl = hasAnaba   ? 'ans.overall_score, ans.course_score' : 'NULL, NULL';
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

  })().catch((err: any) => {
    send(`エラー: ${err.message}`, { error: true, done: true });
    res.end();
  });
});

app.listen(PORT, () => {
  console.log(`サーバー起動: http://localhost:${PORT}`);
  // デフォルト年範囲のキャッシュを起動直後にバックグラウンドで生成
  setTimeout(() => {
    fetch(`http://localhost:${PORT}/api/jockey-ninki-stats?yearFrom=2020&yearTo=2026&minRides=1`)
      .then(() => console.log('騎手統計キャッシュ: 準備完了'))
      .catch(() => {});
  }, 500);
  initFactTableStatus().catch(() => {});
});
