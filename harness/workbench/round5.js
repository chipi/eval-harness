// The Workbench mockup, round 5: what 0.8.0 built after round 4 (RFC-026 to RFC-031): a goal's held-out test side and
// who has read it, a study, labels from what happened later, replaying the code that ran, and jobs as they are.
// Same rule as the other files: every value is the harness's own answer (MOCK.round5, read by mock_data.py from
// workbench/round5_inputs.py's throwaway projects); what is pretended is labelled.
(() => {
  const WB = window.WB;
  const { M, H, esc, $, q, cmd, note, save } = WB;
  const R = M.round5;
  const S = () => WB.S;
  const part = (letter, key, title, body, status) => `<section class="part">
    <div class="parthead"><span class="letter">${letter}</span><h2>${esc(title)}</h2>${key ? q(key) : ""}<span class="grow"></span>${status ? `<span class="status ${status.warn ? "warn" : "ok"}">${esc(status.text)}</span>` : ""}</div>
    ${key && H[key] && H[key].hint ? `<p class="hint">${esc(H[key].hint)}</p>` : ""}<div class="body">${body}</div></section>`;
  const head = (kicker, title, lead, key) => `<div class="kicker">${kicker}</div><h1>${esc(title)}</h1>${lead ? `<p class="lead hintable">${lead} ${key ? q(key) : ""}</p>` : ""}`;
  const back = (href = "#hub", label = "Back to the goal") => `<a class="btn" href="${href}">${label}</a>`;
  const n4 = (x) => (x === null || x === undefined ? "—" : Number(x).toFixed(4));
  const pct = (x) => `${(100 * x).toFixed(2)}%`;
  const day = (x) => String(x || "").slice(0, 10);
  const table = (cols, rows) => `<div class="tablewrap"><table><thead><tr>${cols.map((c) => `<th${c.num ? ' class="num"' : ""}>${esc(c.t || c)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;

  // ── a goal's held-out test side: sealed, who has read it, counts for safety, one candidate, the confirmation ──
  function screenHeldout() {
    const ex = R.exposure || {}, pr = R.heldout_pair || {}, chk = R.exposure_check || {};
    const counts = ((R.sealed_counts || {}).counts || {})["held-out items"] || {};
    const days = Object.keys(counts).sort();
    const kinds = [...new Set(days.flatMap((d) => Object.keys(counts[d]).filter((k) => k !== "n")))].sort();
    const left = Object.values(pr.left_out_exposed || {})[0] || 0;
    const s = S(), h = s.heldout || {};
    return `<div class="screen wide">
      ${head(`Day to day · ${esc(ex.dataset_id || "")} · the held-out test`, "The held-out test", "Items kept back from tuning until one candidate is named, so the last number is a fair one. A seal stops runs and labels on them; reads it cannot stop, so they are recorded, and every score here leaves the read items out.", "heldout.what")}
      ${part("1", "heldout.seal", "The seal", `<div class="stats"><div><b>${ex.items}</b><span>held-out items</span></div><div><b>sealed</b><span>at the split's boundary</span></div><div><b>kind</b><span>what its counts may show</span></div></div>
        <div class="note">Split by time: every item on or after the boundary is held out; a run, a label sheet or a reference on it is refused until a candidate is named in advance.</div>`, { text: "sealed" })}
      ${part("2", "heldout.reads", "Who has read it", `<div class="stats"><div><b>${ex.exposed} of ${ex.items}</b><span>items read</span></div><div><b>${ex.reads}</b><span>reads recorded</span></div><div><b>${ex.items - ex.exposed}</b><span>still unread</span></div></div>
        ${table(["who read", { t: "reads", num: true }], Object.entries(ex.by || {}).map(([k, v]) => `<tr><td class="mono">${esc(k)}</td><td class="num">${v}</td></tr>`))}
        ${table(["what was read", { t: "reads", num: true }], Object.entries(ex.what || {}).map(([k, v]) => `<tr><td>${esc(k)}</td><td class="num">${v}</td></tr>`))}
        ${h.read ? `<div class="note">Read recorded: ${esc(h.read)}.</div>` : `<div class="inline"><input type="text" id="readwhat" placeholder="what was read: the decision and its reason, a label in a fixture…" style="width:360px"><button class="btn" type="button" id="readadd">Record a read</button></div>`}
        <div class="note">The leak check searched the public repos for these items' ids: ${chk.named} named after its time, ${chk.new} not yet in the register (written to a file to record, never printed). It cannot catch a paraphrase, a title, or a list written without the ids' prefix.</div>
        ${note("one read here was recorded by hand (an agent's); the other is the leak check's find, recorded from the file it wrote. A read the harness itself shows (an item's text, an output, a label sheet) is recorded with whoever ran it.")}`, { text: `${ex.exposed} read`, warn: ex.exposed > 0 })}
      ${part("3", "heldout.counts", "Counts, for safety only", `${table(["day", { t: "items", num: true }, ...kinds.map((k) => ({ t: k, num: true }))], days.map((d) => `<tr><td class="mono">${esc(d)}</td><td class="num">${counts[d].n}</td>${kinds.map((k) => `<td class="num">${counts[d][k] || ""}</td>`).join("")}</tr>`))}`)}
      ${part("4", "heldout.unseal", "Open it for one candidate", `${(R.unseal || []).map((l) => `<div class="mono" style="font-size:12px">${esc(l.trim())}</div>`).join("")}
        <div class="note">The candidate's config and its hypothesis (what it is against, the measure, the direction) were committed first; opening it is one look at this test set, and every later look is tested at a stricter level.</div>`, { text: "look 1" })}
      ${part("5", "heldout.confirm", "The confirmation", `${table(["", { t: "items", num: true }, { t: "delta (A − B)", num: true }, { t: "p", num: true }, "verdict"], [
        `<tr><td><b>the number that counts</b> <span class="muted">(${left} read items left out)</span></td><td class="num">${pr.n}</td><td class="num">${pr.delta >= 0 ? "+" : ""}${n4(pr.delta)}</td><td class="num">${n4(pr.p)}</td><td><span class="verdict v-ns">${esc((pr.verdict || "").toLowerCase())}</span></td></tr>`,
        pr.with_exposed ? `<tr class="muted"><td>with the read items kept (not the one that counts)</td><td class="num">${pr.with_exposed.n}</td><td class="num">${pr.with_exposed.delta >= 0 ? "+" : ""}${n4(pr.with_exposed.delta)}</td><td class="num">—</td><td></td></tr>` : "",
      ])}`)}
      <div class="actions">${back()}</div>
      ${note("the held-out side is the tutorial's tickets split at 2026-11-02, sealed, two of its items read, opened for a two-sentence candidate: every number above is the harness's own answer in a throwaway project (workbench/round5_inputs.py).")}
      ${cmd(`evh dataset-split <dataset> --split-by time --key opened --at <T> --seal --count-by kind\nevh exposure-add --dataset-id <dataset>_test --item <id> --what "…" --read-by agent:<name>\nevh exposure --dataset-id <dataset>_test\nevh exposure-check --dataset-id <dataset>_test --out leaks.tsv\nevh sealed-counts --dataset-id <dataset>_test\nevh dataset-unseal <dataset>_test --config <candidate> --reason "…"\nevh pair-test --dataset-id <dataset>_test --a <candidate> --b <baseline> --include-exposed`)}
    </div>`;
  }
  function wireHeldout() {
    const s = S(); s.heldout = s.heldout || {};
    $("#readadd")?.addEventListener("click", () => { const v = $("#readwhat").value.trim(); if (!v) { $("#readwhat").focus(); return; } s.heldout.read = v; save(); WB.render(); });
  }

  // ── a study: the search a person or an agent runs, ending in one look at the test set ──
  function screenStudy() {
    const st = R.study || {}, c = R.confirm || {}, lk = c.look || {};
    const trials = st.trials || [];
    return `<div class="screen wide">
      ${head(`Day to day · ${esc(st.goal || "")} · a study`, "A study", "A search over one thing at a time, measured against the best so far on the validation set; it never promotes. When it ends, its best is confirmed once on the test set: one look.", "study.what")}
      ${part("1", "study.spec", "What it searches", `<div class="stats"><div><b>${esc(st.baseline || "")}</b><span>from the baseline</span></div><div><b>grid</b><span>how it chooses</span></div><div><b>${trials.length}</b><span>trials</span></div><div><b>${esc(st.status || "")}</b><span>its state</span></div></div>`)}
      ${part("2", "study.trials", "Its trials", table(["trial", "what changed", "outcome", "why"], trials.map((t) => `<tr><td class="mono">t${t.k}</td><td>${esc(Object.entries((t.change || {}).params || {}).map(([k, v]) => `${k} ${v}`).join(", "))}</td><td><span class="verdict ${t.outcome === "kept" ? "v-lead" : "v-ns"}">${esc(t.outcome || "")}</span></td><td>${esc(t.reason || "")}</td></tr>`)) +
        `<div class="note">Best so far: <span class="mono">${esc((st.best || {}).config_id || st.baseline || "")}</span>.</div>`)}
      ${part("3", "study.confirm", "Confirm it on the test set: one look", `${table([{ t: "test items", num: true }, { t: "delta", num: true }, { t: "p (one-sided)", num: true }, "level", "outcome"], [`<tr><td class="num">${c.n}</td><td class="num">+${n4(c.delta)}</td><td class="num">${n4(c.p_one_sided)}</td><td class="num">look ${lk.number} at ${pct(lk.level || 0)}</td><td><span class="verdict v-lead">${esc(c.outcome || "")}</span></td></tr>`])}
        <div class="note">The rule (${esc(c.rule || "")}) is named before any test item is read; each look at a test set is tested at a stricter level, so a set used often stops being able to confirm anything.</div>`)}
      <div class="actions">${back()}</div>
      ${note("a grid study on twelve tickets (sentences 2, 3, 4 against a one-sentence baseline) and its confirmation on twelve more: the harness's own answers in a throwaway project.")}
      ${cmd(`evh study-run <goal>/<id> --spec study.yaml [--dry-run]\nevh studies --study <goal>/<id>\nevh study-stop <goal>/<id>\nevh study-confirm <goal>/<id> --test <test set> --rule superiority\nevh looks --dataset <test set>`)}
    </div>`;
  }

  // ── production: labels from what happened later, in other systems ──
  function screenProductionLabels() {
    const cov = R.label_coverage || {}, src = (R.label_set || {}).source || {}, items = (R.label_set || {}).items || {};
    const outs = Array.isArray(src.outcomes) ? src.outcomes : [], cn = cov.counts || {}, mu = R.label_mutants || {};
    const joined = (o) => `<div class="stats"><div><b>${esc(o.as || o.capture || "")}</b><span>read as, from capture ${esc(o.capture || "")}</span></div><div><b class="mono">${esc(o.join || "")}</b><span>joined by</span></div><div><b class="mono">${esc(o.within || "—")}</b><span>within, after the decision</span></div><div><b class="mono">${esc(o.identity || "—")}</b><span>and the same object</span></div></div>`;
    const said = { labelled: "labelled now", skipped: "skipped by design", not_mature: "not yet mature", unmatched: "no rule matches", no_record: "not in the capture", gone: "gone from the source, or its id reused" };
    return `<div class="screen wide">
      ${head("Production · labels", "Labels from what happened later", "A decision's outcome often lives in another system (the issue it filed, the errors that followed) and some outcomes take time to show. Read that system once, as a capture of its own, and join it to the decisions.", "plabels.what")}
      ${part("1", "plabels.join", "Joined from other systems", `${outs.map(joined).join("")}
        <div class="note">Each system is read once, as a capture of its own, kept, hashed and dated (read ${outs.map((o) => esc(day(o.captured_at))).join(", ")}); the rules read each under its name (<span class="mono">issue.state_reason</span>). Another system is another <span class="mono">--outcomes</span>, with its own join.</div>`)}
      ${part("2", "plabels.coverage", "How far the rules label it now", table(["", { t: "items", num: true }], Object.entries(said).map(([k, t]) => `<tr><td>${esc(t)}</td><td class="num">${cn[k] || 0}</td></tr>`)) +
        `<div class="note">An item still maturing waits for its window ("not seen again within 14 days" is knowable only then); one whose outside record is gone, or whose id now names another object, is never labelled.</div>`)}
      ${part("3", "plabels.dates", "Each label, with two dates", table(["decision", "label", "happened", "knowable", "holds only under"], Object.entries(items).map(([id, r]) => `<tr><td class="mono" style="font-size:12px">${esc(id)}</td><td>${esc(r.label || "")}</td><td class="mono">${esc(day(r.happened_at)) || "—"}</td><td class="mono">${esc(day(r.knowable_at))}</td><td>${r.under_action ? `production's <b>${esc(r.under_action)}</b>` : "any action"}</td></tr>`)) +
        `<div class="note">A label that holds only under production's action (an issue's close reason exists because production filed it) is not scored for a variant that acted otherwise: "not scorable under this variant", counted. A relabel later keeps these, adds what matured and marks any that changed.</div>`)}
      ${part("4", "plabels.mutants", "Is the labeller right? Its mutants", table(["a change to the rules or the join", { t: "labels moved", num: true }, ""], (mu.mutants || []).map((m) => `<tr><td>${esc(m.mutant)}</td><td class="num">${m.moved}</td><td>${m.moved ? '<span class="verdict v-lead">caught</span>' : '<span class="verdict v-worse">survived</span>'}</td></tr>`)) +
        `<div class="note">A change that moves no label is a finding: the labelled decisions do not reach what it changes. Read why before trusting the labels.</div>`, (mu.survived || []).length ? { text: `${mu.survived.length} survived`, warn: true } : null)}
      <div class="actions">${back("#production-live", "Back to production")}</div>
      ${note("six decisions joined to the issues they filed: the harness's own answers in a throwaway project (workbench/round5_inputs.py).")}
      ${cmd(`evh capture --importer <the other system's> --capture issues\nevh label-coverage --dataset-id <d> --capture <decisions> --map rules.yaml --outcomes issues --outcomes-as issue --join fp=fp --within -1m,+15m --identity first_seen=first_seen\nevh label-from-capture … --set outcomes_1 --action-field action\nevh label-from-capture … --set outcomes_2 --from-set outcomes_1     # a relabel: adds what matured\nevh label-mutants --dataset-id <d> --capture <decisions> --map rules.yaml --outcomes issues … [--mutants mine.py]`)}
    </div>`;
  }

  // ── production: replay the code that ran, and a past period beside a candidate ──
  function screenProductionReplay() {
    const f = R.faithfulness || {}, sc = R.replay_scores || {}, rec = (R.code_records || [])[0] || {};
    const cf = sc.confound || {};
    return `<div class="screen wide">
      ${head("Production · replay", "Replay the code that ran", "Run the system's own code over its recorded history, each decision at the version deployed then, against the world as it was. Prove the replay reproduces production before scoring it; then a candidate is compared fairly, period by period.", "preplay.what")}
      ${part("1", "preplay.record", "The code under test", `<div class="stats"><div><b class="mono">${esc(rec.model || "")}</b><span>its code record</span></div><div><b>${esc(rec.onboarding || "")}</b><span>versions</span></div><div><b>${esc(rec.goals || "")}</b><span>its goal</span></div></div>
        ${table(["period", "from", "to", "commit", { t: "decisions", num: true }, "faithful"], (R.periods || []).map((p) => `<tr><td class="num">${p.period}</td><td class="mono">${esc(day(p.from))}</td><td class="mono">${esc(day(p.to)) || "now"}</td><td class="mono">${esc((p.commit || "").slice(0, 12))}</td><td class="num">${p.items}</td><td>${p.faithfulness ? `${p.faithfulness.agreed} of ${p.faithfulness.items}` : "—"}${p.dated_by === "commit" ? ' <span class="tag">dated by commit time</span>' : ""}</td></tr>`))}`)}
      ${part("2", "preplay.faith", "Does the replay reproduce production?", `<div class="stats"><div><b>${(f.counts || {}).agree} of ${(f.counts || {}).items}</b><span>decisions agree</span></div><div><b>${Object.keys(f.commits || {}).length}</b><span>commits, each unpacked once</span></div><div><b>reopened</b><span>production's own writes hidden</span></div></div>
        <div class="note">Production's own reopens inside the replayed window are hidden from the world the replay reads; the replay's own stand in for them, and people's closes stay. Hidden or not, the replay must agree with production on every decision (or each disagreement is named) before it may be scored.</div>`, { text: "faithful" })}
      ${part("3", "preplay.confound", "A candidate, and what history cannot hide", `${table(["", { t: "exact", num: true }, "history confound"], [
        `<tr><td>the code that ran (replayed)</td><td class="num">${n4(sc.replay)}</td><td>${(sc.replay_confound || {}).items || 0} of ${(sc.replay_confound || {}).of || 0}</td></tr>`,
        `<tr><td>the candidate (one later commit, every decision)</td><td class="num">${n4(sc.candidate)}</td><td><b>${cf.items} of ${cf.of}</b></td></tr>`,
      ])}<div class="note">Where the candidate acted otherwise and a person later reacted to what production did, its score reads a reaction to another decision: those items are named beside the run, never for a held-out side.</div>`, cf.items ? { text: `${cf.items} confounded`, warn: true } : null)}
      ${part("4", "preplay.periods", "Period by period", table(["period", { t: "decisions", num: true }, { t: "production", num: true }, { t: "the code then", num: true }, { t: "the candidate", num: true }, { t: "difference", num: true }, { t: "p", num: true }, "counts"], (R.period_compare || []).map((p, i) => `<tr><td>${esc(p.period || `period ${i + 1}`)}</td><td class="num">${p.items}</td><td class="num">${n4(p.production)}</td><td class="num">${n4(p.as_run)}</td><td class="num">${n4(p.candidate)}</td><td class="num">${p.delta >= 0 ? "+" : ""}${n4(p.delta)}</td><td class="num">${n4(p.p)}</td><td>${p.counts ? "yes" : "<b>no</b>: the replay disagrees there"}</td></tr>`)) +
        `<div class="note">A window over several deployments mixes a fix's before and after: compare each period at the code that ran then.</div>`)}
      <div class="actions">${back("#production-live", "Back to production")}</div>
      ${note("the replay example's filing system (20 decisions, three versions): the harness's own answers in a throwaway project (workbench/round5_inputs.py).")}
      ${cmd(`evh faithfulness --config data/configs/<replay>.yaml --production <production's run>\nevh run --config data/configs/<replay>.yaml\nevh run --config data/configs/<candidate>.yaml\nevh periods --model <code record> --config data/configs/<replay>.yaml\nevh period-compare --config data/configs/<replay>.yaml --candidate <candidate> --production <production> --period 2\nevh label-from-capture … --reproduced-by <replay run> --production <production's run>`)}
    </div>`;
  }

  // ── jobs, as RFC-026 has them ──
  function screenJobsReal() {
    const jobs = (S().jobs || []).slice().reverse(), real = R.jobs || [];
    return `<div class="screen wide">${head("Jobs", "Jobs", "Every step that runs is a job: its cost first, then its progress and log, then its result. A job keeps running when the page closes, can be watched again, stopped, and a run resumed with what the stopped job left of its cap.", "jobs.what")}
      ${jobs.length ? `<div class="tablewrap"><table><thead><tr><th>job</th><th>status</th><th>started</th><th class="num">progress</th><th></th></tr></thead><tbody>
        ${jobs.map((j) => `<tr><td class="mono">${esc(j.name)}</td><td><span class="verdict ${j.status === "done" ? "v-lead" : "v-ns"}">${esc(j.status)}</span></td><td class="num">${esc(j.started)}</td><td class="num">${j.n} / ${j.total} ${esc(j.unit)}</td><td>${j.status === "running" ? '<button class="btn" type="button" disabled>Stop</button>' : j.resumable ? '<button class="btn" type="button" disabled>Resume</button>' : ""}</td></tr>`).join("")}</tbody></table></div>`
        : '<p class="muted">No jobs yet in this walk-through. They appear here as you fetch, check arms, run and score.</p>'}
      <h2 style="margin:24px 0 8px">A real job</h2>
      ${table(["job", "command", "state", "who", { t: "cap", num: true }, "holds"], real.map((j) => { const st = R.job_started && R.job_started.id === j.id ? R.job_started : {};
        return `<tr><td class="mono" style="font-size:12px">${esc(j.id)}</td><td class="mono">${esc(j.command)} ${esc((j.argv || []).join(" "))}</td><td><span class="verdict v-lead">${esc(j.state)}</span></td><td class="mono">${esc(j.by || "")}</td><td class="num">${(st.env || {}).EVAL_MAX_COST_USD ? `$${Number(st.env.EVAL_MAX_COST_USD).toFixed(2)}` : "—"}</td><td class="mono" style="font-size:12px">${(st.locks || []).map(([k, ex]) => `${esc(k)}${ex ? " (alone)" : ""}`).join(", ")}</td></tr>`; }))}
      <div class="note">A job that spends carries its cap; a job waits, named, while another holds what it writes (queued); a job whose supervisor stopped reads "running (unsupervised)" while its command lives, "lost" after.</div>
      ${note("the walk-through's jobs above are pretended; the job below them is a real one, run in a throwaway project.")}
      ${cmd(`evh jobs-start run --arg config=<arm> --max-cost-usd 1\nevh jobs-status [JOB]\nevh jobs-logs JOB --follow\nevh jobs-stop JOB\nevh jobs-resume JOB`)}</div>`;
  }

  // ── the goal hub's and the rail's new day-to-day places ──
  const DAY = [["heldout", "The held-out test", "items kept back until one candidate is named: the seal, who has read them, the confirmation"], ["study", "A study", "a search over one thing at a time, confirmed once on the test set"]];
  WB.dayToDay = (WB.dayToDay || []).concat(DAY);

  Object.assign(WB.routes, {
    heldout: [screenHeldout, wireHeldout],
    study: [screenStudy],
    "production-labels": [screenProductionLabels],
    "production-replay": [screenProductionReplay],
    jobs: [screenJobsReal],
  });
})();
