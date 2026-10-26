// Baseline page: every answer on the baseline's dataset (other baselines first, then runs), its
// mean per-item difference from the baseline, and the paired verdict (Holm across all of
// them). The interval is the one that agrees with the paired test; below 6 items no interval
// exists, so the range of per-item differences is drawn instead. Reads /api/compare.
(function () {
  // The API sits beside the catalog's root (assets/ is in that root): /api/ when the catalog is
  // served at a host's root (evh catalog-serve), /catalog/api/ under evals.humancopilot.eu.
  const API = new URL('../api/', document.currentScript.src).href;
  const ITEM = document.body.dataset.item || 'item', ITEMS = ITEM + 's';
  const SERVE = document.body.dataset.serve || 'evh catalog-serve';
  const box = document.getElementById('forest');
  if (!box) return;
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const base = box.dataset.baseline;
  const runs = box.dataset.runs.split(',').filter(Boolean);
  const siblings = new Set((box.dataset.baselines || '').split(',').filter(Boolean));
  const parse = v => { try { return JSON.parse(v || '{}'); } catch (e) { return {}; } };
  const families = parse(box.dataset.families), authors = parse(box.dataset.authors);
  const fmt = v => v == null ? '—' : Math.abs(v) >= 10 ? v.toFixed(1) : Math.abs(v) >= 1 ? v.toFixed(2) : v.toFixed(3);
  const sgn = v => (v >= 0 ? '+' : '') + fmt(v);
  const pfmt = p => p == null ? '' : p < 0.001 ? p.toExponential(0) : p.toFixed(3);

  async function load(metric) {
    box.innerHTML = '<p class="muted">Scoring every answer on this dataset against the baseline… the first load can take a minute.</p>';
    const q = new URLSearchParams({runs: [...runs, base].join(','), baseline: base, rescore: '1'});
    if (metric) q.set('metric', metric);
    let d;
    try { d = await (await fetch(API + 'compare?' + q)).json(); }
    catch (e) { box.innerHTML = `<p class="note"><b>No inspector server.</b> This chart is computed live: run <code>${esc(SERVE)}</code> and open the page from the address it prints.</p>`; return; }
    if (d.error) { box.innerHTML = `<p class="note"><b>${esc(d.error)}</b></p>`; return; }
    const warn = (d.warnings || []).map(w => `<li>${esc(w)}</li>`).join('');
    const notes = warn ? `<details class="fnotes" ${d.state !== 'compared' ? 'open' : ''}><summary>${(d.warnings || []).length} note(s) on what is and is not shown</summary><ul>${warn}</ul></details>` : '';
    if (d.state === 'not scorable') { box.innerHTML = '<p class="eyebrow">not scorable</p>' + notes; return; }
    if (!(d.rows || []).length && !Object.keys(d.averages || {}).length) { box.innerHTML = `<p class="muted">No answer on this dataset shares a per-${ITEM} metric with the baseline.</p>` + notes; return; }
    if (d.baseline !== base) { box.innerHTML = `<p class="note">This baseline has no per-${ITEM} scores, so nothing can be compared with it.</p>` + notes; return; }
    draw(d, notes);
  }

  // Strip what every label shares at a _ boundary (the full name stays in the tooltip).
  function shortener(names) {
    if (names.length < 3) return n => n;
    let pre = names.reduce((a, n) => { let i = 0; while (i < a.length && a[i] === n[i]) i++; return a.slice(0, i); });
    pre = pre.slice(0, pre.lastIndexOf('_') + 1);
    return n => (pre && n.startsWith(pre) ? '…' + n.slice(pre.length) : n);
  }

  function draw(d, notes) {
    const label = Object.fromEntries((d.arms || []).map(a => [a.id, a.label]));
    const source = Object.fromEntries((d.arms || []).map(a => [a.id, a.source || '']));
    const bs = d.series[base] || {};
    const deltasOf = arm => Object.entries(d.series[arm] || {}).filter(([ep]) => ep in bs).map(([ep, v]) => v - bs[ep]);
    const tested = d.rows.filter(r => r.delta != null);
    const isSib = r => siblings.has(r.arm.split('#')[0]);
    const sib = tested.filter(isSib).sort((a, b) => b.delta - a.delta);
    const rest = tested.filter(r => !isSib(r)).sort((a, b) => b.delta - a.delta);
    const bv = Object.values(bs), bmean = bv.reduce((a, b) => a + b, 0) / (bv.length || 1);
    const avgs = Object.entries(d.averages || {}).map(([arm, v]) => ({arm, v, delta: v - bmean})).sort((a, b) => b.delta - a.delta);
    const shortP = shortener(Object.values(label));
    // Narrow: room for 30 characters before the value on the same line; the tooltip has the rest.
    const short = n => { const t = shortP(n); return window.matchMedia('(max-width: 700px)').matches && t.length > 30 ? t.slice(0, 29) + '…' : t; };
    const better = d.higher_is_better, neutral = d.neutral;
    // A silver can favour its author's own family: mark answers from that family.
    const refFam = authors[(d.metric.split(' vs ')[1] || '')] || '';
    const sameFam = arm => refFam && families[arm.split('#')[0]] === refFam;
    const ext = tested.flatMap(r => { if (r.ci) return r.ci; const ds = deltasOf(r.arm); return ds.length ? [Math.min(...ds), Math.max(...ds)] : [r.delta]; });
    const lo = Math.min(0, ...ext, ...avgs.map(a => a.delta)), hi = Math.max(0, ...ext, ...avgs.map(a => a.delta));
    const pad = (hi - lo) * 0.06 || 0.01, x0 = lo - pad, x1 = hi + pad;
    // Below 700px: labels above each row and the right column on the label line, so it fits.
    const NARROW = window.matchMedia('(max-width: 700px)').matches;
    const W = NARROW ? 420 : 1000, L = NARROW ? 8 : 330, R = NARROW ? 8 : 230, RH = NARROW ? 40 : 24, HEAD = 30;
    const ry = cy => (NARROW ? cy - 12 : cy + 4);  // label/value baseline for a row centred at cy
    const vx = NARROW ? W - R : W - R + 14, va = NARROW ? ' text-anchor="end"' : '';
    const groups = [[sib, 'other baselines on this dataset'], [rest, 'runs'], [avgs, `average only: no per-${ITEM} scores, so no interval and no test`]].filter(gr => gr[0].length);
    const H = HEAD + groups.reduce((h, gr) => h + 26 + gr[0].length * RH, 0) + 34;
    const x = v => L + (v - x0) / (x1 - x0) * (W - L - R);
    const raw = (x1 - x0) / 5, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
    let g = '';
    for (let t = Math.ceil(x0 / step) * step; t <= x1; t += step) {
      const tv = +t.toFixed(10);
      g += `<line class="grid" x1="${x(tv)}" x2="${x(tv)}" y1="${HEAD - 6}" y2="${H - 30}"/>`;
      g += `<text class="tick" x="${x(tv)}" y="${HEAD - 12}" text-anchor="middle">${sgn(tv)}</text><text class="tick" x="${x(tv)}" y="${H - 14}" text-anchor="middle">${sgn(tv)}</text>`;
    }
    g += `<line class="zero" x1="${x(0)}" x2="${x(0)}" y1="${HEAD - 6}" y2="${H - 30}"/>`;
    const maxN = tested.length ? Math.max(...tested.map(r => r.n)) : 0;
    const word = r => {
      if (!r.verdict.startsWith('separated')) return ['·', ''];
      if (neutral) return [r.delta > 0 ? 'higher' : 'lower', ''];
      return r.verdict.includes('better') ? ['✓ better', 'good'] : ['✗ worse', 'bad'];
    };
    let y = HEAD;
    for (const [rows, title] of groups) {
      g += `<text class="gl" x="0" y="${y + 16}">${esc(title)} (${rows.length})</text>`;
      y += 26;
      for (const r of rows) {
        const cy = y + RH / 2, name = label[r.arm] || r.arm, src = source[r.arm] || '';
        if (title.startsWith('average')) {
          const cx = x(r.delta);
          const dy = NARROW ? cy + 6 : cy;
          g += `<g class="frow avg"><title>${esc(name)}\nrecorded average ${fmt(r.v)} vs the baseline's ${fmt(bmean)} (Δ ${sgn(r.delta)}); no per-${ITEM} scores, not tested</title>`
            + `<text class="rl" x="0" y="${ry(cy)}">${esc(short(name))}</text><path class="pt" d="M${cx} ${dy - 6}L${cx + 6} ${dy}L${cx} ${dy + 6}L${cx - 6} ${dy}Z"/>`
            + `<text class="rv" x="${vx}" y="${ry(cy)}"${va}>◇ ${sgn(r.delta)}  average</text></g>`;
        } else {
          const ds = deltasOf(r.arm), [w, cls] = word(r);
          const href = '../inspect.html?' + new URLSearchParams({runs: [r.arm, base].join(','), baseline: base, metric: d.metric, rescore: '1', family: String(d.family_size), ...(r.threshold ? {threshold: String(r.threshold)} : {})});
          const iv = r.ci ? `95% interval ${sgn(r.ci[0])} to ${sgn(r.ci[1])}` : `no interval on ${r.n} ${ITEMS}; per-${ITEM} range ${ds.length ? sgn(Math.min(...ds)) + ' to ' + sgn(Math.max(...ds)) : '—'}`;
          const tip = `${name}\n${d.metric}: ${fmt(r.mean)} vs ${fmt(r.baseline_mean)} (Δ ${sgn(r.delta)}) on ${r.n} ${ITEMS}; ${iv}\nwins–losses ${r.wins}–${r.losses}${r.ties ? ' (' + r.ties + ' tied)' : ''}; ${r.verdict}${r.p != null ? ', p ' + pfmt(r.p) : ''} (Holm across ${d.family_size})\nscore: ${src || 'unknown source'}`;
          g += `<a href="${esc(href)}"><g class="frow"><title>${esc(tip)}</title><rect x="0" y="${y}" width="${W}" height="${RH}" class="hit"/>`
            + `<text class="rl" x="0" y="${ry(cy)}">${esc(short(name))}</text>`;
          const dy = NARROW ? cy + 6 : cy;
          if (r.ci) g += `<line class="ci" x1="${x(r.ci[0])}" x2="${x(r.ci[1])}" y1="${dy}" y2="${dy}"/>`;
          else if (ds.length > 1) g += `<line class="range" x1="${x(Math.min(...ds))}" x2="${x(Math.max(...ds))}" y1="${dy}" y2="${dy}"/>`;
          g += `<circle class="pt ${cls}" cx="${x(r.delta)}" cy="${dy}" r="5"/>`;
          const tag = (src.startsWith('re-scored') ? ' ↻' : '') + (sameFam(r.arm) ? ' ⚑' : '');
          g += `<text class="rv" x="${vx}" y="${ry(cy)}"${va}>${sgn(r.delta)}  ${r.wins}–${r.losses}  ${esc(w)}${tag}</text></g></a>`;
        }
        y += RH;
      }
    }
    const metrics = (d.metrics || []).filter(m => !m.neutral && m.baseline_has && m.arms > 1 && !(d.shape || {})[m.name]);
    const sel = metrics.length > 1 ? ` <select id="fmetric">${metrics.map(m => `<option value="${esc(m.name)}" ${m.name === d.metric ? 'selected' : ''}>${esc(m.name)}${m.format ? ' (' + esc(m.format) + ')' : ''}${m.archived ? ' (archived reference)' : ''}</option>`).join('')}</select>` : ` ${esc(d.metric)}`;
    const dir = neutral ? 'a count: left lower, right higher, neither better' : better ? 'right is better' : 'left is better';
    const how = maxN && maxN < 6
      ? `<br><b>With ${maxN} ${ITEMS} nothing here can be called a difference</b> (the smallest attainable p is over 0.05): the dotted line is the range of per-${ITEM} differences and the numbers are wins–losses. Read it as direction only.`
      : ' The line is the 95% interval that agrees with the paired test: zero outside it means the test separates before correction.';
    box.innerHTML = `<figure class="chart"><figcaption><b>Every answer against this baseline</b> ·${sel} · dot = mean per-${ITEM} difference, ${dir}. `
      + `Right column: difference, wins–losses, verdict (Holm across all ${d.family_size} answers on this dataset; the same correction carries into the inspector when you click a row). ↻ = re-scored live with the project's scorer.${refFam ? ` ⚑ = same model family (${esc(refFam)}) as the reference's author, which may favour it.` : ''}${how}</figcaption>`
      + `${notes}<div class="scroll-x"><svg class="forest" viewBox="0 0 ${W} ${H}" role="img" aria-label="Answers against this baseline">${g}</svg></div></figure>`;
    const s = document.getElementById('fmetric');
    if (s) s.onchange = () => load(s.value);
  }
  load('');
})();
