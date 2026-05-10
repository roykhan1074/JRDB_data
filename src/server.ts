import express from 'express';
import path from 'path';
import { spawn } from 'child_process';
import * as fs from 'fs';
import { runPipeline, PrefixName } from './pipeline';
import { createConnection } from './db/dbConnection';

const ANABA_SQL_FILE = path.join(__dirname, '..', 'sql', 'anaba_index.sql');

const PART_LABELS: Record<number, string> = {
  1: 'テーブル定義 (CREATE TABLE)',
  2: 'ファクトデータ投入 (T_ANABA_RACE_LOG)',
  3: 'ファクター集計 (T_ANABA_FACTOR_AGG)',
  4: '指数計算 (T_ANABA_SCORE)',
};

/** SQLファイルを -- Part N: マーカーで4パートに分割 */
function splitAnabaSql(content: string): string[] {
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

  const conn = await createConnection();
  try {
    const tableNames = TABLE_META.map(m => m.table);

    // information_schema から行数を一括取得（COUNT(*) の全件スキャンを回避）
    const [isRows] = await conn.query<any>(
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
        const [[dateRow]] = await conn.query<any>(
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
  } finally {
    await conn.end();
  }
});

// レース検索: GET /api/races?date=YYYYMMDD[&course=XX]
app.get('/api/races', async (req, res) => {
  const { date, course } = req.query as { date?: string; course?: string };
  if (!date || !/^\d{8}$/.test(date)) {
    res.status(400).json({ error: '日付はYYYYMMDD形式で指定してください' });
    return;
  }
  const conn = await createConnection();
  try {
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
    const [rows] = await conn.query<any>(sql, params);
    res.json(rows);
  } finally {
    await conn.end();
  }
});

// レース単体情報: GET /api/races/:raceKey
app.get('/api/races/:raceKey', async (req, res) => {
  const { raceKey } = req.params;
  if (!/^\d{8}$/.test(raceKey)) {
    res.status(400).json({ error: '無効なレースキーです' });
    return;
  }
  const course_code = raceKey.slice(0, 2);
  const year_code   = raceKey.slice(2, 4);
  const kai         = raceKey.slice(4, 5);
  const day_code    = raceKey.slice(5, 6);
  const race_num    = raceKey.slice(6, 8);

  const conn = await createConnection();
  try {
    const [[race]] = await conn.query<any>(
      `SELECT course_code, year_code, kai, day_code, race_num,
              ymd, race_name, race_name_9char, distance, tds_code,
              grade, \`class\`, heads, start_time, data_kubun, migihidari, naigai
       FROM T_BAC
       WHERE course_code=? AND year_code=? AND kai=? AND day_code=? AND race_num=?`,
      [course_code, year_code, kai, day_code, race_num]
    );
    if (!race) { res.status(404).json({ error: 'レースが見つかりません' }); return; }
    res.json(race);
  } finally {
    await conn.end();
  }
});

// レース詳細: GET /api/races/:raceKey/entries
// raceKey = course_code(2) + year_code(2) + kai(1) + day_code(1) + race_num(2)
app.get('/api/races/:raceKey/entries', async (req, res) => {
  const { raceKey } = req.params;
  if (!/^\d{8}$/.test(raceKey)) {
    res.status(400).json({ error: '無効なレースキーです' });
    return;
  }
  const course_code = raceKey.slice(0, 2);
  const year_code   = raceKey.slice(2, 4);
  const kai         = raceKey.slice(4, 5);
  const day_code    = raceKey.slice(5, 6);
  const race_num    = raceKey.slice(6, 8);

  const conn = await createConnection();
  try {
    const [rows] = await conn.query<any>(
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
       ) kya ON kya.trainer_code = TRIM(k.trainer_code)
       LEFT JOIN T_ANABA_SCORE ans
         ON  ans.course_code = k.course_code AND ans.year_code = k.year_code
         AND ans.kai = k.kai AND ans.day_code = k.day_code
         AND ans.race_num = k.race_num AND ans.uma_num = k.uma_num
       LEFT JOIN T_SED s
         ON  s.course_code = k.course_code AND s.year_code = k.year_code
         AND s.kai = k.kai AND s.day_code = k.day_code
         AND s.race_num = k.race_num AND s.umaban = k.uma_num
       WHERE k.course_code=? AND k.year_code=? AND k.kai=? AND k.day_code=? AND k.race_num=?
       ORDER BY CAST(k.uma_num AS UNSIGNED)`,
      [course_code, year_code, kai, day_code, race_num]
    );
    res.json({ source: 'entries', rows });
  } finally {
    await conn.end();
  }
});

// ────────────────────────────────────────────────────────────────────────────
// 分析API: POST /api/analyze
// ────────────────────────────────────────────────────────────────────────────

// 集計キーの SELECT / GROUP BY 式のホワイトリスト
// orderSql: ORDER BY 用の数値キャスト式。未指定の場合は groupSql を流用。
const AGGREGATE_MAP: Record<string, { selectSql: string; groupSql: string; orderSql?: string; alias: string }> = {
  ymd:         { alias: '日付',        selectSql: "b.ymd",           groupSql: "b.ymd" },
  course:      { alias: '競馬場',      groupSql: "b.course_code",
                 selectSql: "CASE b.course_code WHEN '01' THEN '札幌' WHEN '02' THEN '函館' WHEN '03' THEN '福島' WHEN '04' THEN '新潟' WHEN '05' THEN '東京' WHEN '06' THEN '中山' WHEN '07' THEN '中京' WHEN '08' THEN '京都' WHEN '09' THEN '阪神' WHEN '10' THEN '小倉' ELSE b.course_code END" },
  tds:         { alias: '芝ダ',        groupSql: "b.tds_code",
                 selectSql: "CASE b.tds_code WHEN '1' THEN '芝' WHEN '2' THEN 'ダート' WHEN '3' THEN '障害' ELSE b.tds_code END" },
  distance:    { alias: '距離',        selectSql: "b.distance",      groupSql: "b.distance",    orderSql: "CAST(b.distance AS UNSIGNED)" },
  class:       { alias: 'クラス',      groupSql: "b.`class`",
                 selectSql: "CASE b.`class` WHEN 'A1' THEN '新馬' WHEN 'A3' THEN '未勝利' WHEN '05' THEN '1勝クラス' WHEN '10' THEN '2勝クラス' WHEN '16' THEN '3勝クラス' WHEN 'OP' THEN 'オープン' ELSE b.`class` END" },
  odds:        { alias: '基準オッズ',  selectSql: "k.kijun_odds",    groupSql: "k.kijun_odds",  orderSql: "CAST(k.kijun_odds AS DECIMAL(7,1))" },
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
};
// caseベースの集計キーは selectSql と groupSql を同一にする
for (const key of Object.keys(AGGREGATE_MAP)) {
  const entry = AGGREGATE_MAP[key];
  if (!entry.selectSql) entry.selectSql = entry.groupSql;
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
    kishu, trainer, umanushi,
    aggregate_01, aggregate_02, aggregate_03,
  } = req.body as Record<string, string>;

  // 集計キーをホワイトリストで検証
  const aggKeys = [aggregate_01, aggregate_02, aggregate_03]
    .filter(k => k && AGGREGATE_MAP[k]);

  const params: (string | number)[] = [];

  // 集計キーの SELECT 句
  const selectParts = aggKeys.map((k, i) => {
    const alias = `agg_key_${i + 1}`;
    return `(${AGGREGATE_MAP[k].selectSql}) AS \`${alias}\``;
  });

  // 集計統計 — order_of_finish を一度だけ評価する派生サブクエリで CAST 回数を削減
  selectParts.push(`
    COUNT(*)                                   AS total_heads,
    SUM(fin.f1)                                AS first_number,
    SUM(fin.f2)                                AS second_number,
    SUM(fin.f3)                                AS third_number,
    SUM(fin.fo)                                AS also_ran,
    ROUND(SUM(fin.f1) / COUNT(*) * 100, 1)    AS first_rate,
    ROUND((SUM(fin.f1) + SUM(fin.f2)) / COUNT(*) * 100, 1) AS second_rate,
    ROUND((SUM(fin.f1) + SUM(fin.f2) + SUM(fin.f3)) / COUNT(*) * 100, 1) AS third_rate,
    ROUND(COALESCE(SUM(fin.win_amt),   0) / COUNT(*), 1) AS win_recovery_rate,
    ROUND(COALESCE(SUM(fin.place_amt), 0) / COUNT(*), 1) AS place_recovery_rate
  `);

  // t_sed を派生テーブルで前処理し、CAST/TRIM をまとめる（1回だけ評価）
  const sedDerived = `(
    SELECT course_code, year_code, kai, day_code, race_num, umaban,
      CAST(TRIM(order_of_finish) AS UNSIGNED)         AS fn,
      CAST(TRIM(win)             AS UNSIGNED)         AS win_amt,
      CAST(TRIM(place)           AS UNSIGNED)         AS place_amt,
      CAST(TRIM(order_of_finish) AS UNSIGNED) = 1     AS f1,
      CAST(TRIM(order_of_finish) AS UNSIGNED) = 2     AS f2,
      CAST(TRIM(order_of_finish) AS UNSIGNED) = 3     AS f3,
      CAST(TRIM(order_of_finish) AS UNSIGNED) >= 4    AS fo
    FROM t_sed
    WHERE ijou_kubun IN ('0','')
  ) fin`;

  // 日付範囲あり → STRAIGHT_JOIN で idx_bac_ymd を先頭ドライバーに固定
  // 日付範囲なし → STRAIGHT_JOIN 外してオプティマイザに t_kyi 関数インデックスを使わせる
  const hint = (ymd_from && ymd_to) ? 'STRAIGHT_JOIN' : '';

  let sql = `SELECT ${hint} ${selectParts.join(',\n')}
    FROM t_bac b
    INNER JOIN t_kyi k
      ON  b.course_code = k.course_code AND b.year_code = k.year_code
      AND b.kai = k.kai AND b.day_code = k.day_code AND b.race_num = k.race_num
    INNER JOIN ${sedDerived}
      ON  k.course_code = fin.course_code AND k.year_code = fin.year_code
      AND k.kai = fin.kai AND k.day_code = fin.day_code
      AND k.race_num = fin.race_num AND k.uma_num = fin.umaban
    LEFT JOIN t_cyb c
      ON  k.course_code = c.course_code AND k.year_code = c.year_code
      AND k.kai = c.kai AND k.day_code = c.day_code
      AND k.race_num = c.race_num AND k.uma_num = c.uma_num
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

  const conn = await createConnection();
  try {
    const [rows] = await conn.query<any>(sql, params);
    // レスポンスに集計キーのラベルを付与
    const aggLabels = aggKeys.map((k, i) => ({
      key: `agg_key_${i + 1}`,
      label: AGGREGATE_MAP[k].alias,
    }));
    res.json({ aggLabels, rows });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  } finally {
    await conn.end();
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

  const conn = await createConnection();
  try {
    const isUmanushi = (type === 'umanushi');
    const pattern = isUmanushi ? `%${q.trim()}%` : `${q.trim()}%`;
    const [rows] = await conn.query<any>(
      `SELECT DISTINCT TRIM(\`${col}\`) AS name
       FROM T_KYI
       WHERE \`${col}\` LIKE ?
       ORDER BY name
       LIMIT 20`,
      [pattern]
    );
    res.json(rows.map((r: any) => r.name));
  } finally { await conn.end(); }
});


// ────────────────────────────────────────────────────────────────────────────
// コース別傾向API
// ────────────────────────────────────────────────────────────────────────────

// コース一覧: GET /api/courses
app.get('/api/courses', async (_req, res) => {
  const conn = await createConnection();
  try {
    const [rows] = await conn.query<any>(
      `SELECT course_code, tds_code, distance, total_count
       FROM T_COURSE_FACTOR_AGG
       WHERE factor_type='baseline' AND total_count >= 100
       ORDER BY course_code, tds_code, CAST(distance AS UNSIGNED)`
    );
    res.json(rows);
  } finally { await conn.end(); }
});

// コース分析: GET /api/course-analysis?course_code=05&tds_code=1&distance=1600
app.get('/api/course-analysis', async (req, res) => {
  const { course_code, tds_code, distance } = req.query as Record<string, string>;
  if (!course_code || !tds_code || !distance) {
    res.status(400).json({ error: 'course_code, tds_code, distance は必須です' });
    return;
  }
  const conn = await createConnection();
  try {
    const [rows] = await conn.query<any>(
      `SELECT factor_type, factor_value, total_count, win_count, renso_count, place_count,
              win_rate, renso_rate, place_rate, win_recovery, place_recovery
       FROM T_COURSE_FACTOR_AGG
       WHERE course_code=? AND tds_code=? AND distance=?
       ORDER BY factor_type, factor_value`,
      [course_code, tds_code, distance.padStart(4, ' ')]
    );
    // distance は TRIM済みなのでそのまま試す
    const data = rows.length ? rows : await (async () => {
      const [r2] = await conn.query<any>(
        `SELECT factor_type, factor_value, total_count, win_count, place_count,
                win_rate, place_rate, win_recovery, place_recovery
         FROM T_COURSE_FACTOR_AGG
         WHERE course_code=? AND tds_code=? AND TRIM(distance)=?
         ORDER BY factor_type, factor_value`,
        [course_code, tds_code, distance.trim()]
      );
      return r2;
    })();
    if (!data.length) { res.status(404).json({ error: 'データが見つかりません' }); return; }
    // factor_type 別に整理
    const result: Record<string, any[]> = {};
    for (const row of data) {
      if (!result[row.factor_type]) result[row.factor_type] = [];
      result[row.factor_type].push(row);
    }
    res.json({ course_code, tds_code, distance: distance.trim(), factors: result });
  } finally { await conn.end(); }
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
    const parts = splitAnabaSql(sql);

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
      const conn = await createConnection();
      const [[row]] = await conn.query<any>(
        'SELECT COUNT(*) AS cnt FROM T_ANABA_SCORE'
      );
      await conn.end();
      send(`完了: T_ANABA_SCORE ${Number(row.cnt).toLocaleString()} 件`);
    } catch { /* 無視 */ }

    res.write(`data: ${JSON.stringify({ done: true })}\n\n`);
    res.end();
  })().catch((err) => {
    res.write(`data: ${JSON.stringify({ error: err.message, done: true })}\n\n`);
    res.end();
  });
});

app.listen(PORT, () => {
  console.log(`サーバー起動: http://localhost:${PORT}`);
});
