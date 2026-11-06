/* eval catalog: a setting as a form (UXS-004 §03-05). Built from the kind's schema the server sends (references
   inlined) and the setting's values; nobody types YAML. EVHForm.edit(el, spec) renders the form into `el` and returns
   {values(), changed(), problems(list)}; EVHForm.view(spec) is a setting's fields, read-only. */
(function () {
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const isObj = v => v !== null && typeof v === 'object' && !Array.isArray(v);
  const clone = v => v === undefined ? undefined : JSON.parse(JSON.stringify(v));
  const key = p => p.join('.');
  const label = k => String(k).replace(/_/g, ' ');
  const singular = k => /ses$/.test(k) ? k.slice(0, -2) : /s$/.test(k) ? k.slice(0, -1) : null;

  // What control a schema node is: its type, or what its words and types allow.
  function kindOf(node) {
    if (!isObj(node)) return 'any';
    if ('const' in node) return 'const';
    if (node.enum) return 'enum';
    const alts = node.oneOf || node.anyOf;
    if (alts || Array.isArray(node.type)) {
      const types = union(node).types;
      return types.has('object') || types.has('array') ? 'any' : 'union';
    }
    const t = node.type;
    if (t === 'object' || (!t && node.properties)) {
      if (isObj(node.additionalProperties)) return 'map';
      return node.properties ? 'group' : 'free';
    }
    if (t === 'array') return isObj(node.items) && (node.items.type === 'object' || node.items.properties) && !isObj(node.items.additionalProperties) && node.items.properties ? 'cards' : 'list';
    if (t === 'string') return 'text';
    if (t === 'number' || t === 'integer') return 'number';
    if (t === 'boolean') return 'bool';
    return 'any';
  }
  function union(node) {
    const types = new Set(), words = [];
    const add = n => {
      if (!isObj(n)) return;
      if ('const' in n) words.push(n.const);
      if (n.enum) words.push(...n.enum);
      [].concat(n.type || []).forEach(t => types.add(t));
      (n.oneOf || n.anyOf || []).forEach(add);
    };
    add(node);
    return {types, words};
  }
  // A typed word as the value the node allows: a number, null, a yes/no, or the text.
  function parseUnion(node, text) {
    const {types} = union(node);
    const t = text.trim();
    if (t === '') return undefined;
    if (t === 'null' && types.has('null')) return null;
    if ((types.has('number') || types.has('integer')) && /^-?\d+(\.\d+)?([eE][-+]?\d+)?$/.test(t)) return Number(t);
    if (types.has('boolean') && (t === 'true' || t === 'false')) return t === 'true';
    return text;
  }
  const typeOfValue = v => v === null ? 'null' : Array.isArray(v) ? 'list' : isObj(v) ? 'group' : typeof v === 'number' ? 'number' : typeof v === 'boolean' ? 'yes/no' : 'text';
  const blank = kind => ({number: 0, 'yes/no': false, null: null, list: [], group: {}, text: ''})[kind];

  // A new item of a list or card: its required keys, empty.
  function fresh(node) {
    const k = kindOf(node);
    if (k === 'const') return node.const;
    if (k === 'group') {
      const o = {};
      (node.required || []).forEach(r => { const v = fresh(node.properties[r] || {}); if (v !== undefined) o[r] = v; });
      return o;
    }
    if (k === 'map' || k === 'free') return {};
    if (k === 'list' || k === 'cards') return [];
    if (k === 'text' || k === 'union' || k === 'any') return '';
    return undefined;
  }

  function match(pattern, path) {
    const ps = pattern.split('.');
    return ps.length === path.length && ps.every((s, i) => s === '*' || s === String(path[i]));
  }
  const lookup = (table, path) => { for (const [p, v] of Object.entries(table || {})) if (match(p, path)) return v; return null; };

  function getAt(o, path) { return path.reduce((a, k) => (a == null ? undefined : a[k]), o); }
  function setAt(o, path, v) {
    let a = o;
    path.slice(0, -1).forEach((k, i) => {
      if (a[k] == null || typeof a[k] !== 'object') a[k] = typeof path[i + 1] === 'number' ? [] : {};
      a = a[k];
    });
    const last = path[path.length - 1];
    if (v === undefined) { if (Array.isArray(a)) a.splice(last, 1); else delete a[last]; } else a[last] = v;
  }

  // ── the read-only view ────────────────────────────────────────────────────────────────────────────────────────
  function viewValue(node, v) {
    if (v === null) return '<span class="muted">null</span>';
    if (typeof v === 'boolean') return v ? 'yes' : 'no';
    if (Array.isArray(v)) {
      if (!v.length) return '<span class="muted">none</span>';
      const item = isObj(node) ? node.items : null;
      if (v.every(x => !isObj(x) && !Array.isArray(x))) return `<ul class="df-vlist">${v.map(x => `<li>${viewValue(item, x)}</li>`).join('')}</ul>`;
      return `<ol class="df-vcards">${v.map(x => `<li>${viewValue(item, x)}</li>`).join('')}</ol>`;
    }
    if (isObj(v)) {
      const props = (isObj(node) && node.properties) || {};
      const extra = isObj(node) && isObj(node.additionalProperties) ? node.additionalProperties : null;
      const keys = [...Object.keys(props).filter(k => k in v), ...Object.keys(v).filter(k => !(k in props))];
      if (!keys.length) return '<span class="muted">none</span>';
      return `<dl class="df-view">${keys.map(k => `<dt>${esc(label(k))}</dt><dd>${viewValue(props[k] || extra, v[k])}</dd>`).join('')}</dl>`;
    }
    return `<span class="df-vtext">${esc(v)}</span>`;
  }
  function view(spec) { return viewValue(spec.schema, spec.values); }

  // ── the form ──────────────────────────────────────────────────────────────────────────────────────────────────
  function edit(el, spec) {
    const state = clone(spec.values) || {};
    const original = JSON.stringify(state);
    const LONG = new Set(spec.long || []);
    let uid = 0;

    function datalist(name) {
      const o = spec.options || {};
      let list = name === 'deployments' ? (o.deployments || {})[state.model_record] || [] : o[name] || [];
      return list;
    }
    function help(node) { return node && node.description ? `<p class="df-help">${esc(node.description)}</p>` : ''; }

    // One control: the input for a scalar, the nested rows for a group, the items of a list.
    function control(node, path, v) {
      const k = kindOf(node), p = esc(key(path)), id = `df-${++uid}`;
      const writer = lookup(spec.written, path);
      if (writer) return [id, `<div class="df-ro">${viewValue(node, v)}<p class="df-help">written by <code>${esc(writer)}</code>; kept as it is</p></div>`];
      if (spec.id_key && path.length === 1 && path[0] === spec.id_key && spec.id_is_file_name && !spec.new) {
        return [id, `<span class="df-fixed" id="${id}">${esc(v)}</span><p class="df-help">the file's name; renaming is not supported</p>`];
      }
      const ref = lookup(spec.refs, path);
      const dl = ref ? ` list="dl-${esc(ref)}"` : '';
      if (k === 'const') return [id, `<span class="df-fixed" id="${id}">${esc(node.const)}</span>`];
      if (k === 'enum') {
        const opts = ['<option value="">not set</option>', ...node.enum.map(e => `<option value="${esc(JSON.stringify(e))}"${JSON.stringify(e) === JSON.stringify(v) ? ' selected' : ''}>${esc(e)}</option>`)];
        return [id, `<select id="${id}" data-p="${p}" data-t="enum">${opts.join('')}</select>`];
      }
      if (k === 'bool') {
        const sel = x => (v === x ? ' selected' : '');
        return [id, `<select id="${id}" data-p="${p}" data-t="bool"><option value="">not set</option><option value="true"${sel(true)}>yes</option><option value="false"${sel(false)}>no</option></select>`];
      }
      if (k === 'number') return [id, `<input id="${id}" type="number" step="${node.type === 'integer' ? 1 : 'any'}" data-p="${p}" data-t="number" value="${v == null ? '' : esc(v)}">`];
      if (k === 'text' || k === 'union') {
        const words = k === 'union' ? union(node).words : [];
        const wl = words.length ? ` list="${id}-w"` : dl;
        const dlw = words.length ? `<datalist id="${id}-w">${words.map(w => `<option value="${esc(w)}">`).join('')}${union(node).types.has('null') ? '<option value="null">' : ''}</datalist>` : '';
        const shown = v == null ? (v === null ? 'null' : '') : v;
        if (k === 'text' && LONG.has(String(path[path.length - 1]))) {
          return [id, `<textarea id="${id}" rows="3" data-p="${p}" data-t="text">${esc(shown)}</textarea>`];
        }
        return [id, `<input id="${id}" type="text" data-p="${p}" data-t="${k}"${wl} value="${esc(shown)}" autocomplete="off">${dlw}`];
      }
      if (k === 'group') return [id, group(node, path, v)];
      if (k === 'list') return [id, list(node, path, v)];
      if (k === 'cards') return [id, cards(node, path, v)];
      if (k === 'map') return [id, map(node, path, v)];
      if (k === 'free') return [id, free(path, v)];
      return [id, anyValue(path, v)];
    }

    function row(name, node, path, v, required) {
      const [id, html] = control(node, path, v);
      return `<div class="df-row" data-at="${esc(key(path))}"><label class="df-label" for="${id}">${esc(label(name))}${required ? ' <span class="df-req" title="required">*</span>' : ''}</label>`
        + `<div class="df-ctl">${html}${help(node)}<p class="df-err" hidden></p></div></div>`;
    }
    const addBtn = (path, what, init) => `<button type="button" class="btn small df-add" data-path="${esc(key(path))}" data-init="${esc(JSON.stringify(init))}">+ add ${esc(what)}</button>`;

    function group(node, path, v) {
      const props = node.properties || {}, req = new Set(node.required || []);
      const val = isObj(v) ? v : {};
      const names = Object.keys(props);
      const first = names.filter(n => req.has(n)), set = names.filter(n => !req.has(n) && n in val), unset = names.filter(n => !req.has(n) && !(n in val));
      const r = n => row(n, props[n], [...path, n], val[n], req.has(n));
      const later = unset.map(n => {
        const k = kindOf(props[n]);
        if (['group', 'map', 'free', 'list', 'cards'].includes(k)) {
          return `<div class="df-row" data-at="${esc(key([...path, n]))}"><span class="df-label">${esc(label(n))}</span><div class="df-ctl">${addBtn([...path, n], label(n), fresh(props[n]))}${help(props[n])}<p class="df-err" hidden></p></div></div>`;
        }
        return r(n);
      });
      const others = Object.keys(val).filter(n => !(n in props));
      const extra = others.length && node.additionalProperties !== false
        ? `<div class="df-row"><span class="df-label">other keys</span><div class="df-ctl">${others.map(n => `<div class="df-kv" data-at="${esc(key([...path, n]))}"><span class="df-k">${esc(n)}</span>${anyValue([...path, n], val[n])}<button type="button" class="btn small df-del" data-path="${esc(key([...path, n]))}" aria-label="remove ${esc(n)}">×</button></div>`).join('')}</div></div>` : '';
      const more = later.length ? (path.length ? later.join('') : `<details class="df-more"><summary>more fields (${later.length})</summary>${later.join('')}</details>`) : '';
      return `<div class="df-group">${[...first, ...set].map(r).join('')}${extra}${more}</div>`;
    }
    function list(node, path, v) {
      const items = Array.isArray(v) ? v : [];
      const it = node.items || {};
      return `<div class="df-list">${items.map((x, i) => `<div class="df-item" data-at="${esc(key([...path, i]))}">${control(it, [...path, i], x)[1]}<button type="button" class="btn small df-del" data-path="${esc(key([...path, i]))}" aria-label="remove item ${i + 1}">×</button></div>`).join('')}`
        + addBtn([...path, items.length], 'one', fresh(it)) + '</div>';
    }
    function cards(node, path, v) {
      const items = Array.isArray(v) ? v : [];
      const name = String(path[path.length - 1] ?? 'item');
      const word = singular(name) || name;
      return `<div class="df-cards">${items.map((x, i) => `<div class="df-card" data-at="${esc(key([...path, i]))}"><div class="df-card-h"><span>${esc(label(word))} ${i + 1}</span>`
        + `<button type="button" class="btn small df-del" data-path="${esc(key([...path, i]))}" aria-label="remove ${esc(label(word))} ${i + 1}">×</button></div>${group(node.items, [...path, i], x)}</div>`).join('')}`
        + addBtn([...path, items.length], `a ${label(word)}`, fresh(node.items)) + '</div>';
    }
    function map(node, path, v) {
      const val = isObj(v) ? v : {};
      const props = node.properties || {}, each = node.additionalProperties;
      const known = Object.keys(props).filter(n => n in val);
      const rows = [...known.map(n => row(n, props[n], [...path, n], val[n], false)),
        ...Object.keys(val).filter(n => !(n in props)).map(n => {
          const [, html] = control(each, [...path, n], val[n]);
          return `<div class="df-kv" data-at="${esc(key([...path, n]))}"><input class="df-k" type="text" value="${esc(n)}" data-rename="${esc(key([...path, n]))}" aria-label="key">`
            + `<div class="df-kv-v">${html}</div><button type="button" class="btn small df-del" data-path="${esc(key([...path, n]))}" aria-label="remove ${esc(n)}">×</button></div>`;
        })];
      return `<div class="df-map">${rows.join('')}<button type="button" class="btn small df-addkey" data-path="${esc(key(path))}" data-init="${esc(JSON.stringify(fresh(each) ?? ''))}">+ add a key</button></div>`;
    }
    function free(path, v) {
      const val = isObj(v) ? v : {};
      return `<div class="df-map">${Object.keys(val).map(n => `<div class="df-kv" data-at="${esc(key([...path, n]))}"><input class="df-k" type="text" value="${esc(n)}" data-rename="${esc(key([...path, n]))}" aria-label="key">`
        + `<div class="df-kv-v">${anyValue([...path, n], val[n])}</div><button type="button" class="btn small df-del" data-path="${esc(key([...path, n]))}" aria-label="remove ${esc(n)}">×</button></div>`).join('')}`
        + `<button type="button" class="btn small df-addkey" data-path="${esc(key(path))}" data-init='""'>+ add a key</button></div>`;
    }
    // A value of any type: its type chosen, then its control (a list or group nests the same).
    function anyValue(path, v) {
      const t = v === undefined ? 'not set' : typeOfValue(v), p = esc(key(path));
      const types = [...(v === undefined ? ['not set'] : []), 'text', 'number', 'yes/no', 'list', 'group', 'null'];
      const pick = `<select class="df-type" data-retype="${p}" aria-label="type">${types.map(x => `<option${x === t ? ' selected' : ''}>${x}</option>`).join('')}</select>`;
      let inner = '';
      if (t === 'text') inner = `<input type="text" data-p="${p}" data-t="text" value="${esc(v)}" autocomplete="off">`;
      else if (t === 'number') inner = `<input type="number" step="any" data-p="${p}" data-t="number" value="${esc(v)}">`;
      else if (t === 'yes/no') inner = `<select data-p="${p}" data-t="bool-set"><option value="true"${v ? ' selected' : ''}>yes</option><option value="false"${v ? '' : ' selected'}>no</option></select>`;
      else if (t === 'list') inner = `<div class="df-list">${v.map((x, i) => `<div class="df-item" data-at="${esc(key([...path, i]))}">${anyValue([...path, i], x)}<button type="button" class="btn small df-del" data-path="${esc(key([...path, i]))}" aria-label="remove item ${i + 1}">×</button></div>`).join('')}${addBtn([...path, v.length], 'one', '')}</div>`;
      else if (t === 'group') inner = free(path, v);
      return `<span class="df-any">${pick}${inner}</span>`;
    }

    const pathOf = s => s.split('.').map(x => (/^\d+$/.test(x) ? Number(x) : x));
    function isRequired(path) {
      let node = spec.schema;
      for (let i = 0; i < path.length - 1; i++) {
        const k = path[i];
        if (!isObj(node)) return false;
        node = typeof k === 'number' ? node.items : (node.properties && node.properties[k]) || (isObj(node.additionalProperties) ? node.additionalProperties : null);
      }
      return isObj(node) && (node.required || []).includes(path[path.length - 1]);
    }

    function render() {
      const y = window.scrollY;
      const names = new Set(Object.values(spec.refs || {}));
      const lists = [...names].map(n => `<datalist id="dl-${esc(n)}">${datalist(n).map(x => `<option value="${esc(x)}">`).join('')}</datalist>`).join('');
      el.innerHTML = `<div class="df-form">${group(spec.schema, [], state)}</div>${lists}`;
      window.scrollTo(0, y);
    }

    el.addEventListener('input', ev => {
      const t = ev.target;
      if (!t.dataset || !t.dataset.p) return;
      const path = pathOf(t.dataset.p), kind = t.dataset.t;
      let v;
      if (kind === 'text') v = t.value === '' && !isRequired(path) && typeof path[path.length - 1] !== 'number' ? undefined : t.value;
      else if (kind === 'number') v = t.value === '' ? undefined : Number(t.value);
      else if (kind === 'union') {
        let node = spec.schema;
        path.forEach(k => { node = typeof k === 'number' ? node.items : (node.properties || {})[k] || node.additionalProperties; });
        v = parseUnion(node, t.value);
      } else return;
      setAt(state, path, v);
      t.closest('.df-row, .df-kv, .df-item')?.querySelector('.df-err')?.setAttribute('hidden', '');
    });
    el.addEventListener('change', ev => {
      const t = ev.target;
      if (t.dataset.retype) {
        const path = pathOf(t.dataset.retype);
        setAt(state, path, t.value === 'not set' ? undefined : blank(t.value));
        render(); return;
      }
      if (t.dataset.rename) {
        const path = pathOf(t.dataset.rename), to = t.value.trim(), from = path[path.length - 1];
        const parent = getAt(state, path.slice(0, -1));
        if (!to || to === from || (to in parent)) { t.value = from; return; }
        const rebuilt = {};
        Object.keys(parent).forEach(k => { rebuilt[k === from ? to : k] = parent[k]; });
        Object.keys(parent).forEach(k => delete parent[k]);
        Object.assign(parent, rebuilt);
        render(); return;
      }
      if (!t.dataset.p) return;
      const path = pathOf(t.dataset.p), kind = t.dataset.t;
      if (kind === 'enum') setAt(state, path, t.value === '' ? undefined : JSON.parse(t.value));
      else if (kind === 'bool') setAt(state, path, t.value === '' ? undefined : t.value === 'true');
      else if (kind === 'bool-set') setAt(state, path, t.value === 'true');
      else return;
      if (path.length === 1 && path[0] === 'model_record') render();
    });
    el.addEventListener('click', ev => {
      const b = ev.target.closest('button');
      if (!b || !el.contains(b)) return;
      if (b.classList.contains('df-del')) { setAt(state, pathOf(b.dataset.path), undefined); render(); }
      else if (b.classList.contains('df-add')) { setAt(state, pathOf(b.dataset.path), JSON.parse(b.dataset.init ?? 'null') ?? ''); render(); }
      else if (b.classList.contains('df-addkey')) {
        const path = pathOf(b.dataset.path);
        const at = getAt(state, path) || {};
        let n = 1; while (`key${n}` in at) n++;
        setAt(state, [...path, `key${n}`], JSON.parse(b.dataset.init || '""'));
        render();
        el.querySelector(`[data-rename="${CSS.escape(key([...path, `key${n}`]))}"]`)?.select();
      }
    });

    render();
    return {
      values: () => clone(state),
      changed: () => JSON.stringify(state) !== original,
      // Each problem at its field (or the nearest field above it that is on the page), and the list of them all.
      problems(list) {
        el.querySelectorAll('.df-err').forEach(e => { e.hidden = true; e.textContent = ''; });
        el.querySelectorAll('.df-bad').forEach(e => e.classList.remove('df-bad'));
        return list.map(pr => {
          let path = pr.path.slice(), target = null;
          while (!target) {
            target = el.querySelector(`[data-at="${CSS.escape(key(path))}"]`);
            if (target || !path.length) break;
            path = path.slice(0, -1);
          }
          if (target) {
            target.classList.add('df-bad');
            const d = target.closest('details'); if (d) d.open = true;
            const err = target.querySelector('.df-err') || target.closest('.df-row')?.querySelector('.df-err');
            if (err) { err.hidden = false; err.textContent = (err.textContent ? err.textContent + '; ' : '') + pr.message; }
          }
          return {where: pr.path.length ? pr.path.map(label).join(' › ') : 'the setting', message: pr.message, target};
        });
      },
    };
  }

  window.EVHForm = {edit, view, kindOf};
})();
