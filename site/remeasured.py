"""The judging page: what re-measuring a frozen experiment changed, and what that teaches
about LLM judges.

Same rules as build.py: every number typed into quoted prose goes through `q()` and must
appear in the report it cites; every other number is computed from the committed runs,
verdicts and adjudication records (figures.compute()["remeasure"]). Helpers arrive as `H`.
"""

from __future__ import annotations

SUMM = "research/REPORT_SUMMARIZATION.md"
CLASS = "research/REPORT_CLASSIFICATION.md"
JUDGE = "research/REPORT_SUMMEVAL.md"


# ── charts ──────────────────────────────────────────────────────────────────
def rank_shift(H, rows: list, left: str, right: str, highlight: tuple, fmt1, fmt2,
               width: int = 1000, height: int = 560, compact: bool = False) -> str:
    """Every arm's rank under the old measurement (left) and the new one (right). Lines are
    coloured by kind; the highlighted arms are drawn thick and labelled on both sides."""
    n = len(rows)
    if compact:
        width, height = 400, 520
    top, bottom = 52, height - 18
    x0, x1 = (150, width - 150) if not compact else (110, width - 110)
    fs = 15 if compact else 14

    def y(r):
        return top + (r - 1) * (bottom - top) / (n - 1)

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{H.e(left)} rank against {H.e(right)} rank">',
           f'<text x="{x0}" y="22" text-anchor="middle" class="t-muted" font-size="{fs}">{H.e(left)}</text>',
           f'<text x="{x1}" y="22" text-anchor="middle" class="t-muted" font-size="{fs}">{H.e(right)}</text>',
           f'<text x="{x0}" y="40" text-anchor="middle" class="t-muted" font-size="{fs - 3}">rank 1 at the top</text>',
           f'<text x="{x1}" y="40" text-anchor="middle" class="t-muted" font-size="{fs - 3}">rank 1 at the top</text>',
           f'<line x1="{x0}" x2="{x0}" y1="{top - 6}" y2="{bottom + 6}" class="axis"/>',
           f'<line x1="{x1}" x2="{x1}" y1="{top - 6}" y2="{bottom + 6}" class="axis"/>']
    hi = [r for r in rows if r["arm"] in highlight]
    for r in sorted(rows, key=lambda r: r["arm"] in highlight):
        k = H.kind_of(r)
        on = r["arm"] in highlight
        tip = (f'{r["arm"]}\n{left}: {fmt1(r["v1"])} (rank {r["r1"]} of {n})\n'
               f'{right}: {fmt2(r["v2"])} (rank {r["r2"]} of {n})')
        out.append(f'<line x1="{x0}" y1="{y(r["r1"]):.1f}" x2="{x1}" y2="{y(r["r2"]):.1f}" class="s-{k}" '
                   f'stroke-width="{3.5 if on else 1.2}" opacity="{1 if on else 0.4}"/>'
                   f'<circle cx="{x0}" cy="{y(r["r1"]):.1f}" r="{5.5 if on else 3.5}" class="dot k-{k}" data-tip="{H.e(tip)}"><title>{H.e(tip)}</title></circle>'
                   f'<circle cx="{x1}" cy="{y(r["r2"]):.1f}" r="{5.5 if on else 3.5}" class="dot k-{k}" data-tip="{H.e(tip)}"><title>{H.e(tip)}</title></circle>')
    ly = H.spread([(r["arm"], y(r["r1"])) for r in hi], 18)
    ry = H.spread([(r["arm"], y(r["r2"])) for r in hi], 18)
    for r in hi:
        lab_l = f'{r["arm"]} {r["r1"]}' if compact else f'{r["arm"]} · {r["r1"]}'
        lab_r = f'{r["r2"]} {r["arm"]}' if compact else f'{r["r2"]} · {r["arm"]}'
        out.append(f'<text x="{x0 - 12}" y="{ly[r["arm"]] + 5:.1f}" text-anchor="end" class="t-ink" font-size="{fs}">{H.e(lab_l)}</text>'
                   f'<text x="{x1 + 12}" y="{ry[r["arm"]] + 5:.1f}" class="t-ink" font-size="{fs}">{H.e(lab_r)}</text>')
    out.append("</svg>")
    return "".join(out)


def tau_bars(H, items: list, width: int = 1000, compact: bool = False) -> str:
    """Horizontal bars: how well each instrument agrees with SummEval's experts (mean tau)."""
    if compact:
        width = 400
    row, top = (46 if compact else 40), 10
    lab = 150 if compact else 300
    x0, x1 = lab, width - (60 if compact else 90)
    height = top + row * len(items) + 24
    hi = 0.6
    fs = 15 if compact else 14

    def x(v):
        return x0 + v / hi * (x1 - x0)

    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Agreement with expert judgements, by instrument">']
    for t in (0, 0.2, 0.4, 0.6):
        out.append(f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{top}" y2="{height - 22}" class="axis" opacity="0.5"/>'
                   f'<text x="{x(t):.1f}" y="{height - 4}" text-anchor="middle" class="t-muted" font-size="{fs - 2}">{t:.1f}</text>')
    for i, (name, note, v, k) in enumerate(items):
        yy = top + i * row
        out.append(f'<text x="{x0 - 12}" y="{yy + row / 2 + 1:.1f}" text-anchor="end" class="t-ink" font-size="{fs}">{H.e(name)}</text>'
                   + (f'<text x="{x0 - 12}" y="{yy + row / 2 + 17:.1f}" text-anchor="end" class="t-muted" font-size="{fs - 3}">{H.e(note)}</text>' if note and not compact else "")
                   + f'<rect x="{x0}" y="{yy + 8}" width="{x(v) - x0:.1f}" height="{row - 18}" rx="3" class="k-{k}"/>'
                   f'<text x="{x(v) + 8:.1f}" y="{yy + row / 2 + 4:.1f}" class="t-ink" font-size="{fs}">{v:.2f}</text>')
    out.append("</svg>")
    return "".join(out)


# ── the page ────────────────────────────────────────────────────────────────
def figures_for(H, f: dict) -> dict:
    """The page's numbers, checked: each claim the prose makes is asserted on the data."""
    r = f["remeasure"]
    ag, db, sm, se = r["ag"], r["db"], r["summ"], r["summeval"]
    by = {x["slug"]: x for x in f["experiments"]}
    agr = {a["arm"]: a for a in ag["arms"]}
    smr = {a["arm"]: a for a in sm["arms"]}
    fts = ("bert_base_ta", "bert_base_fy", "bert_mini")
    hosted_ag = [a for a in ag["arms"] if a["kind"] == "hosted"]
    hosted_sm = [a for a in sm["arms"] if a["kind"] == "hosted"]
    fig = sm["fig"]
    H.require(min(a["v2"] for a in hosted_ag) > max(agr[a]["v2"] for a in fts),
              "AG News v2: every hosted arm above every fine-tune")
    H.require(min(a["v2"] for a in hosted_sm) > smr["bart_l"]["v2"],
              "summarisation judged: every hosted arm above bart_l")
    H.require(fig["human_check"]["judge_prefers_deepseek_m"] == fig["human_check"]["pairs"],
              "the judges preferred deepseek_m on every human-check pair")
    # The headline ("a free model first or not separable from first") counts AG News and
    # summarisation today; on the re-measured scores the reports say the leader is hosted and
    # separated from every local arm there (q-quoted on the page), so both would leave it.
    for slug in ("ag-news", "summarization"):
        x = by[slug]
        H.require(x["top"]["kind"] == "local", f"{slug}: a local arm leads on the primary")
    H.require(ag["arms"] and max(ag["arms"], key=lambda a: a["v2"])["kind"] == "hosted"
              and max(sm["arms"], key=lambda a: a["v2"])["kind"] == "hosted",
              "on the re-measured scores both leaders are hosted")
    return {"ag": ag, "db": db, "sm": sm, "se": se, "fig": fig, "agr": agr, "smr": smr,
            "fts": fts, "headline_now": f["local_first_or_tied"],
            "headline_remeasured": f["local_first_or_tied"] - 2, "n_exp": len(f["experiments"]),
            "hosted_sm_range": (min(a["v2"] for a in hosted_sm), max(a["v2"] for a in hosted_sm)),
            "sm_leader": max(sm["arms"], key=lambda a: a["v2"]),
            "ag_leader": max(ag["arms"], key=lambda a: a["v2"])}


def judging_page(H, f: dict) -> str:
    g = figures_for(H, f)
    q, e = H.q, H.e
    ag, db, sm, se, fig, agr, smr = g["ag"], g["db"], g["sm"], g["se"], g["fig"], g["agr"], g["smr"]
    hc = fig["human_check"]
    bart, ldr = smr["bart_l"], g["sm_leader"]
    lo, hi = g["hosted_sm_range"]
    pos_lo, pos_hi = fig["position_mean_abs_diff_range"]
    noi_lo, noi_hi = fig["noise_mean_abs_diff_range"]
    by = {x["slug"]: x for x in f["experiments"]}
    se_arms = {a["arm"]: a for a in by["summeval"]["arms"]}
    bars = [("coverage", "what summarisation ranks by", se["coverage"], "baseline"),
            ("ROUGE-1", "the field's usual metric", se["rouge1"], "baseline"),
            ("UniEval", "free, trained to judge", se["best_free_tau"], "local"),
            ("qwen_s", "LLM judge used below", se["qwen_s"], H.kind_of(se_arms["qwen_s"])),
            ("gemma_l", "LLM judge used below", se["gemma_l"], H.kind_of(se_arms["gemma_l"])),
            (se["best_judge"], "the best of 24 LLM judges", se["best_judge_tau"],
             H.kind_of(se_arms[se["best_judge"]]))]
    ratio = se["gemma_l"] / se["coverage"]
    fmt_cov = lambda v: f"coverage {v:.4f}"  # noqa: E731
    fmt_j = lambda v: f"judge score {v:.2f} of 5"  # noqa: E731
    fmt_acc = lambda v: f"accuracy {v:.4f}"  # noqa: E731
    sm_chart = H.both(rank_shift(H, sm["arms"], "coverage (primary)", "validated LLM judges",
                                 ("bart_l", "deepseek_m", "anthropic_l", "lead3"), fmt_cov, fmt_j),
                      rank_shift(H, sm["arms"], "coverage", "judges",
                                 ("bart_l", "deepseek_m", "anthropic_l"), fmt_cov, fmt_j, compact=True))
    ag_chart = H.both(rank_shift(H, ag["arms"], "dataset gold (primary)", "adjudicated gold",
                                 ("bert_base_ta", "bert_mini", "anthropic_l", "gemma_m"), fmt_acc, fmt_acc),
                      rank_shift(H, ag["arms"], "dataset gold", "adjudicated",
                                 ("bert_base_ta", "bert_mini", "anthropic_l"), fmt_acc, fmt_acc, compact=True))
    fts = [agr[a] for a in g["fts"]]
    db_fy = next(a for a in db["arms"] if a["arm"] == "bert_base_fy")
    facts = [("Re-measured", "3 experiments: summarisation by LLM judges; AG News and DBpedia "
                             "against labels a person corrected"),
             ("Re-run", "nothing: every model output is the one committed when it was measured"),
             ("Cost", f'{H.money(fig["billed_usd"])} for {fig["calls"]} judge calls; $0 for the labels'),
             ("Primary metric", "unchanged in all three, by decision (below)")]
    facts_html = "".join(f'<div class="fact"><div class="k">{e(k)}</div><div class="v">{e(v)}</div></div>'
                         for k, v in facts)
    checklist = [
        ("Validate it against people, on outputs like yours.",
         "The gate refuses a judge whose validation run is missing, and one that does not beat the best "
         "free scorer on the same human ratings. What it cannot check is whether those ratings look like "
         "your outputs. Here they did not, and that is where it went wrong."),
        ("Use two judges from different vendors, blind.",
         "Each judge is reported, and how far they agree. Arm names are hidden and the order shuffled, so "
         "a judge cannot favour a name or a slot, and a judge's own family is flagged."),
        ("Measure the judge's own noise and position bias.",
         f"A second shuffle and a repeat on a subset. Here the reshuffle moved per-article scores by "
         f"{pos_lo:.2f}–{pos_hi:.2f} and a repeat by {noi_lo:.2f}–{noi_hi:.2f}: a gap between arms "
         "smaller than that is not a difference."),
        ("Keep every verdict.",
         "Each raw reply is stored, so the pass resumes, costs $0 to re-read, and anyone can check what the "
         "judge said."),
        ("Read some yourself before you trust the ranking.",
         "Agreement between two judges is not agreement with people. One afternoon reading 20 pairs is what "
         "caught the problem here; the primary metric changes only after a check like that agrees."),
    ]
    check_html = "".join(f'<li><div><h3>{e(h)}</h3><p>{e(p)}</p></div></li>' for h, p in checklist)
    body = f"""
<section class="hero"><div class="wrap">
  <div class="kicker"><b>Judging</b> · re-measured, not re-run</div>
  <h1>Change the ruler, <em>not the run.</em></h1>
  <p class="dek">Every model output in these experiments is frozen, so when a better way to score them arrives the experiment can be measured again for the price of the scoring alone. We did it twice: a person corrected disputed labels, and validated LLM judges re-scored every summary. Both moved a headline result. The judges then disagreed with a person. Judging is the strongest instrument on this site, and the easiest to over-trust.</p>
  <div class="facts">{facts_html}</div>
  <div class="btns"><a class="btn primary" href="#value">Why judge</a><a class="btn" href="#checklist">Judging, done right</a><a class="btn" href="../docs/GUIDE/#10-optional-re-measure-with-an-llm-judge">Try it, offline</a></div>
</div></section>

<section class="block" id="value"><div class="wrap">
  <div class="eyebrow"><span class="num">01</span>Why judge at all</div>
  <h2>The metric was the weak link.</h2>
  <div class="prose">
    <p>The summarisation experiment ranks by <strong>coverage</strong>, an overlap score against reference summaries. SummEval measures how well a scorer agrees with expert annotators. Coverage agrees with them at τ {se["coverage"]:.2f}. The two LLM judges used below agree at {se["gemma_l"]:.2f} and {se["qwen_s"]:.2f}, about {ratio:.0f}× the agreement of the metric the leaderboard was sorted by.</p>
    <p>{q("The best judges reach 93% of a human's agreement (the best of 24, chosen on the same articles; 92% held out).", JUDGE)} That is the case for judging: when the cheap metric barely tracks what people think, a validated judge is the better instrument, and it can re-score outputs you already have.</p>
  </div>
  <figure class="chart" style="margin-top:32px;max-width:900px">{H.both(tau_bars(H, bars), tau_bars(H, bars, compact=True))}<figcaption>Mean Kendall τ against SummEval's expert annotators, 100 articles × 16 summaries. 0 is no agreement. Coloured by kind, as elsewhere on this site.</figcaption></figure>
</div></section>

<section class="block" id="judged"><div class="wrap">
  <div class="eyebrow"><span class="num">02</span>A judge re-measures summarisation</div>
  <h2>First on coverage. {H.ordinal(bart["r2"]).capitalize()} on the judges.</h2>
  <div class="prose">
    <p>The two judges read every article with all {sm["n_arms"]} arms' summaries, names hidden and order shuffled: {fig["calls"]} calls, {H.money(fig["billed_usd"])}, {sm["items_scored"]} of {fig["items_total"]} articles scored. On their score <strong>every hosted LLM ranks above every BART model</strong>. <code>bart_l</code>, first on coverage, scores {bart["v2"]:.2f} of 5 and ranks {H.ordinal(bart["r2"])} of {sm["n_arms"]}; the hosted LLMs score {lo:.2f}–{hi:.2f}, with <code>{ldr["arm"]}</code> first ({H.ordinal(ldr["r1"])} on coverage).</p>
    <p>The judges agree closely with each other: Spearman {fig["agreement_arm_mean_spearman"]:.2f} over arm means. Re-ordering the summaries moved per-article scores by {pos_lo:.2f}–{pos_hi:.2f}, a repeat call by {noi_lo:.2f}–{noi_hi:.2f}. By every check the harness runs, a clean result.</p>
  </div>
  <figure class="chart" style="margin-top:32px">{legend_html(H)}{sm_chart}<figcaption>Each line is one arm: its rank on coverage (left) and on the judges' mean score (right). Tap a dot for both scores.</figcaption></figure>
</div></section>

<section class="block" id="person"><div class="wrap">
  <div class="eyebrow"><span class="num">03</span>Then a person read them</div>
  <h2>{hc["human_prefers_bart_l"]} to {hc["human_prefers_deepseek_m"]} the other way.</h2>
  <ol class="findings">
    <li><div><h3>The one blind human check disagreed.</h3><p>One non-expert reader compared {hc["pairs"]} pairs of <code>bart_l</code> and <code>deepseek_m</code> summaries, blind, on truncated articles, and preferred <code>bart_l</code> {hc["human_prefers_bart_l"]} to {hc["human_prefers_deepseek_m"]} ({q("sign test p = 0.115", SUMM)}). The judges preferred <code>deepseek_m</code> on all {hc["judge_prefers_deepseek_m"]}. Scored one summary at a time instead of in lists, they still rated <code>deepseek_m</code> higher on {fig["pointwise"]["deepseek_m_above_bart_l"]} of {fig["pointwise"]["articles"]} articles and never lower.</p></div></li>
    <li><div><h3>On published human ratings of modern summaries, the judges look like people — with a lean.</h3><p>{q("On a different pair, the GPT-3 and BART-based BRIO summaries of Goyal, Li & Durrett (2022, CC BY 4.0; 100 CNN articles, three annotators each), the judges agree with people about as well as people agree with each other: against one annotator they score 0.498 (gemma_l) and 0.526 (qwen_s), annotators against each other 0.454, chance 0.333. On the same articles they prefer the GPT-3 summary more often than the annotators do (72.7% and 77.0% against 63.6% and 63.2%; the 95% intervals overlap for both judges).", SUMM)}</p></div></li>
    <li><div><h3>So the judged ranking is directional at most, and coverage stays primary.</h3><p>The judges were validated on SummEval's summaries, written by systems of 2019. The arms here are modern LLMs. A validation earned on one kind of output does not carry to another, and two judges agreeing with each other is not two judges agreeing with people.</p></div></li>
  </ol>
</div></section>

<section class="block" id="labels"><div class="wrap">
  <div class="eyebrow"><span class="num">04</span>A person re-measures the labels</div>
  <h2>The fine-tunes' lead was the dataset's convention.</h2>
  <div class="prose">
    <p>On AG News three small fine-tunes led every hosted LLM, concentrated in {ag["changed"]} items the hosted field mostly got wrong. One reader adjudicated by topic every item the hosted field missed and every item a fine-tune missed, {ag["n_items"]} in all, shown each item's text, its gold label and the hosted majority's answer. The gold was wrong on all {ag["changed"]}: AG News files company news from a technology desk as Sci/Tech and non-US news, sport included, as World.</p>
    <p>Re-scored against those labels for $0, every hosted LLM scores above every fine-tune. The fine-tunes fall from {", ".join(str(a["r1"]) for a in fts)} to {"–".join(str(x) for x in (min(a["r2"] for a in fts), max(a["r2"] for a in fts)))} of {ag["n_arms"]}; <code>{g["ag_leader"]["arm"]}</code> rises from {H.ordinal(g["ag_leader"]["r1"])} to first at {g["ag_leader"]["v2"]:.4f}. {q("It is separated from all three (tied at 0.9050).", CLASS)} On DBpedia {db["changed"]} labels were wrong; the top stays a crowd, and <code>bert_base_fy</code> moves from {H.ordinal(db_fy["r1"])} to {H.ordinal(db_fy["r2"])} at an unchanged {db_fy["v1"]:.4f}.</p>
    <p>Here the better instrument was a person, not a model, and the lesson is the same: a fine-tune trained on a dataset learns its conventions. If your labels follow a house convention, that is what you want. If they mean what the words say, it is not.</p>
  </div>
  <figure class="chart" style="margin-top:32px">{legend_html(H)}{ag_chart}<figcaption>AG News, {ag["n_arms"]} arms: rank on the dataset's gold (left) and on the adjudicated gold (right).</figcaption></figure>
</div></section>

<section class="block" id="decided"><div class="wrap">
  <div class="eyebrow"><span class="num">05</span>What we did with it</div>
  <h2>Both stay beside the primary. Neither replaces it.</h2>
  <div class="cols"><div class="prose">
    <p>A re-measurement is written beside the original, never over it, and an experiment's primary metric changes only by a recorded decision with the old one kept. Both decisions here kept the original:</p>
    <p><strong>AG News and DBpedia</strong> keep the dataset's gold: anyone can repeat it, and the adjudication is one reader's, made while seeing the hosted answer. <strong>Summarisation</strong> keeps coverage: the judges' ranking has not been confirmed by people on these summaries, and the one check that exists went the other way.</p>
    <p>It matters. A free model is first, or not separable from first, in {g["headline_now"]} of the {g["n_exp"]} experiments on their primary metrics. On the re-measured scores AG News and summarisation would leave that count, and it would be {g["headline_remeasured"]} of {g["n_exp"]}. That is how much a measurement decision can move a headline, and why the decision is recorded rather than made by whichever number came last.</p>
  </div>
  <div class="note"><b>What would settle it.</b> Several readers comparing full articles, not one reader on truncated ones; or judges validated on published human ratings of LLM-written summaries rather than 2019 ones. Either is a re-measurement of the same frozen outputs.</div></div>
</div></section>

<section class="block" id="checklist"><div class="wrap">
  <div class="eyebrow"><span class="num">06</span>Judging, done right</div>
  <h2>Five rules the harness enforces, or asks you to.</h2>
  <ol class="findings">{check_html}</ol>
</div></section>

<section class="block" id="yours"><div class="wrap">
  <div class="eyebrow"><span class="num">07</span>On your outputs</div>
  <h2>Re-measure what you already have.</h2>
  <div class="cols"><div class="prose">
    <p>A judge scorer is one file: two or more judges, the task they score (what an item is, what the outputs are, the dimensions, the scale), the prompt, and the runs that validated each judge against people. The harness refuses one that is not validated, freezes a blinded judging set, stores every verdict and writes scored runs the leaderboard and the paired tests read unchanged. It is optional: nothing else in the harness needs it.</p>
    <div class="btns"><a class="btn primary" href="../docs/GUIDE/#10-optional-re-measure-with-an-llm-judge">Try it offline, $0</a><a class="btn" href="../docs/harness/RUNBOOK/#12-re-measure-with-a-validated-judge">The runbook</a><a class="btn" href="{H.BLOB}/docs/adr/ADR-0001-judge-scorers.md">The design</a><a class="btn" href="{H.BLOB}/{SUMM}">The summarisation report</a></div>
  </div>
<pre class="term"><span class="c"># price it: builds the judging set, calls nothing</span>
<span class="p">$ </span>make judge-score DATASET_ID=my_v1 SCORER=my-judge ARGS=--dry-run
<span class="c"># judge, capped and resumable; refused until validated</span>
<span class="p">$ </span>make judge-score DATASET_ID=my_v1 SCORER=my-judge
<span class="c"># rank and test on the judged scores</span>
<span class="p">$ </span>EVAL_RUNS_DIR=data/runs-judged/my-judge make leaderboard DATASET_ID=my_v1</pre></div>
</div></section>
{H.author("judging")}"""
    return H.page("Change the ruler, not the run — judging · eval-harness",
                  "What re-measuring frozen experiments with validated LLM judges and corrected labels "
                  "changed, why a judge beat the metric, and why a person still had the last word.",
                  body, depth=1, here="judging")


def legend_html(H) -> str:
    return H.legend(band=False, baseline=True)
