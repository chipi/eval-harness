/* eval catalog: the data page (UXS-004). What the project keeps under data/, in either store, from the local
   server's /api/data/; a project's settings created, changed and deleted there. State in the URL:
   ?path=<folder or file>, &edit=1 (the editor), &new=1 (a new setting in a settings folder). Writes carry the
   X-EVH-Data header (ADR-0027); the server takes them on this machine only. */
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
  async function write(method, route, q, text) {
    const r = await fetch(API + 'data/' + route + '?' + new URLSearchParams(q), {
      method, body: text, cache: 'no-store',
      headers: {'X-EVH-Data': '1', 'Content-Type': 'text/plain; charset=utf-8'},
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
    const add = settings ? `<a class="btn dm-new" href="${href({path, new: '1'})}">+ New ${esc(ls.kind)}</a>` : '';
    app.innerHTML = `<div class="dm-head">${crumbs(path)}${add}</div>` + note()
      + (ls.entries.length ? `<div class="scroll-x"><table class="dm-table"><thead><tr><th>name</th><th>what</th><th>modified</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>${pager}`
        : `<p class="muted">Nothing in ${esc(path)} yet.${settings ? ' Its first setting creates it.' : ''}</p>`)
      + `<div id="dm-panel"></div>`;
    app.querySelectorAll('.dm-del').forEach(b => b.addEventListener('click', () => confirmRun(b.dataset.run, path)));
  }

  // ── 03 a file ────────────────────────────────────────────────────────────────────────────────────────────────
  async function file(path) {
    const f = await get('file', {path});
    const head = `<div class="dm-head">${crumbs(path)}`
      + (f.editable ? `<span class="btns"><a class="btn" href="${href({path, edit: '1'})}">Edit</a>`
        + `<button type="button" class="btn dm-del-file">Delete</button></span>` : '') + '</div>';
    const meta = `<p class="dm-meta small"><span>${size(f.size)}</span> · <span>${esc(f.modified)}</span> · `
      + `<span title="${esc(f.sha256)}">sha256 ${esc(f.sha256.slice(0, 12))}</span> · <span class="badge">${f.editable ? 'setting' : esc(f.kind)}</span></p>`;
    const who = f.editable ? (f.runs_made ? `<p class="muted small">${count(f.runs_made, 'run')} ${f.runs_made === 1 ? 'was' : 'were'} made with this config; they keep the settings they recorded.</p>` : '')
      : `<p class="dm-ro small">${f.kind === 'code' ? 'Code is never edited here.' : `Written by <code>${esc(f.written_by)}</code>; it is not edited here.`}`
        + (f.run ? ` <a href="inspect.html?runs=${encodeURIComponent(f.run)}">inspect this run</a>` : '') + '</p>';
    const body = f.text == null ? `<p class="muted">binary, ${f.size.toLocaleString()} bytes</p>` : `<pre class="dm-text" tabindex="0">${esc(f.text)}</pre>`;
    app.innerHTML = head + note() + meta + who + body + '<div id="dm-panel"></div>';
    const del = app.querySelector('.dm-del-file');
    if (del) del.addEventListener('click', () => confirmFile(path));
  }

  // ── 04 editing, 05 a new setting ─────────────────────────────────────────────────────────────────────────────
  async function editor(path, isNew) {
    let text = '', runs = 0, folderName = path, name = '';
    if (isNew) {
      folderName = P.get('folder') || path;
      if (folderName === 'validate.json') { text = '{\n}\n'; }
    } else {
      const f = await get('file', {path});
      if (!f.editable) { location.replace(href({path})); return; }
      text = f.text; runs = f.runs_made || 0;
    }
    const isPolicy = folderName === 'validate.json';
    const nameRow = isNew && !isPolicy ? `<p class="dm-name"><label for="dm-name">Name</label> <input id="dm-name" placeholder="the setting's id" `
      + `pattern="[A-Za-z0-9_.-]+" autocomplete="off"> <span class="muted small">.yaml, its id</span></p>` : '';
    app.innerHTML = `<div class="dm-head">${crumbs(isNew ? (isPolicy ? '' : folderName) : path, isNew ? 'new' : 'editing')}</div>`
      + (runs ? `<p class="dm-warn small">${count(runs, 'run')} ${runs === 1 ? 'was' : 'were'} made with this config; they keep the settings they recorded. A change applies to the next run.</p>` : '')
      + nameRow + `<label class="sr" for="dm-edit">The setting's text</label><textarea id="dm-edit" class="dm-edit" spellcheck="false">${esc(text)}</textarea>`
      + `<p class="btns"><button type="button" class="btn" id="dm-check">Check</button>`
      + `<button type="button" class="btn primary" id="dm-save" disabled>${isNew ? 'Create' : 'Save'}</button>`
      + `<button type="button" class="btn" id="dm-cancel">Cancel</button></p><div id="dm-result" role="status"></div><div id="dm-panel"></div>`;
    const ta = document.getElementById('dm-edit'), save = document.getElementById('dm-save');
    const result = document.getElementById('dm-result'), nm = document.getElementById('dm-name');
    const original = text;
    let checked = null;
    const target = () => isPolicy ? 'validate.json' : (isNew ? `${folderName}/${(nm.value || '').trim()}.yaml` : path);
    if (isNew && nm) {
      nm.addEventListener('input', async () => {
        checked = null; save.disabled = true;
        const id = nm.value.trim();
        if (id && (ta.value === '' || ta.dataset.templated === '1')) {
          try { ta.value = (await get('template', {folder: folderName, id})).text; ta.dataset.templated = '1'; } catch (e) { result.innerHTML = fail(e); }
        }
      });
      nm.focus();
    }
    ta.addEventListener('input', () => { checked = null; save.disabled = true; ta.dataset.templated = '0'; result.innerHTML = ''; });
    document.getElementById('dm-check').addEventListener('click', async () => {
      if (isNew && !isPolicy && !(nm.value || '').trim()) { result.innerHTML = '<p class="dm-bad">Give it a name first: its id.</p>'; return; }
      try {
        const r = await write('POST', 'check', {path: target()}, ta.value);
        if (r.problems.length) {
          result.innerHTML = `<ul class="dm-bad">${r.problems.map(x => `<li>${esc(x)}</li>`).join('')}</ul>`;
          checked = null; save.disabled = true;
        } else {
          result.innerHTML = `<p class="dm-good">✓ It passes the check: ${esc(r.checked)}.</p>`;
          checked = ta.value; save.disabled = false;
        }
      } catch (e) { result.innerHTML = fail(e); }
    });
    save.addEventListener('click', async () => {
      if (checked !== ta.value) { save.disabled = true; return; }
      try {
        const q = {path: target()};
        if (isNew) q.new = '1';
        const f = await write('PUT', 'file', q, ta.value);
        location.href = href({path: f.path, note: `${isNew ? 'Created' : 'Saved'}. sha256 ${f.sha256.slice(0, 12)}`});
      } catch (e) { result.innerHTML = fail(e); }
    });
    document.getElementById('dm-cancel').addEventListener('click', () => {
      const back = isNew ? href({path: isPolicy ? '' : folderName}) : href({path});
      if (ta.value === original) { location.href = back; return; }
      const panel = document.getElementById('dm-panel');
      panel.innerHTML = `<div class="dm-confirm"><p>Discard your changes?</p><p class="btns"><a class="btn danger" href="${back}">Discard</a>`
        + `<button type="button" class="btn" id="dm-keep">Keep editing</button></p></div>`;
      document.getElementById('dm-keep').addEventListener('click', () => { panel.innerHTML = ''; ta.focus(); });
    });
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

  // ── the router ───────────────────────────────────────────────────────────────────────────────────────────────
  async function main() {
    let o;
    try { o = await get('store'); } catch (e) { app.innerHTML = NEEDS; return; }
    if (badge) badge.innerHTML = o.store === 'sqlite'
      ? `store: SQLite · <code>${esc(o.database)}</code> · ${size(o.database_bytes)}` : 'store: files';
    const path = (P.get('path') || '').replace(/^\/+|\/+$/g, '');
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
