// The Workbench mockup's workflows beyond the five steps (PRD-017): home, jobs, the other dataset sources, bringing in a
// model (W5), labelling and review (W2), changing a reference (W6), a judge (W7), production (W3) and settings (W8).
// Same rule as workbench.js: every value is read from the project by mock_data.py; what is pretended is labelled.
(() => {
  const WB = window.WB;
  const { M, H, esc, $, w, q, field, cmd, note, save, progress, usd, secs } = WB;
  const S = () => WB.S;
  const main = $("#main");
  const part = (letter, key, title, on, body, status) => `<section class="part ${on ? "" : "off"}">
    <div class="parthead"><span class="letter">${letter}</span><h2>${esc(title)}</h2>${key ? q(key) : ""}<span class="grow"></span>${status ? `<span class="status ${status === "check" ? "warn" : "ok"}">${esc(status)}</span>` : ""}</div>
    ${on ? `${key && H[key] && H[key].hint ? `<p class="hint">${esc(H[key].hint)}</p>` : ""}<div class="body">${body}</div>` : ""}</section>`;
  const head = (kicker, title, lead, key) => `<div class="kicker">${kicker}</div><h1>${esc(title)}</h1>${lead ? `<p class="lead hintable">${lead} ${key ? q(key) : ""}</p>` : ""}`;
  const back = (href = "#hub", label = "Back to the goal") => `<a class="btn" href="${href}">${label}</a>`;
  const gid = () => (S().goal ? S().goal.goal_id : M.goal.goal_id);
  const dsid = () => (S().dataset ? S().dataset.id : "cnn_dailymail_200");

  // ── home: every goal and where it stands; what is running ────────────────
  function screenHome() {
    const s = S();
    const running = (s.jobs || []).filter((j) => j.status === "running");
    const mine = s.goal ? [{ id: s.goal.goal_id, title: s.goal.title, measure: s.goal.measure, direction: s.goal.direction, walk: true }] : [];
    const real = M.home.filter((g) => !mine.some((x) => x.id === g.id));
    const next = (g) => (g.walk ? WB.nextStep() : g.open.length ? `round ${g.open[0]} is open` : g.deployed ? "learn from production" : "open a round");
    return `<div class="screen wide">
      ${head("Home · project harness", "Your goals", "Each goal with where it stands and its next step. What is running shows here too, across goals.", null)}
      <div class="part"><div class="parthead"><h2>Running now</h2><span class="grow"></span><a href="#jobs" class="status">every job →</a></div>
        <div class="body">${running.length ? running.map((j) => `<div class="job"><span>${esc(j.name)}</span><span class="status">${esc(j.status)}</span></div>`).join("") : '<p class="muted" style="margin:0">Nothing is running.</p>'}</div></div>
      <div class="tablewrap" style="margin-top:18px"><table><thead><tr><th>goal</th><th>decides</th><th>datasets</th><th>rounds</th><th>reference sets</th><th>next</th></tr></thead><tbody>
        ${mine.map((g) => `<tr><td><a href="#hub"><b>${esc(g.title)}</b></a><div class="mono muted">${esc(g.id)} · this walk-through</div></td><td>${esc(g.measure)} (${esc(g.direction)})</td>
          <td>${esc(dsid())}</td><td class="num">${(M.rounds.length) + (s.r4 ? 1 : 0)}</td><td>${s.reference ? esc(s.reference.id) : "—"}</td><td><a href="#hub">${esc(next(g))} →</a></td></tr>`).join("")}
        ${real.map((g) => `<tr><td><b>${esc(g.title)}</b>${g.deployed ? ' <span class="tag new">deployed</span>' : ""}<div class="mono muted">${esc(g.id)}</div></td><td>${esc(g.measure)} (${esc(g.direction)})</td>
          <td>${g.datasets.length}</td><td class="num">${g.rounds} · last ${esc(g.last || "—")}</td><td>${g.references.length || "—"}</td>
          <td>${g.deployed ? `<a href="#production-live">${esc(next(g))} →</a>` : esc(next(g))}</td></tr>`).join("")}</tbody></table></div>
      ${note(`the walk-through's goal first, then this repository's ${M.home.length} real goals as they stand (read from data/goals and data/rounds).`)}
      <div class="actions">${s.goal ? "" : '<a class="btn primary" href="#goal-new">Set a goal</a>'}<a class="btn" href="#catalog">The catalog ↗</a></div>
    </div>`;
  }

  // ── jobs: what ran, what runs ─────────────────────────────────────────────
  function screenJobs() {
    const jobs = (S().jobs || []).slice().reverse();
    return `<div class="screen wide">${head("Jobs", "Jobs", "Every step that runs is a job: its cost first, then its progress and log, then its result. A job keeps running when the page closes; it can be stopped, and resumed where its command allows.", null)}
      ${jobs.length ? `<div class="tablewrap"><table><thead><tr><th>job</th><th>status</th><th>started</th><th class="num">progress</th><th></th></tr></thead><tbody>
        ${jobs.map((j) => `<tr><td class="mono">${esc(j.name)}</td><td><span class="verdict ${j.status === "done" ? "v-lead" : "v-ns"}">${esc(j.status)}</span></td><td class="num">${esc(j.started)}</td>
          <td class="num">${j.n} / ${j.total} ${esc(j.unit)}</td><td>${j.status === "running" ? '<button class="btn" type="button" disabled>Stop</button>' : j.resumable ? '<button class="btn" type="button" disabled>Resume</button>' : ""}</td></tr>`).join("")}</tbody></table></div>`
        : '<p class="muted">No jobs yet in this walk-through. They appear here as you fetch, check arms, run and score.</p>'}
      ${note("these are the walk-through's pretend jobs. A real one keeps its log on the server; Stop and Resume (evh run --resume) act on it.")}</div>`;
  }

  // ── step 2 from the other sources: the same four parts ────────────────────
  // what each source asks, with the example its own module documents (harness/evaluation_harness/sources/*.py)
  const SRC = {
    folder: { name: "A folder of files", fields: [["path", "raw/tickets", "the folder, on the server"], ["glob", "*.txt", "which files are items"], ["recursive", "false", "also read the folders inside"]] },
    manifest: { name: "A table", fields: [["path", "items.csv", "a .csv or .jsonl: item_id and source_url per row; other columns are fields"]] },
    croissant: { name: "Croissant", fields: [["url", "https://…/croissant.json", "the dataset's Croissant description"], ["record_set", "default", "which record set (default: the first)"], ["text", "text", "the field that is an item's text"], ["id", "id", "the field that is an item's id"]] },
    zenodo: { name: "Zenodo", fields: [["record", "6857505", "the record id: each version has its own"], ["file", "comments.csv", "which file of the record"], ["text", "comment", "the column that is an item's text"]] },
    openml: { name: "OpenML", fields: [["dataset", "61", "its OpenML id: each version has its own"], ["text", "class", "the column that is an item's text"]] },
    kaggle: { name: "Kaggle", fields: [["ref", "uciml/iris", "owner/slug"], ["version", "2", "default: the current one, recorded either way"], ["file", "Iris.csv", "the file inside it"], ["text", "Species", "the column that is an item's text"]] },
  };
  function screenSource(kind) {
    if (!S().goal) { location.hash = "#start"; return ""; }
    if (kind === "capture") return screenFromCapture();
    const src = SRC[kind], h = (S().src || {})[kind] || {};
    const query = Object.fromEntries(src.fields.map(([k, ex]) => [k, h[k] ?? ex]));
    return `<div class="screen wide">
      ${head(`Step 2 of 5 · ${esc(gid())} · from ${esc(src.name)}`, `A dataset from ${src.name.replace(/^A /, "a ")}`, "The same four parts for every source: where from, what's in it, its fields, its name.", "dataset.from")}
      ${part("a", "dataset.from", "Where from", true, `${src.fields.map(([k, ex, what]) => `<div class="field"><div class="name mono">${esc(k)}</div><div><input type="text" data-k="${esc(k)}" value="${esc(h[k] ?? "")}" placeholder="e.g. ${esc(ex)}"><div class="hint" style="grid-column:auto">${esc(what)}</div></div></div>`).join("")}
        <div class="actions" style="margin-top:0"><button class="btn primary" type="button" disabled>Read it</button><span class="muted" style="font-size:13px">reads the description and the first rows; nothing is saved yet</span></div>
        ${note(`the example values are the ones the ${kind} source documents; the mockup reads only Hugging Face, so parts b to d are on that screen.`)}`)}
      ${part("b", "dataset.columns", "What's in it", false, "")}${part("c", "dataset.fields", "Its fields", false, "")}${part("d", "dataset.name", "Name it", false, "")}
      <div class="actions"><a class="btn" href="#dataset">Other sources</a><a class="btn" href="#dataset-hf">See the four parts on Hugging Face</a></div>
      ${cmd(`evh dataset-create --source ${kind} --dataset-id <id> \\\n  --query '${JSON.stringify(query)}'`)}
    </div>`;
  }
  function wireSource(kind) {
    main.querySelectorAll("[data-k]").forEach((i) => i.addEventListener("input", () => {
      const s = S(); s.src = s.src || {}; s.src[kind] = s.src[kind] || {}; s.src[kind][i.dataset.k] = i.value; save();
      const src = SRC[kind], h = s.src[kind];
      $(".cmd pre").textContent = `evh dataset-create --source ${kind} --dataset-id <id> \\\n  --query '${JSON.stringify(Object.fromEntries(src.fields.map(([k, ex]) => [k, h[k] || ex])))}'`;
    }));
  }
  function screenFromCapture() {
    const p = M.production;
    return `<div class="screen wide">
      ${head(`Step 2 of 5 · ${esc(gid())} · from production`, "A dataset from production", "What a deployed system decided, kept as a capture, chosen and frozen as items.", "dataset.from")}
      ${part("a", "dataset.from", "Which capture", true, `<div class="tablewrap"><table><thead><tr><th></th><th>capture</th><th class="num">records</th><th>from</th><th>to</th></tr></thead><tbody>
          <tr><td><input type="radio" name="cap" checked aria-label="choose ${esc(p.capture)}"></td><td class="mono">${esc(p.capture)}</td><td class="num">${p.records}</td><td>${esc(p.first.slice(0, 10))}</td><td>${esc(p.last.slice(0, 10))}</td></tr></tbody></table></div>
        <div class="field"><div class="name">Which records</div><div><input type="text" placeholder="e.g. FIELD:VALUE keeps, FIELD!=VALUE drops"><div class="hint" style="grid-column:auto">leave empty for all</div></div></div>
        <div class="field"><div class="name">One per</div><div><input type="text" placeholder="a field, e.g. the error's fingerprint"><div class="hint" style="grid-column:auto">keeps one record for each value, so one noisy source does not fill the dataset</div></div></div>
        ${note(`this project's capture, from its deployed triage goal; the CNN goal is not deployed, so it has none.`)}`)}
      ${part("b", "dataset.columns", "What's in it", false, "")}${part("c", "dataset.fields", "Its fields", false, "")}${part("d", "dataset.name", "Name it", false, "")}
      <div class="actions"><a class="btn" href="#dataset">Other sources</a></div>
      ${cmd(`evh dataset-from-capture ${p.capture} --dataset-id <id> --one-per <field>`)}</div>`;
  }

  // ── W5: bring in a model ─────────────────────────────────────────────────
  function screenModelNew() {
    const s = S(), nm = s.newModel || {}, rec = M.onboard[nm.variant || "pass"], dep = rec.deployments.find((d) => d.onboarding.status === (nm.variant || "pass")) || rec.deployments[0];
    const rep = dep.onboarding.report || {};
    const probe = nm.probed ? `<div class="tablewrap"><table><thead><tr><th>probe</th><th>found</th></tr></thead><tbody>
        <tr><td>answers</td><td>${rep.default ? `yes, ${rep.default.tokens_out} tokens in ${rep.default.s} s (finish: ${esc(rep.default.finish)})` : "—"}</td></tr>
        <tr><td>thinks before it answers</td><td>${rep.default ? (rep.default.reasoned ? "yes, by default" : "no") : "—"}</td></tr>
        <tr><td>with the chosen settings</td><td>${rep.chosen ? `${rep.chosen.tokens_out} tokens in ${rep.chosen.s} s, reasoned: ${rep.chosen.reasoned ? "yes" : "no"}${Object.keys(rep.chosen.settings || {}).length ? ` (${esc(Object.entries(rep.chosen.settings).map(([k, v]) => `${k}: ${v}`).join(", "))})` : " (the defaults)"}` : "—"}</td></tr>
        <tr><td>speed</td><td class="num">${rep.tokens_per_s ?? "—"} tokens/s</td></tr>
        <tr><td>the same answer twice</td><td>${rep.deterministic == null ? "—" : rep.deterministic ? "yes" : "no"}</td></tr>
        <tr><td>valid JSON when asked</td><td>${rep.json_valid == null ? "—" : rep.json_valid ? "yes" : "no"}</td></tr></tbody></table></div>
      <div class="note"><b>${esc(dep.onboarding.status)}</b> on ${esc(dep.where || dep.id)}, ${esc((dep.onboarding.at || "").slice(0, 10))}${(dep.onboarding.flags || []).length ? ` · flagged: ${dep.onboarding.flags.map(esc).join("; ")}` : " · nothing flagged"}</div>
      ${rec.settings_why ? Object.entries(rec.settings_why).map(([k, v]) => `<div class="note">Setting <code>${esc(k)}: ${esc(rec.settings[k])}</code> because ${esc(v)}</div>`).join("") : ""}
      ${note(`the probe results are ${rec.id}'s real onboarding, read from its record.`)}` : "";
    return `<div class="screen wide">
      ${head("Models · bring one in", "Bring in a model", "A model is onboarded once and every goal can use it: the probes find how it answers, what it costs, whether it thinks first. What they find is shown, never typed in.", "models.pick")}
      ${part("a", null, "What it is and where it runs", true, `
        <div class="field"><div class="name">Its name</div><div><input type="text" id="nmname" value="${esc(nm.name ?? rec.name ?? rec.id)}"></div></div>
        <div class="field"><div class="name">Where it runs</div><div class="choices">
          <label class="choice"><input type="radio" name="where" value="hosted" ${(nm.where || "hosted") === "hosted" ? "checked" : ""}> a hosted gateway <small>LiteLLM, an API</small></label>
          <label class="choice"><input type="radio" name="where" value="ollama" ${nm.where === "ollama" ? "checked" : ""}> a machine of ours <small>Ollama, vLLM</small></label>
          <label class="choice"><input type="radio" name="where" value="inproc" ${nm.where === "inproc" ? "checked" : ""}> inside the harness <small>a Hugging Face model (ML)</small></label></div></div>
        <div class="field"><div class="name">Its address</div><div><input type="text" value="${esc(dep.endpoint ? `${dep.endpoint.base_url || ""} · ${dep.endpoint.model || ""}` : "")}"></div></div>
        <div class="field"><div class="name">Weights · licence</div><div class="inline"><select aria-label="weights"><option ${rec.weights === "open" ? "selected" : ""}>open</option><option ${rec.weights === "proprietary" ? "selected" : ""}>proprietary</option></select><input type="text" value="${esc(rec.licence || "")}" style="width:140px" aria-label="licence"></div></div>`)}
      ${part("b", "models.pick", "Onboard it", true, nm.probed ? probe : `<div class="inline"><button class="btn primary" type="button" id="probe">Run the probes</button>
          <label class="choice"><input type="radio" name="variant" value="pass" ${(nm.variant || "pass") === "pass" ? "checked" : ""}> show a pass</label>
          <label class="choice"><input type="radio" name="variant" value="check" ${nm.variant === "check" ? "checked" : ""}> show a check</label></div><div id="probejob"></div>`, nm.probed ? dep.onboarding.status : "")}
      ${part("c", null, "Approve it", !!nm.probed, nm.vetted ? `<div class="note">Vetted by ${esc(nm.by)}: “${esc(nm.why)}”. It is a choice in step 4 now.</div>`
        : `${dep.onboarding.status === "check" ? `<p class="mocknote">mockup: a check is read before approving: ${esc((dep.onboarding.flags || []).join("; "))}.</p>` : ""}
          <div class="field"><div class="name">Who</div><div><input type="text" id="nmby" value="you"></div></div>
          <div class="field"><div class="name">Why</div><div><input type="text" id="nmwhy" placeholder="e.g. the probes passed; reasoning off for this task"></div></div>
          <div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="vet">Approve</button><span class="muted" style="font-size:13px">then smoke it on an arm in step 4</span></div>`, nm.vetted ? "vetted" : "")}
      <div class="actions">${back("#models", "Back to the models")}</div>
      ${cmd(`# the model's record (data/models/<id>.yaml), then\nevh model-onboard ${rec.id} --deployment ${dep.id}\nevh arm-smoke --config <an arm on it> --items 3`)}
    </div>`;
  }
  function wireModelNew() {
    const s = S(); s.newModel = s.newModel || {};
    const nm = s.newModel;
    main.querySelectorAll("input[name=variant]").forEach((r) => r.addEventListener("change", () => { nm.variant = r.value; save(); WB.render(); }));
    main.querySelectorAll("input[name=where]").forEach((r) => r.addEventListener("change", () => { nm.where = r.value; save(); }));
    $("#nmname")?.addEventListener("input", (e) => { nm.name = e.target.value; save(); });
    $("#probe")?.addEventListener("click", (e) => { e.target.disabled = true; progress($("#probejob"), `model-onboard · ${M.onboard[nm.variant || "pass"].id}`, 6, "probes", () => { nm.probed = true; save(); WB.render(); }); });
    $("#vet")?.addEventListener("click", () => { nm.vetted = true; nm.by = $("#nmby").value || "you"; nm.why = $("#nmwhy").value || "(no reason written)"; save(); WB.render(); });
  }

  // ── W2: label the items (the expected answer), in the app or by a sheet ─
  function screenLabel() {
    if (!S().dataset) { location.hash = "#hub"; return ""; }
    const s = S(), at = s.labelAt || 0, it = M.items[at], ans = (s.labels || {})[it.id] ?? "";
    const n = Object.values(s.labels || {}).filter((x) => x.trim()).length;
    return `<div class="screen wide">
      ${head(`Prepare · ${esc(dsid())} · its reference set`, "Label the items", "Write the expected answer for each item. Your answers are a label set; promoted, they become the reference set every output is scored against.", "prepare.reference")}
      <div class="tabs" role="tablist"><button type="button" role="tab" aria-selected="${!s.sheetMode}" data-mode="app">Here, an item at a time</button><button type="button" role="tab" aria-selected="${!!s.sheetMode}" data-mode="sheet">With a sheet (CSV)</button></div>
      ${s.sheetMode ? `<div class="part"><div class="parthead"><span class="letter">1</span><h3>Get the sheet</h3></div><div class="body"><p style="margin:0">A CSV with a row per item: its id, its text, an empty answer. Fill it in a spreadsheet, or hand it to someone.</p>
          <div class="actions" style="margin-top:0"><button class="btn" type="button" disabled>Download the sheet</button></div></div></div>
        <div class="part"><div class="parthead"><span class="letter">2</span><h3>Bring it back</h3></div><div class="body"><p style="margin:0">Drop the filled sheet here. It is checked before anything is kept: the item ids, an answer per row, the label choices.</p>
          <div class="dropzone">drop a .csv</div></div></div>
        ${note("downloading and dropping files are not mocked.")}
        ${cmd(`evh label-sheet --dataset-id ${dsid()} --out sheet.csv --items unlabelled\nevh label-import sheet.csv --dataset-id ${dsid()} --set <name> --by you`)}`
      : `<div class="pager" style="margin:12px 0"><button type="button" data-lat="-1" aria-label="previous">‹</button><span>item ${at + 1} of ${M.items.length} shown · row ${it.row}</span><button type="button" data-lat="1" aria-label="next">›</button><span class="grow"></span><span>${n} labelled</span></div>
        <div class="reader"><div class="pane"><div class="kicker">${w("item", "the item")} · the article (first 600 characters)</div>${esc(it.article)}…</div>
          <div class="pane"><div class="kicker">your answer: its summary</div><textarea id="lab" rows="8" placeholder="2-3 short sentences: the story's main points">${esc(ans)}</textarea>
            <div class="inline" style="margin-top:8px"><button class="btn" type="button" id="labhl">Start from its highlights</button><button class="btn primary" type="button" id="labnext">Save and next</button></div></div></div>
        ${note(`the dataset has ${M.profile.n} items; the mockup shows the first ${M.items.length}.`)}
        ${cmd(`# each answer is kept as it is saved, in a label set of yours\nevh label-import <answers> --dataset-id ${dsid()} --set ${dsid()}_mine --by you`)}`}
      <div class="actions">${n ? `<a class="btn primary" href="#reference">Promote ${n} labels to a reference set →</a>` : ""}${back("#prepare", "Back to prepare")}</div>
    </div>`;
  }
  function wireLabel() {
    const s = S();
    main.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => { s.sheetMode = b.dataset.mode === "sheet"; save(); WB.render(); }));
    main.querySelectorAll("[data-lat]").forEach((b) => b.addEventListener("click", () => { s.labelAt = ((s.labelAt || 0) + Number(b.dataset.lat) + M.items.length) % M.items.length; save(); WB.render(); }));
    const keep = () => { s.labels = s.labels || {}; s.labels[M.items[s.labelAt || 0].id] = $("#lab").value; save(); };
    $("#lab")?.addEventListener("input", keep);
    $("#labhl")?.addEventListener("click", () => { $("#lab").value = M.items[s.labelAt || 0].highlights; keep(); });
    $("#labnext")?.addEventListener("click", () => { keep(); s.labelAt = ((s.labelAt || 0) + 1) % M.items.length; save(); WB.render(); });
  }

  // ── W2: review outputs side by side, pick, tag, note ─────────────────────
  function screenReview() {
    if (!S().goal) { location.hash = "#start"; return ""; }
    const s = S(), rv = s.review || (s.review = { a: M.arms[0].config_id, b: M.arms[1].config_id, at: 0, marks: {} });
    const A = M.arms.find((x) => x.config_id === rv.a), B = M.arms.find((x) => x.config_id === rv.b);
    const at = rv.at, it = M.items[at], mk = rv.marks[it.id] || {}, blind = rv.blind !== false;
    const flip = blind && (it.row % 2 === 1);
    const L = flip ? B : A, R = flip ? A : B, nameOf = (x, side) => (blind ? side : x.arm);
    const done = Object.values(rv.marks).filter((x) => x.pick).length;
    const opt = (sel) => M.arms.map((x) => `<option value="${esc(x.config_id)}" ${x.config_id === sel ? "selected" : ""}>${esc(x.arm)} · ${x.coverage.toFixed(3)}</option>`).join("");
    const out = (x, side) => `<div class="pane"><div class="kicker">${esc(nameOf(x, side))}${blind ? "" : ` · coverage ${x.replies[at].coverage.toFixed(2)}`}</div>${esc(x.replies[at].text)}</div>`;
    return `<div class="screen wide">
      ${head(`Day to day · ${esc(gid())} · review and label`, "Review the outputs", "Read two arms' outputs on the same item, say which is better, and tag what went wrong. Your picks and tags are kept as a label set, with who made them.", null)}
      <div class="inline" style="margin-bottom:12px"><label class="choice">compare <select id="rva" aria-label="first arm">${opt(rv.a)}</select></label><label class="choice">with <select id="rvb" aria-label="second arm">${opt(rv.b)}</select></label>
        <label class="choice"><input type="checkbox" id="rvblind" ${blind ? "checked" : ""}> hide which arm is which</label><span class="grow"></span><span class="muted">${done} of ${M.items.length - 1} picked</span></div>
      <div class="pager"><button type="button" data-rat="-1" aria-label="previous">‹</button><span>item ${at + 1} of ${M.items.length - 1} · row ${it.row}</span><button type="button" data-rat="1" aria-label="next">›</button></div>
      <details class="part" style="margin-top:10px"><summary class="parthead"><h3>The article and its reference</h3></summary><div class="body"><div class="reader"><div class="pane">${esc(it.article)}…</div><div class="pane"><div class="kicker">the reference</div>${esc(it.highlights)}</div></div></div></details>
      <div class="reader even" style="margin-top:12px">${out(L, "A")}${out(R, "B")}</div>
      <div class="part" style="margin-top:12px"><div class="body" style="margin-top:0">
        <div class="field"><div class="name">Which is better</div><div class="choices row">${[["A", "A"], ["B", "B"], ["tie", "the same"], ["neither", "neither is good"]].map(([v, l]) => `<label class="choice"><input type="radio" name="pick" value="${v}" ${mk.pick === v ? "checked" : ""}> ${l}</label>`).join("")}</div></div>
        <div class="field"><div class="name">What went wrong</div><div class="chips">${M.modes.map((m) => `<label class="chip" title="${esc(m.description)}"><input type="checkbox" data-mode="${esc(m.id)}" ${(mk.tags || []).includes(m.id) ? "checked" : ""}> ${esc(m.id)}</label>`).join("")}<button class="btn" type="button" disabled>+ a mode</button></div></div>
          <div class="hint">the ${w("failure mode", "failure modes")}: proposed from this eval's own format checks; point at one for when it applies; scores stay hidden while arms are hidden</div></div>
        <div class="field"><div class="name">A note</div><div><input type="text" id="rvnote" value="${esc(mk.note || "")}" placeholder="anything a number would miss"></div></div>
        <div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="rvnext">Save and next</button></div></div></div>
      ${note(`the outputs are the arms' real summaries of the first ${M.items.length - 1} items; the failure modes are the CNN adapter's checks (narration, label, markdown, bullets, paragraphs, overlong, truncated).`)}
      ${cmd(`# the same sheet, to fill elsewhere, and read back\nevh inspect --sheet --goal ${gid()} --round r1 --runs ${A.config_id},${B.config_id} --csv sheet.csv --fill pick\nevh sheet-import sheet.csv --dataset-id ${dsid()} --by you --kind person --set <name>`)}
    </div>`;
  }
  function wireReview() {
    const s = S(), rv = s.review;
    const it = () => M.items[rv.at];
    const mark = () => (rv.marks[it().id] = rv.marks[it().id] || {});
    $("#rva").addEventListener("change", (e) => { rv.a = e.target.value; save(); WB.render(); });
    $("#rvb").addEventListener("change", (e) => { rv.b = e.target.value; save(); WB.render(); });
    $("#rvblind").addEventListener("change", (e) => { rv.blind = e.target.checked; save(); WB.render(); });
    main.querySelectorAll("[data-rat]").forEach((b) => b.addEventListener("click", () => { rv.at = (rv.at + Number(b.dataset.rat) + (M.items.length - 1)) % (M.items.length - 1); save(); WB.render(); }));
    main.querySelectorAll("input[name=pick]").forEach((r) => r.addEventListener("change", () => { mark().pick = r.value; save(); }));
    main.querySelectorAll("[data-mode]").forEach((c) => c.addEventListener("change", () => { const m = mark(); const t = new Set(m.tags || []); c.checked ? t.add(c.dataset.mode) : t.delete(c.dataset.mode); m.tags = [...t]; save(); }));
    $("#rvnote").addEventListener("input", (e) => { mark().note = e.target.value; save(); });
    $("#rvnext").addEventListener("click", () => { rv.at = (rv.at + 1) % (M.items.length - 1); save(); WB.render(); });
  }

  // ── W6: change the reference, see what moves first ───────────────────────
  function screenReference() {
    if (!S().dataset) { location.hash = "#hub"; return ""; }
    const s = S(), sv = M.silver, gold = M.arms;
    const rankOf = (arm) => (gold.find((g) => g.arm === arm) || {}).rank;
    const rows = sv.rows.slice(0, 12);
    return `<div class="screen wide">
      ${head(`Prepare · ${esc(dsid())} · its reference set`, "Change the reference set", "A different reference can reorder the arms. See what it moves before anything is re-scored.", "prepare.reference")}
      ${part("a", null, "The new reference set", true, `<div class="choices">
          <label class="choice"><input type="radio" name="newref" checked> <span><b>silver/${esc(dsid())}</b> <small>written by the arm ${esc(sv.authored_by)} ($${sv.cost_usd.toFixed(2)}), ${esc(sv.created_at.slice(0, 10))}</small></span></label>
          ${Object.keys(s.labels || {}).length ? `<label class="choice"><input type="radio" name="newref" disabled> <span>your labels <small>(${Object.keys(s.labels).length} item${Object.keys(s.labels).length === 1 ? "" : "s"}; preview not mocked)</small></span></label>` : ""}</div>
        <p class="note" style="margin:0">${esc(sv.caveat)}</p>`)}
      ${part("b", null, "What it moves", true, `<div class="tablewrap"><table class="cmp"><thead><tr><th class="num">on silver</th><th>arm</th><th class="num">coverage</th><th>vs the leader</th><th class="num">on gold</th><th>moves</th></tr></thead><tbody>
          ${rows.map((r) => { const g = rankOf(r.arm), mv = g ? g - r.rank : 0; return `<tr><td class="num">${r.rank}</td><td class="mono">${esc(r.arm)}${r.arm.split("_")[0] === sv.authored_by.split("_")[0] ? ' <span class="tag new">author\'s family</span>' : ""}</td><td class="num">${r.coverage.toFixed(3)}</td>
            <td><span class="verdict ${r.verdict === "leader" ? "v-lead" : r.verdict === "not significant" ? "v-ns" : "v-worse"}">${esc(r.verdict)}</span>${r.p ? ` <small class="muted">p ${esc(r.p)}</small>` : ""}</td><td class="num">${g ?? "—"}</td><td class="num ${mv > 0 ? "v-lead" : mv < 0 ? "v-worse" : ""}">${mv > 0 ? `↑ ${mv}` : mv < 0 ? `↓ ${-mv}` : "—"}</td></tr>`; }).join("")}</tbody></table></div>
        <div class="note">On gold, bart_l leads and deepseek_m is not significantly different. On this silver set, ${esc(sv.rows[0].arm)} leads and deepseek_m is significantly worse (p ${esc(sv.rows[1].p)}). The two arms that rise most are the author's own family: read that before promoting it.</div>
        ${note(`both orders are the harness's real scores on the same 200 items (evh goals --goal ${M.goal.goal_id}); the first 12 of ${sv.rows.length} shown.`)}`)}
      ${part("c", null, "Promote it", true, s.newRef ? `<div class="note"><span class="tag">silver</span> promoted by ${esc(s.newRef.by)}: “${esc(s.newRef.why)}”. Re-scoring the arms is a job: <a href="#jobs">jobs →</a></div>`
        : `<div class="field"><div class="name">Who</div><div><input type="text" id="refby2" value="you"></div></div>
          <div class="field"><div class="name">Why</div><div><input type="text" id="refwhy2" placeholder="why these answers are the yardstick"></div></div>
          <div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="promref">Promote and re-score</button><span class="muted" style="font-size:13px">re-scoring reads stored outputs: no calls, $0</span></div><div id="rescorejob"></div>`)}
      <div class="actions">${back("#prepare", "Back to prepare")}</div>
      ${cmd(`evh score-preview --goal ${M.goal.goal_id}\nevh reference-promote --dataset-id ${dsid()} --labels <set> --tier silver --by you --reason "<why>"\nevh rescore --goal ${M.goal.goal_id} --why "<why>"`)}
    </div>`;
  }
  function wireReference() {
    const s = S();
    $("#promref")?.addEventListener("click", (e) => {
      e.target.disabled = true;
      const by = $("#refby2").value || "you", why = $("#refwhy2").value || "(no reason written)";
      progress($("#rescorejob"), `rescore · ${M.arms.length} arms`, M.arms.length, "arms re-scored", () => { s.newRef = { by, why }; save(); WB.render(); });
    });
  }

  // ── W7: a judge ───────────────────────────────────────────────────────────
  function screenJudge() {
    const J = M.judge, s = S(), v = J.validation, c = J.checks["goyal2022-cnn"];
    const passes = v.runs.every((r) => r.value > r.min_metric);
    return `<div class="screen wide">
      ${head(`Scoring · ${esc(gid())}`, "A judge for this goal", "A judge is a model that scores outputs the way a person would. It may decide only after it agrees with people's labels on a set where both are known.", null)}
      ${part("a", null, "Its judges", true, `<div class="tablewrap"><table><thead><tr><th>judge</th><th>model</th><th>family</th></tr></thead><tbody>${J.judges.map((j) => `<tr><td class="mono">${esc(j.id)}</td><td class="mono">${esc(j.model)}</td><td>${esc(j.family)}</td></tr>`).join("")}</tbody></table></div>
        <div class="hint">two families at least, so one vendor's taste does not decide; chosen from onboarded models</div>`)}
      ${part("b", null, "How it judges", true, `<div class="field"><div class="name">Mode</div><div class="choices row"><label class="choice"><input type="radio" name="jm"> grade each</label><label class="choice"><input type="radio" name="jm" ${J.protocol.listwise ? "checked" : ""}> rank a block</label><label class="choice"><input type="radio" name="jm"> pick the better of two</label></div></div>
        <div class="field"><div class="name">The prompt</div><div class="mono">${esc(J.prompt)}</div></div>
        <div class="field"><div class="name">Guards</div><div class="muted" style="font-size:13px">${J.protocol.outputs_per_call} outputs per call · arms hidden · ${Math.round(J.protocol.position_check_fraction * 100)}% re-asked in another order · ${Math.round(J.protocol.noise_check_fraction * 100)}% re-asked as is</div></div>
        <div class="field"><div class="name">At most</div><div class="num">$${J.cost_cap_usd.toFixed(2)} for the whole pass</div></div>`)}
      ${part("c", null, "Does it agree with people?", true, `<div class="tablewrap"><table><thead><tr><th>judge</th><th class="num">${esc(v.metric)} on ${esc(v.dataset)}</th><th class="num">the best free scorer</th><th class="num">best pick on CNN (Goyal 2022)</th><th class="num">by chance</th></tr></thead><tbody>
          ${v.runs.map((r) => { const g = c.judges[r.judge]; return `<tr><td class="mono">${esc(r.judge)}</td><td class="num">${r.value.toFixed(3)}</td><td class="num">${r.min_metric.toFixed(3)}</td><td class="num">${g ? `${g.rate.toFixed(2)} (${g.ci95[0].toFixed(2)}–${g.ci95[1].toFixed(2)})` : "—"}</td><td class="num">${g ? g.chance.toFixed(2) : "—"}</td></tr>`; }).join("")}</tbody></table></div>
        <div class="note">${esc(v.what)}. ${passes ? "Both judges beat the best free scorer, so the judge may score this goal." : "A judge below the best free scorer may not decide."}</div>
        ${note("the judges, guards, cost cap and agreement are judge-summ-v2's real record and validation reports.")}`, passes ? "validated" : "")}
      ${part("d", null, "Score the arms with it", true, s.judged ? `<div class="note">Judged: a job ran over the round's arms. <a href="#jobs">jobs →</a></div>`
        : `<div class="actions" style="margin-top:0"><button class="btn" type="button" id="jdry">Dry run: the cost first</button><button class="btn primary" type="button" id="jrun" ${s.jdry ? "" : "disabled"}>Judge ${M.arms.length} arms</button></div>
          <div id="jout">${s.jdry ? `<div class="note">Dry run: at most $${J.cost_cap_usd.toFixed(2)}, counting verdicts already stored.</div>` : ""}</div>`)}
      <div class="actions">${back("#eval", "Back to the eval")}</div>
      ${cmd(`evh judge-score --dataset-id ${dsid()} --scorer ${J.id} --dry-run\nevh judge-score --dataset-id ${dsid()} --scorer ${J.id}`)}
    </div>`;
  }
  function wireJudge() {
    const s = S();
    $("#jdry")?.addEventListener("click", () => { s.jdry = true; save(); WB.render(); });
    $("#jrun")?.addEventListener("click", (e) => { e.target.disabled = true; progress($("#jout"), `judge-score · ${M.judge.id}`, M.arms.length, "arms judged", () => { s.judged = true; save(); WB.render(); }); });
  }

  // ── W3: production ───────────────────────────────────────────────────────
  function screenProductionGoal() {
    if (!S().goal) { location.hash = "#start"; return ""; }
    return `<div class="screen">
      ${head(`Day to day · ${esc(gid())} · production`, "Production", "Once a goal's choice is deployed, this is where you learn from it: what it decided, where it was wrong or saw something new, and the next dataset version made from those.", null)}
      <div class="part"><h3 style="margin:0">This goal is not deployed</h3><p class="muted" style="margin:8px 0 0">Nothing has been captured from a system running its choice. When it is, its captures show here.</p></div>
      <div class="actions"><a class="btn primary" href="#production-live">See it on this project's deployed goal</a>${back()}</div>
      ${note("the CNN goal is not deployed; this project's triage goal is, so production is shown on it.")}</div>`;
  }
  function screenProductionLive() {
    const p = M.production, s = S(), pr = s.prod || {};
    const base = p.rows.find((r) => r.arm.startsWith("triage_baseline")), lead = p.rows[0];
    const nItems = (M.datasets.find((d) => d.id === p.dataset) || {}).items;
    const baseVs = base ? base.vs.split(", ").slice(1).join(", ") : "";
    return `<div class="screen wide">
      ${head(`Day to day · ${esc(p.goal)} · production`, p.title, "What the deployed system decided, compared with what people later decided, and the rows worth adding to the next dataset version.", null)}
      ${part("1", null, "What it decided", true, `<div class="stats"><div><b>${p.records}</b><span>decisions captured</span></div><div><b>${esc(p.first.slice(0, 10))}</b><span>first</span></div><div><b>${esc(p.last.slice(0, 10))}</b><span>last</span></div><div><b>${esc(p.captured_at.slice(0, 10))}</b><span>captured</span></div></div>
        <div class="note mono">${esc(p.capture)} → dataset ${esc(p.dataset)} (${nItems} labelled decisions)</div>
        <div class="actions" style="margin-top:0"><button class="btn" type="button" disabled>Capture since ${esc(p.captured_at.slice(0, 10))}</button></div>`)}
      ${part("2", null, "Against people's labels", true, `<div class="tablewrap"><table class="cmp"><thead><tr><th>arm</th><th class="num">triage_cost</th><th>vs the leader</th><th class="num">per decision</th></tr></thead><tbody>
          ${p.rows.map((r) => `<tr><td class="mono">${esc(r.arm)}${r === base ? ' <span class="tag gold">production\'s model</span>' : ""}${r === lead ? ' <span class="tag new">recommended</span>' : ""}</td><td class="num">${r.triage_cost.toFixed(3)}</td><td>${esc(r.vs)}</td><td class="num">${esc(r.usd_per_item)}</td></tr>`).join("")}</tbody></table></div>
        <div class="note">${esc(p.decides)}. Production's own model costs ${base ? base.triage_cost.toFixed(3) : "—"} against ${lead.triage_cost.toFixed(3)} for the recommended prompt (${esc(baseVs)}); ${nItems} items are too few to show a tie, so the goal names no contenders.</div>
        ${note("the arms and numbers are the triage goal's real comparison on its v2 dataset (evh goals --goal triage_orrery).")}`)}
      ${part("3", null, "Pick the rows for the next version", true, `<p style="margin:0">Rows where production was wrong, or saw something the dataset does not have yet. Each pick has a reason; picks wait until a new version is made.</p>
        <div class="choices row"><label class="choice"><input type="radio" name="pf" checked> wrong against the labels</label><label class="choice"><input type="radio" name="pf"> new since ${esc(p.dataset)}</label><label class="choice"><input type="radio" name="pf"> not labelled yet</label></div>
        ${pr.picked ? `<div class="note">${pr.picked} rows picked, waiting for the next version.</div>` : `<div class="actions" style="margin-top:0"><button class="btn" type="button" id="pickrows">Pick 3 rows</button></div>`}
        ${note("which rows were wrong is not computed in the mockup; the project has no picks waiting (evh picks).")}`, pr.picked ? `${pr.picked} picked` : "")}
      ${part("4", null, "The next dataset version", !!pr.picked, pr.extended ? `<div class="note">${esc(p.dataset)} + ${pr.picked} picks → the next version, recorded as made from it.</div>` : `<div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="extend">Make the next version</button></div>`)}
      <div class="actions">${back("#home", "Home")}</div>
      ${cmd(`evh capture … (the deployment's importer)\nevh arm-from-capture --dataset-id ${p.dataset} --capture ${p.capture} --as production_<date>_v1\nevh label-from-capture --dataset-id ${p.dataset} --capture ${p.capture} --map rules.yaml --set outcomes\nevh inspect --goal ${p.goal} --wrong-against gold_${p.dataset}\nevh pick --dataset-id ${p.dataset} --item <id> --note "<why>"\nevh dataset-extend ${p.dataset} --dataset-id <next> --picks`)}
    </div>`;
  }
  function wireProductionLive() {
    const s = S(); s.prod = s.prod || {};
    $("#pickrows")?.addEventListener("click", () => { s.prod.picked = 3; save(); WB.render(); });
    $("#extend")?.addEventListener("click", () => { s.prod.extended = true; save(); WB.render(); });
  }

  // ── W8: settings, terse ──────────────────────────────────────────────────
  function screenSettings() {
    const rows = [
      ["Where the project keeps its data", "files (data/ in git) or one SQLite database; moving keeps everything", "evh data-migrate --to sqlite --dry-run"],
      ["Check the project", "the integrity checks over every dataset, run and reference; a job, not a Save button", "evh validate"],
      ["Committed runs and their floors", "which run folders the checks hold to their numbers", "evh data-put validate.json …"],
      ["The goal policy", "what every goal must have before a round closes", "evh data-put goals/policy.yaml …"],
      ["Budgets", "a round's spending cap, checked before a run starts", "evh round-open … --budget-usd 5"],
      ["Publish a dataset", "to a new Hugging Face repo, read back to check it", "evh dataset-publish --dataset-id <id> --to huggingface --query '{\"repo\": \"owner/name\"}'"],
    ];
    return `<div class="screen wide">${head("Settings", "Govern and maintain", "Rare, so terse: each is one form or one command.", null)}
      <div class="tablewrap"><table><thead><tr><th>what</th><th>why</th><th>the command</th></tr></thead><tbody>${rows.map(([a, b, c]) => `<tr><td><b>${esc(a)}</b></td><td>${esc(b)}</td><td class="mono" style="font-size:12px">${esc(c)}</td></tr>`).join("")}</tbody></table></div>
      ${note("each row opens a short form in the real Workbench; here they are listed only.")}</div>`;
  }

  Object.assign(WB.routes, {
    home: [screenHome], jobs: [screenJobs], "model-new": [screenModelNew, wireModelNew], label: [screenLabel, wireLabel],
    review: [screenReview, wireReview], reference: [screenReference, wireReference], judge: [screenJudge, wireJudge],
    production: [screenProductionGoal], "production-live": [screenProductionLive, wireProductionLive], settings: [screenSettings],
    "dataset-src-capture": [() => screenSource("capture")],
    ...Object.fromEntries(Object.keys(SRC).map((k) => [`dataset-src-${k}`, [() => screenSource(k), () => wireSource(k)]])),
  });
})();
