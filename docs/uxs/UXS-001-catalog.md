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
  `harness/scripts/catalog_periods.py` (the periods, the tiles' trends, each row's period
  numbers), `harness/scripts/catalog_arms.py` (the arms page),
  `harness/catalog_assets/style.css` and `catalog.css` (tokens and components),
  `harness/catalog_assets/catalog.js` (theme, search, filter, sort, paging),
  `period.js` (the period on every page), `overview.js` (the home tiles and the charts),
  `arms.js` (the arms page's grouping, filters and picking)

## Summary

`evh catalog` builds static pages over a project's runs into `.build/catalog/`: a home page with
the whole project at a glance, an activity page, a datasets page and a page per dataset, an arms
and configs page and a page per arm, a goals page and a page per goal, a references page and a
page per reference, a metrics page and a page per metric, and the shell of the inspector. Every
page is read-only and carries counts and means only, so the pages can be published. The pages a
home tile opens carry the same period and trends as the tile ([the period](#the-period-every-listing-page)).
This spec describes the pages as built at 0.4.2, checked by building the catalog on this
repository's data (6 goals, 13 datasets, 313 arms, 181 configs, 15 references) and on a tutorial
project with gold, silver and an open round.

## Principles

- **Answer first.** A goal page and a dataset page open with what has been decided (the promoted
  baseline and its reason), then the evidence.
- **Say what a number is measured against**, on every row, and mark the rows that are not scored
  against gold.
- **Rank only like with like.** Arms are ranked within a group scored against the same thing;
  a mean is never presented as a verdict.
- **Read-only.** A decision is shown as the command that makes it.
- **Dense, quiet, both themes.** Tables carry the data; colour marks meaning, never decoration:
  a subject (goals, data, experiments, work and spend), a row's tint, a series. Never red or
  green for a direction: a count that went up is neither good nor bad.
- **A tile is a door.** Whatever a home tile counts, the page it opens shows in more detail, for
  the same period.

## Scope

**In scope:** the shared shell, the period, the home, activity, datasets, dataset, arms, arm,
goals, goal, references, reference and metrics pages, global search, table filter, sort and
paging, row tints.

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

- **Header bar:** the brand (the icon and the product's name, `--brand`, "eval catalog" by
  default, linking to the overview); the global search ("Search ( / )"); the nav, by the
  subjects of the home tiles: **Overview**, **Goals**, **Data ▾** (Datasets, References),
  **Experiments ▾** (Arms, Configs, Metrics), **Activity**, **Inspector**; the theme toggle. A
  group opens a short list under its name and closes on a click elsewhere; the group a page
  belongs to is underlined like a current page. On a phone the nav is a ☰ menu at the left of
  the bar listing every page, a group's under its name; the name gives way to the icon, and the
  search is a round button beside the theme toggle that opens the search box on a row below the
  bar. The bar has the site's and the docs' geometry: 56 px high, 36 px round buttons
  (34 px under 375 px), 8 px apart, the same icons.
- **Switcher (with `--link`):** the parts of the publication the catalog belongs to, in the
  order given, e.g. **Harness · Catalog · Docs**, the catalog marked, after the brand; the brand
  then opens the first part. The same control heads the deployment's site and docs, ☰ at the
  left in all three, so each part keeps its own navigation and any other is one tap away.
- **Counts on the overview:** a count longer than 7 characters shows in short form on a phone
  (19.5M); the tile's title keeps the exact number.
- **Tables:** a cell breaks between words, never inside a name; a table wider than the screen
  scrolls sideways; a cell of running text keeps a readable width on a phone.
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

## The period (every listing page)

The home page, the activity page and the goals, datasets, arms, references and metrics pages
show the same period, and the home tiles open those pages at the period picked.

- **The bar, in the hero:** four chips, **14 days** (picked first), **30 days**, **this month**,
  **all time**, then a **more…** list with the rest: last 7 and 90 days, this week, last week,
  last month, this year. A period picked from the list shows in it, marked like a chip. Beside
  them one line says what the trends compare with ("▲▼ compared with the 30 days before"; for all
  time "since <first day>"); its title gives the dates. On a phone the chips scroll sideways in
  one row.
- **From today:** the period is worked out in the browser from the viewer's date, so "this week"
  is this week even when the catalog was built days ago. A trend compares with the same days of
  the period before (this month to date against the same days of last month, clamped to its end;
  weeks start on Monday). All time has no trend.
- **In the link:** `page.html#p30d`; a page opens at the period its link names, and every link a
  tile or a page gives to another period page carries it. Nothing is remembered between visits.
- **On a table of dated rows:** a **new** badge, in the colour of the table's subject, on the
  row's name when it was made in the period (on the name's line: a long name wraps, the badge
  never sits alone); chips over the table, **all / new in period N / active in period N**, that
  keep only those rows (with the text filter, the paging and the sort); and in-period columns:
  the number, its trend as **▲ 12%**, **▼ 31%**, **▲ from 0** (nothing the period before) or
  nothing when both are zero, and under the runs a line of runs per day. A filter that leaves
  nothing says so ("Nothing new in the last 30 days.").
- **New** means: a dataset on its `created_at` (else its first run); an arm, a config or a metric
  on its first run; a reference on its `created_at`; a goal on its first round or the first day
  of its datasets.
- **Without a script:** the chips stay hidden, the line says the page shows all time, and the
  in-period columns hold all-time counts.
- **Commands:** every list takes `--period P` (`evh datasets`, `goals`, `references`,
  `metrics`, `arms`, `overview`, `activity`), with the same numbers: each page's rows in the
  period come from one builder that the page and the command both read.

## The home page

The whole project at a glance, for the period picked ([the period](#the-period-every-listing-page)).

- Hero: kicker `catalog`, title "Every evaluation, at a glance", a dek saying every name is a
  link, then the period bar and the **tiles**, in four subjects, one colour each (a band on
  top, its trend badge, its line), named in a legend under them: **goals** (goals); **data**
  (datasets, references); **experiments** (configs, arms, metrics); **work and spend**
  (measured runs, billed in USD, tokens). The colour says what a tile is about and nothing
  more. Each tile opens its page at the period picked: goals, datasets, references and metrics
  their pages; arms the arms page; configs the arms page grouped by config; measured runs,
  billed and tokens the activity page.
  - A **stock** tile (goals to metrics) shows the total so far, "+N new" in the period (or "none
    new") and a line of the total growing over the period.
  - A **flow** tile (measured runs, billed, tokens) shows the period's total, its change against
    the period before (**▲ 12%**, **▼ 31%**, **▲ from 0**) and a line of the amount per day. The
    badge is in the tile's colour whichever way it goes, never red or green: up is neither good
    nor bad. The tile's title says it in full ("▲ 173% vs the 30 days before").
  - A long number is shortened (13.7M) wherever its tile is narrow; the title keeps it exact.
- `01 goals at a glance`: one row per goal and dataset it decides on (a dataset marked `decides: false` is left out): **goal**, **dataset**, **decides** (the
  measure, ↓ when lower is better), **baseline** (the promoted arm and its mean, or "none
  promoted"), **leader** (the best arm the goal's decision may recommend, scored against the gold group's
  reference: not flagged, over a limit or retired; and its mean; with no gold reference, the first group scored against a reference, and **decides**
  says "no gold: scored against <reference>"), **leader vs baseline** (the paired test of the two alone, threshold 0.05: verdict,
  Δ, p, and an **inspect** button; "the baseline leads" when they are the same arm),
  **recommended** (the arm the goal's strategy picks once limits and the tie-break are applied;
  shown with cost and speed ratios against the baseline, e.g. "cost 212× · speed p95 1× vs
  baseline"). A note says the goal page tests every arm, Holm across them.
- `02 activity and spend`, side by side (one above the other on a phone): **activity**, measured
  runs per day as bars stacked by dataset (repeats counted one by one); **spend**, cumulative,
  one line for the systems under test and one for the judges, with a **USD / tokens** switch.
  Tokens are tokens in plus out as each call reported them, so a local model's use counts when
  its adapter or server reports usage. The charts span the period (all time starts at the first
  day anything was recorded); a period with nothing in it says so. A button under them opens the
  activity page.
- `03 coverage`: one row per dataset: **dataset**, **items**, **arms scored against** (gold,
  silver and judged counts), **references**, **metrics** (a count that opens to the list),
  **goals**, **last run**.
- `04 recorded`: everything recorded, newest first: **when**, **what** (ran or rescored or judged
  an arm on a dataset, one line per arm and day; a reference made, with its author; a baseline
  promoted; a round opened or closed; every name linked), **kind**. Paged. Only the period's.
- Command: `evh overview [--period 14d|7d|30d|90d|week|lastweek|month|lastmonth|year|all]`: the
  tiles with the same numbers and trends, then the sections, for the period from today.

## The activity page

When the work happened and what it cost, in the period; the measured runs, billed and tokens
tiles open it.

- Hero: kicker `activity`, "Activity and spend", a dek saying what is counted (measured runs,
  repeats one by one; what was billed, in USD and in tokens, to the systems under test and the
  judges), then the period bar.
- `01 activity` and `02 spend`: the home page's two charts, each the page's full width.
- `03 by dataset`: **dataset**, **runs in period**, **runs per day**, **spend in period**,
  **tokens in period**; what moved most against the period before first (up or down, by runs),
  then the busiest; for all time, which has no period before, the busiest.
- `04 by arm`: the all / new / active chips, then **arm**, **dataset**, **runs in period** (with
  its line), **spend in period**, **tokens in period**, in the same order. Filterable.
- `05 by kind`: systems under test and judges: **spend in period**, **tokens in period**.
- Command: `evh activity [--period P] [--arms N]`: the same three tables, in the same order (the N
  arms that moved most).

## The datasets page

- Hero: kicker `datasets`, "Every run, by dataset", and "N arms on M datasets, from K configs. An
  arm is one config on one dataset scored one way, its repeats averaged per item, exactly as
  `pair-test` reads it: a config rescored against silver or by a judge is an arm of its own."
  `evh catalog` prints the same counts, and `evh datasets` has a `configs` column beside `arms`.
- The period bar in the hero.
- `01 datasets`: **group by** chips (no grouping, goal: a dataset under several goals is a group
  named after all of them, one under none is "no goal"), the all / new / active chips, then one
  row per dataset, most arms first:
  **dataset** ("from `<parent>`" under a version; the new badge), **items**, **arms**, **runs in
  period** (with its trend), **runs per day** (a line), **spend in period**, **references**,
  **goals**, **baseline** (the promoted arm), **last run**. Filterable.
- Command: `evh datasets [--period P]`.

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
- `02 what's inside`, from the dataset's profile (`data/profiles/<id>.json`, written by
  `evh dataset-profile` where the dataset is materialized and committed, so a catalog built anywhere
  shows it; never the items' text, which may not be redistributable):
  - one line: "200 items, text, 15–136 words (median 40, middle half 32–46)"; the source, linked,
    when the profile names one ("The text stays there; each item below links to its row", the second
    half only when an item has a link; a link only to an `http(s)` address); and "The
    items changed since this profile was written", when its items digest is not the dataset's;
  - a histogram of words per item;
  - **the gold**: per gold reference its shape: labels in a table (**label**, **items**, **share**),
    entries per item for a list (entities, ranked ids), the fields of a record (scores), or words
    per reference for text; "not profiled" when its texts were not where the profile was written;
  - the items, paged and filterable: **item** (the id, short, the full id in its title), **words**,
    **gold** (the label, "3 entries", "57 words"), **open**: **source ↗** (its row at the source,
    when the dataset or its fetcher recorded one) and **inspect** (the inspector on the dataset's
    largest group of comparable arms, its first 40, opened at this item; only when that group has
    at least two arms). A **text** column only when the
    profile carries text, which `--with-text` writes only for items git already tracks;
  - without a profile: "No profile yet", and the command that writes one.
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
- The period bar in the hero.
- `01 goals`: the all / new / active chips, then **goal** (linked; the new badge), **statement**
  (a column wide enough that a row stays two or three lines), **decides** ("<measure>
  (<direction>)"), **datasets**, **configs filed** (configs that name the goal, each counted once
  however many ways it was scored), **runs in period** (with its line), **spend in period**,
  **changes in period** (a count: baselines promoted, rounds opened or closed), **recommended**
  (per dataset, the arm the goal's strategy picks, with its cost and speed against the baseline,
  as on the home page; "none yet").
- `02 what happened in the period`: one row per change, newest first: **when**, **goal**,
  **what** ("baseline `<arm>`", "round r2 opened"), only the period's; "Nothing happened to a
  goal in this period." The changes are a table of their own, not a cell: a list is not a value.
- Empty state: "No goals yet: add `data/goals/<goal_id>.yaml` (schema: `goal.schema.json`)."
- Command: `evh goals [--period P]` (then "what happened in the period" under the table).

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
     <arm>" (linked), or "No single arm recommended" ("yet", or ": no arm is eligible"), or
     "Shown, not recommended" for a group that never recommends, with the reason as its last line: a
     dataset the goal does not decide on (`decides: false`), a silver group beside a gold one (gold
     decides), and a group measured by unvalidated judges (a trial); then the reasons, one per line: each arm that is out and why ("speed p95 3,462 ms > limit 2,000 ms"),
     the strategy with the quality leader, who is tied with it and, under `balanced`, who is not
     separated but further off, so not tied; and how the tie-break picked. With no eligible arm the
     line counts the reasons ("No arm is eligible: n 31 < min_items 32 (5 arms)."). When the
     recommendation is not the promoted baseline, a bold last line says by how much and whether
     the paired test separates them ("Differs from the promoted baseline, v1: v2 is +0.037 on
     rouge_l against it, not separated (p 0.1246)…"): the rule follows the strategy, the baseline
     is a person's decision. A muted footer names the strategy and its rule, what the goal weighs,
     the tie-break order, and that promoting is `evh run-promote`.
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
  it is recorded, and which goals decide on it.", then the period bar.
- `01 metrics`: **group by** chips (no grouping, role), the all / new / active chips, then one
  row per metric (bookkeeping and totals
  last), its name linked to the metric's own page (each row keeps the anchor `#m-<metric>`; the
  new badge): **metric**, **role** ("decides" when a goal decides on it, "weighs" when a goal
  weighs it as an axis, else "describes"; sortable, and the filter box takes the word), **what it measures** (the
  adapter's `METRIC_DESCRIPTIONS`, else the harness's own description, else "not described: add
  it to the adapter's `METRIC_DESCRIPTIONS`"; the adapter as it is today, over what the runs
  recorded), **better** (lower, higher, or "neutral: a description" when every dataset that
  records it declares it descriptive), **recorded on** (each dataset, linked, with its arm count), **decides · weighs** (the
  goals whose primary measure it is; then, muted, "weighed by" and the goals that weigh it as an
  axis: cost, speed or their own), **arms recording it in period** (with its trend and line).
  Filterable.
- Command: `evh metrics [--dataset-id <id>] [--period P]`.

## The arms and configs page

Every arm, and every config across the datasets it ran on. The arms tile opens it; the configs
tile opens it grouped by config (`arms.html?group=config`).

- Hero: kicker `arms`, "Arms and configs", "N arms from K configs on M datasets. An arm is one
  config on one dataset scored one way: measured, rescored against another reference, judged, or
  run again (the how column says which; group by config to see them together). Pick arms on one
  dataset to open them in the inspector.", then the period bar.
- `01 every arm`:
  - **group by** chips: no grouping, dataset, config, model, provider, scored against. A group
    has a heading row with its name and arm count; a column's sort holds inside each group.
  - **only** chips: local, hosted (hosted when it runs through a provider that bills per call,
    litellm, openai, anthropic and the like, or its config prices tokens), then each price tier
    the configs declare (free, small, mid, large); ties the leader, below the leader (the arm's
    place in a goal's decision: tied with its quality leader, the leader included, or weighed and
    not tied; an arm no decision weighs is in neither); open weights, proprietary (the model's
    weights, from the project's `data/models.yaml`; an unlisted model is in neither; the chips
    show only when the file lists a model an arm ran). Within one kind any chip picked keeps a
    row; across kinds all must.
  - the all / new / active chips; a compare bar once an arm is ticked: "N picked", **open in the
    inspector** (only when the picked arms share a dataset, else "the inspector compares arms on
    one dataset: pick arms of one"), **clear**.
  - the table, flat: a tick box, **arm** (linked; the new badge; under it the role badges:
    baseline, leader, recommended, retired in a round, over a limit (a goal leaves it out for a
    limit it breaks), not eligible (left out for another reason)), **how measured** (measured;
    rescored against `<reference>`; judged by `<scorer>`; re-parsed; run again (`<runs dir>`);
    under a derived arm, how its deciding measure moved from the config's measured arm, "0.712 →
    0.745 (+0.033) vs measured", when both are on the same measure: a judge scores its own),
    **dataset**, **model · provider** (provider muted, "· local" for a local
    one), **deciding measure** (the goal's measure and the arm's mean on it, else its own
    headline), **repeats**, **cost / item**, **latency**, **runs in period** (with its line),
    **spend in period**. Filterable. An arm measured several ways is several rows, one per way,
    said by **how measured**; group by config to read them together. No nesting.
- `02 configs`: the all / new / active chips, then one row per config: **config**, **model ·
  provider**, **datasets** (each linked), **arms**, **spend**, **rank on each goal** (its best
  arm's place among the arms the goal's decision weighs, "#3 of 33"), **runs in period**,
  **spend in period**. Filterable.
- `03 what changed in the period`: **when**, **arm**, **what** (first run, how it was measured,
  promoted as the baseline, retired in a round and why), only the period's. Three or more arms of
  one dataset re-measured the same way on one day (a rescore of every arm) are one line, "N arms
  on `<dataset>`", so they do not bury the rest.
- `04 cost and quality, by goal`: a goal list; the goal's trade-off charts (its quality against
  cost and against speed, the frontier drawn), as on its goal page, one goal at a time.
- Command: `evh arms [--dataset-id <id>] [--by dataset|config|model|provider|scored]
  [--where local|hosted] [--tier <tier>] [--weights open|proprietary] [--quality ties|below]
  [--period P]`, and `evh arms --configs` for `02`. A derived arm's **how measured** carries its
  move, "(+0.033 vs measured)".

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
- `04 config`: the config id, the adapter, and the params; credentials are never shown
  (`api_key_env` is left out; a param named like a key, token, secret or password reads
  "(hidden)", and `experiment-run` refuses such a config in the first place).
- `05 conditions`: what its runs were measured under (machine, libraries, harness, scorer, item
  and reference checksums).
- `06 the same config, scored other ways`: the same config on the same dataset scored against
  another reference or by a judge, tinted as everywhere.
- `07 rounds`: each round it was in, in play or retired, and the round's status.
- Notes, when the adapter has any (runs left out, and why).
- Command: `evh arms --arm <arm id or config id>`; `evh arms [--dataset-id <id>]` lists them.

## The metric page

- Hero: kicker `metric`, the metric's name, then **better** (higher, lower, or "neutral: a
  description"), **kind** ("cost: what an item cost, from the bill or the tokens; needs no
  reference", "speed: how long an item took, by the clock; needs no reference", descriptive, or
  quality; a metric declared quality on some datasets and descriptive on others is a quality
  that names the others, "quality: … (descriptive on summeval_100)", and each dataset's tables
  read it by that dataset's declaration), **decides** (the goals whose primary measure it is), **weighed by** (the goals that
  weigh it as an axis), **recorded on** (its datasets). A cost in USD is shown to six places
  ($0.000012) in its tables, here and on the arm page.
- `01 what it measures, and how`: the one-line summary, then the longer explanation: the
  project's `METRIC_DESCRIPTIONS` `details`, else the harness's own for its metrics. A project
  metric with only one line says how to add the details.
- One section per dataset, `on <dataset>`: a strip chart of the arms' means, a row per thing
  they are scored against (better end marked), then the arms best first: **arm**, **mean**,
  **items**, **scored against**, tinted.
- Command: `evh metrics --metric <metric> [--dataset-id <id>]`.

## The references page

- Hero: kicker `references`, and what gold and silver mean, then the period bar.
- `01 references`: the all / new / active chips, then **reference** (the new badge),
  **tier**, **dataset**, **items**, **written by** (linked to the author's arm), **created**,
  **arms scored**, **arms scored in period**, **runs in period** (with its line). Filterable.
- Command: `evh references [--period P]`.

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
  `references`, `metrics`, `arms`, `activity`), or the command gains it in the same change; a
  page's period numbers come from its builder in `catalog_build.py` (`period_*`), never computed
  twice.
- A table that shows the period keeps the new badge, the row chips and the trends' form.
- `make browser-check` and `harness/tests/test_catalog.py` pass.
