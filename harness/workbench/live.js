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
      <div class="actions"><a class="btn" href="${location.origin}/">The catalog ↗</a></div></div>`;
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

  // ── a screen not wired yet: says which step wires it ───────────────────────
  function screenLater() {
    return `<div class="screen"><div class="kicker">Not wired yet</div><h1>This screen comes later</h1>
      <p class="lead">The Workbench is wired to your project a workflow at a time (RFC-032's build order). This screen still
      shows the mockup's walk-through, read from the harness's own repository, so it is not shown here.</p>
      <div class="actions"><a class="btn primary" href="#home">Your goals</a></div></div>`;
  }

  const WIRED = { home: [screenHome], goal: [() => screenGoal(WB.param || "")], glossary: null };

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
