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
def rank_shift(
    H,
    rows: list,
    left: str,
    right: str,
    highlight: tuple,
    fmt1,
    fmt2,
    width: int = 1000,
    height: int = 560,
    compact: bool = False,
) -> str:
    """Every arm's rank under the old measurement (left) and the new one (right). Lines are
    coloured by kind; the highlighted arms are drawn thick and labelled on both sides."""
    n = len(rows)
    if compact:
        width, height = 400, 520
    top, bottom = 52, height - 18
    x0, x1 = (150, width - 150) if not compact else (128, width - 136)
    fs = 14

    def y(r):
        return top + (r - 1) * (bottom - top) / (n - 1)

    out = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{H.e(left)} rank against {H.e(right)} rank">',
        f'<text x="{x0}" y="22" text-anchor="middle" class="t-muted" font-size="{fs}">{H.e(left)}</text>',
        f'<text x="{x1}" y="22" text-anchor="middle" class="t-muted" font-size="{fs}">{H.e(right)}</text>',
        f'<text x="{x0}" y="40" text-anchor="middle" class="t-muted" font-size="{fs - 3}">rank 1 at the top</text>',
        f'<text x="{x1}" y="40" text-anchor="middle" class="t-muted" font-size="{fs - 3}">rank 1 at the top</text>',
        f'<line x1="{x0}" x2="{x0}" y1="{top - 6}" y2="{bottom + 6}" class="axis"/>',
        f'<line x1="{x1}" x2="{x1}" y1="{top - 6}" y2="{bottom + 6}" class="axis"/>',
    ]
    hi = [r for r in rows if r["arm"] in highlight]
    for r in sorted(rows, key=lambda r: r["arm"] in highlight):
        k = H.kind_of(r)
        on = r["arm"] in highlight
        tip = (
            f"{r['arm']}\n{left}: {fmt1(r['v1'])} (rank {r['r1']} of {n})\n"
            f"{right}: {fmt2(r['v2'])} (rank {r['r2']} of {n})"
        )
        out.append(
            f'<line x1="{x0}" y1="{y(r["r1"]):.1f}" x2="{x1}" y2="{y(r["r2"]):.1f}" class="s-{k}" '
            f'stroke-width="{3.5 if on else 1.2}" opacity="{1 if on else 0.4}"/>'
            f'<circle cx="{x0}" cy="{y(r["r1"]):.1f}" r="{5.5 if on else 3.5}" class="dot k-{k}" data-tip="{H.e(tip)}"><title>{H.e(tip)}</title></circle>'
            f'<circle cx="{x1}" cy="{y(r["r2"]):.1f}" r="{5.5 if on else 3.5}" class="dot k-{k}" data-tip="{H.e(tip)}"><title>{H.e(tip)}</title></circle>'
        )
    ly = H.spread([(r["arm"], y(r["r1"])) for r in hi], 18)
    ry = H.spread([(r["arm"], y(r["r2"])) for r in hi], 18)
    for r in hi:
        lab_l = f"{r['arm']} {r['r1']}" if compact else f"{r['arm']} · {r['r1']}"
        lab_r = f"{r['r2']} {r['arm']}" if compact else f"{r['r2']} · {r['arm']}"
        out.append(
            f'<text x="{x0 - 12}" y="{ly[r["arm"]] + 5:.1f}" text-anchor="end" class="t-ink" font-size="{fs}">{H.e(lab_l)}</text>'
            f'<text x="{x1 + 12}" y="{ry[r["arm"]] + 5:.1f}" class="t-ink" font-size="{fs}">{H.e(lab_r)}</text>'
        )
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
    fs = 14

    def x(v):
        return x0 + v / hi * (x1 - x0)

    out = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Agreement with expert judgements, by instrument">'
    ]
    for t in (0, 0.2, 0.4, 0.6):
        out.append(
            f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{top}" y2="{height - 22}" class="axis" opacity="0.5"/>'
            f'<text x="{x(t):.1f}" y="{height - 4}" text-anchor="middle" class="t-muted" font-size="{fs - 2}">{t:.1f}</text>'
        )
    for i, (name, note, v, k) in enumerate(items):
        yy = top + i * row
        out.append(
            f'<text x="{x0 - 12}" y="{yy + row / 2 + 1:.1f}" text-anchor="end" class="t-ink" font-size="{fs}">{H.e(name)}</text>'
            + (
                f'<text x="{x0 - 12}" y="{yy + row / 2 + 17:.1f}" text-anchor="end" class="t-muted" font-size="{fs - 3}">{H.e(note)}</text>'
                if note and not compact
                else ""
            )
            + f'<rect x="{x0}" y="{yy + 8}" width="{x(v) - x0:.1f}" height="{row - 18}" rx="3" class="k-{k}"/>'
            f'<text x="{x(v) + 8:.1f}" y="{yy + row / 2 + 4:.1f}" class="t-ink" font-size="{fs}">{v:.2f}</text>'
        )
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
    H.require(
        min(a["v2"] for a in hosted_ag) > max(agr[a]["v2"] for a in fts),
        "AG News v2: every hosted arm above every fine-tune",
    )
    H.require(
        min(a["v2"] for a in hosted_sm) > smr["bart_l"]["v2"],
        "summarisation judged: every hosted arm above bart_l",
    )
    H.require(
        fig["human_check"]["judge_prefers_deepseek_m"] == fig["human_check"]["pairs"],
        "the judges preferred deepseek_m on every human-check pair",
    )
    # The headline ("a free model first or not separable from first") counts AG News and
    # summarisation today; on the re-measured scores the reports say the leader is hosted and
    # separated from every local arm there (q-quoted on the page), so both would leave it.
    for slug in ("ag-news", "summarization"):
        x = by[slug]
        H.require(x["top"]["kind"] == "local", f"{slug}: a local arm leads on the primary")
    H.require(
        ag["arms"]
        and max(ag["arms"], key=lambda a: a["v2"])["kind"] == "hosted"
        and max(sm["arms"], key=lambda a: a["v2"])["kind"] == "hosted",
        "on the re-measured scores both leaders are hosted",
    )
    # The same re-measurement moves the other headline too: in both experiments the dearest
    # hosted model is the re-measured leader.
    for slug, rows in (("ag-news", ag["arms"]), ("summarization", sm["arms"])):
        H.require(
            by[slug]["dearest"]["arm"] == max(rows, key=lambda a: a["v2"])["arm"],
            f"{slug}: the dearest model leads on the re-measured score",
        )
    # "2 of 6" and "3 of 6" also need DBpedia, the third re-measured experiment, to stay put:
    # the dearest model not first there, and the top a crowd (q-quoted on the page).
    H.require(
        by["dbpedia"]["dearest"]["arm"] != max(db["arms"], key=lambda a: a["v2"])["arm"],
        "dbpedia: the dearest model is not first on the adjudicated labels",
    )
    H.require(
        by["dbpedia"]["dearest"]["arm"] != by["dbpedia"]["top"]["arm"],
        "dbpedia: the dearest model is not first on the primary",
    )
    return {
        "ag": ag,
        "db": db,
        "sm": sm,
        "se": se,
        "fig": fig,
        "agr": agr,
        "smr": smr,
        "dearest_first_remeasured": H.remeasured_counts(f)["dearest_first"],
        "dearest": by["ag-news"]["dearest"]["arm"],
        "fts": fts,
        "headline_now": f["local_first_or_tied"],
        "headline_remeasured": f["local_first_or_tied"] - H.remeasured_counts(f)["local_lost"],
        "n_exp": len(f["experiments"]),
        "hosted_sm_range": (min(a["v2"] for a in hosted_sm), max(a["v2"] for a in hosted_sm)),
        "sm_leader": max(sm["arms"], key=lambda a: a["v2"]),
        "ag_leader": max(ag["arms"], key=lambda a: a["v2"]),
    }


def judging_page(H, f: dict) -> str:
    g = figures_for(H, f)
    q, qv, e = H.q, H.qv, H.e
    ag, db, sm, se, fig, agr, smr = g["ag"], g["db"], g["sm"], g["se"], g["fig"], g["agr"], g["smr"]
    hc = fig["human_check"]
    bart, ldr = smr["bart_l"], g["sm_leader"]
    lo, hi = g["hosted_sm_range"]
    pos_lo, pos_hi = fig["position_mean_abs_diff_range"]
    noi_lo, noi_hi = fig["noise_mean_abs_diff_range"]
    by = {x["slug"]: x for x in f["experiments"]}
    se_arms = {a["arm"]: a for a in by["summeval"]["arms"]}
    bars = [
        ("coverage", "what summarisation ranks by", se["coverage"], "baseline"),
        ("ROUGE-1", "the field's usual metric", se["rouge1"], "baseline"),
        ("UniEval", "free, trained to judge", se["best_free_tau"], "local"),
        ("qwen_s", "LLM judge used below", se["qwen_s"], H.kind_of(se_arms["qwen_s"])),
        ("gemma_l", "LLM judge used below", se["gemma_l"], H.kind_of(se_arms["gemma_l"])),
        (
            se["best_judge"],
            "the best of 24 LLM judges",
            se["best_judge_tau"],
            H.kind_of(se_arms[se["best_judge"]]),
        ),
    ]
    fmt_cov = lambda v: f"coverage {v:.4f}"  # noqa: E731
    fmt_j = lambda v: f"judge score {v:.2f} of 5"  # noqa: E731
    fmt_acc = lambda v: f"accuracy {v:.4f}"  # noqa: E731
    sm_chart = H.both(
        rank_shift(
            H,
            sm["arms"],
            "coverage (primary)",
            "SummEval-validated judges",
            ("bart_l", "deepseek_m", "anthropic_l", "lead3"),
            fmt_cov,
            fmt_j,
        ),
        rank_shift(
            H,
            sm["arms"],
            "coverage",
            "judges",
            ("bart_l", "deepseek_m", "anthropic_l"),
            fmt_cov,
            fmt_j,
            compact=True,
        ),
    )
    ag_chart = H.both(
        rank_shift(
            H,
            ag["arms"],
            "dataset gold (primary)",
            "adjudicated gold",
            ("bert_base_ta", "bert_mini", "anthropic_l", "gemma_m"),
            fmt_acc,
            fmt_acc,
        ),
        rank_shift(
            H,
            ag["arms"],
            "dataset gold",
            "adjudicated",
            ("bert_base_ta", "bert_mini", "anthropic_l"),
            fmt_acc,
            fmt_acc,
            compact=True,
        ),
    )
    fts = [agr[a] for a in g["fts"]]
    db_fy = next(a for a in db["arms"] if a["arm"] == "bert_base_fy")
    facts = [
        (
            "Re-measured",
            (
                "3 experiments: summarisation by LLM judges; AG News and DBpedia "
                "against labels a person corrected"
            ),
        ),
        ("Re-run", "nothing: every model output is the one committed when it was measured"),
        (
            "Cost",
            f"{H.money(fig['billed_usd'])} for the first judges, {H.money(f['remeasure']['summ_v2']['billed_usd'])} for the frontier judges, {fig['calls']} calls each; {H.money(f['remeasure']['validation_usd'])} checking all four against published human ratings; $0 for the labels",
        ),
        ("Primary metric", "unchanged in all three, by decision (below)"),
    ]
    facts_html = "".join(
        f'<div class="fact"><div class="k">{e(k)}</div><div class="v">{e(v)}</div></div>' for k, v in facts
    )
    sfg = sm["self_family_gap"]
    checklist = [
        (
            "Validate it against people, on outputs like yours.",
            (
                "The gate refuses a judge with no committed validation run, and one below the scorer's floor if "
                "the scorer sets one (set it to the best free scorer's score on the same human ratings). What it "
                "cannot check is whether those ratings look like your outputs. Here the first validation was on "
                "2019 summaries; a second, on crowd ratings of LLM-era summaries (§05), agrees with it, and "
                "neither is this experiment's own outputs."
            ),
        ),
        (
            "Use two judges from different vendors, blind.",
            "Each judge is reported, and how far they agree. Arm names are hidden and the order is shuffled "
            "per article, so a preference for a name is impossible and a preference for a slot is spread "
            "across the arms instead of following one. Arms from a judge's own vendor family are flagged: "
            + "; ".join(f"{j} rated them {v:+.2f} against the others" for j, v in sfg.items())
            + ", a raw gap, not a bias estimate, since families differ in real quality.",
        ),
        (
            "Measure the judge's own noise and position bias.",
            (
                f"A second shuffle and a repeat on a subset. Here the reshuffle moved per-article scores by "
                f"{pos_lo:.2f}–{pos_hi:.2f} and a repeat by {noi_lo:.2f}–{noi_hi:.2f}. Those are per-article "
                "numbers; whether a gap between two arms' means is real is what the paired tests answer, run on "
                "the judged scores like any other."
            ),
        ),
        (
            "Keep every verdict.",
            (
                "Each reply is stored with its scores, so the pass resumes, costs $0 to re-read, and anyone can "
                "check what the judge said. A reply that is not bare JSON scores, which can carry the source's "
                "text, is kept only as its hash."
            ),
        ),
        (
            "Read some yourself before you trust the ranking.",
            (
                f"Agreement between two judges is not agreement with people. Reading {hc['pairs']} pairs is what produced the "
                "disagreement here; the primary metric changes only after a check like that agrees, and a check "
                "worth that weight needs more than one reader."
            ),
        ),
    ]
    check_html = "".join(f"<li><div><h3>{e(h)}</h3><p>{e(p)}</p></div></li>" for h, p in checklist)
    frontier_html = frontier_section(H, f, sm)
    body = f"""
<section class="hero"><div class="wrap">
  <div class="kicker"><b>Judging</b> · re-measured, not re-run</div>
  <h1>Change the ruler, <em>not the run.</em></h1>
  <p class="dek">Every model output in these experiments is frozen, so when a better way to score them arrives the experiment can be measured again for the price of the scoring alone. We did it twice: a person corrected disputed labels, and SummEval-validated LLM judges re-scored the summaries. Both moved a headline result. Then one reader's blind check went the other way from the judges, and judges at {H.times(f["remeasure"]["summ_v2"]["billed_usd"] / fig["billed_usd"])} the price agreed with the first ones, not with the reader. On SummEval's expert ratings and on crowd ratings of 2022 LLM summaries, judges agree with people far better than the metric this leaderboard used, though not system by system; on this experiment's own outputs, nobody has yet shown which of the two to believe. That is the lesson: a judge is worth having, and worth checking.</p>
  <div class="facts">{facts_html}</div>
  <div class="btns"><a class="btn primary" href="#value">Why judge</a><a class="btn" href="#checklist">Judging, done right</a><a class="btn" href="../docs/GUIDE/#10-optional-re-measure-with-an-llm-judge">Try it, offline</a></div>
</div></section>

<section class="block" id="value"><div class="wrap">
  <div class="eyebrow"><span class="num">01</span>Why judge at all</div>
  <h2>The metric was the weak link.</h2>
  <div class="prose">
    <p>The summarisation experiment ranks by <strong>coverage</strong>, an overlap score against reference summaries. SummEval measures how well a scorer agrees with expert annotators, as Kendall τ: 1 when the scorer orders an article's summaries as the experts do, 0 when unrelated. Coverage agrees with them at τ {se["coverage"]:.2f}. The two LLM judges used below agree at τ {se["gemma_l"]:.2f} and {se["qwen_s"]:.2f}, against {se["coverage"]:.2f} for the metric the leaderboard was sorted by.</p>
    <p>{qv("The best judges agree with the experts about 93% as well as an expert does", JUDGE)}, {q("the best of 24 chosen on the same articles, and 92% held out.", JUDGE)} That is the case for judging: when the cheap metric barely tracks what people think, a validated judge is the better instrument on that data, and it can re-score outputs you already have. Two caveats from the same report: the judges rank all 16 summaries of an article in one call, which this measure rewards, and a {qv("no-model lookup of which system wrote each summary already reaches 63% of an expert", JUDGE)}, so part of a judge's score may be recognising which system wrote a summary; how much is not measured.</p>
  </div>
  <figure class="chart" style="margin-top:32px;max-width:900px">{H.both(tau_bars(H, bars), tau_bars(H, bars, compact=True))}<figcaption>Mean Kendall τ against SummEval's expert annotators, 100 articles × 16 summaries. 0 is no agreement. Coloured by kind, as elsewhere on this site.</figcaption></figure>
</div></section>

<section class="block" id="judged"><div class="wrap">
  <div class="eyebrow"><span class="num">02</span>A judge re-measures summarisation</div>
  <h2>First on coverage. {H.ordinal(bart["r2"]).capitalize()} on the judges.</h2>
  <div class="prose">
    <p>The two judges read every article with all {sm["n_arms"]} arms' summaries, names hidden and order shuffled: {fig["calls"]} calls, {H.money(fig["billed_usd"])}, {sm["items_scored"]} of {fig["items_total"]} articles scored. On their score <strong>every hosted LLM ranks above every BART model</strong>. <code>bart_l</code>, first on coverage, scores {bart["v2"]:.2f} of 5 and ranks {H.ordinal(bart["r2"])} of {sm["n_arms"]}, {qv("separated below all 24 hosted LLMs", SUMM)}. The hosted LLMs score {lo:.2f}–{hi:.2f}, bunched near the top of a 5-point scale, so the order among them, <code>{ldr["arm"]}</code> first ({H.ordinal(ldr["r1"])} on coverage), is not a finding.</p>
    <p>The judges agree closely with each other: Spearman {fig["agreement_arm_mean_spearman"]:.2f} over arm means. Re-ordering the summaries moved per-article scores by {pos_lo:.2f}–{pos_hi:.2f}, a repeat call by {noi_lo:.2f}–{noi_hi:.2f}. {sm["unparsed"]} of {sm["calls"]} replies did not parse; an article counts only when every block of every judge parsed, and {sm["items_scored"]} of {sm["items_total"]} did.</p>
  </div>
  <figure class="chart" style="margin-top:32px">{legend_html(H)}{sm_chart}<figcaption>Each line is one arm: its rank on coverage (left) and on the judges' mean score (right). Tap a dot for both scores.</figcaption></figure>
</div></section>

<section class="block" id="person"><div class="wrap">
  <div class="eyebrow"><span class="num">03</span>Then a person read them</div>
  <h2>{hc["human_prefers_bart_l"]} to {hc["human_prefers_deepseek_m"]} the other way.</h2>
  <ol class="findings">
    <li><div><h3>The one blind human check went the other way.</h3><p>One reader, the author and not an expert, compared {hc["pairs"]} pairs of <code>bart_l</code> and <code>deepseek_m</code> summaries blind and preferred <code>bart_l</code> {hc["human_prefers_bart_l"]} to {hc["human_prefers_deepseek_m"]} ({qv("sign test p = 0.115", SUMM)}: a split at least this lopsided would turn up that often from coin flips, so not significant). The judges preferred <code>deepseek_m</code> on all {hc["judge_prefers_deepseek_m"]}. Scored one summary at a time instead of in lists (unvalidated), they still rated <code>deepseek_m</code> higher on {fig["pointwise"]["deepseek_m_above_bart_l"]} of {fig["pointwise"]["articles"]} articles and never lower. Two limits on the check itself: the reader saw only the {qv("first 170-220 words", "examples/summarization-cnn-dailymail/human_check_judge.json")} of each article, which can favour a summary that stays close to the lead; and the judged leader, <code>{ldr["arm"]}</code>, was not in it.</p></div></li>
    <li><div><h3>A published check, on three 2022 systems.</h3><p>{qv("On three other systems, the GPT-3, BART-based BRIO and T0 summaries of Goyal, Li & Durrett (2022, CC BY 4.0; 100 CNN articles, three annotators each), the judges agree with people about as well as people agree with each other: picking the best of the three, against one annotator they score 0.498 (gemma_l) and 0.526 (qwen_s), annotators against each other 0.454, chance 0.333. On the same articles they prefer the GPT-3 summary to BRIO's more often than the annotators do (72.7% and 77.0% against 63.6% and 63.2%; each rate's 95% interval is computed on its own, not as a paired test, and the intervals overlap for both judges).", SUMM)} So they lean towards the LLM summary, within noise, in one comparison. The reader above was asked a different question, which summary is better overall; the judges score four dimensions.</p></div></li>
    <li><div><h3>So neither instrument is confirmed, and coverage stays primary.</h3><p>The judges' ranking is directional at most. The one check against it is one reader on truncated articles, also not conclusive. Possible reasons the two differ, none tested here: the judges were validated on 2019 summaries and checked on 2022 ones (§05), never on these arms; the truncated articles can favour a summary that copies the lead; one reader is a small sample. Two judges agreeing with each other is not two judges agreeing with people.</p></div></li>
  </ol>
</div></section>

{frontier_html}
{zhang_section(H, f)}
<section class="block" id="labels"><div class="wrap">
  <div class="eyebrow"><span class="num">06</span>A person re-measures the labels</div>
  <h2>How much of the fine-tunes' lead was {ag["changed"]} labels?</h2>
  <div class="prose">
    <p>On AG News three small fine-tunes led every hosted LLM, concentrated in {ag["changed"]} items that at least 80% of the hosted field got wrong. One reader, the author, adjudicated by topic those items and every item a fine-tune missed, {ag["n_items"]} in all, shown each item's text, its gold label and the hosted majority's answer. The reader judged the gold wrong on all {ag["changed"]}, and right on every item the fine-tunes missed. The reader's reason: the labels follow the source feed's section, so company news from a technology desk is Sci/Tech and non-US news, sport included, is World.</p>
    <p>Re-scored against those labels for $0, every hosted LLM has a higher accuracy than every fine-tune. The fine-tunes fall from {", ".join(str(a["r1"]) for a in fts)} to {"–".join(str(x) for x in (min(a["r2"] for a in fts), max(a["r2"] for a in fts)))} of {ag["n_arms"]}, and <code>{g["ag_leader"]["arm"]}</code> rises from {H.ordinal(g["ag_leader"]["r1"])} to first at {g["ag_leader"]["v2"]:.4f}, {qv("separated from 9, including all three fine-tunes", CLASS)} (which tie at {fts[0]["v2"]:.4f}), and {qv("not separated from 20 hosted arms", CLASS)}: most of the new order is not separated. On DBpedia {db["changed"]} labels were judged wrong; {qv("the top stays a crowd: gemma_m and qwen_m lead at 0.9964, gemma_m is separated from only 5 of 27", CLASS)}, and <code>bert_base_fy</code> moves from {H.ordinal(db_fy["r1"])} to {H.ordinal(db_fy["r2"])} at an unchanged {db_fy["v1"]:.4f}.</p>
    <p>The instrument here was a person, with two limits. The reader saw the hosted answer, and every item the hosted field missed was resolved the hosted field's way, which is also what anchoring on that answer would produce. And only items some arm disagreed on were read, so an error the gold and every arm share would not be seen. What it shows for certain is how much the ranking depends on those labels: a fine-tune trained on a dataset learns its conventions. If your labels follow a house convention, that is what you want. If they mean what the words say, it is not.</p>
  </div>
  <figure class="chart" style="margin-top:32px">{legend_html(H)}{ag_chart}<figcaption>AG News, {ag["n_arms"]} arms: rank on the dataset's gold (left) and on the adjudicated gold (right).</figcaption></figure>
</div></section>

<section class="block" id="decided"><div class="wrap">
  <div class="eyebrow"><span class="num">07</span>What we did with it</div>
  <h2>Both stay beside the primary. Neither replaces it.</h2>
  <div class="cols"><div class="prose">
    <p>A re-measurement is written beside the original, never over it, and an experiment's primary metric changes only by a recorded decision with the old one kept. Both decisions here kept the original:</p>
    <p><strong>AG News and DBpedia</strong> keep the dataset's gold: anyone can repeat it, and the adjudication is one reader's, made while seeing the hosted answer. <strong>Summarisation</strong> keeps coverage: the judges' ranking has not been confirmed by people on these summaries, and the one check that exists went the other way.</p>
    <p>It matters, in both directions. On the primary metrics a free model is first, or not separable from first, in {g["headline_now"]} of the {g["n_exp"]} experiments, and the dearest model is first in none. Taken at face value, the two re-measurements would make that {g["headline_remeasured"]} of {g["n_exp"]}, and put the dearest model, <code>{g["dearest"]}</code>, first in {g["dearest_first_remeasured"]} of {g["n_exp"]}: in AG News and summarisation it is first on the point estimate of both re-measured rankings, though unseparated from most of the field in AG News; DBpedia's top stays a crowd. One of them rests on one reader who saw the hosted answer, the other on a ranking one reader's check went against. That is how much a measurement decision can move a headline, and why the decision is recorded rather than made by whichever number came last.</p>
  </div>
  <div class="note"><b>What would settle it.</b> Not a larger, dearer judge: that was tried (§04). Judges checked on human ratings of LLM-written summaries: that was done too (§05); they track people better than one rater does on coherence and relevance, trail on faithfulness, and deviate from them system by system in both directions. What is left is people on this experiment's own outputs: several readers comparing full articles, not one reader on truncated ones. That is a re-measurement of the same frozen outputs.</div></div>
</div></section>

<section class="block" id="checklist"><div class="wrap">
  <div class="eyebrow"><span class="num">08</span>Judging, done right</div>
  <h2>Five rules the harness enforces, or asks you to.</h2>
  <ol class="findings">{check_html}</ol>
</div></section>

<section class="block" id="yours"><div class="wrap">
  <div class="eyebrow"><span class="num">09</span>On your outputs</div>
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
    return H.page(
        "Change the ruler, not the run — judging · eval-harness",
        "What re-measuring frozen experiments with SummEval-validated LLM judges and corrected labels "
        "changed, why a judge beat the metric on SummEval, and why one reader's check kept coverage primary.",
        body,
        depth=1,
        here="judging",
    )


def frontier_section(H, f: dict, v1: dict) -> str:
    """Do larger, dearer judges side with the reader? judge-summ-v2 (the two highest-scoring
    SummEval judges from vendors not in judge-summ-v1) on the same judging set."""
    v2 = f["remeasure"]["summ_v2"]
    by = {x["slug"]: x for x in f["experiments"]}
    se_tau = {a["arm"]: a["score"] for a in by["summeval"]["arms"]}
    r1 = {a["arm"]: a for a in v1["arms"]}
    r2 = {a["arm"]: a for a in v2["arms"]}
    hosted = [a for a in v2["arms"] if a["kind"] == "hosted"]
    barts = [a for a in v2["arms"] if a["arm"].startswith("bart")]
    H.require(
        min(a["v2"] for a in hosted) > max(a["v2"] for a in barts),
        "frontier judges: every hosted arm above every BART model",
    )
    H.require(v2["items_scored"] == v2["items_total"], "frontier judges scored every article")
    H.require(
        v2["prefers_deepseek_m"] == v2["human_pairs"], "frontier judges prefer deepseek_m on every pair"
    )
    # Spearman between the two scorers' arm means.
    arms = sorted(r1)
    n = len(arms)
    d2 = sum((r1[a]["r2"] - r2[a]["r2"]) ** 2 for a in arms)
    rho = 1 - 6 * d2 / (n * (n * n - 1))
    rows = [
        {
            "arm": a,
            "kind": r1[a]["kind"],
            "weights": r1[a]["weights"],
            "v1": r1[a]["v2"],
            "v2": r2[a]["v2"],
            "r1": r1[a]["r2"],
            "r2": r2[a]["r2"],
        }
        for a in arms
    ]
    fmt = lambda v: f"judge score {v:.2f} of 5"  # noqa: E731
    chart = H.both(
        rank_shift(
            H,
            rows,
            "judge-summ-v1 (gemma_l, qwen_s)",
            "judge-summ-v2 (openai_l, anthropic_l)",
            ("bart_l", "deepseek_m", "anthropic_l", "mistral_l"),
            fmt,
            fmt,
        ),
        rank_shift(
            H,
            rows,
            "v1 judges",
            "frontier judges",
            ("bart_l", "deepseek_m", "anthropic_l"),
            fmt,
            fmt,
            compact=True,
        ),
    )
    j1, j2 = v2["judges"]
    gap = v2["self_family_gap"]
    ratio = v2["billed_usd"] / v1["billed_usd"]
    bart = r2["bart_l"]
    ldr = max(v2["arms"], key=lambda a: a["v2"])
    goyal = goyal_v2(H)
    v1j = v1["judges"]
    H.require(
        min(se_tau[j1], se_tau[j2]) < max(se_tau[j] for j in v1j) < max(se_tau[j1], se_tau[j2]),
        "frontier judges: a first-pair judge scores between them on SummEval",
    )
    return f"""<section class="block" id="frontier"><div class="wrap">
  <div class="eyebrow"><span class="num">04</span>Frontier judges</div>
  <h2>Same validation score, {H.times(ratio)} the price, the same verdict.</h2>
  <div class="prose">
    <p>Were the first judges simply too small? The two highest-scoring SummEval judges from vendors not in the first pair, <code>{j1}</code> (τ {se_tau[j1]:.2f}) and <code>{j2}</code> ({se_tau[j2]:.2f}; the first pair's <code>{max(v1j, key=lambda j: se_tau[j])}</code> scored {max(se_tau[j] for j in v1j):.2f}), validated by their committed SummEval runs, judged the same judging set with the same prompt, reasoning off: {v2["calls"]} calls, {H.money(v2["billed_usd"])}, {v2["items_scored"]} of {v2["items_total"]} articles, {"no reply unparsed" if not v2["unparsed"] else f"{v2['unparsed']} replies unparsed"}. They are larger and dearer judges, not clearly better ones.</p>
    <p>They reach the same verdict. Every hosted LLM again ranks above every BART model; <code>bart_l</code> scores {bart["v2"]:.2f} of 5 and ranks {H.ordinal(bart["r2"])} of {v2["n_arms"]}, {H.qv("separated below all 24 hosted LLMs", SUMM)} on their score too. The two scorers order the arms alike (Spearman {rho:.2f} over arm means), and on the {v2["human_pairs"]} human-check pairs the frontier judges also prefer <code>deepseek_m</code>, {v2["prefers_deepseek_m"]} to {v2["prefers_bart_l"]}. {goyal}</p>
    <p>So the disagreement with the reader is not a small-judge problem: judges of very different size and price agree with each other, and not with the one reader. Either LLM judges share a preference that reader does not, or the reader's check is too small to tell; §05 tests the first. One thing grows with the frontier judges: own-family scores. <code>{j1}</code> rated its own vendor's arms {gap[j1]:+.2f} above the others and <code>{j2}</code> {gap[j2]:+.2f}, against {"/".join(f"{v:+.2f}" for v in v1["self_family_gap"].values())} for the first pair: raw gaps, not bias estimates, but the judged leader, <code>{ldr["arm"]}</code>, is one judge's own family. Paying {H.times(ratio)} as much did not settle it; only people can.</p>
  </div>
  <figure class="chart" style="margin-top:32px">{legend_html(H)}{chart}<figcaption>Each line is one arm: its rank on the first judges' score (left) and on the frontier judges' (right).</figcaption></figure>
</div></section>"""


def zhang_section(H, f: dict) -> str:
    """All four judges against Zhang et al.'s crowd ratings of LLM-era summaries."""
    z = f["remeasure"]["zhang"]
    v1, v2 = z["judge-summ-v1"], z["judge-summ-v2"]
    judges = {**v1["judges"], **v2["judges"]}
    paired = {**v1["paired_non_reference_18"], **v2["paired_non_reference_18"]}
    rank = {j: s["system_means"]["ranking"] for s in (v1, v2) for j in s["judges"]}
    hum = v1["human_baseline"]["non_reference_18"]
    fm = v1["free_metrics_non_reference_18"]
    raters = next(iter(rank.values()))["raters"]
    brio_j = sorted(rank[j]["judges"][j]["brio"] for j in rank)
    sp = [rank[j]["spearman_vs_raters"][j] for j in rank]
    ahead_r = [p["vs_one_rater"]["a_ahead"] for p in paired.values()]
    ahead_c = [p["vs_coverage"]["a_ahead"] for p in paired.values()]
    faith = [r["non_reference_18"]["faithfulness"] for r in judges.values()]
    H.require(
        all(r["non_reference_18"]["mean"] > hum["mean"] > fm["coverage"]["mean"] for r in judges.values()),
        "Zhang: every judge above one rater, one rater above coverage",
    )
    H.require(
        all(p[k]["p_two_sided"] < 0.001 for p in paired.values() for k in ("vs_one_rater", "vs_coverage")),
        "Zhang: every paired comparison p < 0.001",
    )
    H.require(max(brio_j) < raters["brio"], "Zhang: the judges rank BRIO higher than the raters do")
    ref_j = sorted(rank[j]["judges"][j]["reference"] for j in rank)
    H.require(
        max(ref_j) < raters["reference"],
        "Zhang: the judges rank the reference highlights higher than the raters do",
    )
    by = {x["slug"]: x for x in f["experiments"]}
    k = {a["arm"]: H.kind_of(a) for a in by["summeval"]["arms"]}
    bars = [
        ("coverage", "vs the reference highlights", fm["coverage"]["mean"], "baseline"),
        ("ROUGE-1", "vs the reference highlights", fm["rouge1"]["mean"], "baseline"),
        ("one rater", "vs the other two", hum["mean"], "baseline"),
    ]
    bars += [
        (j, "LLM judge", judges[j]["non_reference_18"]["mean"], k.get(j, "open"))
        for j in ("qwen_s", "gemma_l", "openai_l", "anthropic_l")
    ]
    cost1 = sum(r["billed_usd"] for r in v1["judges"].values())
    cost2 = sum(r["billed_usd"] for r in v2["judges"].values())
    return f"""<section class="block" id="zhang"><div class="wrap">
  <div class="eyebrow"><span class="num">05</span>People, on LLM summaries</div>
  <h2>Checked against people, on LLM-era summaries.</h2>
  <div class="prose">
    <p>SummEval's summaries are from 2019. <a href="https://aclanthology.org/2024.tacl-1.3/">Zhang et al. (2024)</a> released crowd ratings of {v1["systems"]} summarisers on {v1["articles"]} CNN/DailyMail articles: GPT-3-era LLMs, base and instruction-tuned; the fine-tunes BRIO and Pegasus; and the reference highlights, three ratings each. All four judges scored them. Each is measured against the mean of two ratings with the third held out, and so is one rater against the other two; the ratings themselves are not stored here, only the judges' scores. Agreement is Kendall τ per article: 1 when an instrument orders the summaries as the raters do, 0 when it is unrelated, −1 when reversed.</p>
    <p>Every judge agrees with the raters' consensus better than one rater does, ahead on {min(ahead_r)}–{max(ahead_r)} of the articles, and better than <code>coverage</code>, ahead on {min(ahead_c)}–{max(ahead_c)}; every comparison p &lt; 0.001. The cheap pair does as well as the frontier pair, for ${cost1:.2f} against ${cost2:.2f}. On faithfulness alone they trail one rater ({min(faith):.2f}–{max(faith):.2f} against {hum["faithfulness"]:.2f}).</p>
    <p>And on the question this page keeps returning to: ranking the systems by mean coherence and relevance, the raters put BRIO, a BART-based fine-tune, {H.ordinal(raters["brio"])} of {v1["systems"]}, after four instruction-tuned LLMs; the judges rank it {H.ordinal(brio_j[0])} or {H.ordinal(brio_j[-1])} (Spearman {min(sp):.2f}–{max(sp):.2f} between the judges' and the raters' rankings of the systems; 1 is the same order). So these judges show no blanket preference for LLM-written summaries over a BART-style one. They deviate from the raters system by system in both directions: the raters rank the reference highlights {H.ordinal(raters["reference"])}, the judges {H.ordinal(ref_j[0])} to {H.ordinal(ref_j[-1])}.</p>
    <p>The limits. One crowd rating is a noisy baseline, and these τ are against crowd raters on another set, so they do not compare with SummEval's experts. The {v1["systems"]} systems span a wide range of quality, which makes a high Spearman easier. The articles and ratings have been public since 2023, so a judge may have seen them. And these are 2022's systems, not this experiment's arms: this is evidence about the judges, not a check of the ranking in §02.</p>
  </div>
  <figure class="chart" style="margin-top:32px;max-width:900px">{H.both(tau_bars(H, bars), tau_bars(H, bars, compact=True))}<figcaption>Mean Kendall τ per article against the mean of two crowd ratings, over coherence, relevance and faithfulness, on the {v1["systems"] - 1} non-reference summaries.</figcaption></figure>
</div></section>"""


def goyal_v2(H) -> str:
    """The Goyal comparison for the frontier judges, as REPORT_SUMMARIZATION §3.8 states it."""
    return H.qv(
        "On the Goyal et al. systems they score 0.466 (openai_l) and 0.488 (anthropic_l) against "
        "one annotator, annotators against each other 0.454; on the articles both decided, openai_l "
        "prefers the GPT-3 summary on 70.4% against the annotators' 61.7%, and anthropic_l on 64.2% "
        "against 64.2%.",
        SUMM,
    )


def legend_html(H) -> str:
    return H.legend(band=False, baseline=True)
