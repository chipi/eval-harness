// The Workbench mockup (UXS-005, round 1 of the mockup): the app's first, static form. Every value shown is read from
// this project by mock.js's extractor; what the mockup only pretends (jobs, saving) is labelled where it happens.
(() => {
  const M = window.MOCK, H = window.HELP, G = window.GLOSSARY;
  const KEY = "wb-mock-r1";
  const fresh = () => ({ goal: null, draft: {}, dataset: null, hf: {}, fetched: false, looked: false, reference: null, hints: true, models: [], checked: [], r4: null });
  let S = fresh();
  try { Object.assign(S, JSON.parse(localStorage.getItem(KEY) || "{}")); } catch (_e) { /* no storage: start fresh */ }
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (_e) { /* per-viewer only */ } };

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const $ = (sel, el = document) => el.querySelector(sel);
  const main = $("#main"), rail = $("#rail"), help = $("#help"), layout = $("#layout");
  const slug = (t) => String(t || "").toLowerCase().replace(/\(([^)]*)\)/g, " $1").replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 40);
  const short = (sha) => String(sha || "").slice(0, 7);
  const ds = () => S.dataset && S.dataset.id;

  // a word of the harness, taught where it first appears: pointing shows its meaning, clicking opens it
  const w = (word, text) => `<dfn data-word="${esc(word)}" title="${esc(G[word] || "")}" tabindex="0">${esc(text || word)}</dfn>`;
  const q = (key) => `<button type="button" class="q" data-help="${esc(key)}" aria-label="What is ${esc(H[key]?.title || key)}?" aria-expanded="false">?</button>`;
  const field = (key, control, name) => `<div class="field"><div class="name">${esc(name || H[key].title)} ${q(key)}</div><div>${control}</div>${H[key].hint ? `<div class="hint">${esc(H[key].hint)}</div>` : ""}</div>`;
  const cmd = (text, label = "the command this runs") => `<details class="cmd"><summary>${esc(label)}</summary><pre>${esc(text)}</pre></details>`;
  const note = (text) => `<p class="mocknote">mockup: ${esc(text)}</p>`;

  // ── the help panel ───────────────────────────────────────────────────────
  function openHelp(key, btn) {
    document.querySelectorAll(".q[aria-expanded=true]").forEach((b) => b.setAttribute("aria-expanded", "false"));
    const h = H[key];
    if (!h) return;
    if (btn) btn.setAttribute("aria-expanded", "true");
    const row = (k, v) => (v ? `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>` : "");
    help.innerHTML = `<header><h2>${esc(h.title)}</h2><button type="button" data-close aria-label="Close">×</button></header>
      <dl>${row("What it is", h.what)}${row("Why it matters", h.why)}${row("Example", h.example)}${row("If it is wrong", h.wrong)}</dl>
      ${h.more ? `<p class="more">Read more: <a href="#docs">${esc(h.more)} ↗</a></p>` : ""}`;
    help.hidden = false;
  }
  function openWord(word) {
    help.innerHTML = `<header><h2>${esc(word)}</h2><button type="button" data-close aria-label="Close">×</button></header>
      <dl><div><dt>Meaning</dt><dd>${esc(G[word])}</dd></div></dl><p class="more"><a href="#glossary">Every word ↗</a></p>`;
    help.hidden = false;
  }
  document.addEventListener("click", (e) => {
    const b = e.target.closest(".q");
    if (b) { openHelp(b.dataset.help, b); return; }
    const d = e.target.closest("dfn[data-word]");
    if (d) { openWord(d.dataset.word); return; }
    if (e.target.closest("[data-close]")) { help.hidden = true; document.querySelectorAll(".q[aria-expanded=true]").forEach((x) => x.setAttribute("aria-expanded", "false")); }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") help.hidden = true;
    if (e.key === "Enter" && e.target.matches("dfn[data-word]")) openWord(e.target.dataset.word);
  });

  // ── the journey rail ─────────────────────────────────────────────────────
  const STEPS = [
    { n: 1, id: "goal", name: "Goal" },
    { n: 2, id: "dataset", name: "Dataset" },
    { n: 3, id: "prepare", name: "Prepare" },
    { n: 4, id: "models", name: "Models" },
    { n: 5, id: "eval", name: "Eval" },
  ];
  const prepared = () => S.fetched && S.looked && !!S.reference;
  const done = (id) => ({ goal: !!S.goal, dataset: !!S.dataset, prepare: prepared(), models: (S.checked || []).length >= 2, eval: !!(S.r4 && S.r4.closed) })[id];
  const open = (id) => ({ goal: true, dataset: !!S.goal, prepare: !!S.dataset, models: prepared(), eval: prepared() })[id];
  const OUTSIDE = ["start", "home", "jobs", "settings", "glossary", "model-new", "production-live", "production-labels", "production-replay", "catalog", "docs"];
  function drawRail(route) {
    if (!S.goal || OUTSIDE.includes(route)) { layout.classList.add("no-rail"); rail.innerHTML = ""; return; }
    layout.classList.remove("no-rail");
    const cur = route.startsWith("dataset") ? "dataset" : route === "goal-edit" ? "goal" : route;
    rail.innerHTML = `<div class="label">Goal</div><div class="goalname">${esc(S.goal.title)}</div>
      <a class="step" href="#hub" ${route === "hub" ? 'aria-current="page"' : ""}><span class="dot">≡</span>Overview</a>
      ${STEPS.map((s) => {
        const cls = done(s.id) ? "done" : open(s.id) ? (cur === s.id ? "now" : "") : "locked";
        const href = open(s.id) ? `#${s.id === "goal" ? "goal-edit" : s.id}` : "#hub";
        return `<a class="step ${cls}" href="${href}" ${cur === s.id ? 'aria-current="page"' : ""}><span class="dot">${done(s.id) ? "✓" : s.n}</span>${s.name}</a>`;
      }).join("")}
      <div class="label" style="margin-top:18px">Day to day</div>
      ${[["review", "Review and label"], ["production", "Production"], ["judge", "A judge"], ...(window.WB.dayToDay || []).map(([id, name]) => [id, name])].map(([id, name]) => `<a class="step" href="#${id}" ${route === id || route.startsWith(id + "-") ? 'aria-current="page"' : ""}><span class="dot">·</span>${name}</a>`).join("")}`;
  }

  // ── step 0: an empty project ─────────────────────────────────────────────
  function screenStart() {
    if (S.goal) { location.hash = "#home"; return ""; }
    return `<div class="screen empty">
      <div class="kicker">Project harness · no goals yet</div>
      <h1>Start with the decision you have to make.</h1>
      <p class="lead">An evaluation compares systems (a model, a prompt, a setting) on the same examples and tells you which
      is better for that decision, with how sure it is and what each costs. You set a ${w("goal")} first; everything after
      it is chosen for it.</p>
      <div class="path" aria-label="The steps"><span>1 Goal</span><span>2 Dataset</span><span>3 Prepare</span><span>4 Models</span><span>5 Eval</span></div>
      <div class="actions"><a class="btn primary" href="#goal-new">Set your first goal</a>
        <a class="btn" href="#catalog">See what other projects measured ↗</a></div>
      <p class="note" style="margin-top:36px">Agents do all of this through <code>evh</code> and the MCP server; this is the same work for people, a step at a time.</p>
      ${note(`this project really has ${M.goals.length} goals; the mockup starts empty to show the first visit.`)}
    </div>`;
  }

  // ── step 1: the goal ─────────────────────────────────────────────────────
  function goalYaml(g) {
    return `goal_id: ${g.goal_id}
title: ${g.title}
statement: ${g.statement}
decision: ${g.decision}
success_criteria:
  primary: {measure: ${g.measure}, direction: ${g.direction}}${g.strategy !== "balanced" ? `\n  strategy: ${g.strategy}` : ""}`;
  }
  function screenGoal(editing) {
    const d = editing && S.goal ? { ...S.goal } : { direction: "higher", strategy: "balanced", ...S.draft };
    const ex = M.goal;
    const radio = (name, val, label, small) => `<label class="choice"><input type="radio" name="${name}" value="${val}" ${d[name] === val ? "checked" : ""}> <span>${label}${small ? ` <small>${esc(small)}</small>` : ""}</span></label>`;
    return `<div class="screen">
      <div class="kicker">Step 1 of 5</div>
      <h1>${editing ? "The goal" : "Set the goal"}</h1>
      <p class="lead hintable">A ${w("goal")} is the decision this evaluation helps you make. Everything later is measured against it. ${q("goal")}</p>
      <form class="form" id="goalform" autocomplete="off">
        ${field("goal.title", `<input type="text" name="title" value="${esc(d.title)}" placeholder="e.g. ${esc(ex.title)}"><label class="idline">id <input type="text" name="goal_id" class="idinput" value="${esc(d.goal_id || slug(d.title))}" placeholder="made from the title" ${editing ? "readonly" : ""}></label>`)}
        ${field("goal.statement", `<textarea name="statement" rows="2" placeholder="e.g. ${esc(ex.statement)}">${esc(d.statement)}</textarea>`)}
        ${field("goal.decision", `<textarea name="decision" rows="2" placeholder="e.g. ${esc(ex.decision)}">${esc(d.decision)}</textarea>`)}
        ${field("goal.measure", `<div class="inline"><select name="measure" aria-label="measure"><option value="">choose a ${"measure"}</option>${M.measures.map((m) => `<option ${d.measure === m ? "selected" : ""}>${esc(m)}</option>`).join("")}</select>
            <div class="choices row">${radio("direction", "higher", "higher is better")}${radio("direction", "lower", "lower is better")}</div></div>`)}
        ${field("goal.strategy", `<div class="choices">${radio("strategy", "balanced", "balanced", "shown no worse than the best by more than 5% of it, then the cheapest")}
            ${radio("strategy", "quality_first", "quality first", "the same quality only")}${radio("strategy", "frugal", "frugal", "shown no worse than the best by more than 10% of it, then the cheapest")}</div>
            <details class="adv" style="margin-top:8px"><summary>advanced: the margin, the tie-break, other measures</summary>
              <div class="form" style="gap:12px;margin-top:12px">
                <div class="field"><div class="name">Margin</div><div class="inline"><input type="text" name="margin" value="${esc(d.margin ?? "")}" placeholder="default: 5% of the best (balanced), 10% (frugal)" style="width:300px"><span class="muted" style="font-size:13px">how much worse than the best an arm may be and still win, in the measure's units</span></div></div>
                <div class="field"><div class="name">Then pick by</div><div class="inline"><select name="tie1" aria-label="first tie-break"><option>cost</option><option>speed</option><option>quality</option></select><select name="tie2" aria-label="second tie-break"><option>speed</option><option>cost</option><option>quality</option></select><span class="muted" style="font-size:13px">among the arms that may win</span></div></div>
                <div class="field"><div class="name">Also show</div><div class="inline">${Object.entries(M.axes).map(([k, v]) => `<span class="tag">${esc(k)} · ${esc(v.direction)}</span>`).join(" ")}<button class="btn" type="button" disabled>+ a measure</button><span class="muted" style="font-size:13px">shown beside the deciding measure, never deciding</span></div></div>
              </div>${note("the CNN goal's own extra measure is rouge1; margin and tie-break defaults are the goal schema's.")}</details>`)}
      </form>
      <div class="actions">
        <button class="btn primary" id="goalsave" type="button">${editing ? "Save the goal" : "Save the goal and continue"}</button>
        ${editing ? `<a class="btn" href="#hub">Cancel</a>` : `<button class="btn" type="button" id="fillex">Fill in this project's CNN goal</button>`}
      </div>
      <p class="muted" id="goalwhy" style="font-size:13px;margin-top:10px"></p>
      ${cmd("")}
    </div>`;
  }
  function wireGoal(editing) {
    const f = $("#goalform");
    const read = () => Object.fromEntries(new FormData(f).entries());
    const missing = (g) => ["title", "goal_id", "statement", "decision", "measure"].filter((k) => !String(g[k] || "").trim());
    const idIn = f.elements.goal_id;
    let idEdited = editing || (!!idIn.value && idIn.value !== slug(f.elements.title.value));
    idIn.addEventListener("input", () => { idEdited = !!idIn.value; });
    const sync = () => {
      if (!idEdited) idIn.value = slug(f.elements.title.value);
      const g = read();
      if (!editing) { S.draft = g; save(); }
      const m = missing(g);
      $("#goalsave").disabled = m.length > 0;
      $("#goalwhy").textContent = m.length ? `Still to fill: ${m.map((k) => (k === "goal_id" ? "its id" : H[`goal.${k}`].title)).join(", ")}.` : "";
      $(".cmd pre").textContent = `# data/goals/<id>.yaml, checked before it is saved\nevh data-put goals/${g.goal_id || "<id>"}.yaml goal.yaml --new\n\n# goal.yaml\n${goalYaml({ ...g, goal_id: g.goal_id || "<id>" })}`;
    };
    f.addEventListener("input", sync);
    $("#fillex")?.addEventListener("click", () => { S.draft = { ...M.goal }; save(); render(); });
    $("#goalsave").addEventListener("click", () => {
      const g = read();
      if (missing(g).length) return;
      S.goal = { ...g };
      S.draft = {};
      save();
      location.hash = "#hub";
    });
    sync();
  }

  // ── the goal's hub ───────────────────────────────────────────────────────
  function screenHub() {
    if (!S.goal) { location.hash = "#start"; return ""; }
    const g = S.goal;
    const rows = [
      { id: "goal", title: "Goal", what: "the decision, and how a winner is picked", status: "set", go: "#goal-edit", label: "Edit" },
      { id: "dataset", title: "Dataset", what: "the examples every system is tested on", status: ds() ? `${ds()} · ${S.dataset.items} items · ${S.dataset.role}` : "", go: "#dataset", label: ds() ? "Change" : "Add a dataset" },
      { id: "prepare", title: "Prepare", what: "fetch its items, look inside, its reference set", status: [S.fetched && "fetched", S.looked && "looked at", S.reference && "reference set"].filter(Boolean).join(" · "), go: "#prepare", label: prepared() ? "Open" : "Prepare it" },
      { id: "models", title: "Models", what: "the systems you compare, each checked on three items first", status: (S.checked || []).length ? `${S.checked.length} arms checked` : (S.models || []).length ? `${S.models.length} chosen` : "", go: "#models", label: (S.checked || []).length >= 2 ? "Open" : "Choose models" },
      { id: "eval", title: "Eval", what: "the goal measured in rounds: arms, runs, scores, a decision", status: `${M.rounds.length} rounds closed${S.r4 ? ` · r4 ${S.r4.closed ? "closed" : "open"}` : ""}`, go: "#eval", label: "Open" },
    ];
    return `<div class="screen">
      <div class="goalhead"><div><div class="kicker">Goal · ${esc(g.goal_id)}</div><h1>${esc(g.title)}</h1>
        <div class="meta">decides <b>${esc(g.measure)}</b> (${esc(g.direction)} is better) · <b>${esc(g.strategy.replace("_", " "))}</b></div></div>
        <a class="btn" href="#goal-edit">Edit</a></div>
      <p class="lead">${esc(g.statement)}</p>
      <div class="steps">${rows.map((r, i) => {
        const ok = done(r.id), can = open(r.id);
        return `<div class="row ${can ? "" : "locked"} ${ok ? "done" : can ? "now" : ""}"><span class="dot">${ok ? "✓" : i + 1}</span>
          <div><h3>${r.title}</h3><p>${esc(r.what)}</p>${r.status ? `<div class="status ${ok ? "ok" : ""}">${esc(r.status)}</div>` : ""}</div>
          ${can ? `<a class="btn ${!ok && can ? "primary" : ""}" href="${r.go}">${r.label}</a>` : `<span class="status">${i >= 3 && prepared() && r.id === "models" ? "" : "after the step before"}</span>`}</div>`;
      }).join("")}</div>
      <h2 style="margin:28px 0 10px">Day to day</h2>
      <div class="steps">${[["#review", "Review and label", "read outputs side by side, pick the better, tag what went wrong"], ["#production", "Production", "what the deployed choice decided, and the next dataset version from it"], ["#judge", "A judge", "a model that scores like a person, validated against people first"], ...(window.WB.dayToDay || []).map(([id, t, d]) => [`#${id}`, t, d])].map(([h, t, d]) => `<div class="row"><span class="dot">·</span><div><h3>${t}</h3><p>${d}</p></div><a class="btn" href="${h}">Open</a></div>`).join("")}</div>
    </div>`;
  }

  // ── step 2: the dataset ──────────────────────────────────────────────────
  const SOURCES = [
    ["folder", "A folder of files", "one file per item, on this machine"],
    ["manifest", "A table", "CSV or JSON lines: a row per item"],
    ["huggingface", "Hugging Face", "a dataset on the Hub, read at one commit"],
    ["croissant", "Croissant", "a dataset described in Croissant JSON-LD"],
    ["zenodo", "Zenodo", "a published record's files"],
    ["openml", "OpenML", "a dataset by its OpenML id"],
    ["kaggle", "Kaggle", "a Kaggle dataset's files"],
    ["capture", "From production", "what your system decided, kept as a capture"],
  ];
  function screenDataset() {
    if (!S.goal) { location.hash = "#start"; return ""; }
    return `<div class="screen wide">
      <div class="kicker">Step 2 of 5 · ${esc(S.goal.goal_id)}</div>
      <h1>Add a dataset</h1>
      <p class="lead hintable">A ${w("dataset")} is the set of examples your systems will be tested on: a frozen list of ${w("item", "items")}, each with a hash, so every system sees exactly the same examples, now and later. ${q("dataset")}</p>
      <h2>Use one you have</h2>
      <div class="inline" style="margin-top:12px">
        <select id="pick" aria-label="the project's datasets"><option value="">choose one of the project's ${M.datasets.length} datasets</option>
          ${M.datasets.map((d) => `<option value="${esc(d.id)}">${esc(d.id)} · ${d.items} items</option>`).join("")}</select>
        <button class="btn" id="usepick" type="button" disabled>Use it</button></div>
      <div class="or">or make one from a source</div>
      <div class="cards">${SOURCES.map(([id, name, what]) => `<button type="button" class="card" data-source="${id}" aria-pressed="false"><b>${esc(name)}</b><span>${esc(what)}</span></button>`).join("")}</div>
      <div id="srcnote" style="margin-top:14px"></div>
    </div>`;
  }
  function wireDataset() {
    const pick = $("#pick");
    pick.addEventListener("change", () => { $("#usepick").disabled = !pick.value; });
    $("#usepick").addEventListener("click", () => {
      const d = M.datasets.find((x) => x.id === pick.value);
      S.dataset = { id: d.id, items: d.items, role: "validation", how: "existing" };
      Object.assign(S, d.id === "cnn_dailymail_200" ? { fetched: true, looked: false, reference: null } : { fetched: false, looked: false, reference: null });
      save(); location.hash = "#prepare";
    });
    main.querySelectorAll(".card").forEach((c) => c.addEventListener("click", () => {
      location.hash = c.dataset.source === "huggingface" ? "#dataset-hf" : `#dataset-src-${c.dataset.source}`; return;
      main.querySelectorAll(".card").forEach((x) => x.setAttribute("aria-pressed", String(x === c)));
      $("#srcnote").innerHTML = note("round 1 mocks the Hugging Face path only; the others take the same four parts (where from, what's in it, its fields, name it).");
    }));
  }

  // step 2 from Hugging Face: four parts on one screen, each opening when the one before is done
  function screenHF() {
    if (!S.goal) { location.hash = "#start"; return ""; }
    const src = M.source, h = S.hf;
    const read = !!h.read, cols = !!h.cols, fields = !!h.fields;
    const part = (letter, key, title, on, body, status) => `<section class="part ${on ? "" : "off"}">
      <div class="parthead"><span class="letter">${letter}</span><h2>${esc(title)}</h2>${q(key)}<span class="grow"></span>${status ? `<span class="status ok">${esc(status)}</span>` : ""}</div>
      ${on ? `<p class="hint">${esc(H[key].hint)}</p><div class="body">${body}</div>` : ""}</section>`;
    const preview = `<div class="tablewrap"><table><thead><tr><th>row</th><th>id</th><th>article</th><th>highlights</th></tr></thead><tbody>
      ${M.items.map((it) => `<tr><td class="num">${it.row}</td><td class="mono">${esc(it.id.slice(0, 8))}…</td><td class="clip"><div>${esc(it.article)}</div></td><td class="clip"><div>${esc(it.highlights)}</div></td></tr>`).join("")}
      </tbody></table></div><div class="muted" style="font-size:12px">The first ${M.items.length} rows of ${src.split_rows.toLocaleString("en")} in the test split, as read.</div>`;
    const id = h.id ?? "cnn_dailymail_200";
    const query = { ref: src.ref, config: src.config, split: src.split, text: "article", id: "id", limit: Number(h.limit || 200) };
    return `<div class="screen wide">
      <div class="kicker">Step 2 of 5 · ${esc(S.goal.goal_id)} · from Hugging Face</div>
      <h1>A dataset from Hugging Face</h1>
      <p class="lead hintable">Read once at a pinned commit, so the same dataset can be rebuilt exactly. <a href="#dataset">Other sources</a></p>
      ${part("a", "dataset.from", "Where from", true, `
        <div class="field"><div class="name">Repository</div><div><input type="text" id="hfref" value="${esc(h.ref ?? src.ref)}"></div></div>
        <div class="field"><div class="name">Config · split</div><div class="inline"><select id="hfconfig" aria-label="config"><option>${esc(src.config)}</option></select><select id="hfsplit" aria-label="split"><option>${esc(src.split)}</option></select></div></div>
        ${read ? `<div class="note">Pinned to commit <code>${short(src.revision)}</code> · licence ${esc(src.licence)} · ${src.split_rows.toLocaleString("en")} rows in ${esc(src.split)} · columns <code>article</code> <code>highlights</code> <code>id</code></div>${preview}`
          : `<div class="actions" style="margin-top:0"><button class="btn primary" id="hfread" type="button">Read it</button><span class="muted" style="font-size:13px">reads the card and the first rows; nothing is saved yet</span></div>`}`,
        read ? `pinned ${short(src.revision)}` : "")}
      ${part("b", "dataset.columns", "What's in it", read, `
        <div class="field"><div class="name">The item</div><div><select id="hftext" aria-label="the item's column"><option selected>article</option><option>highlights</option><option>id</option></select><div class="hint" style="grid-column:auto">what a system receives</div></div></div>
        <div class="field"><div class="name">The expected answer</div><div><select id="hfanswer" aria-label="the answer's column"><option selected>highlights</option><option value="">none</option><option>article</option></select><div class="hint" style="grid-column:auto">becomes its ${w("reference set")} in step 3</div></div></div>
        <div class="field"><div class="name">The item's id</div><div><select aria-label="the id column"><option selected>id</option><option value="">the row number</option></select></div></div>
        <div class="field"><div class="name">How many</div><div class="inline"><input type="text" id="hflimit" value="${esc(h.limit ?? 200)}" style="width:90px" inputmode="numeric"> <span class="muted" style="font-size:13px">the first rows, in order (the committed runs measured the first 200, all CNN)</span></div></div>
        ${cols ? "" : `<div class="actions" style="margin-top:0"><button class="btn primary" id="hfcols" type="button">Next</button></div>`}
        ${note("the huggingface source takes the item's column and its id today; taking the answer column too is new (UXS-005).")}`,
        cols ? `article · answer highlights · ${h.limit ?? 200}` : "")}
      ${part("c", "dataset.fields", "Its fields", cols, `
        <p style="margin:0">No fields proposed: this dataset's other columns are the answer and the id, neither a fact to slice the results by.</p>
        ${fields ? "" : `<div class="actions" style="margin-top:0"><button class="btn primary" id="hffields" type="button">Next</button></div>`}`,
        fields ? "none" : "")}
      ${part("d", "dataset.name", "Name it", fields, `
        <div class="field"><div class="name">Id</div><div><input type="text" id="hfid" value="${esc(id)}"></div></div>
        <div class="field"><div class="name">Its role</div><div class="choices row">
          <label class="choice"><input type="radio" name="role" value="validation" ${(h.role || "test") === "validation" ? "checked" : ""}> ${w("validation")} <small>while you choose and tune</small></label>
          <label class="choice"><input type="radio" name="role" value="test" ${(h.role || "test") === "test" ? "checked" : ""}> ${w("test")} <small>the final answer, kept untouched</small></label></div></div>
        <div class="actions" style="margin-top:0"><button class="btn primary" id="hfmake" type="button">Make the dataset</button><span class="muted" style="font-size:13px">a job: reads the ${esc(h.limit ?? 200)} rows and freezes each with its hash</span></div>
        <div id="hfjob"></div>`)}
      ${cmd(`evh dataset-create --source huggingface --dataset-id ${id} --licence ${src.licence} \\\n  --query '${JSON.stringify(query)}'`)}
    </div>`;
  }
  function wireHF() {
    const set = (k, v) => { S.hf[k] = v; save(); };
    $("#hfread")?.addEventListener("click", (e) => job(e.target, 900, () => { set("read", true); render(); }));
    $("#hfcols")?.addEventListener("click", () => { set("limit", $("#hflimit").value); set("cols", true); render(); });
    $("#hffields")?.addEventListener("click", () => { set("fields", true); render(); });
    $("#hfid")?.addEventListener("input", (e) => set("id", e.target.value));
    main.querySelectorAll("input[name=role]").forEach((r) => r.addEventListener("change", () => set("role", r.value)));
    $("#hfmake")?.addEventListener("click", (e) => {
      e.target.disabled = true;
      const n = Number(S.hf.limit || 200);
      progress($("#hfjob"), `dataset-create · ${S.hf.id || "cnn_dailymail_200"}`, n, "items frozen", () => {
        S.dataset = { id: S.hf.id || "cnn_dailymail_200", items: n, role: S.hf.role || "test", how: "huggingface" };
        Object.assign(S, { fetched: false, looked: false, reference: null });
        save(); location.hash = "#prepare";
      });
    });
  }

  // a pretend job: the real one is a Workbench job (PRD-017), its progress read from the job's log
  function job(btn, ms, then) { btn.disabled = true; btn.textContent = "Reading…"; setTimeout(then, ms); }
  function progress(el, name, total, unit, then) {
    S.jobs = S.jobs || [];
    const rec = { name, total, unit, n: 0, status: "running", started: new Date().toTimeString().slice(0, 8) };
    S.jobs.push(rec); save();
    el.innerHTML = `<div class="job"><span>${esc(name)}</span><span class="status num" data-n>0 / ${total} ${esc(unit)}</span><div class="bar-track"><div class="bar-fill"></div></div></div>${note("a pretend job; the real one runs on the server and survives closing the page.")}`;
    let k = 0;
    const t = setInterval(() => {
      k = Math.min(total, k + Math.ceil(total / 24));
      $(".bar-fill", el).style.width = `${(100 * k) / total}%`;
      $("[data-n]", el).textContent = `${k} / ${total} ${unit}`;
      rec.n = k;
      if (k >= total) { clearInterval(t); rec.status = "done"; save(); setTimeout(then, 350); }
    }, 60);
  }

  // ── step 3: prepare ──────────────────────────────────────────────────────
  function hist(h, label, unit) {
    const W = 520, Hh = 120, pad = 22, max = Math.max(...h.map((b) => b[2]));
    const bw = (W - 2 * pad) / h.length;
    const bars = h.map((b, i) => {
      const bh = ((Hh - 2 * pad) * b[2]) / max;
      return `<rect x="${pad + i * bw + 1}" y="${Hh - pad - bh}" width="${bw - 2}" height="${bh}" fill="var(--accent)" opacity=".8"><title>${b[0]}–${b[1]} ${unit}: ${b[2]} items</title></rect>`;
    }).join("");
    const ticks = [0, Math.floor(h.length / 2)].map((i) => `<text x="${pad + i * bw}" y="${Hh - 6}" fill="var(--muted)" font-size="10" font-family="var(--mono)">${h[i][0]}</text>`).join("");
    const end = `<text x="${W - pad}" y="${Hh - 6}" fill="var(--muted)" font-size="10" font-family="var(--mono)" text-anchor="end">${h[h.length - 1][1]}</text>`;
    return `<div class="hist"><svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="${esc(label)}"><line x1="${pad}" x2="${W - pad}" y1="${Hh - pad}" y2="${Hh - pad}" stroke="var(--axis)"/>${bars}${ticks}${end}</svg><div class="cap">${esc(label)}</div></div>`;
  }
  function screenPrepare() {
    if (!S.dataset) { location.hash = S.goal ? "#dataset" : "#start"; return ""; }
    const id = ds(), cnn = id === "cnn_dailymail_200", P = M.profile, n = S.dataset.items;
    const part = (letter, key, title, on, body, status) => `<section class="part ${on ? "" : "off"}">
      <div class="parthead"><span class="letter">${letter}</span><h2>${esc(title)}</h2>${q(key)}<span class="grow"></span>${status ? `<span class="status ok">${esc(status)}</span>` : ""}</div>
      ${on ? `<p class="hint">${esc(H[key].hint)}</p><div class="body">${body}</div>` : ""}</section>`;
    const it = M.items[S.at || 0];
    const look = cnn ? `
      <div class="stats"><div><b>${P.n}</b><span>items</span></div><div><b>${P.words.median}</b><span>words, median</span></div>
        <div><b>${P.words.min}–${P.words.max}</b><span>words, shortest–longest</span></div><div><b>${P.reference.words.median}</b><span>words in a reference, median</span></div></div>
      ${hist(P.histogram, `Words per article, ${P.n} items (half between ${P.words.p25} and ${P.words.p75})`, "words")}
      <div class="pager"><span>Read an item</span><button type="button" data-at="-1" aria-label="previous">‹</button><span>row ${it.row} · ${esc(it.id.slice(0, 8))}</span><button type="button" data-at="1" aria-label="next">›</button></div>
      <div class="reader"><div class="pane"><div class="kicker">${w("item", "the item")} · article (first 600 characters)</div>${esc(it.article)}…</div>
        <div class="pane"><div class="kicker">its highlights</div>${esc(it.highlights)}</div></div>
      ${S.looked ? "" : `<div class="actions" style="margin-top:0"><button class="btn primary" id="looked" type="button">I've looked</button></div>`}
      ${cmd(`evh dataset-profile --dataset-id ${id}\nevh dataset-items --dataset-id ${id}`)}`
      : note("round 1 reads only cnn_dailymail_200's profile and items; choose it in step 2 to see this part.");
    const ways = [
      ["promote", "It came with answers", "promote the highlights as they are", "gold"],
      ["label", "Label them here", "you or a colleague write each answer, an item at a time", ""],
      ["sheet", "Bring a filled sheet", "a CSV with an answer per item (download the empty one)", ""],
    ];
    const ref = S.reference;
    return `<div class="screen wide">
      <div class="kicker">Step 3 of 5 · ${esc(S.goal.goal_id)} · ${esc(id)}</div>
      <h1>Prepare ${esc(id)}</h1>
      <p class="lead hintable">Three things the dataset needs before anything runs. Each is done once per dataset. ${q("prepare")}</p>
      ${part("a", "prepare.fetch", "Fetch its items", true, S.fetched ? `<div class="note">${n} of ${n} items fetched and checked against their hashes${cnn ? ` · items ${short(P.items_sha256)}` : ""}.</div>${cmd(`evh dataset-materialize --dataset-id ${id}`)}`
        : `<div class="actions" style="margin-top:0"><button class="btn primary" id="fetch" type="button">Fetch ${n} items</button></div><div id="fetchjob"></div>${cmd(`evh dataset-materialize --dataset-id ${id}`)}`, S.fetched ? `${n} / ${n} checked` : "")}
      ${part("b", "prepare.look", "Look inside", S.fetched, look, S.looked ? "looked at" : "")}
      ${part("c", "prepare.reference", "Its reference set", S.fetched, ref ? `<div class="note"><span class="tag gold">${esc(ref.tier)}</span> <code>${esc(ref.id)}</code> · ${n} references · by ${esc(ref.by)} · “${esc(ref.why)}”</div>
          <div class="actions" style="margin-top:0"><a class="btn" href="#reference">Change the reference set</a><a class="btn" href="#label">Label items yourself</a></div>
          ${cmd(`evh reference-promote --dataset-id ${id} --labels ${id}_highlights --tier ${ref.tier} \\\n  --by ${ref.by} --reason "${ref.why}"`)}`
        : `<div class="cards" role="radiogroup">${ways.map(([k, name, what]) => `<button type="button" class="card" data-way="${k}" aria-pressed="${S.way === k}"><b>${esc(name)}</b><span>${esc(what)}</span></button>`).join("")}</div>
          ${S.way === "promote" ? `<div class="field"><div class="name">Tier</div><div class="choices row"><label class="choice"><input type="radio" name="tier" value="gold" checked> ${w("gold")} <small>checked by people</small></label><label class="choice"><input type="radio" name="tier" value="silver"> ${w("silver")} <small>a model's answers</small></label></div></div>
            <div class="field"><div class="name">Who</div><div><input type="text" id="refby" value="you"></div></div>
            <div class="field"><div class="name">Why</div><div><input type="text" id="refwhy" value="the dataset's own highlights, as published"><div class="hint" style="grid-column:auto">recorded with the reference set, shown wherever it is used</div></div></div>
            <div class="actions" style="margin-top:0"><button class="btn primary" id="promote" type="button" ${cnn ? "" : "disabled"}>Promote ${n} answers</button></div>`
            : S.way ? `<div class="actions" style="margin-top:0"><a class="btn primary" href="#label" id="tolabel">${S.way === "label" ? "Label the items" : "Use a sheet"} →</a></div>` : ""}`, ref ? `${ref.tier} · ${n}` : "")}
      <div class="actions"><span class="status ${prepared() ? "ok" : ""}">Ready when: fetched ${S.fetched ? "✓" : "○"} · looked at ${S.looked ? "✓" : "○"} · a reference set ${ref ? "✓" : "○"}</span>
        <span class="grow"></span><a class="btn ${prepared() ? "primary" : ""}" href="${prepared() ? "#models" : "#hub"}">${prepared() ? "Next: the models →" : "Back to the goal"}</a></div>
    </div>`;
  }
  function wirePrepare() {
    $("#fetch")?.addEventListener("click", (e) => { e.target.disabled = true; progress($("#fetchjob"), `dataset-materialize · ${ds()}`, S.dataset.items, "checked", () => { S.fetched = true; save(); render(); }); });
    $("#looked")?.addEventListener("click", () => { S.looked = true; save(); render(); });
    main.querySelectorAll("[data-at]").forEach((b) => b.addEventListener("click", () => { S.at = ((S.at || 0) + Number(b.dataset.at) + M.items.length) % M.items.length; save(); render(); }));
    main.querySelectorAll("[data-way]").forEach((b) => b.addEventListener("click", () => { S.way = b.dataset.way; save(); render(); }));
    $("#promote")?.addEventListener("click", () => {
      const tier = $("input[name=tier]:checked").value;
      S.reference = { tier, id: `${tier}/${ds()}`, by: $("#refby").value || "you", why: $("#refwhy").value };
      save(); render();
    });
  }

  // ── step 4: models ───────────────────────────────────────────────────────
  const ONB = { pass: "probed and passed", probed: "probed, not yet run on an arm", check: "a probe flagged something to read", none: "never probed (run before onboarding existed)" };
  const armOf = (m) => M.arms.find((a) => a.rank === m.cnn_rank);
  const usd = (x, d = 4) => (x == null ? "—" : x === 0 ? "$0" : `$${x.toFixed(d)}`);
  const perM = (x) => (x == null ? "—" : x === 0 ? "$0" : `$${Math.round(x * 1e6).toLocaleString("en")}`);
  const secs = (ms) => (ms == null ? "—" : ms < 100 ? `${(ms / 1000).toFixed(4)} s` : `${(ms / 1000).toFixed(1)} s`);
  function screenModels() {
    if (!prepared()) { location.hash = "#hub"; return ""; }
    const all = !!S.allModels, chosen = new Set(S.models || []);
    const list = M.models.filter((m) => all || m.cnn_rank).sort((a, b) => (a.cnn_rank ?? 999) - (b.cnn_rank ?? 999) || a.id.localeCompare(b.id));
    const st = (m) => m.onboarding.split(" ")[0];
    const checked = S.checked || [];
    const a0 = M.arms[1];
    const part = (letter, key, title, on, body, status) => `<section class="part ${on ? "" : "off"}">
      <div class="parthead"><span class="letter">${letter}</span><h2>${esc(title)}</h2>${q(key)}<span class="grow"></span>${status ? `<span class="status ok">${esc(status)}</span>` : ""}</div>
      ${on ? `<p class="hint">${esc(H[key].hint)}</p><div class="body">${body}</div>` : ""}</section>`;
    const table = `<div class="inline" style="font-size:13px"><label class="choice"><input type="radio" name="mset" value="goal" ${all ? "" : "checked"}> run on this goal before (${M.models.filter((m) => m.cnn_rank).length})</label>
        <label class="choice"><input type="radio" name="mset" value="all" ${all ? "checked" : ""}> every model in the project (${M.models.length})</label></div>
      <div class="tablewrap"><table><thead><tr><th></th><th>model</th><th>kind</th><th>weights</th><th>${w("onboarding")}</th><th class="num">arms</th>${all ? "" : "<th class='num'>on this goal</th>"}</tr></thead><tbody>
      ${list.map((m) => `<tr><td><input type="checkbox" data-model="${esc(m.id)}" aria-label="choose ${esc(m.id)}" ${chosen.has(m.id) ? "checked" : ""}></td>
        <td class="mono">${esc(m.id)}</td><td>${esc(m.kind)}</td><td>${esc(m.weights)}</td>
        <td><span class="tag onb-${st(m)}" title="${esc(ONB[st(m)])}">${esc(m.onboarding)}</span></td><td class="num">${m.arms}</td>
        ${all ? "" : `<td class="num">#${m.cnn_rank} of ${M.arms.length}</td>`}</tr>`).join("")}</tbody></table></div>
      <div class="inline"><span class="muted" style="font-size:13px">${chosen.size} chosen</span><span class="grow"></span>
        <button class="btn" type="button" id="newmodel">Bring a model that isn't here</button></div>
      <div id="newmodelbox"></div>`;
    const settings = `<div class="field"><div class="name">The prompt</div><div><textarea rows="2" id="prompt">${esc(S.prompt ?? M.prompt)}</textarea><div class="hint" style="grid-column:auto">the same for every arm; the r1 arms used this one (${esc(a0.prompt_file)}). Saved, it is a prompt version named by its content${(M.round5.prompts || [])[0] ? ` (this one: <span class="mono">${esc(M.round5.prompts[0].latest)}</span>)` : ""}, and each arm records the version it ran: a changed prompt is a new version, never an edit.</div></div></div>
      <div class="field"><div class="name">Temperature</div><div class="inline"><input type="text" value="${a0.temperature}" style="width:80px"><span class="muted" style="font-size:13px">0: the same reply each time, so a rerun measures the same thing</span></div></div>
      <div class="field"><div class="name">Most it may write</div><div class="inline"><input type="text" value="${a0.max_tokens}" style="width:80px"><span class="muted" style="font-size:13px">tokens; a reply cut off here is flagged</span></div></div>
      ${note("ML models (BART) take no prompt; their arms carry their own settings.")}`;
    const smoke = checked.length ? checked.map((id) => {
      const m = M.models.find((x) => x.id === id), a = armOf(m);
      if (!a) return `<div class="part"><div class="parthead"><h3 class="mono">${esc(id)}</h3><span class="grow"></span><span class="status">no replies to show</span></div>${note("this model has no CNN run, so the mockup has no real replies for it.")}</div>`;
      const spent = a.replies.reduce((s, r) => s + (r.cost_usd || 0), 0);
      return `<details class="part smokecard"><summary class="parthead"><h3 class="mono">${esc(id)}</h3><span class="muted" style="font-size:13px">arm ${esc(a.arm)}</span><span class="grow"></span>
          <span class="status ok">3 replies · spent ${usd(spent, 5)} · all 200 ≈ ${usd(a.usd_per_item * 200, 2)}</span></summary>
        <div class="body">${a.replies.map((r, i) => `<div class="reader"><div class="pane"><div class="kicker">item ${i + 1} · its reply · ${secs(r.latency_ms)}</div>${esc(r.text)}</div>
          <div class="pane"><div class="kicker">the reference · ${w("coverage")} ${r.coverage == null ? "—" : r.coverage.toFixed(2)}</div>${esc(M.items[i].highlights)}</div></div>`).join("")}</div></details>`;
    }).join("") + note("the replies, their cost and timing are the r1 run's real first three items.")
      : `<div class="actions" style="margin-top:0"><button class="btn primary" id="smoke" type="button" ${chosen.size ? "" : "disabled"}>Check ${chosen.size || ""} arm${chosen.size === 1 ? "" : "s"} on 3 items</button><span class="muted" style="font-size:13px">a few cents; nothing is compared yet</span></div><div id="smokejob"></div>`;
    const cfg = [...chosen].map((id) => armOf(M.models.find((x) => x.id === id))).filter(Boolean)[0];
    return `<div class="screen wide">
      <div class="kicker">Step 4 of 5 · ${esc(S.goal.goal_id)} · ${esc(ds())}</div>
      <h1>Choose the models to compare</h1>
      <p class="lead hintable">A model with its prompt and settings, run on this dataset, is an ${w("arm")}. Each is checked on three items before it costs anything. ${q("models")}</p>
      ${part("a", "models.pick", "Pick the models", true, table, chosen.size ? `${chosen.size} chosen` : "")}
      ${part("b", "models.settings", "Their settings", chosen.size > 0, settings, "")}
      ${part("c", "models.smoke", "Check each on three items", chosen.size > 0, smoke, checked.length ? `${checked.length} checked` : "")}
      <div class="actions"><span class="status ${checked.length >= 2 ? "ok" : ""}">Ready when: at least two arms checked (${checked.length})</span><span class="grow"></span>
        <a class="btn ${checked.length >= 2 ? "primary" : ""}" href="${checked.length >= 2 ? "#eval" : "#hub"}">${checked.length >= 2 ? "Next: the eval →" : "Back to the goal"}</a></div>
      ${cmd(`# once per model, for every goal\nevh model-onboard <model_id>\n# each arm, on the dataset's first three items\nevh arm-smoke --config ${cfg ? `examples/summarization-cnn-dailymail/configs/arm_${cfg.arm}_n200.yaml` : "<arm config>"} --items 3`)}
    </div>`;
  }
  function wireModels() {
    main.querySelectorAll("input[name=mset]").forEach((r) => r.addEventListener("change", () => { S.allModels = r.value === "all"; save(); render(); }));
    main.querySelectorAll("[data-model]").forEach((c) => c.addEventListener("change", () => {
      const s = new Set(S.models || []);
      c.checked ? s.add(c.dataset.model) : s.delete(c.dataset.model);
      S.models = [...s]; S.checked = []; save(); render();
    }));
    $("#prompt")?.addEventListener("input", (e) => { S.prompt = e.target.value; save(); });
    $("#newmodel")?.addEventListener("click", () => { location.hash = "#model-new"; });
    $("#smoke")?.addEventListener("click", (e) => {
      e.target.disabled = true;
      const n = (S.models || []).length * 3;
      progress($("#smokejob"), `arm-smoke · ${(S.models || []).length} arms × 3 items`, n, "replies", () => { S.checked = [...(S.models || [])]; save(); render(); });
    });
  }

  // ── step 5: the eval ─────────────────────────────────────────────────────
  const VERD = (a) => (a.rank === 1 ? ["leader", "lead"] : a.verdict === "not significant" ? ["not significant", "ns"] : [a.verdict || "—", "worse"]);
  function scatter(arms, sel) {
    const W = 640, Hh = 252, l = 46, r = 16, t = 26, b = 34;
    const ys = arms.map((a) => a.coverage), y0 = Math.floor(Math.min(...ys) * 50) / 50, y1 = Math.ceil(Math.max(...ys) * 50) / 50;
    const paid = arms.filter((a) => a.usd_per_item > 0).map((a) => a.usd_per_item);
    const lx0 = Math.log10(Math.min(...paid)) - 0.1, lx1 = Math.log10(Math.max(...paid)) + 0.1, zeroW = 56;
    const X = (a) => (a.usd_per_item === 0 ? l + zeroW / 2 : l + zeroW + ((Math.log10(a.usd_per_item) - lx0) / (lx1 - lx0)) * (W - l - r - zeroW));
    const Y = (v) => t + (1 - (v - y0) / (y1 - y0)) * (Hh - t - b);
    const yt = []; for (let v = y0; v <= y1 + 1e-9; v += 0.02) yt.push(v);
    const xt = [1e-4, 1e-3, 1e-2].filter((v) => Math.log10(v) >= lx0 && Math.log10(v) <= lx1);
    const tx = (s, x, y, anchor = "middle") => `<text x="${x}" y="${y}" fill="var(--muted)" font-size="10" font-family="var(--mono)" text-anchor="${anchor}">${s}</text>`;
    return `<svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="coverage against cost per article, one dot per arm" class="scatter">
      ${yt.map((v) => `<line x1="${l}" x2="${W - r}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--hair)"/>${tx(v.toFixed(2), l - 6, Y(v) + 3, "end")}`).join("")}
      <line x1="${l + zeroW}" x2="${l + zeroW}" y1="${t}" y2="${Hh - b}" stroke="var(--axis)" stroke-dasharray="2 3"/>
      ${tx("$0", l + zeroW / 2, Hh - b + 14)}
      ${xt.map((v) => tx(`$${Math.round(v * 1e6).toLocaleString("en")}`, X({ usd_per_item: v }), Hh - b + 14)).join("")}
      ${tx("cost per 1M articles (log) →", W - r, Hh - 4, "end")}${tx("coverage ↑", 4, 10, "start")}
      ${arms.map((a) => { const [, k] = VERD(a); return `<circle cx="${X(a)}" cy="${Y(a.coverage)}" r="${a.config_id === sel ? 7 : 5}" class="dot-${k}" data-arm="${esc(a.config_id)}" tabindex="0"><title>${esc(a.arm)} · ${a.coverage.toFixed(3)} · ${perM(a.usd_per_item)} per 1M</title></circle>`; }).join("")}
      ${arms.filter((a) => a.rank <= 2).map((a) => tx(a.arm, X(a) + 9, Y(a.coverage) - 7, "start")).join("")}
    </svg>`;
  }
  function armPanel(a) {
    if (!a) return "";
    const [v] = VERD(a);
    return `<section class="part armpanel"><div class="parthead"><h2 class="mono">${esc(a.arm)}</h2>${a.baseline ? '<span class="tag gold">baseline</span>' : ""}${a.recommended ? '<span class="tag new">recommended</span>' : ""}<span class="grow"></span><button type="button" class="round" data-closearm aria-label="Close">×</button></div>
      <div class="stats" style="margin-top:12px"><div><b>${a.coverage.toFixed(3)}</b><span>coverage</span></div><div><b>${esc(v)}</b><span>${a.p ? `vs the leader, p ${esc(a.p)}` : "the best mean"}</span></div>
        <div><b>${usd(a.total_usd, 2)}</b><span>for all 200</span></div><div><b>${secs(a.p50_ms)}</b><span>per article, median</span></div></div>
      <div class="note mono" style="margin-top:12px">${esc(a.model || "a rule: the article's first three sentences")}${a.temperature != null ? ` · temperature ${a.temperature}` : ""}${a.max_tokens ? ` · max ${a.max_tokens} tokens` : ""}${a.prompt_file ? ` · ${esc(a.prompt_file)}` : ""} · run ${esc(a.run_id)}</div>
      <div class="body">${a.replies.map((r, i) => `<div class="reader"><div class="pane"><div class="kicker">row ${M.items[i].row} · its summary · coverage ${r.coverage == null ? "—" : r.coverage.toFixed(2)}</div>${esc(r.text)}</div>
        <div class="pane"><div class="kicker">the reference</div>${esc(M.items[i].highlights)}</div></div>`).join("")}</div></section>`;
  }
  function compareTable(arms, sel) {
    const max = Math.max(...arms.map((a) => a.coverage));
    return `<div class="tablewrap"><table class="cmp"><thead><tr><th class="num">#</th><th>arm</th><th>${w("measure", "coverage")}</th><th>vs the leader</th><th class="num">per 1M articles</th><th class="num">per article</th></tr></thead><tbody>
      ${arms.map((a) => { const [v, k] = VERD(a); return `<tr data-arm="${esc(a.config_id)}" class="${a.config_id === sel ? "sel" : ""}" tabindex="0"><td class="num">${a.rank}</td>
        <td><span class="mono">${esc(a.arm)}</span> ${a.baseline ? '<span class="tag gold">baseline</span>' : ""} ${a.recommended ? '<span class="tag new">recommended</span>' : ""}</td>
        <td><div class="cov"><span class="num">${a.coverage.toFixed(3)}</span><i style="width:${(100 * a.coverage) / max}%"></i></div></td>
        <td><span class="verdict v-${k}">${esc(v)}</span>${a.p ? ` <small class="muted num">p ${esc(a.p)}</small>` : ""}</td>
        <td class="num">${perM(a.usd_per_item)}</td><td class="num">${secs(a.p50_ms)}</td></tr>`; }).join("")}</tbody></table></div>`;
  }
  function screenEval() {
    if (!S.goal) { location.hash = "#start"; return ""; }
    const r4 = S.r4, tab = S.tab || (r4 ? "r4" : "r1");
    const tabs = [...M.rounds.map((r) => [r.id, `${r.id} · ${r.status}`]), ...(r4 ? [["r4", `r4 · ${r4.closed ? "closed" : "open"}`]] : [])];
    let body;
    if (tab === "r4" && r4) body = roundOpen(r4);
    else {
      const r = M.rounds.find((x) => x.id === tab);
      const arms = r.id === "r1" ? M.arms : [];
      const shown = S.showAll ? arms : arms.filter((a) => a.verdict !== "significant: worse");
      body = `<div class="roundhead"><div class="kicker">round ${esc(r.id)} · ${esc(r.status)} · ${esc((r.opened || "").slice(0, 10))}${r.closed ? ` → ${esc(r.closed.slice(0, 10))}` : ""}${r.from ? ` · from ${esc(r.from)}` : ""}</div>
          <h2 class="question">${esc(r.question)}</h2></div>
        ${arms.length ? `
          <div class="parthead" style="margin-top:20px"><h3>The comparison</h3>${q("eval.compare")}<span class="grow"></span><span class="muted" style="font-size:13px">${arms.length} arms · 200 items · scored against gold/${esc(ds() || "cnn_dailymail_200")}</span></div>
          <div class="cmpgrid"><div>${scatter(arms, S.arm)}<div class="legend"><span><i class="dot-lead"></i>leader</span><span><i class="dot-ns"></i>not significantly different</span><span><i class="dot-worse"></i>significantly worse</span></div></div>
            <div class="note"><b>What the goal's rule picks.</b> Balanced: the arms shown no worse than the best by more than 5% of it, then the cheapest. Here none could be shown within the margin, so the leader stands: <b>bart_l</b>.
              <div style="margin-top:8px">${esc(M.detectable)} ${q("eval.detect")}</div></div></div>
          ${armPanel(M.arms.find((a) => a.config_id === S.arm))}
          ${compareTable(shown, S.arm)}
          <div class="inline" style="margin-top:8px"><button type="button" class="btn" id="showall">${S.showAll ? "Hide" : "Show"} the ${arms.length - arms.filter((a) => a.verdict !== "significant: worse").length} significantly worse</button><span class="muted" style="font-size:13px">select an arm to read its summaries</span></div>`
          : `<p class="muted">${r.retired} run${r.retired === 1 ? "" : "s"} retired in this round; no new arms.</p>`}
        <div class="part" style="margin-top:20px"><div class="parthead"><h3>Its conclusion</h3><span class="grow"></span>${r.promoted ? `<span class="status ok">promoted ${esc(r.promoted.replace(/_\d{8}T\d{6}Z$/, ""))}</span>` : ""}</div><p style="margin:10px 0 0">${esc(r.conclusion)}</p></div>
        ${cmd(`evh rounds --goal ${M.goal.goal_id} --round ${r.id}\nevh goals --goal ${M.goal.goal_id}`, "the commands that show this")}`;
    }
    return `<div class="screen wide">
      <div class="kicker">Step 5 of 5 · ${esc(S.goal.goal_id)} · ${esc(ds() || "cnn_dailymail_200")}</div>
      <h1>The eval</h1>
      <p class="lead hintable">The goal measured on its dataset, in ${w("round", "rounds")}: each round asks one question, compares its ${w("arm", "arms")}, and ends in a decision kept with its reason. ${q("eval")}</p>
      <div class="answer"><div class="kicker">the answer so far · baseline bart_l</div><p>${esc(M.answer)}</p></div>
      ${baselineLine()}
      <div class="tabs" role="tablist">${tabs.map(([id, label]) => `<button type="button" role="tab" data-tab="${id}" aria-selected="${id === tab}">${esc(label)}</button>`).join("")}
        ${r4 ? "" : `<button type="button" class="btn primary" id="openr4" ${(S.checked || []).length >= 2 ? "" : "disabled"} title="${(S.checked || []).length >= 2 ? "" : "check two arms in step 4 first"}">Open round r4</button>`}</div>
      ${note("r1 to r3 are this project's real rounds; r4 is the one this walk-through opens.")}
      ${body}
    </div>`;
  }
  function baselineLine() {
    const b = (M.round5 || {}).baseline;
    if (!b) return "";
    const who = b.actor && b.actor.type !== "unknown" ? `by ${b.actor.type}:${b.actor.name}` : "who promoted it was not recorded (before 0.8.0)";
    const reason = (b.reason || "").replace(/\.+$/, "");
    const fresh = reason && !(M.answer || "").startsWith(reason.slice(0, 40));
    return `<div class="note" style="margin-bottom:16px"><b>The baseline</b> ${q("eval.baseline")} version ${b.current} for this goal on ${esc(b.dataset)}: ${esc((b.promoted_from || "").replace(/_\d{8}T\d{6}Z$/, ""))}, promoted ${esc((b.promoted_at || "").slice(0, 10))}; ${esc(who)}${fresh ? `; its reason: ${esc(reason)}` : "; its reason is the answer above"}. Every later promotion is a new version with who and why; an earlier one comes back by rollback, never by editing.
      ${cmd(`evh baselines --goal ${esc(b.goal)} --all-versions\nevh baseline-rollback --goal ${esc(b.goal)} --dataset ${esc(b.dataset)} --to <version> --reason "…" --by person:<you>`, "the commands that show and roll it back")}</div>`;
  }
  function roundOpen(r4) {
    const picked = (S.checked || []).map((id) => armOf(M.models.find((m) => m.id === id))).filter(Boolean);
    const base = M.arms[0];
    const own = picked.filter((a) => a !== base);
    const clones = r4.clones || [];
    const est = own.reduce((s, a) => s + a.usd_per_item * 200, 0) + clones.reduce((s, c) => s + (M.arms.find((a) => a.config_id === c.from) || {}).usd_per_item * 200, 0);
    const ran = !!r4.ran, retired = r4.retired || {}, promoted = r4.promoted || null;
    const results = ran ? [base, ...own].sort((a, b) => a.rank - b.rank) : [];
    const CH = { prompt: "the prompt", model: "the model", temperature: "the temperature", max_tokens: "the most it may write" };
    const runOf = (a) => a.run_id;
    return `<div class="roundhead"><div class="kicker">round r4 · ${r4.closed ? "closed" : "open"} · from r1</div></div>
      <div class="form" style="margin-top:12px">${field("eval.question", `<input type="text" id="r4q" value="${esc(r4.question || "")}" placeholder="e.g. ${esc(H["eval.question"].example)}" ${r4.closed ? "readonly" : ""}>`)}</div>
      <div class="part" style="margin-top:18px"><div class="parthead"><span class="letter">1</span><h3>Its arms</h3><span class="grow"></span><span class="status">${own.length} from step 4${clones.length ? ` · ${clones.length} cloned` : ""} · the baseline carried from r1</span></div>
        <div class="body"><div class="tablewrap"><table><thead><tr><th>arm</th><th>model</th><th class="num">dry run: 200 items</th></tr></thead><tbody>
          <tr><td class="mono">bart_l <span class="tag gold">baseline</span></td><td class="mono">${esc(base.model)}</td><td class="num">carried, not re-run</td></tr>
          ${own.map((a) => `<tr><td class="mono">${esc(a.arm)}</td><td class="mono">${esc(a.model || "—")}</td><td class="num">${usd(a.usd_per_item * 200, 2)}</td></tr>`).join("")}
          ${clones.map((c) => { const f = M.arms.find((a) => a.config_id === c.from); return `<tr><td class="mono">${esc(f.arm)} · ${esc(c.change)} <span class="tag new">clone</span></td><td class="mono">${esc(f.model || "—")}</td><td class="num">${usd(f.usd_per_item * 200, 2)}</td></tr>`; }).join("")}</tbody></table></div>
          <div class="muted" style="font-size:12px">Each estimate is the arm's real r1 cost per item × 200 (a clone's, its source's).</div>
          ${ran || r4.closed ? "" : `<details class="adv"><summary>Clone an arm and change one thing</summary><div class="inline" style="margin-top:10px">
            <select id="clfrom" aria-label="the arm to clone">${[...own].map((a) => `<option value="${esc(a.config_id)}">${esc(a.arm)}</option>`).join("")}</select>
            <select id="clwhat" aria-label="what changes">${Object.entries(CH).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
            <input type="text" id="clto" placeholder="its new value" style="width:220px"><button class="btn" type="button" id="cladd">Add the clone</button></div>
            <div class="hint" style="margin:6px 0 0">one change, so a difference in its score is that change's</div></details>`}</div></div>
      <div class="part"><div class="parthead"><span class="letter">2</span><h3>Run</h3><span class="grow"></span>${ran ? `<span class="status ok">${own.length + clones.length} runs · 200 items each</span>` : ""}</div>
        <div class="body">${ran ? "" : `<div class="actions" style="margin-top:0"><button class="btn primary" id="runr4" type="button" ${r4.question ? "" : "disabled"}>Run ${own.length + clones.length} arms · about ${usd(est, 2)}</button><span class="muted" style="font-size:13px">${r4.question ? "jobs on the server; you can close the page" : "write the round's question first"}</span></div><div id="runjob"></div>`}</div></div>
      <div class="part ${ran ? "" : "off"}"><div class="parthead"><span class="letter">3</span><h3>Results</h3>${q("eval.compare")}</div>
        ${ran ? `<div class="body">${note("a local arm shows its own re-run (the project's Linux re-runs, compared with bart_l's by evh pair-test); a hosted arm has no re-run in the project, so its r1 run is shown and says so; a clone has no run, so no scores.")}
          <div class="tablewrap"><table class="cmp r4res"><thead><tr><th>arm</th><th class="num">coverage</th><th>vs bart_l</th><th class="num">per 1M articles</th><th class="num">per article</th><th>its run</th><th></th></tr></thead><tbody>
          ${results.map((a) => { const [v, k] = VERD(a); const rt = retired[a.config_id]; const isBase = promoted ? promoted === a.config_id : a === base; const rr = a !== base && M.reruns[a.config_id];
            return `<tr class="${rt ? "retired" : ""}"><td class="mono">${esc(a.arm)} ${isBase ? '<span class="tag gold">baseline</span>' : ""}${rt ? `<div class="muted" style="font-size:12px">retired: ${esc(rt)}</div>` : ""}</td><td class="num">${(rr ? rr.coverage : a.coverage).toFixed(3)}</td>
              <td>${rr ? `<span class="num">${rr.delta.toFixed(4)}</span> <small class="muted">p ${esc(rr.p)}, one pair, uncorrected</small>` : `<span class="verdict v-${k}">${esc(v)}</span>${a.p ? ` <small class="muted">p ${esc(a.p)}</small>` : ""}`}</td><td class="num">${perM(a.usd_per_item)}</td>
              <td class="num">${secs(rr ? rr.p50_ms : a.p50_ms)}</td><td class="muted" style="font-size:12px">${a === base ? "carried from r1" : rr ? `its own, ${esc(rr.created_at.slice(0, 10))}, Linux` : "r1's (no re-run)"}</td>
              <td>${r4.closed || rt ? "" : `<button class="linkbtn" type="button" data-retire="${esc(a.config_id)}" ${a === base ? "disabled" : ""}>Retire</button> ${isBase ? "" : `<button class="linkbtn" type="button" data-promote="${esc(a.config_id)}">Make baseline</button>`}`}</td></tr>`; }).join("")}
          ${clones.map((c) => `<tr><td class="mono">${esc(M.arms.find((a) => a.config_id === c.from).arm)} · ${esc(c.change)} <span class="tag new">clone</span></td><td class="num">—</td><td class="muted">no run in the project</td><td class="num">—</td><td class="num">—</td><td class="muted" style="font-size:12px">not run</td><td></td></tr>`).join("")}</tbody></table></div>
          <div id="actbox"></div>
          ${armPanel(M.arms.find((a) => a.config_id === S.arm))}
          ${r4.closed ? `<div class="note"><b>Closed.</b> ${esc(r4.conclusion)}${promoted ? ` The baseline is now ${esc(M.arms.find((a) => a.config_id === promoted).arm)}.` : ""}</div>` : `<div class="field"><div class="name">The conclusion ${q("eval.close")}</div><div><textarea id="r4c" rows="2" placeholder="what the round showed, and what it decided"></textarea></div></div>
          <div class="actions" style="margin-top:0"><button class="btn primary" id="closer4" type="button">Close the round</button><span class="muted" style="font-size:13px">${promoted ? `promotes ${esc(M.arms.find((a) => a.config_id === promoted).arm)} as the baseline` : "the baseline stays bart_l unless you make another one the baseline"}</span></div>`}</div>` : ""}</div>
      <div class="actions"><a class="btn" href="#judge">Score with a judge too</a><a class="btn" href="#review">Review the outputs</a></div>
      ${cmd(`evh round-open --goal ${M.goal.goal_id} --dataset ${ds() || "cnn_dailymail_200"} --from r1 \\\n  --hypothesis "${r4.question || "<the question>"}"\n${own.map((a) => `evh run --config examples/summarization-cnn-dailymail/configs/arm_${a.arm}_n200.yaml --dry-run`).join("\n")}\n${own.map((a) => `evh run --config examples/summarization-cnn-dailymail/configs/arm_${a.arm}_n200.yaml`).join("\n")}${Object.entries(retired).map(([id, why]) => `\nevh round-retire --goal ${M.goal.goal_id} --round r4 --arm ${id} --reason "${why}"`).join("")}\nevh round-close --goal ${M.goal.goal_id} --round r4 --conclusion "<what it showed and decided>" --by person:<you>${promoted ? ` \\\n  --promote ${runOf(M.arms.find((a) => a.config_id === promoted))}` : ""}`)}`;
  }
  function wireEval() {
    main.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => { S.tab = b.dataset.tab; S.arm = null; save(); render(); }));
    const pickArm = (id) => { S.arm = S.arm === id ? null : id; save(); render(); };
    main.querySelectorAll("tr[data-arm], circle[data-arm]").forEach((el) => {
      el.addEventListener("click", () => pickArm(el.dataset.arm));
      el.addEventListener("keydown", (e) => { if (e.key === "Enter") pickArm(el.dataset.arm); });
    });
    $("[data-closearm]")?.addEventListener("click", () => { S.arm = null; save(); render(); });
    $("#showall")?.addEventListener("click", () => { S.showAll = !S.showAll; save(); render(); });
    $("#openr4")?.addEventListener("click", () => { S.r4 = { question: "" }; S.tab = "r4"; S.arm = null; save(); render(); });
    $("#r4q")?.addEventListener("input", (e) => { S.r4.question = e.target.value; save(); const b = $("#runr4"); if (b) b.disabled = !e.target.value.trim(); });
    $("#runr4")?.addEventListener("click", (e) => {
      e.target.disabled = true;
      const n = (S.checked || []).length * 200;
      progress($("#runjob"), `run · ${(S.checked || []).length} arms`, n, "items", () => { S.r4.ran = true; save(); render(); });
    });
    $("#closer4")?.addEventListener("click", () => { S.r4.closed = true; S.r4.conclusion = $("#r4c").value || "(no conclusion written)"; save(); render(); });
    $("#cladd")?.addEventListener("click", () => {
      const to = $("#clto").value.trim(); if (!to) { $("#clto").focus(); return; }
      S.r4.clones = [...(S.r4.clones || []), { from: $("#clfrom").value, change: `${$("#clwhat").selectedOptions[0].text}: ${to}` }]; save(); render();
    });
    const ask = (label, then) => {
      $("#actbox").innerHTML = `<div class="inline" style="margin-top:10px"><span>${esc(label)}</span><input type="text" id="actwhy" placeholder="the reason, recorded with it" style="width:320px"><button class="btn primary" type="button" id="actok">Confirm</button><button class="btn" type="button" id="actno">Cancel</button></div>`;
      $("#actwhy").focus();
      $("#actok").addEventListener("click", () => { const why = $("#actwhy").value.trim(); if (!why) { $("#actwhy").focus(); return; } then(why); });
      $("#actno").addEventListener("click", () => { $("#actbox").innerHTML = ""; });
    };
    main.querySelectorAll("[data-retire]").forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); ask(`Retire ${b.dataset.retire}:`, (why) => { S.r4.retired = { ...(S.r4.retired || {}), [b.dataset.retire]: why }; save(); render(); }); }));
    main.querySelectorAll("[data-promote]").forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); ask(`Make ${b.dataset.promote} the baseline:`, (why) => { S.r4.promoted = b.dataset.promote; S.r4.promoteWhy = why; save(); render(); }); }));
  }

  // ── the glossary ─────────────────────────────────────────────────────────
  function screenGlossary() {
    return `<div class="screen"><div class="kicker">Words</div><h1>The harness's words</h1>
      <p class="lead">Every screen uses these, taught where they first appear. The same text as the ? panels.</p>
      <dl class="gloss">${Object.entries(G).map(([k, v]) => `<dt id="w-${slug(k)}">${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl></div>`;
  }
  const outside = (what) => `<div class="screen"><h1>${what}</h1>${note("a link out of the Workbench; not part of the mockup.")}<div class="actions"><a class="btn" href="#hub">Back</a></div></div>`;

  // ── routing ──────────────────────────────────────────────────────────────
  const ROUTES = {
    start: [screenStart], "goal-new": [() => screenGoal(false), () => wireGoal(false)], "goal-edit": [() => screenGoal(true), () => wireGoal(true)],
    hub: [screenHub], dataset: [screenDataset, wireDataset], "dataset-hf": [screenHF, wireHF], prepare: [screenPrepare, wirePrepare],
    models: [screenModels, wireModels], eval: [screenEval, wireEval],
    glossary: [screenGlossary], catalog: [() => outside("The catalog")], docs: [() => outside("The docs")],
  };
  function render() {
    const route = (location.hash || "#start").slice(1);
    const [screen, wire] = ROUTES[route] || ROUTES.start;
    document.body.classList.toggle("hide-hints", !S.hints);
    $("#hints").checked = S.hints;
    const html = screen();
    if (!html) return;
    main.innerHTML = html;
    drawRail(route);
    if (wire) wire();
    main.focus?.();
  }
  const nextStep = () => (!S.dataset ? "add a dataset" : !prepared() ? "prepare the dataset" : (S.checked || []).length < 2 ? "choose the models" : !S.r4 ? "open a round" : S.r4.closed ? "review the outputs" : "finish round r4");
  window.WB = { get S() { return S; }, M, H, G, esc, $, w, q, field, cmd, note, save, render, progress, usd, perM, secs, armOf, routes: ROUTES, nextStep };
  // on a phone a table of four or more columns stacks (workbench.css): each row a card, each cell named by its column;
  // a comparison, or a table to pick rows from (its first column a checkbox), stacks compact: its row's name as the
  // card's title, the other cells on a line or two
  const stackTables = () => main.querySelectorAll("table").forEach((t) => {
    const heads = [...t.querySelectorAll("thead th")].map((th) => th.textContent.trim());
    if (heads.length < 4) return;
    const compact = t.classList.contains("cmp") || heads[0] === "";
    const title = compact ? Math.max(0, heads.findIndex((h) => /^(arm|model|decision|capture)$/i.test(h))) : -1;
    t.classList.add("stack");
    t.classList.toggle("compact", compact);
    t.querySelectorAll("tbody tr").forEach((tr) => [...tr.children].forEach((td, i) => {
      if (heads[i]) td.dataset.label = heads[i];
      td.classList.toggle("title", i === title);
    }));
  });
  new MutationObserver(stackTables).observe(main, { childList: true, subtree: true });
  window.addEventListener("hashchange", () => { help.hidden = true; render(); window.scrollTo(0, 0); });
  $("#hints").addEventListener("change", (e) => { S.hints = e.target.checked; save(); render(); });
  $("#mocknotes").addEventListener("change", (e) => document.body.classList.toggle("mocknotes-off", !e.target.checked));
  $("#reset").addEventListener("click", () => { S = fresh(); save(); help.hidden = true; location.hash = "#start"; render(); });
  $("#theme").addEventListener("click", () => {
    const r = document.documentElement, dark = r.dataset.theme ? r.dataset.theme === "dark" : !matchMedia("(prefers-color-scheme: light)").matches;
    r.dataset.theme = dark ? "light" : "dark";
  });
  $("#menubtn").addEventListener("click", () => { const n = $("#nav"), o = n.classList.toggle("open"); $("#menubtn").setAttribute("aria-expanded", String(o)); });
  window.addEventListener("hashchange", () => { $("#nav").classList.remove("open"); $("#menubtn").setAttribute("aria-expanded", "false"); });
  window.addEventListener("DOMContentLoaded", render);
})();
