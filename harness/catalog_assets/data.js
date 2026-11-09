/* eval catalog: the data page (UXS-004). What the project keeps under data/, in either store, from the local
   server's /api/data/; a project's settings created, changed and deleted there. State in the URL:
   ?path=<folder or file>, &edit=1 (the setting's form), &new=1 (a new setting in a settings folder). A setting is
   shown and entered as a form (data_form.js), never as YAML text. Writes carry the
   X-EVH-Data header (ADR-0027); the server takes them on this machine only, with its token (RFC-026), a cookie set
   by the Configure link `evh catalog-serve` prints. */
(function () {
  const API = document.body.dataset.api || '/api/';
  const SERVE = document.body.dataset.serve || 'evh catalog-serve';
  const app = document.getElementById('app'), badge = document.getElementById('store');
  const P = new URLSearchParams(location.search);
  const count = (n, word) => `${Number(n).toLocaleString()} ${word}${n === 1 ? '' : 's'}`;
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const size = n => n == null ? '' : n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`;
  const href = (o) => '?' + new URLSearchParams(Object.entries(o).filter(([, v]) => v !== '' && v != null));
  const NEEDS = `<p class="dm-notice">Managing data needs <code>${esc(SERVE)}</code> on this machine.</p>`;

  async function get(route, q) {
    const r = await fetch(API + 'data/' + route + (q ? '?' + new URLSearchParams(q) : ''), {cache: 'no-store'});
    const body = await r.json().catch(() => ({error: `the server answered ${r.status}`}));
    if (!r.ok) throw Object.assign(new Error(body.error || r.status), {status: r.status, kind: body.kind});
    return body;
  }
  async function write(method, route, q, json) {
    const r = await fetch(API + 'data/' + route + '?' + new URLSearchParams(q), {
      method, body: json === undefined ? undefined : JSON.stringify(json), cache: 'no-store',
      headers: {'X-EVH-Data': '1', 'Content-Type': 'application/json; charset=utf-8'},
    });
    const body = await r.json().catch(() => ({error: `the server answered ${r.status}`}));
    if (!r.ok) throw Object.assign(new Error(body.error || r.status), {status: r.status, kind: body.kind});
    return body;
  }

  function crumbs(path, last) {
    const parts = path ? path.split('/') : [];
    const out = [`<a href="${href({})}">data</a>`];
    parts.forEach((p, i) => {
      const at = parts.slice(0, i + 1).join('/');
      out.push(i === parts.length - 1 && !last ? `<span>${esc(p)}</span>` : `<a href="${href({path: at})}">${esc(p)}</a>`);
    });
    if (last) out.push(`<span class="muted">${esc(last)}</span>`);
    return `<p class="dm-crumbs">${out.join(' <span class="muted">/</span> ')}</p>`;
  }
  const note = () => {
    const n = P.get('note');
    return n ? `<p class="dm-note" role="status">${esc(n)}</p>` : '';
  };
  const fail = e => `<p class="dm-notice">${esc(e.message)}</p>`;

  // ── 01 the overview ──────────────────────────────────────────────────────────────────────────────────────────
  async function overview() {
    const o = await get('store');
    const tiles = o.settings.map(s => {
      const target = s.folder === 'validate.json' ? (s.files ? href({path: s.folder}) : href({path: '', new: '1', folder: s.folder})) : href({path: s.folder});
      return `<a class="tile dm-tile" data-group="data" href="${target}"><span class="dm-n">${s.files}</span>`
        + `<strong>${esc(s.folder)}</strong><span class="muted small">${esc(s.kind)}</span></a>`;
    }).join('');
    const data = o.data.length ? o.data.map(d => `<li><a href="${href({path: d.folder})}">${esc(d.folder)}</a>`
      + ` <span class="muted">${count(d.files, 'file')}${d.kind !== d.folder ? ' · ' + esc(d.kind) : ''}</span></li>`).join('') : '<li class="muted">nothing yet</li>';
    app.innerHTML = note()
      + `<form class="dm-find" role="search"><label class="sr" for="dm-q">Find a file</label>`
      + `<input id="dm-q" name="q" type="search" placeholder="find a file by name…" value="${esc(P.get('q') || '')}" autocomplete="off"></form>`
      + `<div id="dm-hits"></div>`
      + `<h2 class="dm-h">Settings <span class="muted dm-sub">you can edit these</span></h2><div class="tiles dm-tiles">${tiles}</div>`
      + `<h2 class="dm-h">Data <span class="muted dm-sub">written by evh commands; read-only here</span></h2><ul class="dm-data">${data}</ul>`;
    const q = document.getElementById('dm-q'), hits = document.getElementById('dm-hits');
    let t = null;
    const find = async () => {
      const v = q.value.trim();
      if (v.length < 2) { hits.innerHTML = ''; return; }
      try {
        const r = await get('find', {q: v});
        hits.innerHTML = r.total ? `<ul class="dm-hits">${r.paths.map(p => `<li><a href="${href({path: p})}">${esc(p)}</a></li>`).join('')}</ul>`
          + (r.total > r.paths.length ? `<p class="muted small">and ${r.total - r.paths.length} more</p>` : '')
          : `<p class="muted">No file matches ${esc(v)}.</p>`;
      } catch (e) { hits.innerHTML = fail(e); }
    };
    q.addEventListener('input', () => { clearTimeout(t); t = setTimeout(find, 200); });
    q.form.addEventListener('submit', ev => { ev.preventDefault(); find(); });
    if (q.value) find();
  }

  // ── 02 a folder ──────────────────────────────────────────────────────────────────────────────────────────────
  async function folder(path, ls) {
    const offset = ls.offset, settings = ls.settings_folder;
    const rows = ls.entries.map(e => {
      if (e.type === 'run') {
        const del = `<button type="button" class="btn small dm-del" data-run="${esc(e.path)}">delete</button>`;
        return `<tr><td><a href="${href({path: e.path})}">${esc(e.name)}/</a></td><td>run · ${esc(e.dataset ?? '—')}`
          + ` · ${e.items ?? '—'} items${e.finished ? '' : ' · not finished'}</td><td class="nowrap">${esc(e.made ?? '')}</td><td>${del}</td></tr>`;
      }
      if (e.type === 'folder') return `<tr><td><a href="${href({path: e.path})}">${esc(e.name)}/</a></td><td>${count(e.files, 'file')}</td><td></td><td></td></tr>`;
      return `<tr><td><a href="${href({path: e.path})}">${esc(e.name)}</a></td><td class="nowrap">${size(e.size)}</td><td class="nowrap">${esc(e.modified)}</td><td></td></tr>`;
    }).join('');
    const pager = ls.total > ls.entries.length ? `<p class="pager small muted">Showing ${offset + 1}–${offset + ls.entries.length} of ${ls.total}`
      + (offset > 0 ? ` <a class="btn small" href="${href({path, offset: Math.max(0, offset - 500)})}">previous</a>` : '')
      + (offset + ls.entries.length < ls.total ? ` <a class="btn small" href="${href({path, offset: offset + 500})}">next</a>` : '') + '</p>' : '';
    const add = (settings ? `<a class="btn dm-new" href="${href({path, new: '1'})}">+ New ${esc(ls.kind)}</a>` : '')
      + (ls.also_new ? ` <a class="btn dm-new-policy" href="${href({path, new: '1', folder: ls.also_new})}">+ New goal policy</a>` : '');
    app.innerHTML = `<div class="dm-head">${crumbs(path)}${add}</div>` + note()
      + (ls.entries.length ? `<div class="scroll-x"><table class="dm-table"><thead><tr><th>name</th><th>what</th><th>modified</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>${pager}`
        : `<p class="muted">Nothing in ${esc(path)} yet.${settings ? ' Its first setting creates it.' : ''}</p>`)
      + `<div id="dm-panel"></div>`;
    app.querySelectorAll('.dm-del').forEach(b => b.addEventListener('click', () => confirmRun(b.dataset.run, path)));
  }

  // ── 03 a file ────────────────────────────────────────────────────────────────────────────────────────────────
  const runsNote = (n, more) => n ? `<p class="dm-warn small">${count(n, 'run')} ${n === 1 ? 'was' : 'were'} made with this config; they keep the settings they recorded.${more ? ' A change applies to the next run.' : ''}</p>` : '';
  async function file(path) {
    const f = await get('file', {path});
    const head = `<div class="dm-head">${crumbs(path)}`
      + (f.editable ? `<span class="btns"><a class="btn" href="${href({path, edit: '1'})}">Edit</a>`
        + `<button type="button" class="btn dm-del-file">Delete</button></span>` : '') + '</div>';
    const meta = `<p class="dm-meta small"><span>${size(f.size)}</span> · <span>${esc(f.modified)}</span> · `
      + `<span title="${esc(f.sha256)}">sha256 ${esc(f.sha256.slice(0, 12))}</span> · <span class="badge">${f.editable ? esc(f.setting_kind || 'setting') : esc(f.kind)}</span></p>`;
    let body;
    if (f.editable) {
      let fields;
      try {
        const spec = await get('form', {path});
        fields = runsNote(spec.runs_made, false) + `<div class="df-show">${window.EVHForm.view(spec)}</div>`;
      } catch (e) { fields = fail(e); }
      body = fields + `<details class="dm-stored"><summary>the file as stored</summary><pre class="dm-text" tabindex="0">${esc(f.text)}</pre></details>`;
    } else {
      body = `<p class="dm-ro small">${f.kind === 'code' ? 'Code is never edited here.' : `Written by <code>${esc(f.written_by)}</code>; it is not edited here.`}`
        + (f.run ? ` <a href="inspect.html?runs=${encodeURIComponent(f.run)}">inspect this run</a>` : '') + '</p>'
        + (f.text == null ? `<p class="muted">binary, ${f.size.toLocaleString()} bytes</p>` : `<pre class="dm-text" tabindex="0">${esc(f.text)}</pre>`);
    }
    app.innerHTML = head + note() + meta + body + '<div id="dm-panel"></div>';
    const del = app.querySelector('.dm-del-file');
    if (del) del.addEventListener('click', () => confirmFile(path));
  }

  // ── 04 the form, 05 a new setting ────────────────────────────────────────────────────────────────────────────
  async function editor(path, isNew) {
    const folderName = isNew ? (P.get('folder') || path) : null;
    const spec = isNew ? await get('form', {new: folderName}) : await get('form', {path});
    const isPolicy = spec.folder === 'validate.json' || spec.folder === 'goals/policy.yaml';
    const isConfig = spec.folder === 'configs';
    const nameRow = isNew && isConfig
      ? `<div class="df-row dm-filename" data-at="(file)"><label class="df-label" for="dm-name">file name <span class="df-req">*</span></label><div class="df-ctl">`
        + `<span class="dm-name"><span class="muted">configs/</span><input id="dm-name" type="text" pattern="[A-Za-z0-9_.-]+" autocomplete="off"><span class="muted">.yaml</span></span>`
        + `<p class="df-help">The arm's file; its config_id below is its identity, and can carry a version (tickets_lead1_v1).</p><p class="df-err" hidden></p></div></div>` : '';
    app.innerHTML = `<div class="dm-head">${crumbs(isNew ? (spec.folder === 'validate.json' ? '' : spec.folder.split('/')[0]) : path, isNew ? 'new ' + spec.kind : 'editing')}</div>`
      + runsNote(spec.runs_made, true) + nameRow + '<div id="dm-form"></div>'
      + `<div id="dm-result" role="status"></div><p class="btns"><button type="button" class="btn primary" id="dm-save">${isNew ? 'Create' : 'Save'}</button>`
      + `<button type="button" class="btn" id="dm-cancel">Cancel</button></p><div id="dm-panel"></div>`;
    const form = window.EVHForm.edit(document.getElementById('dm-form'), spec);
    const result = document.getElementById('dm-result'), nm = document.getElementById('dm-name');
    // the list of problems is the last save's: an edit makes it stale, so it goes (each field's own message too)
    ['input', 'change'].forEach(ev => app.addEventListener(ev, e => { if (e.target.closest('#dm-form, .dm-filename')) result.innerHTML = ''; }));
    const target = () => {
      if (isPolicy) return spec.folder;
      if (!isNew) return path;
      const stem = isConfig ? (nm.value || '').trim() : String(form.values()[spec.id_key] || '').trim();
      return stem ? `${spec.folder}/${stem}.yaml` : '';
    };
    const showProblems = list => {
      const shown = form.problems(list);
      result.innerHTML = `<div class="dm-bad"><p>Not saved: ${count(list.length, 'problem')} to fix.</p><ul>`
        + shown.map((x, i) => `<li><a href="#" data-i="${i}">${esc(x.where)}</a>: ${esc(x.message)}</li>`).join('') + '</ul></div>';
      result.querySelectorAll('a[data-i]').forEach(a => a.addEventListener('click', ev => {
        ev.preventDefault();
        const t = shown[Number(a.dataset.i)].target;
        if (t) { t.scrollIntoView({block: 'center'}); t.querySelector('input, select, textarea, button')?.focus(); }
      }));
      result.scrollIntoView({block: 'nearest'});
    };
    document.getElementById('dm-save').addEventListener('click', async () => {
      const to = target();
      if (!to) {
        const field = isConfig ? 'the file name' : spec.id_key;
        result.innerHTML = `<div class="dm-bad"><p>Not saved: give it ${esc(field)} first; it names the file.</p></div>`;
        return;
      }
      try {
        const q = {path: to};
        if (isNew) q.new = '1';
        const r = await write('PUT', 'form', q, form.values());
        if (!r.saved) { showProblems(r.problems); return; }
        const said = isNew ? 'Created' : r.unchanged ? 'Nothing changed' : 'Saved';
        location.href = href({path: r.path, note: `${said}. sha256 ${r.sha256.slice(0, 12)}`});
      } catch (e) { result.innerHTML = fail(e); }
    });
    document.getElementById('dm-cancel').addEventListener('click', () => {
      const back = isNew ? href({path: spec.folder === 'validate.json' ? '' : spec.folder.split('/')[0]}) : href({path});
      if (!form.changed() && !(nm && nm.value)) { location.href = back; return; }
      const panel = document.getElementById('dm-panel');
      panel.innerHTML = `<div class="dm-confirm"><p>Discard your changes?</p><p class="btns"><a class="btn danger" href="${back}">Discard</a>`
        + `<button type="button" class="btn" id="dm-keep">Keep editing</button></p></div>`;
      document.getElementById('dm-keep').addEventListener('click', () => { panel.innerHTML = ''; });
    });
    (nm || document.querySelector('#dm-form input, #dm-form select, #dm-form textarea'))?.focus();
  }

  // ── 06 deleting ──────────────────────────────────────────────────────────────────────────────────────────────
  function confirmPanel(question, onYes) {
    const panel = document.getElementById('dm-panel');
    panel.innerHTML = `<div class="dm-confirm" role="alertdialog" aria-label="Confirm delete"><p>${question}</p>`
      + `<p class="btns"><button type="button" class="btn danger" id="dm-yes">Delete</button><button type="button" class="btn" id="dm-no">Cancel</button></p></div>`;
    panel.scrollIntoView({block: 'nearest'});
    document.getElementById('dm-no').addEventListener('click', () => { panel.innerHTML = ''; });
    document.getElementById('dm-yes').addEventListener('click', async () => {
      try { await onYes(); } catch (e) { panel.innerHTML = fail(e); }
    });
  }
  function confirmFile(path) {
    confirmPanel(`Delete <code>${esc(path)}</code>? This cannot be undone.`, async () => {
      await write('DELETE', 'file', {path});
      const up = path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '';
      location.href = href({path: up, note: `Deleted ${path}.`});
    });
  }
  async function confirmRun(path, back) {
    let s;
    try { s = await get('run', {path}); } catch (e) { document.getElementById('dm-panel').innerHTML = fail(e); return; }
    confirmPanel(`Delete the run <code>${esc(path)}</code>? Its record and ${count(s.files, 'file')}, ${count(s.outputs, 'output')} and `
      + `${count(s.rows, 'row')} go. This cannot be undone.`, async () => {
      await write('DELETE', 'file', {path});
      location.href = href({path: back, note: `Deleted the run ${path}.`});
    });
  }

  // ── the catalog's rebuild: its other pages are built ahead; after a change they show it once rebuilt ─────────
  async function rebuildLine(start) {
    let el = document.getElementById('dm-rebuild');
    if (!el) {
      el = document.createElement('p');
      el.id = 'dm-rebuild'; el.className = 'dm-rebuild small';
      el.setAttribute('role', 'status');
      (badge || app).insertAdjacentElement('afterend', el);
    }
    let r;
    try { r = start ? await write('POST', 'rebuild', {}) : await get('rebuild'); } catch (e) { el.textContent = e.message; return; }
    const btn = '<button type="button" class="btn small" id="dm-rebuild-go">Rebuild the catalog</button>';
    if (r.state === 'running') {
      el.innerHTML = `Rebuilding the catalog… <span class="muted">(${Math.round(Date.now() / 1000 - r.started)} s)</span>`;
      setTimeout(() => rebuildLine(false), 2000);
      return;
    }
    if (r.state === 'done') el.innerHTML = `Rebuilt in ${r.seconds} s: the catalog's pages show the project's data as it is now. ${btn}`;
    else if (r.state === 'failed') el.innerHTML = `The rebuild failed; the catalog is the one built ${esc(r.built || 'before')}. ${btn}<pre class="dm-text">${esc(r.tail || '')}</pre>`;
    else el.innerHTML = `The catalog's pages were built ${esc(r.built || '(not yet)')}; a change made here shows there once it is rebuilt. ${btn}`;
    document.getElementById('dm-rebuild-go').addEventListener('click', () => rebuildLine(true));
  }

  // ── the router ───────────────────────────────────────────────────────────────────────────────────────────────
  async function main() {
    let o;
    try { o = await get('store'); } catch (e) { app.innerHTML = e.status === 401 ? fail(e) : NEEDS; return; }
    if (badge) badge.innerHTML = o.store === 'sqlite'
      ? `store: SQLite · <code>${esc(o.database)}</code> · ${size(o.database_bytes)}` : 'store: files';
    const path = (P.get('path') || '').replace(/^\/+|\/+$/g, '');
    rebuildLine(false);
    try {
      if (P.get('new') === '1') return await editor(path, true);
      if (!path) return await overview();
      if (P.get('edit') === '1') return await editor(path, false);
      const ls = await get('list', {path, offset: P.get('offset') || 0});
      return ls.file ? await file(path) : await folder(path, ls);
    } catch (e) { app.innerHTML = (path ? crumbs(path) : '') + fail(e); }
  }
  main();
})();
