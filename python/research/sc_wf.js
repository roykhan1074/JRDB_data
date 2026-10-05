// 注目馬複合シグナル sc の walk-forward 計算（研究用・DB書き込みなし）
// combo / kyusha は日単位 trailing（当日より前の確定結果のみ）。
// EX指数は引数 "ho" で T_ANABA_SCORE_HO（2023年までで集計したholdout版）、省略時は全期間版。
// sc 計算は entries.html の evaluateRaceSignals() をそのまま抽出して使う。
// 実行: node python/research/sc_wf.js [ho]   → .scratch/sc_wf_{ho|lk}.json
require('dotenv').config();
const mysql = require('mysql2/promise');
const fs = require('fs');
const MODE = process.argv[2] || 'lk';
const USE_HO = MODE !== 'lk';
const HO_TBL = (MODE === 'wf2' || MODE === 'wf3' || MODE === 'wf4') ? 'T_ANABA_SCORE_WF2' : MODE === 'wf' ? 'T_ANABA_SCORE_WF' : MODE === 'ho25' ? 'T_ANABA_SCORE_HO25' : 'T_ANABA_SCORE_HO';
const HM_TBL = (MODE === 'wf3' || MODE === 'wf4') ? 'T_HONMEI_SCORE_WF2' : MODE === 'wf3' ? 'T_HONMEI_SCORE_WF2' : (MODE === 'wf' || MODE === 'wf2') ? 'T_HONMEI_SCORE_WF' : MODE === 'hoall' ? 'T_HONMEI_SCORE_HO' : 'T_HONMEI_SCORE';

const html = fs.readFileSync('public/entries.html', 'utf8');
function extract(name) {
  const i = html.indexOf('function ' + name + '(');
  let d = 0; const j = html.indexOf('{', i);
  for (let k = j; k < html.length; k++) {
    if (html[k] === '{') d++;
    else if (html[k] === '}') { d--; if (d === 0) return html.slice(i, k + 1); }
  }
}
let MYOMI_ON = false;
eval(extract('anabaMyomiGrade').replace('function anabaMyomiGrade', 'function anabaMyomiGradeReal') +
  '\nfunction anabaMyomiGrade(a,b,c){ return MYOMI_ON ? anabaMyomiGradeReal(a,b,c) : null; }\n' +
  extract('evaluateRaceSignals') + '\nglobalThis.ev = evaluateRaceSignals;');

(async () => {
  const conn = await mysql.createConnection({
    host: process.env.DB_HOST, port: +process.env.DB_PORT, user: process.env.DB_USER,
    password: process.env.DB_PASS, database: process.env.DB_NAME,
  });
  const J = a => `${a}.course_code=k.course_code AND ${a}.year_code=k.year_code AND ${a}.kai=k.kai AND ${a}.day_code=k.day_code AND ${a}.race_num=k.race_num`;
  const [rows] = await conn.query(`
    SELECT b.ymd, b.\`class\` AS cls, TRIM(b.tds_code) AS tds, CAST(TRIM(b.distance) AS UNSIGNED) AS dist,
           k.course_code, k.year_code, k.kai, k.day_code, k.race_num, k.uma_num,
           k.kijun_odds, k.kijun_ninki, k.joho_index, k.idm, k.in_idm, k.goal_juni, k.ten_index_juni, k.agari_index_juni, k.ten_index, k.agari_index,
           k.kyakushitsu, k.chokyo_yajirushi, k.kishu_code, k.trainer_code, k.kyusha_index,
           c.oi_index, c.shiage_index,
           ans.course_score AS anaba_course_score, hms.course_score AS honmei_course_score,
           s.order_of_finish, s.ijou_kubun, s.win AS win_pay, s.place AS place_pay
    FROM T_BAC b
    JOIN T_KYI k ON ${J('b')}
    LEFT JOIN T_CYB c ON ${J('c')} AND c.uma_num=k.uma_num
    LEFT JOIN ${USE_HO ? HO_TBL : 'T_ANABA_SCORE'} ans ON ${J('ans')} AND ans.uma_num=k.uma_num
    LEFT JOIN ${HM_TBL} hms ON ${J('hms')} AND hms.uma_num=k.uma_num
    LEFT JOIN T_SED s ON ${J('s')} AND s.umaban=k.uma_num
    WHERE TRIM(b.tds_code) IN ('1','2')
    ORDER BY b.ymd`);
  await conn.end();

  const days = new Map();
  for (const r of rows) {
    if (!days.has(r.ymd)) days.set(r.ymd, new Map());
    const rk = `${r.course_code}${r.year_code}${r.kai}${r.day_code}${r.race_num}`;
    const dm = days.get(r.ymd);
    if (!dm.has(rk)) dm.set(rk, []);
    dm.get(rk).push(r);
  }
  const res = r => {
    const fin = parseInt(String(r.order_of_finish ?? '').trim());
    if (isNaN(fin) || fin <= 0) return null;
    const ij = String(r.ijou_kubun ?? '').trim();
    const normal = ij === '0' || ij === '';
    return { fin, win: normal ? (Number(r.win_pay) || 0) : 0, place: normal ? (Number(r.place_pay) || 0) : 0 };
  };
  const combo = new Map(), kyu = new Map(), out = [];
  for (const [ymd, races] of [...days.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    for (const hs of races.values()) {
      for (const r of hs) {
        const c = combo.get(`${r.kishu_code}|${r.trainer_code}`);
        r.combo_n = c ? c.n : 0; r.combo_place_rr = c && c.n ? c.pay / c.n : 0;
        const k = kyu.get(r.trainer_code);
        r.kyusha_anaba_n = k ? k.n : 0; r.kyusha_anaba_place_rr = k && k.n ? k.pay / k.n : 0;
      }
      const evm = new Map(ev(hs).evaluated.map(h => [h.umaNum, h]));
      for (const r of hs) {
        const rr = res(r); if (!rr) continue;
        const h = evm.get(parseInt(r.uma_num)); if (!h) continue;
        // シグナル内訳（カテゴリごとの重み）。調教は「矢印」と「追切」を分ける。矢印↓の減点は sigs に入らないので別出し
        const w = cat => h.sigs.filter(s => s.cat === cat).reduce((a, s) => a + s.w, 0);
        const yaji = String(r.chokyo_yajirushi ?? '').trim();
        out.push({ y: +ymd.slice(0, 4), sc: h.sc, odds: Number(r.kijun_odds), shinba: String(r.cls).trim() === 'A1' ? 1 : 0,
                   ex: r.anaba_course_score === null ? null : Number(r.anaba_course_score),
                   hm: r.honmei_course_score === null ? null : Number(r.honmei_course_score),
                   rid: `${r.course_code}${r.year_code}${r.kai}${r.day_code}${r.race_num}`, uma: parseInt(r.uma_num),
                   ab: h.abilityOk ? 1 : 0,
                   s_idx: w('idx'), s_combo: w('combo'), s_kyusha: w('kyusha'), s_joho: w('joho'), s_gap: w('gap'),
                   s_pace: w('pace'), s_goal: w('goal'),
                   s_yaji: h.sigs.filter(s => s.cat === 'chokyo' && s.text.startsWith('調教矢印')).reduce((a, s) => a + s.w, 0),
                   s_oi: h.sigs.filter(s => s.cat === 'chokyo' && s.text.startsWith('追切')).reduce((a, s) => a + s.w, 0),
                   s_down: (yaji === '4' || yaji === '5') ? -2 : 0,
                   agari: parseInt(String(r.agari_index_juni ?? '').trim()) || 99,
                   tds: r.tds, dist: Number(r.dist), course: r.course_code,
                   ...rr });
      }
    }
    for (const hs of races.values()) for (const r of hs) {
      const rr = res(r); if (!rr) continue;
      const ck = `${r.kishu_code}|${r.trainer_code}`;
      const c = combo.get(ck) ?? { n: 0, pay: 0 }; c.n++; c.pay += rr.place; combo.set(ck, c);
      const odds = Number(r.kijun_odds), ki = Number(r.kyusha_index);
      if (r.kyusha_index !== null && !isNaN(ki) && ki >= 0 && odds >= 15) {
        const k = kyu.get(r.trainer_code) ?? { n: 0, pay: 0 }; k.n++; k.pay += rr.place; kyu.set(r.trainer_code, k);
      }
    }
  }
  fs.writeFileSync(`.scratch/sc_wf_${MODE}.json`, JSON.stringify(out));
  console.error('written', out.length);
})();
