"""The method page, the "use it on your problem" page, and the pieces of them that the
landing and eval pages borrow.

The findings are the hook; the method is the point. These pages tell the six habits as
the evals taught them, then show how to apply them to a problem of your own.

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
JUDGE = "research/REPORT_SUMMEVAL.md"
GUIDE = "docs/GUIDE.md"
TUTORIAL3 = "docs/tutorials/3-frontier-reference-and-judging.md"
TUTORIAL4 = "docs/tutorials/4-rounds-and-versions.md"
TUTORIAL6 = "docs/tutorials/6-datasets-from-production.md"
TUTORIAL7 = "docs/tutorials/7-set-up-a-model.md"


#: Where each lifecycle step is in this repository's catalog: (page, what it shows there).
CATALOG_STEP = {
    "dataset": ("datasets.html", "Every dataset, its versions and items"),
    "references": ("references.html", "Every reference, who wrote it, what is scored against it"),
    "arms": ("arms.html#configs", "Every config, across the datasets it ran on"),
    "runs": ("arms.html", "Every arm, how it was measured, its cost and speed"),
    "baseline": ("goals.html", "Every goal, its promoted baseline and its reason"),
    "remeasure": ("arms.html", "Re-scored and judged arms beside the originals"),
    "rounds": ("goals.html", "Every goal, its rounds and their conclusions"),
}
#: Where each habit can be seen in this repository's catalog: (page, link text). "tested" opens
#: the inspector on the summarisation field (H.catalog_inspect).
CATALOG_HABIT = {
    "experiment": ("goals.html", "each goal's arms, side by side"),
    "data": ("datasets.html", "every dataset, frozen, with its versions"),
    "gold": ("references.html", "every reference, gold and silver, and what is scored against it"),
    "noise": ("arms.html", "every arm, the ones run more than once included"),
    "tested": (None, "the summarisation field, every arm tested against its leader"),
    "record": ("goals.html", "every goal's baseline, with the reason a person recorded"),
}
#: Every top-level catalog page the site may link to.
CATALOG_PAGES = {p for p, _ in CATALOG_STEP.values()} | {p for p, _ in CATALOG_HABIT.values() if p}


def doc_href(page: str, anchor: str) -> str:
    """The docs site's address for a section of one of the docs' markdown pages."""
    return f"docs/{page.removeprefix('docs/').removesuffix('.md')}/#{anchor}"


# ── the lifecycle, shared by both pages ─────────────────────────────────────
#: id, label, sub-label, what it is, where it lives, the command, the guide section
NODES = [
    (
        "sources",
        "Sources",
        "your inputs",
        (
            "Any files: tickets, transcripts, documents, prompts. Keep them under version control "
            "— an untracked input makes every run unattributable. Or what your system did in production, "
            "kept as a capture: each record hashed, and a dataset frozen from a selection of them."
        ),
        "data/sources/ — or anywhere · data/captures/&lt;id&gt;/",
        "evh capture --importer jsonl --query … --capture …",
        (GUIDE, "1-create-a-dataset"),
    ),
    (
        "dataset",
        "Dataset",
        "frozen · sha256",
        (
            "The comparison contract: an item list with the hash of every item. Two runs on "
            "different datasets cannot be compared, and a changed input is a new version."
        ),
        "data/datasets/&lt;id&gt;.json",
        "evh dataset-create --dataset-id tickets_v1",
        (GUIDE, "1-create-a-dataset"),
    ),
    (
        "materialized",
        "Materialized",
        "hash-checked copy",
        (
            "A working copy, re-verified against the frozen hashes every time — so a run can "
            "never measure bytes the dataset does not describe."
        ),
        "data/materialized/&lt;id&gt;/",
        "evh dataset-materialize --dataset-id tickets_v1",
        (GUIDE, "2-materialize"),
    ),
    (
        "references",
        "Reference sets",
        "silver · gold",
        (
            "What each item is scored against: labels (a person's, a model's, a rule's) promoted on purpose, "
            "at the tier chosen then. Silver: consistent, not correct, often an expensive arm's labels, so the "
            "cheaper arms are measured by how close they come to it. Gold: the yardstick a decision rests on. "
            "Gold always wins, and every run says which it used."
        ),
        "data/references/&lt;tier&gt;/&lt;id&gt;/",
        "evh label-from-run · evh reference-promote",
        (GUIDE, "5-make-its-outputs-the-reference-optional"),
    ),
    (
        "arms",
        "Arms",
        "one config each",
        (
            "One system under test: provider, model, prompt, settings, in a YAML file. Change one "
            "thing, bump the config_id — the fingerprint will prove what moved. An arm can name a model "
            "record, set up once where it runs, and is smoked on a few items before its full run."
        ),
        "data/configs/*.yaml · data/models/&lt;id&gt;.yaml",
        "evh arm-smoke --config …",
        (GUIDE, "3-describe-your-arms"),
    ),
    (
        "runs",
        "Runs",
        "outputs + fingerprint",
        (
            "One pass of an arm over the dataset: every output, every per-item score, billed cost, "
            "latency, and a fingerprint of data, code, model and build. Repeat it to measure noise."
        ),
        "data/runs/&lt;run_id&gt;/",
        "evh run --config … --repeat 3",
        (GUIDE, "6-run-the-other-arms-three-times-each"),
    ),
    (
        "tests",
        "Tests",
        "significant or not",
        (
            "The leaderboard with its significance block, paired tests, Holm-corrected families. "
            "A claim means significant, not scored higher."
        ),
        "your terminal",
        "evh family-test --dataset-id … --a … --against …",
        (GUIDE, "7-compare"),
    ),
    (
        "baseline",
        "Baseline",
        "a decision + reason",
        (
            "The run future changes are measured against, recorded with why. Never edited: the "
            "next promotion replaces it and git keeps the old one — in six months, “why is this "
            "the baseline?” has an answer."
        ),
        "data/baselines/",
        'evh run-promote --run … --reason "…"',
        (GUIDE, "8-choose"),
    ),
    (
        "remeasure",
        "Re-measure",
        "optional · later",
        (
            "The same frozen outputs, measured again without re-running an arm: new gold or a new "
            "code scorer for $0, or LLM judges (grading each output, picking the best, or comparing two), "
            "billed and capped, that the harness refuses until "
            "they are validated against people. Written beside the originals, never over them; the "
            "primary metric changes only by a recorded decision. A new scoring rule is previewed first, "
            "then re-scores a round, which records the scorer it is judged by."
        ),
        "data/runs-rescored/&lt;scorer&gt;/ · data/runs-judged/&lt;scorer&gt;/",
        "evh score-preview --goal … · evh rescore --goal … --round …",
        (TUTORIAL4, "7-when-the-scoring-changes"),
    ),
    (
        "rounds",
        "Next round",
        "optional · and on",
        (
            "A goal is answered in rounds: each says what it set out to learn, carries the arms that stay, "
            "retires the rest with why, and closes with a conclusion. Before deploy they narrow a field; "
            "after it the same goal goes on, on new dataset versions of what the deployed system decides."
        ),
        "data/rounds/&lt;goal&gt;/r&lt;n&gt;.yaml",
        "evh round-open --goal … --from r1",
        (TUTORIAL4, "4-round-2-change-one-thing"),
    ),
]


def lifecycle(interactive: bool = False) -> str:
    """The pipeline as a vertical diagram. Nodes carry data-node so a page can light them."""
    w, bh, step, x = 300, 54, 76, 20
    parts = []
    for i, (nid, label, sub, *_rest) in enumerate(NODES):
        y = 12 + i * step
        if i:
            parts.append(
                f'<path class="lc-edge" d="M{w / 2} {y - step + bh + 4} V{y - 6}"/>'
                f'<path class="lc-head" d="M{w / 2 - 5} {y - 11} L{w / 2} {y - 5} L{w / 2 + 5} {y - 11}"/>'
            )
        node = (
            f'<rect x="{x}" y="{y}" width="{w - 2 * x}" height="{bh}" rx="10"/>'
            f'<text class="lc-label" x="{x + 18}" y="{y + 24}">{label}</text>'
            f'<text class="lc-sub" x="{x + 18}" y="{y + 42}">{sub}</text>'
            f'<text class="lc-num" x="{w - x - 16}" y="{y + 24}" text-anchor="end">{i + 1:02d}</text>'
        )
        if interactive:
            parts.append(
                f'<a href="#lc-{nid}" class="lc-node" data-node="{nid}" '
                f'aria-label="{label}: {sub}">{node}</a>'
            )
        else:
            parts.append(f'<g class="lc-node" data-node="{nid}">{node}</g>')
    h = 12 + len(NODES) * step
    return (
        f'<svg class="lc" viewBox="0 0 {w} {h}" role="img" aria-label="The evaluation '
        f"lifecycle: sources, dataset, materialized copy, reference sets, arms, runs, tests, "
        f'baseline, an optional re-measurement, and the next round">{"".join(parts)}</svg>'
    )


def lifecycle_panels(H) -> str:
    out = []
    for nid, label, sub, what, where, cmd, anchor in NODES:
        cmd_html = f'<pre class="term"><span class="p">$ </span>{H.e(cmd)}</pre>' if cmd else ""
        ours = CATALOG_STEP.get(nid)
        ours_html = (
            f' <a class="lc-more" href="{H.CATALOG}{ours[0]}" title="{H.e(ours[1])}">Ours, in the catalog →</a>'
            if ours
            else ""
        )
        out.append(
            f'<div class="lc-panel" id="lc-{nid}" data-node="{nid}">'
            f'<div class="eyebrow"><span class="num">{label}</span>{sub}</div>'
            f'<p>{what}</p><div class="lc-where"><span>lives in</span> <code>{where}</code></div>'
            f'{cmd_html}<div class="lc-links"><a class="lc-more" href="{doc_href(*anchor)}">In the guide →</a>{ours_html}</div></div>'
        )
    return "".join(out)


# ── the six habits ──────────────────────────────────────────────────────────
def chapters(H, f: dict) -> list:
    exps = f["evals"]
    by = {x["slug"]: x for x in exps}
    ties = sum(x["n_contenders"] > 0 for x in exps)
    s = by["summarization"]
    sf = by["scifact"]
    return [
        {
            "id": "experiment",
            "nodes": "arms runs",
            "kicker": "Experiment",
            "title": "An eval is an experiment.",
            "short": "Vary one thing. Record everything else.",
            "story": (
                f"<p>The same {max(x['n_hosted'] for x in exps)} hosted models (the cheapest twelve on SciFact) ran on {H.word(len(exps))} tasks with one prompt per "
                "task, at temperature 0 with reasoning off (on SummEval, Qwen's large slot is "
                "a stand-in, qwen37max) — so when a model's score differs "
                "between two tasks, the task is what changed, apart from what each report states: on "
                "SummEval a stand-in model, prices a month later and a different calling machine.</p>"
                "<p>Every run carries a <strong>fingerprint</strong>: hashes of the data, the "
                "prompt and the scoring code, the model behind the alias, library versions, "
                "the commit. Before the harness shows a single delta between two runs, it "
                "lists the fields that moved.</p>"
            ),
            "habit": "Change one thing per arm, and record everything else — so “we only changed "
            "the prompt” is checkable rather than claimed.",
            "tool": (
                "evh run-compare --baseline … --candidate …",
                "Fingerprints DIFFER. Fields that moved: arm.params.sentences",
            ),
            "yours": "Your arms are your candidates — prompts, models, retrieval settings, "
            "thresholds — one YAML file each.",
        },
        {
            "id": "data",
            "nodes": "sources dataset materialized",
            "kicker": "Data",
            "title": "The data is the instrument.",
            "short": "Freeze it, hash it, check it against the world.",
            "story": (
                "<p>"
                + H.q(
                    "The summarisation sample was the first 200 articles of the "
                    "CNN/DailyMail test set. The test set lists CNN's articles first, so every one "
                    "was CNN's, while the benchmark is mostly DailyMail. Copying the first three "
                    "sentences scored ROUGE-1 30.20 on that slice against 39.94 on the full test "
                    "set.",
                    SUMM,
                )
                + "</p>"
                "<p>No check in the harness could see it: every one compared the repository "
                "with itself. One <strong>calibration row</strong> — a known baseline against its "
                "published value — caught it. Now every eval has one, and "
                f"{f['calibration_consistent']} of {len(f['calibration'])} agree with the literature, "
                f"{f['calibration_inside']} of them inside their own interval.</p>"
            ),
            "habit": "Freeze the data and hash it, so a number always means the same items. Then "
            "check your sample against the population it claims to represent.",
            "tool": (
                "evh dataset-create · evh dataset-materialize",
                "a changed input fails loudly instead of silently measuring different bytes",
            ),
            "yours": "Your dataset is a set of real inputs, frozen. Sample it on purpose — by date, "
            "by customer, by difficulty — and write down what it covers.",
        },
        {
            "id": "gold",
            "nodes": "references remeasure",
            "kicker": "Ground truth",
            "title": "Silver is not gold.",
            "short": "Silver ranks; gold judges. You choose which, when you promote.",
            "story": (
                "<p>"
                + H.q(
                    "In the tutorial, the system that wrote the silver references, the one every "
                    "other arm was measured against, is not first once six summaries a person "
                    "wrote are the measure — and six items can almost never tell the arms apart.",
                    TUTORIAL3,
                )
                + "</p>"
                "<p>"
                + H.q(
                    "On AG News, the lead of the three fine-tunes is concentrated in 17 "
                    "items the hosted field mostly gets wrong. Adjudicated by topic by one reader "
                    "shown the hosted answer, the gold was wrong on all 17, and on that gold every "
                    "hosted LLM scores above every fine-tune.",
                    CLASS,
                )
                + " The dataset's own gold stays primary; the adjudicated one sits beside it. "
                "Disputed gold is a finding, not noise.</p>"
                "<p>"
                + H.q(
                    "An AI judge is silver too, and SummEval measures how good: scored "
                    "against the mean of two experts, as one expert is against the other two, the "
                    "best judges reach 93% of a human's agreement (the best of 24, chosen on the same "
                    "articles; 92% held out). The experts are not noiseless "
                    "either: 41 of 44 groups of word-for-word identical summaries got different "
                    "expert scores.",
                    JUDGE,
                )
                + " Close to a person is not the same as a person.</p>"
                "<p>"
                + H.q(
                    "Two of those judges re-measured the summarisation eval and "
                    "ranked every hosted LLM above every BART model. The one blind human check on "
                    "those outputs, one non-expert reader on 20 pairs, preferred bart_l 14 to 6.",
                    SUMM,
                )
                + " That check is weak too (p = 0.115, truncated articles), so neither is "
                "confirmed on those outputs; on crowd ratings of 2022 LLM summaries the judges track "
                "people better than one rater does on coherence and relevance, not on faithfulness, "
                "and not system by system. "
                "So the harness refuses a judge until it is validated, and the "
                "summarisation eval still ranks by coverage.</p>"
            ),
            "habit": "Silver gets you started; gold tells you the truth. Write a small gold set "
            "early, promote it on purpose with why, check silver — and any AI judge — against it, and "
            "read every item where strong systems agree against the gold.",
            "tool": (
                (
                    "evh label-sheet · evh label-import · evh reference-promote --tier gold · "
                    "evh rescore --reference-id gold/… · evh silver-calibrate · evh judge-score"
                ),
                (
                    "label the items, promote the labels you would sign, re-score old runs against the new "
                    "gold for $0, measure how far silver drifts, re-measure with judges you have validated"
                ),
            ),
            "yours": "A small set of answers written by someone who knows the domain is worth more "
            "than a large set a model generated: it is the only one that can tell you the "
            "model is wrong.",
        },
        {
            "id": "noise",
            "nodes": "runs",
            "kicker": "Noise",
            "title": "Measure the noise before the difference.",
            "short": "A delta below an arm's own jitter is nothing.",
            "story": (
                "<p>"
                + H.q("BART's apparent lead at n=20 was 0.0737; across 200 articles it was 0.00008.", SUMM)
                + " "
                + H.q(
                    "Two independent 100-article measurements of the same models agree at only ρ = 0.79.",
                    SUMM,
                )
                + "</p>"
                "<p>"
                + H.q(
                    "A pilot correlates beautifully and picks the wrong winner — in "
                    "three of the five evals here that ran one.",
                    SYN,
                )
                + "</p>"
            ),
            "habit": "Run every arm more than once and measure how far it disagrees with itself. "
            "Tune on a small pilot slice, report on the rest, and measure how many items a "
            "ranking needs instead of assuming it.",
            "tool": (
                "evh run --repeat 3 · evh holdout · evh rank-stability",
                H.q("treat deltas below 0.029372 as noise", GUIDE),
            ),
            "yours": "Before you believe the new prompt is a few points better, run the old one twice.",
        },
        {
            "id": "tested",
            "nodes": "tests",
            "kicker": "Significance",
            "title": "Tested, not read.",
            "short": "Say significant, not higher.",
            "story": (
                f"<p>A leaderboard sorts, so something is always first. In {ties} of "
                f"{len(exps)} evals here the leader is not significantly different from a group of "
                f"others — on summarisation, from {s['n_contenders']} of them, the cheapest paid one "
                f"{H.times(s['contender_ratio'])} cheaper than the dearest model in the field.</p>"
                "<p>Every significance claim on this site rests on a paired permutation test "
                "per item, with a Holm correction for the number of comparisons made at "
                "once. Not significant means the test could not tell two arms apart at this many items, "
                "not that they are equal. Intervals elsewhere (the human ceiling) are "
                "bootstrapped, and the price slopes are fits, not tests.</p>"
            ),
            "habit": "Decide the comparisons before reading the table, correct for how many you "
            "made, and report a tie as a tie.",
            "tool": (
                "evh family-test · evh leaderboard",
                (
                    f"significantly different from {sf['n_arms'] - 1 - sf['n_contenders']} of {sf['n_arms'] - 1} opponents"
                    f"   ← SciFact's leader, {sf['leader_row']['arm']}"
                ),
            ),
            "yours": "When the answer is “not significant”, look at the gap and the sample size first: if the "
            "gap is one you can live with, the cheapest arm in that group is the decision.",
        },
        {
            "id": "record",
            "nodes": "baseline",
            "kicker": "The record",
            "title": "Decide on the record.",
            "short": "The scorer is part of the eval. So is the reason.",
            "story": (
                "<p>Running the evals found eight defects in the harness's own "
                "instrument, each of which changed published numbers or would have. "
                + H.q(
                    "Three of these — the parser, the unparsed-as-empty rule, the "
                    "reasoning flag — moved a single arm by more than the gap separating most of "
                    "the field.",
                    SYN,
                )
                + " The scoring code is a model-sized lever.</p>"
                "<p>The lab notebook records the findings that were retracted along the way, "
                "several caused by this harness's own scorer; the reports state today's figures, "
                "and git keeps every earlier version.</p>"
            ),
            "habit": "Hash and test the scorer, re-score stored outputs when it changes, and "
            "promote a baseline only with a reason that says what the tests showed.",
            "tool": (
                'evh rescore · evh run-promote --reason "…" · evh validate',
                "re-scoring is $0; validation exits non-zero, so it belongs in CI",
            ),
            "yours": "Keep a journal. The mistakes you write down are the checks you add next.",
        },
    ]


#: Four habits for an evaluation that goes on (0.6.0): not taught by the six evals, so not told as their
#: stories; each with the step that keeps it (owner, 2026-11-01).
LASTING = [
    (
        "Set it up before you measure it.",
        (
            "Settle once, per model and where it runs, what a server would otherwise choose: whether it reasons, how long "
            "a reply may run, which build a tag names. Smoke an arm on a few items before its full run. Left at the "
            "defaults, an arm measures the defaults. The measurement is the deployment (weights, server, machine), not "
            "the laptop that ran it."
        ),
        "evh model-onboard · evh arm-smoke",
        "docs/tutorials/7-set-up-a-model/",
    ),
    (
        "Production is the test, not the answer key.",
        (
            "Keep what your system decided as a capture, every record hashed. Its decisions become an arm, scored "
            "against labels; what happened next is a rule's labels, never a reference set until you promote it. The rows "
            "worth keeping are picked for the next version of a dataset you govern."
        ),
        "evh capture · evh arm-from-capture · evh label-from-capture · evh pick",
        "docs/tutorials/6-datasets-from-production/",
    ),
    (
        "A changed rule is a decision too.",
        (
            "When a scoring rule turns out wrong, preview what the new one moves, then re-score the round or adopt it "
            "from the next one, with why. A round's evidence is measured by one scorer, and says which."
        ),
        "evh score-preview · evh rescore --round",
        "docs/tutorials/4-rounds-and-versions/#7-when-the-scoring-changes",
    ),
    (
        "An evaluation doesn't stop at deploy.",
        (
            "Answer a goal in rounds. Before deploy they narrow a field; after it the same goal goes on, on what the "
            "deployed system decides, against new candidates. Each round records what it set out to learn and what it "
            "concluded."
        ),
        "evh round-open --from · evh rounds",
        "docs/tutorials/4-rounds-and-versions/#after-deploy",
    ),
]


def method_page(H, f: dict) -> str:
    chs = chapters(H, f)
    lasting = "".join(
        f'<div class="habit-card"><b>{H.e(t)}</b><span>{H.e(d)}</span>'
        f'<code class="lasting-cmd">{H.e(cmd)}</code><span><a href="{href}">In the docs →</a></span></div>'
        for t, d, cmd, href in LASTING
    )
    toc = "".join(
        f'<a href="#{c["id"]}"><span>{i:02d}</span>{H.e(c["title"])}</a>' for i, c in enumerate(chs, 1)
    )
    by = {x["slug"]: x for x in f["evals"]}
    body_ch = []
    for i, c in enumerate(chs, 1):
        cmd, out = c["tool"]
        page, text = CATALOG_HABIT[c["id"]]
        href = H.CATALOG + (page or H.catalog_inspect(by["summarization"]))
        body_ch.append(f"""
<article class="chapter reveal" id="{c["id"]}" data-nodes="{c["nodes"]}">
  <div class="eyebrow"><span class="num">{i:02d}</span>{H.e(c["kicker"])}</div>
  <h2>{H.e(c["title"])}</h2>
  <div class="story prose">{c["story"]}</div>
  <div class="habit"><b>The habit</b>{H.e(c["habit"])}</div>
  <div class="tool"><span class="k">In the harness</span><pre class="term"><span class="p">$ </span>{H.e(cmd)}
<span class="c">{H.e(out)}</span></pre></div>
  <p class="yours"><b>In ours</b> <a href="{href}">{H.e(text)} →</a>, in the catalog.</p>
  <p class="yours"><b>In your project</b> {H.e(c["yours"])}</p>
</article>""")
    body = f"""
<section class="hero"><div class="wrap">
  <div class="kicker"><b>The method</b> · six habits · learned the hard way</div>
  <h1>How to know what you <em>think you know.</em></h1>
  <p class="dek">The findings on this site took no special model and no big budget. They took a method — six habits, each learned by getting something wrong first. Here they are as the evals taught them, with the step in the harness that keeps each one, and what it means for your own work; then <a href="#lasting">four more</a>, for an evaluation that goes on.</p>
  <nav class="toc">{toc}</nav>
</div></section>

<section class="block method"><div class="wrap method-grid">
  <aside class="method-aside"><div class="sticky">{lifecycle()}<p class="aside-note">The lifecycle every eval here followed. Each habit lights the step it protects.</p></div></aside>
  <div class="chapters">{"".join(body_ch)}</div>
</div></section>

<section class="block" id="lasting"><div class="wrap">
  <div class="eyebrow"><span class="num">07</span>And on</div>
  <h2>Four more, for an evaluation that goes on.</h2>
  <p class="lede">The six habits make one comparison trustworthy. These four keep an evaluation trustworthy as it goes on, round after round, before deploy and after it. Each is optional, and each is a step in the harness.</p>
  <div class="habits two">{lasting}</div>
</div></section>

<section class="block" id="influences"><div class="wrap">
  <div class="eyebrow"><span class="num">08</span>Standing on</div>
  <h2>Built on Chip Huyen's framing.</h2>
  <div class="cols">
    <div class="prose">
      <p>The approach in this repository builds on Chip Huyen's books. Their framing — evaluation is engineering work on <strong>your</strong> data, a model is chosen on a private leaderboard rather than a public one, the dataset is a design decision, every experiment is tracked and versioned — is the foundation this harness was built on. What this project adds is a tool that enforces it, and six evals that show what skipping it costs.</p>
      <p>The idea-by-idea mapping, with chapters, is in <a href="docs/INFLUENCES/">Influences</a>.</p>
    </div>
    <ul class="reading">
      <li><b>Chip Huyen — <i>AI Engineering</i></b> (O'Reilly, 2025). Ch. 2: sampling makes models probabilistic, and so inconsistent — measured here at temperature 0. Ch. 3–4: why public benchmarks rarely pick the model for your application, private leaderboards, AI judges as subjective evaluation to be checked against exact and human evaluation. Ch. 8: dataset engineering — quality, coverage, quantity.</li>
      <li><b>Chip Huyen — <i>Designing Machine Learning Systems</i></b> (O'Reilly, 2022). Ch. 4: sampling and labelling. Ch. 6: baselines, experiment tracking and versioning. Ch. 8: distribution shift.</li>
      <li><b>Martin Zinkevich — <i>Rules of Machine Learning</i></b> (Google). Design and implement your metrics first.</li>
      <li><b>Breck et al. — <i>The ML Test Score</i></b> (2017). Tests for data, models and infrastructure.</li>
      <li><b>Bernardi et al. — <i>150 Successful Machine Learning Models</i></b> (KDD 2019, Booking.com). Offline gains do not automatically become real ones.</li>
      <li>More, curated by Chip Huyen: <a href="https://huyenchip.com/mlops/">huyenchip.com/mlops</a></li>
    </ul>
  </div>
  <p>The habits hold when an agent does the work, too: it can read every number they rest on, the goals and their tests, from the catalog over MCP, and the decisions stay a person's (<a href="./#mcp">ask it from your agent</a>).</p>
  <div class="btns"><a class="btn primary" href="use.html">Use it on your problem →</a><a class="btn" href="docs/GUIDE/">The step-by-step guide</a><a class="btn" href="evals.html">The evals</a></div>
</div></section>
<script>
(function(){{const nodes=document.querySelectorAll('.method-aside .lc-node');
const io=new IntersectionObserver(es=>es.forEach(x=>{{if(!x.isIntersecting)return;
const on=x.target.dataset.nodes.split(' ');nodes.forEach(n=>n.classList.toggle('on',on.includes(n.dataset.node)));}}),{{rootMargin:'-40% 0px -50% 0px'}});
document.querySelectorAll('.chapter').forEach(c=>io.observe(c));}})();
</script>"""
    return H.page(
        "The method — eval-harness",
        "Six habits for measuring AI systems, as six evals taught them: "
        "experiments, frozen data, gold references, noise, significance, the record; "
        "and four for an evaluation that goes on.",
        body + H.author("method"),
        here="method",
    )


# ── use it on your problem ──────────────────────────────────────────────────
def patterns(H, f: dict) -> list:
    by = {x["slug"]: x for x in f["evals"]}
    db = by["dbpedia"]
    return [
        (
            "Is the cheaper model good enough?",
            "arms = models, same prompt",
            (
                f"On DBpedia a {H.times(db['contender_ratio'])} price difference was not shown to buy accuracy. "
                "Run both on your items; if they tie and the gap is one you can live with, the cheap "
                "one wins."
            ),
            "classification-dbpedia-14",
            "accuracy · cost per item",
        ),
        (
            "Did my prompt change help?",
            "arms = prompts, same model",
            "Name the pair before you look, tune on a pilot slice, confirm on the held-out rest.",
            "summarization-cnn-dailymail",
            "pair-test · holdout",
        ),
        (
            "Route or label tickets",
            "arms = LLMs vs. a small fine-tune",
            (
                "A small model trained on your labels can match or beat LLMs run with one prompt — and "
                "part of its lead can be learning your labels' quirks. Read the disputed items."
            ),
            "classification-ag-news",
            "accuracy · disputed gold",
        ),
        (
            "Search and RAG retrieval",
            "arms = retrievers and rerankers",
            (
                "The answer is a ranked list over a corpus; the corpus is hashed into every fingerprint "
                "so two runs searched the same haystack."
            ),
            "retrieval-scifact",
            "nDCG@10 · recall@100",
        ),
        (
            "Pull fields out of text",
            "arms = extractors",
            (
                "The answer is a set; matching and parsing are part of the instrument, and an unreadable "
                "answer must score zero, not be skipped."
            ),
            "ner-few-nerd",
            "set F1 · parse rate",
        ),
        (
            "Use an LLM as a judge",
            "arms = judges, scored against people",
            H.q(
                "Score a few dozen outputs yourself, then measure how well each judge orders them "
                "the way you do. On SummEval the best judges reached 93% of an expert's agreement "
                "(the best of 24, chosen on the same articles; 92% held out), and an open-weight one at 1/23 of the "
                "leader's price was not significantly different from it.",
                JUDGE,
            )
            + " Pin the provider: one judge, run once on each of two providers, scored 0.0113 apart and billed 3.7× apart."
            " Once validated, a judge can re-measure your arms' stored outputs (evh judge-score), "
            "on any text task you declare; validate it on outputs like the ones it will judge.",
            "summeval-judging",
            "Kendall τ · human ceiling",
        ),
        (
            "Summaries and generated text",
            "arms = generators",
            (
                "Score against references, clip for length so verbosity cannot buy recall, and check "
                "silver against a gold slice."
            ),
            "summarization-cnn-dailymail",
            "coverage · ROUGE",
        ),
        (
            "Is my system still deciding well in production?",
            "arms = the deployed one + candidates",
            (
                "Capture what it decided, score its decisions as an arm against labels (a rule's over what "
                "happened next, or a person's), and pick the rows where it was wrong for the next version of "
                "the dataset you govern."
            ),
            "triage-fleet",
            "capture · arm-from-capture · pick",
        ),
        (
            "Is this model set up right before I compare it?",
            "a model record",
            (
                "Onboard it where it runs (its build, whether it reasons, JSON, determinism), then smoke the "
                "arm on a few items before its full run."
            ),
            "",
            "model-onboard · arm-smoke",
        ),
        (
            "My scoring rule was wrong: do I run everything again?",
            "no: re-score",
            (
                "Preview what the new rule moves, then re-score the round at $0 from the stored outputs; "
                "the round records the scorer and why."
            ),
            "",
            "score-preview · rescore",
        ),
        (
            "Catch regressions before release",
            "a baseline + CI",
            (
                "Promote today's run as the baseline; compare every change against it with the noise "
                "floor you measured; validate in CI."
            ),
            "",
            "run-compare · validate",
        ),
        (
            "How many test items do I need?",
            "measure it",
            (
                "Split your items into disjoint halves and see when two halves agree on the ranking — "
                "measured, not taken from a power table."
            ),
            "",
            "rank-stability",
        ),
    ]


STEPS = [
    (
        "Set up",
        "A new folder, the harness pinned to a release, and the tutorial kit copied in.",
        'pip install "evaluation-harness @ git+{repo}@v{version}#subdirectory=harness"\nevh init --tutorial',
        "wrote    26 file(s), the tutorial kit under tutorial/",
        GUIDE,
        "0-set-up",
    ),
    (
        "Create a dataset",
        "Your inputs become a contract: an item list with a hash per item.",
        "evh dataset-create --dataset-id tickets_v1 --source-dir tutorial/tickets",
        "data/datasets/tickets_v1.json  (6 item(s))",
        GUIDE,
        "1-create-a-dataset",
    ),
    (
        "Describe your arms",
        "One YAML per candidate. Change one thing; bump the id.",
        "cp tutorial/configs/tickets_*.yaml data/configs/",
        "",
        GUIDE,
        "3-describe-your-arms",
    ),
    (
        "Optional: set the model up first",
        "A record per model, a deployment per machine; onboarding checks its build, reasoning, JSON and determinism there.",
        "evh model-onboard llama3.1-8b --deployment laptop",
        "ONBOARD PASS",
        TUTORIAL7,
        "2-onboard-it",
    ),
    (
        "Run the best arm; its outputs become the reference set",
        "Your best system answers first; its answers become a model's labels, promoted to silver, and the others are measured by how close they come.",
        "evh run --config data/configs/tickets_author.yaml\nevh label-from-run --run … --set author_v1\nevh reference-promote --dataset-id tickets_v1 --labels author_v1 --tier silver --reason … --by me",
        "data/references/silver/tickets_v1: 6 of 6 item(s), silver, promoted from tickets_v1/author_v1",
        GUIDE,
        "5-make-its-outputs-the-reference-optional",
    ),
    (
        "Run the others — three times",
        "The spread is how far an arm disagrees with itself.",
        "evh run --config data/configs/tickets_lead2_noisy.yaml --repeat 3",
        "overlap_f1     spread=0.029372   treat deltas below 0.029372 as noise",
        GUIDE,
        "6-run-the-other-arms-three-times-each",
    ),
    (
        "Compare",
        "Read the significance block, not the row numbers.",
        "evh leaderboard --dataset-id tickets_v1",
        "pairs distinguishable: 1 of 3",
        GUIDE,
        "7-compare",
    ),
    (
        "Choose, and record why",
        "Promote with a reason that says what the tests showed; validate in CI.",
        'evh run-promote --run … --reason "leads on silver but differs significantly from neither arm at n=6"',
        "VALIDATION PASSED",
        GUIDE,
        "8-choose",
    ),
    (
        "Then: the next round",
        "Carry what stays, retire what lost with why, close with a conclusion. The goal goes on, before deploy and after.",
        (
            "evh round-retire --goal tickets_summary --round r1 --arm tickets_lead1_v1 --reason …\n"
            "evh round-close --goal tickets_summary --round r1 --conclusion …"
        ),
        "round r1 of tickets_summary closed",
        TUTORIAL4,
        "3-drop-an-arm-and-close-the-round",
    ),
    (
        "When the scoring changes",
        "Preview what a new rule moves; then re-score the round at $0, or adopt the rule from the next round.",
        "evh score-preview --goal tickets_summary",
        "recommended  tickets_lead2_v1",
        TUTORIAL4,
        "7-when-the-scoring-changes",
    ),
    (
        "Then: make it golden",
        "A person's answers, imported as labels and promoted at gold; re-score every run against them for $0.",
        (
            "evh label-import tutorial/gold --dataset-id tickets_v1 --set owner_gold --by owner\n"
            "evh reference-promote --dataset-id tickets_v1 --labels owner_gold --tier gold --reason … --by owner\n"
            "evh rescore --dataset-id tickets_v1 --reference-id gold/tickets_v1 --out data/runs-gold"
        ),
        "NO detectable arm effect · pairs distinguishable: 0 of 6",
        TUTORIAL3,
        "2-make-it-golden",
    ),
    (
        "Optional: re-measure with a judge",
        (
            "LLM judges re-read every arm's stored outputs. The "
            "harness refuses a judge nobody validated; the tutorial's are fake, so it runs labelled."
        ),
        "evh judge-score --dataset-id tickets_v1 --scorer tickets-judge-v1 --unvalidated",
        "data/runs-judged/tickets-judge-v1  (6/6 items, unvalidated judge)",
        TUTORIAL3,
        "5-re-measure-with-an-llm-judge-optional",
    ),
]


def use_page(H, f: dict) -> str:
    cards = "".join(
        f'<div class="pattern reveal"><div class="task">{H.e(var)}</div><h3>{H.e(title)}</h3>'
        f'<p>{H.e(text)}</p><div class="meta"><span>{H.e(metric)}</span>'
        + (
            f'<a href="{H.REPO}/tree/main/examples/{ex}">copy: {H.e(ex)} ↗</a>'
            if ex
            else "<span>any example</span>"
        )
        + "</div></div>"
        for title, var, text, ex, metric in patterns(H, f)
    )
    steps = "".join(
        f'<li class="reveal"><div><h3>{H.e(t)}</h3><p>{H.e(d)} <a href="{doc_href(page, a)}">Guide →</a></p>'
        '<pre class="term">'
        + "\n".join(
            f'<span class="p">$ </span>{H.e(c)}'
            for c in cmd.format(repo=H.REPO, version=H.VERSION).split("\n")
        )
        + (f'\n<span class="c">{H.e(H.q(out, page))}</span>' if out else "")
        + "</pre></div></li>"
        for t, d, cmd, out, page, a in STEPS
    )
    body = f"""
<section class="hero"><div class="wrap">
  <div class="kicker"><b>Use it</b> · on your problem · offline in fifteen minutes</div>
  <h1>Measure <em>your</em> problem.</h1>
  <p class="dek">You do not need our benchmarks. You need a decision to make, a few dozen real inputs, and an afternoon. Write one adapter for your system; the harness brings frozen data, fingerprints, noise, significance and cost — the habits, enforced.</p>
  <div class="btns"><a class="btn primary" href="docs/GUIDE/">Start the guide</a><a class="btn" href="#lifecycle">How it fits together</a><a class="btn" href="method.html">Why it works this way</a></div>
</div></section>

<section class="block" id="lifecycle"><div class="wrap">
  <div class="eyebrow"><span class="num">01</span>The lifecycle</div>
  <h2>Eight things, one direction, and two optional passes.</h2>
  <p class="lede">Every evaluation here — ours and yours — moves through the same eight artifacts; re-measuring the stored outputs later, and the next round, are optional. Pick one to see what it is, where it lives and the command that makes it.</p>
  <div class="lc-explorer">
    <div class="lc-map">{lifecycle(interactive=True)}</div>
    <div class="lc-panels">{lifecycle_panels(H)}</div>
  </div>
</div></section>

<section class="block" id="patterns"><div class="wrap">
  <div class="eyebrow"><span class="num">02</span>Patterns</div>
  <h2>Your question is probably one of these.</h2>
  <p class="lede">Each maps to an eval in this repository you can copy — its adapter, its configs, its scorer — and change the data. The idea underneath all of them — build a private leaderboard for your own application instead of trusting a public one — is Chip Huyen's, from <i>AI Engineering</i> (<a href="docs/INFLUENCES/">influences</a>).</p>
  <div class="patterns">{cards}</div>
</div></section>

<section class="block" id="steps"><div class="wrap">
  <div class="eyebrow"><span class="num">03</span>Step by step</div>
  <h2>Eight steps and four optional ones, on a real example.</h2>
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
      <li><b>A goal</b> — what the evaluation is for: the measure that decides, limits on cost and speed, how a tie is broken.</li>
    </ul></div>
    <div class="byo-col"><h3>The harness gives you</h3><ul>
      <li>Datasets frozen by content hash, re-checked on every use.</li>
      <li>A fingerprint per run: data, prompt, code, model, build.</li>
      <li>Each arm's own noise, measured.</li>
      <li>Paired and Holm-corrected tests — significant or not.</li>
      <li>Billed cost and latency beside quality.</li>
      <li>Re-scoring from stored outputs for $0; validation for CI; baselines with reasons.</li>
      <li>A recommendation per goal, with its reasons, beside the baseline a person promoted.</li>
      <li>A catalog of every goal, dataset (and what is inside it), arm and run, and an inspector that tests arms against a baseline and shows one item's outputs (<a href="{H.CATALOG}">ours</a>).</li>
      <li>The same read commands as MCP tools for an agent: <code>evh mcp</code> on your machine or for a team (<a href="docs/harness/INTEGRATION/#for-an-agent-evh-mcp">how</a>).</li>
      <li>Optional LLM judges that re-measure stored outputs, refused until validated against people.</li>
    </ul></div>
    <div class="byo-col check"><h3>Start on Monday</h3><ul>
      <li>Write the question as a goal: <i>can ticket routing move to the cheaper model?</i></li>
      <li>Collect real inputs; freeze them.</li>
      <li>Write gold answers for a slice yourself.</li>
      <li>Write the adapter; one config per candidate.</li>
      <li>Dry-run; set a cost cap.</li>
      <li>Run each arm three times; note its noise.</li>
      <li>Test the comparison you named; promote with a reason; put <code>evh validate</code> in CI.</li>
    </ul></div>
  </div>
</div></section>

<section class="block" id="doors"><div class="wrap">
  <div class="eyebrow"><span class="num">05</span>Three doors</div>
  <h2>Look at ours, rerun ours, or build yours.</h2>
  <div class="cards doors">
    <a class="card" href="{H.CATALOG}"><div class="task">Look at ours</div><h3>Every run, in the catalog.</h3><p>The six evals as the harness shows them: every goal, dataset, arm and reference set, and an inspector that tests any arms against a baseline, item by item. Nothing to install; your agent can ask it too, at <code>evals.humancopilot.eu/mcp</code>.</p><div class="meta"><span>evals.humancopilot.eu/catalog</span><b>The catalog →</b></div></a>
    <a class="card" href="docs/REPRODUCE/"><div class="task">Rerun ours</div><h3>Check every finding yourself.</h3><p>Five levels, from recomputing every number for $0 to rerunning every model with one key — with a replication card that re-tests every significance verdict.</p><div class="meta"><span>make verify</span><b>Reproduce it →</b></div></a>
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
    return H.page(
        "Use it on your problem — eval-harness",
        "Apply the method to your own system: the evaluation lifecycle, patterns for "
        "common questions, seven steps and an optional judging step on a real example, "
        "and what you write vs. what "
        "the harness gives you.",
        body + H.author("use"),
        here="use",
    )


# ── borrowed by the landing and eval pages ──────────────────────────────────
def landing_teaser(H, f: dict, num: str = "03") -> str:
    chs = chapters(H, f)
    habits = "".join(
        f'<a class="habit-card reveal" href="method.html#{c["id"]}"><span class="n">{i:02d}</span>'
        f"<b>{H.e(c['title'])}</b><span>{H.e(c['short'])}</span></a>"
        for i, c in enumerate(chs, 1)
    )
    return f"""
<section class="block" id="method"><div class="wrap">
  <div class="eyebrow"><span class="num">{num}</span>The method</div>
  <h2>The harness enforces a method.</h2>
  <p class="lede">Nothing here needed special access or a big budget. It took six habits — each learned by getting something wrong first — and a harness that enforces them. They work on any problem you can put into a dataset. The framing builds on Chip Huyen's <i>AI Engineering</i> and <i>Designing Machine Learning Systems</i>.</p>
  <div class="habits">{habits}</div>
  <div class="btns"><a class="btn primary" href="method.html">Read the method</a><a class="btn" href="use.html">Use it on your problem</a></div>
</div></section>
"""


def eval_lesson(H, x: dict) -> tuple:
    """(chapter id, chapter title, what this eval taught) for an eval page."""
    slug = x["slug"]
    if slug == "summarization":
        return (
            "data",
            "The data is the instrument.",
            H.q(
                "The committed sample turned out to be all CNN's articles. A calibration row "
                "— copying the first three sentences on the full test set, against its "
                "published score — is what showed it.",
                SUMM,
            ),
        )
    if slug == "ag-news":
        return (
            "gold",
            "Silver is not gold.",
            H.q(
                "Nearly the whole lead of the three fine-tunes sits in 17 items whose gold "
                "labels most of the hosted field disputes.",
                CLASS,
            ),
        )
    if slug == "dbpedia":
        return (
            "tested",
            "Tested, not read.",
            (
                f"{x['n_contenders']} arms are not significantly different from the leader. A saturated benchmark "
                "sorts; it does not rank — and the table still prints them first, second, third."
            ),
        )
    if slug == "few-nerd":
        return (
            "gold",
            "Silver is not gold.",
            H.q(
                "57% of the winner's margin over openai_m is one entity type the prompt "
                "never defined (30–57% across the hosted arms).",
                NER,
            )
            + " A clean win can still be partly a win at the "
            "annotation, not the task.",
        )
    if slug == "summeval":
        return (
            "gold",
            "Silver is not gold.",
            H.q(
                "The best of the 24 judges agrees with the experts at τ 0.5398 — better than "
                "any free scorer measured, and, against two experts, 93% of one expert's "
                "agreement with the other two.",
                JUDGE,
            )
            + " An LLM judge is a silver reference. This eval is what checking one "
            "against a gold set looks like.",
        )
    return (
        "noise",
        "Measure the noise before the difference.",
        H.q("The pilot slice's leader finished 10th of 19, a rank inside a tie.", RET),
    )
