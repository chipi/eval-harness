# RFC-034: Charts that show the evidence, and judges that say why

- **Status**: Accepted (0.8.0), building. Owner, 2026-11-18, after comparing the harness with EvalBench (Google
  Cloud, shown at AGNTCon + MCPCon North America 2026): "do 1 and 2 now for 0.8", then "did we look enough into how
  much more we can visualize?", choosing every chart in §2.
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-032](RFC-032-one-model-two-surfaces.md) (one model; the command line and the API as its
  surfaces), [RFC-029](RFC-029-studies-and-test-set-looks.md) (studies), [RFC-027](RFC-027-who-acted-and-baselines-per-goal.md)
  (baselines and rounds), [RFC-030](RFC-030-replay-and-faithfulness.md) (periods and faithfulness),
  [ADR-0001](../adr/ADR-0001-judge-scorers.md) (the validated judge), [ADR-0026](../adr/ADR-0026-contenders-by-non-inferiority.md)
  (contenders), [RFC-035](RFC-035-agent-journeys.md) (agent journeys, 0.9.0)

## Abstract

The harness computes more than it draws. The catalog draws five kinds of chart (runs per day, spend over time, words
per item, quality against cost or speed with the frontier, a metric per arm as a strip). The Workbench draws none.
Confidence intervals, rank stability, label agreement matrices, latency per item and study trials are computed and
stored, and shown only as numbers or not at all. A judge's verdict is a number with no reason.

This RFC adds one chart operation (`evh chart`, `GET /api/v1/charts/{kind}`) that every surface draws from, nine
charts, and a reason inside every judge verdict.

## Decisions (owner, 2026-11-18)

1. **The reason is inside the verdict**, in the same call: the judge replies with its scores and a short `why`.
   Not a second call. A judge whose prompt asks for a reason is a different judge (its message changes), so it is
   validated as such.
2. **Every verdict carries its reason** (the reason costs output tokens, not calls; measured on the first smoke
   before any paid run).
3. **The gain-against-cost chart** goes on studies and rounds, with the significance rules of §3.
4. **Also in 0.8.0**: the difference with its interval, study progress, rank stability, latency spread, judge
   against people, the per-item heat map, the charts in the Workbench, and trends over time.

## 1. One chart operation

A chart is a read operation (RFC-032), so it has every surface at once:

```
evh chart KIND [--goal G] [--round R] [--study S] [--dataset D] [--scorer S] [--json] [--svg FILE]
GET /api/v1/charts/{kind}?goal=…&round=…
```

- **Values**: `{kind, title, caption, data, svg}`. `data` is what is drawn (points, rows, cells), each with the
  numbers a reader needs to check it; `svg` is the drawing.
- **Command line**: prints `data` as a table and the caption; `--svg FILE` writes the drawing; `--json` gives the
  values. Nothing is only in the picture.
- **Catalog**: the page calls the same function at build time and embeds the SVG, with the table under a
  `<details>`.
- **Workbench**: the screen asks the API and inserts the SVG. The drawing is made by `catalog_charts.py` from
  escaped text only, served same-origin under the Workbench's CSP.
- **A chart with too little to draw refuses** with the reason (`not-enough`), as `rank-stability` does now, and the
  surface shows that sentence instead of an empty frame.

Every drawing follows the existing rules of `catalog_charts.py`: one scale per axis, labels from the theme's
tokens, readable at 390 px (the Workbench's phone width), and no colour that carries meaning alone (a filled or
hollow mark, a line style or a word carries it too).

## 2. The charts

| kind | what it shows | from | where |
| --- | --- | --- | --- |
| `gain-cost` | each arm's or trial's difference in quality against its difference in cost per item, from the baseline | a round's evidence; a study's trials | round, study (catalog, Workbench) |
| `intervals` | each arm's difference from the leader, with its confidence interval, the non-inferiority margin and the verdict | the goal leaderboard's groups | goal, round |
| `study-progress` | a study's trials in order: kept, dropped or no effect, with the best-so-far line and the test-set confirmation | the study's log | study |
| `rank-stability` | how often two disjoint halves agree on the order, as items grow | `rank-stability` | dataset, goal |
| `latency` | per-item latency per arm, with p50 and p95 marked; cost per item beside it | the runs' rows | goal, round |
| `agreement` | the confusion matrix of two label sets, or of a judge and people; the judge's position-bias agreement | `label-set` comparison; a judging summary's controls | dataset, scorer |
| `items` | arms by items, coloured by score, items ordered by how much the arms disagree; each cell links to the item | the comparison's rows | round, goal |
| `trend` | the goal's baseline across its versions and the promoted run of each closed round; production's agreement per deployed period | baselines' history, closed rounds, periods and faithfulness records | goal, production |

`gain-cost` is the picture EvalBench draws for a skill's ablation ("free win", "worth paying for", "token tax"). A
study's trial is one change against the baseline by construction, so a study is an ablation; a round's arm against
the round's baseline (or the leader when there is none) is the same question asked of a whole arm.

## 3. What the gain-against-cost chart may claim

The quadrant names are claims, so they follow the tests the harness already makes:

- **x**: the difference in mean cost per item from the baseline, in dollars (tokens when no arm has a cost). Lower
  is left.
- **y**: the difference in the goal's measure from the baseline, oriented so up is better (a `lower` measure is
  flipped and the axis says so), with its confidence interval as a whisker.
- **A filled mark** only when the difference is significant at the level the round or study uses (its p and Holm
  adjustment where the round applies one). Otherwise the mark is hollow and the point is **not separated**: it sits
  in a quadrant by its estimate, but the quadrant's name is not claimed for it.
- **Names**: "better and cheaper", "better, costs more", "worse and cheaper", "worse, costs more", plus "no gain
  shown, costs more" for a hollow mark to the right of zero (EvalBench's token tax, without claiming the gain is
  zero).
- A study's trial that its rule dropped for a limit (RFC-029: a guard metric fell beyond its limit) is drawn with
  that reason in its tooltip and table row.

## 4. The difference with its interval

`vs_leader` holds the difference, its p and its verdict; the interval is computed by `stats` (`exact_ci` for paired
item deltas, `cluster_ci` where items are clustered) and not passed on. The goal leaderboard's `vs_leader` gains
`ci: [low, high]` at the same level as its test, so the number and the drawing agree. The chart draws zero, the
margin when the goal decides by non-inferiority (ADR-0026), and each arm's interval, with its verdict as a word.

## 5. Judges that say why

**The reply.** The harness appends one reminder to the judge's message when the scorer explains (the prompt file is
unchanged):

- `grade`: `"why": ["…", "…"]`, one sentence per numbered output, in order, beside the score lists.
- `pick` and `pairwise`: `"why": "…"`, one or two sentences.

The reminder asks for the reason **after** the scores in the same JSON object and for no quotation of the source
or the outputs beyond a few words.

**Parsing.** `parse_reply` returns the verdict as before, plus `why` when it is present and well formed (a string,
or one string per output for `grade`). A reply whose scores parse and whose `why` does not keeps its scores; the
verdict records `why_missing: true`. A reason never decides whether the scores parsed.

**Storing.** The verdict file gains `why`. The rule that keeps a source's text out of git (V12: a committed reply is
bare JSON and repeats no eight consecutive words of the item or the outputs) applies to the reply as now and to
`why` on its own: a `why` that repeats the source is not committed (`why_withheld: "repeats the source"`, kept in
the git-ignored local copy as an unparsed reply is now), and the scores still are.

**The scorer.** A new field `explain: true | false`, default `true` for a new scorer (`scorer-new`). Every committed
scorer (`harness/data/scorers/*.yaml`, `harness/tutorial/scorers/*.yaml`) was validated and judged without reasons,
so the migration writes `explain: false` into each: their messages stay byte-identical and their validations still
hold. A scorer that wants reasons is a new scorer version (`supersedes`), as any change to a judging scorer is.

**Validation.** `validation_problems` also compares `explain` between the scorer and its validation runs (a run
measured with `explain: false` does not validate a scorer with `explain: true`). The judge's fingerprint includes
`explain`.

**Where the reason is read.**

- The command line: `evh judge-verdicts --scorer S [--item I] [--arm A]` lists verdicts with their reasons (the
  scores per dimension, the reason, the judge, the pass).
- The Workbench's judge screen: each judged item shows its verdicts and their reasons.
- The catalog's item page (the local inspector, not the public catalog, which shows no item text): the verdicts of
  that item beside the outputs they judge.
- The judging summary: the lowest-scored verdicts with their reasons, as the "what failed and why" the talk asked
  for.

**Cost.** The reason adds output tokens to each call. The judge's dry run (`judge-score --dry-run`) counts them in
its projection (an estimate per output, replaced by the measured mean once verdicts exist), and the arm-smoke rule
applies: a three-item judging smoke and its replies are read before a paid pass.

## 6. What changes for a project

- Judge scorers gain `explain`; the migration writes `explain: false` into existing ones (no reasons, nothing else
  changes). New scorers explain by default.
- `evh chart` and `evh judge-verdicts` are new reads. The goal leaderboard's `vs_leader` gains `ci`.
- Catalog pages gain charts; nothing is removed.

## 7. Tests

- Each chart kind: its data on a project made by the test (echo arms, a study, label sets, a judging set on
  `provider: fake`), the SVG well formed and free of unescaped text, the refusal when there is too little, and the
  command line's table equal to the API's `data`.
- `gain-cost`: a significant and a non-significant arm on the same side of zero draw filled and hollow; the names
  follow §3; a `lower` measure is flipped. Mutation: dropping the significance check must fail a test.
- Judge reasons: the fake provider returns a `why`; parsing with and without it, a `why` that quotes the source
  withheld while the scores stay, `explain: false` sends a byte-identical message to today's (checked against the
  committed message hash), validation refusing a mismatch of `explain`.
- Browser: the Workbench's round, study and judge screens show their charts and reasons at 1280 and 390 px.

## Alternatives set aside

- **A second call for the reason.** It keeps validated messages unchanged, but the reason would explain a verdict it
  did not produce, and it is a call per verdict. Set aside by the owner (decision 1).
- **Drawing in the browser** (a chart library in the Workbench). Two implementations of every chart, a new
  dependency, and the command line would have none. One Python drawing, served everywhere, is kept.
- **Quadrant names without significance.** What EvalBench's slide shows; it would call a lucky estimate a "free
  win". §3 keeps the names for what the tests support.
