// The Workbench on its server (RFC-032): served by `catalog-serve` under /workbench/, it reads the project through the
// model's API. The mockup (mockup.html, its data in mock.js) is a frozen design reference in the repository (D7): it does
// not load this file and does not ship in the package.
// Screens are wired workflow by workflow as their entities land on the model; until then a screen says which step
// wires it, never this repository's data as if it were the project's.
(() => {
  const WB = window.WB;
  const LIVE = { on: false, cache: {}, pending: {}, wanted: {}, failed: null };
  window.LIVE = LIVE;
  const esc = WB.esc;

  // One API read, kept until the page reloads; a screen asks again by key and is drawn again when it lands.
  function load(key, path, raw = false) {
    if (key in LIVE.cache) return LIVE.cache[key];
    // An answer redraws the screen that asked for it last, never one that did not ask: a slow read (a chart) landing on
    // another screen redrew it under the person's typing, and the text box it replaced took the rest of their
    // keystrokes. A screen asking for a read already on its way (the screen before asked first) is recorded too, or
    // the read lands, redraws nothing, and the screen stays on "Reading…".
    LIVE.wanted[key] = location.hash;
    if (!LIVE.pending[key]) {
      LIVE.pending[key] = fetch(`/api/v1${path}`, { credentials: "same-origin" })
        .then(async (r) => {
          const body = await r.json().catch(() => ({}));
          LIVE.cache[key] = r.ok ? (raw ? body : body.result) : { error: body.error || `${r.status}` };
        })
        .catch((e) => { LIVE.cache[key] = { error: String(e) }; })
        .finally(() => {
          const asked = LIVE.wanted[key];
          delete LIVE.pending[key];
          delete LIVE.wanted[key];
          if (location.hash === asked) WB.render();
        });
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
    if (goals.error) return `<div class="screen wide">${head}${failed(goals)}<div class="actions"><a class="btn primary" href="#settings">Settings</a></div></div>`;
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
      : jobs.jobs.length ? jobs.jobs.map((j) => `<div class="job"><a href="#jobs/${enc(j.id)}">${esc(j.operation)}</a><span class="status">${esc(j.state)}</span></div>`).join("")
      : '<p class="muted" style="margin:0">Nothing is running.</p>';
    return `<div class="screen wide">${head}
      <div class="part"><div class="parthead"><h2>Running now</h2><span class="grow"></span><a href="#jobs">Every job</a></div><div class="body">${running}</div></div>
      ${goals.goals.length ? `<div class="tablewrap" style="margin-top:18px"><table><thead><tr><th>goal</th><th>decides</th><th>datasets</th><th class="num">rounds</th><th>next</th></tr></thead><tbody>${rows.join("")}</tbody></table></div>`
        : `<div class="answer" style="margin-top:18px"><p><b>What should this project help you decide?</b></p><p>An evaluation starts with a goal: the decision you need to make, and how you will know which system is better for it.</p></div>`}
      <div class="actions"><a class="btn primary" href="#goal-new">${goals.goals.length ? "New goal" : "Start with a goal"}</a><a class="btn" href="#models">Models</a><a class="btn" href="#prompts">Prompts</a><a class="btn" href="#settings">Settings</a><a class="btn" href="${location.origin}/">The catalog ↗</a></div></div>`;
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
      ${chartBox("trend", { goal: id }, true)}
      ${WB.cmd(`evh goal-status ${id}`)}
      <div class="actions"><a class="btn primary" href="#dataset/${encodeURIComponent(id)}">Add a dataset</a><a class="btn" href="#systems/${encodeURIComponent(id)}">Choose the systems</a><a class="btn" href="#eval/${encodeURIComponent(id)}">The eval</a><a class="btn" href="#review/${encodeURIComponent(id)}">Review the outputs</a><a class="btn" href="#production/${encodeURIComponent(id)}">Production</a><a class="btn" href="#heldout/${encodeURIComponent(id)}">The held-out test</a><a class="btn" href="#study/${encodeURIComponent(id)}">Studies</a><a class="btn" href="#goal-edit/${encodeURIComponent(id)}">Edit the goal</a><a class="btn" href="#home">Back to your goals</a></div></div>`;
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
  // A recorded actor in words, as the CLI's `_actor.said`: a record `evh migrate` filled in names nobody.
  const actorSaid = (a) => !a || !a.name ? "?" : a.from === "migration" ? `nobody recorded (${a.name})` : a.name + (a.for ? ` for ${a.for}` : "");
  const STATE_TAG ={ vetted: "pass", onboarded: "pass", check: "check", none: "none" };
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
        <div id="job-${esc(k)}" data-out aria-live="polite">${job ? `<p class="muted">${jobLine(job)}</p>` : ""}</div>
        ${on && on.status === "check" ? `<div data-form="accept-${esc(k)}"><h3>Accept what it raises</h3>
          <p class="muted">When a flag is the deployment's own nature (a hosted gateway has no build to pin), accept it with why: it is kept in its checks and no longer counts against it.</p>
          <div class="field"><label class="name" for="flag-${esc(k)}">The flag's kind</label><div><input type="text" id="flag-${esc(k)}" placeholder="the words before its colon: reasoning, where it ran"></div></div>
          <div class="field"><label class="name" for="why-${esc(k)}">Why</label><div><input type="text" id="why-${esc(k)}" placeholder="a sentence"></div></div>
          ${byField(`by-${k}`)}
          <div class="actions" style="margin-top:0"><button class="btn" type="button" data-send data-accept="${esc(k)}">Accept it</button>${mark}</div>
          <div id="acc-${esc(k)}" data-out></div></div>` : ""}
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
        <div class="actions" style="margin-top:0"><button class="btn" type="button" id="dep-add" data-send>Add it</button>${mark}</div><div id="dep-out" data-out></div></div></section>
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
      <div id="nm-out" data-out></div>
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
      <div id="gf-out" data-out></div>
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
      const r = await fetch(`/api/v1/jobs/${enc(id)}`, { credentials: "same-origin" }).catch(() => null);
      if (!r || r.status === 503) {
        if (box) box.innerHTML = `<p class="muted" aria-live="polite">${esc(what)}: the project is being moved, waiting…</p>`;
        await new Promise((ok) => setTimeout(ok, 1000 * Number((r && r.headers.get("Retry-After")) || 2)));
        continue;
      }
      const j = await r.json().catch(() => ({}));
      if (box) box.innerHTML = `<p class="muted" aria-live="polite">${esc(what)}: ${esc(j.state || "…")}</p>`;
      if (!["queued", "running", "running (unsupervised)"].includes(j.state)) return j;
      await new Promise((ok) => setTimeout(ok, 1000));
    }
  }
  const jobRefusal = async (j) => {
    const r = await fetch(`/api/v1/jobs/${enc(j.id)}/log`, { credentials: "same-origin" });
    const lines = ((await r.json().catch(() => ({}))).log || "").trim().split("\n").filter((x) => x.trim());
    const err = lines.filter((x) => x.startsWith("ERROR")).pop();
    return err ? `<p class="note" role="alert"><b>${esc(j.state)}.</b> ${esc(err)}</p>`
      : `<p class="note" role="alert"><b>${esc(j.state)}${j.exit != null ? ` (exit ${esc(j.exit)})` : ""}.</b> What it printed last:</p><pre class="reply">${esc(lines.slice(-10).join("\n"))}</pre>`;
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
        <div id="ds-use-out" data-out></div></div></section>
      <section class="part" data-form="dataset-new"><div class="parthead"><h2>Or make one from a source</h2></div><div class="body">
        <div class="field"><label class="name" for="ds-source">Where from</label><div><select id="ds-source"><option value="">choose a source</option>
          ${Object.entries(SOURCES).map(([k, [name]]) => `<option value="${k}" ${src === k ? "selected" : ""}>${esc(name)}</option>`).join("")}</select></div></div>
        ${fields.map(([k, hint, ex]) => `<div class="field"><label class="name" for="dsq-${k}">${esc(k)}</label><div><input type="text" id="dsq-${k}" data-q="${k}" value="${esc((d.q || {})[k] ?? "")}" placeholder="${esc(ex)}" autocapitalize="off" spellcheck="false"><div class="hint">${esc(hint)}</div></div></div>`).join("")}
        ${src ? `<div class="actions" style="margin-top:0"><button class="btn" type="button" id="ds-read">Read it</button><span class="muted">a job: the source's description and its first rows; nothing is saved</span></div>` : ""}
        <div id="ds-read-out" data-out>${said ? `<p class="note">${esc(JSON.stringify(said.source || {}))}${said.licence ? ` · licence ${esc(said.licence)}` : ""}</p>${rows}` : ""}</div>
        ${src && tabular(src) ? `<h3>Its fields</h3><p class="muted">Facts about each item to slice the results by, proposed from the source's columns; keep the ones you would compare on.</p>
          <div class="actions" style="margin-top:0"><button class="btn" type="button" id="ds-fields">Propose its fields</button></div>
          <div id="ds-fields-out" data-out>${fieldRows(d.fields)}</div>` : ""}
        ${src ? `<div class="field"><label class="name" for="ds-id">Its id</label><div><input type="text" id="ds-id" value="${esc(d.id || "")}" placeholder="cnn_dailymail_200" autocapitalize="off" spellcheck="false"><div class="hint">lowercase letters, digits and _</div></div></div>
        ${byField("ds-by")}
        <div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="ds-make" data-send>Make the dataset</button><span class="unsent" data-unsent-mark hidden>not saved yet · kept in this browser until it is made</span></div>` : ""}
        <div id="ds-make-out" data-out></div></div></section>
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
  // A goal's systems share one prompt, kept as versions of the name `<goal>/prompt` (RFC-028): a system points at the
  // version it sends (prompts: {name: {version}}), and every run records it, so the prompts' history says which text
  // each run sent. A prompt typed here is recorded first (the same text is the same version), then pointed at.
  const promptName = (goal) => `${goal}/prompt`;
  const latestOf = (pv) => (pv && !pv.error && (pv.versions || []).length ? pv.versions[pv.versions.length - 1] : null);
  const promptOf = (rec) => {
    const pr = ((rec || {}).record || {}).prompts || {}, n = Object.keys(pr)[0];
    return n ? { name: n, version: (pr[n] || {}).version || null } : null;
  };
  async function recordPrompt(name, text, parent, note, by, box) {
    const done = await runJob("/prompts/versions", { name, text, note, ...(parent ? { parent } : {}), by }, box, "recording the prompt");
    return done ? (((done.result || {}).result || {}).values || {}).version : null;
  }
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
    const pv = load(`prompt:${promptName(goal)}`, `/prompts/versions?name=${enc(promptName(goal))}&text=true`);
    if (pv === undefined) return `<div class="screen wide">${head}${loading("the goal's prompt")}</div>`;
    const latest = latestOf(pv);
    const d = readSys(goal) || { model: "", deployment: "", prompt: latest ? latest.text : "", temperature: "0", max_tokens: "", id: "" };
    const sysrec = Object.fromEntries(sys.systems.map((x) => [x.system, load(`sysrec:${x.system}`, `/systems/${enc(x.system)}`)]));
    const promptCell = (id) => {
      const r = sysrec[id];
      if (r === undefined) return "…";
      const pr = promptOf(r);
      if (pr) return `<a class="mono" href="#prompts/${enc(pr.name)}">${esc(pr.version || pr.name)}</a>`;
      return r && !r.error && ((r.record || {}).params || {}).prompt != null ? '<span class="muted">inline, no version</span>' : '<span class="muted">—</span>';
    };
    if (readSys(goal)) UNSENT.set("system-new", `a new system for ${goal}`);
    const mrec = d.model ? load(`model:${d.model}`, `/models/${enc(d.model)}`) : null;
    const deps = mrec && !mrec.error ? mrec.deployments.map((x) => x.deployment) : [];
    const runnable = ms.models.filter((m) => m.deployments > 0);
    return `<div class="screen wide">${head}
      <section class="part"><div class="parthead"><h2>Check each on three items</h2></div><div class="body">
        <div class="inline"><label class="name" for="sm-ds">on</label><select id="sm-ds">${datasets.map((x) => `<option>${esc(x)}</option>`).join("")}</select>
          <label class="name" for="sm-cap">spend at most (USD)</label><input type="number" id="sm-cap" min="0.01" step="0.01" value="0.05" inputmode="decimal" style="width:7rem"></div>
        <div class="tablewrap"><table><thead><tr><th>system</th><th>model</th><th>where it runs</th><th>its prompt</th><th>its check</th></tr></thead><tbody>
        ${sys.systems.map((x) => `<tr><td class="mono">${esc(x.system)}</td><td>${esc(x.model || "")}</td><td>${esc(x.deployment || "")}</td><td>${promptCell(x.system)}</td>
          <td><button class="btn" type="button" data-smoke="${esc(x.system)}">Check it on three items</button> <button class="btn" type="button" data-clone="${esc(x.system)}">Clone it, change one thing</button>
            <div id="sm-${esc(x.system)}" data-out aria-live="polite">${smokeView(smokes[`${goal}/${x.system}`])}</div><div id="cl-${esc(x.system)}"></div></td></tr>`).join("")}</tbody></table></div>
        ${byField("sm-by")}</div></section>
      <section class="part" data-form="system-new"><div class="parthead"><h2>Make a system from a model</h2></div><div class="body">
        <div class="field"><label class="name" for="sn-model">The model</label><div><select id="sn-model"><option value="">choose a model that has somewhere to run</option>
          ${runnable.map((m) => { const b = (m.best || []).find((x) => x.goal === goal);
            return `<option value="${esc(m.model)}" ${d.model === m.model ? "selected" : ""}>${esc(m.name || m.model)} · ${esc(m.state)}${b ? ` · #${b.rank} of ${b.of} on this goal` : ""}</option>`; }).join("")}</select>
          <div class="hint">a model not here is brought in first: <a href="#model-new">Bring in a model</a></div></div></div>
        ${d.model ? `<div class="field"><label class="name" for="sn-dep">Where it runs</label><div><select id="sn-dep">${deps.map((x) => `<option ${d.deployment === x ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></div></div>
        <div class="field"><label class="name" for="sn-prompt">The prompt</label><div><textarea id="sn-prompt" rows="2" placeholder="Summarise the following in one sentence:">${esc(d.prompt)}</textarea><div class="hint">the same for every system, so a difference in the scores is the model's. It is kept as a version of <a class="mono" href="#prompts/${enc(promptName(goal))}">${esc(promptName(goal))}</a>${latest ? ` (now ${esc(latest.id)})` : ""}: a changed text is a new version, and every run records the version it sent</div></div></div>
        <div class="field"><label class="name" for="sn-temp">Temperature</label><div><input type="text" id="sn-temp" inputmode="decimal" value="${esc(d.temperature)}" style="width:6rem"></div></div>
        <div class="field"><label class="name" for="sn-max">At most this many tokens</label><div><input type="text" id="sn-max" inputmode="numeric" value="${esc(d.max_tokens)}" placeholder="the model's default" style="width:10rem"></div></div>
        <div class="field"><label class="name" for="sn-id">Its id</label><div><input type="text" id="sn-id" value="${esc(d.idTyped ? d.id : `${d.model}_${d.deployment || deps[0] || ""}`.replace(/[^A-Za-z0-9_.-]+/g, "_"))}" autocapitalize="off" spellcheck="false"></div></div>
        ${byField("sn-by")}
        <div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="sn-make" data-send>Make the system</button><span class="unsent" data-unsent-mark hidden>not saved yet · kept in this browser until it is made</span></div>` : ""}
        <div id="sn-out" data-out></div></div></section>
      ${WB.cmd(`evh prompt-version --name ${promptName(goal)} --text "..." --note "..."\nevh system-new <id> --set model_record=<model> --set deployment=<where> --set 'prompts={"${promptName(goal)}": {"version": "<id>"}}'\nevh arm-smoke --system <id> --dataset ${datasets[0] || "<dataset>"} --max-cost-usd 0.05`)}
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
        <button class="btn primary" type="button" id="cl-go-${esc(src)}" data-send>Make the clone</button>${mark}</div><div id="cl-out-${esc(src)}" data-out></div>`;
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
          if (what === "prompt") {
            // a new version of the source's prompt (or of the goal's, for a system that kept its prompt inline)
            const pr = promptOf(r.result) || { name: promptName(goal), version: null };
            const ver = await recordPrompt(pr.name, raw, pr.version, `${v(`cl-id-${src}`)}: ${src}'s prompt, changed`, by, out);
            if (!ver) { ev.target.disabled = false; return; }
            delete params.prompt;
            rest.prompts = { [pr.name]: { version: ver.id } };
            forget(`prompt:${pr.name}`);
          } else params[what] = ["temperature", "max_tokens"].includes(what) ? Number(raw) : raw;
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
      if (d.temperature !== "") set["params.temperature"] = Number(d.temperature);
      if (d.max_tokens !== "") set["params.max_tokens"] = Number(d.max_tokens);
      ev.target.disabled = true;
      try {
        if (d.prompt.trim()) {
          // the goal's prompt as a version (the same text is the same version), the system pointing at it
          const latest = latestOf(LIVE.cache[`prompt:${promptName(goal)}`]);
          const ver = await recordPrompt(promptName(goal), d.prompt.trim(), latest && latest.text !== d.prompt.trim() ? latest.id : null, `the prompt of system ${d.id}, made in the Workbench`, by, out);
          if (!ver) { ev.target.disabled = false; return; }
          set.prompts = { [promptName(goal)]: { version: ver.id } };
          forget(`prompt:${promptName(goal)}`);
        }
        await send("POST", `/systems/${enc(d.id)}`, { set, by });
        sent("system-new"); dropSys(goal); forget("systems"); forget("sysrec:");
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
  // An evidence chart (RFC-034), drawn by the server as the catalog and `evh chart` draw it: the drawing, its numbers
  // folded under it, and its command. `quiet`: a chart with too little to draw yet leaves no note behind.
  const chartArgs = (p) => Object.entries(p).filter(([, v]) => v).map(([k, v]) => `--${k} ${v}`).join(" ");
  function chartBox(kind, params, quiet = false) {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
    const r = load(`chart:${kind}:${qs}`, `/charts/${kind}?${qs}`);
    if (r === undefined) return `<div class="chart-box">${loading("the chart")}</div>`;
    if (r.error) return quiet ? "" : `<div class="chart-box" data-chart="${esc(kind)}"><p class="muted">No chart yet: ${esc(r.error)}</p></div>`;
    const cols = r.columns || [];
    const cell = (v) => (v == null ? "—" : typeof v === "number" ? num(v, 4) : typeof v === "object" ? esc(JSON.stringify(v)) : esc(v));
    return `<div class="chart-box" data-chart="${esc(kind)}">${r.svg}<details class="table"><summary>The numbers</summary><div class="tablewrap"><table><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
      <tbody>${(r.rows || []).map((x) => `<tr>${cols.map((c) => `<td>${cell(x[c])}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>${WB.cmd(`evh chart ${kind} ${chartArgs(params)}`)}</div>`;
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
        <div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="ro-open" data-send>Open the round</button>${mark}</div><div id="ro-out" data-out></div></div></section>`;
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
      ${versions.map((b) => `<li>v${b.version}${b.version === b.current ? ' <span class="status ok">current</span>' : ""} · <span class="mono">${esc(b.promoted_from)}</span> · ${esc(actorSaid(b.actor))} · <small>${esc(b.reason || "")}</small>
        ${b.version !== b.current ? `<div class="inline" data-form="rollback-${b.version}"><input type="text" id="rb-why-${b.version}" placeholder="why go back to it, a sentence" aria-label="why roll back to v${b.version}" style="min-width:16rem">
          <button class="btn" type="button" data-rollback="${b.version}" data-send>Roll back to v${b.version}</button>${mark}</div>` : ""}</li>`).join("")}</ul><div id="rb-out" data-out></div></div></section>` : "";
    const leaderRun = (() => { const a = r.arms.find((x) => x.arm === ev.leader); return a ? a.runs[a.runs.length - 1] : ""; })();
    return `<div class="screen wide">${head}${tabs}
      <h2>${esc(r.hypothesis || "(no question)")}</h2>
      ${byField("ev-by")}
      <p class="muted">${esc(r.round_id)} · ${esc(r.status)} · on ${esc(r.dataset_id)}${r.from ? ` · from ${esc(r.from)}` : ""}${r.budget_usd != null ? ` · budget $${esc(r.budget_usd)}` : ""} · spent $${num(ev.spent_usd, 4)}</p>
      ${r.conclusion ? `<div class="answer"><div class="kicker">its conclusion</div><p>${esc(typeof r.conclusion === "string" ? r.conclusion : r.conclusion.text || JSON.stringify(r.conclusion))}</p></div>` : ""}
      <section class="part"><div class="parthead"><h2>The evidence</h2><span class="grow"></span><span class="muted">${esc(ev.metric || "")} · each arm against the leader, Holm</span></div><div class="body">
        ${chartBox("gain-cost", { goal, round: cur })}
        ${rows ? `<p class="muted">The leader: <b class="mono">${esc(short(ev.leader))}</b>. A verdict holds when the raw p is under its threshold.</p>
          <div class="tablewrap"><table><thead><tr><th>arm</th><th class="num">mean</th><th class="num">Δ</th><th class="num">raw p</th><th class="num">threshold</th><th>verdict</th></tr></thead><tbody>${rows}</tbody></table></div>` : ""}
        ${(ev.notes || []).length ? `<ul>${ev.notes.map((n) => `<li class="muted">${esc(n)}</li>`).join("")}</ul>` : ""}</div></section>
      <section class="part"><div class="parthead"><h2>Where the arms stand</h2></div><div class="body">
        <p class="muted">Every arm of the goal on ${esc(r.dataset_id)}, this round's and before.</p>
        ${chartBox("intervals", { goal, dataset: r.dataset_id })}${chartBox("items", { goal, dataset: r.dataset_id })}${chartBox("latency", { goal, dataset: r.dataset_id }, true)}</div></section>
      <section class="part"><div class="parthead"><h2>Its arms</h2></div><div class="body"><ul id="arms">${arms || '<li class="muted">none yet</li>'}</ul>
        ${isOpen ? `<div id="rt-box"></div>` : ""}
        ${isOpen && carryable.length ? `<div class="inline"><label class="name" for="cy-arm">Carry in from ${esc(r.from)}</label><select id="cy-arm">${carryable.map((x) => `<option>${esc(x)}</option>`).join("")}</select>
          <button class="btn" type="button" id="cy-go">Carry it in</button><span class="muted">unchanged, not run again</span></div><div id="cy-out" data-out></div>` : ""}</div></section>
      ${baseline}
      ${isOpen ? `<section class="part"><div class="parthead"><h2>Run arms in it</h2></div><div class="body">
        ${toRun.length ? `<div class="choices">${toRun.map((x) => `<label class="choice"><input type="checkbox" data-run="${esc(x.system)}"> <span class="mono">${esc(x.system)}</span> <small>${esc(x.model || "")}</small></label>`).join("")}</div>
          <div class="inline"><label class="name" for="rn-cap">spend at most (USD)</label><input type="number" id="rn-cap" min="0.01" step="0.01" value="1" inputmode="decimal" style="width:7rem">
          <button class="btn" type="button" id="rn-est">See the cost first</button><button class="btn primary" type="button" id="rn-go">Run them</button></div>
          <div id="rn-out" data-out aria-live="polite"></div>` : '<p class="muted">Every system of the project is in this round.</p>'}</div></section>
        <section class="part" data-form="round-close"><div class="parthead"><h2>Close the round</h2></div><div class="body">
          <div class="field"><label class="name" for="rc-text">Its conclusion</label><div><textarea id="rc-text" rows="3" placeholder="What the round showed, and what it decided, in a sentence or more."></textarea></div></div>
          ${leaderRun ? `<label class="choice"><input type="checkbox" id="rc-promote" value="${esc(leaderRun)}"> promote the leader's run (<span class="mono">${esc(leaderRun)}</span>) to the goal's baseline, the conclusion as its reason</label>` : ""}
          <div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="rc-close" data-send>Close the round</button>${mark}</div><div id="rc-out" data-out></div></div></section>` : openForm}
      ${WB.cmd(`evh round-list ${goal}\nevh round-evidence ${goal} ${r.round_id}`)}
      <div class="actions"><a class="btn" href="#judge/${enc(goal)}">A judge for this goal</a><a class="btn" href="#goal/${enc(goal)}">Back to the goal</a></div></div>`;
  }
  function wireEval() {
    const [goal, wanted] = String(WB.param || "").split("/");
    const rl = LIVE.cache[`rounds:${goal}`] || { rounds: [] };
    const cur = wanted || ((rl.rounds || []).find((r) => r.status === "open") || rl.rounds[rl.rounds.length - 1] || {}).round_id;
    const v = (id) => (document.getElementById(id)?.value || "").trim();
    const byOr = (id) => byOf(id) || (who() ? `person:${who()}` : null);
    const again = (round, box) => {
      forget(`rounds:${goal}`); forget(`round:${goal}/`); forget(`evidence:${goal}/`); forget(`status:${goal}`); forget("goals"); forget("chart:");
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
        <button class="btn" type="button" id="rt-go" data-send>Retire it</button>${mark}<button class="btn" type="button" id="rt-no">Keep it</button></div><div id="rt-out" data-out></div></div>`;
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

  // ── W2 review the outputs (UXS-005 W2): which is better, blind, or what went wrong, on a sheet submitted when done ──
  // The sheet is a sheet-export job's (API 1): the page reads the sheet, never its key, so "which is better" stays blind;
  // the filled sheet goes to sheet-import with export_job, which reads the key where the job kept it.
  const revKey = (goal) => `evh.draft.review.${goal}`;
  const readRev = (goal) => { try { return JSON.parse(localStorage.getItem(revKey(goal)) || "null"); } catch { return null; } };
  const keepRev = (goal, d) => { try { localStorage.setItem(revKey(goal), JSON.stringify(d)); } catch { /* this visit only */ } };
  const dropRev = (goal) => { try { localStorage.removeItem(revKey(goal)); } catch { /* nothing kept */ } };
  const revDone = (d) => Object.values(d.answers || {}).filter((a) => a.pick || Object.values(a.tags || {}).some((t) => t && t.length)).length;
  function screenReview(goal) {
    const head = `<div class="kicker">Review · ${esc(goal)}</div><h1>Review the outputs</h1>
      <p class="lead">Two arms' outputs on the same item, side by side: say which is better (blind, the arms hidden) or what went wrong in each. Nothing is written until you submit the sheet.</p>`;
    if (!goal) return `<div class="screen">${head}</div>`;
    const d = readRev(goal);
    if (!d || !d.sheet) {
      const rec = load(`goalrec:${goal}`, `/goals/${enc(goal)}`), fm = load("failure-modes", "/failure-modes");
      if (rec === undefined || fm === undefined) return `<div class="screen wide">${head}${loading("the goal")}</div>`;
      if (rec.error || fm.error) return `<div class="screen wide">${head}${failed(rec.error ? rec : fm)}</div>`;
      const datasets = (rec.record.datasets || []).map((x) => x.dataset_id), pickDs = (d && d.dataset) || datasets[0];
      const arms = pickDs ? load(`arms:${pickDs}`, `/datasets/${enc(pickDs)}/arms`) : { arms: [] };
      if (arms === undefined) return `<div class="screen wide">${head}${loading("the arms")}</div>`;
      const systems = [...new Set((arms.arms || []).map((a) => a.system))];
      const lists = (fm.failure_modes || []).map((x) => x.failure_modes).filter(Boolean);
      return `<div class="screen wide">${head}
        <div class="field"><label class="name" for="rv-ds">On</label><div><select id="rv-ds">${datasets.map((x) => `<option value="${esc(x)}" ${x === pickDs ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></div></div>
        <div class="field"><label class="name" for="rv-a">Compare</label><div class="inline"><select id="rv-a">${systems.map((x, i) => `<option value="${esc(x)}" ${i === 0 ? "selected" : ""}>${esc(x)}</option>`).join("")}</select>
          with <select id="rv-b">${systems.map((x, i) => `<option value="${esc(x)}" ${i === 1 ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></div></div>
        <div class="field"><div class="name" id="rv-mode-l">What you will say</div><div class="choices" role="radiogroup" aria-labelledby="rv-mode-l">
          <label class="choice"><input type="radio" name="rv-mode" value="pick" checked> which is better <small>the arms hidden and shuffled per item, so the pick is not swayed</small></label>
          <label class="choice"><input type="radio" name="rv-mode" value="tags"> what went wrong <small>each output tagged with the failure modes it shows</small></label></div></div>
        <div class="field"><label class="name" for="rv-modes">Failure modes</label><div><select id="rv-modes">${lists.map((x) => `<option>${esc(x)}</option>`).join("")}<option value="">a new list…</option></select>
          <div class="inline"><input type="text" id="rv-new-id" placeholder="its id: summaries" style="width:10rem" autocapitalize="off" spellcheck="false"><input type="text" id="rv-new-modes" placeholder="its modes: narration, overlong, truncated" style="min-width:18rem" autocapitalize="off" spellcheck="false"></div>
          <div class="hint">for "what went wrong": a named list, so tags are counted, not re-invented in each note</div></div></div>
        ${byField("rv-by")}
        <div class="actions"><button class="btn primary" type="button" id="rv-make">Make the sheet</button><a class="btn" href="#goal/${enc(goal)}">Back to the goal</a></div><div id="rv-out" data-out></div>
        <p class="muted">The expected answers are labelled on their own screen: <a href="#label/${enc(pickDs || "")}">label ${esc(pickDs || "")}'s items</a>.</p>
        ${WB.cmd(`evh sheet-export --dataset-id ${pickDs || "<dataset>"} --runs A,B --csv review.csv --fill pick`)}</div>`;
    }
    const n = revDone(d);
    if (n) UNSENT.set("review-sheet", `${n} answer(s) on the review of ${goal}`);
    const [header, ...rows] = d.sheet, at = (h) => header.indexOf(h);
    const iId = at("item_id"), iItem = at("item");
    const items = rows.filter((r) => !String(r[iId]).startsWith("#"));
    const legend = (rows.find((r) => String(r[iId]) === "#modes") || [])[iItem] || "";
    const tokens = header.filter((h) => h.startsWith("failure_modes: ")).map((h) => h.slice("failure_modes: ".length));
    const body = items.map((r) => {
      const id = r[iId], a = (d.answers || {})[id] || {};
      if (d.mode === "pick") {
        const letters = ["A", "B"].filter((x) => at(x) >= 0);
        return `<tr><td class="mono">${esc(id)}</td><td class="clip"><div>${esc(r[iItem])}</div></td>${letters.map((x) => `<td class="clip"><div>${esc(r[at(x)])}</div></td>`).join("")}
          <td><div class="choices">${[...letters, "A|B"].map((x) => `<label class="choice"><input type="radio" name="pk-${esc(id)}" data-pick="${esc(id)}" value="${x}" ${a.pick === x ? "checked" : ""}> ${x === "A|B" ? "the same" : x}</label>`).join("")}</div></td></tr>`;
      }
      return `<tr><td class="mono">${esc(id)}</td><td class="clip"><div>${esc(r[iItem])}</div></td>${tokens.map((t) => `<td><div class="clip"><div>${esc(r[at(`output: ${t}`)])}</div></div>
        <div class="choices">${[...d.modeIds, "ok"].map((m) => `<label class="choice"><input type="checkbox" data-tag="${esc(id)}" data-arm="${esc(t)}" value="${esc(m)}" ${((a.tags || {})[t] || []).includes(m) ? "checked" : ""}> ${esc(m)}</label>`).join("")}</div></td>`).join("")}</tr>`;
    }).join("");
    const cols = d.mode === "pick" ? `<th>A</th><th>B</th><th>which is better</th>` : tokens.map((t) => `<th>${esc(t)}</th>`).join("");
    return `<div class="screen wide" data-form="review-sheet">${head}
      <p class="muted">${esc(d.dataset)} · ${d.mode === "pick" ? "which is better, blind" : `what went wrong · ${esc(legend)}`}</p>
      <div class="tablewrap"><table><thead><tr><th>item</th><th>the item</th>${cols}</tr></thead><tbody>${body}</tbody></table></div>
      <div class="field"><label class="name" for="rv-name">${d.mode === "pick" ? "The judgements' name" : "The tag set's name"}</label><div><input type="text" id="rv-name" value="${esc(d.name || "")}" placeholder="${d.mode === "pick" ? "owner_picks" : "first_pass"}" autocapitalize="off" spellcheck="false"></div></div>
      ${byField("rv-by")}
      <div class="actions"><button class="btn primary" type="button" id="rv-submit" data-send>Submit</button><span class="unsent" data-unsent-mark hidden><span id="rv-count">${n}</span> answer(s) not submitted · kept in this browser</span>
        <button class="btn" type="button" id="rv-drop">Throw the sheet away</button></div><div id="rv-out" data-out></div></div>`;
  }
  function wireReview() {
    const goal = WB.param || "";
    const v = (id) => (document.getElementById(id)?.value || "").trim();
    document.getElementById("rv-ds")?.addEventListener("change", () => { keepRev(goal, { dataset: v("rv-ds") }); WB.render(true); });
    document.getElementById("rv-make")?.addEventListener("click", async (ev) => {
      const out = document.getElementById("rv-out"), by = byOf("rv-by") || (who() ? `person:${who()}` : null);
      if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are: a job names who asked.</p>'; return; }
      const mode = document.querySelector("input[name=rv-mode]:checked").value, ds = v("rv-ds");
      const runs = mode === "pick" ? [v("rv-a"), v("rv-b")] : [...new Set([v("rv-a"), v("rv-b")])];
      if (mode === "pick" && runs[0] === runs[1]) { out.innerHTML = '<p class="note" role="alert">Two different arms: a pick needs two outputs.</p>'; return; }
      ev.target.disabled = true;
      try {
        let modes = v("rv-modes");
        if (mode === "tags" && !modes) {
          modes = v("rv-new-id");
          const ids = v("rv-new-modes").split(",").map((x) => x.trim()).filter(Boolean);
          await send("POST", `/failure-modes/${enc(modes)}`, { set: { modes: ids.map((id) => ({ id })) }, by });
          forget("failure-modes");
        }
        const inputs = { runs: runs.join(","), csv: "review.csv", fill: mode, by };
        if (mode === "tags") inputs.modes = modes;
        const done = await runJob(`/datasets/${enc(ds)}/sheets`, inputs, out, "making the sheet");
        if (done) {
          const sheet = parseCsv(await (await fetch(`/api/v1/jobs/${enc(done.id)}/files/review.csv`, { credentials: "same-origin" })).text()).filter((r) => r.length > 1);
          let modeIds = [];
          if (mode === "tags") {
            const fmr = await fetch(`/api/v1/failure-modes/${enc(modes)}`, { credentials: "same-origin" }).then((x) => x.json());
            modeIds = (((fmr.result || {}).record || {}).modes || []).map((m) => m.id);
          }
          keepRev(goal, { dataset: ds, mode, modes, modeIds, job: done.id, sheet, answers: {}, name: "" });
          WB.render(true);
        }
      } catch (e) { out.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    const d = readRev(goal);
    if (!d || !d.sheet) return;
    const name = () => v("rv-name");
    const show = (cur) => {
      const n = revDone(cur), btn = document.getElementById("rv-submit");
      if (n) UNSENT.set("review-sheet", `${n} answer(s) on the review of ${goal}`); else UNSENT.delete("review-sheet");
      document.getElementById("rv-count").textContent = n;
      document.querySelector("[data-form=review-sheet] [data-unsent-mark]").hidden = !n;
      btn.disabled = !n;
      btn.textContent = `Submit ${n} answer(s) as ${cur.mode === "pick" ? "judgements" : "tag set"} ${name() || "…"}`;
    };
    show(d);
    document.querySelector("[data-form=review-sheet]").addEventListener("change", (e) => {
      const cur = readRev(goal) || d, t = e.target;
      cur.answers = cur.answers || {};
      if (t.dataset.pick) { cur.answers[t.dataset.pick] = { ...(cur.answers[t.dataset.pick] || {}), pick: t.value }; }
      if (t.dataset.tag) {
        const a = cur.answers[t.dataset.tag] = cur.answers[t.dataset.tag] || {};
        a.tags = a.tags || {};
        const set = new Set(a.tags[t.dataset.arm] || []);
        if (t.checked) set.add(t.value); else set.delete(t.value);
        a.tags[t.dataset.arm] = [...set];
      }
      cur.name = name();
      keepRev(goal, cur); show(cur);
    }, true);
    document.getElementById("rv-name").addEventListener("input", () => { const cur = readRev(goal) || d; cur.name = name(); keepRev(goal, cur); show(cur); });
    document.getElementById("rv-drop").addEventListener("click", () => {
      if (!window.confirm(`Throw away ${revDone(readRev(goal) || d)} answer(s) not submitted?`)) return;
      dropRev(goal); UNSENT.delete("review-sheet"); WB.render(true);
    });
    document.getElementById("rv-submit").addEventListener("click", async (ev) => {
      const cur = readRev(goal) || d, out = document.getElementById("rv-out"), by = byOf("rv-by");
      if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are: a sheet names who filled it.</p>'; return; }
      if (!name()) { out.innerHTML = '<p class="note" role="alert">Name what it is written as.</p>'; return; }
      const [header, ...rows] = cur.sheet, at = (h) => header.indexOf(h), iId = at("item_id");
      const filled = [header, ...rows.map((r) => {
        const x = [...r], a = (cur.answers || {})[r[iId]] || {};
        if (cur.mode === "pick" && at("pick") >= 0 && !String(r[iId]).startsWith("#")) x[at("pick")] = a.pick || "";
        if (cur.mode === "tags") for (const [t, ms] of Object.entries(a.tags || {})) if (at(`failure_modes: ${t}`) >= 0) x[at(`failure_modes: ${t}`)] = ms.join("|");
        return x;
      })];
      const content = btoa(unescape(encodeURIComponent(csvOf(filled))));
      const inputs = { sheet: { name: "review.csv", content_base64: content }, export_job: cur.job, by };
      if (cur.mode === "pick") inputs.scorer = name(); else { inputs.tags = name(); inputs.modes = cur.modes; }
      ev.target.disabled = true;
      try {
        const done = await runJob(`/datasets/${enc(cur.dataset)}/sheets/import`, inputs, out, "submitting the sheet");
        if (done) {
          dropRev(goal); UNSENT.delete("review-sheet");
          out.innerHTML = `<p class="note">Written: ${cur.mode === "pick" ? `the judgements <b>${esc(name())}</b>, read as judged/${esc(name())}` : `the tag set <b>${esc(name())}</b>`}. <button class="btn" type="button" data-again>Make another sheet</button></p>`;
          out.querySelector("[data-again]").addEventListener("click", () => WB.render(true));
          document.querySelector("[data-form=review-sheet] [data-unsent-mark]").hidden = true;
        }
      } catch (e) { out.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
  }

  // ── W3 production (UXS-005 W3): what the deployed system decided, scored against labels, the rows to keep, the next
  // version of the dataset made from them ────────────────────────────────────────────────────────────────────────────
  const IMPORTERS = ["jsonl", "tsv", "github", "langfuse"];
  const blocksView = (res) => `<pre class="reply">${esc((((res || {}).blocks) || []).flatMap((b) => b.lines || []).join("\n"))}</pre>`;
  // label-coverage-show answers values (label_coverage.show prints them): the classes counted, each rule's reach
  const coverageView = (c) => `<p class="muted">${esc(c.dataset_id)}: ${c.items} item(s) over capture ${esc(c.capture)}</p>
    <div class="tablewrap"><table><thead><tr><th>class</th><th class="num">items</th></tr></thead><tbody>${Object.entries(c.counts || {}).map(([k, n]) => `<tr><td>${esc(k.replace(/_/g, " "))}</td><td class="num">${n}</td></tr>`).join("")}</tbody></table></div>
    <div class="tablewrap"><table><thead><tr><th>rule</th><th class="num">now</th><th class="num">when mature</th></tr></thead><tbody>${(c.rules || []).map((r) => `<tr><td class="mono">${esc(r.text)}</td><td class="num">${r.now}</td><td class="num">${r.when_mature}</td></tr>`).join("")}</tbody></table></div>`;
  const RULES_EXAMPLE = "- when: {resolved: fixed}\n  label: real problem\n- when: {resolved: wontfix}\n  label: not a problem\n- min_age_days: 14\n  absent: [resolved]\n  label: not a problem";
  function screenProduction(goal) {
    const head = `<div class="kicker">Production · ${esc(goal)}</div><h1>Learn from production</h1>
      <p class="lead">What the deployed system decided, kept as a capture; scored like an arm against the labels; the rows where it was wrong picked for the next version of the dataset.</p>`;
    if (!goal) return `<div class="screen">${head}</div>`;
    const caps = load("captures", "/captures"), sys = load("systems", "/systems"), ds = load("datasets", "/datasets"), rec = load(`goalrec:${goal}`, `/goals/${enc(goal)}`);
    if ([caps, sys, ds, rec].includes(undefined)) return `<div class="screen wide">${head}${loading("the captures")}</div>`;
    const bad = [caps, sys, ds, rec].find((x) => x.error);
    if (bad) return `<div class="screen wide">${head}${failed(bad)}</div>`;
    const capIds = caps.captures.map((c) => c.capture), dsIds = ds.datasets.map((x) => x.dataset), sysIds = sys.systems.map((x) => x.system);
    const ms = load("models", "/models");
    const codeIds = ms && !ms.error ? ms.models.filter((m) => m.kind === "code").map((m) => m.model) : [];
    const rp = WB._replay || {};
    const opt = (xs, sel) => xs.map((x) => `<option value="${esc(x)}" ${x === sel ? "selected" : ""}>${esc(x)}</option>`).join("");
    const pv = WB._prod || {};
    const wrong = pv.rows ? `<div class="tablewrap"><table><thead><tr><th>keep</th><th>item</th><th>production decided</th><th>the labels</th></tr></thead><tbody>
      ${pv.rows.map((r) => `<tr><td><input type="checkbox" data-keep-item="${esc(r.item)}" aria-label="pick ${esc(r.item)}" ${r.picked ? "disabled checked" : ""}></td><td class="mono">${esc(r.item)}</td>
        <td class="clip"><div>${esc(Object.values(r.decisions || {})[0] ?? "")}</div></td><td class="clip"><div>${esc(Object.values(r.labels || {}).join(" · "))}</div></td></tr>`).join("")}</tbody></table></div>
      <p class="muted">${pv.rows.length} row(s) where production's decision is not ${esc(pv.against)}'s.</p>` : "";
    return `<div class="screen wide">${head}
      ${byField("pd-by")}
      <section class="part"><div class="parthead"><span class="letter">1</span><h2>What it decided</h2></div><div class="body">
        ${caps.captures.length ? `<ul>${caps.captures.map((c) => `<li><b class="mono">${esc(c.capture)}</b> · ${c.records} record(s) · ${esc(c.importer)} · ${esc((c.captured_at || "").slice(0, 16))}${(c.datasets || []).length ? ` · made into ${c.datasets.map(esc).join(", ")}` : ""}</li>`).join("")}</ul>` : '<p class="muted">No capture yet.</p>'}
        <div data-form="capture-new"><h3>Capture records</h3>
          <div class="inline"><select id="cp-importer" aria-label="the importer">${opt(IMPORTERS, "jsonl")}</select>
            <input type="text" id="cp-id" placeholder="the capture's id: prod_2026_11" autocapitalize="off" spellcheck="false"></div>
          <textarea id="cp-query" rows="2" placeholder='{"path": "records.jsonl"}' aria-label="the importer's query" style="width:100%"></textarea>
          <div class="actions" style="margin-top:0"><button class="btn" type="button" id="cp-go" data-send>Capture them</button>${mark}</div><div id="cp-out" data-out></div></div>
        ${capIds.length ? `<h3>Make a dataset of a capture</h3><div class="inline" data-form="capture-dataset"><select id="cd-cap" aria-label="the capture">${opt(capIds)}</select>
          <input type="text" id="cd-id" placeholder="its dataset's id" autocapitalize="off" spellcheck="false"><button class="btn" type="button" id="cd-go" data-send>Make the dataset</button>${mark}</div><div id="cd-out" data-out></div>` : ""}</div></section>
      <section class="part"><div class="parthead"><span class="letter">2</span><h2>Against people's labels</h2></div><div class="body">
        <p class="muted">Production's recorded decisions become an arm, scored like any (no call), beside the goal's arms in the eval.</p>
        ${capIds.length ? `<div class="inline" data-form="capture-arm"><select id="ca-cap" aria-label="the capture">${opt(capIds)}</select><select id="ca-ds" aria-label="the dataset">${opt(dsIds)}</select>
          <input type="text" id="ca-as" placeholder="the arm's system id: production_v1" autocapitalize="off" spellcheck="false">
          <input type="text" id="ca-field" placeholder="the record's field holding the decision" autocapitalize="off" spellcheck="false">
          <button class="btn" type="button" id="ca-go" data-send>Score its decisions</button>${mark}</div><div id="ca-out" data-out></div>` : '<p class="muted">Capture production\'s records first.</p>'}</div></section>
      <section class="part"><div class="parthead"><span class="letter">3</span><h2>Pick the rows for the next version</h2></div><div class="body">
        <div class="inline"><select id="wr-ds" aria-label="the dataset">${opt(dsIds, pv.dataset)}</select><select id="wr-run" aria-label="production's arm">${opt(sysIds, pv.run)}</select>
          <input type="text" id="wr-set" value="${esc(pv.against || "")}" placeholder="against a label set: SET or DATASET/SET" autocapitalize="off" spellcheck="false"><button class="btn" type="button" id="wr-show">Show where it was wrong</button></div>
        <div id="wr-out" data-out>${wrong}</div>
        ${pv.rows && pv.rows.length ? `<div data-form="pick"><div class="inline"><input type="text" id="pk-for" placeholder="the dataset they may join (optional)" autocapitalize="off" spellcheck="false">
          <input type="text" id="pk-note" placeholder="why they are worth keeping" style="min-width:18rem"><button class="btn primary" type="button" id="pk-go" data-send>Pick them</button>${mark}</div><div id="pk-out" data-out></div></div>` : ""}</div></section>
      <section class="part"><div class="parthead"><span class="letter">4</span><h2>The next dataset version</h2></div><div class="body" data-form="extend">
        <div class="inline"><select id="ex-from" aria-label="the dataset it grows from">${opt(dsIds, pv.dataset)}</select>
          <input type="text" id="ex-id" placeholder="the new version's id: tickets_v2" autocapitalize="off" spellcheck="false">
          <button class="btn primary" type="button" id="ex-go" data-send>Make the next version</button>${mark}</div>
        <p class="muted">Its items and every pick waiting for it.</p><div id="ex-out" data-out></div></div></section>
      <section class="part"><div class="parthead"><span class="letter">5</span><h2>Labels from what happened later</h2></div><div class="body">
        <p class="muted">Rules over each record's outcome (what production recorded afterwards) give the item its label, or skip it; tried in order, the first that matches decides.</p>
        ${capIds.length ? `<div data-form="outcome-labels"><div class="inline"><select id="ol-cap" aria-label="the capture">${opt(capIds)}</select><select id="ol-ds" aria-label="the dataset">${opt(dsIds, pv.dataset)}</select>
          <input type="text" id="ol-set" placeholder="the label set's name: outcomes_2026_11" autocapitalize="off" spellcheck="false"></div>
          <textarea id="ol-rules" rows="6" style="width:100%" aria-label="the rules" placeholder="${esc(RULES_EXAMPLE)}"></textarea>
          <div class="actions" style="margin-top:0"><button class="btn" type="button" id="ol-go" data-send>Label from the outcomes</button>${mark}</div></div><div id="ol-out" data-out></div>` : '<p class="muted">Capture production\'s records first.</p>'}</div></section>
      <section class="part"><div class="parthead"><span class="letter">6</span><h2>Replay the code that ran</h2></div><div class="body">
        <p class="muted">A code record's periods, each at the commit production ran; a replay of a system at those commits compared with production's arm, item by item.</p>
        ${codeIds.length ? `<div class="inline"><select id="rp-model" aria-label="the code record">${opt(codeIds, rp.model)}</select><button class="btn" type="button" id="rp-read">Show its periods and faithfulness</button></div>
          <div id="rp-out" data-out>${rp.periods ? `<h3>Its periods</h3>${blocksView(rp.periods)}` : ""}${rp.faith ? `<h3>Its newest faithfulness record</h3>${blocksView(rp.faith)}` : ""}</div>
          <h3>Replay a system</h3><div class="inline" data-form="replay"><select id="rf-sys" aria-label="the replay system">${opt(sysIds)}</select><select id="rf-ds" aria-label="the dataset">${opt(dsIds)}</select>
            <input type="text" id="rf-prod" placeholder="production's run id" autocapitalize="off" spellcheck="false">
            <input type="number" id="rf-cap" min="0.01" step="0.01" value="1" inputmode="decimal" style="width:6rem" aria-label="spend at most (USD)">
            <button class="btn" type="button" id="rf-est">See the plan first</button><button class="btn primary" type="button" id="rf-go" data-send>Replay it</button>${mark}</div><div id="rf-out" data-out></div>` : '<p class="muted">No code record in this project (a model record of kind: code).</p>'}</div></section>
      ${WB.cmd("evh capture --importer jsonl --query '{...}' --capture <id>\nevh arm-from-capture --capture <id> --dataset-id <d> --as <system>\nevh sheet-show <d> --runs <production> --wrong-against <set>\nevh pick --dataset-id <d> --item ... --note \"...\"\nevh dataset-extend --dataset <v1> --dataset-id <v2> --picks")}
      <div class="actions"><a class="btn" href="#goal/${enc(goal)}">Back to the goal</a></div></div>`;
  }
  function wireProduction() {
    const goal = WB.param || "";
    const v = (id) => (document.getElementById(id)?.value || "").trim();
    const by = () => byOf("pd-by") || (who() ? `person:${who()}` : null);
    const done = (form, out) => { sent(form); forget("captures"); forget("datasets"); forget("systems"); if (UNSENT.size) out.insertAdjacentHTML("beforeend", '<p class="note">Done. <button class="btn" type="button" data-show>Show it</button></p>'); else WB.render(true); out.querySelector("[data-show]")?.addEventListener("click", () => WB.render(true)); };
    const act = (btn, form, out, what, run) => document.getElementById(btn)?.addEventListener("click", async (ev) => {
      const box = document.getElementById(out), who_ = by();
      if (!who_) { box.innerHTML = '<p class="note" role="alert">Say who you are above: a change names who made it.</p>'; return; }
      ev.target.disabled = true;
      try { if (await run(who_, box)) done(form, box); } catch (e) { box.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    holds("capture-new", () => `Capture ${v("cp-id") || "…"}`);
    holds("capture-dataset", () => `Make dataset ${v("cd-id") || "…"}`);
    holds("capture-arm", () => `Score ${v("ca-as") || "…"}`);
    holds("extend", () => `Make ${v("ex-id") || "…"}`);
    act("cp-go", "capture-new", "cp-out", "capturing", (b, box) => runJob(`/captures/${enc(v("cp-id"))}`, { importer: v("cp-importer"), query: v("cp-query"), by: b }, box, "capturing"));
    act("cd-go", "capture-dataset", "cd-out", "making the dataset", async (b, box) => {
      // a dataset made from a capture is fetched at once: production's decisions are scored on its fetched items
      if (!(await runJob(`/captures/${enc(v("cd-cap"))}/datasets`, { dataset_id: v("cd-id"), by: b }, box, "making the dataset"))) return null;
      return runJob(`/datasets/${enc(v("cd-id"))}/materialize`, { by: b }, box, "fetching its items");
    });
    act("ca-go", "capture-arm", "ca-out", "scoring", (b, box) => {
      const inputs = { dataset_id: v("ca-ds"), as: v("ca-as"), goal, by: b };
      if (v("ca-field")) inputs.field = v("ca-field");
      return runJob(`/captures/${enc(v("ca-cap"))}/arms`, inputs, box, "scoring production's decisions");
    });
    document.getElementById("wr-show")?.addEventListener("click", async () => {
      const out = document.getElementById("wr-out"), dsId = v("wr-ds"), run = v("wr-run"), against = v("wr-set");
      if (!against) { out.innerHTML = '<p class="note" role="alert">Name the label set it is compared against.</p>'; return; }
      out.innerHTML = '<p class="muted">reading the sheet…</p>';
      const r = await fetch(`/api/v1/datasets/${enc(dsId)}/sheet?runs=${enc(run)}&wrong_against=${enc(against)}`, { credentials: "same-origin" });
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { out.innerHTML = `<p class="note" role="alert">${esc(b.error || r.status)}</p>`; return; }
      WB._prod = { dataset: dsId, run, against, rows: ((b.result || {}).values || {}).rows || [] };
      WB.render(true);
    });
    holds("pick", () => `Pick ${document.querySelectorAll("[data-keep-item]:checked:not([disabled])").length} row(s)`);
    act("pk-go", "pick", "pk-out", "picking", (b, box) => {
      const items = [...document.querySelectorAll("[data-keep-item]:checked:not([disabled])")].map((x) => x.dataset.keepItem);
      const inputs = { item: items, note: v("pk-note"), by: b };
      if (v("pk-for")) inputs.targets = [v("pk-for")];
      return runJob(`/datasets/${enc((WB._prod || {}).dataset)}/picks`, inputs, box, "picking").then((j) => { if (j) WB._prod = null; return j; });
    });
    act("ex-go", "extend", "ex-out", "making the next version", (b, box) => runJob(`/datasets/${enc(v("ex-from"))}/extend`, { dataset_id: v("ex-id"), picks: true, by: b }, box, "making the next version"));
    // labels from the outcomes: the rules sent as a file the job keeps; the coverage read from where it kept them
    holds("outcome-labels", () => `Label ${v("ol-ds") || "…"} as ${v("ol-set") || "…"}`);
    document.getElementById("ol-go")?.addEventListener("click", async (ev) => {
      const box = document.getElementById("ol-out"), who_ = by();
      if (!who_) { box.innerHTML = '<p class="note" role="alert">Say who you are above: a label set names who made it.</p>'; return; }
      const rules = document.getElementById("ol-rules").value;
      ev.target.disabled = true;
      try {
        const done = await runJob(`/captures/${enc(v("ol-cap"))}/label-sets`, { dataset_id: v("ol-ds"), set: v("ol-set"), map: { name: "rules.yaml", content_base64: btoa(unescape(encodeURIComponent(rules))) }, by: who_ }, box, "labelling from the outcomes");
        if (done) {
          sent("outcome-labels");
          const map = ((await fetch(`/api/v1/jobs/${enc(done.id)}`, { credentials: "same-origin" }).then((x) => x.json())).inputs || {}).map;
          const cov = await fetch(`/api/v1/datasets/${enc(v("ol-ds"))}/label-coverage?capture=${enc(v("ol-cap"))}&map=${enc(map)}`, { credentials: "same-origin" }).then((x) => x.json());
          box.innerHTML = `<p class="note">Written: label set <b>${esc(v("ol-set"))}</b> (source rule). How far the rules label ${esc(v("ol-ds"))} now:</p>${cov.result ? coverageView(cov.result) : `<p class="note" role="alert">${esc(cov.error || "")}</p>`}`;
        }
      } catch (e) { box.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    // replay: a code record's periods and faithfulness, read; a replay as a job, its plan first
    document.getElementById("rp-read")?.addEventListener("click", async () => {
      const m = v("rp-model"), box = document.getElementById("rp-out");
      box.innerHTML = '<p class="muted">reading…</p>';
      const get = (path) => fetch(`/api/v1${path}`, { credentials: "same-origin" }).then((x) => x.json()).catch(() => ({}));
      const [per, fa] = await Promise.all([get(`/models/${enc(m)}/periods`), get(`/models/${enc(m)}/faithfulness`)]);
      WB._replay = { model: m, periods: per.result || { blocks: [{ lines: [per.error || "no periods"] }] }, faith: fa.result || { blocks: [{ lines: [fa.error || "no faithfulness record yet"] }] } };
      box.innerHTML = `<h3>Its periods</h3>${blocksView(WB._replay.periods)}<h3>Its newest faithfulness record</h3>${blocksView(WB._replay.faith)}`;
    });
    holds("replay", () => `Replay ${v("rf-sys") || "…"}`);
    const replayInputs = () => ({ dataset: v("rf-ds"), production: v("rf-prod") });
    document.getElementById("rf-est")?.addEventListener("click", async () => {
      const box = document.getElementById("rf-out");
      box.innerHTML = '<p class="muted">planning…</p>';
      const r = await fetch("/api/v1/estimate", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-EVH-Data": "1" }, body: JSON.stringify({ operation: "faithfulness", inputs: { system: v("rf-sys"), ...replayInputs() } }) });
      const b = await r.json().catch(() => ({}));
      box.innerHTML = r.ok ? blocksView(b.result) : `<p class="note" role="alert">${esc(b.error || b.text || r.status)}</p>`;
    });
    document.getElementById("rf-go")?.addEventListener("click", async (ev) => {
      const box = document.getElementById("rf-out"), who_ = by(), cap = Number(v("rf-cap"));
      if (!who_) { box.innerHTML = '<p class="note" role="alert">Say who you are above: a replay names who asked.</p>'; return; }
      if (!(cap > 0)) { box.innerHTML = '<p class="note" role="alert">Say the most it may spend first.</p>'; return; }
      ev.target.disabled = true;
      try {
        const done = await runJob(`/systems/${enc(v("rf-sys"))}/faithfulness`, { ...replayInputs(), by: who_, max_cost_usd: cap }, box, "replaying");
        if (done) { sent("replay"); box.innerHTML = `<p class="note">Replayed.</p>${blocksView((done.result || {}).result)}`; }
      } catch (e) { box.innerHTML = refusal(e); }
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
        <button class="btn" type="button" data-promote="${esc(x.name)}" data-send>Promote</button>${mark}</div><div id="po-${esc(x.name)}" data-out></div></div>`).join("");
    return `<div class="screen wide">${head}
      <section class="part"><div class="parthead"><span class="letter">a</span><h2>Fetch its items</h2><span class="grow"></span>${done(fetched)}</div><div class="body">
        <p class="muted">Downloads every item and checks it against its hash, so a run reads exactly the frozen items.</p>
        ${fetched ? "" : `<div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="pp-fetch">Fetch them</button></div>`}<div id="pp-fetch-out" data-out></div></div></section>
      <section class="part"><div class="parthead"><span class="letter">b</span><h2>Look inside</h2><span class="grow"></span>${done(looked)}</div><div class="body">
        <p class="muted">How many items, how long, each field's values: most surprises show here, before anything runs.</p>
        ${looked ? `<p><a href="${catalogPage(ds)}">Open its page in the catalog ↗</a></p>` : `<div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="pp-look" ${fetched ? "" : "disabled"}>Profile it</button>${fetched ? "" : '<span class="muted">after it is fetched</span>'}</div>`}
        <div id="pp-look-out" data-out></div></div></section>
      <section class="part"><div class="parthead"><span class="letter">c</span><h2>Its reference set</h2><span class="grow"></span>${done(refs.length)}</div><div class="body">
        <p class="muted">The expected answer for each item, that outputs are scored against. Gold is checked by people; silver is a model's answers, enough to rank systems. Who and why are recorded.</p>
        ${refs.length ? `<ul>${refs.map((r) => `<li><b>${esc(r.reference)}</b> · ${r.items} item(s) · ${esc(r.kind || "")}</li>`).join("")}</ul>
          <div class="actions" style="margin-top:0"><a class="btn" href="#reference/${enc(ds)}">Change the reference set</a><span class="muted">see what another one moves first</span></div>` : ""}
        ${sets.length ? `<h3>Promote a label set</h3>${promote}` : '<p class="muted">No label set yet.</p>'}
        <h3>Or label it</h3><div class="actions" style="margin-top:0"><a class="btn" href="#label/${enc(ds)}">Label it here</a></div>
        ${byField("pp-by")}</div></section>
      ${chartBox("rank-stability", { dataset: ds }, true)}${chartBox("agreement", { dataset: ds }, true)}
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

  // ── W6: change the reference set (UXS-005 W6): what a label set moves, promoted with why, the arms re-scored ($0) ──
  // "What it moves" scores the stored outputs against the label set under its own label (rescore --labels: never where
  // a goal reads), then reads the leaderboard: one table per reference the arms were scored against.
  const fx = (x) => (typeof x === "number" ? x.toFixed(3) : "—");
  const orderLine = (g) => {
    const o = g.ordering || {}, d = g.decision || {}, lead = String(d.leader || "").split("/").pop();
    const p = typeof o.global_p === "number" ? `p ${o.global_p.toFixed(4)}` : "";
    return `${lead ? `leader <b class="mono">${esc(lead)}</b>; ` : ""}${o.arm_effect ? `the arms differ (${p})` : o.enough_data === false ? "too few items to test an order" : `no detectable difference between the arms${p ? ` (${p})` : ""}: do not report an order`}`;
  };
  function movesView(lb, newRef, oldRef) {
    const groups = ((lb && lb.values) || {}).groups || [], nw = groups.find((g) => g.reference === newRef), od = groups.find((g) => g.reference === oldRef);
    if (!nw) return `<p class="note" role="alert">No arm is scored against ${esc(newRef)} yet.</p>`;
    const m = nw.sort_by, rankOld = Object.fromEntries(((od || {}).arms || []).map((a) => [a.system_id, a]));
    const rows = nw.arms.map((a) => {
      const o = rankOld[a.system_id], mv = o ? o.rank - a.rank : 0;
      return `<tr><td class="num">${a.rank}</td><td class="mono">${esc(a.system_id)}${a.wrote_reference ? ' <span class="tag new">wrote this reference</span>' : ""}</td><td class="num">${fx(a.metrics[m])}</td>
        <td class="num">${o ? o.rank : "—"}</td><td class="num">${o ? fx(o.metrics[m]) : "—"}</td><td class="num ${mv > 0 ? "v-lead" : mv < 0 ? "v-worse" : ""}">${mv > 0 ? `↑ ${mv}` : mv < 0 ? `↓ ${-mv}` : "—"}</td></tr>`;
    }).join("");
    return `<div class="tablewrap"><table class="cmp"><thead><tr><th class="num">on it</th><th>arm</th><th class="num">${esc(m)}</th><th class="num">on ${esc(oldRef || "—")}</th><th class="num">${esc(m)}</th><th>moves</th></tr></thead><tbody>${rows}</tbody></table></div>
      <p class="muted">On ${esc(newRef)}: ${orderLine(nw)}.${od ? ` On ${esc(oldRef)}: ${orderLine(od)}.` : ""}</p>
      ${nw.arms.some((a) => a.wrote_reference) ? '<p class="note">An arm that wrote the reference is scored against its own answers: read its rise, and its family\'s, before promoting it.</p>' : ""}`;
  }
  function screenReference(ds) {
    const head = `<div class="kicker">Prepare · ${esc(ds)} · its reference set</div><h1>Change the reference set</h1>
      <p class="lead">A different reference can reorder the arms. See what it moves before anything is promoted; re-scoring reads stored outputs, so it costs nothing.</p>`;
    if (!ds) return `<div class="screen">${head}<p class="note">Open it from a dataset's prepare screen.</p></div>`;
    const refs = load("references", "/references"), ls = load(`labelsets:${ds}`, `/datasets/${enc(ds)}/label-sets`), lb = load(`leaderboard:${ds}`, `/datasets/${enc(ds)}/leaderboard`), goals = load("goals", "/goals");
    if ([refs, ls, lb, goals].includes(undefined)) return `<div class="screen wide">${head}${loading("the reference sets")}</div>`;
    const bad = [refs, ls, goals].find((x) => x.error);
    if (bad) return `<div class="screen wide">${head}${failed(bad)}</div>`;
    const mine = refs.references.filter((r) => r.dataset === ds), sets = ls.label_sets.map((x) => String(x.set).split("/").pop());
    const scored = lb.error ? [] : ((lb.values || {}).groups || []).map((g) => g.reference);
    const st = WB._ref && WB._ref.ds === ds ? WB._ref : {};
    const against = st.against || (mine.find((r) => r.tier === "gold") || mine[0] || {}).reference || scored[0];
    const opt = (xs, sel) => xs.map((x) => `<option value="${esc(x)}" ${x === sel ? "selected" : ""}>${esc(x)}</option>`).join("");
    const readers = goals.goals.filter((g) => (g.datasets || []).some((d) => (d.dataset_id || d.dataset || d) === ds)).map((g) => g.goal);
    const sp = WB._sp && WB._sp.ds === ds ? WB._sp : {}, spGoal = sp.goal || readers[0];
    const rounds = spGoal ? load(`rounds:${spGoal}`, `/goals/${enc(spGoal)}/rounds`) : null;
    const roundIds = rounds && !rounds.error ? rounds.rounds.map((r) => r.round_id) : [];
    const agree = (ls.agreement || []).map((a) => `<li><span class="mono">${esc(a.a)}</span> and <span class="mono">${esc(a.b)}</span>: ${a.both} item(s) in both${a.kappa != null ? `, kappa ${fx(a.kappa)}` : ""}${a.alpha != null ? `, alpha ${fx(a.alpha)}` : ""} (${esc(a.kind || "")})</li>`).join("");
    const spView = sp.values ? Object.entries(sp.values.datasets || {}).map(([d, x]) => `<h3>${esc(d)} · ${esc(x.measure)}, now → with the scorer in this tree</h3>
      <div class="tablewrap"><table class="cmp"><thead><tr><th>arm</th><th class="num">now</th><th class="num">after</th><th class="num">moved</th><th>within the limits</th></tr></thead><tbody>${x.arms.map((a) => `<tr><td class="mono">${esc(a.arm)}</td><td class="num">${fx(a.now)}</td><td class="num">${fx(a.after)}</td><td class="num ${a.moved > 0 ? "v-lead" : a.moved < 0 ? "v-worse" : ""}">${a.moved > 0 ? "+" : ""}${a.moved.toFixed(4)}</td><td>${a.within_limits_now ? "yes" : "no"} → ${a.within_limits_after ? "yes" : "no"}</td></tr>`).join("")}</tbody></table></div>
      <p class="muted">leader ${esc(x.leader.now || "—")} → ${esc(x.leader.after || "—")} · recommended ${esc(x.recommended.now || "—")} → ${esc(x.recommended.after || "—")} · contenders ${x.contenders.now} → ${x.contenders.after}</p>`).join("")
      + `<p class="muted">${sp.values.rescored} run(s) re-scored in a temporary folder by scorer ${esc(sp.values.scorer)}; nothing written.</p>` : "";
    return `<div class="screen wide">${head}
      ${byField("rf6-by")}
      <section class="part"><div class="parthead"><span class="letter">a</span><h2>Its reference sets now</h2></div><div class="body">
        ${mine.length ? `<div class="tablewrap"><table><thead><tr><th>reference</th><th class="num">items</th><th>from</th><th>by</th><th>when</th><th class="num">arms scored</th></tr></thead><tbody>${mine.map((r) => `<tr><td class="mono"><span class="tag ${esc(r.tier)}">${esc(r.tier)}</span> ${esc(r.reference)}</td><td class="num">${r.items}</td><td class="mono">${esc(r.label_set || "—")} <span class="muted">${esc(r.kind || "")}${r.author ? ` · written by ${esc(r.author)}` : ""}</span></td><td>${esc(r.promoted_by || "")}</td><td>${esc((r.created_at || "").slice(0, 10))}</td><td class="num">${r.scored}</td></tr>`).join("")}</tbody></table></div>` : '<p class="muted">None yet: promote a label set below.</p>'}
        <h3>Its label sets</h3>${ls.label_sets.length ? `<ul>${ls.label_sets.map((x) => `<li><b class="mono">${esc(x.set)}</b> · ${x.items} item(s) · ${esc(x.kind)}${x.actor && x.actor.name ? ` · by ${esc(actorSaid(x.actor))}` : ""} · ${esc((x.created_at || "").slice(0, 10))}</li>`).join("")}</ul>` : '<p class="muted">None yet. <a href="#label/' + enc(ds) + '">Label it here</a>.</p>'}
        ${agree ? `<p class="muted" style="margin-bottom:4px">How often two sets agree:</p><ul>${agree}</ul>` : ""}</div></section>
      <section class="part"><div class="parthead"><span class="letter">b</span><h2>What it moves</h2></div><div class="body">
        ${sets.length ? `<div class="inline"><select id="mv-set" aria-label="the label set">${opt(sets, st.set)}</select>
          <span class="muted">compared with</span><select id="mv-against" aria-label="the reference it is compared with">${opt(scored, against)}</select>
          <button class="btn primary" type="button" id="mv-go">Score the arms against it ($0)</button></div>
          <div id="mv-out" data-out>${st.label ? movesView(lb, `labels/${ds}/${st.set}`, against) : ""}</div>` : '<p class="muted">No label set to compare yet.</p>'}</div></section>
      <section class="part"><div class="parthead"><span class="letter">c</span><h2>Promote it</h2></div><div class="body">
        ${sets.length ? `<div data-form="ref-promote"><div class="inline"><select id="rp6-set" aria-label="the label set">${opt(sets, st.set)}</select><select id="rp6-tier" aria-label="tier"><option value="gold">gold</option><option value="silver">silver</option></select>
          <input type="text" id="rp6-name" placeholder="its name: ${esc(ds)}" autocapitalize="off" spellcheck="false" aria-label="the reference set's name"></div>
          <input type="text" id="rp6-why" placeholder="why these answers are the yardstick: a sentence" aria-label="why it is promoted" style="width:100%;margin-top:8px">
          <div class="actions" style="margin-top:8px"><button class="btn primary" type="button" id="rp6-go" data-send>Promote</button>${mark}<span class="muted" style="font-size:13px">then the arms are re-scored against it: stored outputs, no calls, $0</span></div></div><div id="rp6-out" data-out></div>` : '<p class="muted">No label set to promote.</p>'}</div></section>
      <section class="part"><div class="parthead"><span class="letter">d</span><h2>When the scoring changes</h2></div><div class="body">
        <p class="muted">The scorer in this tree, run over a goal's stored outputs in a temporary folder: each arm now and after, and whether the leader, the recommendation or the contenders change. Nothing is written.</p>
        ${readers.length ? `<div class="inline"><select id="sp-goal" aria-label="the goal">${opt(readers, spGoal)}</select><select id="sp-round" aria-label="the round"><option value="">every arm</option>${opt(roundIds, sp.round)}</select>
          <button class="btn" type="button" id="sp-go">Preview the change</button></div><div id="sp-out" data-out>${spView}</div>
          ${roundIds.length ? `<div data-form="rescore-round"><h3>Apply it to a round</h3><div class="inline"><select id="rr-round" aria-label="the round">${opt(roundIds, sp.round)}</select>
            <input type="text" id="rr-why" placeholder="why the scoring changed, recorded on the round" style="min-width:20rem"><button class="btn primary" type="button" id="rr-go" data-send>Re-score the round</button>${mark}</div><div id="rr-out" data-out></div></div>` : ""}`
          : '<p class="muted">No goal reads this dataset.</p>'}</div></section>
      ${WB.cmd(`evh rescore --dataset-id ${ds} --labels <set>\nevh leaderboard ${ds}\nevh reference-promote --dataset-id ${ds} --labels <set> --tier gold --reason "..."\nevh rescore --dataset-id ${ds} --reference-id gold/${ds}\nevh score-preview --goal <goal>\nevh rescore --goal <goal> --round rN --why "..."`)}
      <div class="actions"><a class="btn" href="#prepare/${enc(ds)}">Back to prepare</a></div></div>`;
  }
  function wireReference() {
    const ds = WB.param || "";
    const v = (id) => (document.getElementById(id)?.value || "").trim();
    const by = () => byOf("rf6-by") || (who() ? `person:${who()}` : null);
    const needWho = (box) => { box.innerHTML = '<p class="note" role="alert">Say who you are above: a job names who asked.</p>'; };
    const reread = () => { forget(`leaderboard:${ds}`); forget("references"); forget(`labelsets:${ds}`); forget(`dataset:${ds}`); };
    document.getElementById("mv-against")?.addEventListener("change", () => { WB._ref = { ...(WB._ref || {}), ds, against: v("mv-against") }; WB.render(); });
    document.getElementById("mv-go")?.addEventListener("click", async (ev) => {
      const box = document.getElementById("mv-out"), who_ = by(), set = v("mv-set");
      if (!who_) return needWho(box);
      ev.target.disabled = true;
      try {
        const done = await runJob("/runs/rescore", { dataset_id: ds, labels: set, by: who_ }, box, "scoring the arms against it");
        if (done) {
          const label = ((((done.result || {}).result || {}).values || {}).labels || [])[0];
          WB._ref = { ds, set, label, against: v("mv-against") };
          forget(`leaderboard:${ds}`);
          WB.render(true);
        }
      } catch (e) { box.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    holds("ref-promote", () => `Promote ${v("rp6-set") || "…"} as ${v("rp6-tier")}/${v("rp6-name") || ds}`);
    document.getElementById("rp6-go")?.addEventListener("click", async (ev) => {
      const box = document.getElementById("rp6-out"), who_ = by(), tier = v("rp6-tier"), name = v("rp6-name") || ds;
      if (!who_) return needWho(box);
      ev.target.disabled = true;
      try {
        const inputs = { labels: v("rp6-set"), tier, reason: v("rp6-why"), by: who_ };
        if (v("rp6-name")) inputs.name = name;
        if (await runJob(`/datasets/${enc(ds)}/references`, inputs, box, "promoting")) {
          sent("ref-promote");
          const done = await runJob("/runs/rescore", { dataset_id: ds, reference_id: `${tier}/${name}`, by: who_ }, box, "re-scoring the arms against it");
          if (done) {
            reread();
            box.innerHTML = `<p class="note">Promoted <b>${esc(tier)}/${esc(name)}</b>; the arms re-scored against it.</p>${blocksView((done.result || {}).result)}`;
            const k = document.createElement("p");
            k.innerHTML = '<button class="btn" type="button">Show the reference sets</button>';
            k.querySelector("button").addEventListener("click", () => WB.render(true));
            box.appendChild(k);
          }
        }
      } catch (e) { box.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    document.getElementById("sp-goal")?.addEventListener("change", () => { WB._sp = { ds, goal: v("sp-goal") }; WB.render(); });
    document.getElementById("sp-go")?.addEventListener("click", async (ev) => {
      const box = document.getElementById("sp-out"), who_ = by(), goal = v("sp-goal"), round = v("sp-round");
      if (!who_) return needWho(box);
      ev.target.disabled = true;
      try {
        const done = await runJob(`/goals/${enc(goal)}/score-preview`, { ...(round ? { round } : {}), by: who_ }, box, "previewing the scoring");
        if (done) { WB._sp = { ds, goal, round, values: ((done.result || {}).result || {}).values }; WB.render(true); }
      } catch (e) { box.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    holds("rescore-round", () => `Re-score ${v("rr-round") || "…"}`);
    document.getElementById("rr-go")?.addEventListener("click", async (ev) => {
      const box = document.getElementById("rr-out"), who_ = by(), goal = v("sp-goal");
      if (!who_) return needWho(box);
      ev.target.disabled = true;
      try {
        const done = await runJob("/runs/rescore", { goal, round: v("rr-round"), why: v("rr-why"), by: who_ }, box, "re-scoring the round");
        if (done) { sent("rescore-round"); reread(); forget(`round:${goal}`); forget(`evidence:${goal}`); box.innerHTML = `<p class="note">Re-scored; the reason is kept on the round.</p>${blocksView((done.result || {}).result)}`; }
      } catch (e) { box.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
  }

  // ── W7: a judge (UXS-005 W7): its judges, how it judges, whether it agrees with people (as stored: validating stays a
  // tool, D6), the cost first (POST /estimate, the dry run), then the judging as a job under a cap, and what it cost ──
  const MODES = [["grade", "grade each"], ["pick", "pick the best of an item's outputs"], ["pairwise", "pick the better of two"]];
  const PROTO = [["protocol.outputs_per_call", "outputs per call", 16], ["protocol.position_check_fraction", "re-asked in another order (fraction)", 0.5], ["protocol.noise_check_fraction", "re-asked as is (fraction)", 0.5]];
  const dig = (o, key) => key.split(".").reduce((x, k) => (x == null ? undefined : x[k]), o);
  function screenJudge(goal) {
    const head = `<div class="kicker">Scoring · ${esc(goal)}</div><h1>A judge for this goal</h1>
      <p class="lead">A judge is a model that scores outputs the way a person would. It decides only once it agrees with people's labels on a set where both are known; until then every number it makes is labelled.</p>`;
    if (!goal) return `<div class="screen">${head}</div>`;
    const rec = load(`goalrec:${goal}`, `/goals/${enc(goal)}`), sc = load("scorers", "/scorers"), sys = load("systems", "/systems");
    if ([rec, sc, sys].includes(undefined)) return `<div class="screen wide">${head}${loading("the judges")}</div>`;
    const bad = [rec, sc, sys].find((x) => x.error);
    if (bad) return `<div class="screen wide">${head}${failed(bad)}</div>`;
    const dss = (rec.record.datasets || []).map((x) => x.dataset_id);
    const mine = sc.scorers.filter((x) => dss.includes(x.dataset)), others = sc.scorers.filter((x) => !dss.includes(x.dataset));
    const st = WB._judge && WB._judge.goal === goal ? WB._judge : {};
    const cur = st.scorer && sc.scorers.some((x) => x.scorer === st.scorer) ? st.scorer : (mine[0] || {}).scorer;
    const one = cur ? load(`scorer:${cur}`, `/scorers/${enc(cur)}`) : null;
    const opt = (xs, sel) => xs.map((x) => `<option value="${esc(x)}" ${x === sel ? "selected" : ""}>${esc(x)}</option>`).join("");
    const sysIds = sys.systems.map((x) => x.system), withModel = sys.systems.filter((x) => x.model).map((x) => x.system);
    const list = mine.length ? `<div class="tablewrap"><table><thead><tr><th>scorer</th><th>mode</th><th>dataset</th><th>judges</th><th>validated</th><th class="num">judged scores</th></tr></thead><tbody>${mine.map((x) => `<tr><td class="mono"><a href="#judge/${enc(goal)}" data-scorer="${esc(x.scorer)}">${esc(x.scorer)}</a>${x.scorer === cur ? ' <span class="tag new">shown</span>' : ""}</td><td>${esc(x.mode)}</td><td class="mono">${esc(x.dataset)}</td>
      <td>${x.judges.map((j) => `<span class="mono">${esc(j.judge)}</span> <span class="muted">${esc(j.model || j.system || "")} · ${esc(j.family || "no family")}</span>`).join("<br>")}</td><td>${x.validated ? '<span class="status ok">yes</span>' : '<span class="status">no</span>'}</td><td class="num">${x.judged_scores}</td></tr>${x.problem ? `<tr><td colspan="6"><p class="note" role="alert" style="margin:0">${esc(x.problem)}</p></td></tr>` : ""}`).join("")}</tbody></table></div>`
      : `<p class="muted">No judge scorer for ${dss.map(esc).join(", ") || "this goal's datasets"} yet.${others.length ? ` The project has ${others.length} for other datasets.` : ""}</p>`;
    const base = st.supersedes ? ((LIVE.cache[`scorer:${st.supersedes}`] || {}).record || {}) : {};
    const baseSys = (base.judges || []).filter((j) => j.system).map((j) => j.system);
    const kept = (base.judges || []).map((j, i) => [j, i]).filter(([j]) => !j.system).map(([j, i]) => `<label class="choice"><input type="checkbox" name="jn-keep" value="${i}" checked> <span class="mono">${esc(j.id)}</span> <small class="muted">${esc((j.params || {}).model || "")} · ${esc((j.params || {}).family || "no family")}, as it is</small></label>`).join("");
    const judgesPick = kept + sysIds.map((x) => `<label class="choice"><input type="checkbox" name="jn-judge" value="${esc(x)}" ${baseSys.includes(x) ? "checked" : ""}> <span class="mono">${esc(x)}</span>${withModel.includes(x) ? "" : ' <small class="muted">(names no model)</small>'}</label>`).join("");
    const newForm = `<details class="part" ${mine.length ? "" : "open"}><summary><b>Make a judge scorer</b></summary><div class="body" data-form="scorer-new">
        <div class="field"><label class="name" for="jn-id">Its id</label><div><input type="text" id="jn-id" value="${esc(st.supersedes ? `${st.supersedes}-v2` : "")}" placeholder="${esc(goal)}-judge-v1" autocapitalize="off" spellcheck="false">${st.supersedes ? `<div class="hint">a new version of ${esc(st.supersedes)}, which has judged and is kept as it is</div>` : ""}</div></div>
        <div class="field"><label class="name" for="jn-ds">On</label><div><select id="jn-ds">${opt(dss)}</select></div></div>
        <div class="field"><div class="name">How it judges</div><div class="choices row">${MODES.map(([m, t]) => `<label class="choice"><input type="radio" name="jn-mode" value="${m}" ${(base.mode || "grade") === m ? "checked" : ""}> ${esc(t)}</label>`).join("")}</div></div>
        <div class="field"><div class="name">Its reasons</div><div><label class="choice"><input type="checkbox" id="jn-explain" ${base.explain === false ? "" : "checked"}> each judge says why, inside its verdict</label><div class="hint">a short reason per output, read below; it costs output tokens, not calls. A judge asked for reasons is validated with them.</div></div></div>
        <div class="field"><div class="name">Its judges</div><div><div class="choices">${judgesPick || '<p class="muted">No system yet: <a href="#models">bring in a model</a> and make a system of it.</p>'}</div><div class="hint">two families at least, so one vendor's taste does not decide: each judge is called, priced and fingerprinted as its system is</div></div></div>
        <div class="field"><label class="name" for="jn-prompt">The prompt</label><div><input type="text" id="jn-prompt" value="${esc(dig(base, "prompt.file") || "")}" placeholder="prompts/judge.txt: a file in the project" autocapitalize="off" spellcheck="false"><div class="hint">a file in the project, relative to data/scorers/ or the project; {n} becomes the number of outputs in a call</div></div></div>
        ${PROTO.map(([k, t, d]) => `<div class="field"><label class="name" for="jn-${k.split(".").pop()}">${esc(t)}</label><div><input type="number" id="jn-${k.split(".").pop()}" value="${esc(dig(base, k) ?? d)}" step="any" min="0" style="width:8rem"></div></div>`).join("")}
        <div class="field"><label class="name" for="jn-cap">At most (USD)</label><div><input type="number" id="jn-cap" value="${esc(base.cost_cap_usd ?? 1)}" step="0.01" min="0" style="width:8rem"><div class="hint">for one whole judging pass</div></div></div>
        <div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="jn-go" data-send>Make it</button>${mark}</div><div id="jn-out" data-out></div></div></details>`;
    let shown = "";
    if (cur && one === undefined) shown = loading("the scorer");
    else if (one && one.error) shown = failed(one);
    else if (one) {
      const r = one.record || {}, va = one.validation || {}, b = va.block || {};
      const editable = !one.judged_scores;
      const guards = `${dig(r, "protocol.outputs_per_call")} output(s) per call · arms ${dig(r, "protocol.blinding") === false ? "named" : "hidden"} · ${Math.round((dig(r, "protocol.position_check_fraction") || 0) * 100)}% re-asked in another order · ${Math.round((dig(r, "protocol.noise_check_fraction") || 0) * 100)}% re-asked as is`;
      const edit = editable ? `<div data-form="scorer-set"><div class="choices row">${MODES.map(([m, t]) => `<label class="choice"><input type="radio" name="ss-mode" value="${m}" ${(r.mode || "grade") === m ? "checked" : ""}> ${esc(t)}</label>`).join("")}</div>
          <div class="inline"><label>the prompt <input type="text" id="ss-prompt" value="${esc(dig(r, "prompt.file") || "")}" autocapitalize="off" spellcheck="false"></label>
          ${PROTO.map(([k, t]) => `<label>${esc(t)} <input type="number" id="ss-${k.split(".").pop()}" value="${esc(dig(r, k) ?? "")}" step="any" min="0" style="width:6rem"></label>`).join("")}
          <label>at most (USD) <input type="number" id="ss-cap" value="${esc(r.cost_cap_usd ?? "")}" step="0.01" min="0" style="width:6rem"></label></div>
          <div class="actions" style="margin-top:0"><button class="btn" type="button" id="ss-go" data-send>Save</button>${mark}</div><div id="ss-out" data-out></div></div>`
        : `<p class="note">It has made ${one.judged_scores} judged score(s), so it stays as it judged. <button class="btn" type="button" id="ss-new">Make a new version of it</button></p>`;
      const valRows = (b.runs || []).map((x) => `<tr><td class="mono">${esc(x.judge)}</td><td class="num">${fx(x.value)}</td><td class="num">${fx(x.min_metric ?? b.min_metric)}</td><td class="mono">${esc(x.run)}</td></tr>`).join("");
      const checks = (one.checks || []).map((c) => `<li>${esc(typeof c === "string" ? c : JSON.stringify(c))}</li>`).join("");
      shown = `<section class="part"><div class="parthead"><span class="letter">b</span><h2>How ${esc(cur)} judges</h2></div><div class="body">
          <p><b>${esc((MODES.find(([m]) => m === (r.mode || "grade")) || [])[1] || r.mode)}</b> · ${r.explain === true ? "each judge says why" : "no reasons asked"} · on <span class="mono">${esc(r.dataset_id)}</span> · the prompt <span class="mono">${esc(dig(r, "prompt.file") || "—")}</span> · at most $${esc(r.cost_cap_usd ?? "—")} a pass</p>
          <p class="muted">${guards}</p>
          <div class="tablewrap"><table><thead><tr><th>judge</th><th>model or system</th><th>family</th></tr></thead><tbody>${(one.judges || []).map((j) => `<tr><td class="mono">${esc(j.judge)}</td><td class="mono">${esc(j.model || j.system || "")}</td><td>${esc(j.family || "—")}</td></tr>`).join("")}</tbody></table></div>
          ${one.problem ? `<p class="note" role="alert">${esc(one.problem)}</p>` : ""}${edit}</div></section>
        <section class="part"><div class="parthead"><span class="letter">c</span><h2>Does it agree with people?</h2><span class="grow"></span>${va.validated ? '<span class="status ok">validated</span>' : '<span class="status">not validated</span>'}</div><div class="body">
          ${valRows ? `<p class="muted">${esc(b.what || "")}${b.metric ? ` · ${esc(b.metric)} on ${esc(b.dataset_id)}` : ""}${b.differs_from_this_use ? ` · differs from this use: ${esc(b.differs_from_this_use)}` : ""}</p>
            <div class="tablewrap"><table><thead><tr><th>judge</th><th class="num">${esc(b.metric || "agreement")}</th><th class="num">it must beat</th><th>measured by</th></tr></thead><tbody>${valRows}</tbody></table></div>` : '<p class="muted">No validation recorded: nothing measured these judges against people\'s labels.</p>'}
          ${(va.problems || []).length ? `<ul class="problems">${va.problems.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
          ${checks ? `<p class="muted" style="margin-bottom:4px">People's checks of its judges:</p><ul>${checks}</ul>` : ""}
          <p class="muted">Shown as stored. Measuring it is a tool, not this screen: <code>tools/validate_judge_*.py</code> writes the runs a validation names.</p>
          ${(one.judging_sets || []).some((j) => j.verdicts) ? chartBox("agreement", { scorer: cur }, true) : ""}</div></section>
        <section class="part"><div class="parthead"><span class="letter">d</span><h2>Score the arms with it</h2></div><div class="body" data-form="judge-run">
          <div class="inline"><select id="js-ds" aria-label="the dataset">${opt(dss, r.dataset_id)}</select>
            <input type="text" id="js-arms" placeholder="only these arms: a,b (optional)" autocapitalize="off" spellcheck="false">
            <label>at most (USD) <input type="number" id="js-cap" value="${esc(r.cost_cap_usd ?? 1)}" step="0.01" min="0.01" inputmode="decimal" style="width:6rem"></label>
            ${va.validated ? "" : '<label class="choice"><input type="checkbox" id="js-unval"> run it unvalidated, every number labelled so</label>'}</div>
          <div class="actions" style="margin-top:0"><button class="btn" type="button" id="js-est">The cost first (a dry run)</button><button class="btn primary" type="button" id="js-go" data-send>Judge the arms</button>${mark}</div>
          <div id="js-out" data-out></div>
          ${(one.judging_sets || []).length ? `<p class="muted" style="margin-bottom:4px">What it judged:</p><ul>${one.judging_sets.map((j) => `<li><span class="mono">${esc(j.set)}</span> · ${j.arms} arm(s) · ${j.items} item(s) · ${j.verdicts} verdict(s)${j.summary ? ` · ${esc(j.summary.label || "")}${j.summary.current ? "" : " · made by an older version of the scorer"}` : ""}</li>`).join("")}</ul>
            <p class="muted">Read as <span class="mono">judged/${esc(cur)}</span> on the leaderboard.</p>` : ""}</div></section>
        ${(one.judging_sets || []).some((j) => j.verdicts) ? whySection(cur, st.whyOffset || 0) : ""}`;
    }
    return `<div class="screen wide">${head}<span id="jd-cur" data-cur="${esc(cur || "")}" hidden></span>
      ${byField("jd-by")}
      <section class="part"><div class="parthead"><span class="letter">a</span><h2>Its judge scorers</h2></div><div class="body">${list}${newForm}</div></section>
      ${shown}
      <section class="part"><div class="parthead"><span class="letter">f</span><h2>What it cost</h2></div><div class="body">
        <p class="muted">The billed cost of each arm, and what judging cost, from the runs and the judges' verdicts.</p>
        <div class="inline"><select id="cr-ds" aria-label="the dataset">${opt(dss)}</select><button class="btn" type="button" id="cr-go">Show the costs</button></div><div id="cr-out" data-out></div></div></section>
      ${WB.cmd(`evh scorer-list\nevh scorer-new <id> --set dataset_id=... --set judges.0.system=... --set prompt.file=...\nevh judge-score --dataset-id <d> --scorer ${cur || "<id>"} --dry-run\nevh judge-score --dataset-id <d> --scorer ${cur || "<id>"}\nevh cost-report --dataset-id <d>`)}
      <div class="actions"><a class="btn" href="#eval/${enc(goal)}">The eval</a><a class="btn" href="#goal/${enc(goal)}">Back to the goal</a></div></div>`;
  }
  // What the judges said and why (RFC-034 §5), the lowest scores first: what failed, and the judge's reason for it.
  function whySection(cur, offset) {
    const r = load(`verdicts:${cur}:${offset}`, `/scorers/${enc(cur)}/verdicts?limit=10&offset=${offset}`);
    const body = r === undefined ? loading("the verdicts") : r.error ? failed(r) : !r.rows.length ? '<p class="muted">No verdicts on the primary pass.</p>'
      : `<p class="muted">${r.offset + 1}–${r.offset + r.rows.length} of ${r.total} · ${r.explained} with a reason · the lowest scores first</p>
        <div class="tablewrap"><table class="why"><thead><tr><th>item</th><th>arm</th><th>judge</th><th class="num">said</th><th>why</th></tr></thead><tbody>${r.rows.map((x) => `<tr><td class="mono">${esc(x.item)}</td><td class="mono">${esc(x.arm)}</td><td class="mono">${esc(x.judge)}</td><td class="num">${typeof x.said === "number" ? fx(x.said) : esc(x.said ?? "—")}</td><td>${x.why ? esc(x.why) : `<span class="muted">${esc(x.why_status === "withheld" ? "withheld: it repeated the source" : x.why_status === "missing" ? "missing" : "not asked")}</span>`}</td></tr>`).join("")}</tbody></table></div>
        <div class="actions" style="margin-top:0">${r.offset > 0 ? '<button class="btn" type="button" id="why-prev">Lower</button>' : ""}${r.offset + r.rows.length < r.total ? '<button class="btn" type="button" id="why-next">Higher</button>' : ""}</div>`;
    return `<section class="part" id="why"><div class="parthead"><span class="letter">e</span><h2>What it said, and why</h2></div><div class="body">${body}
      ${WB.cmd(`evh judge-verdicts ${cur}`)}</div></section>`;
  }
  function wireJudge() {
    const goal = WB.param || "";
    const v = (id) => (document.getElementById(id)?.value || "").trim();
    const by = () => byOf("jd-by") || (who() ? `person:${who()}` : null);
    const needWho = (box) => { box.innerHTML = '<p class="note" role="alert">Say who you are above: a change names who made it.</p>'; };
    const st = () => (WB._judge && WB._judge.goal === goal ? WB._judge : (WB._judge = { goal }));
    const cur = () => document.getElementById("jd-cur")?.dataset.cur || "";
    document.querySelectorAll("[data-scorer]").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); st().scorer = a.dataset.scorer; WB.render(); }));
    const num = (id) => (v(id) === "" ? undefined : Number(v(id)));
    holds("scorer-new", () => `Make ${v("jn-id") || "…"}`);
    document.getElementById("jn-go")?.addEventListener("click", async (ev) => {
      const box = document.getElementById("jn-out"), who_ = by(), id = v("jn-id");
      if (!who_) return needWho(box);
      const judges = [...document.querySelectorAll("input[name=jn-judge]:checked")].map((x) => x.value);
      const set = { dataset_id: v("jn-ds"), mode: document.querySelector("input[name=jn-mode]:checked")?.value || "grade", explain: !!document.getElementById("jn-explain")?.checked, cost_cap_usd: num("jn-cap"), "protocol.blinding": true };
      const old = st().supersedes ? ((LIVE.cache[`scorer:${st().supersedes}`] || {}).record || {}).judges || [] : [];
      const keep = [...document.querySelectorAll("input[name=jn-keep]:checked")].map((x) => old[Number(x.value)]).filter(Boolean);
      keep.forEach((j, i) => { set[`judges.${i}.id`] = j.id; set[`judges.${i}.params`] = j.params; });
      judges.forEach((j, i) => { set[`judges.${keep.length + i}.id`] = j; set[`judges.${keep.length + i}.system`] = j; });
      if (v("jn-prompt")) set["prompt.file"] = v("jn-prompt");
      for (const [k] of PROTO) set[k] = num(`jn-${k.split(".").pop()}`);
      if (st().supersedes) set.supersedes = st().supersedes;
      ev.target.disabled = true;
      try {
        await send("POST", `/scorers/${enc(id)}`, { set, by: who_ });
        sent("scorer-new"); forget("scorers"); forget(`scorer:${id}`);
        WB._judge = { goal, scorer: id };
        WB.render(true);
      } catch (e) { box.innerHTML = refusal(e); ev.target.disabled = false; }
    });
    const page = (d) => { st().whyOffset = Math.max(0, (st().whyOffset || 0) + d); WB.render(); };
    document.getElementById("why-next")?.addEventListener("click", () => page(10));
    document.getElementById("why-prev")?.addEventListener("click", () => page(-10));
    document.getElementById("ss-new")?.addEventListener("click", () => { st().supersedes = cur(); WB.render(); document.getElementById("jn-id")?.closest("details")?.setAttribute("open", ""); });
    holds("scorer-set", () => `Save ${cur()}`);
    document.getElementById("ss-go")?.addEventListener("click", async (ev) => {
      const box = document.getElementById("ss-out"), who_ = by(), id = cur();
      if (!who_) return needWho(box);
      const rec = ((LIVE.cache[`scorer:${id}`] || {}).record) || {};
      const want = { mode: document.querySelector("input[name=ss-mode]:checked")?.value, "prompt.file": v("ss-prompt"), cost_cap_usd: num("ss-cap") };
      for (const [k] of PROTO) want[k] = num(`ss-${k.split(".").pop()}`);
      const set = Object.fromEntries(Object.entries(want).filter(([k, x]) => x !== undefined && x !== "" && JSON.stringify(dig(rec, k) ?? (k === "mode" ? "grade" : undefined)) !== JSON.stringify(x)));
      if (!Object.keys(set).length) { sent("scorer-set"); WB.render(); return; }
      ev.target.disabled = true;
      try { await send("PATCH", `/scorers/${enc(id)}`, { set, by: who_ }); sent("scorer-set"); forget("scorers"); forget(`scorer:${id}`); WB.render(true); }
      catch (e) { box.innerHTML = refusal(e); ev.target.disabled = false; }
    });
    const judgeInputs = () => {
      const i = { dataset_id: v("js-ds") };
      if (v("js-arms")) i.arms = v("js-arms");
      if (document.getElementById("js-unval")?.checked) i.unvalidated = true;
      return i;
    };
    document.getElementById("js-est")?.addEventListener("click", async (ev) => {
      const box = document.getElementById("js-out");
      box.innerHTML = '<p class="muted">costing it…</p>';
      ev.target.disabled = true;
      const r = await fetch("/api/v1/estimate", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-EVH-Data": "1" }, body: JSON.stringify({ operation: "judge-score", inputs: { scorer: cur(), ...judgeInputs() } }) });
      const b = await r.json().catch(() => ({}));
      box.innerHTML = r.ok ? blocksView(b.result) : `<p class="note" role="alert">${esc(b.error || b.text || r.status)}</p>`;
      ev.target.disabled = false;
    });
    holds("judge-run", () => `Judge with ${cur()}`);
    document.getElementById("js-go")?.addEventListener("click", async (ev) => {
      const box = document.getElementById("js-out"), who_ = by(), cap = Number(v("js-cap"));
      if (!who_) return needWho(box);
      if (!(cap > 0)) { box.innerHTML = '<p class="note" role="alert">Say the most it may spend first.</p>'; return; }
      ev.target.disabled = true;
      try {
        const done = await runJob(`/scorers/${enc(cur())}/judge`, { ...judgeInputs(), by: who_, max_cost_usd: cap }, box, "judging");
        if (done) { sent("judge-run"); forget(`scorer:${cur()}`); forget("scorers"); forget(`verdicts:${cur()}:`); forget("chart:"); box.innerHTML = `<p class="note">Judged.</p>${blocksView((done.result || {}).result)}`; }
      } catch (e) { box.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    document.getElementById("cr-go")?.addEventListener("click", async (ev) => {
      const box = document.getElementById("cr-out"), who_ = by();
      if (!who_) return needWho(box);
      ev.target.disabled = true;
      try {
        const done = await runJob("/reports/cost", { dataset_id: v("cr-ds"), by: who_ }, box, "reading the costs");
        if (done) box.innerHTML = blocksView((done.result || {}).result);
      } catch (e) { box.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
  }

  // ── W8: settings (UXS-005 W8): rare, so terse; one row each, with its command. config.yaml is not edited here (D9) ──
  const SETTING_FILES = [["validate.json", "Committed runs and their floors", "which run folders the checks hold to their numbers"], ["goals/policy.yaml", "The goal policy", "what every goal must have before a round closes"]];
  const b64 = (text) => btoa(unescape(encodeURIComponent(text)));
  function screenSettings() {
    const head = `<div class="kicker">Settings</div><h1>Govern and maintain</h1>
      <p class="lead">Rare, so terse: each row is one form, and the command that does the same.</p>`;
    const ov = load("data-ls", "/data"), ds = load("datasets", "/datasets");
    if (ov === undefined || ds === undefined) return `<div class="screen wide">${head}${loading("the project")}</div>`;
    if (ov.error) return `<div class="screen wide">${head}${failed(ov)}</div>`;
    const o = ov.overview || {}, other = o.store === "sqlite" ? "files" : "sqlite";
    const where = o.store === "sqlite" ? `one database, <span class="mono">${esc(o.database || "data/project.sqlite")}</span>${o.database_bytes != null ? `, ${o.database_bytes.toLocaleString()} bytes` : ", not made yet"}` : "every run, label and score a file under data/, kept in git";
    const st = WB._settings || {}, path = st.path || SETTING_FILES[0][0];
    const file = load(`data-file:${path}`, `/data/file?path=${enc(path)}`);
    const text = file === undefined ? null : file.error ? "" : ((file.file || {}).text ?? "");
    const row = (n, title, why, body, cmd) => `<section class="part"><div class="parthead"><span class="letter">${n}</span><h2>${esc(title)}</h2></div><div class="body">
        <p class="muted">${why}</p>${body}${WB.cmd(cmd)}</div></section>`;
    const opt = (xs, sel) => xs.map((x) => `<option value="${esc(x)}" ${x === sel ? "selected" : ""}>${esc(x)}</option>`).join("");
    return `<div class="screen wide">${head}
      ${byField("st-by")}
      ${row(1, "Where the project keeps its data", `config.yaml names <b>${esc(o.store || "?")}</b>: ${where}. The data moves into the store config.yaml names, keeping everything; while it moves the server answers every call with “wait” (503). To move it to ${other}, set <code>store: ${other}</code> in config.yaml first (it is not edited here), then come back.`,
        `<div class="actions" style="margin-top:0"><button class="btn" type="button" id="mv-dry">Count what would move into ${esc(o.store)}</button><button class="btn primary" type="button" id="mv-run" disabled>Move it</button></div><div id="mv-st-out" data-out></div>`,
        `evh data-migrate --to ${o.store} --dry-run\nevh data-migrate --to ${o.store}`)}
      ${row(2, "Bring the data to this release's formats", "After upgrading the harness: runs, datasets, records and fingerprints, once; a second run changes nothing.",
        `<div class="actions" style="margin-top:0"><button class="btn" type="button" id="mg-check">Compare the formats</button><button class="btn" type="button" id="mg-dry">What it would change</button><button class="btn primary" type="button" id="mg-run">Migrate</button></div><div id="mg-out" data-out></div>`,
        "evh migrate --check\nevh migrate --dry-run\nevh migrate")}
      ${row(3, "Check the project", "The integrity checks over every dataset, run, reference and scorer; each exists because its absence let a real defect through. It reads everything: about half a minute on a large project.",
        `<div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="vd-go">Check it</button></div><div id="vd-out" data-out></div>`,
        "evh validate")}
      ${row(4, "Its policies", "Two settings files under data/, checked before they are saved.",
        `<div class="inline"><select id="sf-path" aria-label="the setting">${SETTING_FILES.map(([f, t]) => `<option value="${esc(f)}" ${f === path ? "selected" : ""}>${esc(t)} · ${esc(f)}</option>`).join("")}</select></div>
          <p class="muted">${esc((SETTING_FILES.find(([f]) => f === path) || [])[2] || "")}${file && file.error ? " · not made yet: saving makes it" : ""}</p>
          ${text === null ? loading("the file") : `<div data-form="setting-file"><textarea id="sf-text" rows="8" style="width:100%" class="mono" aria-label="its text" spellcheck="false">${esc(text)}</textarea>
          <div class="actions" style="margin-top:0"><button class="btn" type="button" id="sf-check">Check it</button><button class="btn primary" type="button" id="sf-save" data-send>Save</button>${mark}</div></div><div id="sf-out" data-out></div>`}`,
        `evh data-show ${path}\nevh data-put --path ${path} --file - --check\nevh data-put --path ${path} --file -`)}
      ${row(5, "Budgets", "A round's spending cap is set when the round opens, and checked before a run starts; a job that spends carries its own cap.",
        '<p class="muted" style="margin:0">Open a round from a goal\'s eval.</p>', "evh round-open <goal> --budget-usd 5 ...")}
      ${row(6, "Publish a dataset", "To a new Hugging Face repo: private first, read back and checked by sha256. Needs a token with write access on this machine.",
        ds.error ? failed(ds) : `<div class="inline" data-form="publish"><select id="pb-ds" aria-label="the dataset">${opt(ds.datasets.map((x) => x.dataset))}</select>
          <input type="text" id="pb-repo" placeholder="owner/name" autocapitalize="off" spellcheck="false" aria-label="the repo"><button class="btn" type="button" id="pb-go" data-send>Publish</button>${mark}</div><div id="pb-out" data-out></div>`,
        `evh dataset-publish --dataset-id <id> --to huggingface --query '{"repo": "owner/name"}'`)}
      <div class="actions"><a class="btn" href="#home">Your goals</a></div></div>`;
  }
  function wireSettings() {
    const v = (id) => (document.getElementById(id)?.value || "").trim();
    const by = () => byOf("st-by") || (who() ? `person:${who()}` : null);
    const needWho = (box) => { box.innerHTML = '<p class="note" role="alert">Say who you are above: a job names who asked.</p>'; };
    const job = (btn, out, path, body, what, after) => document.getElementById(btn)?.addEventListener("click", async (ev) => {
      const box = document.getElementById(out), who_ = by();
      if (!who_) return needWho(box);
      ev.target.disabled = true;
      try {
        const done = await runJob(typeof path === "function" ? path() : path, { ...body(), by: who_ }, box, what);
        if (done) { box.innerHTML = blocksView((done.result || {}).result); if (after) after(box, done); }
      } catch (e) { box.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    // the move goes into the store config.yaml names; it is offered once its dry run has counted something to move
    const to = ((LIVE.cache["data-ls"] || {}).overview || {}).store;
    job("mv-dry", "mv-st-out", "/project/store/move", () => ({ to, dry_run: true }), "counting", (box, done) => {
      const n = (((done.result || {}).result || {}).values) || {};
      const some = (n.files || 0) + (n.rows || 0) + (n.outputs || 0) > 0;
      document.getElementById("mv-run").disabled = !some;
      if (!some) box.insertAdjacentHTML("beforeend", `<p class="muted">Nothing to move: the data is in ${esc(to)} already.</p>`);
    });
    job("mv-run", "mv-st-out", "/project/store/move", () => ({ to }), "moving the data", (box) => {
      forget("data-ls");
      box.insertAdjacentHTML("beforeend", '<p class="note">Moved. <button class="btn" type="button" data-again>Read it again</button></p>');
      box.querySelector("[data-again]").addEventListener("click", () => WB.render(true));
    });
    job("mg-check", "mg-out", "/project/migrate", () => ({ check: true }), "comparing");
    job("mg-dry", "mg-out", "/project/migrate", () => ({ dry_run: true }), "looking");
    job("mg-run", "mg-out", "/project/migrate", () => ({}), "migrating");
    document.getElementById("vd-go")?.addEventListener("click", async (ev) => {
      const box = document.getElementById("vd-out");
      ev.target.disabled = true;
      box.innerHTML = '<p class="muted" aria-live="polite">checking… (it reads everything)</p>';
      const r = await fetch("/api/v1/validate", { credentials: "same-origin" }).catch(() => null);
      const b = r ? await r.json().catch(() => ({})) : {};
      const lines = (((b.result || {}).blocks) || []).flatMap((x) => x.lines || []);
      const bad = lines.filter((x) => /^\s*FAIL\b/.test(x));
      box.innerHTML = r && r.ok ? `<p class="${bad.length ? "note" : "muted"}" ${bad.length ? 'role="alert"' : ""}>${bad.length ? `${bad.length} check(s) failed:` : "Every check passed."}</p>${bad.length ? `<ul>${bad.map((x) => `<li class="mono">${esc(x.trim())}</li>`).join("")}</ul>` : ""}<details><summary>Every check</summary>${blocksView(b.result)}</details>`
        : `<p class="note" role="alert">${esc(b.error || (r ? r.status : "no answer"))}</p>`;
      ev.target.disabled = false;
    });
    document.getElementById("sf-path")?.addEventListener("change", () => { WB._settings = { path: v("sf-path") }; WB.render(); });
    const path = () => v("sf-path"), exists = () => !((LIVE.cache[`data-file:${path()}`] || {}).error);
    holds("setting-file", () => `Save ${path()}`);
    const put = (check) => async (ev) => {
      const box = document.getElementById("sf-out"), who_ = by();
      if (!who_) return needWho(box);
      ev.target.disabled = true;
      try {
        const body = { path: path(), file: { name: path().split("/").pop(), content_base64: b64(document.getElementById("sf-text").value) }, by: who_ };
        if (check) body.check = true;
        else if (!exists()) body.new = true;
        // a file with problems ends the job (exit 1) with each problem printed on its line, not as an ERROR: shown whole
        const j = await send("POST", "/data/file", body);
        const done = await watchJob(j.id, box, check ? "checking" : "saving");
        if (done.state === "succeeded") {
          box.innerHTML = `<p class="note">${check ? "It passes the check" : "Saved"}.</p>${blocksView((done.result || {}).result)}`;
          if (!check) { sent("setting-file"); forget(`data-file:${path()}`); }
        } else {
          const log = ((await fetch(`/api/v1/jobs/${enc(j.id)}/log`, { credentials: "same-origin" }).then((x) => x.json()).catch(() => ({}))).log || "");
          const said = log.split("\n").filter((x) => x.trim() && !x.startsWith("[")).slice(-12).join("\n");
          box.innerHTML = `<p class="note" role="alert"><b>${check ? "It does not pass" : "Not saved"}.</b></p><pre class="reply">${esc(said)}</pre>`;
        }
      } catch (e) { box.innerHTML = refusal(e); }
      ev.target.disabled = false;
    };
    document.getElementById("sf-check")?.addEventListener("click", put(true));
    document.getElementById("sf-save")?.addEventListener("click", put(false));
    holds("publish", () => `Publish ${v("pb-ds") || "…"} to ${v("pb-repo") || "…"}`);
    job("pb-go", "pb-out", () => `/datasets/${enc(v("pb-ds"))}/publish`, () => ({ to: "huggingface", query: JSON.stringify({ repo: v("pb-repo") }) }), "publishing", () => sent("publish"));
  }

  // ── the jobs (UXS-005, Jobs; RFC-026): every job, filtered by state, operation and goal, a page at a time; one job's
  // record, progress, result, files and log, followed while it runs; stopped, and a stopped run resumed ──
  const RUNNING = ["queued", "running", "running (unsupervised)"];
  const STATE_SETS = [["", "every state"], ["queued,running,running (unsupervised)", "running or waiting"], ["succeeded", "succeeded"], ["failed", "failed"], ["cancelled", "stopped"], ["lost", "lost"]];
  const PAGE = 50;
  const stateTagOf = (st) => `<span class="verdict ${st === "succeeded" ? "v-lead" : RUNNING.includes(st) ? "v-ns" : "v-worse"}">${esc(st)}</span>`;
  const progressOf = (p) => (p ? `${p.done ?? p.n ?? "?"} / ${p.total ?? "?"}${p.unit ? ` ${esc(p.unit)}` : ""}` : "—");
  function screenJobs(param) {
    const id = String(param || "");
    if (id) return screenJob(id);
    const f = WB._jobsF || { state: "", operation: "", goal: "", offset: 0 };
    const q = new URLSearchParams();
    if (f.state) q.set("state", f.state);
    if (f.operation) q.set("operation", f.operation);
    if (f.goal) q.set("goal", f.goal);
    q.set("offset", String(f.offset || 0));
    q.set("limit", String(PAGE));
    const head = `<div class="kicker">Jobs</div><h1>Jobs</h1>
      <p class="lead">Every step that runs is a job: its cost first, then its progress and log, then its result. A job keeps running when the page closes; it can be watched again, stopped, and a stopped run resumed with what it left of its cap.</p>`;
    const js = load(`jobs:${q}`, `/jobs?${q}`, true), goals = load("goals", "/goals");
    if (js === undefined || goals === undefined) return `<div class="screen wide">${head}${loading("the jobs")}</div>`;
    if (js.error) return `<div class="screen wide">${head}${failed(js)}</div>`;
    const ops = [...new Set(js.jobs.map((j) => j.operation).concat(f.operation ? [f.operation] : []))].sort();
    const goalIds = goals.error ? [] : goals.goals.map((g) => g.goal);
    const opt = (xs, sel, none) => `<option value="">${esc(none)}</option>` + xs.map((x) => `<option value="${esc(x)}" ${x === sel ? "selected" : ""}>${esc(x)}</option>`).join("");
    const from = (f.offset || 0) + 1, to = (f.offset || 0) + js.jobs.length;
    const rows = js.jobs.map((j) => `<tr><td class="mono"><a href="#jobs/${enc(j.id)}">${esc(j.id)}</a></td><td class="mono">${esc(j.operation)}</td><td>${stateTagOf(j.state)}${j.waiting_for ? ` <small class="muted">waits for ${esc(j.waiting_for)}</small>` : ""}</td>
      <td class="mono">${esc(j.by || "")}</td><td class="num">${esc((j.created_at || "").replace("T", " ").slice(0, 16))}</td><td class="num">${progressOf(j.progress)}</td><td class="num">${j.spent_usd ? `$${Number(j.spent_usd).toFixed(4)}` : "—"}</td></tr>`).join("");
    return `<div class="screen wide">${head}
      <div class="inline"><select id="jf-state" aria-label="state">${STATE_SETS.map(([v, t]) => `<option value="${esc(v)}" ${v === f.state ? "selected" : ""}>${esc(t)}</option>`).join("")}</select>
        <select id="jf-op" aria-label="operation">${opt(ops, f.operation, "every operation")}</select><select id="jf-goal" aria-label="goal">${opt(goalIds, f.goal, "every goal")}</select></div>
      ${js.jobs.length ? `<div class="tablewrap" style="margin-top:12px"><table><thead><tr><th>job</th><th>operation</th><th>state</th><th>who</th><th class="num">made</th><th class="num">progress</th><th class="num">spent</th></tr></thead><tbody>${rows}</tbody></table></div>
        <p class="muted">${from}–${to} of ${js.total}</p>` : '<p class="muted">No job like that.</p>'}
      <div class="actions">${f.offset ? '<button class="btn" type="button" id="jf-prev">Newer</button>' : ""}${to < js.total ? '<button class="btn" type="button" id="jf-next">Older</button>' : ""}<a class="btn" href="#home">Your goals</a></div>
      ${WB.cmd("evh jobs-status [--state running] [--operation run] [--goal <goal>]\nevh jobs-status <job>\nevh jobs-logs <job> --follow\nevh jobs-stop <job>\nevh jobs-resume <job>")}</div>`;
  }
  function screenJob(id) {
    const head = `<div class="kicker"><a href="#jobs">Jobs</a> · ${esc(id)}</div>`;
    const j = load(`job:${id}`, `/jobs/${enc(id)}`, true);
    if (j === undefined) return `<div class="screen wide">${head}${loading("the job")}</div>`;
    if (j.error) return `<div class="screen wide">${head}${failed(j)}</div>`;
    const running = RUNNING.includes(j.state), cap = (j.env || {}).EVAL_MAX_COST_USD;
    const res = (j.result || {}).result;
    return `<div class="screen wide">${head}<h1 class="mono">${esc(j.operation)}</h1>
      <p class="lead">${stateTagOf(j.state)}${j.waiting_for ? ` · waits for ${esc(j.waiting_for)}` : ""} · asked by <span class="mono">${esc(j.by || "?")}</span> · made ${esc((j.created_at || "").replace("T", " ").slice(0, 19))}${j.ended_at ? ` · ended ${esc(String(j.ended_at).replace("T", " ").slice(0, 19))}` : ""}${j.exit != null ? ` · exit ${esc(j.exit)}` : ""}</p>
      <div class="tablewrap"><table><tbody>
        <tr><th>progress</th><td>${progressOf(j.progress)}</td></tr>
        <tr><th>spent</th><td>${j.spent_usd ? `$${Number(j.spent_usd).toFixed(4)}` : "$0"}${cap ? ` of at most $${Number(cap).toFixed(2)}` : ""}</td></tr>
        <tr><th>holds</th><td class="mono">${(j.locks || []).map(([k, ex]) => `${esc(k)}${ex ? " (alone)" : ""}`).join(", ") || "—"}</td></tr>
        ${j.run_id ? `<tr><th>its run</th><td class="mono">${esc(j.run_id)}</td></tr>` : ""}
        <tr><th>inputs</th><td><pre class="reply">${esc(JSON.stringify(j.inputs || {}, null, 2))}</pre></td></tr>
      </tbody></table></div>
      <div class="actions">${running ? '<button class="btn" type="button" id="jb-stop">Stop it</button>' : ""}${j.run_id && !running && j.state !== "succeeded" ? '<button class="btn primary" type="button" id="jb-resume">Resume the run</button>' : ""}</div><div id="jb-out" data-out></div>
      ${res ? `<h2>Its result</h2>${blocksView(res)}` : ""}
      ${(j.files || []).length ? `<h2>Its files</h2><ul>${j.files.map((n) => `<li><a class="mono" href="/api/v1/jobs/${enc(id)}/files/${enc(n)}" download="${esc(n)}">${esc(n)}</a></li>`).join("")}</ul>` : ""}
      <h2>Its log</h2><pre class="reply" id="jb-log">reading…</pre>
      ${WB.cmd(`evh jobs-status ${id}\nevh jobs-logs ${id}${running ? " --follow" : ""}${running ? `\nevh jobs-stop ${id}` : ""}`)}
      <div class="actions"><a class="btn" href="#jobs">Every job</a></div></div>`;
  }
  function wireJobs() {
    const id = String(WB.param || "");
    if (id) return wireJob(id);
    const f = WB._jobsF || { state: "", operation: "", goal: "", offset: 0 };
    const set = (k, v) => { WB._jobsF = { ...f, [k]: v, offset: k === "offset" ? v : 0 }; WB.render(); };
    document.getElementById("jf-state")?.addEventListener("change", (e) => set("state", e.target.value));
    document.getElementById("jf-op")?.addEventListener("change", (e) => set("operation", e.target.value));
    document.getElementById("jf-goal")?.addEventListener("change", (e) => set("goal", e.target.value));
    document.getElementById("jf-prev")?.addEventListener("click", () => set("offset", Math.max(0, (f.offset || 0) - PAGE)));
    document.getElementById("jf-next")?.addEventListener("click", () => set("offset", (f.offset || 0) + PAGE));
  }
  function wireJob(id) {
    const pre = document.getElementById("jb-log");
    const j = LIVE.cache[`job:${id}`] || {};
    // the log from the start, then followed while the job runs; the job read again when it ends
    let next = 0, alive = true;
    const shown = location.hash;
    const follow = async () => {
      while (alive && location.hash === shown) {
        const r = await fetch(`/api/v1/jobs/${enc(id)}/log?from=${next}`, { credentials: "same-origin" }).catch(() => null);
        const b = r && r.ok ? await r.json().catch(() => ({})) : {};
        if (pre && b.log != null) {
          if (next === 0) pre.textContent = "";
          pre.textContent += b.log;
          next = b.next ?? next;
          if (!pre.textContent) pre.textContent = "(nothing printed yet)";
        }
        if (!RUNNING.includes(j.state)) return;
        await new Promise((ok) => setTimeout(ok, 1000));
        const now = await fetch(`/api/v1/jobs/${enc(id)}`, { credentials: "same-origin" }).then((x) => x.json()).catch(() => ({}));
        if (!alive) return;  // the stop button read the job again already
        if (now.state && !RUNNING.includes(now.state)) { alive = false; forget(`job:${id}`); forget("jobs:"); WB.render(true); return; }
      }
    };
    follow();
    const act = (btn, path, what, after) => document.getElementById(btn)?.addEventListener("click", async (ev) => {
      const box = document.getElementById("jb-out");
      ev.target.disabled = true;
      try {
        const r = await send("POST", path, {});
        box.innerHTML = `<p class="note">${esc(what)}</p>`;
        after(r);
      } catch (e) { box.innerHTML = refusal(e); ev.target.disabled = false; }
    });
    // the job read again once: by the log's poll when it saw the end first (alive then false), else here
    act("jb-stop", `/jobs/${enc(id)}/stop`, "Stopped.", () => { if (!alive) return; alive = false; forget(`job:${id}`); forget("jobs:"); WB.render(true); });
    act("jb-resume", `/jobs/${enc(id)}/resume`, "Resumed as a new job.", (r) => { forget("jobs:"); location.hash = `#jobs/${enc(r.id)}`; });
  }

  // ── the held-out test (UXS-005; RFC-029, RFC-031): items kept back until one candidate is named. The seal; who has
  // read it (reads recorded, the leak check); counts for safety only; opening it for one candidate (one look); its runs;
  // the confirmation with the read items left out. Holding a dataset out is a split, sealed ──
  function screenHeldout(goal) {
    const head = `<div class="kicker">Day to day · ${esc(goal)}</div><h1>The held-out test</h1>
      <p class="lead">Items kept back from tuning until one candidate is named, so the last number is a fair one. A seal stops runs and labels on them; reads it cannot stop are recorded, and every score on them leaves the read items out.</p>`;
    if (!goal) return `<div class="screen">${head}</div>`;
    const rec = load(`goalrec:${goal}`, `/goals/${enc(goal)}`), ds = load("datasets", "/datasets"), sys = load("systems", "/systems");
    if ([rec, ds, sys].includes(undefined)) return `<div class="screen wide">${head}${loading("the goal's datasets")}</div>`;
    const bad = [rec, ds, sys].find((x) => x.error);
    if (bad) return `<div class="screen wide">${head}${failed(bad)}</div>`;
    const mine = (rec.record.datasets || []).map((x) => x.dataset_id), byId = Object.fromEntries(ds.datasets.map((x) => [x.dataset, x]));
    const sides = ds.datasets.filter((x) => x.sealed && (mine.includes(x.dataset) || mine.includes(x.parent))).map((x) => x.dataset);
    const st = WB._ho && WB._ho.goal === goal ? WB._ho : {};
    const side = sides.includes(st.side) ? st.side : sides[0];
    const opt = (xs, sel) => xs.map((x) => `<option value="${esc(x)}" ${x === sel ? "selected" : ""}>${esc(x)}</option>`).join("");
    const sysIds = sys.systems.map((x) => x.system), splittable = mine.filter((x) => !(byId[x] || {}).parent || !/_(test|validation)$/.test(x));
    const splitForm = `<details class="part" ${sides.length ? "" : "open"}><summary><b>Hold ${sides.length ? "another dataset" : "some items"} out</b></summary><div class="body" data-form="split">
        <p class="muted">A split makes two datasets: <span class="mono">&lt;id&gt;_validation</span> to tune on and <span class="mono">&lt;id&gt;_test</span>, sealed, to decide on once.</p>
        <div class="inline"><select id="sp-ds" aria-label="the dataset">${opt(splittable)}</select>
          <label class="choice"><input type="radio" name="sp-by" value="time" checked> by time</label><label class="choice"><input type="radio" name="sp-by" value="hash"> by hash</label></div>
        <div class="inline"><input type="text" id="sp-key" placeholder="the time field: opened (by hash: one value to one side)" autocapitalize="off" spellcheck="false" style="min-width:16rem">
          <input type="text" id="sp-at" placeholder="by time: the boundary, 2026-11-02T00:00:00Z" autocapitalize="off" spellcheck="false" style="min-width:16rem">
          <input type="number" id="sp-test" placeholder="by hash: the test share, 0.3" step="0.05" min="0.05" max="0.95" style="width:12rem"></div>
        <div class="inline"><label class="choice"><input type="checkbox" id="sp-seal" checked> seal the test side</label>
          <input type="text" id="sp-count" placeholder="fields its counts may show: kind (fixed now)" autocapitalize="off" spellcheck="false" style="min-width:16rem"></div>
        <div class="actions" style="margin-top:0"><button class="btn primary" type="button" id="sp-go" data-send>Split it</button>${mark}</div><div id="sp-out" data-out></div></div></details>`;
    if (!side) return `<div class="screen wide">${head}${byField("ho-by")}<p class="muted">None of this goal's datasets is held out yet.</p>${splitForm}
      ${WB.cmd("evh dataset-split --dataset-id <dataset> --split-by time --key opened --at <T> --seal --count-by kind")}<div class="actions"><a class="btn" href="#goal/${enc(goal)}">Back to the goal</a></div></div>`;
    const d = load(`dataset:${side}`, `/datasets/${enc(side)}`), ex = load(`exposure:${side}`, `/exposure?dataset=${enc(side)}`);
    const counts = load(`sealedcounts:${side}`, `/datasets/${enc(side)}/sealed-counts`), lk = load(`looks:${side}`, `/looks?dataset=${enc(side)}`);
    if ([d, ex, counts, lk].includes(undefined)) return `<div class="screen wide">${head}${loading("the held-out side")}</div>`;
    const r = (d.record || {}), seal = r.sealed || {}, split = r.split || {}, opened = r.unsealed || [];
    const exs = ((ex.sides || []).find((x) => x.dataset_id === side)) || { items: d.n_items, exposed: 0, reads: 0, by: {}, what: {} };
    const look = ((lk.sets || []).find((x) => x.dataset_id === side)) || {};
    const cnt = ((((counts || {}).values || {}).counts) || {})["held-out items"] || {};
    const days = Object.keys(cnt).sort(), keys = [...new Set(days.flatMap((x) => Object.keys(cnt[x]).filter((k) => k !== "n")))].sort();
    const last = opened[opened.length - 1];
    const cand = st.cand || (last || {}).system_id, against = st.against || ((last || {}).hypothesis || {}).against, measure = ((last || {}).hypothesis || {}).measure;
    const pt = cand && against ? load(`pairtest:${side}:${cand}:${against}`, `/datasets/${enc(side)}/pair-test?a=${enc(cand)}&b=${enc(against)}${measure ? `&metric=${enc(measure)}` : ""}&include_exposed=true`) : null;
    const pv = pt && !pt.error ? pt.values || {} : null;
    const tbl = (h, rows) => `<div class="tablewrap"><table><thead><tr>${h.map((x) => `<th>${esc(x)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
    const part = (n, title, body, tag = "") => `<section class="part"><div class="parthead"><span class="letter">${n}</span><h2>${esc(title)}</h2><span class="grow"></span>${tag}</div><div class="body">${body}</div></section>`;
    const pct = (x) => (typeof x === "number" ? `${(x * 100).toFixed(4)}%` : "—");
    return `<div class="screen wide">${head}<span id="ho-cur" data-side="${esc(side)}" hidden></span>
      ${sides.length > 1 ? `<div class="inline"><span class="muted">the held-out side</span><select id="ho-side" aria-label="the held-out side">${opt(sides, side)}</select></div>` : ""}
      ${byField("ho-by")}
      ${part(1, "The seal", `<div class="stats"><div><b>${d.n_items}</b><span>held-out items</span></div><div><b>${seal.at ? esc(String(seal.at).slice(0, 10)) : "not sealed"}</b><span>sealed</span></div><div><b>${esc((seal.count_by || []).join(", ") || "—")}</b><span>what its counts may show</span></div></div>
        <p class="muted">${split.split_by === "time" ? `Split by time on <span class="mono">${esc(split.key || "")}</span>: every item on or after ${esc(split.at || "")} is held out` : `Split by hash${split.key ? ` on <span class="mono">${esc(split.key)}</span>` : ""}, ${Math.round((split.test || 0) * 100)}% held out`}; its other side is <span class="mono">${esc(seal.open_side || "")}</span>, to tune on. A run, a label sheet or a reference on it is refused until a candidate is named in advance.</p>`, `<span class="status ${seal.at ? "ok" : ""}">${seal.at ? "sealed" : "open"}</span>`)}
      ${part(2, "Who has read it", `<div class="stats"><div><b>${exs.exposed} of ${exs.items}</b><span>items read</span></div><div><b>${exs.reads}</b><span>reads recorded</span></div><div><b>${exs.items - exs.exposed}</b><span>still unread</span></div></div>
        ${Object.keys(exs.by || {}).length ? tbl(["who read", "reads"], Object.entries(exs.by).map(([k, v]) => `<tr><td class="mono">${esc(k)}</td><td class="num">${v}</td></tr>`)) : ""}
        ${Object.keys(exs.what || {}).length ? tbl(["what was read", "reads"], Object.entries(exs.what).map(([k, v]) => `<tr><td>${esc(k)}</td><td class="num">${v}</td></tr>`)) : ""}
        <div data-form="read"><h3>Record a read</h3><div class="inline"><input type="text" id="rd-items" placeholder="the items read: t02, t05" autocapitalize="off" spellcheck="false">
          <input type="text" id="rd-what" placeholder="what was read: the decision and its reason" style="min-width:16rem">
          <input type="text" id="rd-who" placeholder="who read it: agent:homelab (default: you)" autocapitalize="off" spellcheck="false"></div>
          <div class="actions" style="margin-top:0"><button class="btn" type="button" id="rd-go" data-send>Record it</button>${mark}</div><div id="rd-out" data-out></div></div>
        <h3>The leak check</h3><p class="muted">Searches the project's public repos (config.yaml's exposure) for these items' ids; a find not yet recorded can be recorded as a read. It cannot catch a paraphrase.</p>
        <div class="actions" style="margin-top:0"><button class="btn" type="button" id="lk-go">Check for leaks</button></div><div id="lk-out" data-out></div>`, `<span class="status ${exs.exposed ? "" : "ok"}">${exs.exposed} read</span>`)}
      ${part(3, "Counts, for safety only", `${counts.error ? failed(counts) : days.length ? tbl(["day", "items", ...keys], days.map((x) => `<tr><td class="mono">${esc(x)}</td><td class="num">${cnt[x].n}</td>${keys.map((k) => `<td class="num">${cnt[x][k] || ""}</td>`).join("")}</tr>`)) : '<p class="muted">No counts.</p>'}
        <p class="muted">Never to judge an effect: whoever reads them did not choose what they show.</p>
        <div data-form="seal-counts"><div class="inline"><input type="text" id="sc-add" placeholder="allow one more field" autocapitalize="off" spellcheck="false"><input type="text" id="sc-why" placeholder="why the counts need it: a sentence" style="min-width:18rem">
          <button class="btn" type="button" id="sc-go" data-send>Allow it</button>${mark}</div><div id="sc-out" data-out></div></div>`)}
      ${part(4, "Open it for one candidate", `<p class="muted">The candidate's hypothesis (what it is against, the measure, the direction) must be in it and committed first. Opening it is one look at this test set; each later look is tested at a stricter level.</p>
        <p>Next: look ${look.next ?? "?"}, one-sided at ${pct(look.next_level)}; ${look.limit != null ? `at most ${look.limit} looks` : ""}${(look.looks || []).length ? ` · ${look.looks.length} so far` : ""}</p>
        ${opened.length ? tbl(["look", "candidate", "against", "why", "committed", "by"], opened.map((u) => `<tr><td class="num">${(u.look || {}).number ?? ""}</td><td class="mono">${esc(u.system_id)}</td><td class="mono">${esc((u.hypothesis || {}).against || "")}</td><td>${esc(u.reason || "")}</td><td class="mono">${esc(String(u.commit || "").slice(0, 8))}</td><td>${esc(u.actor && u.actor.name ? actorSaid(u.actor) : "")}</td></tr>`)) : ""}
        <div data-form="unseal"><div class="inline"><select id="us-sys" aria-label="the candidate">${opt(sysIds)}</select><input type="text" id="us-why" placeholder="why this candidate, and why now: a sentence" style="min-width:18rem">
          ${look.limit != null && look.next > look.limit ? '<label class="choice"><input type="checkbox" id="us-extra"> look past the limit (a person only)</label>' : ""}
          <button class="btn primary" type="button" id="us-go" data-send>Open it for this candidate</button>${mark}</div><div id="us-out" data-out></div></div>`, opened.length ? `<span class="status">look ${opened.length}</span>` : "")}
      ${last ? part(5, "Run the candidate and what it is against", `<p class="muted">Each on the held-out side: the runs the confirmation reads.</p>
        <div class="inline"><label>at most (USD) <input type="number" id="hr-cap" value="1" min="0.01" step="0.01" style="width:6rem"></label>
          <button class="btn" type="button" id="hr-go">Run ${esc(cand)} and ${esc(against || "")}</button></div><div id="hr-out" data-out></div>`) : ""}
      ${last ? part(6, "The confirmation", pt === undefined ? loading("the paired test") : pt && pt.error ? failed(pt) : pv ? `${tbl(["", "items", "delta (A − B)", "p", "verdict"], [
          `<tr><td><b>the number that counts</b>${Object.values(pv.left_out_exposed || {})[0] ? ` <span class="muted">(${Object.values(pv.left_out_exposed)[0]} read item(s) left out)</span>` : ""}</td><td class="num">${pv.n}</td><td class="num">${pv.delta >= 0 ? "+" : ""}${fx(pv.delta)}</td><td class="num">${fx(pv.p)}</td><td><span class="verdict ${pv.verdict === "SIGNIFICANT" ? "v-lead" : "v-ns"}">${esc(String(pv.verdict || "").toLowerCase())}</span></td></tr>`,
          pv.with_exposed ? `<tr class="muted"><td>with the read items kept (not the one that counts)</td><td class="num">${pv.with_exposed.n}</td><td class="num">${pv.with_exposed.delta >= 0 ? "+" : ""}${fx(pv.with_exposed.delta)}</td><td class="num">—</td><td></td></tr>` : "",
        ])}<details><summary>As the harness says it</summary>${blocksView(pt)}</details>` : "") : ""}
      ${splitForm}
      ${WB.cmd(`evh exposure --dataset ${side}\nevh exposure-add --dataset-id ${side} --item <id> --what "…" --read-by agent:<name>\nevh exposure-check --dataset-id ${side} --out leaks.tsv\nevh sealed-counts ${side}\nevh dataset-unseal --dataset-id ${side} --system <candidate> --reason "…"\nevh pair-test ${side} --a <candidate> --b <against> --include-exposed`)}
      <div class="actions"><a class="btn" href="#goal/${enc(goal)}">Back to the goal</a></div></div>`;
  }
  function wireHeldout() {
    const goal = WB.param || "";
    const v = (id) => (document.getElementById(id)?.value || "").trim();
    const by = () => byOf("ho-by") || (who() ? `person:${who()}` : null);
    const needWho = (box) => { box.innerHTML = '<p class="note" role="alert">Say who you are above: a change names who made it.</p>'; };
    const cur = (LIVE.cache[`goalrec:${goal}`] || {}).record || {};
    const theSide = () => document.getElementById("ho-cur")?.dataset.side || "";
    const again = (box, done, keys) => {
      keys.forEach((k) => forget(k));
      box.innerHTML = `<p class="note">Done.</p>${blocksView((done.result || {}).result)}`;
      const k = document.createElement("p");
      k.innerHTML = '<button class="btn" type="button">Read it again</button>';
      k.querySelector("button").addEventListener("click", () => WB.render(true));
      box.appendChild(k);
    };
    const job = (btn, out, form, path, body, what, keys, after) => document.getElementById(btn)?.addEventListener("click", async (ev) => {
      const box = document.getElementById(out), who_ = by();
      if (!who_) return needWho(box);
      ev.target.disabled = true;
      try {
        const done = await runJob(typeof path === "function" ? path() : path, { ...body(), by: who_ }, box, what);
        if (done) { if (form) sent(form); again(box, done, keys()); if (after) await after(box, done, who_); }
      } catch (e) { box.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    document.getElementById("ho-side")?.addEventListener("change", () => { WB._ho = { goal, side: v("ho-side") }; WB.render(); });
    holds("read", () => `Record ${v("rd-items").split(/[\s,]+/).filter(Boolean).length || "…"} read(s)`);
    job("rd-go", "rd-out", "read", () => `/datasets/${enc(theSide())}/exposure`, () => {
      const b = { item: v("rd-items").split(/[\s,]+/).filter(Boolean), what: v("rd-what") };
      if (v("rd-who")) b.read_by = v("rd-who");
      return b;
    }, "recording", () => [`exposure:${theSide()}`, `pairtest:${theSide()}`]);
    document.getElementById("lk-go")?.addEventListener("click", async (ev) => {
      const box = document.getElementById("lk-out"), who_ = by();
      if (!who_) return needWho(box);
      ev.target.disabled = true;
      try {
        const j = await send("POST", "/exposure/check", { dataset_id: theSide(), out: "leaks.tsv", by: who_ });
        const done = await watchJob(j.id, box, "checking");
        if (done.state !== "succeeded" && done.exit !== 6) { box.innerHTML = await jobRefusal(done); ev.target.disabled = false; return; }
        const log = ((await fetch(`/api/v1/jobs/${enc(done.id)}/log`, { credentials: "same-origin" }).then((x) => x.json()).catch(() => ({}))).log || "").trim();
        box.innerHTML = `${done.exit === 6 ? '<p class="note">It found ids the register lacks.</p>' : '<p class="note">Nothing found that the register lacks.</p>'}<pre class="reply">${esc(log.split("\n").slice(-12).join("\n"))}</pre>`;
        await leaks(box, done, who_);
      } catch (e) { box.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    async function leaks(box, done, who_) {
      if (!(done.files || []).includes("leaks.tsv")) return;
      const tsv = await (await fetch(`/api/v1/jobs/${enc(done.id)}/files/leaks.tsv`, { credentials: "same-origin" })).text();
      const n = tsv.split("\n").filter((x) => x.trim()).length - 1;
      if (n <= 0) return;
      box.insertAdjacentHTML("beforeend", `<p class="note">${n} find(s) not yet in the register. <button class="btn" type="button" id="lk-add">Record them as reads</button></p>`);
      document.getElementById("lk-add").addEventListener("click", async (ev) => {
        ev.target.disabled = true;
        try {
          const added = await runJob(`/datasets/${enc(theSide())}/exposure`, { from: { name: "leaks.tsv", content_base64: b64(tsv) }, by: who_ }, box, "recording the finds");
          if (added) again(box, added, [`exposure:${theSide()}`, `pairtest:${theSide()}`]);
        } catch (e) { box.innerHTML = refusal(e); }
      });
    }
    holds("seal-counts", () => `Allow ${v("sc-add") || "…"}`);
    job("sc-go", "sc-out", "seal-counts", () => `/datasets/${enc(theSide())}/sealed-counts/allow`, () => ({ add: v("sc-add"), reason: v("sc-why") }), "allowing", () => [`sealedcounts:${theSide()}`, `dataset:${theSide()}`]);
    holds("unseal", () => `Open it for ${v("us-sys") || "…"}`);
    job("us-go", "us-out", "unseal", () => `/datasets/${enc(theSide())}/unseal`, () => {
      const b = { system: v("us-sys"), reason: v("us-why") };
      if (document.getElementById("us-extra")?.checked) b.confirm_extra_look = true;
      return b;
    }, "opening it", () => [`dataset:${theSide()}`, `looks:${theSide()}`, `pairtest:${theSide()}`]);
    document.getElementById("hr-go")?.addEventListener("click", async (ev) => {
      const box = document.getElementById("hr-out"), who_ = by(), cap = Number(v("hr-cap"));
      if (!who_) return needWho(box);
      const u = (((LIVE.cache[`dataset:${theSide()}`] || {}).record || {}).unsealed || []).slice(-1)[0] || {};
      ev.target.disabled = true;
      try {
        // a split makes its sides unfetched: the runs read the side's items, so they are fetched first
        if (!((((LIVE.cache[`dataset:${theSide()}`] || {}).parts || {}).materialized || {}).present) && !(await runJob(`/datasets/${enc(theSide())}/materialize`, { by: who_ }, box, "fetching its items"))) { ev.target.disabled = false; return; }
        for (const s of [u.system_id, (u.hypothesis || {}).against].filter(Boolean)) {
          const j = await send("POST", "/jobs", { operation: "run", inputs: { system: s, dataset: theSide() }, by: who_, max_cost_usd: cap });
          const done = await watchJob(j.id, box, `running ${s}`);
          if (done.state !== "succeeded") { box.innerHTML = await jobRefusal(done); ev.target.disabled = false; return; }
        }
        again(box, { result: {} }, [`pairtest:${theSide()}`]);
      } catch (e) { box.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    holds("split", () => `Split ${v("sp-ds") || "…"}`);
    job("sp-go", "sp-out", "split", () => `/datasets/${enc(v("sp-ds"))}/split`, () => {
      const b = { split_by: document.querySelector("input[name=sp-by]:checked")?.value || "time" };
      if (v("sp-key")) b.key = v("sp-key");
      if (b.split_by === "time" && v("sp-at")) b.at = v("sp-at");
      if (b.split_by === "hash" && v("sp-test")) b.test = Number(v("sp-test"));
      if (document.getElementById("sp-seal").checked) b.seal = true;
      if (v("sp-count")) b.count_by = v("sp-count");
      return b;
    }, "splitting", () => ["datasets", "dataset:"], async (box, done, who_) => {
      // both sides join the goal: the validation side to tune on, the test side to decide on
      const base = v("sp-ds"), n = (cur.datasets || []).length;
      try {
        await send("PATCH", `/goals/${enc(goal)}`, { set: { [`datasets.${n}.dataset_id`]: `${base}_validation`, [`datasets.${n}.role`]: "validation", [`datasets.${n + 1}.dataset_id`]: `${base}_test`, [`datasets.${n + 1}.role`]: "test" }, by: who_ });
        forget(`goalrec:${goal}`); forget(`status:${goal}`);
        box.insertAdjacentHTML("beforeend", `<p class="note">Both sides joined the goal: ${esc(base)}_validation to tune on, ${esc(base)}_test to decide on.</p>`);
      } catch (e) { box.insertAdjacentHTML("beforeend", refusal(e)); }
    });
  }

  // ── studies (UXS-005; RFC-029): a search over one thing at a time on the validation items, never evidence; its trials
  // and the best so far; the agent sampler's ask and tell from the page; stopped; confirmed once on a test set (one
  // look). A spec is YAML, written on the page and checked (the dry run) before it runs ──
  // A baseline that points at a prompt version lets the study change it: the agent proposes a new text, each trial a
  // new version of it (its parent the best so far's).
  const specOf = (ds, base, measure, sampler, prompts = []) => `dataset: ${ds}\nbaseline: {system: ${base}}\nmeasure: ${measure}\nsampler: ${sampler}\naccept: {point: {min_gain: 0}}\nstop: {trials: 5}\nspace:\n${prompts.length ? `  prompts: [${prompts.join(", ")}]\n` : ""}  groups:\n    - {name: length, reason: how much to keep, params: {sentences: [2, 3, 4]}}\n`;
  function screenStudies(param) {
    const [goal, sid] = String(param || "").split("/");
    const head = `<div class="kicker">Day to day · ${esc(goal)}</div><h1>${sid ? `The study ${esc(sid)}` : "Studies"}</h1>
      <p class="lead">A search over one thing at a time, each trial measured against the best so far on the validation items; it never promotes. Its best is confirmed once on a test set: one look.</p>`;
    if (!goal) return `<div class="screen">${head}</div>`;
    const rec = load(`goalrec:${goal}`, `/goals/${enc(goal)}`), list = load(`studies:${goal}`, `/goals/${enc(goal)}/studies`), sys = load("systems", "/systems"), dsl = load("datasets", "/datasets");
    if ([rec, list, sys, dsl].includes(undefined)) return `<div class="screen wide">${head}${loading("the studies")}</div>`;
    const bad = [rec, list, sys, dsl].find((x) => x.error);
    if (bad) return `<div class="screen wide">${head}${failed(bad)}</div>`;
    const dss = rec.record.datasets || [], roleOf = (r) => dss.filter((x) => x.role === r).map((x) => x.dataset_id);
    const sealed = dsl.datasets.filter((x) => x.sealed && dss.some((d) => d.dataset_id === x.dataset || d.dataset_id === x.parent)).map((x) => x.dataset);
    const tests = [...new Set(roleOf("test").concat(sealed))], vals = roleOf("validation").length ? roleOf("validation") : dss.map((x) => x.dataset_id);
    const measure = ((rec.record.success_criteria || {}).primary || {}).measure || "";
    const sysIds = sys.systems.map((x) => x.system);
    const opt = (xs, sel) => xs.map((x) => `<option value="${esc(x)}" ${x === sel ? "selected" : ""}>${esc(x)}</option>`).join("");
    const tbl = (h, rows) => `<div class="tablewrap"><table><thead><tr>${h.map((x) => `<th>${esc(x)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
    const part = (n, title, body, tag = "") => `<section class="part"><div class="parthead"><span class="letter">${n}</span><h2>${esc(title)}</h2><span class="grow"></span>${tag}</div><div class="body">${body}</div></section>`;
    const cmd = WB.cmd(`evh study-run --study ${goal}/<id> --spec study.yaml --dry-run\nevh study-run --study ${goal}/<id> --spec study.yaml\nevh study-list ${goal}\nevh study-ask --study ${goal}/<id>\nevh study-tell --study ${goal}/<id> --ask <id> --proposal-json '{...}'\nevh study-stop --study ${goal}/<id>\nevh study-confirm --study ${goal}/<id> --test <test set> --rule superiority`);
    if (!sid) {
      const draft = (WB._study || {})[goal] || specOf(vals[0] || "<dataset>", sysIds[0] || "<system>", measure, "grid");
      return `<div class="screen wide">${head}${byField("st6-by")}
        ${list.studies.length ? tbl(["study", "state", "on", "from", "trials", "kept", "spent", "confirmed"], list.studies.map((x) => `<tr><td class="mono"><a href="#study/${enc(goal)}/${enc(x.study.split("/").pop())}">${esc(x.study)}</a></td><td>${esc(x.status)}</td><td class="mono">${esc(x.dataset)}</td><td class="mono">${esc(x.baseline)}</td><td class="num">${x.trials}</td><td class="num">${x.kept}</td><td class="num">$${Number(x.spent_usd || 0).toFixed(4)}</td><td class="num">${x.confirms}</td></tr>`)) : '<p class="muted">No study yet.</p>'}
        ${part("a", "A new study", `<div data-form="study-new"><div class="inline"><input type="text" id="sn6-id" placeholder="its id: s1" autocapitalize="off" spellcheck="false">
            <select id="sn6-ds" aria-label="the validation dataset">${opt(vals)}</select><select id="sn6-base" aria-label="the system it starts from">${opt(sysIds)}</select>
            <select id="sn6-sampler" aria-label="how it chooses"><option value="grid">grid: every value in turn</option><option value="agent">agent: proposals asked and told</option></select>
            <button class="btn" type="button" id="sn6-fill">Write the spec from these</button></div>
          <textarea id="sn6-spec" rows="10" style="width:100%" class="mono" aria-label="the spec" spellcheck="false">${esc(draft)}</textarea>
          <div class="actions" style="margin-top:0"><button class="btn" type="button" id="sn6-dry">Check it (nothing runs)</button>
            <label>at most (USD) <input type="number" id="sn6-cap" value="1" min="0.01" step="0.01" style="width:6rem"></label>
            <button class="btn primary" type="button" id="sn6-go" data-send>Run it</button>${mark}</div><div id="sn6-out" data-out></div></div>`)}
        ${part("b", "Import a past loop", `<p class="muted">A results.tsv from a loop run elsewhere, kept as a closed study: shown, never confirmed.</p>
          <div class="inline" data-form="study-import"><input type="text" id="si-id" placeholder="the study's id" autocapitalize="off" spellcheck="false"><input type="file" id="si-file" accept=".tsv,text/tab-separated-values" aria-label="the results.tsv">
            <button class="btn" type="button" id="si-go" data-send>Import it</button>${mark}</div><div id="si-out" data-out></div>`)}
        ${cmd}<div class="actions"><a class="btn" href="#goal/${enc(goal)}">Back to the goal</a></div></div>`;
    }
    const one = load(`study:${goal}/${sid}`, `/goals/${enc(goal)}/studies/${enc(sid)}`);
    if (one === undefined) return `<div class="screen wide">${head}${loading("the study")}</div>`;
    if (one.error) return `<div class="screen wide">${head}${failed(one)}<div class="actions"><a class="btn" href="#study/${enc(goal)}">Every study</a></div></div>`;
    const sp = one.spec || {}, verdicts = (one.confirms || []).filter((c) => c.outcome);
    const st = (WB._studyOne || {})[`${goal}/${sid}`] || {};
    const agent = sp.sampler === "agent", open = one.status !== "ended";
    return `<div class="screen wide">${head}<span id="st6-cur" data-study="${esc(goal)}/${esc(sid)}" hidden></span>${byField("st6-by")}
      ${part(1, "What it searches", `<div class="stats"><div><b>${esc(one.baseline || "")}</b><span>from</span></div><div><b>${esc(sp.sampler || "")}</b><span>how it chooses</span></div><div><b>${(one.trials || []).length}</b><span>trials</span></div><div><b>${esc(one.status || "")}</b><span>its state</span></div></div>
        <p class="muted">On <span class="mono">${esc(sp.dataset || "")}</span>, decided on ${esc(sp.measure || "")}; round ${esc(one.round || "")}; spent $${Number(one.spent_usd || 0).toFixed(4)}.${one.end ? ` Ended: ${esc(one.end)}.` : ""}</p>
        <details><summary>Its spec</summary><pre class="reply">${esc(JSON.stringify(sp, null, 2))}</pre></details>`)}
      ${part(2, "Its trials", `${(one.trials || []).length ? chartBox("study-progress", { goal, study: sid }) + chartBox("gain-cost", { goal, study: sid }) : ""}${(one.rows || []).length ? tbl(["trial", "what changed", "outcome", "why", "vs the best", "cost"], one.rows.map((x) => `<tr><td class="mono">t${x.k}</td><td>${esc(x.change || "")}${x.hypothesis && x.hypothesis !== x.change ? `<div class="muted">${esc(x.hypothesis)}</div>` : ""}</td><td><span class="verdict ${x.outcome === "kept" ? "v-lead" : "v-ns"}">${esc(x.outcome || "")}</span></td><td>${esc(x.reason || "")}</td><td class="num">${typeof x.delta === "number" ? (x.delta >= 0 ? "+" : "") + x.delta.toFixed(4) : "—"}</td><td class="num">$${Number(x.cost_usd || 0).toFixed(4)}</td></tr>`)) : '<p class="muted">No trial yet.</p>'}
        <p class="note">Best so far: <span class="mono">${esc(one.best || one.baseline || "")}</span>. Research on validation items: no evidence until it is confirmed.</p>
        ${open ? `<div class="actions" style="margin-top:0"><button class="btn" type="button" id="so-stop">Stop it</button>${agent ? "" : '<label>at most (USD) <input type="number" id="so-cap" value="1" min="0.01" step="0.01" style="width:6rem"></label><button class="btn" type="button" id="so-resume">Continue it</button>'}</div><div id="so-out" data-out></div>` : ""}`)}
      ${agent && open ? part(3, "Propose the next trial", `<p class="muted">The agent sampler: ask for the study's state (its weakest items, what was tried), then tell a proposal, which runs as the next trial.</p>
        <div class="actions" style="margin-top:0"><button class="btn" type="button" id="sa-go">Ask its state</button></div><div id="sa-out" data-out>${st.ask ? `<p>ask <b class="mono">${esc(st.ask)}</b></p><details><summary>its state</summary><pre class="reply">${esc(JSON.stringify(st.state || {}, null, 2))}</pre></details>` : ""}</div>
        ${st.ask ? `<div data-form="tell"><p class="muted">${Object.keys(((st.state || {}).best || {}).prompts || {}).length ? "Its prompts are below as the best so far sends them: change the text to try a new version." : "Change its settings (params) by their dotted names."}</p><textarea id="tl-json" rows="8" style="width:100%" class="mono" spellcheck="false" aria-label="the proposal">${esc(JSON.stringify({ params: {}, ...(Object.keys(((st.state || {}).best || {}).prompts || {}).length ? { prompts: (st.state.best || {}).prompts } : {}), hypothesis: "", rationale: "" }, null, 2))}</textarea>
          <div class="actions" style="margin-top:0"><label>at most (USD) <input type="number" id="tl-cap" value="1" min="0.01" step="0.01" style="width:6rem"></label><button class="btn primary" type="button" id="tl-go" data-send>Run this trial</button>${mark}</div><div id="tl-out" data-out></div></div>` : ""}`) : ""}
      ${part(agent && open ? 4 : 3, "Confirm it on a test set: one look", `${verdicts.length ? tbl(["trial", "test set", "rule", "items", "delta", "p (one-sided)", "look", "outcome"], verdicts.map((c) => `<tr><td class="mono">t${c.trial}</td><td class="mono">${esc(c.test)}</td><td>${esc(c.rule)}</td><td class="num">${c.n ?? c.items ?? ""}</td><td class="num">${typeof c.delta === "number" ? (c.delta >= 0 ? "+" : "") + c.delta.toFixed(4) : ""}</td><td class="num">${typeof c.p_one_sided === "number" ? c.p_one_sided.toFixed(4) : ""}</td><td class="num">${(c.look || {}).number ?? ""} at ${(((c.look || {}).level || 0) * 100).toFixed(4)}%</td><td><span class="verdict ${c.outcome === "better" || c.outcome === "noninferior" ? "v-lead" : "v-ns"}">${esc(c.outcome)}</span></td></tr>`)) : ""}
        <p class="muted">The rule is given before any test item is read; each look at a test set is tested at a stricter level.</p>
        <div data-form="confirm"><div class="inline"><select id="cf-test" aria-label="the test set">${opt(tests)}</select>
          <select id="cf-rule" aria-label="the rule"><option value="superiority">better than where it started</option><option value="noninferiority">no worse, within a margin</option></select>
          <input type="number" id="cf-margin" placeholder="the margin (no worse)" step="any" style="width:10rem"><input type="number" id="cf-trial" placeholder="trial (default: the best)" min="1" style="width:10rem">
          <label>at most (USD) <input type="number" id="cf-cap" value="1" min="0.01" step="0.01" style="width:6rem"></label></div>
          <div class="actions" style="margin-top:0"><button class="btn" type="button" id="cf-dry">What it would read (nothing runs)</button><button class="btn primary" type="button" id="cf-go" data-send>Confirm it</button>${mark}</div><div id="cf-out" data-out></div></div>`, verdicts.length ? `<span class="status ok">${verdicts.length} confirmed</span>` : "")}
      ${cmd}<div class="actions"><a class="btn" href="#study/${enc(goal)}">Every study</a><a class="btn" href="#goal/${enc(goal)}">Back to the goal</a></div></div>`;
  }
  function wireStudies() {
    const [goal, sid] = String(WB.param || "").split("/");
    const v = (id) => (document.getElementById(id)?.value || "").trim();
    const by = () => byOf("st6-by") || (who() ? `person:${who()}` : null);
    const needWho = (box) => { box.innerHTML = '<p class="note" role="alert">Say who you are above: a job names who asked.</p>'; };
    const cap = (id) => Number(v(id));
    const job = (btn, out, form, path, body, what, after) => document.getElementById(btn)?.addEventListener("click", async (ev) => {
      const box = document.getElementById(out), who_ = by();
      if (!who_) return needWho(box);
      ev.target.disabled = true;
      try {
        const b = body();
        if (b === null) { ev.target.disabled = false; return; }
        const done = await runJob(typeof path === "function" ? path() : path, { ...b, by: who_ }, box, what);
        if (done) {
          if (form) sent(form);
          box.innerHTML = blocksView((done.result || {}).result);
          if (after) after(box, done);
        }
      } catch (e) { box.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    const reread = (box) => {
      const k = document.createElement("p");
      k.innerHTML = '<button class="btn" type="button">Read it again</button>';
      k.querySelector("button").addEventListener("click", () => { forget(`studies:${goal}`); forget(`study:${goal}/`); forget("chart:"); WB.render(true); });
      box.appendChild(k);
    };
    if (!sid) {
      const spec = document.getElementById("sn6-spec");
      // the spec is longer work: kept in this browser until the study runs
      spec?.addEventListener("input", () => { WB._study = { ...(WB._study || {}), [goal]: spec.value }; });
      document.getElementById("sn6-fill")?.addEventListener("click", async () => {
        const m = ((((LIVE.cache[`goalrec:${goal}`] || {}).record || {}).success_criteria || {}).primary || {}).measure || "";
        // the baseline's declared prompts: the agent may change them
        const r = await fetch(`/api/v1/systems/${enc(v("sn6-base"))}`, { credentials: "same-origin" }).then((x) => x.json()).catch(() => ({}));
        const named = v("sn6-sampler") === "agent" ? Object.keys(((r.result || {}).record || {}).prompts || {}) : [];
        spec.value = specOf(v("sn6-ds"), v("sn6-base"), m, v("sn6-sampler"), named);
        spec.dispatchEvent(new Event("input", { bubbles: true }));
      });
      const specBody = (dry) => () => {
        if (!v("sn6-id")) { document.getElementById("sn6-out").innerHTML = '<p class="note" role="alert">Name it first: its id.</p>'; return null; }
        return { spec: { name: `${v("sn6-id")}.yaml`, content_base64: b64(spec.value) }, dry_run: dry, max_cost_usd: cap("sn6-cap") };
      };
      holds("study-new", () => `Run study ${v("sn6-id") || "…"}`);
      job("sn6-dry", "sn6-out", null, () => `/goals/${enc(goal)}/studies/${enc(v("sn6-id"))}`, specBody(true), "checking the spec");
      job("sn6-go", "sn6-out", "study-new", () => `/goals/${enc(goal)}/studies/${enc(v("sn6-id"))}`, specBody(false), "running the study", (box) => {
        WB._study = { ...(WB._study || {}), [goal]: undefined };
        box.insertAdjacentHTML("beforeend", `<p><a class="btn" href="#study/${enc(goal)}/${enc(v("sn6-id"))}">Open it</a></p>`);
        forget(`studies:${goal}`);
      });
      holds("study-import", () => `Import ${v("si-id") || "…"}`);
      document.getElementById("si-go")?.addEventListener("click", async (ev) => {
        const box = document.getElementById("si-out"), who_ = by(), f = document.getElementById("si-file").files[0];
        if (!who_) return needWho(box);
        if (!f) { box.innerHTML = '<p class="note" role="alert">Choose the results.tsv first.</p>'; return; }
        ev.target.disabled = true;
        try {
          const text = await f.text();
          const done = await runJob(`/goals/${enc(goal)}/study-imports`, { study: v("si-id"), file: { name: f.name, content_base64: b64(text) }, by: who_ }, box, "importing");
          if (done) { sent("study-import"); box.innerHTML = blocksView((done.result || {}).result); reread(box); }
        } catch (e) { box.innerHTML = refusal(e); }
        ev.target.disabled = false;
      });
      return;
    }
    const base = `/goals/${enc(goal)}/studies/${enc(sid)}`;
    job("so-stop", "so-out", null, `${base}/stop`, () => ({}), "stopping", (box) => reread(box));
    job("so-resume", "so-out", null, base, () => ({ resume: true, max_cost_usd: cap("so-cap") }), "continuing", (box) => reread(box));
    job("sa-go", "sa-out", null, `${base}/ask`, () => ({}), "asking", (box, done) => {
      const vals = ((done.result || {}).result || {}).values || {};
      WB._studyOne = { ...(WB._studyOne || {}), [`${goal}/${sid}`]: { ask: vals.ask_id, state: vals.state } };
      WB.render();
    });
    holds("tell", () => "Run this trial");
    job("tl-go", "tl-out", "tell", `${base}/tell`, () => {
      const st = (WB._studyOne || {})[`${goal}/${sid}`] || {};
      try { JSON.parse(v("tl-json")); } catch { document.getElementById("tl-out").innerHTML = '<p class="note" role="alert">The proposal is not JSON.</p>'; return null; }
      return { ask: st.ask, proposal_json: v("tl-json"), max_cost_usd: cap("tl-cap") };
    }, "running the trial", (box) => { WB._studyOne = { ...(WB._studyOne || {}), [`${goal}/${sid}`]: {} }; reread(box); });
    const confirmBody = (dry) => () => {
      const b = { test: v("cf-test"), rule: v("cf-rule") };
      if (v("cf-margin")) b.margin = Number(v("cf-margin"));
      if (v("cf-trial")) b.trial = Number(v("cf-trial"));
      return dry ? { ...b, dry_run: true, max_cost_usd: cap("cf-cap") } : { ...b, max_cost_usd: cap("cf-cap") };
    };
    holds("confirm", () => `Confirm on ${v("cf-test") || "…"}`);
    job("cf-dry", "cf-out", null, `${base}/confirm`, confirmBody(true), "looking at what it would read");
    job("cf-go", "cf-out", "confirm", `${base}/confirm`, confirmBody(false), "confirming", (box) => { forget(`looks:`); reread(box); });
  }

  // ── prompts (RFC-028): every prompt with its versions, the runs that sent each, two versions' diff; a version recorded
  // or written out. A manual eval's systems and a study's trials both make versions; this is where their history is read ──
  function screenPrompts(param) {
    const name = String(param || "");
    const head = `<div class="kicker">Prompts${name ? ` · ${esc(name)}` : ""}</div><h1>${name ? esc(name) : "Prompts"}</h1>
      <p class="lead">Each prompt's versions, each with who made it, what it was made from and the runs that sent it. A system points at a version; a study's trials make new ones.</p>`;
    const list = load("prompts", "/prompts");
    if (list === undefined) return `<div class="screen wide">${head}${loading("the prompts")}</div>`;
    if (list.error) return `<div class="screen wide">${head}${failed(list)}</div>`;
    const tbl = (h, rows) => `<div class="tablewrap"><table><thead><tr>${h.map((x) => `<th>${esc(x)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
    const names = list.prompts.map((x) => x.name);
    const listView = list.prompts.length ? tbl(["prompt", "versions", "runs", "latest"], list.prompts.map((x) => `<tr><td class="mono"><a href="#prompts/${enc(x.name)}">${esc(x.name)}</a>${x.name === name ? ' <span class="tag new">shown</span>' : ""}</td><td class="num">${x.versions}</td><td class="num">${x.runs}</td><td class="mono">${esc(x.latest || "")}</td></tr>`)) : '<p class="muted">No prompt versions yet: a system made in step 4 records its prompt, and a study\'s trials record theirs.</p>';
    if (!name || !names.includes(name)) return `<div class="screen wide">${head}${listView}${WB.cmd("evh prompt-list\nevh prompt-show --name <name> --text")}<div class="actions"><a class="btn" href="#home">Your goals</a></div></div>`;
    const pv = load(`prompt:${name}`, `/prompts/versions?name=${enc(name)}&text=true`);
    if (pv === undefined) return `<div class="screen wide">${head}${loading("its versions")}</div>`;
    if (pv.error) return `<div class="screen wide">${head}${failed(pv)}</div>`;
    const vs = pv.versions, ids = vs.map((x) => x.id), last = vs[vs.length - 1];
    const opt = (sel) => ids.map((x) => `<option value="${esc(x)}" ${x === sel ? "selected" : ""}>${esc(x)}</option>`).join("");
    const df = WB._pdiff && WB._pdiff.name === name ? WB._pdiff : null;
    return `<div class="screen wide">${head}${byField("pp6-by")}
      <section class="part"><div class="parthead"><span class="letter">1</span><h2>Its versions</h2></div><div class="body">
        ${vs.map((x) => `<details class="version" ${x === last ? "open" : ""}><summary><b>v${x.n}</b> <span class="mono">${esc(x.id)}</span> · ${esc(String(x.created_at || "").slice(0, 16).replace("T", " "))} · by ${esc(actorSaid(x.actor))}${x.parent ? ` · from <span class="mono">${esc(x.parent)}</span>` : ""} · ${x.runs.length} run(s)</summary>
          <p class="muted">${esc(x.note || "")}</p><pre class="reply">${esc(x.text || "")}</pre>
          ${x.runs.length ? tbl(["run", "measure", "score"], x.runs.map((r) => `<tr><td class="mono">${esc(r.run_id)}</td><td>${esc(r.metric || "")}</td><td class="num">${typeof r.score === "number" ? r.score.toFixed(4) : esc(r.score ?? "")}</td></tr>`)) : '<p class="muted">No run sent it yet.</p>'}</details>`).join("")}</div></section>
      <section class="part"><div class="parthead"><span class="letter">2</span><h2>What changed between two</h2></div><div class="body">
        ${ids.length > 1 ? `<div class="inline"><select id="pd-a" aria-label="from">${opt((df || {}).a || ids[ids.length - 2])}</select><span class="muted">to</span><select id="pd-b" aria-label="to">${opt((df || {}).b || ids[ids.length - 1])}</select><button class="btn" type="button" id="pd-go">Compare</button></div>
          <div id="pd-out" data-out>${df && df.diff ? `<pre class="reply diff">${esc(df.diff)}</pre>` : ""}</div>` : '<p class="muted">One version: nothing to compare yet.</p>'}</div></section>
      <section class="part"><div class="parthead"><span class="letter">3</span><h2>A new version</h2></div><div class="body" data-form="prompt-new">
        <p class="muted">Made from ${esc(last.id)}. A system points at it once it is recorded (step 4: clone a system, change its prompt).</p>
        <textarea id="pn-text" rows="5" style="width:100%" aria-label="its text">${esc(last.text || "")}</textarea>
        <input type="text" id="pn-note" placeholder="what changed and why" style="width:100%;margin-top:8px">
        <div class="actions" style="margin-top:8px"><button class="btn primary" type="button" id="pn-go" data-send>Record it</button>${mark}</div><div id="pn-out" data-out></div></div></section>
      <section class="part"><div class="parthead"><span class="letter">4</span><h2>Write one out</h2></div><div class="body">
        <p class="muted">A version as a file, for a project that keeps its prompts in its own repository to commit.</p>
        <div class="inline"><select id="px-id" aria-label="the version">${opt(last.id)}</select><input type="text" id="px-to" value="${esc(name.split("/").pop())}.txt" aria-label="its file name" autocapitalize="off" spellcheck="false"><button class="btn" type="button" id="px-go">Write it out</button></div><div id="px-out" data-out></div></div></section>
      ${WB.cmd(`evh prompt-show --name ${name} --text\nevh prompt-diff --a <id> --b <id>\nevh prompt-version --name ${name} --text "..." --parent ${last.id} --note "..."\nevh prompt-export --id <id> --to <file>`)}
      <div class="actions"><a class="btn" href="#prompts">Every prompt</a><a class="btn" href="#home">Your goals</a></div></div>`;
  }
  function wirePrompts() {
    const name = String(WB.param || "");
    const v = (id) => (document.getElementById(id)?.value || "").trim();
    const by = () => byOf("pp6-by") || (who() ? `person:${who()}` : null);
    document.getElementById("pd-go")?.addEventListener("click", async () => {
      const box = document.getElementById("pd-out");
      const r = await fetch(`/api/v1/prompts/diff?a=${enc(v("pd-a"))}&b=${enc(v("pd-b"))}`, { credentials: "same-origin" });
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { box.innerHTML = `<p class="note" role="alert">${esc(b.error || r.status)}</p>`; return; }
      const res = b.result || {};
      WB._pdiff = { name, a: v("pd-a"), b: v("pd-b"), diff: (res.diff || []).join ? (res.diff || []).join("") : String(res.diff || "") || "(the same text)" };
      WB.render();
    });
    holds("prompt-new", () => `Record a new version of ${name}`);
    document.getElementById("pn-go")?.addEventListener("click", async (ev) => {
      const box = document.getElementById("pn-out"), who_ = by();
      if (!who_) { box.innerHTML = '<p class="note" role="alert">Say who you are above: a version names who made it.</p>'; return; }
      if (!v("pn-note")) { box.innerHTML = '<p class="note" role="alert">Say what changed and why: a version keeps its note.</p>'; return; }
      const last = latestOf(LIVE.cache[`prompt:${name}`]);
      ev.target.disabled = true;
      try {
        const ver = await recordPrompt(name, document.getElementById("pn-text").value, last ? last.id : null, v("pn-note"), who_, box);
        if (ver) { sent("prompt-new"); forget(`prompt:${name}`); forget("prompts"); WB.render(true); }
      } catch (e) { box.innerHTML = refusal(e); }
      ev.target.disabled = false;
    });
    document.getElementById("px-go")?.addEventListener("click", async (ev) => {
      const box = document.getElementById("px-out"), who_ = by();
      if (!who_) { box.innerHTML = '<p class="note" role="alert">Say who you are above: a job names who asked.</p>'; return; }
      ev.target.disabled = true;
      try {
        const done = await runJob("/prompts/versions/export", { id: v("px-id"), to: v("px-to"), by: who_ }, box, "writing it out");
        if (done) box.innerHTML = `<p class="note">Written: <a class="mono" href="/api/v1/jobs/${enc(done.id)}/files/${enc((done.files || [])[0] || v("px-to"))}" download>${esc((done.files || [])[0] || v("px-to"))}</a></p>`;
      } catch (e) { box.innerHTML = refusal(e); }
      ev.target.disabled = false;
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
        <div class="actions"><button class="btn primary" type="button" id="lb-make">Make the sheet</button><a class="btn" href="#prepare/${enc(ds)}">Back</a></div><div id="lb-make-out" data-out></div>
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
        <button class="btn" type="button" id="lb-drop">Throw the sheet away</button></div><div id="lb-out" data-out></div>
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

  // ── links out: the catalog this server builds, and the harness's docs ───────────────────────
  const DOCS = "https://evals.humancopilot.eu/docs/";
  const screenOut = (title, href, what) => () => `<div class="screen"><div class="kicker">Out of the Workbench</div><h1>${esc(title)}</h1>
      <p class="lead">${esc(what)}</p><div class="actions"><a class="btn primary" href="${esc(href)}">Open it ↗</a><a class="btn" href="#home">Your goals</a></div></div>`;

  const WIRED = {
    home: [screenHome], goal: [() => screenGoal(WB.param || "")], glossary: null,
    models: [screenModels], model: [() => screenModel(WB.param || ""), wireModel], "model-new": [screenModelNew, wireModelNew],
    dataset: [() => screenDatasetNew(WB.param || ""), wireDatasetNew],
    "goal-new": [() => screenGoalForm(""), wireGoalForm], "goal-edit": [() => screenGoalForm(WB.param || ""), wireGoalForm],
    prepare: [() => screenPrepare(WB.param || ""), wirePrepare], label: [() => screenLabel(WB.param || ""), wireLabel],
    systems: [() => screenSystems(WB.param || ""), wireSystems], eval: [() => screenEval(WB.param || ""), wireEval],
    review: [() => screenReview(WB.param || ""), wireReview], production: [() => screenProduction(WB.param || ""), wireProduction],
    reference: [() => screenReference(WB.param || ""), wireReference], judge: [() => screenJudge(WB.param || ""), wireJudge],
    settings: [screenSettings, wireSettings], jobs: [() => screenJobs(WB.param || ""), wireJobs],
    heldout: [() => screenHeldout(WB.param || ""), wireHeldout], study: [() => screenStudies(WB.param || ""), wireStudies],
    prompts: [() => screenPrompts(WB.param || ""), wirePrompts],
    "production-labels": [() => screenProduction(WB.param || ""), wireProduction], "production-replay": [() => screenProduction(WB.param || ""), wireProduction],
    // the mockup's own routes, each the live screen it stands for: its goal hub is a goal's screen or the home, its
    // dataset sources are step 2's, its deployed goal is production
    hub: [screenHome], "production-live": [() => screenProduction(WB.param || ""), wireProduction],
    "dataset-hf": [() => screenDatasetNew(WB.param || ""), wireDatasetNew],
    catalog: [screenOut("The catalog", "/", "The pages this server builds over the project's runs, datasets and goals.")],
    docs: [screenOut("The docs", DOCS, "The harness's documentation: getting started, the tutorials, every command.")],
  };

  function goLive() {
    LIVE.on = true;
    document.body.classList.add("live");
    // a route the live Workbench does not have is the home
    for (const k of Object.keys(WB.routes)) if (!(k in WIRED)) WB.routes[k] = [screenHome];
    for (const [k, v] of Object.entries(WIRED)) if (v) WB.routes[k] = v;
    WB.routes.start = [screenHome];
    if (!location.hash || location.hash === "#start") location.hash = "#home";
    WB.render();
  }

  // Until the project answers, no screen is drawn. A refusal (its data at another format) is the project's: live. No
  // answer, or no API (404): the page was opened some other way, and says how to open it.
  const opening = (title, text) => `<div class="screen"><h1>${title}</h1><p class="lead">${text}</p></div>`;
  for (const k of Object.keys(WB.routes)) WB.routes[k] = [() => opening("Workbench", "Opening this project…")];
  WB.render(true);
  const noProject = () => {
    for (const k of Object.keys(WB.routes)) WB.routes[k] = [() => opening("Open it from your project", `The Workbench reads a project through <code>evh catalog-serve</code>: run it in the project and open the Workbench link it prints.`)];
    WB.render(true);
  };
  if (!location.pathname.startsWith("/workbench")) noProject();
  else {
    fetch("/api/v1/goals", { credentials: "same-origin" }).then((r) => {
      if (r.status === 404) noProject();
      else if (r.status !== 401) goLive();
      else {
        document.querySelector("#main").innerHTML = `<div class="screen"><h1>Sign in</h1><p class="lead">Open the Workbench through the link
          <code>evh catalog-serve</code> printed: it carries this server's token once and leaves a cookie.</p></div>`;
      }
    }).catch(noProject);
  }
})();
