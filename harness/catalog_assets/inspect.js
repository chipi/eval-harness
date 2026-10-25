/* eval catalog: the run inspector. Reads ?runs=&baseline=&metric=&rescore= and asks the local
   server (catalog_serve.py) for per-item scores, verdicts and item outputs. What an item is
   called comes from <body data-item>, the command that starts the server from <body data-serve>. */
(function () {
  const ITEM = document.body.dataset.item || 'item', ITEMS = ITEM + 's';
  const SERVE = document.body.dataset.serve || 'evh catalog-serve';
  const app = document.getElementById('app'), pick = document.getElementById('pick');
  const P = new URLSearchParams(location.search);
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const fmt = v => v == null ? '—' : (Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(3));
  // As every command prints a p (stats.fmt_p): four decimals, and "<0.0001" below that.
  const fmtp = p => p == null ? '—' : (p.toFixed(4) === '0.0000' ? '<0.0001' : p.toFixed(4));
  const runs = () => (P.get('runs') || '').split(',').filter(Boolean);
  const go = () => { location.search = P.toString(); };
  const short = a => a.replace(/^runs\//, '');
  const ARMS = window.RUNS || {};

  function picker() {
    const chips = runs().map(r => `<span class="chip pickchip">${esc(short(r))}<button data-rm="${esc(r)}" aria-label="remove">×</button></span>`).join('');
    // Only offer runs that can be compared with what is selected: same dataset_id, or none recorded.
    const all = ARMS, ds = new Set(runs().map(r => all[r] || all[r.split('#')[0]]).filter(Boolean));
    const on = ds.size === 1 ? [...ds][0] : '';
    const opts = Object.entries(all).filter(([r, d]) => !on || !d || d === on)
      .map(([r, d]) => `<option value="${esc(r)}" label="${esc(d || 'no dataset id')}">`).join('');
    const hint = on ? `add a run on ${on}` : 'add a run: type part of its name';
    pick.innerHTML = `<div class="chips">${chips || '<span class="muted">No runs selected.</span>'}</div>
      <form id="add" class="filter"><input list="allruns" id="addrun" placeholder="${esc(hint)}" autocomplete="off">
      <datalist id="allruns">${opts}</datalist><button class="btn" type="submit">Add</button></form>`;
    pick.querySelectorAll('[data-rm]').forEach(b => b.onclick = () => {
      P.set('runs', runs().filter(r => r !== b.dataset.rm).join(',')); P.delete('baseline'); go(); });
    document.getElementById('add').onsubmit = ev => { ev.preventDefault();
      const v = document.getElementById('addrun').value.trim(); if (!v) return;
      P.set('runs', [...new Set([...runs(), v])].join(',')); go(); };
  }

  // Strip what every selected run's label shares, at a _ / · boundary; the full name stays in a tooltip.
  function shorten(full) {
    const ids = Object.keys(full), names = ids.map(i => full[i]);
    if (names.length < 2) return full;
    const cut = (a, b) => { let i = 0; while (i < a.length && i < b.length && a[i] === b[i]) i++; return i; };
    let pre = names.reduce((n, x) => Math.min(n, cut(names[0], x)), Infinity);
    pre = names[0].slice(0, pre).search(/[_\/·][^_\/·]*$/) + 1;
    const rev = names.map(x => [...x].reverse().join(''));
    let suf = rev.reduce((n, x) => Math.min(n, cut(rev[0], x)), Infinity);
    // A shared tail is cut only at a " · " (what they are scored by), never inside the config
    // id: "_v1" is the arm's version, and it stays when every arm happens to share it.
    const tail = suf ? names[0].slice(names[0].length - suf) : '';
    const at = tail.indexOf(' · ');
    suf = at >= 0 ? tail.length - at : 0;
    const out = {};
    ids.forEach((id, k) => { const s = names[k].slice(Math.max(pre, 0), names[k].length - suf) || names[k]; out[id] = s; });
    return out;
  }
  const tip = (full, id) => `title="${esc(full[id] || id)}"`;
  // The catalog's own pages, as catalog_build.slug names them: an arm's and a metric's.
  const slug = s => String(s).replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || 'x';
  const UP = document.body.dataset.up || '';
  const armName = (id, text) => window.CATALOG_PAGES
    ? `<a class="cell-link" href="${UP}a/${slug(id)}.html" title="${esc(id)}">${esc(text)}</a>` : esc(text);

  function verdictChip(v) {
    const cls = v.startsWith('separated: better') ? 'v-better' : v.startsWith('separated: worse') ? 'v-worse' : 'v-none';
    const sym = cls === 'v-better' ? '▲ ' : cls === 'v-worse' ? '▼ ' : '';
    return `<span class="chip ${cls}">${sym}${esc(v)}</span>`;
  }

  async function load() {
    picker();
    if (!runs().length) { app.innerHTML = '<p class="muted">Pick runs from an experiment or dataset page in the catalog ("Inspect runs"), or add them above.</p>'; return; }
    let d;
    try {
      const r = await fetch('/api/compare?' + P.toString());
      d = await r.json();
    } catch (e) {
      app.innerHTML = `<p class="note"><b>No inspector server.</b> Start it with <code>${esc(SERVE)}</code> and open this page from the address it prints.</p>`;
      return;
    }
    if (d.error) { app.innerHTML = `<p class="note"><b>${esc(d.error)}</b></p>`; return; }
    const label = shorten(Object.fromEntries((d.arms || []).map(a => [a.id, a.label])));
    const warn = (d.warnings || []).map(w => `<p class="note">${esc(w)}</p>`).join('');
    if (!d.metrics || !d.metrics.length || d.state === 'not scorable') {
      const pickable = (d.metrics || []).map(m => `<a class="btn" href="?${new URLSearchParams({...Object.fromEntries(P), metric: m.name})}">compare ${esc(m.name)}</a>`).join('');
      const on = new URLSearchParams(P); on.delete('rescore');
      const again = !d.can_rescore || P.get('rescore') !== '0' ? '' : `<a class="btn" href="?${on}">Re-score with the project's scorers</a>`;
      app.innerHTML = `<p class="eyebrow"><span class="num">—</span>not scorable</p>` + warn + `<div class="btns">${again}${pickable}</div>`;
      return;
    }
    const arrow = d.higher_is_better ? '↑ higher is better' : '↓ lower is better';
    const mopts = d.metrics.map(m => `<option value="${esc(m.name)}" ${m.name === d.metric ? 'selected' : ''}>${esc(m.name)}${m.format ? ' (' + esc(m.format) + ')' : ''}${m.archived ? ' (archived reference)' : ''} ${m.lower_is_better ? '↓' : '↑'} · ${m.arms} arm(s)</option>`).join('');
    const bopts = Object.keys(d.series).map(a => `<option value="${esc(a)}" ${a === d.baseline ? 'selected' : ''}>${esc(label[a] || a)}</option>`).join('');
    const resc = P.get('rescore') !== '0';
    const controls = `<div class="controls">
      <label>metric <select id="metric">${mopts}</select></label>
      <label>baseline <select id="baseline">${bopts}</select></label>
      ${d.can_rescore ? `<label class="tick"><input type="checkbox" id="rescore" ${resc ? 'checked' : ''}> re-score what is not on record</label>` : ''}</div>`
      + fieldControls(d);

    const rows = [...d.rows].sort((a, b) => (a.p ?? 9) - (b.p ?? 9));
    // A row's tint says what its scores are measured against, as on the catalog's pages.
    const kind = id => { const a = (d.arms || []).find(x => x.id === id) || {};
      return a.wrote_reference ? 't-author' : a.judge ? 't-judged' : (a.reference || '').startsWith('silver/') ? 't-silver' : ''; };
    // The verdict is the second column, so a phone sees it without scrolling.
    const vt = rows.map(r => `<tr class="${kind(r.arm)}"><td class="mono">${armName(r.arm, label[r.arm] || r.arm)}</td>
      <td>${verdictChip(r.verdict)}${r.n && r.min_p > 0.05 ? ' <small class="muted">' + r.n + ' ' + ITEMS + ' cannot reach 0.05</small>' : ''}</td>
      <td class="num">${r.n}</td><td class="num">${fmt(r.mean)}</td><td class="num">${fmt(r.delta)}</td>
      <td class="num">${r.ci ? (r.ci[0] >= 0 ? '+' : '') + r.ci[0].toFixed(3) + ' to ' + (r.ci[1] >= 0 ? '+' : '') + r.ci[1].toFixed(3) : '—'}</td>
      <td class="num">${r.wins}–${r.losses}${r.ties ? ' (' + r.ties + ' tied)' : ''}</td>
      <td class="num">${fmtp(r.p)}</td><td class="num">${r.threshold ? r.threshold.toFixed(4) : '—'}</td></tr>`).join('');
    const baseMean = d.items.length ? (() => { const v = Object.values(d.series[d.baseline]); return v.reduce((a, b) => a + b, 0) / v.length; })() : null;
    const verdicts = `<div class="scroll-x"><table class="data" data-nopage><thead><tr><th>run vs baseline</th><th>verdict</th><th>${ITEMS}</th><th>mean</th><th>Δ vs baseline</th><th>95% CI of Δ</th><th>wins–losses</th><th>p (exact ≤30)</th><th>Holm threshold</th></tr></thead>
      <tbody>${vt || '<tr><td colspan="9" class="muted">Only the baseline has this metric.</td></tr>'}</tbody></table></div>
      <p class="small muted">Baseline ${armName(d.baseline, label[d.baseline] || d.baseline)}: mean ${fmt(baseMean)}. Holm across ${d.family_size} comparison(s)${P.get('threshold') ? ' (this row\'s threshold carried from the page you came from, so the verdict matches it)' : P.get('family') ? ' (family carried from the page you came from)' : ''}; ${esc(arrow)}. Scores come from: ${esc([...new Set(d.arms.map(a => a.source).filter(Boolean))].join('; '))}.</p>`;

    const arms = Object.keys(d.series), better = d.higher_is_better ? 1 : -1;
    const head = arms.map(a => `<th class="${a === d.baseline ? 'isbase' : ''}">${esc(label[a] || a)}${a === d.baseline ? '<br><small>baseline</small>' : ''}</th>`).join('');
    const body = d.items.map(ep => `<tr data-ep="${esc(ep)}" class="eprow" tabindex="0" aria-label="open ${ITEM} ${esc(ep)}"><td class="mono">${esc(ep)}</td>${arms.map(a => {
      const v = d.series[a][ep], b = d.series[d.baseline][ep];
      if (v == null) return '<td class="num muted">—</td>';
      let mark = '';
      if (a !== d.baseline && b != null && v !== b) mark = (v - b) * better > 0 ? ' <span class="up">▲</span>' : ' <span class="down">▼</span>';
      return `<td class="num">${fmt(v)}${mark}</td>`; }).join('')}</tr>`).join('');
    const eps = `<div class="scroll-x"><table class="data eps"><thead><tr><th>${ITEM}</th>${head}</tr></thead><tbody>${body}</tbody></table></div>
      <p class="small muted">▲ better / ▼ worse than the baseline on that ${ITEM}. Click a row to see the outputs.</p><div id="drill"></div>`;

    // Runs that recorded only a run-level average: listed, never tested.
    const avgs = Object.entries(d.averages || {}).sort((a, b) => (d.higher_is_better ? b[1] - a[1] : a[1] - b[1]));
    const avgTable = !avgs.length ? '' : `<h3 class="sub">Average only · ${avgs.length}: no per-${ITEM} scores, so no test</h3>
      <div class="scroll-x"><table class="data"><thead><tr><th>run</th><th>recorded average</th><th>vs the baseline's mean</th></tr></thead><tbody>${avgs.map(([a, v]) =>
        `<tr><td class="mono">${armName(a, label[a] || a)}</td><td class="num">${fmt(v)}</td><td class="num">${baseMean == null ? '—' : (v - baseMean >= 0 ? '+' : '') + fmt(v - baseMean)}</td></tr>`).join('')}</tbody></table></div>`;
    const mslug = slug(d.metric.split(' vs ')[0]);
    // The metric's own page where the catalog has one; else its row on a metrics page; else plain.
    const mlink = window.CATALOG_PAGES ? `<a class="cell-link" href="${UP}m/${mslug}.html">${esc(d.metric)}</a>`
      : document.querySelector('nav.nav a[href$="metrics.html"]')
      ? `<a class="cell-link" href="${UP}metrics.html#m-${mslug}">${esc(d.metric)}</a>` : esc(d.metric);
    app.innerHTML = controls + warn + `<p class="eyebrow"><span class="num">01</span>verdicts · ${mlink}</p>` + verdicts + conditions(d, label) + avgTable
      + breakdown(d, label)
      + `<p class="eyebrow gap"><span class="num">02</span>analysis</p>` + charts(d, label)
      + `<p class="eyebrow gap"><span class="num">03</span>per ${ITEM} · ${d.items.length}</p>` + eps;
    wireCharts(d, label);
    wireFields(d);
    // Long tables (the per-item one) page 10 at a time; the verdict tables stay whole (data-nopage).
    if (window.paginate) app.querySelectorAll('table.data').forEach(t => window.paginate(t));
    document.getElementById('metric').onchange = ev => { P.set('metric', ev.target.value); go(); };
    document.getElementById('baseline').onchange = ev => { P.set('baseline', ev.target.value); go(); };
    const rs = document.getElementById('rescore');
    if (rs) rs.onchange = ev => { ev.target.checked ? P.delete('rescore') : P.set('rescore', '0'); go(); };
    // The reference the metric names ("<metric> vs <reference>"), else the one the baseline was scored against.
    const ref = (d.metric.split(' vs ')[1] || '').trim() || ((d.arms || []).find(a => a.id === d.baseline) || {}).reference || '';
    app.querySelectorAll('tr.eprow').forEach(tr => {
      tr.onclick = () => drill(tr.dataset.ep, arms, d.baseline, label, ref, tr);
      tr.onkeydown = ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); tr.onclick(); } };
    });
  }


  // ── item fields (ADR-0003): filter the comparison, break it down by a choice or yes/no field ─
  function fieldControls(d) {
    const fs = d.fields || [];
    if (!fs.length) return '';
    const chips = P.getAll('where').map(w => { const [n, v] = [w.slice(0, w.indexOf(':')), w.slice(w.indexOf(':') + 1)];
      const f = fs.find(x => x.name === n) || {};
      return `<span class="chip pickchip">${esc(f.label || n)} = ${esc(v)}<button data-unwhere="${esc(w)}" aria-label="remove filter">×</button></span>`; }).join('');
    const fopts = fs.map(f => `<option value="${esc(f.name)}">${esc(f.label)}</option>`).join('');
    const bopts = '<option value="">none</option>' + fs.filter(f => f.groupable).map(f =>
      `<option value="${esc(f.name)}" ${P.get('by') === f.name ? 'selected' : ''}>${esc(f.label)}</option>`).join('');
    return `<div class="controls">
      <form id="addwhere" class="filter"><label>filter ${ITEMS} by <select id="wfield">${fopts}</select></label>
        <span id="wvalue"></span><button class="btn small" type="submit">Filter</button></form>
      ${fs.some(f => f.groupable) ? `<label>break down by <select id="by">${bopts}</select></label>` : ''}</div>`
      + (chips ? `<div class="chips">${chips}</div>` : '');
  }

  function valueInput(f) {
    if (f.type === 'choice') return `<select id="wv">${(f.values || []).map(v => `<option>${esc(v)}</option>`).join('')}</select>`;
    if (f.type === 'boolean') return '<select id="wv"><option value="true">yes</option><option value="false">no</option></select>';
    const hint = ['number', 'integer', 'duration'].includes(f.type)
      ? (f.type === 'duration' ? 'seconds: 600..  or  ..1800' : 'min..max, or one value') : 'exact value';
    return `<input id="wv" placeholder="${esc(hint)}" autocomplete="off">`;
  }

  function wireFields(d) {
    const fs = d.fields || [], sel = document.getElementById('wfield');
    if (!sel) return;
    const show = () => { document.getElementById('wvalue').innerHTML = valueInput(fs.find(f => f.name === sel.value) || {}); };
    sel.onchange = show; show();
    document.getElementById('addwhere').onsubmit = ev => { ev.preventDefault();
      const v = (document.getElementById('wv').value || '').trim(); if (!v) return;
      P.append('where', sel.value + ':' + v); go(); };
    app.querySelectorAll('[data-unwhere]').forEach(b => b.onclick = () => {
      const keep = P.getAll('where').filter(w => w !== b.dataset.unwhere); P.delete('where'); keep.forEach(w => P.append('where', w)); go(); });
    const by = document.getElementById('by');
    if (by) by.onchange = () => { by.value ? P.set('by', by.value) : P.delete('by'); go(); };
  }

  // What the compared runs were measured under, from their fingerprints: one line when it all
  // matches, else the fields that differ, arm by arm, and what that does to the comparison.
  function conditions(d, label) {
    const c = d.conditions;
    if (!c || !c.fields) return '';
    const what = 'machine, library versions, harness, scorer, items, reference bytes';
    if (!c.differ.length) return `<p class="small muted conds">Same conditions: all ${c.fields} recorded fields match across these runs (${what}).</p>`;
    const arms = Object.keys(d.series);
    const short = v => v == null ? '—' : /^[0-9a-f]{40,}$/.test(v) ? v.slice(0, 12) + '…' : v;
    const head = arms.map(a => `<th>${esc(label[a] || a)}${a === d.baseline ? '<br><small>baseline</small>' : ''}</th>`).join('');
    const body = c.differ.map(f => {
      const base = f.values[d.baseline];
      return `<tr><td class="mono">${esc(f.name)}</td>${arms.map(a => `<td class="mono${a !== d.baseline && f.values[a] !== base ? ' diff' : ''}" title="${esc(f.values[a] ?? '')}">${esc(short(f.values[a]))}</td>`).join('')}</tr>`;
    }).join('');
    const warns = (c.warnings || []).map(w => `<p class="note">${esc(w)}</p>`).join('');
    return `<h3 class="sub">Conditions · ${c.differ.length} of ${c.fields} fields differ <small>(${what})</small></h3>`
      + warns
      + `<div class="scroll-x"><table class="data conds"><thead><tr><th>field</th>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  function breakdown(d, label) {
    const b = d.breakdown;
    if (!b) return '';
    const f = (d.fields || []).find(x => x.name === d.by) || {label: d.by};
    const name = g => f.type === 'boolean' ? (g === 'true' ? 'yes' : 'no') : g;
    const rows = b.groups.flatMap(g => g.rows.map(r => `<tr><td>${esc(name(g.group))} <small class="muted">${g.items} ${ITEMS}</small></td>
      <td class="mono">${armName(r.arm, label[r.arm] || r.arm)}</td><td>${verdictChip(r.verdict)}${r.n && r.min_p > 0.05 ? ' <small class="muted">' + r.n + ' ' + ITEMS + ' cannot reach 0.05</small>' : ''}</td><td class="num">${r.n}</td>
      <td class="num">${fmt(r.delta)}</td><td class="num">${r.wins}–${r.losses}</td><td class="num">${fmtp(r.p)}</td>
      <td class="num">${r.threshold ? r.threshold.toFixed(4) : '—'}</td></tr>`)).join('');
    return `<h3 class="sub">By ${esc(f.label)} · ${b.groups.length} group(s)</h3>
      <div class="scroll-x"><table class="data" data-nopage><thead><tr><th>${esc(f.label)}</th><th>run vs baseline</th><th>verdict</th><th>${ITEMS}</th><th>Δ vs baseline</th><th>wins–losses</th><th>p</th><th>Holm threshold</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="8" class="muted">No group has two arms to test.</td></tr>'}</tbody></table></div>
      <p class="small muted">The same paired test within each group, Holm-corrected over all ${b.family_size} tests together: each extra group is another chance of a false "separated", so the thresholds are stricter than for one group alone.</p>`;
  }

  function fieldsTable(fs) {
    if (!fs || !fs.length) return '';
    // Returns HTML: every value escaped; a link only for an http(s) URL (an adapter's own data
    // could carry any scheme, and a javascript: href would run on click).
    const clock = v => { const s = Math.round(v); return `${Math.floor(s / 3600)}:${String(Math.floor(s % 3600 / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`; };
    const show = f => f.type === 'boolean' ? (f.value ? 'yes' : 'no')
      : f.type === 'duration' && typeof f.value === 'number' ? clock(f.value)
      : f.type === 'url' && /^https?:\/\//i.test(String(f.value)) ? `<a href="${esc(f.value)}" rel="noopener noreferrer" target="_blank">${esc(f.value)}</a>`
      : esc(f.value) + (f.unit ? ' ' + esc(f.unit) : '');
    return `<table class="data fields"><tbody>${fs.map(f => `<tr><th>${esc(f.label)}</th><td>${show(f)}</td></tr>`).join('')}</tbody></table>`;
  }

  // ── charts: inline SVG, the catalog's tokens; colours follow the run, never its rank ─────────
  const SLOTS = 8;
  function colorOf(d) {
    const out = {}; let i = 0;
    Object.keys(d.series).forEach(a => {
      if (a === d.baseline) out[a] = 'var(--baseline)';
      else out[a] = i < SLOTS ? `var(--s${++i})` : 'var(--muted)';
    });
    return out;
  }
  // Below 700px the charts use a narrow layout: labels sit above each row and values at its end.
  const NARROW = window.matchMedia('(max-width: 700px)').matches;
  const W = NARROW ? 420 : 1000, LEFT = NARROW ? 8 : 250, RIGHT = NARROW ? 8 : 30;
  const ROW = NARROW ? 46 : 34;
  // A value printed at the end of a row: right of the plot when wide, on the label line when narrow.
  const rowValue = (y, xWide, text) => NARROW
    ? `<text class="rv" x="${W - RIGHT}" y="${y - 13}" text-anchor="end">${text}</text>`
    : `<text class="rv" x="${xWide}" y="${y + 4}">${text}</text>`;
  function scale(lo, hi, a, b) { const span = hi - lo || 1; return v => a + (v - lo) / span * (b - a); }
  function ticks(lo, hi, n = 5) {
    const raw = (hi - lo) / n || 1, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
    const out = []; for (let t = Math.ceil(lo / step) * step; t <= hi + 1e-12; t += step) out.push(+t.toFixed(10));
    return out;
  }
  const tfmt = v => Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : +v.toFixed(3) + '';
  function axis(x, lo, hi, top, bottom) {
    return ticks(lo, hi).map(t => `<line class="grid" x1="${x(t)}" x2="${x(t)}" y1="${top}" y2="${bottom}"/>
      <text class="tick" x="${x(t)}" y="${bottom + 16}" text-anchor="middle">${tfmt(t)}</text>`).join('');
  }
  function rowLabel(y, text, full, color) {
    const max = NARROW ? 40 : 34, t = text.length > max ? text.slice(0, max - 1) + '…' : text;
    const ly = NARROW ? y - 13 : y + 4, cy = NARROW ? y - 17 : y;
    return `<g><title>${esc(full)}</title><circle cx="${NARROW ? 5 : 12}" cy="${cy}" r="5" fill="${color}"/>
      <text class="rl" x="${NARROW ? 14 : 24}" y="${ly}">${esc(t)}</text></g>`;
  }
  const dot = (cx, cy, color, tip, r = 4.5) =>
    `<circle class="dot" cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${r}" fill="${color}" data-tip="${esc(tip)}"><title>${esc(tip)}</title></circle>`;
  const mean = xs => xs.reduce((a, b) => a + b, 0) / xs.length;
  // deterministic vertical jitter so tied scores stay visible
  const jit = (ep, k) => { let h = 0; for (const c of ep + k) h = (h * 31 + c.charCodeAt(0)) % 997; return (h / 997 - 0.5) * 12; };

  function spread(d, label, col) {
    const mu = a => mean(Object.values(d.series[a]));
    const dirn = d.higher_is_better || d.neutral ? -1 : 1;
    const others = Object.keys(d.series).filter(a => a !== d.baseline).sort((a, b) => dirn * (mu(a) - mu(b)));
    const arms = [d.baseline, ...others];
    const vals = arms.flatMap(a => Object.values(d.series[a]));
    if (!vals.length) return '';
    let lo = Math.min(...vals), hi = Math.max(...vals); const pad = (hi - lo) * 0.06 || 0.05; lo -= pad; hi += pad;
    const RH = ROW, top = NARROW ? 30 : 14, H = top + arms.length * RH + 30, x = scale(lo, hi, LEFT, W - RIGHT - (NARROW ? 0 : 80));
    const bm = mean(Object.values(d.series[d.baseline]));
    let g = axis(x, lo, hi, top - 6, top + arms.length * RH);
    g += `<line class="basemean" x1="${x(bm)}" x2="${x(bm)}" y1="${top - 6}" y2="${top + arms.length * RH}"/>`;
    arms.forEach((a, i) => {
      const y = top + i * RH + RH / 2, v = d.series[a], ys = Object.values(v);
      g += rowLabel(y, label[a] || a, a, col[a]);
      g += Object.entries(v).map(([ep, s]) => dot(x(s), y + jit(ep, a), col[a], `${label[a] || a} · ${ep}: ${tfmt(s)}`)).join('');
      if (ys.length) g += `<line class="meanmark" x1="${x(mean(ys))}" x2="${x(mean(ys))}" y1="${y - 11}" y2="${y + 11}" data-tip="${esc((label[a] || a) + ' mean ' + tfmt(mean(ys)))}"/>`
        + rowValue(y, W - RIGHT - 66, tfmt(mean(ys)));
    });
    return `<figure class="chart"><figcaption><b>Spread per run</b> · every ${ITEM}'s ${esc(d.metric)}, one row per run, baseline first, then best mean first; the bar and the number are the run's mean, the dashed line the baseline's mean.</figcaption>
      <div class="scroll-x"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Spread of per-${ITEM} scores per run">${g}</svg></div></figure>`;
  }

  function deltas(d, label, col) {
    const base = d.series[d.baseline], arms = Object.keys(d.series).filter(a => a !== d.baseline);
    const rows = arms.map(a => [a, Object.entries(d.series[a]).filter(([ep]) => ep in base).map(([ep, s]) => [ep, s - base[ep]])]).filter(r => r[1].length);
    if (!rows.length) return '';
    const md = r => mean(r[1].map(z => z[1]));
    rows.sort((p, q) => (d.higher_is_better || d.neutral ? md(q) - md(p) : md(p) - md(q)));
    const m = Math.max(...rows.flatMap(r => r[1].map(x => Math.abs(x[1])))) * 1.08 || 1;
    const RH = ROW, top = NARROW ? 30 : 14, H = top + rows.length * RH + 30, x = scale(-m, m, LEFT, W - RIGHT - (NARROW ? 0 : 160));
    const verdict = Object.fromEntries(d.rows.map(r => [r.arm, r]));
    let g = axis(x, -m, m, top - 6, top + rows.length * RH);
    g += `<line class="zero" x1="${x(0)}" x2="${x(0)}" y1="${top - 6}" y2="${top + rows.length * RH}"/>`;
    rows.forEach(([a, ds], i) => {
      const y = top + i * RH + RH / 2, mu = mean(ds.map(z => z[1])), r = verdict[a] || {};
      g += rowLabel(y, label[a] || a, a, col[a]);
      g += ds.map(([ep, z]) => dot(x(z), y + jit(ep, a), col[a], `${label[a] || a} · ${ep}: ${z >= 0 ? '+' : ''}${tfmt(z)} vs baseline`)).join('');
      g += `<line class="meanmark" x1="${x(mu)}" x2="${x(mu)}" y1="${y - 11}" y2="${y + 11}"/>`;
      // Words, not arrows: for a lower-is-better metric an up-arrow beside a negative number reads wrong.
      const v = r.verdict || '';
      const word = !v.startsWith('separated') ? '·' : d.neutral ? (mu > 0 ? 'higher' : 'lower') : v.includes('better') ? '✓ better' : '✗ worse';
      g += rowValue(y, W - RIGHT - 150, `${mu >= 0 ? '+' : ''}${tfmt(mu)} ${r.wins != null ? r.wins + '–' + r.losses : ''} ${word}`);
    });
    const side = d.neutral ? '← lower · higher →' : d.higher_is_better ? '← worse · better →' : '← better · worse →';
    return `<figure class="chart"><figcaption><b>Difference from the baseline</b> · each ${ITEM}'s ${esc(d.metric)} minus the baseline's (${esc(label[d.baseline] || d.baseline)}); bar = mean difference; right column: mean difference, wins–losses, and ✓ better / ✗ worse when separated after Holm. <span class="muted">${side}</span></figcaption>
      <div class="scroll-x"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Per-${ITEM} difference from the baseline">${g}</svg></div></figure>`;
  }

  function scatter(d, label, col, xm) {
    const xs = d.shape[xm]; if (!xs) return '';
    const pts = []; Object.keys(d.series).forEach(a => Object.entries(d.series[a]).forEach(([ep, y]) => { const v = (xs[a] || {})[ep]; if (v != null) pts.push([a, ep, v, y]); }));
    if (pts.length < 3) return '';
    const H = NARROW ? 330 : 420, top = 14, bottom = H - 40, L = NARROW ? 46 : 70;
    let x0 = Math.min(...pts.map(p => p[2])), x1 = Math.max(...pts.map(p => p[2])), y0 = Math.min(...pts.map(p => p[3])), y1 = Math.max(...pts.map(p => p[3]));
    const px = (x1 - x0) * 0.05 || 1, py = (y1 - y0) * 0.06 || 0.05; x0 = Math.max(0, x0 - px); x1 += px; y0 -= py; y1 += py;
    const x = scale(x0, x1, L, W - RIGHT), y = scale(y0, y1, bottom, top);
    let g = ticks(x0, x1).map(t => `<line class="grid" x1="${x(t)}" x2="${x(t)}" y1="${top}" y2="${bottom}"/><text class="tick" x="${x(t)}" y="${bottom + 16}" text-anchor="middle">${tfmt(t)}</text>`).join('');
    g += ticks(y0, y1).map(t => `<line class="grid" x1="${L}" x2="${W - RIGHT}" y1="${y(t)}" y2="${y(t)}"/><text class="tick" x="${L - 8}" y="${y(t) + 4}" text-anchor="end">${tfmt(t)}</text>`).join('');
    g += '<g class="faded">' + pts.map(([a, ep, xv, yv]) => dot(x(xv), y(yv), col[a], `${label[a] || a} · ${ep}: ${tfmt(yv)} at ${tfmt(xv)} ${esc(xm)}`, 5)).join('') + '</g>';
    // Each run's average position: the length/quality trade-off per run, the decision question.
    Object.keys(d.series).forEach(a => {
      const mine = pts.filter(p => p[0] === a); if (!mine.length) return;
      const cx = x(mean(mine.map(p => p[2]))), cy = y(mean(mine.map(p => p[3])));
      g += `<g class="centroid" data-tip="${esc((label[a] || a) + ' average: ' + tfmt(mean(mine.map(p => p[3]))) + ' at ' + tfmt(mean(mine.map(p => p[2]))))}">`
        + `<path d="M${cx - 9} ${cy}H${cx + 9}M${cx} ${cy - 9}V${cy + 9}" stroke="${col[a]}"/>`
        + `<text class="cl" x="${cx + 11}" y="${cy - 6}">${esc((label[a] || a).slice(0, 24))}</text></g>`;
    });
    g += `<text class="axl" x="${(L + W - RIGHT) / 2}" y="${H - 6}" text-anchor="middle">${esc(xm)} (per ${ITEM})</text>`;
    return `<div class="scroll-x"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Score against ${esc(xm)}">${g}</svg></div>`;
  }

  function legend(d, label, col) {
    // The swatch colour is set after rendering (wireCharts), never as a style="" attribute,
    // which a Content-Security-Policy without 'unsafe-inline' refuses.
    return '<p class="legend">' + Object.keys(d.series).map(a => `<span title="${esc(a)}"><i data-swatch="${esc(col[a])}"></i>${esc(label[a] || a)}${a === d.baseline ? ' <small>baseline</small>' : ''}</span>`).join('') + '</p>';
  }

  function charts(d, label) {
    const col = colorOf(d), keys = Object.keys(d.shape || {});
    const xm = keys[0];
    const sc = xm ? `<figure class="chart"><figcaption><b>${esc(d.metric)} against <select id="xmetric">${keys.map(k => `<option ${k === xm ? 'selected' : ''}>${esc(k)}</option>`).join('')}</select></b> · faded dots: one per run per ${ITEM}; cross: each run's average, the length/quality trade-off per run.</figcaption><div id="scatterbox">${scatter(d, label, col, xm)}</div></figure>` : '';
    return legend(d, label, col) + spread(d, label, col) + deltas(d, label, col) + sc;
  }

  function wireCharts(d, label) {
    app.querySelectorAll('i[data-swatch]').forEach(i => { i.style.background = i.dataset.swatch; });
    const tip = document.getElementById('ctip') || Object.assign(document.body.appendChild(document.createElement('div')), {id: 'ctip'});
    // Every mark with a tooltip also has an SVG <title>: a screen reader names it, not only the pointer.
    app.querySelectorAll('svg [data-tip]').forEach(el => {
      if (!el.querySelector(':scope > title')) { const t = document.createElementNS('http://www.w3.org/2000/svg', 'title'); t.textContent = el.dataset.tip; el.prepend(t); }
    });
    app.querySelectorAll('svg').forEach(svg => {
      svg.addEventListener('pointermove', ev => { const t = ev.target.closest('[data-tip]'); if (!t) { tip.classList.remove('on'); return; }
        tip.textContent = t.dataset.tip; tip.classList.add('on');
        tip.style.left = Math.min(ev.clientX + 14, innerWidth - tip.offsetWidth - 8) + 'px'; tip.style.top = (ev.clientY + 14) + 'px'; });
      svg.addEventListener('pointerleave', () => tip.classList.remove('on'));
    });
    const sel = document.getElementById('xmetric');
    if (sel) sel.onchange = () => { document.getElementById('scatterbox').innerHTML = scatter(d, label, colorOf(d), sel.value); wireCharts(d, label); };
  }

  function words(t) { return String(t || '').split(/(\s+)/); }
  function diff(a, b) {  // word-level LCS: what b adds (ins) and drops (del) relative to a
    const A = words(a), B = words(b), n = A.length, m = B.length;
    if (n * m > 4e6) return esc(b);
    const L = Array.from({length: n + 1}, () => new Uint16Array(m + 1));
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    let i = 0, j = 0, out = '';
    while (i < n && j < m) {
      if (A[i] === B[j]) { out += esc(B[j]); i++; j++; }
      else if (L[i + 1][j] >= L[i][j + 1]) { if (A[i].trim()) out += `<del>${esc(A[i])}</del>`; i++; }
      else { out += B[j].trim() ? `<ins>${esc(B[j])}</ins>` : esc(B[j]); j++; }
    }
    while (i < n) { if (A[i].trim()) out += `<del>${esc(A[i])}</del>`; i++; }
    while (j < m) { out += B[j].trim() ? `<ins>${esc(B[j])}</ins>` : esc(B[j]); j++; }
    return out;
  }

  function view(v, base) {
    if (!v || v.kind === 'none') return `<p class="muted">${esc((v && v.note) || 'No stored output.')}</p>`;
    const show = x => typeof x === 'number' ? (x >= 100 ? x.toFixed(0) : x.toFixed(1)) : x;
    const info = v.info && Object.keys(v.info).length ? `<p class="small muted">${esc(Object.entries(v.info).map(([k, x]) => k.replace(/_/g, ' ') + ' ' + show(x)).join(' · '))}</p>` : '';
    if (v.kind === 'text') {
      const t = DIFF && base && base.kind === 'text' && base !== v ? diff(base.text, v.text) : esc(v.text);
      return info + `<div class="outtext">${t}</div><p class="small muted">${String(v.text || '').split(/\s+/).filter(Boolean).length} words</p>`;
    }
    if (v.kind === 'insights') return info + `<p class="small muted">${v.items.length} insights · ${v.quotes} quotes</p><ol class="outlist">${v.items.map(x => `<li>${x.grounded ? '<span title="grounded" class="up">●</span> ' : '<span title="not grounded" class="muted">○</span> '}${esc(x.text)}</li>`).join('')}</ol>`;
    if (v.kind === 'nodes') return info + Object.entries(v.groups).map(([k, xs]) => `<p class="small"><b>${esc(k)}</b> · ${xs.length}</p><p class="chips">${xs.map(x => `<span class="chip">${esc(x)}</span>`).join('')}</p>`).join('');
    if (v.kind === 'entities') return info + `<p class="small muted">${v.items.length} entities</p><p class="chips">${v.items.map(x => `<span class="chip">${esc(x)}</span>`).join('')}</p>`;
    return '';
  }

  let DIFF = false;
  async function drill(ep, arms, baseline, label, ref, tr) {
    document.querySelectorAll('tr.eprow.on').forEach(x => x.classList.remove('on')); tr.classList.add('on');
    const box = document.getElementById('drill');
    box.innerHTML = '<p class="muted">Loading outputs…</p>';
    const q = new URLSearchParams({arms: arms.join(','), item: ep});
    if (ref) q.set('ref', ref);
    const d = await (await fetch('/api/item?' + q)).json();
    if (d.error) { box.innerHTML = `<p class="note">${esc(d.error)}</p>`; return; }
    const base = d.views[baseline];
    const cols = Object.entries(d.views).map(([a, v]) => `<div class="outcol"><h3>${esc(label[a] || a)}${a === baseline ? ' <small class="muted">baseline</small>' : ''}</h3>${view(v, a === baseline ? null : base)}</div>`).join('');
    const refcol = d.reference && d.reference.view && d.reference.view.kind !== 'none' ? `<div class="outcol refcol"><h3>${esc(d.reference.id)} <small class="muted">reference</small></h3>${view(d.reference.view, null)}</div>` : '';
    const hasText = Object.values(d.views).some(v => v && v.kind === 'text');
    const toggle = hasText ? `<label class="tick small"><input type="checkbox" id="difft" ${DIFF ? 'checked' : ''}> mark what each run <ins>adds</ins> and <del>drops</del> against the baseline (useful between near-identical outputs, noisy between independent ones)</label>` : '';
    // The item itself, what every arm read (the local inspector only); folded when it is long.
    const src = d.source && d.source.kind !== 'none' && d.source.text
      ? `<details class="srcbox"${d.source.text.length <= 1500 ? ' open' : ''}><summary>the ${ITEM} itself <small class="muted">${d.source.text.length.toLocaleString()} characters, what every arm read</small></summary><div class="outtext">${esc(d.source.text)}</div></details>` : '';
    box.innerHTML = `<p class="eyebrow gap"><span class="num">04</span>${ITEM} · ${esc(ep)}</p>${fieldsTable(d.fields)}${src}${toggle}<div class="outgrid">${refcol}${cols}</div>`;
    const t = document.getElementById('difft');
    if (t) t.onchange = () => { DIFF = t.checked; drill(ep, arms, baseline, label, ref, tr); };
    box.scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  load();
})();
