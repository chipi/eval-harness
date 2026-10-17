"""The method page, the "use it on your problem" page, and the pieces of them that the
landing and experiment pages borrow.

The findings are the hook; the method is the point. These pages tell the six habits as
the experiments taught them, then show how to apply them to a problem of your own.

Same rules as build.py: every number typed into quoted prose goes through `q()` and must
appear in the report (or guide) it cites; everything else is computed from the runs.
Helpers arrive as a namespace `H` from build.py, so this module never imports it.
"""

from __future__ import annotations

SUMM = "research/REPORT_SUMMARIZATION.md"
CLASS = "research/REPORT_CLASSIFICATION.md"
NER = "research/REPORT_NER.md"
RET = "research/REPORT_RETRIEVAL.md"
SYN = "research/REPORT_SYNTHESIS.md"
GUIDE = "docs/GUIDE.md"

# ── the lifecycle, shared by both pages ─────────────────────────────────────
#: id, label, sub-label, what it is, where it lives, the command, the guide section
NODES = [
    ("sources", "Sources", "your inputs",
     "Any files: tickets, transcripts, documents, prompts. Keep them under version control "
     "— an untracked input makes every run unattributable.",
     "data/sources/ — or anywhere", "", "1-freeze-a-dataset"),
    ("dataset", "Dataset", "frozen · sha256",
     "The comparison contract: an item list with the hash of every item. Two runs on "
     "different datasets cannot be compared, and a changed input is a new version.",
     "data/datasets/&lt;id&gt;.json", 'make dataset-create DATASET_ID=tickets_v1', "1-freeze-a-dataset"),
    ("materialized", "Materialized", "hash-checked copy",
     "A working copy, re-verified against the frozen hashes every time — so a run can "
     "never measure bytes the dataset does not describe.",
     "data/materialized/&lt;id&gt;/", "make dataset-materialize DATASET_ID=tickets_v1", "2-materialize"),
    ("references", "References", "silver · gold",
     "What each item is scored against. Silver: a model wrote it — consistent, not correct. "
     "Gold: a person wrote or checked it. Gold always wins, and every run says which it used.",
     "data/references/&lt;tier&gt;/&lt;id&gt;/", "make reference-create DATASET_ID=… CONFIG=…",
     "4-author-silver-references"),
    ("arms", "Arms", "one config each",
     "One system under test: provider, model, prompt, settings, in a YAML file. Change one "
     "thing, bump the config_id — the fingerprint will prove what moved.",
     "data/configs/*.yaml", "", "3-describe-your-arms"),
    ("runs", "Runs", "outputs + fingerprint",
     "One pass of an arm over the dataset: every output, every per-item score, billed cost, "
     "latency, and a fingerprint of data, code, model and build. Repeat it to measure noise.",
     "data/runs/&lt;run_id&gt;/", "make experiment-run CONFIG=… REPEAT=3", "5-commit-then-measure"),
    ("tests", "Tests", "separated or tied",
     "The leaderboard with its significance block, paired tests, Holm-corrected families. "
     "A claim means separated, not scored higher.",
     "your terminal", "make family-test DATASET_ID=… A=… AGAINST=…", "8-decide-is-the-winner-separated"),
    ("baseline", "Baseline", "a decision + reason",
     "The run future changes are measured against, recorded with why. Superseded, never "
     "edited — in six months, “why is this the baseline?” has an answer.",
     "data/baselines/", 'make run-promote RUN=… REASON="…"', "9-promote-a-baseline"),
]


def lifecycle(interactive: bool = False) -> str:
    """The pipeline as a vertical diagram. Nodes carry data-node so a page can light them."""
    w, bh, step, x = 300, 54, 76, 20
    parts = []
    for i, (nid, label, sub, *_rest) in enumerate(NODES):
        y = 12 + i * step
        if i:
            parts.append(f'<path class="lc-edge" d="M{w/2} {y - step + bh + 4} V{y - 6}"/>'
                         f'<path class="lc-head" d="M{w/2 - 5} {y - 11} L{w/2} {y - 5} L{w/2 + 5} {y - 11}"/>')
        node = (f'<rect x="{x}" y="{y}" width="{w - 2 * x}" height="{bh}" rx="10"/>'
                f'<text class="lc-label" x="{x + 18}" y="{y + 24}">{label}</text>'
                f'<text class="lc-sub" x="{x + 18}" y="{y + 42}">{sub}</text>'
                f'<text class="lc-num" x="{w - x - 16}" y="{y + 24}" text-anchor="end">{i + 1:02d}</text>')
        if interactive:
            parts.append(f'<a href="#lc-{nid}" class="lc-node" data-node="{nid}" '
                         f'aria-label="{label}: {sub}">{node}</a>')
        else:
            parts.append(f'<g class="lc-node" data-node="{nid}">{node}</g>')
    h = 12 + len(NODES) * step
    return (f'<svg class="lc" viewBox="0 0 {w} {h}" role="img" aria-label="The evaluation '
            f'lifecycle: sources, dataset, materialized copy, references, arms, runs, tests, '
            f'baseline">{"".join(parts)}</svg>')


def lifecycle_panels(H) -> str:
    out = []
    for nid, label, sub, what, where, cmd, anchor in NODES:
        cmd_html = (f'<pre class="term"><span class="p">$ </span>{H.e(cmd)}</pre>' if cmd else "")
        out.append(
            f'<div class="lc-panel" id="lc-{nid}" data-node="{nid}">'
            f'<div class="eyebrow"><span class="num">{label}</span>{sub}</div>'
            f'<p>{what}</p><div class="lc-where"><span>lives in</span> <code>{where}</code></div>'
            f'{cmd_html}<a class="lc-more" href="docs/GUIDE/#{anchor}">In the guide →</a></div>')
    return "".join(out)


# ── the six habits ──────────────────────────────────────────────────────────
def chapters(H, f: dict) -> list:
    exps = f["experiments"]
    by = {x["slug"]: x for x in exps}
    ties = sum(x["n_tied"] > 0 for x in exps)
    s = by["summarization"]
    sf = by["scifact"]
    return [
        {"id": "experiment", "nodes": "arms runs", "kicker": "Experiment",
         "title": "An eval is an experiment.",
         "short": "Vary one thing. Record everything else.",
         "story": (f"<p>The same {max(x['n_hosted'] for x in exps)} hosted models ran on five tasks with one prompt per "
                   "task, at temperature 0 with reasoning off — so when a model's score differs "
                   "between two tasks, the task is the only thing that changed.</p>"
                   "<p>Every run carries a <strong>fingerprint</strong>: hashes of the data, the "
                   "prompt and the scoring code, the model behind the alias, library versions, "
                   "the commit. Before the harness shows a single delta between two runs, it "
                   "lists the fields that moved.</p>"),
         "habit": "Change one thing per arm, and record everything else — so “we only changed "
                  "the prompt” is checkable rather than claimed.",
         "tool": ("make run-compare BASE=… CAND=…",
                  "Fingerprints DIFFER. Fields that moved: arm.params.sentences"),
         "yours": "Your arms are your candidates — prompts, models, retrieval settings, "
                  "thresholds — one YAML file each."},
        {"id": "data", "nodes": "sources dataset materialized", "kicker": "Data",
         "title": "The data is the instrument.",
         "short": "Freeze it, hash it, check it against the world.",
         "story": ("<p>" + H.q("The summarisation sample was the first 200 articles of the "
                   "CNN/DailyMail test set. The test set lists CNN's articles first, so every one "
                   "was CNN's, while the benchmark is mostly DailyMail. Copying the first three "
                   "sentences scored ROUGE-1 30.20 on that slice against 39.94 on the full test "
                   "set.", SUMM) + "</p>"
                   "<p>No check in the harness could see it: every one compared the repository "
                   "with itself. One <strong>calibration row</strong> — a known baseline against its "
                   "published value — caught it. Now every experiment has one, and "
                   f"{f['calibration_consistent']} of {len(f['calibration'])} match the literature.</p>"),
         "habit": "Freeze the data and hash it, so a number always means the same items. Then "
                  "check your sample against the population it claims to represent.",
         "tool": ("make dataset-create · make dataset-materialize",
                  "a changed input fails loudly instead of silently measuring different bytes"),
         "yours": "Your dataset is a set of real inputs, frozen. Sample it on purpose — by date, "
                  "by customer, by difficulty — and write down what it covers."},
        {"id": "gold", "nodes": "references", "kicker": "Ground truth",
         "title": "Silver is not gold.",
         "short": "A model's answers rank; a person's answers judge.",
         "story": ("<p>" + H.q("In the tutorial, the system that wrote the silver references "
                   "scores a perfect 1.000 against them and ranks first. Re-scored against six "
                   "summaries a person wrote, it falls to second — and no arm can be told apart "
                   "from any other (p = 0.2124).", GUIDE) + "</p>"
                   "<p>" + H.q("On AG News, nearly the whole lead of the three fine-tunes sits in 17 "
                   "items whose gold labels most of the hosted field disputes.", CLASS)
                   + " Read, many of those labels were wrong. Disputed gold is a finding, not "
                   "noise.</p>"),
         "habit": "Silver gets you started; gold tells you the truth. Write a small gold set "
                  "early, check silver against it, and read every item where strong systems "
                  "agree against the gold.",
         "tool": ("make rescore REFERENCE=gold/… · make silver-calibrate",
                  "re-score old runs against new gold for $0, then measure how far silver drifts"),
         "yours": "A small set of answers written by someone who knows the domain is worth more "
                  "than a large set a model generated: it is the only one that can tell you the "
                  "model is wrong."},
        {"id": "noise", "nodes": "runs", "kicker": "Noise",
         "title": "Measure the noise before the difference.",
         "short": "A delta below an arm's own jitter is nothing.",
         "story": ("<p>" + H.q("BART's apparent lead at n=20 was 0.0737; across 200 articles it "
                   "was 0.00008.", SUMM) + " " + H.q("Two independent 100-article evals of the same "
                   "models agree at only ρ = 0.79.", SUMM) + "</p>"
                   "<p>" + H.q("A pilot correlates beautifully and picks the wrong winner — in "
                   "three of five experiments here.", SYN) + "</p>"),
         "habit": "Run every arm more than once and measure how far it disagrees with itself. "
                  "Tune on a small dev slice, report on the rest, and measure how many items a "
                  "ranking needs instead of assuming it.",
         "tool": ("make experiment-run REPEAT=3 · make holdout · make rank-stability",
                  H.q("treat deltas below 0.044479 as noise", GUIDE)),
         "yours": "Before you believe the new prompt is a few points better, run the old one "
                  "twice."},
        {"id": "tested", "nodes": "tests", "kicker": "Significance",
         "title": "Tested, not read.",
         "short": "Say separated, not higher.",
         "story": (f"<p>A leaderboard sorts, so something is always first. In {ties} of "
                   f"{len(exps)} experiments here the leader cannot be separated from a group of "
                   f"others — on summarisation, from {s['n_tied']} of them, the cheapest paid one "
                   f"{H.times(s['tied_ratio'])} cheaper than the dearest model in the field.</p>"
                   "<p>Every claim on this site rests on a paired permutation test per item, "
                   "with a Holm correction for the number of comparisons made at once.</p>"),
         "habit": "Decide the comparisons before reading the table, correct for how many you "
                  "made, and report a tie as a tie.",
         "tool": ("make family-test · make leaderboard",
                  f"separated from {sf['n_arms'] - 1 - sf['n_tied']} of {sf['n_arms'] - 1} opponents"
                  f"   ← SciFact's leader, {sf['leader_row']['arm']}"),
         "yours": "When the answer is “tied”, the cheapest member of the tie is the decision."},
        {"id": "record", "nodes": "baseline", "kicker": "The record",
         "title": "Decide on the record.",
         "short": "The scorer is part of the experiment. So is the reason.",
         "story": ("<p>" + H.q("Three of these — the parser, the unparsed-as-empty rule, the "
                   "reasoning flag — moved a single arm by more than the gap separating most of "
                   "the field.", SYN) + " The scoring code is a model-sized lever.</p>"
                   "<p>Every correction is kept: the lab notebook records the findings that were "
                   "retracted along the way, several caused by this harness's own scorer.</p>"),
         "habit": "Hash and test the scorer, re-score stored outputs when it changes, and "
                  "promote a baseline only with a reason that says what the tests showed.",
         "tool": ('make rescore · make run-promote REASON="…" · make validate',
                  "re-scoring is $0; validation exits non-zero, so it belongs in CI"),
         "yours": "Keep a journal. The mistakes you write down are the checks you add next."},
    ]


def method_page(H, f: dict) -> str:
    chs = chapters(H, f)
    toc = "".join(f'<a href="#{c["id"]}"><span>{i:02d}</span>{H.e(c["title"])}</a>'
                  for i, c in enumerate(chs, 1))
    body_ch = []
    for i, c in enumerate(chs, 1):
        cmd, out = c["tool"]
        body_ch.append(f"""
<article class="chapter reveal" id="{c['id']}" data-nodes="{c['nodes']}">
  <div class="eyebrow"><span class="num">{i:02d}</span>{H.e(c['kicker'])}</div>
  <h2>{H.e(c['title'])}</h2>
  <div class="story prose">{c['story']}</div>
  <div class="habit"><b>The habit</b>{H.e(c['habit'])}</div>
  <div class="tool"><span class="k">In the harness</span><pre class="term"><span class="p">$ </span>{H.e(cmd)}
<span class="c">{H.e(out)}</span></pre></div>
  <p class="yours"><b>In your project</b> {H.e(c['yours'])}</p>
</article>""")
    body = f"""
<section class="hero"><div class="wrap">
  <div class="kicker"><b>The method</b> · six habits · learned the hard way</div>
  <h1>How to know what you <em>think you know.</em></h1>
  <p class="dek">The findings on this site took no special model and no big budget. They took a method — six habits, each learned by getting something wrong first. Here they are as the experiments taught them, with the step in the harness that keeps each one, and what it means for your own work.</p>
  <nav class="toc">{toc}</nav>
</div></section>

<section class="block method"><div class="wrap method-grid">
  <aside class="method-aside"><div class="sticky">{lifecycle()}<p class="aside-note">The lifecycle every experiment here followed. Each habit lights the step it protects.</p></div></aside>
  <div class="chapters">{''.join(body_ch)}</div>
</div></section>

<section class="block" id="influences"><div class="wrap">
  <div class="eyebrow"><span class="num">07</span>Standing on</div>
  <h2>Built on Chip Huyen's framing.</h2>
  <div class="cols">
    <div class="prose">
      <p>The approach in this repository builds on Chip Huyen's books. Their framing — evaluation is engineering work on <strong>your</strong> data, a model is chosen on a private leaderboard rather than a public one, the dataset is a design decision, every experiment is tracked and versioned — is the foundation this harness was built on. What this project adds is a tool that enforces it, and five experiments that show what skipping it costs.</p>
      <p>The idea-by-idea mapping, with chapters, is in <a href="docs/INFLUENCES/">Influences</a>.</p>
    </div>
    <ul class="reading">
      <li><b>Chip Huyen — <i>AI Engineering</i></b> (O'Reilly, 2025). Ch. 3–4: why public benchmarks rarely pick the model for your application, private leaderboards, AI judges as subjective evaluation to be checked against exact and human evaluation. Ch. 8: dataset engineering — quality, coverage, quantity.</li>
      <li><b>Chip Huyen — <i>Designing Machine Learning Systems</i></b> (O'Reilly, 2022). Ch. 4: sampling and labelling. Ch. 6: baselines, experiment tracking and versioning. Ch. 8: distribution shift.</li>
      <li><b>Martin Zinkevich — <i>Rules of Machine Learning</i></b> (Google). Design and implement your metrics first.</li>
      <li><b>Breck et al. — <i>The ML Test Score</i></b> (2017). Tests for data, models and infrastructure.</li>
      <li><b>Bernardi et al. — <i>150 Successful Machine Learning Models</i></b> (KDD 2019, Booking.com). Offline gains do not automatically become real ones.</li>
      <li>More, curated by Chip Huyen: <a href="https://huyenchip.com/mlops/">huyenchip.com/mlops</a></li>
    </ul>
  </div>
  <div class="btns"><a class="btn primary" href="use.html">Use it on your problem →</a><a class="btn" href="docs/GUIDE/">The step-by-step guide</a><a class="btn" href="experiments.html">The experiments</a></div>
</div></section>
<script>
(function(){{const nodes=document.querySelectorAll('.method-aside .lc-node');
const io=new IntersectionObserver(es=>es.forEach(x=>{{if(!x.isIntersecting)return;
const on=x.target.dataset.nodes.split(' ');nodes.forEach(n=>n.classList.toggle('on',on.includes(n.dataset.node)));}}),{{rootMargin:'-40% 0px -50% 0px'}});
document.querySelectorAll('.chapter').forEach(c=>io.observe(c));}})();
</script>"""
    return H.page("The method — eval-harness",
                  "Six habits for measuring AI systems, as five experiments taught them: "
                  "experiments, frozen data, gold references, noise, significance, the record.",
                  body + H.author("method"), here="method")


# ── use it on your problem ──────────────────────────────────────────────────
def patterns(H, f: dict) -> list:
    by = {x["slug"]: x for x in f["experiments"]}
    db = by["dbpedia"]
    return [
        ("Is the cheaper model good enough?", "arms = models, same prompt",
         f"On DBpedia a {H.times(db['tied_ratio'])} price difference bought nothing measurable. "
         "Run both on your items; if they tie, the cheap one wins.",
         "classification-dbpedia-14", "accuracy · cost per item"),
        ("Did my prompt change help?", "arms = prompts, same model",
         "Name the pair before you look, tune on a dev slice, confirm on the held-out rest.",
         "summarization-cnn-dailymail", "pair-test · holdout"),
        ("Route or label tickets", "arms = LLMs vs. a small fine-tune",
         "A small model trained on your labels can beat every LLM — and part of its lead can be "
         "learning your labels' quirks. Read the disputed items.",
         "classification-ag-news", "accuracy · disputed gold"),
        ("Search and RAG retrieval", "arms = retrievers and rerankers",
         "The answer is a ranked list over a corpus; the corpus is hashed into every fingerprint "
         "so two runs searched the same haystack.",
         "retrieval-scifact", "nDCG@10 · recall@100"),
        ("Pull fields out of text", "arms = extractors",
         "The answer is a set; matching and parsing are part of the instrument, and an unreadable "
         "answer must score zero, not be skipped.",
         "ner-few-nerd", "set F1 · parse rate"),
        ("Summaries and generated text", "arms = generators",
         "Score against references, clip for length so verbosity cannot buy recall, and check "
         "silver against a gold slice.",
         "summarization-cnn-dailymail", "coverage · ROUGE"),
        ("Catch regressions before release", "a baseline + CI",
         "Promote today's run as the baseline; compare every change against it with the noise "
         "floor you measured; validate in CI.",
         "", "run-compare · validate"),
        ("How many test items do I need?", "measure it",
         "Split your items into disjoint halves and see when two halves agree on the ranking — "
         "measured, not taken from a power table.",
         "", "rank-stability"),
    ]


STEPS = [
    ("Freeze a dataset", "Your inputs become a contract: an item list with a hash per item.",
     'make dataset-create DATASET_ID=tickets_v1 ARGS="--source-dir tutorial/tickets"',
     "data/datasets/tickets_v1.json  (6 item(s))", "1-freeze-a-dataset"),
    ("Describe your arms", "One YAML per candidate. Change one thing; bump the id.",
     "cp tutorial/configs/tickets_*.yaml data/configs/", "", "3-describe-your-arms"),
    ("Draft silver references", "Let your best system write first answers — and label them silver.",
     "make reference-create DATASET_ID=tickets_v1 CONFIG=data/configs/tickets_author.yaml",
     "data/references/silver/tickets_v1  (6 item(s), tier=silver, $0.0000)", "4-author-silver-references"),
    ("Commit, then measure — three times", "The spread is how far an arm disagrees with itself.",
     "make experiment-run CONFIG=data/configs/tickets_lead2_noisy.yaml REPEAT=3",
     "overlap_f1     spread=0.044479   treat deltas below 0.044479 as noise", "5-commit-then-measure"),
    ("Compare", "Read the significance block, not the row numbers.",
     "make leaderboard DATASET_ID=tickets_v1",
     "pairs distinguishable: 3 of 6", "6-compare"),
    ("Make it golden", "Add answers a person wrote; re-score every run against them for $0.",
     "make rescore DATASET_ID=tickets_v1 REFERENCE=gold/tickets_v1 OUT=data/runs-gold",
     "NO detectable arm effect · pairs distinguishable: 0 of 6", "7-make-it-golden"),
    ("Decide and record", "Promote with a reason that says what the tests showed; validate in CI.",
     'make run-promote RUN=… REASON="leads on gold but separates from no arm"',
     "VALIDATION PASSED", "9-promote-a-baseline"),
]


def use_page(H, f: dict) -> str:
    cards = "".join(
        f'<div class="pattern reveal"><div class="task">{H.e(var)}</div><h3>{H.e(title)}</h3>'
        f'<p>{H.e(text)}</p><div class="meta"><span>{H.e(metric)}</span>'
        + (f'<a href="{H.REPO}/tree/main/examples/{ex}">copy: {H.e(ex)} ↗</a>' if ex else "<span>any example</span>")
        + "</div></div>"
        for title, var, text, ex, metric in patterns(H, f))
    steps = "".join(
        f'<li class="reveal"><div><h3>{H.e(t)}</h3><p>{H.e(d)} <a href="docs/GUIDE/#{a}">Guide →</a></p>'
        f'<pre class="term"><span class="p">$ </span>{H.e(cmd)}'
        + (f'\n<span class="c">{H.e(H.q(out, GUIDE))}</span>' if out else "") + "</pre></div></li>"
        for t, d, cmd, out, a in STEPS)
    body = f"""
<section class="hero"><div class="wrap">
  <div class="kicker"><b>Use it</b> · on your problem · offline in twenty minutes</div>
  <h1>Measure <em>your</em> problem.</h1>
  <p class="dek">You do not need our benchmarks. You need a decision to make, a few dozen real inputs, and an afternoon. Write one adapter for your system; the harness brings frozen data, fingerprints, noise, significance and cost — the habits, enforced.</p>
  <div class="btns"><a class="btn primary" href="docs/GUIDE/">Start the guide</a><a class="btn" href="#lifecycle">How it fits together</a><a class="btn" href="method.html">Why it works this way</a></div>
</div></section>

<section class="block" id="lifecycle"><div class="wrap">
  <div class="eyebrow"><span class="num">01</span>The lifecycle</div>
  <h2>Eight things, one direction.</h2>
  <p class="lede">Every evaluation here — ours and yours — moves through the same eight artifacts. Pick one to see what it is, where it lives and the command that makes it.</p>
  <div class="lc-explorer">
    <div class="lc-map">{lifecycle(interactive=True)}</div>
    <div class="lc-panels">{lifecycle_panels(H)}</div>
  </div>
</div></section>

<section class="block" id="patterns"><div class="wrap">
  <div class="eyebrow"><span class="num">02</span>Patterns</div>
  <h2>Your question is probably one of these.</h2>
  <p class="lede">Each maps to an experiment in this repository you can copy — its adapter, its configs, its scorer — and change the data. The idea underneath all of them — build a private leaderboard for your own application instead of trusting a public one — is Chip Huyen's, from <i>AI Engineering</i> (<a href="docs/INFLUENCES/">influences</a>).</p>
  <div class="patterns">{cards}</div>
</div></section>

<section class="block" id="steps"><div class="wrap">
  <div class="eyebrow"><span class="num">03</span>Step by step</div>
  <h2>Seven steps, on a real example.</h2>
  <p class="lede">The tutorial kit ships six support tickets and summaries a person wrote. Every output below is what the command printed.</p>
  <ol class="findings steps">{steps}</ol>
</div></section>

<section class="block" id="byo"><div class="wrap">
  <div class="eyebrow"><span class="num">04</span>Bring your own</div>
  <h2>What you write. What you get.</h2>
  <div class="byo">
    <div class="byo-col"><h3>You write</h3><ul>
      <li><b>An adapter</b> — <code>call_system()</code> sends one input to your system; <code>score()</code> compares an output with a reference.</li>
      <li><b>Your inputs</b> — real ones, sampled on purpose.</li>
      <li><b>The answers</b> — gold, for a slice you can check; silver from a model you trust for the rest.</li>
      <li><b>One YAML per candidate</b> — model, prompt, settings, price.</li>
    </ul></div>
    <div class="byo-col"><h3>The harness gives you</h3><ul>
      <li>Datasets frozen by content hash, re-checked on every use.</li>
      <li>A fingerprint per run: data, prompt, code, model, build.</li>
      <li>Each arm's own noise, measured.</li>
      <li>Paired and Holm-corrected tests — separated or tied.</li>
      <li>Billed cost and latency beside quality.</li>
      <li>Re-scoring from stored outputs for $0; validation for CI; baselines with reasons.</li>
    </ul></div>
    <div class="byo-col check"><h3>Start on Monday</h3><ul>
      <li>Write the question as a decision: <i>can ticket routing move to the cheaper model?</i></li>
      <li>Collect real inputs; freeze them.</li>
      <li>Write gold answers for a slice yourself.</li>
      <li>Write the adapter; one config per candidate.</li>
      <li>Dry-run; set a cost cap.</li>
      <li>Run each arm three times; note its noise.</li>
      <li>Test the comparison you named; promote with a reason; put <code>make validate</code> in CI.</li>
    </ul></div>
  </div>
</div></section>

<section class="block" id="doors"><div class="wrap">
  <div class="eyebrow"><span class="num">05</span>Two doors</div>
  <h2>Rerun ours, or build yours.</h2>
  <div class="cards doors">
    <a class="card" href="docs/REPRODUCE/"><div class="task">Rerun ours</div><h3>Check every finding yourself.</h3><p>Five levels, from recomputing every number for $0 to rerunning every model with one key — with a replication card that re-tests every separation.</p><div class="meta"><span>make verify</span><b>Reproduce it →</b></div></a>
    <a class="card" href="docs/GUIDE/"><div class="task">Build yours</div><h3>Your first evaluation, end to end.</h3><p>Freeze a dataset, build a golden reference set, measure, compare honestly, promote a baseline — offline, with the real output of every step.</p><div class="meta"><span>harness/tutorial</span><b>The guide →</b></div></a>
  </div>
</div></section>
<script>
(function(){{const panels=[...document.querySelectorAll('.lc-panel')],nodes=[...document.querySelectorAll('.lc-map .lc-node')];
if(!panels.length)return;document.querySelector('.lc-explorer').classList.add('live');
function show(id){{panels.forEach(p=>p.classList.toggle('on',p.dataset.node===id));nodes.forEach(n=>n.classList.toggle('on',n.dataset.node===id));}}
nodes.forEach(n=>{{n.addEventListener('click',ev=>{{ev.preventDefault();show(n.dataset.node);if(innerWidth<=900){{const p=panels.find(p=>p.dataset.node===n.dataset.node);if(p)p.scrollIntoView({{block:'nearest',behavior:'smooth'}});}}}});n.addEventListener('mouseenter',()=>show(n.dataset.node));n.addEventListener('focus',()=>show(n.dataset.node));}});
show('dataset');}})();
</script>"""
    return H.page("Use it on your problem — eval-harness",
                  "Apply the method to your own system: the evaluation lifecycle, patterns for "
                  "common questions, seven steps on a real example, and what you write vs. what "
                  "the harness gives you.", body + H.author("use"), here="use")


# ── borrowed by the landing and experiment pages ────────────────────────────
def landing_teaser(H, f: dict, num: str = "03") -> str:
    chs = chapters(H, f)
    habits = "".join(
        f'<a class="habit-card reveal" href="method.html#{c["id"]}"><span class="n">{i:02d}</span>'
        f'<b>{H.e(c["title"])}</b><span>{H.e(c["short"])}</span></a>'
        for i, c in enumerate(chs, 1))
    return f"""
<section class="block" id="method"><div class="wrap">
  <div class="eyebrow"><span class="num">{num}</span>The method</div>
  <h2>The harness enforces a method.</h2>
  <p class="lede">Nothing here needed special access or a big budget. It took six habits — each learned by getting something wrong first — and a harness that enforces them. They work on any problem you can put into a dataset. The framing builds on Chip Huyen's <i>AI Engineering</i> and <i>Designing Machine Learning Systems</i>.</p>
  <div class="habits">{habits}</div>
  <div class="btns"><a class="btn primary" href="method.html">Read the method</a><a class="btn" href="use.html">Use it on your problem</a></div>
</div></section>
"""


def experiment_lesson(H, x: dict) -> tuple:
    """(chapter id, chapter title, what this experiment taught) for an experiment page."""
    slug = x["slug"]
    if slug == "summarization":
        return ("data", "The data is the instrument.",
                H.q("The committed sample turned out to be all CNN's articles. A calibration row "
                    "— copying the first three sentences on the full test set, against its "
                    "published score — is what showed it.", SUMM))
    if slug == "ag-news":
        return ("gold", "Silver is not gold.",
                H.q("Nearly the whole lead of the three fine-tunes sits in 17 items whose gold "
                    "labels most of the hosted field disputes.", CLASS))
    if slug == "dbpedia":
        return ("tested", "Tested, not read.",
                f"{x['n_tied']} arms cannot be separated from the leader. A saturated benchmark "
                "sorts; it does not rank — and the table still prints them first, second, third.")
    if slug == "few-nerd":
        return ("gold", "Silver is not gold.",
                H.q("57% of the winner's margin is one entity type whose meaning exists only in "
                    "that corpus.", NER) + " A clean win can still be partly a win at the "
                "annotation, not the task.")
    return ("noise", "Measure the noise before the difference.",
            H.q("The dev slice picked the wrong winner — its leader finished 10th of 19.", RET))
