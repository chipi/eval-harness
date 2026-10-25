# UXS-001: The catalog

- **Status**: Active
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-004](../prd/PRD-004-catalog-and-inspector.md) (catalog and inspector),
  [PRD-005](../prd/PRD-005-goals-and-rounds.md) (goals and rounds), [PRD-006](../prd/PRD-006-datasets-versions-fields.md) (versions, fields),
  [PRD-002](../prd/PRD-002-references.md) (references)
- **Related RFCs**: [RFC-003](../rfc/RFC-003-catalog-adapter.md) (the adapter and the build), [RFC-004](../rfc/RFC-004-experiment-rounds.md) (rounds)
- **Related UX specs**: [UXS-002](UXS-002-inspector.md) (the inspector, linked from every page),
  [UXS-003](UXS-003-cli-and-onboarding.md) (the same views as commands)
- **Implementation paths**: `harness/scripts/catalog_build.py` (pages),
  `harness/catalog_assets/style.css` and `catalog.css` (tokens and components),
  `harness/catalog_assets/catalog.js` (theme, search, filter, sort, paging)

## Summary

`evh catalog` builds static pages over a project's runs into `.build/catalog/`: a home page with
the whole project at a glance, a datasets page and a page per dataset, a page per arm, a goals
page and a page per goal, a references page and a page per reference, a metrics page and a page
per metric, and the shell of the inspector. Every page is read-only and carries counts and means only,
so the pages can be published. This spec describes the pages as built at 0.4.0, checked by
building the catalog on this repository's data (6 goals, 9 datasets, 194 arms, 1 reference) and
on a tutorial project with gold, silver and an open round.

## Principles

- **Answer first.** A goal page and a dataset page open with what has been decided (the promoted
  baseline and its reason), then the evidence.
- **Say what a number is measured against**, on every row, and mark the rows that are not scored
  against gold.
- **Rank only like with like.** Arms are ranked within a group scored against the same thing;
  a mean is never presented as a verdict.
- **Read-only.** A decision is shown as the command that makes it.
- **Dense, quiet, both themes.** Tables carry the data; colour marks meaning, never decoration.

## Scope

**In scope:** the shared shell, home, dataset, goals, goal, reference and metrics pages, global
search, table filter, sort and paging, row tints.

**Non-goals:** the inspector's own page (UXS-002); report rendering (the catalog renders none);
any control that writes.

## Theme support

- **Mode:** both, following the system (`prefers-color-scheme`), with a manual toggle (◐ in the
  header) remembered in `localStorage` (`theme`). The theme is applied before first paint by
  `assets/head.js`, a file, so no inline script is needed.
- **Primary palette:** dark (`:root` is dark; light is the override).
- **Breakpoints:** the content column is at most 1180px wide with 24px gutters, 16px below
  640px; nav links marked `hide-sm` are hidden below 760px; tables scroll sideways inside
  `.scroll-x` rather than squeeze.

## Tokens

From `style.css`, with `catalog.css`'s accessibility overrides (muted text at 4.5:1 or more on
every surface).

| Token | Dark | Light | Usage |
| --- | --- | --- | --- |
| `--page` | `#0b0b0a` | `#f6f5f1` | page background |
| `--surface` | `#141413` | `#fcfcfb` | panels, the answer box, round details |
| `--surface-2` | `#1c1c1a` | `#efeee9` | code chips (suggested commands) |
| `--ink` / `--ink-2` | `#f0efec` / `#b9b7ad` | `#0b0b0b` / `#4a4945` | text / secondary text |
| `--muted` | `#8a8880` | `#66645e` | captions, notes |
| `--hair` | `#2a2a27` | `#dddbd3` | borders, dividers |
| `--accent` | `#c8ff3d` | `#3d5c00` | editorial highlight, links, focus ring, the open round; never data |
| `--baseline` | `#6f6d66` | `#85837b` | silver tint, the baseline in charts |
| `--proprietary` | `#3987e5` | `#2a78d6` | judged tint |
| `--local` | `#d95926` | `#eb6834` | author tint, "retired" label |
| `--open` | `#199e70` | `#1baf7a` | "separated: better" chip border |
| `--s1` … `--s8` | categorical | categorical | one colour per arm in the inspector's charts |

**Typography:** `--text` Inter (system fallbacks), `--display` Inter Tight for headings, `--mono`
ui-monospace for ids, numbers in tables, buttons and the eyebrows. Body 17px (16px on phones),
tables 15px.

**Focus:** `:focus-visible` draws a 2px `--accent` outline with a 2px offset.

## The shell (every page)

- **Header bar:** the brand ("eval catalog" and its icon, linking home); the global search
  ("Search everything ( / )"); the nav: **Home**, **Goals**, **Datasets**, **References**,
  **Metrics**, **Inspector**, plus any `--link LABEL=URL` entries; the theme toggle.
- **Page anatomy:** a slim hero (a kicker such as `dataset` or `goal`, the title, a one-paragraph
  dek), then numbered sections (`01`, `02`, ...) each with an eyebrow.
- **Footer:** "Built <date> by `evh catalog`. The pages carry counts and means only; item text
  is fetched from the inspector when you open an item." (`item` is the adapter's word, e.g.
  "episode".)
- **Search:** an index of every dataset, arm, reference, metric and goal. It opens from two
  characters, ranks title matches above description matches (goals first on ties), shows up to
  40 hits each with its kind, and follows the arrow keys; `/` focuses it and Escape closes it. An
  arm hit opens the inspector on that arm. Command: `evh search <text>` (the same index and
  ranking, each hit with the command that shows it).

## Tables

Every data table shares one behaviour:

- **Filter:** where a table has a filter box ("filter arms", "filter datasets", "filter
  metrics"), it keeps the rows containing every typed word and shows "N shown".
- **Sort:** clicking a header sorts by that column, ascending then descending; numbers sort as
  numbers.
- **Paging:** a table longer than 10 rows shows 10, with "Showing 10 of N", **show 10 more** (or
  fewer when fewer are left) and **show all**; when everything shows, **show 10** folds it again.
  Paging counts only the rows the filter leaves, so filter and sort work over every row. A link to
  a row (`#anchor`) opens the table with that row shown.
- **Not paged:** tables whose rows are read together. In the inspector these are the verdict
  table and the breakdown table, whose Holm thresholds depend on each other (UXS-002).

## Row tints

A row's tint says what its scores are measured against. A key above each arms table spells it
out: "scored against silver", "scored by a judge", "wrote the reference it is scored against",
"unmarked rows are scored against gold".

| class | when | look |
| --- | --- | --- |
| (none) | scored against gold | plain |
| `t-silver` | scored against a silver reference | `--baseline` at 12%, 3px `--baseline` bar on the first cell |
| `t-judged` | scored by a judge scorer (the "scored against" cell reads "judge `<scorer>`") | `--proprietary` at 10%, 3px bar |
| `t-author` | the arm wrote the reference it is scored against: graded against its own outputs | `--local` at 12%, 3px bar |

The author tint wins over the others. The same classes tint the inspector's verdict rows, and
`evh datasets --dataset-id` prints the same kind in a `row` column.

## The home page

The whole project at a glance, for the last 14 days of activity or for all time.

- Hero: kicker `catalog`, title "Every evaluation, at a glance", a dek saying every name is a
  link, then **tiles**, each linking to its page: goals, datasets, configs, arms, references,
  metrics, measured runs, billed (USD) and tokens. Under them the period switch, **last 14 days**
  (shown first) or **all time**, with the dates each spans. Recent counts back 14 days from the
  newest thing recorded, so a quiet project still shows its last burst of work.
- `01 goals at a glance`: one row per goal and dataset: **goal**, **dataset**, **decides** (the
  measure, ↓ when lower is better), **baseline** (the promoted arm and its mean, or "none
  promoted"), **leader** (the best unflagged arm scored against the gold group's reference, and
  its mean), **leader vs baseline** (the paired test of the two alone, threshold 0.05: verdict,
  Δ, p, and an **inspect** button; "the baseline leads" when they are the same arm),
  **recommended** (the arm the goal's strategy picks once limits and the tie-break are applied;
  shown with cost and speed ratios against the baseline, e.g. "cost 212× · speed p95 1× vs
  baseline"). A note says the goal page tests every arm, Holm across them.
- `02 activity and spend`, side by side (one above the other on a phone): **activity**, measured
  runs per day as bars stacked by dataset (repeats counted one by one); **spend**, cumulative,
  one line for the systems under test and one for the judges, with a **USD / tokens** switch.
  Tokens are tokens in plus out as each call reported them, so a local model's use counts when
  its adapter or server reports usage. The charts start at the first day anything was recorded.
- `03 coverage`: one row per dataset: **dataset**, **items**, **arms scored against** (gold,
  silver and judged counts), **references**, **metrics** (a count that opens to the list),
  **goals**, **last run**.
- `04 recorded`: everything recorded, newest first: **when**, **what** (ran or rescored or judged
  an arm on a dataset, one line per arm and day; a reference made, with its author; a baseline
  promoted; a round opened or closed; every name linked), **kind**. Paged.
- Command: `evh overview [--all]`.

## The datasets page

- Hero: kicker `datasets`, "Every run, by dataset", and "N arms on M datasets, from K configs. An
  arm is one config on one dataset scored one way, its repeats averaged per item, exactly as
  `pair-test` reads it: a config rescored against silver or by a judge is an arm of its own."
  `evh catalog` prints the same counts, and `evh datasets` has a `configs` column beside `arms`.
- `01 datasets`: one row per dataset, most arms first: **dataset** ("from `<parent>`" under a
  version), **items**, **arms**, **references**, **goals**, **baseline** (the promoted arm),
  **last run**. Filterable.
- Command: `evh datasets`.

## The dataset page

- Hero: kicker `dataset`, the `dataset_id`, and "N items · M arms. Headline: each arm's own
  primary metric, mean over its items; arms with different primary metrics are not ranked
  against each other."
- **The baseline**, when one is promoted: an answer box with "baseline, promoted <date>", the
  arm's name, and the reason given at promotion.
- **Inspect buttons:** one per group of two or more arms with the same headline metric scored
  against the same reference: "Inspect the N arms on <metric>, scored against <reference>". A
  group larger than 40 links its first 40 and says to add others in the inspector.
- `01 arms`: the row key, then one row per arm, sorted first by what it is scored against
  (gold, then silver, then each judge, then no reference), then by reference, then grouped by
  metric and best first, so a silver mean and a gold mean never interleave:
  **arm** (with a `baseline` tag on the promoted one, and "on <machine>" when the arms ran on more
  than one machine), **metric** (linked to the metrics page), **mean** (↓ after it when lower is
  better), **items**, **cost per item** (USD and tokens per item, or "not recorded"), **speed
  per item** (p50 and p95 latency in milliseconds, or "not recorded"), **runs** (repeats
  averaged), **scored against** (the reference, linked, or "judge `<scorer>`"), and an
  **inspect** button. Tinted per [row tints](#row-tints). Filterable.
- `versions`, when the dataset has lineage: "Made from `<parent>`: a added, r removed, c changed"
  with the item ids (the first 12 of each, then …), and "Made into `<child>`: …" for each later
  version, then "Runs on different versions measure different items, so they are never tested
  against each other; compare each version's arms on its own page." A version no arm has run on
  still gets a page when it is linked to one that has.
- `references`: each reference (linked), its tier, and "written by `<config>`" for silver.
- `item fields`, when the dataset declares a field set: "Declared in the field set `<id>`", then
  one row per field: **field** (label and name), **type** (with its unit), **filled** ("k of n"),
  **description**, **values**: for a `public` field a summary (counts per value for a choice or
  yes/no field; min – max and median for numbers and durations; the range for dates; the number
  of distinct values for text and URLs), for any other field "not public".
- Command: `evh datasets --dataset-id <id>` ("<id>: N items, M arms from K configs (a config
  rescored against silver or by a judge is an arm of its own)").

## The goals page

- Hero: kicker `goals`, "What each evaluation is for: who uses the output, the decision it
  informs, and the measure that decides. Runs name their goal in their config (`goal:`)."
- `01 goals`: **goal** (linked), **statement**, **decides** ("<measure> (<direction>)"),
  **datasets**, **arms filed** (arms whose config names the goal).
- Empty state: "No goals yet: add `data/goals/<goal_id>.yaml` (schema: `goal.schema.json`)."
- Command: `evh goals`.

## The goal page

The page answers first, then explains, then shows the evidence.

1. **Hero:** kicker `goal`, the goal's title, its statement.
2. `01 the answer so far`: one answer box per dataset of the goal, linked to its dataset page.
   With a baseline promoted for this goal: "baseline promoted <date> · scored against <tier>",
   the arm in bold, the reason, and an **inspect it** button. Without one: "No decision yet. When
   the tests separate an arm worth keeping, promote its run with the reason they give:
   `evh run-promote --run <run_id> --reason "…"`".
3. `02 rounds`, only when the goal has rounds ([PRD-005](../prd/PRD-005-goals-and-rounds.md)):
   - a note: rounds are optional; decisions are made with `evh round-open`, `round-retire` and
     `round-close`; `evh rounds` says the same as the page;
   - a table, newest round first: **round** ("from rN" under it), **status**, **set out to
     learn** (the hypothesis), **arms in play** ("(k retired)", and an **inspect** button when the
     round has a leader and two or more arms: it opens the inspector on the round's arms, at most
     40, against its leader, on the goal's measure; its tooltip is `evh inspect --round rN --goal
     <id>`), **best on <measure>** (the arm
     and its mean), **against the previous round** (a **vs rN's best** button opening the
     inspector with the previous best as baseline), **concluded** (the conclusion, or *open*).
     The open round's row carries the `--accent` tint (`t-open`);
   - one folded section per round (the open one unfolded) listing "changed: …", "retired
     `<config>`: <reason>", "carried in unchanged: `<config>`", and, for the open round, the
     leader against the previous round's best, the baseline it started from and the arm that
     wrote a silver reference of the dataset ("against the arm that wrote silver/<id>
     (`<config>`): <verdict>, Δ, p"), then
     **suggested next, each as the command that does it (the catalog only reads)**: each
     suggestion with its command in a code chip that selects whole on one click and a **copy**
     button beside it (it reads "copied" for a moment, or "selected" with the chip selected where
     the browser refuses the clipboard), and notes such as the spend against the budget, the
     cost per item, and the reference the round is read against with the arms not compared
     (scored against another).
4. `what it is for`: decision, audience, decides ("<measure>, higher is better" or "no
   significant drop against the baseline" for `non_inferior`, with its threshold), min items,
   output contract, status. Then: weighs (the axes the goal measures, with limits shown in
   column headers), strategy (balanced, quality_first, or frugal — how the rule decides who
   ties with the quality leader), tie-break (the axes that break ties, in order; default: cost,
   then speed), and guardrails (prose rules shown, never computed).
5. **One section per dataset of the goal**, titled with the dataset and its role:
   - the dataset (linked), its size, role and "made from" link; its notes; its references
     (with "written by" for silver);
   - "Mean <measure> over each arm's items, in groups by what each arm is scored against:
     numbers from different references, or from a judge, are different measurements and are
     never ranked together. A mean is not a verdict: the inspector tests each arm against its
     group's leader (Holm across them). Flagged arms are never the leader.";
   - per group, gold first, then silver, then judges: a heading ("scored against
     gold/<id>" or "scored by judge <scorer>"), a **Test every arm in this group against its
     leader** button, the decision box, the table and the trade-off charts. A judged arm records
     its judge's score, not the goal's measure: its group's mean column, test buttons and
     decision use that score (`judge_score`, or `judge_score_unvalidated`).
   - the **decision box** ([ADR-0006](../adr/ADR-0006-goal-axes-and-strategies.md)): "Recommended:
     <arm>" (linked), or "No single arm recommended" ("yet", or ": no arm is eligible" when every
     arm is over a limit, flagged or unscored); then the reasons, one per line: each arm that is
     out and why ("speed p95 3,462 ms > limit 2,000 ms"), the strategy with the quality leader,
     who is tied with it and, under `balanced`, who is not separated but further off, so not
     tied; and how the tie-break picked. A muted footer names the strategy and its rule, what the
     goal weighs, the tie-break order, and that promoting is `evh run-promote`.
   - the table: **arm** (linked to its page; tags: `filed` when its config names the goal, said
     in words in the note above the tables and in the tooltip, `baseline`, `recommended`,
     "retired in rN" in `--local` capitals; a retired arm's whole row is greyed out,
     `t-retired`), **mean <measure>**, **items**, then one column per axis that some arm in the
     group records, headed with the axis and its limit ("speed per item · limit ≤ 2,000"): cost
     as USD and tokens per item, speed as p50 and p95 in milliseconds, a project axis as its
     statistic and unit, "not recorded" when the arm has no number, a value past its limit in
     `--local`; then **flags** ("n k < min_items m", "format f not in the contract", "wrote the
     reference it is scored against", and the reasons an arm is over a limit), and **leader** on
     the leader's row or a **test vs leader** button on the others;
   - the **trade-off charts**, two to a row: quality (vertical) against each axis some arm
     records (horizontal), one labelled point per eligible arm (not flagged, retired or over a
     limit), the frontier drawn, a limit as a dashed line;
   - empty state: "No arm on this dataset records `<measure>`."
6. Commands: `evh goals --goal <id>` (the answer, the strategy, tie-break and guardrails, the
   groups with their axis columns, `[baseline]`, `[recommended]` and `[retired in rN]` marks and
   each group's recommendation with its reasons, and one line per round: status, arms, retired, conclusion) and `evh rounds --goal
   <id>` (the rounds' evidence and suggestions in full).

The suggestions appear on the page only when the catalog is built with the harness's own adapter
over the project's data; with a project adapter the rounds table and details still show.

## The reference page

- Hero: kicker `reference`, the reference id, and what its tier means. Gold: "written or checked
  by a person. Every arm scored against it is measured against what a person signed." Silver:
  "written by a model. Consistent, not correct: good for ranking arms against each other, never
  a claim that any of them is right. The arm that wrote it is graded against its own outputs."
- `01 what it is`: tier, dataset (linked), items, written by, from the run, model, created
  (whichever the adapter knows).
- `02 scored against it · N`: the row key and a table of arms scored against it (**arm**,
  **metric**, **mean**, **items**, **inspect**), tinted; or "No arm is scored against it yet."
- Command: `evh references --reference-id <id>`.

## The metrics page

- Hero: kicker `metrics`, "What each number on these pages measures, which way is better, where
  it is recorded, and which goals decide on it."
- `01 metrics`: one row per metric (bookkeeping and totals last), its name linked to the
  metric's own page (each row keeps the anchor `#m-<metric>`): **metric**, **what it measures** (the
  adapter's `METRIC_DESCRIPTIONS`, else the harness's own description, else "not described: add
  it to the adapter's `METRIC_DESCRIPTIONS`"), **better** (lower, higher, or "neutral: a
  description"), **recorded on** (each dataset, linked, with its arm count), **decides** (the
  goals whose primary measure it is). Filterable.
- Command: `evh metrics [--dataset-id <id>]`.

## The arm page

- Hero: kicker `arm`, the arm's label (with the baseline tag when promoted), "One config on
  `<dataset>`, scored one way; its repeats averaged per item.", then its facts: **dataset**,
  **scored against** (the reference, or the judge), **goal**, **runs**, **headline** (its primary
  metric and mean), **last run**, and when it applies "wrote the reference it is scored against".
  Buttons: **Inspect it**, **Against the baseline** (when the dataset's baseline is scored the
  same way), **With the N arms scored the same way**.
- `01 metrics`: every metric it records, the headline first: **metric**, **mean**, **items**,
  **better**.
- `02 cost and speed`, when its runs record either: **cost per item** (USD and tokens per
  item, or "not recorded"), **speed per item** (p50 and p95 latency in milliseconds); the
  sections after it shift by one when it is absent.
- `03 runs`: **run**, **made**, **items**, **cost**, **how** (measured, or how it was derived:
  rescore, judge, reparse).
- `04 config`: the config id, the adapter, and the params; credentials are never shown.
- `05 conditions`: what its runs were measured under (machine, libraries, harness, scorer, item
  and reference checksums).
- `06 the same config, scored other ways`: the same config on the same dataset scored against
  another reference or by a judge, tinted as everywhere.
- `07 rounds`: each round it was in, in play or retired, and the round's status.
- Notes, when the adapter has any (runs left out, and why).
- Command: `evh arms --arm <arm id or config id>`; `evh arms [--dataset-id <id>]` lists them.

## The metric page

- Hero: kicker `metric`, the metric's name, then **better** (higher, lower, or "neutral: a
  description"), **kind** (cost or speed, needing no reference; descriptive; or quality),
  **decides** (the goals whose primary measure it is), **recorded on** (its datasets).
- `01 what it measures, and how`: the one-line summary, then the longer explanation: the
  project's `METRIC_DESCRIPTIONS` `details`, else the harness's own for its metrics. A project
  metric with only one line says how to add the details.
- One section per dataset, `on <dataset>`: a strip chart of the arms' means, a row per thing
  they are scored against (better end marked), then the arms best first: **arm**, **mean**,
  **items**, **scored against**, tinted.
- Command: `evh metrics --metric <metric> [--dataset-id <id>]`.

## The references page

- Hero: kicker `references`, and what gold and silver mean.
- `01 references`: **reference**, **tier**, **dataset**, **items**, **written by** (linked to the
  author's arm), **created**, **arms scored**. Filterable.
- Command: `evh references`.

### Links everywhere

Every arm, metric, dataset, reference and goal named on a page links to its page: in every table,
in the answers and the facts, a reference's author to its arm, a round's configs to their arms,
and in the search box. In the inspector (when the catalog was built by `evh catalog`), the arm
names and the verdicts' metric open their pages.

## Key states

- **Empty:** each page says what is missing and how to add it (no goals, no arm recording a
  measure, nothing scored against a reference, no decision yet).
- **No server:** the inspector shell opened from disk says "this page needs `evh catalog-serve`"
  (UXS-002).
- **Hover:** links take `--accent`; buttons are pill-shaped, monospace, 13px.

## Checklist for a change to the catalog

- The page still carries counts and means only.
- Every arms table keeps the row key and the tints.
- The same view is still a command, with the same numbers (`evh datasets`, `goals`,
  `references`, `metrics`), or the command gains it in the same change.
- `make browser-check` and `harness/tests/test_catalog.py` pass.
