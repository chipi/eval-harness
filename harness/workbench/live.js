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
    const jobs = load("jobs", "/jobs?state=running", true);
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
      : jobs.jobs.length ? jobs.jobs.map((j) => `<div class="job"><span>${esc(j.command)}</span><span class="status">${esc(j.state)}</span></div>`).join("")
      : '<p class="muted" style="margin:0">Nothing is running.</p>';
    return `<div class="screen wide">${head}
      <div class="part"><div class="parthead"><h2>Running now</h2></div><div class="body">${running}</div></div>
      ${goals.goals.length ? `<div class="tablewrap" style="margin-top:18px"><table><thead><tr><th>goal</th><th>decides</th><th>datasets</th><th class="num">rounds</th><th>next</th></tr></thead><tbody>${rows.join("")}</tbody></table></div>`
        : `<p class="muted" style="margin-top:18px">No goals yet: <code>evh goal-new</code> makes one (the form here is wired with W4).</p>`}
      <div class="actions"><a class="btn" href="#models">Models</a><a class="btn" href="${location.origin}/">The catalog ↗</a></div></div>`;
  }

  // ── a goal: where it stands, and the next step ─────────────────────────────
  function screenGoal(id) {
    const st = load(`status:${id}`, `/goals/${encodeURIComponent(id)}/status`);
    const head = `<div class="kicker">Goal · ${esc(id)}</div>`;
    if (st === undefined) return `<div class="screen wide">${head}${loading("the goal")}</div>`;
    if (st.error) return `<div class="screen wide">${head}${failed(st)}<div class="actions"><a class="btn" href="#home">Back to your goals</a></div></div>`;
    const m = st.measure || {};
    const ds = st.datasets.map((d) => `<tr><td class="mono">${esc(d.dataset)}</td><td>${esc(d.role || "")}${d.decides ? "" : " · does not decide"}</td>
      <td>${d.made ? (d.materialized ? "made, fetched" : "made, not fetched") : "not made"}</td><td>${d.references.length ? d.references.map(esc).join(", ") : "—"}</td>
      <td class="num">${d.runs} run(s) · ${d.arms} arm(s)</td><td>${d.baseline ? `v${d.baseline.version}` : "—"}</td></tr>`).join("");
    const rounds = st.rounds.map((r) => `<li><b>${esc(r.round)}</b> ${esc(r.status)}: ${esc(r.question || "")}</li>`).join("");
    return `<div class="screen wide">${head}<h1>${esc(st.title || id)}</h1>
      <p class="lead">Decides on ${esc(m.measure || "")} (${esc(m.direction || "")} is better).</p>
      <div class="answer"><div class="kicker">next step</div><p>${esc(st.next.what)}</p><p class="source"><code>${esc(st.next.command)}</code></p></div>
      <div class="tablewrap" style="margin-top:18px"><table><thead><tr><th>dataset</th><th>role</th><th>items</th><th>reference</th><th class="num">runs</th><th>baseline</th></tr></thead><tbody>${ds}</tbody></table></div>
      ${rounds ? `<h2 style="margin-top:22px">Rounds</h2><ul>${rounds}</ul>` : ""}
      ${st.running.length ? `<h2 style="margin-top:22px">Running now</h2><ul>${st.running.map((j) => `<li>${esc(j.command)} · ${esc(j.state)}</li>`).join("")}</ul>` : ""}
      ${WB.cmd(`evh goal-status ${id}`)}
      <div class="actions"><a class="btn" href="#home">Back to your goals</a></div></div>`;
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
        ${on && on.status === "check" ? `<h3>Accept what it raises</h3>
          <p class="muted">When a flag is the deployment's own nature (a hosted gateway has no build to pin), accept it with why: it is kept in its checks and no longer counts against it.</p>
          <div class="field"><label class="name" for="flag-${esc(k)}">The flag's kind</label><div><input type="text" id="flag-${esc(k)}" placeholder="the words before its colon: reasoning, where it ran"></div></div>
          <div class="field"><label class="name" for="why-${esc(k)}">Why</label><div><input type="text" id="why-${esc(k)}" placeholder="a sentence"></div></div>
          ${byField(`by-${k}`)}
          <div class="actions" style="margin-top:0"><button class="btn" type="button" data-accept="${esc(k)}">Accept it</button></div>
          <div id="acc-${esc(k)}"></div>` : ""}
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
      <section class="part"><div class="parthead"><h2>Add a deployment</h2></div><div class="body">
        <div class="field"><label class="name" for="dep-id">Its id</label><div><input type="text" id="dep-id" placeholder="mac, dgx, openrouter"></div></div>
        <div class="field"><label class="name" for="dep-where">Where</label><div><input type="text" id="dep-where" placeholder="the machine, or the hosted route"></div></div>
        <div class="field"><label class="name" for="dep-tag">Its tag</label><div><input type="text" id="dep-tag" placeholder="the name the server knows it by"></div></div>
        <div class="field"><label class="name" for="dep-url">Its address</label><div><input type="text" id="dep-url" placeholder="http://host:11434/v1" inputmode="url"></div></div>
        ${byField("dep-by")}
        <div class="actions" style="margin-top:0"><button class="btn" type="button" id="dep-add">Add it</button></div><div id="dep-out"></div></div></section>
      ${WB.cmd(`evh model-show ${id}\nevh model-onboard ${id} --deployment <deployment>\nevh deployment-accept ${id} <deployment> --flag "<kind>" --why "<a sentence>"`)}
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
    document.querySelectorAll("[data-onboard]").forEach((b) => b.addEventListener("click", async () => {
      const dep = b.dataset.onboard, out = document.getElementById(`job-${dep}`);
      const cap = Number(document.getElementById(`cap-${dep}`).value);
      if (!(cap > 0)) { out.innerHTML = '<p class="note" role="alert">Say the most the probes may spend first.</p>'; return; }
      b.disabled = true;
      try {
        const j = await send("POST", "/jobs", { command: "model-onboard", args: { model_id: id, deployment: dep }, by: byOf(`by-${dep}`) || (who() ? `person:${who()}` : undefined), max_cost_usd: cap });
        follow(id, dep, j.id);
      } catch (e) { out.innerHTML = refusal(e); b.disabled = false; }
    }));
    document.querySelectorAll("[data-accept]").forEach((b) => b.addEventListener("click", async () => {
      const dep = b.dataset.accept, out = document.getElementById(`acc-${dep}`), by = byOf(`by-${dep}`);
      if (!by) { out.innerHTML = '<p class="note" role="alert">Say who you are: an acceptance names who made it.</p>'; return; }
      try {
        await send("POST", `/models/${enc(id)}/deployments/${enc(dep)}/accept`, { flag: document.getElementById(`flag-${dep}`).value, why: document.getElementById(`why-${dep}`).value, by });
        forget(`model:${id}`); forget("models"); WB.render();
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
        forget(`model:${id}`); forget("models"); WB.render();
      } catch (e) { out.innerHTML = refusal(e); }
    });
  }

  // ── bring in a model: what it is, then where it runs on its own page ──────────────────────────
  function screenModelNew() {
    return `<div class="screen"><div class="kicker">Models · bring one in</div><h1>Bring in a model</h1>
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
      <div class="actions"><button class="btn primary" type="button" id="nm-save">Make it</button><a class="btn" href="#models">The models</a></div>
      <div id="nm-out"></div>
      ${WB.cmd("evh model-new <id> --set kind=llm --set aliases.0=<the id runs record>")}</div>`;
  }
  function wireModelNew() {
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
        forget("models");
        location.hash = `#model/${enc(id)}`;
      } catch (e) { out.innerHTML = refusal(e); }
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
    fetch("/api/v1/goals", { credentials: "same-origin" }).then((r) => {
      if (r.ok) goLive();
      else if (r.status === 401) {
        document.querySelector("#main").innerHTML = `<div class="screen"><h1>Sign in</h1><p class="lead">Open the Workbench through the link
          <code>evh catalog-serve</code> printed: it carries this server's token once and leaves a cookie.</p></div>`;
      }
    });
  }
})();
