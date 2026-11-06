// The Workbench mockup (UXS-005, round 1 of the mockup): the app's first, static form. Every value shown is read from
// this project by mock.js's extractor; what the mockup only pretends (jobs, saving) is labelled where it happens.
(() => {
  const M = window.MOCK, H = window.HELP, G = window.GLOSSARY;
  const KEY = "wb-mock-r1";
  const fresh = () => ({ goal: null, draft: {}, dataset: null, hf: {}, fetched: false, looked: false, reference: null, hints: true });
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
  const done = (id) => ({ goal: !!S.goal, dataset: !!S.dataset, prepare: prepared(), models: false, eval: false })[id];
  const open = (id) => ({ goal: true, dataset: !!S.goal, prepare: !!S.dataset, models: prepared(), eval: false })[id];
  function drawRail(route) {
    if (!S.goal) { layout.classList.add("no-rail"); rail.innerHTML = ""; return; }
    layout.classList.remove("no-rail");
    const cur = route.startsWith("dataset") ? "dataset" : route === "goal-edit" ? "goal" : route;
    rail.innerHTML = `<div class="label">Goal</div><div class="goalname">${esc(S.goal.title)}</div>
      <a class="step" href="#hub" ${route === "hub" ? 'aria-current="page"' : ""}><span class="dot">≡</span>Overview</a>
      ${STEPS.map((s) => {
        const cls = done(s.id) ? "done" : open(s.id) ? (cur === s.id ? "now" : "") : "locked";
        const href = open(s.id) ? `#${s.id === "goal" ? "goal-edit" : s.id}` : "#hub";
        return `<a class="step ${cls}" href="${href}" ${cur === s.id ? 'aria-current="page"' : ""}><span class="dot">${done(s.id) ? "✓" : s.n}</span>${s.name}</a>`;
      }).join("")}`;
  }

  // ── step 0: an empty project ─────────────────────────────────────────────
  function screenStart() {
    if (S.goal) { location.hash = "#hub"; return ""; }
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
        ${field("goal.strategy", `<div class="choices">${radio("strategy", "balanced", "balanced", "not significantly different from the best and within 5% of it, then the cheapest")}
            ${radio("strategy", "quality_first", "quality first", "the same quality only")}${radio("strategy", "frugal", "frugal", "anything not significantly different, then the cheapest")}</div>
            <details class="adv" style="margin-top:8px"><summary>advanced: margins, other axes (cost, speed)</summary>${note("not mocked in round 1")}</details>`)}
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
      { id: "models", title: "Models", what: "the systems you compare, each checked on three items first", status: "", go: "#models", label: "Next round" },
      { id: "eval", title: "Eval", what: "the goal measured in rounds: arms, runs, scores, a decision", status: "", go: "#eval", label: "Later round" },
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
      ${note("steps 4 and 5 are sketched in UXS-005 and mocked in the next rounds.")}
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
      if (c.dataset.source === "huggingface") { location.hash = "#dataset-hf"; return; }
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
    el.innerHTML = `<div class="job"><span>${esc(name)}</span><span class="status num" data-n>0 / ${total} ${esc(unit)}</span><div class="bar-track"><div class="bar-fill"></div></div></div>${note("a pretend job; the real one runs on the server and survives closing the page.")}`;
    let k = 0;
    const t = setInterval(() => {
      k = Math.min(total, k + Math.ceil(total / 24));
      $(".bar-fill", el).style.width = `${(100 * k) / total}%`;
      $("[data-n]", el).textContent = `${k} / ${total} ${unit}`;
      if (k >= total) { clearInterval(t); setTimeout(then, 350); }
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
          ${cmd(`evh reference-promote --dataset-id ${id} --labels ${id}_highlights --tier ${ref.tier} \\\n  --by ${ref.by} --reason "${ref.why}"`)}`
        : `<div class="cards" role="radiogroup">${ways.map(([k, name, what]) => `<button type="button" class="card" data-way="${k}" aria-pressed="${S.way === k}"><b>${esc(name)}</b><span>${esc(what)}</span></button>`).join("")}</div>
          ${S.way === "promote" ? `<div class="field"><div class="name">Tier</div><div class="choices row"><label class="choice"><input type="radio" name="tier" value="gold" checked> ${w("gold")} <small>checked by people</small></label><label class="choice"><input type="radio" name="tier" value="silver"> ${w("silver")} <small>a model's answers</small></label></div></div>
            <div class="field"><div class="name">Who</div><div><input type="text" id="refby" value="you"></div></div>
            <div class="field"><div class="name">Why</div><div><input type="text" id="refwhy" value="the dataset's own highlights, as published"><div class="hint" style="grid-column:auto">recorded with the reference set, shown wherever it is used</div></div></div>
            <div class="actions" style="margin-top:0"><button class="btn primary" id="promote" type="button" ${cnn ? "" : "disabled"}>Promote ${n} answers</button></div>`
            : S.way ? note(`round 1 mocks promoting; labelling here (W2) and the sheet come in a later round.`) : ""}`, ref ? `${ref.tier} · ${n}` : "")}
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

  // ── later rounds, and the glossary ───────────────────────────────────────
  const later = (n, name, what) => `<div class="screen"><div class="kicker">Step ${n} of 5</div><h1>${name}</h1><p class="lead">${what}</p>${note("sketched in UXS-005, mocked in the next round.")}<div class="actions"><a class="btn" href="#hub">Back to the goal</a></div></div>`;
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
    models: [() => later(4, "Models", "Bring in the models the eval will compare: each is checked on three items before it costs anything.")],
    eval: [() => later(5, "The eval", "The goal measured on its dataset, in rounds: each round compares arms, their runs and scores, and ends in a decision.")],
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
  window.addEventListener("hashchange", () => { help.hidden = true; render(); window.scrollTo(0, 0); });
  $("#hints").addEventListener("change", (e) => { S.hints = e.target.checked; save(); render(); });
  $("#mocknotes").addEventListener("change", (e) => document.body.classList.toggle("mocknotes-off", !e.target.checked));
  $("#reset").addEventListener("click", () => { S = fresh(); save(); help.hidden = true; location.hash = "#start"; render(); });
  $("#theme").addEventListener("click", () => {
    const r = document.documentElement, dark = r.dataset.theme ? r.dataset.theme === "dark" : !matchMedia("(prefers-color-scheme: light)").matches;
    r.dataset.theme = dark ? "light" : "dark";
  });
  render();
})();
