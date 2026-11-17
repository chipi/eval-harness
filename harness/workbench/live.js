// The Workbench on its server (RFC-032): served by `catalog-serve` under /workbench/, it reads the model's API instead
// of the mockup's data. Opened any other way (the mockup's own files, its artifact) it stays the mockup.
// Screens are wired workflow by workflow as their entities land on the model; until then a screen says which step
// wires it, never this repository's data as if it were the project's.
(() => {
  const WB = window.WB;
  const LIVE = { on: false, cache: {}, pending: {}, failed: null };
  window.LIVE = LIVE;
  const esc = WB.esc;

  // One API read, kept until the page reloads; a screen asks again by key and is drawn again when it lands.
  function load(key, path, raw = false) {
    if (key in LIVE.cache) return LIVE.cache[key];
    if (!LIVE.pending[key]) {
      LIVE.pending[key] = fetch(`/api/v1${path}`, { credentials: "same-origin" })
        .then(async (r) => {
          const body = await r.json().catch(() => ({}));
          LIVE.cache[key] = r.ok ? (raw ? body : body.result) : { error: body.error || `${r.status}` };
        })
        .catch((e) => { LIVE.cache[key] = { error: String(e) }; })
        .finally(() => { delete LIVE.pending[key]; WB.render(); });
    }
    return undefined;
  }
  const loading = (what) => `<p class="muted" role="status">Reading ${esc(what)}…</p>`;
  const failed = (x) => `<p class="note" role="alert"><b>Could not read it.</b> ${esc(x.error)}</p>`;

  // ── home: every goal and where it stands; what is running ───────────────────
  function screenHome() {
    const goals = load("goals", "/goals");
    const jobs = load("jobs", `/jobs?state=${encodeURIComponent("queued,running,running (unsupervised)")}`, true);
    const head = `<div class="kicker">Home</div><h1>Your goals</h1>
      <p class="lead">Each goal with where it stands and its next step. What is running shows here too, across goals.</p>`;
    if (goals === undefined) return `<div class="screen wide">${head}${loading("the goals")}</div>`;
    if (goals.error) return `<div class="screen wide">${head}${failed(goals)}</div>`;
    const rows = goals.goals.map((g) => {
      const st = load(`status:${g.goal}`, `/goals/${encodeURIComponent(g.goal)}/status`);
      const m = g.measure || {};
      const ds = st && !st.error ? st.datasets.filter((d) => d.decides).map((d) => d.dataset).join(", ") : "…";
      const rounds = st && !st.error ? st.rounds.length : "…";
      const next = st && !st.error ? `${esc(st.next.what)}` : st && st.error ? esc(st.error) : "…";
      return `<tr><td><a href="#goal/${encodeURIComponent(g.goal)}"><b>${esc(g.title || g.goal)}</b></a><div class="mono muted">${esc(g.goal)}</div></td>
        <td>${esc(m.measure || "")} (${esc(m.direction || "")})</td><td>${esc(ds)}</td><td class="num">${rounds}</td><td>${next}</td></tr>`;
    });
    const running = jobs === undefined ? loading("the jobs") : jobs.error ? failed(jobs)
      : jobs.jobs.length ? jobs.jobs.map((j) => `<div class="job"><span>${esc(j.operation)}</span><span class="status">${esc(j.state)}</span></div>`).join("")
      : '<p class="muted" style="margin:0">Nothing is running.</p>';
    return `<div class="screen wide">${head}
      <div class="part"><div class="parthead"><h2>Running now</h2></div><div class="body">${running}</div></div>
      ${goals.goals.length ? `<div class="tablewrap" style="margin-top:18px"><table><thead><tr><th>goal</th><th>decides</th><th>datasets</th><th class="num">rounds</th><th>next</th></tr></thead><tbody>${rows.join("")}</tbody></table></div>`
        : `<div class="answer" style="margin-top:18px"><p><b>What should this project help you decide?</b></p><p>An evaluation starts with a goal: the decision you need to make, and how you will know which system is better for it.</p></div>`}
      <div class="actions"><a class="btn primary" href="#goal-new">${goals.goals.length ? "New goal" : "Start with a goal"}</a><a class="btn" href="#models">Models</a><a class="btn" href="${location.origin}/">The catalog ↗</a></div></div>`;
  }

  // ── a goal: where it stands, and the next step ─────────────────────────────
  function screenGoal(id) {
    const st = load(`status:${id}`, `/goals/${encodeURIComponent(id)}/status`);
    const head = `<div class="kicker">Goal · ${esc(id)}</div>`;
    if (st === undefined) return `<div class="screen wide">${head}${loading("the goal")}</div>`;
    if (st.error) return `<div class="screen wide">${head}${failed(st)}<div class="actions"><a class="btn" href="#home">Back to your goals</a></div></div>`;
    const m = st.measure || {};
    const ds = st.datasets.map((d) => `<tr><td class="mono"><a href="#prepare/${enc(d.dataset)}">${esc(d.dataset)}</a></td><td>${esc(d.role || "")}${d.decides ? "" : " · does not decide"}</td>
      <td>${d.made ? (d.materialized ? "made, fetched" : "made, not fetched") : "not made"}</td><td>${d.references.length ? d.references.map(esc).join(", ") : "—"}</td>
      <td class="num">${d.runs} run(s) · ${d.arms} arm(s)</td><td>${d.baseline ? `v${d.baseline.version}` : "—"}</td></tr>`).join("");
    const rounds = st.rounds.map((r) => `<li><b>${esc(r.round)}</b> ${esc(r.status)}: ${esc(r.question || "")}</li>`).join("");
    return `<div class="screen wide">${head}<h1>${esc(st.title || id)}</h1>
      <p class="lead">Decides on ${esc(m.measure || "")} (${esc(m.direction || "")} is better).</p>
      <div class="answer"><div class="kicker">next step</div><p>${esc(st.next.what)}</p><p class="source"><code>${esc(st.next.command)}</code></p></div>
      <div class="tablewrap" style="margin-top:18px"><table><thead><tr><th>dataset</th><th>role</th><th>items</th><th>reference</th><th class="num">runs</th><th>baseline</th></tr></thead><tbody>${ds}</tbody></table></div>
      ${rounds ? `<h2 style="margin-top:22px">Rounds</h2><ul>${rounds}</ul>` : ""}
      ${st.running.length ? `<h2 style="margin-top:22px">Running now</h2><ul>${st.running.map((j) => `<li>${esc(j.operation)} · ${esc(j.state)}</li>`).join("")}</ul>` : ""}
      ${WB.cmd(`evh goal-status ${id}`)}
      <div class="actions"><a class="btn primary" href="#dataset/${encodeURIComponent(id)}">Add a dataset</a><a class="btn" href="#systems/${encodeURIComponent(id)}">Choose the systems</a><a class="btn" href="#eval/${encodeURIComponent(id)}">The eval</a><a class="btn" href="#goal-edit/${encodeURIComponent(id)}">Edit the goal</a><a class="btn" href="#home">Back to your goals</a></div></div>`;
  }

  // ── writes: who acted, the data header, and the model's refusal shown as it is ──────────────────────
  // Every change names who made it (RFC-027). The name is asked once and kept in this browser only.
  const who = () => { try { return localStorage.getItem("evh.by") || ""; } catch { return ""; } };
  const byField = (id) => `<div class="field"><label class="name" for="${id}">Who you are</label><div>
      <input type="text" id="${id}" value="${esc(who())}" placeholder="your name" autocomplete="name">
      <div class="hint">kept with the change as person:&lt;name&gt;</div></div></div>`;
  function byOf(id) {
    const v = (document.getElementById(id)?.value || "").trim();
    if (!v) return null;
    try { localStorage.setItem("evh.by", v); } catch { /* kept for this change only */ }
    return v.includes(":") ? v : `person:${v}`;
  }
  async function send(method, path, body) {
    const r = await fetch(`/api/v1${path}`, {
      method, credentials: "same-origin", headers: { "Content-Type": "application/json", "X-EVH-Data": "1" }, body: JSON.stringify(body),
    });
    const b = await r.json().catch(() => ({}));
    if (!r.ok) {
      const e = new Error(b.error || `${r.status}`);
      e.problems = b.problems || [];
      throw e;
    }
    return b.result ?? b;
  }
  const refusal = (e) => `<p class="note" role="alert"><b>Not saved.</b> ${esc(e.message)}</p>${(e.problems || []).length
    ? `<ul class="problems">${e.problems.map((p) => `<li><code>${esc((p.path || []).join("."))}</code> ${esc(p.message)}</li>`).join("")}</ul>` : ""}`;
  const forget = (prefix) => Object.keys(LIVE.cache).filter((k) => k.startsWith(prefix)).forEach((k) => delete LIVE.cache[k]);

  // ── unsent changes (UXS-005, "For every live screen"; owner 2026-11-17) ──────────────────────
  // What a person types is sent only by the form's own button. Until then the form is marked, its button (enabled only
  // then) says what it will write, the screen is not redrawn under it (workbench.js) and leaving asks first. A form is
  // an element with data-form; its button is [data-send], its mark [data-unsent-mark].
  const UNSENT = new Map();
  WB.unsent = () => [...UNSENT.values()];
  WB.forgetUnsent = () => UNSENT.clear();
  window.addEventListener("beforeunload", (e) => { if (UNSENT.size) { e.preventDefault(); e.returnValue = ""; } });
  const mark = '<span class="unsent" data-unsent-mark hidden>not saved yet</span>';
  function holds(form, what) {
    const root = document.querySelector(`[data-form="${form}"]`);
    if (!root) return;
    const btn = root.querySelector("[data-send]"), m = root.querySelector("[data-unsent-mark]");
    const show = () => {
      const on = UNSENT.has(form);
      if (m) m.hidden = !on;
      if (btn) { btn.disabled = !on; btn.textContent = what(); }
    };
    const changed = () => { UNSENT.set(form, what()); show(); };
    root.addEventListener("input", changed);
    root.addEventListener("change", changed);
    show();
  }
  const sent = (form) => UNSENT.delete(form);
  const enc = encodeURIComponent;
  const STATE_TAG = { vetted: "pass", onboarded: "pass", check: "check", none: "none" };
  const stateTag = (s) => `<span class="tag onb-${STATE_TAG[s] || "none"}">${esc(s)}</span>`;

  // ── models: every model in the project and its state ──────────────────────
  function screenModels() {
    const ms = load("models", "/models");
    const head = `<div class="kicker">Models</div><h1>Models in this project</h1>
      <p class="lead">A model is onboarded once for each place it runs, and every goal can use it. Choosing the ones a goal
      compares comes with its systems.</p>`;
    if (ms === undefined) return `<div class="screen wide">${head}${loading("the models")}</div>`;
    if (ms.error) return `<div class="screen wide">${head}${failed(ms)}</div>`;
    const rows = ms.models.map((m) => `<tr><td><a href="#model/${enc(m.model)}"><b>${esc(m.name || m.model)}</b></a>${m.name && m.name !== m.model ? `<div class="mono muted">${esc(m.model)}</div>` : ""}</td>
      <td>${esc(m.kind || "")}</td><td>${esc(m.weights || "")}</td><td class="num">${m.deployments}</td><td>${stateTag(m.state)}</td></tr>`).join("");
    return `<div class="screen wide">${head}
      ${ms.models.length ? `<div class="tablewrap"><table><thead><tr><th>model</th><th>kind</th><th>weights</th><th class="num">deployments</th><th>state</th></tr></thead><tbody>${rows}</tbody></table></div>`
        : '<p class="muted">No models yet.</p>'}
      <div class="actions"><a class="btn primary" href="#model-new">Bring in a model</a></div>
      ${WB.cmd("evh model-list")}</div>`;
  }

  // ── a model: its facts, and each deployment with its checks; onboard one, accept what it raises ─────
  const onboardJobs = {};
  // model-onboard exits 0 on ONBOARD PASS and 6 on ONBOARD CHECK: both are its answer, which the onboarding above shows
  const jobLine = (j) => {
    if (["queued", "running", "running (unsupervised)"].includes(j.state)) return "The probes are running…";
    if (j.state === "succeeded") return "The probes passed.";
    if (j.state === "failed" && j.exit === 6) return "The probes found something to read: it is listed above.";
    return `The probes did not finish: ${j.state}${j.exit != null ? ` (exit ${j.exit})` : ""}; <code>evh jobs-logs ${esc(j.id || "")}</code> shows why.`;
  };
  function deploymentPart(model, d) {
    const r = d.record, st = d.state, on = st.onboarding;
    const job = onboardJobs[`${model}/${d.deployment}`];
    const flags = on && (on.flags || []).length ? `<ul>${on.flags.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : "";
    const smokes = Object.entries(st.smokes).map(([cid, s]) => `<li><span class="mono">${esc(cid)}</span>: ${esc(s.status)} at ${esc((s.at || "").slice(0, 16))}</li>`).join("");
    const accepted = Object.entries(st.accepted).map(([k, why]) => `<li><b>${esc(k)}</b>: ${esc(why)}</li>`).join("");
    const k = `${d.deployment}`;
    return `<section class="part"><div class="parthead"><h2 class="mono">${esc(d.deployment)}</h2><span class="muted">${esc(r.where || "")}${r.backend ? ` · ${esc(r.backend)}` : ""}${r.tag ? ` · ${esc(r.tag)}` : ""}</span>
      <span class="grow"></span>${on ? `<span class="status ${on.status === "pass" ? "ok" : "warn"}">${esc(on.status)}</span>` : '<span class="status">not onboarded</span>'}</div>
      <div class="body">
        <div class="checks"><p>${on ? `Onboarded ${esc((on.at || "").slice(0, 16))}${on.where ? ` on ${esc(on.where)}` : ""}.` : "Never onboarded: the probes find how it answers, whether it thinks first, what it costs."} ${st.checks} check(s) kept.</p>
        ${flags ? `<p>Flagged:</p>${flags}` : ""}
        ${smokes ? `<p>Arm smokes:</p><ul>${smokes}</ul>` : ""}
        ${accepted ? `<p>Accepted as this deployment's nature:</p><ul>${accepted}</ul>` : ""}</div>
        <h3>Onboard it</h3>
        <div class="field"><label class="name" for="cap-${esc(k)}">Spend at most (USD)</label><div><input type="number" id="cap-${esc(k)}" min="0.01" step="0.01" inputmode="decimal">
          <div class="hint">a model of ours costs nothing; a hosted one is charged for each probe call</div></div></div>
        <div class="actions" style="margin-top:0"><button class="btn primary" type="button" data-onboard="${esc(k)}">Run the probes</button></div>
        <div id="job-${esc(k)}" aria-live="polite">${job ? `<p class="muted">${jobLine(job)}</p>` : ""}</div>
        ${on && on.status === "check" ? `<div data-form="accept-${esc(k)}"><h3>Accept what it raises</h3>
          <p class="muted">When a flag is the deployment's own nature (a hosted gateway has no build to pin), accept it with why: it is kept in its checks and no longer counts against it.</p>
          <div class="field"><label class="name" for="flag-${esc(k)}">The flag's kind</label><div><input type="text" id="flag-${esc(k)}" placeholder="the words before its colon: reasoning, where it ran"></div></div>
          <div class="field"><label class="name" for="why-${esc(k)}">Why</label><div><input type="text" id="why-${esc(k)}" placeholder="a sentence"></div></div>
          ${byField(`by-${k}`)}
          <div class="actions" style="margin-top:0"><button class="btn" type="button" data-send data-accept="${esc(k)}">Accept it</button>${mark}</div>
          <div id="acc-${esc(k)}"></div></div>` : ""}
      </div></section>`;
  }
  function screenModel(id) {
    const m = load(`model:${id}`, `/models/${enc(id)}`);
    const head = `<div class="kicker">Model · ${esc(id)}</div>`;
    if (m === undefined) return `<div class="screen wide">${head}${loading("the model")}</div>`;
    if (m.error) return `<div class="screen wide">${head}${failed(m)}<div class="actions"><a class="btn" href="#models">The models</a></div></div>`;
    const r = m.record;
    const facts = [["kind", r.kind], ["weights", r.weights], ["licence", r.licence], ["aliases", (r.aliases || []).join(", ")],
      ["settings", Object.entries(r.settings || {}).map(([k, v]) => `${k}: ${v}`).join(", ")]].filter(([, v]) => v);
    return `<div class="screen wide">${head}<h1>${esc(r.name || id)} ${stateTag(m.state)}</h1>
      <dl class="gloss">${facts.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>
      <h2 style="margin-top:22px">Where it runs</h2>
      ${m.deployments.map((d) => deploymentPart(id, d)).join("") || '<p class="muted">No deployment yet: add the first below.</p>'}
      <section class="part" data-form="dep-add"><div class="parthead"><h2>Add a deployment</h2></div><div class="body">
        <div class="field"><label class="name" for="dep-id">Its id</label><div><input type="text" id="dep-id" placeholder="mac, dgx, openrouter"></div></div>
        <div class="field"><label class="name" for="dep-where">Where</label><div><input type="text" id="dep-where" placeholder="the machine, or the hosted route"></div></div>
        <div class="field"><label class="name" for="dep-tag">Its tag</label><div><input type="text" id="dep-tag" placeholder="the name the server knows it by"></div></div>
        <div class="field"><label class="name" for="dep-url">Its address</label><div><input type="text" id="dep-url" placeholder="http://host:11434/v1" inputmode="url"></div></div>
        ${byField("dep-by")}
        <div class="actions" style="margin-top:0"><button class="btn" type="button" id="dep-add" data-send>Add it</button>${mark}</div><div id="dep-out"></div></div></section>
      ${WB.cmd(`evh model-show ${id}\nevh model-onboard --model-id ${id} --deployment <deployment>\nevh deployment-accept ${id} <deployment> --flag "<kind>" --why "<a sentence>"`)}
      <div class="actions"><a class="btn" href="#models">The models</a></div></div>`;
  }
  async function follow(model, dep, jobId) {
    const key = `${model}/${dep}`;
    for (;;) {
      const r = await fetch(`/api/v1/jobs/${enc(jobId)}`, { credentials: "same-origin" });
      const j = await r.json().catch(() => ({}));
      onboardJobs[key] = j;
      const box = document.getElementById(`job-${dep}`);
      if (box) box.innerHTML = `<p class="muted">${jobLine(j)}</p>`;
      if (!["queued", "running", "running (unsupervised)"].includes(j.state)) break;
      await new Promise((ok) => setTimeout(ok, 2000));
    }
    forget(`model:${model}`);
    forget("models");
    WB.render();
  }
  function wireModel() {
    const id = WB.param || "";
    const val = (x) => (document.getElementById(x)?.value || "").trim();
    holds("dep-add", () => `Add deployment ${val("dep-id") || "…"}`);
    document.querySelectorAll("[data-accept]").forEach((b) => {
      const dep = b.dataset.accept;
      holds(`accept-${dep}`, () => `Accept ${val(`flag-${dep}`) || "the flag"} as ${dep}'s own`);
    });
    document.querySelectorAll("[data-onboard]").forEach((b) => b.addEventListener("click", async () => {
      const dep = b.dataset.onboard, out = document.getElementById(`job-${dep}`);
      const cap = Number(document.getElementById(`cap-${dep}`).value);
      if (!(cap > 0)) { out.innerHTML = '<p class="note" role="alert">Say the most the probes may spend first.</p>'; return; }
      b.disabled = true;
      try {
        const j = await send("POST", `/models/${enc(id)}/onboard`, { deployment: dep, by: byOf(`by-${dep}`) || (who() ? `person:${who()}` : undefined), max_cost_usd: cap });
        follow(id, dep, j.id);
      } catch (e) { out.innerHTML = refusal(e); b.disabled = false; }
    }));
    document.querySelectorAll("[data-accept]").forEach((b) => b.addEventListener("click", async () => {
      const dep = b.dataset.accept, out = document.getElementById(`acc-${dep}`), by = byOf(`by-${dep}`);
      if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are: an acceptance names who made it.</p>'; return; }
      try {
        await send("POST", `/models/${enc(id)}/deployments/${enc(dep)}/accept`, { flag: document.getElementById(`flag-${dep}`).value, why: document.getElementById(`why-${dep}`).value, by });
        sent(`accept-${dep}`); forget(`model:${id}`); forget("models"); WB.render();
      } catch (e) { out.innerHTML = refusal(e); }
    }));
    document.getElementById("dep-add")?.addEventListener("click", async () => {
      const out = document.getElementById("dep-out"), by = byOf("dep-by"), v = (x) => document.getElementById(x).value.trim();
      if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are: a change names who made it.</p>'; return; }
      const set = { where: v("dep-where") };
      if (v("dep-tag")) set.tag = v("dep-tag");
      if (v("dep-url")) Object.assign(set, { "endpoint.base_url": v("dep-url"), "endpoint.provider": "openai", "endpoint.model": v("dep-tag") || id });
      try {
        await send("POST", `/models/${enc(id)}/deployments/${enc(v("dep-id"))}`, { set, by });
        sent("dep-add"); forget(`model:${id}`); forget("models"); WB.render();
      } catch (e) { out.innerHTML = refusal(e); }
    });
  }

  // ── bring in a model: what it is, then where it runs on its own page ──────────────────────────
  function screenModelNew() {
    return `<div class="screen" data-form="model-new"><div class="kicker">Models · bring one in</div><h1>Bring in a model</h1>
      <p class="lead">A model is onboarded once and every goal can use it. Say what it is here; where it runs and its
      probes come next, on its page.</p>
      <div class="field"><label class="name" for="nm-id">Its id</label><div><input type="text" id="nm-id" placeholder="gemma4-12b" autocapitalize="off" spellcheck="false">
        <div class="hint">lowercase letters, digits, . _ -</div></div></div>
      <div class="field"><label class="name" for="nm-name">Its name</label><div><input type="text" id="nm-name" placeholder="Gemma 4 12B"></div></div>
      <div class="field"><div class="name" id="nm-kind-l">What it is</div><div class="choices" role="radiogroup" aria-labelledby="nm-kind-l">
        <label class="choice"><input type="radio" name="nm-kind" value="llm" checked> a language model</label>
        <label class="choice"><input type="radio" name="nm-kind" value="ml"> an ML model <small>a Hugging Face model the harness runs</small></label>
        <label class="choice"><input type="radio" name="nm-kind" value="baseline"> a baseline <small>a rule, the lead sentences</small></label></div></div>
      <div class="field"><label class="name" for="nm-aliases">The ids runs record</label><div><input type="text" id="nm-aliases" placeholder="gemma4:12b, eval-gemma-12b">
        <div class="hint">the model name an arm sends, comma-separated: a gateway alias, an Ollama tag, a Hugging Face repo</div></div></div>
      <div class="field"><div class="name" id="nm-weights-l">Its weights</div><div class="choices" role="radiogroup" aria-labelledby="nm-weights-l">
        <label class="choice"><input type="radio" name="nm-weights" value="open"> open <small>they can be downloaded</small></label>
        <label class="choice"><input type="radio" name="nm-weights" value="proprietary"> proprietary <small>only its vendor serves it</small></label></div></div>
      <div class="field"><label class="name" for="nm-licence">Licence</label><div><input type="text" id="nm-licence" placeholder="Apache-2.0"></div></div>
      ${byField("nm-by")}
      <div class="actions"><button class="btn primary" type="button" id="nm-save" data-send>Make it</button>${mark}<a class="btn" href="#models">The models</a></div>
      <div id="nm-out"></div>
      ${WB.cmd("evh model-new <id> --set kind=llm --set aliases.0=<the id runs record>")}</div>`;
  }
  function wireModelNew() {
    holds("model-new", () => `Make model ${(document.getElementById("nm-id")?.value || "").trim() || "…"}`);
    document.getElementById("nm-save")?.addEventListener("click", async () => {
      const out = document.getElementById("nm-out"), v = (x) => document.getElementById(x).value.trim(), by = byOf("nm-by");
      if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are: a change names who made it.</p>'; return; }
      const id = v("nm-id"), set = { kind: document.querySelector("input[name=nm-kind]:checked").value };
      v("nm-aliases").split(",").map((a) => a.trim()).filter(Boolean).forEach((a, i) => { set[`aliases.${i}`] = a; });
      const wts = document.querySelector("input[name=nm-weights]:checked");
      if (wts) set.weights = wts.value;
      if (v("nm-name")) set.name = v("nm-name");
      if (v("nm-licence")) set.licence = v("nm-licence");
      try {
        await send("POST", `/models/${enc(id)}`, { set, by });
        sent("model-new");
        forget("models");
        location.hash = `#model/${enc(id)}`;
      } catch (e) { out.innerHTML = refusal(e); }
    });
  }

  // ── step 1: a goal, made or changed (UXS-005 step 1): five things on one screen, the rest "advanced" ──────────
  const slugOf = (t) => String(t || "").toLowerCase().replace(/\(([^)]*)\)/g, " $1").replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 40);
  const STRATEGIES = [["balanced", "balanced", "not worse than the best by more than its margin, then the cheapest"],
    ["quality_first", "quality first", "the same quality only"], ["frugal", "frugal", "a wider margin, then the cheapest"]];
  const TIES = ["cost", "speed", "quality"];
  function screenGoalForm(goal) {
    const editing = !!goal;
    const ms = load("metrics", "/metrics"), rec = editing ? load(`goalrec:${goal}`, `/goals/${enc(goal)}`) : {};
    const head = `<div class="kicker">Step 1${editing ? ` · ${esc(goal)}` : ""}</div><h1>${editing ? "The goal" : "Set the goal"}</h1>
      <p class="lead">A goal is the decision this evaluation helps you make. Everything later is measured against it.</p>`;
    if (ms === undefined || rec === undefined) return `<div class="screen">${head}${loading(editing ? "the goal" : "the measures")}</div>`;
    if (ms.error || rec.error) return `<div class="screen">${head}${failed(ms.error ? ms : rec)}</div>`;
    const g = editing ? rec.record : {}, sc = g.success_criteria || {}, pr = sc.primary || {};
    const margin = ((sc.axes || {}).quality || {}).margin, tie = sc.tie_break || ["cost", "speed"];
    const radio = (name, val, label, small, on) => `<label class="choice"><input type="radio" name="${name}" value="${val}" ${on ? "checked" : ""}> <span>${esc(label)}${small ? ` <small>${esc(small)}</small>` : ""}</span></label>`;
    const tieSel = (id, cur) => `<select id="${id}" aria-label="${id === "gf-tie1" ? "first" : "then"}">${TIES.map((t) => `<option ${cur === t ? "selected" : ""}>${t}</option>`).join("")}</select>`;
    return `<div class="screen" data-form="goal-form">${head}
      <div class="field"><label class="name" for="gf-title">What is it?</label><div><input type="text" id="gf-title" value="${esc(g.title || "")}" placeholder="Short news summaries (CNN)">
        <div class="hint">a short title, as you would say it to a colleague</div>
        <label class="idline">id <input type="text" id="gf-id" class="idinput" value="${esc(g.goal_id || "")}" placeholder="made from the title" ${editing ? "readonly" : ""} autocapitalize="off" spellcheck="false"></label></div></div>
      <div class="field"><label class="name" for="gf-statement">What is it for?</label><div><textarea id="gf-statement" rows="2" placeholder="Pick a model that writes a short summary of a news article, at a known cost.">${esc(g.statement || "")}</textarea>
        <div class="hint">one sentence: what you want, for whom, so that what</div></div></div>
      <div class="field"><label class="name" for="gf-decision">The decision</label><div><textarea id="gf-decision" rows="2" placeholder="Which models can be told apart on summary quality, and what each costs.">${esc(g.decision || "")}</textarea>
        <div class="hint">the choice you will make from the result</div></div></div>
      <div class="field"><label class="name" for="gf-measure">How you'll judge</label><div><input type="text" id="gf-measure" list="gf-measures" value="${esc(pr.measure || "")}" placeholder="overlap_f1" autocapitalize="off" spellcheck="false">
        <datalist id="gf-measures">${ms.metrics.map((m) => `<option value="${esc(m.metric)}">${esc(m.description || "")}</option>`).join("")}</datalist>
        <div class="choices row" role="radiogroup" aria-label="which way is better">${radio("gf-dir", "higher", "higher is better", "", (pr.direction || "higher") === "higher")}${radio("gf-dir", "lower", "lower is better", "", pr.direction === "lower")}</div>
        <div class="hint">the number that decides which system is better: one the project's scorers produce, or a new one</div></div></div>
      <div class="field"><div class="name" id="gf-strategy-l">How a winner is picked</div><div><div class="choices" role="radiogroup" aria-labelledby="gf-strategy-l">${STRATEGIES.map(([v, l, sm]) => radio("gf-strategy", v, l, sm, (sc.strategy || "balanced") === v)).join("")}</div>
        <details class="adv" style="margin-top:8px"><summary>advanced: the margin, the tie-break</summary><div class="form" style="gap:12px;margin-top:12px">
          <div class="field"><label class="name" for="gf-margin">Margin</label><div><input type="text" id="gf-margin" inputmode="decimal" value="${esc(margin ?? "")}" placeholder="the strategy's default">
            <div class="hint">how much worse than the best an arm may be and still win, in the measure's units</div></div></div>
          <div class="field"><div class="name">Then pick by</div><div class="inline">${tieSel("gf-tie1", tie[0])}${tieSel("gf-tie2", tie[1])}</div></div></div></details></div></div>
      ${byField("gf-by")}
      <div class="actions"><button class="btn primary" type="button" id="gf-save" data-send>${editing ? "Save the goal" : "Make the goal"}</button>${mark}
        <a class="btn" href="${editing ? `#goal/${enc(goal)}` : "#home"}">Cancel</a></div>
      <div id="gf-out"></div>
      ${WB.cmd(editing ? `evh goal-set ${goal} --set KEY=VALUE` : "evh goal-new <id> --set title=... --set statement=... --set decision=... --set success_criteria.primary.measure=... --set success_criteria.primary.direction=higher --set 'datasets=[]'")}</div>`;
  }
  function wireGoalForm() {
    const goal = WB.param || "", editing = !!goal;
    const v = (id) => (document.getElementById(id)?.value || "").trim();
    const idIn = document.getElementById("gf-id");
    if (!idIn) return;
    let idEdited = editing;
    idIn.addEventListener("input", () => { idEdited = !!idIn.value; });
    document.getElementById("gf-title").addEventListener("input", () => { if (!idEdited) idIn.value = slugOf(v("gf-title")); });
    document.getElementById("gf-measure").addEventListener("change", () => {
      const m = ((LIVE.cache.metrics || {}).metrics || []).find((x) => x.metric === v("gf-measure"));
      const dir = m && ["higher", "lower"].includes(m.better) ? m.better : null;
      if (dir) document.querySelector(`input[name=gf-dir][value=${dir}]`).checked = true;
    });
    holds("goal-form", () => (editing ? `Save goal ${goal}` : `Make goal ${v("gf-id") || "…"}`));
    document.getElementById("gf-save").addEventListener("click", async () => {
      const out = document.getElementById("gf-out"), by = byOf("gf-by");
      if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are: a change names who made it.</p>'; return; }
      const pick = (name) => document.querySelector(`input[name=${name}]:checked`)?.value;
      const want = {
        title: v("gf-title"), statement: v("gf-statement"), decision: v("gf-decision"),
        "success_criteria.primary.measure": v("gf-measure"), "success_criteria.primary.direction": pick("gf-dir"),
        "success_criteria.strategy": pick("gf-strategy"),
      };
      if (v("gf-margin")) want["success_criteria.axes.quality.margin"] = Number(v("gf-margin"));
      const tie = [v("gf-tie1"), v("gf-tie2")];
      const rec = editing ? (LIVE.cache[`goalrec:${goal}`] || {}).record || {} : {};
      const now = (key) => key.split(".").reduce((o, k) => (o == null ? undefined : o[k]), rec);
      if (editing ? JSON.stringify(now("success_criteria.tie_break") || ["cost", "speed"]) !== JSON.stringify(tie) : tie.join() !== "cost,speed") want["success_criteria.tie_break"] = tie;
      const set = editing ? Object.fromEntries(Object.entries(want).filter(([k, x]) => JSON.stringify(now(k)) !== JSON.stringify(x))) : { ...want, datasets: [] };
      const id = editing ? goal : v("gf-id");
      try {
        if (editing && !Object.keys(set).length) { sent("goal-form"); location.hash = `#goal/${enc(goal)}`; return; }
        await send(editing ? "PATCH" : "POST", `/goals/${enc(id)}`, { set, by });
        sent("goal-form"); forget("goals"); forget(`goalrec:${id}`); forget(`status:${id}`);
        location.hash = `#goal/${enc(id)}`;
      } catch (e) { out.innerHTML = refusal(e); }
    });
  }

  // ── step 2: a dataset for a goal (UXS-005 step 2; source-preview, dataset-create with its answers) ─────────────
  // The choices are longer work: kept in this browser until the dataset is made ("For every live screen").
  const SOURCES = {
    huggingface: ["Hugging Face", [["ref", "the dataset", "abisee/cnn_dailymail"], ["config", "its config", "3.0.0"], ["split", "the split", "test"]]],
    folder: ["a folder of files", [["path", "the folder, inside the project", "raw/tickets"], ["glob", "which files", "*.txt"]]],
    manifest: ["a table: CSV, JSON lines", [["path", "the .csv or .jsonl, inside the project: item_id, source_url, field columns", "items.csv"]]],
    croissant: ["Croissant", [["url", "its croissant.json's address", "https://…/croissant.json"], ["path", "or its path, inside the project", "croissant.json"], ["record_set", "the record set", "default"]]],
    zenodo: ["Zenodo", [["record", "the record's number", "10157504"], ["file", "the file in it", "data.csv"]]],
    openml: ["OpenML", [["dataset", "the dataset's number", "61"]]],
    kaggle: ["Kaggle", [["ref", "owner/dataset", "uciml/iris"], ["version", "its version", "2"], ["file", "the file in it", "Iris.csv"]]],
  };
  const COLUMNS = [["text", "the item: the column a system receives", "article"],
    ["answer", "the expected answer's column, if it has one: it becomes the reference set in step 3", "highlights"],
    ["id", "the item's id column (default: the row number)", "id"], ["limit", "take the first N rows (default: all)", "200"]];
  const NUMBERS = new Set(["record", "dataset", "version", "limit"]);
  const tabular = (src) => !["folder", "manifest"].includes(src);
  const draftKey = (goal) => `evh.draft.dataset.${goal}`;
  const readDraft = (goal) => { try { return JSON.parse(localStorage.getItem(draftKey(goal)) || "null"); } catch { return null; } };
  const keepDraft = (goal, d) => { try { localStorage.setItem(draftKey(goal), JSON.stringify(d)); } catch { /* this visit only */ } };
  const dropDraft = (goal) => { try { localStorage.removeItem(draftKey(goal)); } catch { /* nothing kept */ } };
  const queryOf = (d) => {
    const q = {};
    for (const [k, v] of Object.entries(d.q || {})) if (String(v).trim()) q[k] = NUMBERS.has(k) && /^\d+$/.test(String(v).trim()) ? Number(v) : String(v).trim();
    return q;
  };
  async function watchJob(id, box, what) {
    for (;;) {
      const r = await fetch(`/api/v1/jobs/${enc(id)}`, { credentials: "same-origin" });
      const j = await r.json().catch(() => ({}));
      if (box) box.innerHTML = `<p class="muted" aria-live="polite">${esc(what)}: ${esc(j.state || "…")}</p>`;
      if (!["queued", "running", "running (unsupervised)"].includes(j.state)) return j;
      await new Promise((ok) => setTimeout(ok, 1000));
    }
  }
  const jobRefusal = async (j) => {
    const r = await fetch(`/api/v1/jobs/${enc(j.id)}/log`, { credentials: "same-origin" });
    const log = ((await r.json().catch(() => ({}))).log || "").trim().split("\n").filter((x) => x.startsWith("ERROR")).pop();
    return `<p class="note" role="alert"><b>${esc(j.state)}.</b> ${esc(log || "see the job's log")}</p>`;
  };
  const previews = {};
  const fieldRows = (fields) => (fields || []).length
    ? `<div class="tablewrap"><table><thead><tr><th>keep</th><th>field</th><th>type</th><th>values</th></tr></thead><tbody>${fields.map((f, i) => `<tr>
        <td><input type="checkbox" data-keep="${i}" aria-label="keep ${esc(f.name)}" ${f.keep === false ? "" : "checked"}></td><td class="mono">${esc(f.name)}</td>
        <td>${esc(f.type)}</td><td>${esc((f.values || []).join(", "))}</td></tr>`).join("")}</tbody></table></div>`
    : "";
  function screenDatasetNew(goal) {
    const head = `<div class="kicker">Step 2 · ${esc(goal)}</div><h1>Add a dataset</h1>
      <p class="lead">The examples your systems will be tested on: a frozen list of items, each with its hash, so every system sees exactly the same ones, now and later.</p>`;
    if (!goal) return `<div class="screen">${head}<p class="note">Open it from a goal.</p><div class="actions"><a class="btn" href="#home">Your goals</a></div></div>`;
    const ds = load("datasets", "/datasets"), rec = load(`goalrec:${goal}`, `/goals/${enc(goal)}`);
    if (ds === undefined || rec === undefined) return `<div class="screen wide">${head}${loading("the datasets")}</div>`;
    if (ds.error || rec.error) return `<div class="screen wide">${head}${failed(ds.error ? ds : rec)}</div>`;
    const d = readDraft(goal) || { source: "", q: {}, id: "", role: "validation" };
    if (readDraft(goal)) UNSENT.set(`dataset-new`, `a new dataset for ${goal}`);
    const have = new Set((rec.record.datasets || []).map((x) => x.dataset_id));
    const options = ds.datasets.filter((x) => !have.has(x.dataset)).map((x) => `<option value="${esc(x.dataset)}">${esc(x.dataset)} · ${x.items} item(s)</option>`).join("");
    const src = d.source, fields = src ? [...SOURCES[src][1], ...(tabular(src) ? COLUMNS : [])] : [];
    const pv = previews[goal];
    const roles = ["validation", "test"].map((r) => `<label class="choice"><input type="radio" name="ds-role" value="${r}" ${d.role === r ? "checked" : ""}> ${r} <small>${r === "test" ? "the final answer, kept untouched" : "while you choose and tune"}</small></label>`).join("");
    const rows = pv && pv.items ? `<div class="tablewrap"><table><thead><tr><th>item</th><th>text</th><th>answer</th></tr></thead><tbody>${pv.items.map((it) => `<tr><td class="mono">${esc(it.item_id)}</td><td class="clip"><div>${esc(it.text || it.file || it.source_url || "")}</div></td><td class="clip"><div>${esc(it.answer ?? "—")}</div></td></tr>`).join("")}</tbody></table></div>` : "";
    const said = pv && pv.described ? pv.described : null;
    return `<div class="screen wide">${head}
      <section class="part"><div class="parthead"><h2>Use one you have</h2></div><div class="body">
        ${options ? `<div class="inline"><select id="ds-pick" aria-label="the project's datasets"><option value="">choose one of the project's datasets</option>${options}</select>
          <button class="btn" type="button" id="ds-use" disabled>Use it</button></div>` : '<p class="muted">The project has no other dataset.</p>'}
        <div class="field"><div class="name" id="ds-role-l">Its role for this goal</div><div class="choices row" role="radiogroup" aria-labelledby="ds-role-l">${roles}</div></div>
        <div id="ds-use-out"></div></div></section>
      <section class="part" data-form="dataset-new"><div class="parthead"><h2>Or make one from a source</h2></div><div class="body">
        <div class="field"><label class="name" for="ds-source">Where from</label><div><select id="ds-source"><option value="">choose a source</option>
          ${Object.entries(SOURCES).map(([k, [name]]) => `<option value="${k}" ${src === k ? "selected" : ""}>${esc(name)}</option>`).join("")}</select></div></div>
        ${fields.map(([k, hint, ex]) => `<div class="field"><label class="name" for="dsq-${k}">${esc(k)}</label><div><input type="text" id="dsq-${k}" data-q="${k}" value="${esc((d.q || {})[k] ?? "")}" placeholder="${esc(ex)}" autocapitalize="off" spellcheck="false"><div class="hint">${esc(hint)}</div></div></div>`).join("")}
        ${src ? `<div class="actions" style="margin-top:0"><button class="btn" type="button" id="ds-read">Read it</button><span class="muted">a job: the source's description and its first rows; nothing is saved</span></div>` : ""}
        <div id="ds-read-out">${said ? `<p class="note">${esc(JSON.stringify(said.source || {}))}${said.licence ? ` · licence ${esc(said.licence)}` : ""}</p>${rows}` : ""}</div>
        ${src && tabular(src) ? `<h3>Its fields</h3><p class="muted">Facts about each item to slice the results by, proposed from the source's columns; keep the ones you would compare on.</p>
          <div class="actions" style="margin-top:0"><button class="btn" type="button" id="ds-fields">Propose its fields</button></div>
          <div id="ds-fields-out">${fieldRows(d.fields)}</div>` : ""}
        ${src ? `<div class="field"><label class="name" for="ds-id">Its id</label><div><input type="text" id="ds-id" value="${esc(d.id || "")}" placeholder="cnn_dailymail_200" autocapitalize="off" spellcheck="false"><div class="hint">lowercase letters, digits and _</div></div></div>
        ${byField("ds-by")}
        <div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="ds-make" data-send>Make the dataset</button><span class="unsent" data-unsent-mark hidden>not saved yet · kept in this browser until it is made</span></div>` : ""}
        <div id="ds-make-out"></div></div></section>
      ${WB.cmd(`evh source-preview --source ${src || "<source>"} --query '${JSON.stringify(queryOf(d))}'\nevh dataset-create --dataset-id ${d.id || "<id>"} --source ${src || "<source>"} --query '${JSON.stringify(queryOf(d))}'`)}
      <div class="actions"><a class="btn" href="#goal/${enc(goal)}">Back to the goal</a></div></div>`;
  }
  function wireDatasetNew() {
    const goal = WB.param || "";
    if (!goal) return;
    const draft = () => readDraft(goal) || { source: "", q: {}, id: "", role: "validation" };
    const roleOf = () => document.querySelector("input[name=ds-role]:checked")?.value || "validation";
    const addToGoal = async (dataset, by) => {
      const n = ((LIVE.cache[`goalrec:${goal}`] || {}).record?.datasets || []).length;
      await send("PATCH", `/goals/${enc(goal)}`, { set: { [`datasets.${n}.dataset_id`]: dataset, [`datasets.${n}.role`]: roleOf() }, by });
      forget(`goalrec:${goal}`); forget(`status:${goal}`); forget("datasets"); forget("goals");
    };
    const pick = document.getElementById("ds-pick");
    pick?.addEventListener("change", () => { document.getElementById("ds-use").disabled = !pick.value; });
    document.getElementById("ds-use")?.addEventListener("click", async () => {
      const out = document.getElementById("ds-use-out"), by = byOf("ds-by") || (who() ? `person:${who()}` : null);
      if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are below: a change names who made it.</p>'; return; }
      try { await addToGoal(pick.value, by); location.hash = `#goal/${enc(goal)}`; } catch (e) { out.innerHTML = refusal(e); }
    });
    holds("dataset-new", () => `Make dataset ${(document.getElementById("ds-id")?.value || "").trim() || "…"}`);
    const save = () => {
      const d = draft();
      d.source = document.getElementById("ds-source").value;
      d.fields = d.fields || [];
      document.querySelectorAll("[data-q]").forEach((i) => { d.q[i.dataset.q] = i.value; });
      d.id = document.getElementById("ds-id")?.value || d.id;
      d.role = roleOf();
      document.querySelectorAll("[data-keep]").forEach((b) => { if (d.fields && d.fields[b.dataset.keep]) d.fields[b.dataset.keep].keep = b.checked; });
      keepDraft(goal, d);
      return d;
    };
    document.querySelector("[data-form=dataset-new]")?.addEventListener("input", save);
    document.getElementById("ds-source")?.addEventListener("change", () => {
      const d = save();
      d.q = {};
      keepDraft(goal, d);
      delete previews[goal];
      WB.render(true);
    });
    document.getElementById("ds-read")?.addEventListener("click", async (ev) => {
      const d = save(), out = document.getElementById("ds-read-out"), by = byOf("ds-by") || (who() ? `person:${who()}` : null);
      if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are below: a job names who asked.</p>'; return; }
      ev.target.disabled = true;
      try {
        const j = await send("POST", "/source-previews", { source: d.source, query: JSON.stringify(queryOf(d)), rows: 5, by });
        const done = await watchJob(j.id, out, "reading the source");
        if (done.state !== "succeeded") { out.innerHTML = await jobRefusal(done); ev.target.disabled = false; return; }
        previews[goal] = (done.result || {}).result?.values || {};
        const pv = previews[goal], said = pv.described || {};
        out.innerHTML = `<p class="note">${esc(JSON.stringify(said.source || {}))}${said.licence ? ` · licence ${esc(said.licence)}` : ""}</p>
          <div class="tablewrap"><table><thead><tr><th>item</th><th>text</th><th>answer</th></tr></thead><tbody>${(pv.items || []).map((it) => `<tr><td class="mono">${esc(it.item_id)}</td><td class="clip"><div>${esc(it.text || it.file || it.source_url || "")}</div></td><td class="clip"><div>${esc(it.answer ?? "—")}</div></td></tr>`).join("")}</tbody></table></div>`;
      } catch (e) { out.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    document.getElementById("ds-fields")?.addEventListener("click", async (ev) => {
      const d = save(), out = document.getElementById("ds-fields-out"), by = byOf("ds-by") || (who() ? `person:${who()}` : null);
      if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are below: a job names who asked.</p>'; return; }
      ev.target.disabled = true;
      try {
        const j = await send("POST", "/fieldset-proposals", { source: d.source, query: JSON.stringify(queryOf(d)), fieldset_id: (d.id || "proposed").trim() || "proposed", by });
        const done = await watchJob(j.id, out, "proposing fields");
        if (done.state !== "succeeded") { out.innerHTML = await jobRefusal(done); ev.target.disabled = false; return; }
        d.fields = ((done.result || {}).result?.values?.fieldset?.fields || []).map((f) => ({ ...f, keep: true }));
        keepDraft(goal, d);
        out.innerHTML = fieldRows(d.fields) || '<p class="muted">The source proposes no field.</p>';
      } catch (e) { out.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    document.getElementById("ds-make")?.addEventListener("click", async (ev) => {
      const d = save(), out = document.getElementById("ds-make-out"), by = byOf("ds-by");
      if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are: a change names who made it.</p>'; return; }
      ev.target.disabled = true;
      try {
        const kept = (d.fields || []).filter((f) => f.keep !== false).map(({ keep: _k, ...f }) => f);
        const query = queryOf(d), body = { source: d.source, by };
        if (kept.length) {
          await send("POST", `/fieldsets/${enc(d.id.trim())}`, { set: { description: `the fields of ${d.id.trim()}, from source ${d.source}`, fields: kept }, by });
          query.fields = kept.map((f) => f.name);
          body.fieldset = d.id.trim();
        }
        body.query = JSON.stringify(query);
        const j = await send("POST", `/datasets/${enc(d.id.trim())}`, body);
        const done = await watchJob(j.id, out, `dataset-create ${d.id}`);
        if (done.state !== "succeeded") { out.innerHTML = await jobRefusal(done); ev.target.disabled = false; return; }
        await addToGoal(d.id.trim(), by);
        sent("dataset-new"); dropDraft(goal); delete previews[goal];
        location.hash = `#goal/${enc(goal)}`;
      } catch (e) { out.innerHTML = refusal(e); ev.target.disabled = false; }
    });
  }

  // ── step 4: the systems a goal compares (UXS-005 step 4): made from a model where it runs, checked on three items ──
  const sysKey = (goal) => `evh.draft.system.${goal}`;
  const readSys = (goal) => { try { return JSON.parse(localStorage.getItem(sysKey(goal)) || "null"); } catch { return null; } };
  const keepSys = (goal, d) => { try { localStorage.setItem(sysKey(goal), JSON.stringify(d)); } catch { /* this visit only */ } };
  const dropSys = (goal) => { try { localStorage.removeItem(sysKey(goal)); } catch { /* nothing kept */ } };
  const smokes = {};
  const smokeView = (r) => {
    if (!r) return "";
    if (r.error) return r.error;
    const v = r.values || {}, pj = v.projection || {};
    return `<p><span class="status ${v.status === "pass" ? "ok" : "warn"}">${esc(v.status || "?")}</span> · ${v.calls ?? 0} call(s) · spent $${Number(v.spent_usd || 0).toFixed(5)}
      · all ${esc(pj.items ?? "?")} items ≈ $${esc(pj.usd ?? "?")}, about ${esc(pj.minutes ?? "?")} min</p>
      ${(v.flags || []).length ? `<ul>${v.flags.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : ""}
      ${(v.items || []).map((it) => `<details><summary class="mono">${esc(it.item)}</summary><pre class="reply">${esc(it.reply || "")}</pre></details>`).join("")}`;
  };
  function screenSystems(goal) {
    const head = `<div class="kicker">Step 4 · ${esc(goal)}</div><h1>Choose the systems</h1>
      <p class="lead">What is compared is a system: a model where it runs, with a prompt and settings. Each is checked on three items before it costs anything.</p>`;
    if (!goal) return `<div class="screen">${head}</div>`;
    const rec = load(`goalrec:${goal}`, `/goals/${enc(goal)}`), sys = load("systems", "/systems"), ms = load("models", "/models");
    if ([rec, sys, ms].includes(undefined)) return `<div class="screen wide">${head}${loading("the systems")}</div>`;
    const bad = [rec, sys, ms].find((x) => x.error);
    if (bad) return `<div class="screen wide">${head}${failed(bad)}</div>`;
    const datasets = (rec.record.datasets || []).map((x) => x.dataset_id);
    const d = readSys(goal) || { model: "", deployment: "", prompt: "", temperature: "0", max_tokens: "", id: "" };
    if (readSys(goal)) UNSENT.set("system-new", `a new system for ${goal}`);
    const mrec = d.model ? load(`model:${d.model}`, `/models/${enc(d.model)}`) : null;
    const deps = mrec && !mrec.error ? mrec.deployments.map((x) => x.deployment) : [];
    const runnable = ms.models.filter((m) => m.deployments > 0);
    return `<div class="screen wide">${head}
      <section class="part"><div class="parthead"><h2>Check each on three items</h2></div><div class="body">
        <div class="inline"><label class="name" for="sm-ds">on</label><select id="sm-ds">${datasets.map((x) => `<option>${esc(x)}</option>`).join("")}</select>
          <label class="name" for="sm-cap">spend at most (USD)</label><input type="number" id="sm-cap" min="0.01" step="0.01" value="0.05" inputmode="decimal" style="width:7rem"></div>
        <div class="tablewrap"><table><thead><tr><th>system</th><th>model</th><th>where it runs</th><th>its check</th></tr></thead><tbody>
        ${sys.systems.map((x) => `<tr><td class="mono">${esc(x.system)}</td><td>${esc(x.model || "")}</td><td>${esc(x.deployment || "")}</td>
          <td><button class="btn" type="button" data-smoke="${esc(x.system)}">Check it on three items</button> <button class="btn" type="button" data-clone="${esc(x.system)}">Clone it, change one thing</button>
            <div id="sm-${esc(x.system)}" aria-live="polite">${smokeView(smokes[`${goal}/${x.system}`])}</div><div id="cl-${esc(x.system)}"></div></td></tr>`).join("")}</tbody></table></div>
        ${byField("sm-by")}</div></section>
      <section class="part" data-form="system-new"><div class="parthead"><h2>Make a system from a model</h2></div><div class="body">
        <div class="field"><label class="name" for="sn-model">The model</label><div><select id="sn-model"><option value="">choose a model that has somewhere to run</option>
          ${runnable.map((m) => { const b = (m.best || []).find((x) => x.goal === goal);
            return `<option value="${esc(m.model)}" ${d.model === m.model ? "selected" : ""}>${esc(m.name || m.model)} · ${esc(m.state)}${b ? ` · #${b.rank} of ${b.of} on this goal` : ""}</option>`; }).join("")}</select>
          <div class="hint">a model not here is brought in first: <a href="#model-new">Bring in a model</a></div></div></div>
        ${d.model ? `<div class="field"><label class="name" for="sn-dep">Where it runs</label><div><select id="sn-dep">${deps.map((x) => `<option ${d.deployment === x ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></div></div>
        <div class="field"><label class="name" for="sn-prompt">The prompt</label><div><textarea id="sn-prompt" rows="2" placeholder="Summarise the following in one sentence:">${esc(d.prompt)}</textarea><div class="hint">the same for every system, so a difference in the scores is the model's</div></div></div>
        <div class="field"><label class="name" for="sn-temp">Temperature</label><div><input type="text" id="sn-temp" inputmode="decimal" value="${esc(d.temperature)}" style="width:6rem"></div></div>
        <div class="field"><label class="name" for="sn-max">At most this many tokens</label><div><input type="text" id="sn-max" inputmode="numeric" value="${esc(d.max_tokens)}" placeholder="the model's default" style="width:10rem"></div></div>
        <div class="field"><label class="name" for="sn-id">Its id</label><div><input type="text" id="sn-id" value="${esc(d.idTyped ? d.id : `${d.model}_${d.deployment || deps[0] || ""}`.replace(/[^A-Za-z0-9_.-]+/g, "_"))}" autocapitalize="off" spellcheck="false"></div></div>
        ${byField("sn-by")}
        <div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="sn-make" data-send>Make the system</button><span class="unsent" data-unsent-mark hidden>not saved yet · kept in this browser until it is made</span></div>` : ""}
        <div id="sn-out"></div></div></section>
      ${WB.cmd(`evh system-new <id> --set model_record=<model> --set deployment=<where> --set params.prompt=...\nevh arm-smoke --system <id> --dataset ${datasets[0] || "<dataset>"} --max-cost-usd 0.05`)}
      <div class="actions"><a class="btn" href="#goal/${enc(goal)}">Back to the goal</a></div></div>`;
  }
  function wireSystems() {
    const goal = WB.param || "";
    const v = (id) => (document.getElementById(id)?.value || "").trim();
    document.querySelectorAll("[data-smoke]").forEach((b) => b.addEventListener("click", async () => {
      const id = b.dataset.smoke, box = document.getElementById(`sm-${id}`), by = byOf("sm-by") || (who() ? `person:${who()}` : null);
      const cap = Number(v("sm-cap"));
      if (!by) { box.innerHTML = '<p class="note" role="alert">Say who you are below: a check names who asked.</p>'; return; }
      if (!(cap > 0)) { box.innerHTML = '<p class="note" role="alert">Say the most it may spend first.</p>'; return; }
      b.disabled = true;
      try {
        const j = await send("POST", `/systems/${enc(id)}/smoke`, { dataset: v("sm-ds"), by, max_cost_usd: cap });
        const done = await watchJob(j.id, box, "checking on three items");
        // arm-smoke ends 6 when it flags something: its answer, shown as one
        const res = (done.result || {}).result;
        smokes[`${goal}/${id}`] = res ? { values: res.values } : { error: await jobRefusal(done) };
        box.innerHTML = smokeView(smokes[`${goal}/${id}`]);
      } catch (e) { box.innerHTML = refusal(e); }
      b.disabled = false;
    }));
    // a clone changes one thing, so its difference in the scores is that change's (UXS-005 step 5)
    document.querySelectorAll("[data-clone]").forEach((b) => b.addEventListener("click", () => {
      const src = b.dataset.clone, box = document.getElementById(`cl-${src}`);
      box.innerHTML = `<div data-form="clone-${esc(src)}" class="inline" style="margin-top:8px">
        <label class="name" for="cl-id-${esc(src)}">new id</label><input type="text" id="cl-id-${esc(src)}" value="${esc(src)}_2" autocapitalize="off" spellcheck="false">
        <select id="cl-what-${esc(src)}" aria-label="what changes"><option value="prompt">the prompt</option><option value="temperature">the temperature</option><option value="max_tokens">the most tokens</option><option value="model">the model it sends</option></select>
        <input type="text" id="cl-val-${esc(src)}" placeholder="its new value" aria-label="the new value" style="min-width:14rem">
        <button class="btn primary" type="button" id="cl-go-${esc(src)}" data-send>Make the clone</button>${mark}</div><div id="cl-out-${esc(src)}"></div>`;
      holds(`clone-${src}`, () => `Make system ${v(`cl-id-${src}`) || "…"}`);
      document.getElementById(`cl-go-${src}`).addEventListener("click", async (ev) => {
        const out = document.getElementById(`cl-out-${src}`), by = byOf("sm-by") || (who() ? `person:${who()}` : null);
        if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are above: a change names who made it.</p>'; return; }
        const what = v(`cl-what-${src}`), raw = v(`cl-val-${src}`);
        ev.target.disabled = true;
        try {
          const r = await fetch(`/api/v1/systems/${enc(src)}`, { credentials: "same-origin" }).then((x) => x.json());
          const { system_id: _id, ...rest } = (r.result || {}).record || {};
          const params = { ...(rest.params || {}) };
          params[what] = ["temperature", "max_tokens"].includes(what) ? Number(raw) : raw;
          await send("POST", `/systems/${enc(v(`cl-id-${src}`))}`, { set: { ...rest, params }, by });
          sent(`clone-${src}`); forget("systems"); WB.render(true);
        } catch (e) { out.innerHTML = refusal(e); ev.target.disabled = false; }
      });
    }));
    const draft = () => readSys(goal) || { model: "", deployment: "", prompt: "", temperature: "0", max_tokens: "", id: "" };
    const save = () => {
      const d = draft();
      d.model = v("sn-model"); d.deployment = v("sn-dep") || d.deployment; d.prompt = document.getElementById("sn-prompt")?.value ?? d.prompt;
      d.temperature = v("sn-temp") || d.temperature; d.max_tokens = v("sn-max");
      // the id follows the model and where it runs until the person types one
      if (document.getElementById("sn-id")?.dataset.typed) { d.id = v("sn-id"); d.idTyped = true; }
      keepSys(goal, d);
      return d;
    };
    holds("system-new", () => `Make system ${v("sn-id") || "…"}`);
    document.querySelector("[data-form=system-new]")?.addEventListener("input", save);
    document.getElementById("sn-model")?.addEventListener("change", () => {
      const d = save(); d.deployment = ""; d.id = ""; d.idTyped = false; keepSys(goal, d); WB.render(true);
    });
    document.getElementById("sn-make")?.addEventListener("click", async (ev) => {
      const d = save(), out = document.getElementById("sn-out"), by = byOf("sn-by");
      if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are: a change names who made it.</p>'; return; }
      d.id = v("sn-id"); d.deployment = v("sn-dep") || d.deployment;
      const mrec = LIVE.cache[`model:${d.model}`] || {};
      const dep = (mrec.deployments || []).find((x) => x.deployment === d.deployment) || {};
      const ep = (dep.record || {}).endpoint || {};
      const set = { model_record: d.model, deployment: d.deployment };
      for (const k of ["provider", "model", "base_url", "api_key_env"]) if (ep[k]) set[`params.${k}`] = ep[k];
      if (d.prompt.trim()) set["params.prompt"] = d.prompt.trim();
      if (d.temperature !== "") set["params.temperature"] = Number(d.temperature);
      if (d.max_tokens !== "") set["params.max_tokens"] = Number(d.max_tokens);
      ev.target.disabled = true;
      try {
        await send("POST", `/systems/${enc(d.id)}`, { set, by });
        if (d.prompt.trim()) {
          // its history only: the bundled adapter reads params.prompt, not a version (owner, 2026-11-17)
          await runJob("/prompts/versions", { name: d.id, text: d.prompt.trim(), note: `the prompt of system ${d.id}, made in the Workbench`, by }, out, "recording the prompt");
        }
        sent("system-new"); dropSys(goal); forget("systems");
        WB.render(true);
      } catch (e) { out.innerHTML = refusal(e); ev.target.disabled = false; }
    });
  }

  // ── W1 the eval: a goal's rounds (UXS-005 step 5; RFC-032, D2, D3, D5) ───────────────────────────────────────
  // A round asks one question (stored as its hypothesis, D5), compares its arms by the evidence (each arm against the
  // leader, Holm: the raw p and its threshold), and ends in a decision kept with its reason. Its arms run as one sweep
  // (D2); a retire is final (D3).
  const short = (arm) => String(arm || "").split("/").pop();
  const pfmt = (p) => (p == null ? "—" : p < 0.0001 ? "<0.0001" : Number(p).toFixed(4));
  const num = (x, d = 4) => (x == null ? "—" : Number(x).toFixed(d));
  function evalChart(ev) {
    const rows = ev.rows || [];
    if (!rows.length) return "";
    const pts = [{ arm: ev.leader, mean: rows[0].baseline_mean }, ...rows.map((x) => ({ arm: x.arm, mean: x.mean }))]
      .filter((x) => x.mean != null).map((x) => ({ ...x, cost: Number((ev.cost_per_item || {})[x.arm] || 0) }));
    const W = 560, H = 220, L = 56, R = 16, T = 14, B = 40;
    const ys = pts.map((x) => x.mean), y0 = Math.min(...ys), y1 = Math.max(...ys), dy = y1 - y0 || Math.abs(y1) || 1;
    const cs = pts.map((x) => x.cost), c1 = Math.max(...cs);
    // cost runs from $0 (local) to the dearest: a log scale would put $0 nowhere, so it is linear, $ per 1M items
    const X = (c) => L + (c1 ? (c / c1) * (W - L - R) : (W - L - R) / 2), Y = (m) => T + (1 - (m - (y0 - dy * 0.1)) / (dy * 1.2)) * (H - T - B);
    const fmt = (c) => (c * 1e6 >= 1000 ? `$${Math.round(c * 1e6).toLocaleString("en")}` : `$${(c * 1e6).toFixed(c ? 2 : 0)}`);
    const dots = pts.map((x) => `<circle cx="${X(x.cost).toFixed(1)}" cy="${Y(x.mean).toFixed(1)}" r="5" fill="${x.arm === ev.leader ? "var(--ok)" : "var(--accent)"}"><title>${esc(short(x.arm))}: ${num(x.mean)} at ${fmt(x.cost)} per 1M items</title></circle>
      <text x="${(X(x.cost) + 8).toFixed(1)}" y="${(Y(x.mean) + 4).toFixed(1)}" font-size="11" fill="var(--ink-2)">${esc(short(x.arm))}</text>`).join("");
    return `<figure class="chart" aria-label="${esc(ev.metric)} against cost"><svg viewBox="0 0 ${W} ${H}" width="100%" role="img">
      <line x1="${L}" y1="${H - B}" x2="${W - R}" y2="${H - B}" stroke="var(--axis)"/><line x1="${L}" y1="${T}" x2="${L}" y2="${H - B}" stroke="var(--axis)"/>
      <text x="${L}" y="${H - B + 16}" font-size="11" fill="var(--muted)">$0</text><text x="${W - R}" y="${H - B + 16}" font-size="11" fill="var(--muted)" text-anchor="end">${fmt(c1)}</text>
      <text x="${(L + W - R) / 2}" y="${H - 6}" font-size="11" fill="var(--muted)" text-anchor="middle">cost per 1M items</text>
      <text x="${L - 6}" y="${Y(y1) + 4}" font-size="11" fill="var(--muted)" text-anchor="end">${num(y1, 3)}</text><text x="${L - 6}" y="${Y(y0) + 4}" font-size="11" fill="var(--muted)" text-anchor="end">${num(y0, 3)}</text>
      ${dots}</svg><figcaption class="muted">${esc(ev.metric)} (each arm's mean) against what it costs; the leader in green. The table below is the evidence.</figcaption></figure>`;
  }
  function screenEval(param) {
    const [goal, wanted] = String(param || "").split("/");
    const head = `<div class="kicker">The eval · ${esc(goal)}</div><h1>Its rounds</h1>
      <p class="lead">Each round asks one question, compares its arms on the goal's measure, and ends in a decision kept with its reason.</p>`;
    if (!goal) return `<div class="screen">${head}</div>`;
    const rl = load(`rounds:${goal}`, `/goals/${enc(goal)}/rounds`), rec = load(`goalrec:${goal}`, `/goals/${enc(goal)}`);
    if (rl === undefined || rec === undefined) return `<div class="screen wide">${head}${loading("the rounds")}</div>`;
    if (rl.error || rec.error) return `<div class="screen wide">${head}${failed(rl.error ? rl : rec)}</div>`;
    const rounds = rl.rounds, open = rounds.find((r) => r.status === "open");
    const cur = wanted || (open || rounds[rounds.length - 1] || {}).round_id;
    const tabs = rounds.length ? `<div class="tabs" role="tablist">${rounds.map((r) => `<a role="tab" class="tab" aria-selected="${r.round_id === cur}" href="#eval/${enc(goal)}/${enc(r.round_id)}">${esc(r.round_id)} · ${esc(r.status)}</a>`).join("")}</div>` : "";
    const datasets = (rec.record.datasets || []).map((x) => x.dataset_id);
    const last = rounds[rounds.length - 1];
    const openForm = open ? "" : `<section class="part" data-form="round-open"><div class="parthead"><h2>Open ${rounds.length ? "the next round" : "the first round"}</h2></div><div class="body">
        <div class="field"><label class="name" for="ro-q">The round's question</label><div><textarea id="ro-q" rows="2" placeholder="Does a cheaper hosted model match the baseline's coverage?"></textarea><div class="hint">what this round should find out, in one sentence</div></div></div>
        <div class="field"><label class="name" for="ro-ds">On</label><div><select id="ro-ds">${datasets.map((x) => `<option>${esc(x)}</option>`).join("")}</select></div></div>
        ${last ? `<div class="field"><label class="name" for="ro-keep">Carry in from ${esc(last.round_id)}</label><div><select id="ro-keep"><option value="all">every arm still in play</option><option value="">none</option></select><div class="hint">carried arms are not run again</div></div></div>` : ""}
        <div class="field"><label class="name" for="ro-budget">What it may spend (USD)</label><div><input type="text" id="ro-budget" inputmode="decimal" placeholder="no budget" style="width:8rem"></div></div>
        ${byField("ro-by")}
        <div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="ro-open" data-send>Open the round</button>${mark}</div><div id="ro-out"></div></div></section>`;
    if (!cur) return `<div class="screen wide">${head}<p class="muted">No round yet.</p>${openForm}<div class="actions"><a class="btn" href="#goal/${enc(goal)}">Back to the goal</a></div></div>`;
    const rs = load(`round:${goal}/${cur}`, `/goals/${enc(goal)}/rounds/${enc(cur)}`), ev = load(`evidence:${goal}/${cur}`, `/goals/${enc(goal)}/rounds/${enc(cur)}/evidence`);
    const sys = load("systems", "/systems"), bl = load(`baselines:${goal}`, `/baselines?goal=${enc(goal)}`);
    const prev = rs && !rs.error && rs.round.from ? load(`round:${goal}/${rs.round.from}`, `/goals/${enc(goal)}/rounds/${enc(rs.round.from)}`) : null;
    if ([rs, ev, sys, bl, prev].includes(undefined)) return `<div class="screen wide">${head}${tabs}${loading("the round")}</div>`;
    const bad = [rs, ev, sys, bl, prev].find((x) => x && x.error);
    if (bad) return `<div class="screen wide">${head}${tabs}${failed(bad)}</div>`;
    const r = rs.round, isOpen = r.status === "open";
    const rows = (ev.rows || []).map((x) => `<tr><td class="mono">${esc(short(x.arm))}</td><td class="num">${num(x.mean)}</td><td class="num">${num(x.delta)}</td>
      <td class="num">${pfmt(x.p)}</td><td class="num">${pfmt(x.threshold)}</td><td>${esc(x.verdict || "")}</td></tr>`).join("");
    const inPlay = r.arms.filter((a) => !a.retired);
    const arms = r.arms.map((a) => `<li><span class="mono">${esc(a.system)}</span>${a.label ? ` <small>(${esc(a.label)})</small>` : ""} · ${a.runs.length} run(s) · ${esc((a.entered || {}).how || "")}
      ${a.retired ? ` · <span class="status warn">retired</span> <small>${esc(a.retired.reason || "")}</small>` : isOpen ? ` <button class="btn" type="button" data-retire="${esc(a.system)}">Retire</button>` : ""}</li>`).join("");
    const have = new Set(r.arms.map((a) => a.system));
    const toRun = sys.systems.filter((x) => !have.has(x.system));
    const carryable = prev ? prev.round.arms.filter((a) => !a.retired && !have.has(a.system)).map((a) => a.system) : [];
    // a baseline line is its current version, its earlier ones in `history` (view_baselines.lines)
    const line = (bl.baselines || []).find((b) => b.dataset === r.dataset_id);
    const versions = line ? [line, ...(line.history || []).filter((h) => h.version !== line.current)]
      .map((v) => ({ ...v, current: line.current })).sort((a, b) => b.version - a.version) : [];
    const baseline = versions.length ? `<section class="part"><div class="parthead"><h2>The baseline on ${esc(r.dataset_id)}</h2></div><div class="body"><ul>
      ${versions.map((b) => `<li>v${b.version}${b.version === b.current ? ' <span class="status ok">current</span>' : ""} · <span class="mono">${esc(b.promoted_from)}</span> · ${esc((b.actor || {}).name || "")} · <small>${esc(b.reason || "")}</small>
        ${b.version !== b.current ? `<div class="inline" data-form="rollback-${b.version}"><input type="text" id="rb-why-${b.version}" placeholder="why go back to it, a sentence" aria-label="why roll back to v${b.version}" style="min-width:16rem">
          <button class="btn" type="button" data-rollback="${b.version}" data-send>Roll back to v${b.version}</button>${mark}</div>` : ""}</li>`).join("")}</ul><div id="rb-out"></div></div></section>` : "";
    const leaderRun = (() => { const a = r.arms.find((x) => x.arm === ev.leader); return a ? a.runs[a.runs.length - 1] : ""; })();
    return `<div class="screen wide">${head}${tabs}
      <h2>${esc(r.hypothesis || "(no question)")}</h2>
      ${byField("ev-by")}
      <p class="muted">${esc(r.round_id)} · ${esc(r.status)} · on ${esc(r.dataset_id)}${r.from ? ` · from ${esc(r.from)}` : ""}${r.budget_usd != null ? ` · budget $${esc(r.budget_usd)}` : ""} · spent $${num(ev.spent_usd, 4)}</p>
      ${r.conclusion ? `<div class="answer"><div class="kicker">its conclusion</div><p>${esc(typeof r.conclusion === "string" ? r.conclusion : r.conclusion.text || JSON.stringify(r.conclusion))}</p></div>` : ""}
      <section class="part"><div class="parthead"><h2>The evidence</h2><span class="grow"></span><span class="muted">${esc(ev.metric || "")} · each arm against the leader, Holm</span></div><div class="body">
        ${evalChart(ev)}
        ${rows ? `<p class="muted">The leader: <b class="mono">${esc(short(ev.leader))}</b>. A verdict holds when the raw p is under its threshold.</p>
          <div class="tablewrap"><table><thead><tr><th>arm</th><th class="num">mean</th><th class="num">Δ</th><th class="num">raw p</th><th class="num">threshold</th><th>verdict</th></tr></thead><tbody>${rows}</tbody></table></div>` : ""}
        ${(ev.notes || []).length ? `<ul>${ev.notes.map((n) => `<li class="muted">${esc(n)}</li>`).join("")}</ul>` : ""}</div></section>
      <section class="part"><div class="parthead"><h2>Its arms</h2></div><div class="body"><ul id="arms">${arms || '<li class="muted">none yet</li>'}</ul>
        ${isOpen ? `<div id="rt-box"></div>` : ""}
        ${isOpen && carryable.length ? `<div class="inline"><label class="name" for="cy-arm">Carry in from ${esc(r.from)}</label><select id="cy-arm">${carryable.map((x) => `<option>${esc(x)}</option>`).join("")}</select>
          <button class="btn" type="button" id="cy-go">Carry it in</button><span class="muted">unchanged, not run again</span></div><div id="cy-out"></div>` : ""}</div></section>
      ${baseline}
      ${isOpen ? `<section class="part"><div class="parthead"><h2>Run arms in it</h2></div><div class="body">
        ${toRun.length ? `<div class="choices">${toRun.map((x) => `<label class="choice"><input type="checkbox" data-run="${esc(x.system)}"> <span class="mono">${esc(x.system)}</span> <small>${esc(x.model || "")}</small></label>`).join("")}</div>
          <div class="inline"><label class="name" for="rn-cap">spend at most (USD)</label><input type="number" id="rn-cap" min="0.01" step="0.01" value="1" inputmode="decimal" style="width:7rem">
          <button class="btn" type="button" id="rn-est">See the cost first</button><button class="btn primary" type="button" id="rn-go">Run them</button></div>
          <div id="rn-out" aria-live="polite"></div>` : '<p class="muted">Every system of the project is in this round.</p>'}</div></section>
        <section class="part" data-form="round-close"><div class="parthead"><h2>Close the round</h2></div><div class="body">
          <div class="field"><label class="name" for="rc-text">Its conclusion</label><div><textarea id="rc-text" rows="3" placeholder="What the round showed, and what it decided, in a sentence or more."></textarea></div></div>
          ${leaderRun ? `<label class="choice"><input type="checkbox" id="rc-promote" value="${esc(leaderRun)}"> promote the leader's run (<span class="mono">${esc(leaderRun)}</span>) to the goal's baseline, the conclusion as its reason</label>` : ""}
          <div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="rc-close" data-send>Close the round</button>${mark}</div><div id="rc-out"></div></div></section>` : openForm}
      ${WB.cmd(`evh round-list ${goal}\nevh round-evidence ${goal} ${r.round_id}`)}
      <div class="actions"><a class="btn" href="#goal/${enc(goal)}">Back to the goal</a></div></div>`;
  }
  function wireEval() {
    const [goal, wanted] = String(WB.param || "").split("/");
    const rl = LIVE.cache[`rounds:${goal}`] || { rounds: [] };
    const cur = wanted || ((rl.rounds || []).find((r) => r.status === "open") || rl.rounds[rl.rounds.length - 1] || {}).round_id;
    const v = (id) => (document.getElementById(id)?.value || "").trim();
    const byOr = (id) => byOf(id) || (who() ? `person:${who()}` : null);
    const again = (round, box) => {
      forget(`rounds:${goal}`); forget(`round:${goal}/`); forget(`evidence:${goal}/`); forget(`status:${goal}`); forget("goals");
      if (round && round !== cur) { location.hash = `#eval/${enc(goal)}/${enc(round)}`; return; }
      // a redraw now would wipe what is still being written elsewhere on the screen (the unsent-changes rule)
      if (UNSENT.size && box) {
        box.innerHTML = '<p class="note">Done. The round has changed; <button class="btn" type="button" data-show>Show the round</button> when what you are writing is saved.</p>';
        box.querySelector("[data-show]").addEventListener("click", () => WB.render(true));
        return;
      }
      WB.render(true);
    };
    holds("round-open", () => `Open the round`);
    document.getElementById("ro-open")?.addEventListener("click", async (ev) => {
      const out = document.getElementById("ro-out"), by = byOf("ro-by");
      if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are: a decision names who made it.</p>'; return; }
      const inputs = { dataset: v("ro-ds"), hypothesis: v("ro-q"), by };
      const last = rl.rounds[rl.rounds.length - 1];
      if (last) { inputs.from = last.round_id; if (v("ro-keep")) inputs.keep = v("ro-keep"); }
      if (v("ro-budget")) inputs.budget_usd = Number(v("ro-budget"));
      ev.target.disabled = true;
      try {
        if (await runJob(`/goals/${enc(goal)}/rounds`, inputs, out, "opening the round")) {
          sent("round-open"); forget(`rounds:${goal}`);
          const fresh = await fetch(`/api/v1/goals/${enc(goal)}/rounds`, { credentials: "same-origin" }).then((x) => x.json());
          const opened = ((fresh.result || {}).rounds || []).find((x) => x.status === "open");
          again(opened ? opened.round_id : null);
        }
      } catch (e) { out.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    const picked = () => [...document.querySelectorAll("[data-run]:checked")].map((b) => b.dataset.run);
    const sweepInputs = () => ({ systems: picked(), dataset: (LIVE.cache[`round:${goal}/${cur}`] || {}).round?.dataset_id, goal, round: cur });
    document.getElementById("rn-est")?.addEventListener("click", async () => {
      const out = document.getElementById("rn-out");
      if (!picked().length) { out.innerHTML = '<p class="note" role="alert">Pick the systems to run first.</p>'; return; }
      out.innerHTML = '<p class="muted">estimating…</p>';
      const r = await fetch("/api/v1/estimate", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-EVH-Data": "1" }, body: JSON.stringify({ operation: "sweep", inputs: sweepInputs() }) });
      const b = await r.json().catch(() => ({}));
      const lines = ((b.result || {}).blocks || []).flatMap((x) => x.lines || []).filter((l) => /\$|estimat|items|calls|cost/i.test(l));
      out.innerHTML = r.ok ? `<pre class="reply">${esc(lines.join("\n") || b.text || "no cost to estimate")}</pre>` : `<p class="note" role="alert">${esc(b.error || b.text || r.status)}</p>`;
    });
    document.getElementById("rn-go")?.addEventListener("click", async (ev) => {
      const out = document.getElementById("rn-out"), by = byOr("ev-by"), cap = Number(v("rn-cap"));
      if (!picked().length) { out.innerHTML = '<p class="note" role="alert">Pick the systems to run first.</p>'; return; }
      if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are below: a run names who asked.</p>'; return; }
      if (!(cap > 0)) { out.innerHTML = '<p class="note" role="alert">Say the most it may spend first.</p>'; return; }
      ev.target.disabled = true;
      try {
        const { dataset, ...rest } = sweepInputs();  // the dataset is the route's part, not the body's
        const j = await send("POST", `/datasets/${enc(dataset)}/sweeps`, { ...rest, by, max_cost_usd: cap });
        for (;;) {
          const jr = await fetch(`/api/v1/jobs/${enc(j.id)}`, { credentials: "same-origin" }).then((x) => x.json()).catch(() => ({}));
          const pg = jr.progress ? ` · ${jr.progress.done} of ${jr.progress.total}` : "";
          out.innerHTML = `<p class="muted">sweep ${esc(jr.state || "…")}${pg}${jr.spent_usd ? ` · spent $${Number(jr.spent_usd).toFixed(4)}` : ""}</p>`;
          if (!["queued", "running", "running (unsupervised)"].includes(jr.state)) {
            if (jr.state !== "succeeded") out.innerHTML = await jobRefusal(jr);
            else again(null, out);
            break;
          }
          await new Promise((ok) => setTimeout(ok, 1000));
        }
      } catch (e) { out.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    document.querySelectorAll("[data-retire]").forEach((b) => b.addEventListener("click", () => {
      const sysId = b.dataset.retire, box = document.getElementById("rt-box");
      box.innerHTML = `<div data-form="retire"><p>Retire <b class="mono">${esc(sysId)}</b> from ${esc(cur)}: final, kept with its reason; no operation undoes it.</p>
        <div class="inline"><input type="text" id="rt-why" placeholder="why, in a sentence" style="min-width:20rem" aria-label="why it is retired">
        <button class="btn" type="button" id="rt-go" data-send>Retire it</button>${mark}<button class="btn" type="button" id="rt-no">Keep it</button></div><div id="rt-out"></div></div>`;
      holds("retire", () => `Retire ${sysId}`);
      document.getElementById("rt-why").focus();
      document.getElementById("rt-no").addEventListener("click", () => { sent("retire"); box.innerHTML = ""; });
      document.getElementById("rt-go").addEventListener("click", async (ev) => {
        const out = document.getElementById("rt-out"), by = byOr("ev-by");
        if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are below: a decision names who made it.</p>'; return; }
        ev.target.disabled = true;
        try { if (await runJob(`/goals/${enc(goal)}/rounds/${enc(cur)}/retire`, { arm: sysId, reason: v("rt-why"), by }, out, "retiring")) { sent("retire"); again(null, out); } }
        catch (e) { out.innerHTML = refusal(e); }
        ev.target.disabled = false;
      });
    }));
    document.getElementById("cy-go")?.addEventListener("click", async (ev) => {
      const out = document.getElementById("cy-out"), by = byOr("ev-by");
      if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are above: a decision names who made it.</p>'; return; }
      ev.target.disabled = true;
      try { if (await runJob(`/goals/${enc(goal)}/rounds/${enc(cur)}/carry`, { arm: v("cy-arm"), by }, out, "carrying it in")) again(null, out); }
      catch (e) { out.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    document.querySelectorAll("[data-rollback]").forEach((b) => {
      const to = Number(b.dataset.rollback);
      holds(`rollback-${to}`, () => `Roll back to v${to}`);
      b.addEventListener("click", async () => {
        const out = document.getElementById("rb-out"), by = byOr("ev-by");
        if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are above: a decision names who made it.</p>'; return; }
        b.disabled = true;
        const dataset = (LIVE.cache[`round:${goal}/${cur}`] || {}).round?.dataset_id;
        try {
          if (await runJob("/baselines/rollback", { goal, dataset, to, reason: v(`rb-why-${to}`), by }, out, "rolling back")) {
            sent(`rollback-${to}`); forget(`baselines:${goal}`); again(null, out);
          }
        } catch (e) { out.innerHTML = refusal(e); }
        b.disabled = false;
      });
    });
    holds("round-close", () => `Close ${cur}`);
    document.getElementById("rc-close")?.addEventListener("click", async (ev) => {
      const out = document.getElementById("rc-out"), by = byOr("ev-by");
      if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are: a decision names who made it.</p>'; return; }
      if (!window.confirm(`Close ${cur} with this conclusion?${document.getElementById("rc-promote")?.checked ? " Its leader's run becomes the goal's baseline." : ""}`)) return;
      const inputs = { conclusion: v("rc-text"), by };
      if (document.getElementById("rc-promote")?.checked) inputs.promote = document.getElementById("rc-promote").value;
      ev.target.disabled = true;
      try { if (await runJob(`/goals/${enc(goal)}/rounds/${enc(cur)}/close`, inputs, out, "closing the round")) { sent("round-close"); again(); } }
      catch (e) { out.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
  }

  // ── step 3: prepare a dataset (UXS-005 step 3): fetch it, look inside, its reference set ────────────────────────
  const catalogPage = (ds) => `${location.origin}/d/${String(ds || "none").replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "x"}.html`;
  async function runJob(path, body, box, what) {
    const j = await send("POST", path, body);
    const done = await watchJob(j.id, box, what);
    if (done.state !== "succeeded") { box.innerHTML = await jobRefusal(done); return null; }
    return done;
  }
  function screenPrepare(ds) {
    const head = `<div class="kicker">Step 3 · ${esc(ds)}</div><h1>Prepare the dataset</h1>
      <p class="lead">Three things a dataset needs before anything runs: its items fetched, a look inside, and the reference set outputs are scored against.</p>`;
    if (!ds) return `<div class="screen">${head}<p class="note">Open it from a goal's dataset.</p><div class="actions"><a class="btn" href="#home">Your goals</a></div></div>`;
    const d = load(`dataset:${ds}`, `/datasets/${enc(ds)}`);
    if (d === undefined) return `<div class="screen wide">${head}${loading("the dataset")}</div>`;
    if (d.error) return `<div class="screen wide">${head}${failed(d)}</div>`;
    const fetched = d.parts.materialized.present, looked = d.parts.profile.present, refs = d.references || [];
    const sets = (d.label_sets || []).map((x) => ({ ...x, name: String(x.set).split("/").pop() }));
    const done = (on) => (on ? '<span class="status ok">✓</span>' : '<span class="status">to do</span>');
    const promote = sets.map((x) => `<div class="row-form" data-form="promote-${esc(x.name)}"><p><b class="mono">${esc(x.name)}</b> <span class="muted">${esc(x.kind)}${x.kind === "dataset" ? ": the answers the data came with" : ""}</span></p>
        <div class="inline"><select id="pt-${esc(x.name)}" aria-label="tier"><option value="gold">gold</option><option value="silver">silver</option></select>
        <input type="text" id="pr-${esc(x.name)}" placeholder="why: a sentence" aria-label="why it is promoted" style="min-width:18rem">
        <button class="btn" type="button" data-promote="${esc(x.name)}" data-send>Promote</button>${mark}</div><div id="po-${esc(x.name)}"></div></div>`).join("");
    return `<div class="screen wide">${head}
      <section class="part"><div class="parthead"><span class="letter">a</span><h2>Fetch its items</h2><span class="grow"></span>${done(fetched)}</div><div class="body">
        <p class="muted">Downloads every item and checks it against its hash, so a run reads exactly the frozen items.</p>
        ${fetched ? "" : `<div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="pp-fetch">Fetch them</button></div>`}<div id="pp-fetch-out"></div></div></section>
      <section class="part"><div class="parthead"><span class="letter">b</span><h2>Look inside</h2><span class="grow"></span>${done(looked)}</div><div class="body">
        <p class="muted">How many items, how long, each field's values: most surprises show here, before anything runs.</p>
        ${looked ? `<p><a href="${catalogPage(ds)}">Open its page in the catalog ↗</a></p>` : `<div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="pp-look" ${fetched ? "" : "disabled"}>Profile it</button>${fetched ? "" : '<span class="muted">after it is fetched</span>'}</div>`}
        <div id="pp-look-out"></div></div></section>
      <section class="part"><div class="parthead"><span class="letter">c</span><h2>Its reference set</h2><span class="grow"></span>${done(refs.length)}</div><div class="body">
        <p class="muted">The expected answer for each item, that outputs are scored against. Gold is checked by people; silver is a model's answers, enough to rank systems. Who and why are recorded.</p>
        ${refs.length ? `<ul>${refs.map((r) => `<li><b>${esc(r.reference)}</b> · ${r.items} item(s) · ${esc(r.kind || "")}</li>`).join("")}</ul>` : ""}
        ${sets.length ? `<h3>Promote a label set</h3>${promote}` : '<p class="muted">No label set yet.</p>'}
        <h3>Or label it</h3><div class="actions" style="margin-top:0"><a class="btn" href="#label/${enc(ds)}">Label it here</a></div>
        ${byField("pp-by")}</div></section>
      ${WB.cmd(`evh dataset-materialize --dataset-id ${ds}\nevh dataset-profile --dataset-id ${ds}\nevh reference-promote --dataset-id ${ds} --labels <set> --tier gold --reason "..."`)}
      <div class="actions"><a class="btn" href="#home">Your goals</a></div></div>`;
  }
  function wirePrepare() {
    const ds = WB.param || "";
    const by = () => byOf("pp-by") || (who() ? `person:${who()}` : null);
    const again = () => { forget(`dataset:${ds}`); forget("datasets"); WB.render(true); };
    for (const [btn, out, path, what] of [["pp-fetch", "pp-fetch-out", "materialize", "fetching"], ["pp-look", "pp-look-out", "profile", "profiling"]]) {
      document.getElementById(btn)?.addEventListener("click", async (ev) => {
        const box = document.getElementById(out), who_ = by();
        if (!who_) { box.innerHTML = '<p class="note" role="alert">Say who you are below: a job names who asked.</p>'; return; }
        ev.target.disabled = true;
        try { if (await runJob(`/datasets/${enc(ds)}/${path}`, { by: who_ }, box, what)) again(); } catch (e) { box.innerHTML = refusal(e); }
        ev.target.disabled = false;
      });
    }
    document.querySelectorAll("[data-promote]").forEach((b) => {
      const name = b.dataset.promote;
      holds(`promote-${name}`, () => `Promote ${name} as ${document.getElementById(`pt-${name}`).value}`);
      b.addEventListener("click", async () => {
        const box = document.getElementById(`po-${name}`), who_ = by();
        if (!who_) { box.innerHTML = '<p class="note" role="alert">Say who you are below: a promotion names who made it.</p>'; return; }
        b.disabled = true;
        try {
          const ok = await runJob(`/datasets/${enc(ds)}/references`, { labels: name, tier: document.getElementById(`pt-${name}`).value, reason: document.getElementById(`pr-${name}`).value, by: who_ }, box, "promoting");
          if (ok) { sent(`promote-${name}`); again(); }
        } catch (e) { box.innerHTML = refusal(e); }
        b.disabled = false;
      });
    });
  }

  // ── labelling: a sheet filled here and submitted when done (owner, 2026-11-17: never item by item) ─────────────
  // The sheet is label-sheet's (a job's file); the answers stay in this browser until Submit sends the filled sheet to
  // label-import, which writes a frozen label set as a CSV upload would.
  function parseCsv(text) {
    const rows = [];
    let row = [], cell = "", q = false;
    const t = text.replace(/^﻿/, "");
    for (let i = 0; i < t.length; i++) {
      const c = t[i];
      if (q) {
        if (c === '"' && t[i + 1] === '"') { cell += '"'; i++; } else if (c === '"') q = false; else cell += c;
      } else if (c === '"') q = true;
      else if (c === ",") { row.push(cell); cell = ""; }
      else if (c === "\n" || c === "\r") { if (c === "\r" && t[i + 1] === "\n") i++; row.push(cell); rows.push(row); row = []; cell = ""; }
      else cell += c;
    }
    if (cell || row.length) { row.push(cell); rows.push(row); }
    return rows;
  }
  const csvOf = (rows) => rows.map((r) => r.map((c) => (/[",\n\r]/.test(c) ? `"${String(c).replace(/"/g, '""')}"` : c)).join(",")).join("\r\n") + "\r\n";
  const labelKey = (ds) => `evh.draft.label.${ds}`;
  const readSheet = (ds) => { try { return JSON.parse(localStorage.getItem(labelKey(ds)) || "null"); } catch { return null; } };
  const keepSheet = (ds, d) => { try { localStorage.setItem(labelKey(ds), JSON.stringify(d)); } catch { /* this visit only */ } };
  const dropSheet = (ds) => { try { localStorage.removeItem(labelKey(ds)); } catch { /* nothing kept */ } };
  const answered = (d) => Object.values(d.answers || {}).filter((a) => String(a.label || "").trim()).length;
  function screenLabel(ds) {
    const head = `<div class="kicker">Label · ${esc(ds)}</div><h1>Label the items</h1>
      <p class="lead">Give each item its expected answer. Nothing is written until you submit the sheet; then it becomes a label set, which you can promote to the reference set.</p>`;
    if (!ds) return `<div class="screen">${head}</div>`;
    const d = readSheet(ds);
    if (!d) {
      return `<div class="screen wide">${head}
        <div class="field"><div class="name" id="lb-items-l">Which items</div><div class="choices row" role="radiogroup" aria-labelledby="lb-items-l">
          <label class="choice"><input type="radio" name="lb-items" value="unlabelled" checked> not labelled yet</label><label class="choice"><input type="radio" name="lb-items" value="all"> all</label></div></div>
        ${byField("lb-by")}
        <div class="actions"><button class="btn primary" type="button" id="lb-make">Make the sheet</button><a class="btn" href="#prepare/${enc(ds)}">Back</a></div><div id="lb-make-out"></div>
        ${WB.cmd(`evh label-sheet --dataset-id ${ds} --out sheet.csv`)}</div>`;
    }
    if (answered(d)) UNSENT.set("label-sheet", `${answered(d)} answer(s) for ${ds}`);
    const [header, ...rows] = d.sheet, at = (n) => header.findIndex((h) => h === n || h.startsWith(`${n} [`));
    const iItem = at("item"), iProp = at("proposal"), iId = at("item_id");
    const choices = (header[at("label")].match(/\[(.*)\]/) || [, ""])[1].split("|").filter(Boolean);
    const list = choices.length ? `<datalist id="lb-choices">${choices.map((c) => `<option value="${esc(c)}">`).join("")}</datalist>` : "";
    const n = answered(d);
    return `<div class="screen wide" data-form="label-sheet">${head}${list}
      <div class="tablewrap"><table><thead><tr><th>item</th><th>the item</th><th>proposal</th><th>its answer</th><th>a note</th></tr></thead><tbody>
      ${rows.map((r) => { const id = r[iId], a = d.answers[id] || {}; return `<tr><td class="mono">${esc(id)}</td><td class="clip"><div>${esc(r[iItem] || "")}</div></td>
        <td>${esc(r[iProp] || "")}</td><td><input type="text" data-answer="${esc(id)}" value="${esc(a.label || "")}" ${choices.length ? 'list="lb-choices"' : ""} aria-label="the answer for ${esc(id)}"></td>
        <td><input type="text" data-note="${esc(id)}" value="${esc(a.note || "")}" aria-label="a note on ${esc(id)}"></td></tr>`; }).join("")}</tbody></table></div>
      <div class="field"><label class="name" for="lb-set">The label set's name</label><div><input type="text" id="lb-set" value="${esc(d.set || "")}" placeholder="owner_2026_11" autocapitalize="off" spellcheck="false"><div class="hint">lowercase letters, digits, _ . -; a set is never edited, a second pass is a new set</div></div></div>
      ${byField("lb-by")}
      <div class="actions"><button class="btn primary" type="button" id="lb-submit" data-send>Submit</button><span class="unsent" data-unsent-mark hidden><span id="lb-count">${n}</span> answer(s) not submitted · kept in this browser</span>
        <button class="btn" type="button" id="lb-drop">Throw the sheet away</button></div><div id="lb-out"></div>
      ${WB.cmd(`evh label-import --sheet sheet.csv --dataset-id ${ds} --set <name> --by <you>`)}</div>`;
  }
  function wireLabel() {
    const ds = WB.param || "";
    document.getElementById("lb-make")?.addEventListener("click", async (ev) => {
      const box = document.getElementById("lb-make-out"), by = byOf("lb-by") || (who() ? `person:${who()}` : null);
      if (!by) { box.innerHTML = '<p class="note" role="alert">Say who you are: a job names who asked.</p>'; return; }
      ev.target.disabled = true;
      try {
        const done = await runJob(`/datasets/${enc(ds)}/label-sheets`, { out: "sheet.csv", items: document.querySelector("input[name=lb-items]:checked").value, by }, box, "making the sheet");
        if (done) {
          const r = await fetch(`/api/v1/jobs/${enc(done.id)}/files/sheet.csv`, { credentials: "same-origin" });
          const sheet = parseCsv(await r.text()).filter((row) => row.length > 1);
          keepSheet(ds, { sheet, answers: {}, set: "" });
          WB.render(true);
        }
      } catch (e) { box.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    const d = readSheet(ds);
    if (!d) return;
    const name = () => (document.getElementById("lb-set").value || "").trim();
    // dirty once an answer is given, not when the sheet is only made (a sheet with no answer loses nothing)
    const show = (cur) => {
      const n = answered(cur), btn = document.getElementById("lb-submit");
      if (n) UNSENT.set("label-sheet", `${n} answer(s) for ${ds}`); else UNSENT.delete("label-sheet");
      document.getElementById("lb-count").textContent = n;
      document.querySelector("[data-form=label-sheet] [data-unsent-mark]").hidden = !n;
      btn.disabled = !n;
      btn.textContent = `Submit ${n} answer(s) as label set ${name() || "…"}`;
    };
    show(d);
    document.querySelector("[data-form=label-sheet]").addEventListener("input", (e) => {
      const cur = readSheet(ds) || d, id = e.target.dataset.answer || e.target.dataset.note;
      if (id) { cur.answers[id] = cur.answers[id] || {}; cur.answers[id][e.target.dataset.answer ? "label" : "note"] = e.target.value; }
      cur.set = name();
      keepSheet(ds, cur);
      show(cur);
    }, true);
    document.getElementById("lb-drop").addEventListener("click", () => {
      if (!window.confirm(`Throw away ${answered(readSheet(ds) || d)} answer(s) not submitted?`)) return;
      dropSheet(ds); sent("label-sheet"); WB.render(true);
    });
    document.getElementById("lb-submit").addEventListener("click", async (ev) => {
      const cur = readSheet(ds) || d, out = document.getElementById("lb-out"), by = byOf("lb-by");
      if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are: a label set names who labelled it.</p>'; return; }
      if (!name()) { out.innerHTML = '<p class="note" role="alert">Name the label set.</p>'; return; }
      const [header, ...rows] = cur.sheet, at = (n) => header.findIndex((h) => h === n || h.startsWith(`${n} [`));
      const iId = at("item_id"), iLabel = at("label"), iNote = at("note");
      const filled = [header, ...rows.map((r) => { const a = cur.answers[r[iId]] || {}, x = [...r]; x[iLabel] = a.label || ""; if (iNote >= 0) x[iNote] = a.note || ""; return x; })];
      const content = btoa(unescape(encodeURIComponent(csvOf(filled))));
      ev.target.disabled = true;
      try {
        const done = await runJob(`/datasets/${enc(ds)}/label-sets/${enc(name())}`, { sheet: { name: "sheet.csv", content_base64: content }, by }, out, "submitting the sheet");
        if (done) {
          dropSheet(ds); sent("label-sheet"); forget(`dataset:${ds}`);
          out.innerHTML = `<p class="note">Written: label set <b>${esc(name())}</b>. <a href="#prepare/${enc(ds)}">Promote it to the reference set</a>.</p>`;
          document.querySelector("[data-form=label-sheet] [data-unsent-mark]").hidden = true;
        }
      } catch (e) { out.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
  }

  // ── a screen not wired yet: says which step wires it ───────────────────────
  function screenLater() {
    return `<div class="screen"><div class="kicker">Not wired yet</div><h1>This screen comes later</h1>
      <p class="lead">The Workbench is wired to your project a workflow at a time (RFC-032's build order). This screen still
      shows the mockup's walk-through, read from the harness's own repository, so it is not shown here.</p>
      <div class="actions"><a class="btn primary" href="#home">Your goals</a></div></div>`;
  }

  const WIRED = {
    home: [screenHome], goal: [() => screenGoal(WB.param || "")], glossary: null,
    models: [screenModels], model: [() => screenModel(WB.param || ""), wireModel], "model-new": [screenModelNew, wireModelNew],
    dataset: [() => screenDatasetNew(WB.param || ""), wireDatasetNew],
    "goal-new": [() => screenGoalForm(""), wireGoalForm], "goal-edit": [() => screenGoalForm(WB.param || ""), wireGoalForm],
    prepare: [() => screenPrepare(WB.param || ""), wirePrepare], label: [() => screenLabel(WB.param || ""), wireLabel],
    systems: [() => screenSystems(WB.param || ""), wireSystems], eval: [() => screenEval(WB.param || ""), wireEval],
  };

  function goLive() {
    LIVE.on = true;
    document.body.classList.add("live");
    const bar = document.querySelector(".mockbar span");
    if (bar) bar.innerHTML = "<b>Workbench</b> · this project, through its API";
    for (const k of Object.keys(WB.routes)) if (!(k in WIRED)) WB.routes[k] = [screenLater];
    for (const [k, v] of Object.entries(WIRED)) if (v) WB.routes[k] = v;
    WB.routes.start = [screenHome];
    if (!location.hash || location.hash === "#start") location.hash = "#home";
    WB.render();
  }

  if (location.pathname.startsWith("/workbench")) {
    // Until the project answers, no mockup screen is drawn: one of them sends a browser without the mockup's own state
    // to #start, and a reload of a live screen (#dataset/<goal>) ended on the home. The mockup comes back only when
    // there is no project's API to answer.
    const mockRoutes = { ...WB.routes };
    for (const k of Object.keys(WB.routes)) WB.routes[k] = [() => '<div class="screen"><p class="muted">Opening this project…</p></div>'];
    const asMockup = () => { Object.assign(WB.routes, mockRoutes); WB.render(true); };
    fetch("/api/v1/goals", { credentials: "same-origin" }).then((r) => {
      if (r.ok) goLive();
      else if (r.status !== 401) asMockup();
      else {
        document.querySelector("#main").innerHTML = `<div class="screen"><h1>Sign in</h1><p class="lead">Open the Workbench through the link
          <code>evh catalog-serve</code> printed: it carries this server's token once and leaves a cookie.</p></div>`;
      }
    }).catch(asMockup);
  }
})();
