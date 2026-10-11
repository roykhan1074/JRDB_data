// 表レイアウトの実機検証（CLAUDE.md「UI変更時の必須チェック」の自動化）
// 使い方:
//   node .claude/skills/ui-verify/verify.js --url "http://localhost:3000/entries.html?key=05264308" \
//        [--url ...] [--widths 1600,700,500] [--table "table"] [--wrap ".table-wrap"] \
//        [--wait "#tbody tr"] [--shot .scratch/ui-verify]
// 終了コード: 問題なし=0 / 問題あり=1
const puppeteer = require('puppeteer-core');

const args = { url: [], widths: '1600,700,500', table: 'table', wrap: '.table-wrap', wait: 'tbody tr', shot: '' };
for (let i = 2; i < process.argv.length; i += 2) {
  const k = process.argv[i].replace(/^--/, ''), v = process.argv[i + 1];
  if (k === 'url') args.url.push(v); else args[k] = v;
}
if (!args.url.length) { console.error('--url を指定してください'); process.exit(2); }
const widths = args.widths.split(',').map(Number);
const CHROME = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

function inspect(sel, wrapSel) {
  const px = s => { const m = String(s || '').match(/^([\d.]+)px$/); return m ? parseFloat(m[1]) : (s === '0' ? 0 : null); };
  const tables = [...document.querySelectorAll(sel)].filter(t => t.offsetParent !== null);
  return tables.map((t, ti) => {
    const cols = [...t.querySelectorAll(':scope > colgroup > col')];
    const colW = cols.map(c => px(c.style.width));
    const colSum = colW.reduce((a, b) => a + (b || 0), 0);
    // thead の実効列数（colspan 展開後）: 1行目 + rowspan を考慮した最大値として各行の colspan 合計を計算
    const hrows = [...t.querySelectorAll(':scope > thead > tr')];
    const grid = [];
    hrows.forEach((tr, r) => {
      grid[r] = grid[r] || [];
      let c = 0;
      [...tr.children].forEach(th => {
        while (grid[r][c]) c++;
        const cs = th.colSpan || 1, rs = th.rowSpan || 1;
        for (let dr = 0; dr < rs; dr++) for (let dc = 0; dc < cs; dc++) { grid[r + dr] = grid[r + dr] || []; grid[r + dr][c + dc] = true; }
        c += cs;
      });
    });
    const thEff = Math.max(0, ...grid.map(g => g.length));
    const brows = [...t.querySelectorAll(':scope > tbody > tr')];
    const tdCounts = [...new Set(brows.map(tr => [...tr.children].reduce((a, td) => a + (td.colSpan || 1), 0)))];
    // 見出しの行数
    const headers = [...t.querySelectorAll(':scope > thead th')].map(th => {
      const w = th.getBoundingClientRect().width;
      const text = th.innerText.replace(/\s+/g, '');
      // 非表示列（width:0;font-size:0 の方式）は対象外
      if (w < 4 || !text || parseFloat(getComputedStyle(th).fontSize) === 0) return null;
      const range = document.createRange(); range.selectNodeContents(th);
      const tops = new Set([...range.getClientRects()].filter(r => r.width > 0).map(r => Math.round(r.top)));
      return { text, len: [...text].length, lines: tops.size, w: Math.round(w) };
    }).filter(Boolean);
    // 1行目の td の実際の幅と左位置（col 指定幅との突き合わせ・テーブル間の列位置比較用）
    const first = brows.find(tr => [...tr.children].length === cols.length) || brows[0];
    const tL = t.getBoundingClientRect().left;
    const tdGeo = first ? [...first.children].map(td => { const r = td.getBoundingClientRect(); return [Math.round(r.left - tL), Math.round(r.width)]; }) : [];
    const wrap = t.closest(wrapSel);
    return {
      ti, tableWidthStyle: getComputedStyle(t).width, tableWidth: Math.round(t.getBoundingClientRect().width),
      tableWidthDecl: t.style.width || null,
      colCount: cols.length, colW, colSum, thEff, tdCounts, headers, tdGeo,
      scroll: wrap ? { sw: wrap.scrollWidth, cw: wrap.clientWidth } : null,
    };
  });
}

(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME });
  const page = await browser.newPage();
  const problems = [], warnings = [];
  const P = (m) => { problems.push(m); console.log('  ✗ ' + m); };
  const W = (m) => { warnings.push(m); console.log('  △ ' + m); };
  for (const url of args.url) {
    console.log(`\n=== ${url}`);
    const base = {};
    for (const w of widths) {
      await page.setViewport({ width: w, height: 1000 });
      await page.goto(url, { waitUntil: 'networkidle0', timeout: 120000 });
      if (args.wait) await page.waitForSelector(args.wait, { timeout: 60000 }).catch(() => P(`[${w}px] 待機セレクタ ${args.wait} が出ない`));
      const res = await page.evaluate(inspect, args.table, args.wrap);
      console.log(`[${w}px] テーブル${res.length}個`);
      if (!res.length) P(`[${w}px] テーブル ${args.table} が見つからない`);
      res.forEach(t => {
        const tag = `[${w}px] table#${t.ti}`;
        console.log(`  ${tag}: col=${t.colCount} th実効=${t.thEff} td=${t.tdCounts.join('/')} 幅=${t.tableWidth}px col合計=${t.colSum}px` +
          (t.scroll ? ` 横スクロール=${t.scroll.sw > t.scroll.cw ? 'あり' : 'なし'}(${t.scroll.sw}/${t.scroll.cw})` : ''));
        if (t.colCount !== t.thEff || t.tdCounts.length !== 1 || t.tdCounts[0] !== t.colCount)
          P(`${tag} 列数不一致 col=${t.colCount} th=${t.thEff} td=${t.tdCounts.join('/')}`);
        if (t.colW.some(v => v === null)) P(`${tag} 幅未指定（px以外）の col あり: ${t.colW.map((v, i) => v === null ? i + 1 : null).filter(Boolean).join(',')}列目`);
        // col 指定幅とのずれ: 中身（nowrap の長い文字列・バッジ+padding）が指定幅より広いと列が広がる。
        // テーブルが1つなら見た目は崩れないので警告。複数テーブルのページでは下の列位置比較で問題として出る。
        const tight = [];
        t.tdGeo.forEach(([, tw], i) => {
          const cw = t.colW[i];
          if (cw === null || cw === undefined) return;
          if (cw === 0 ? tw > 3 : Math.abs(tw - cw) > 1) tight.push(`${i + 1}列目 ${cw}→${tw}px`);
        });
        if (tight.length) W(`${tag} col 指定幅より広がった列: ${tight.join(', ')}`);
        if (Math.abs(t.tableWidth - t.colSum) > 1) W(`${tag} テーブル幅 ${t.tableWidth}px ≠ col合計 ${t.colSum}px`);
        t.headers.forEach(h => {
          if (h.len <= 4 && h.lines !== 1) P(`${tag} 見出し「${h.text}」(${h.len}文字) が${h.lines}行（4文字以内は1行）`);
          if (h.len >= 5 && h.lines > 2) P(`${tag} 見出し「${h.text}」(${h.len}文字) が${h.lines}行（最大2行）`);
        });
        if (t.scroll && t.scroll.cw < t.colSum && t.scroll.sw <= t.scroll.cw) P(`${tag} 表示幅が col 合計より狭いのに横スクロールしない`);
      });
      // 同一ページ内の複数テーブルで列位置が揃っているか
      if (res.length > 1) {
        const ref = JSON.stringify(res[0].tdGeo);
        res.slice(1).forEach(t => { if (JSON.stringify(t.tdGeo) !== ref) P(`[${w}px] table#${t.ti} の列位置が table#0 とずれている`); });
      }
      // ビューポート間で見出しの幅が変わっていないか（狭い画面での比例縮小の検出）
      res.forEach(t => {
        const key = t.ti, cur = t.headers.map(h => h.w).join(',');
        if (base[key] === undefined) base[key] = cur;
        else if (base[key] !== cur) P(`[${w}px] table#${t.ti} の見出し幅が ${widths[0]}px のときと違う（縮小されている）`);
      });
      if (args.shot) {
        const fs = require('fs'); fs.mkdirSync(args.shot, { recursive: true });
        const name = `${args.shot}/${args.url.indexOf(url)}_${w}.png`;
        await page.screenshot({ path: name, fullPage: true });
        console.log(`  スクリーンショット: ${name}`);
      }
    }
  }
  await browser.close();
  console.log(`\n問題 ${problems.length}件 / 警告 ${warnings.length}件` + (problems.length ? '' : '（問題なし）'));
  process.exit(problems.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
