# UXS-002: The run inspector

- **Status**: Active
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-004](../prd/PRD-004-catalog-and-inspector.md) (catalog and inspector),
  [PRD-006](../prd/PRD-006-datasets-versions-fields.md) (fields), [PRD-002](../prd/PRD-002-references.md) (references)
- **Related RFC**: [RFC-003](../rfc/RFC-003-catalog-adapter.md) (the server, its API and limits)
- **Related UX specs**: [UXS-001](UXS-001-catalog.md) (shell, tokens, tints, paging),
  [UXS-003](UXS-003-cli-and-onboarding.md) (`evh inspect`)
- **Implementation paths**: `harness/catalog_assets/inspect.js` (the page),
  `harness/scripts/catalog_serve.py` (`/api/compare`, `/api/item`),
  `harness/scripts/catalog_build.py` (`render_inspect`: the shell and `runs.js`)

## Summary

The inspector is the catalog's one live page, `inspect.html`, filled by the server that
`evh catalog-serve` starts on 127.0.0.1. The user chooses arms on one dataset; the page tests
each against a baseline with the harness's paired test and shows, in order: the verdicts, the
conditions the arms ran under, any breakdown by a field, the **analysis** charts, the per-item
table, and, on a click, one item's outputs side by side with the reference and the item itself.
Its state lives in the URL, so every link from the catalog opens a ready comparison.

## Principles

- **The verdict first, then the evidence for it.** Charts and items explain a verdict; they do
  not replace it.
- **The same test as the command line.** The page calls the server, the server calls
  `evaluation_harness.stats`; `evh inspect` calls the same function.
- **Refuse and say why.** Arms that cannot be tested against the baseline are set aside with a
  note, never tested anyway.
- **Item text only here, only locally.** The static pages never carry it; a public deployment
  never returns the item itself.

## Scope

**In scope:** choosing arms, the controls, the verdict table, conditions, fields (filter and
breakdown), the analysis charts, the per-item table, the item view.

**Non-goals:** writing anything; choosing a round (the page has no round picker: scope a round
with `evh inspect --round rN`); comparing arms across datasets.

## State in the URL

`inspect.html?runs=<arm>,<arm>,...&baseline=<arm>&metric=<name>&where=<field>:<value>&by=<field>`.
Links from the catalog may also carry `family` and `threshold`, so a verdict reached from a
goal page matches the one that page implied. Every control rewrites the URL and reloads.

## Choosing arms

- **Chips:** each chosen arm as a chip with × to remove it.
- **Add:** a text box with a list of every arm, narrowed to arms on the chosen arms' dataset
  ("add a run on <dataset>"), and an **Add** button.
- **Nothing chosen:** "Pick runs from an experiment or dataset page in the catalog ("Inspect
  runs"), or add them above."
- **No server** (the file opened from disk, or the server stopped): "No inspector server. Start
  it with `evh catalog-serve` and open this page from the address it prints."
- At most 40 arms in one comparison (`--max-arms`); the catalog's group links stop at 40.

## Controls

- **metric:** every metric the arms record, each with its format and "(archived reference)" when
  that applies, ↑ or ↓ for its direction, and how many arms have it. The default prefers a
  quality score over lengths, counts, cost and latency, then what the baseline recorded, then
  what most arms have.
- **baseline:** any chosen arm. Without one, a promoted baseline among the chosen arms, else the
  first arm.
- **re-score what is not on record:** a checkbox shown only when the adapter can re-score
  (the harness's own adapter cannot; a project's may).
- **filter items by** a field, then a value input fitted to its type (a list for a choice, yes/no
  for a boolean, `min..max` or one value for numbers and durations, an exact value otherwise) and
  **Filter**; each filter becomes a chip with ×. Shown when the dataset declares fields.
- **break down by** a `choice` or `boolean` field, or none.

## Notes above the results

Plain-language notes, one per line, for everything the comparison could not do: the baseline
swapped because the chosen one lacks the metric; arms that read different input hashes; arms
with no `dataset_id` on record; arms with no score on this metric; average-only arms set aside
because they recorded exactly the same average as an arm already shown; arms left out because they are on another
dataset; arms not tested because they were scored against another reference than the baseline's
("Pick a baseline scored against the same reference to compare them."); arms with only an
average; outputs that did not follow the asked format; a filter ("a subset is a smaller sample,
so less can be separated"); a breakdown ("a group is held to a stricter threshold than it would
be alone") and items in no group.

**Not scorable:** when no arm has a per-item score, the page says so and offers a button per
metric it can compare (output length, latency) instead.

## 01 verdicts

- Eyebrow "verdicts · <metric>", the metric linked to its row on the metrics page.
- One row per arm against the baseline, smallest p first, tinted like the catalog's rows
  ([UXS-001](UXS-001-catalog.md#row-tints)). Columns: **run vs baseline**, **verdict** (second,
  so a phone sees it), **items**, **mean**, **Δ vs baseline**, **wins–losses** (with ties),
  **p (exact ≤30)**, **Holm threshold**.
- The verdict is a chip: ▲ `separated: better` (border `--open`), ▼ `separated: worse` (border
  `--local`), or plain `not separated`; on a neutral metric `separated: higher` / `lower`. When
  the number of items cannot reach p 0.05 at all, the row says "n items cannot reach 0.05".
- Under the table: "Baseline <arm>: mean m. Holm across k comparison(s)", whether the family or
  threshold came from the page the user came from, the direction, and where the scores come from.
- This table is never paged: its Holm thresholds are read together.

## Conditions

From each arm's recorded conditions (machine, library versions, harness, scorer, items,
reference bytes):

- all equal: one line, "Same conditions: all n recorded fields match across these runs";
- otherwise "Conditions · k of n fields differ", the warnings, and a table of the differing
  fields, one column per arm, the cells that differ from the baseline marked. Warnings: different
  scorers ("these numbers are different measurements. Re-score them with one adapter (evh
  rescore) before reading the test."), different reference bytes, different item bytes, and
  latency compared across machines.

## Average only

Arms that recorded only a run-level average: a table "Average only · n: no per-item scores, so
no test", with each recorded average and its difference from the baseline's mean. Never tested.

## Breakdown

With **break down by** set: "By <field> · g group(s)", a table of group (with its item count),
run vs baseline, verdict, items, Δ, wins–losses, p and Holm threshold, and the note that the
test runs within each group, Holm-corrected over all tests together. Not paged.

## 02 analysis

Inline SVG charts in the catalog's tokens; each arm keeps one colour (`--s1` to `--s8`, then
muted; the baseline `--baseline`) on every chart, never a colour by rank. A legend names them.

- **Spread per run:** every item's score, one row per arm, baseline first, then best mean first;
  a bar and a number for each arm's mean, a dashed line for the baseline's mean.
- **Difference from the baseline:** each item's score minus the baseline's, one row per arm;
  the mean difference, wins–losses, and ✓ better / ✗ worse in words when separated after Holm
  (words, because an up-arrow beside a negative number reads wrong on a lower-is-better metric).
- **<metric> against <shape metric>:** a scatter of score against a per-item fact such as
  output length or latency (a picker chooses which), one faded dot per arm per item and a cross
  at each arm's average: the length or speed trade-off.

Hovering a dot shows its arm, item and value. Below 700px the charts switch to a narrow layout
(labels above each row) rather than scroll.

## 03 per item

"per item · n": one row per item, one column per arm (the baseline's marked), each cell the
score with ▲ or ▼ where it beats or trails the baseline on that item. Paged 10 at a time like
every catalog table. A row opens on click, Enter or Space.

## 04 the item view

"item · <id>", opened under the table:

- the item's **fields**, when the dataset has them (a URL field as a link only for http(s));
- **the item itself**, "what every arm read", with its length; unfolded when 1,500 characters or
  fewer, folded otherwise. The local inspector only;
- a toggle to **mark what each run adds and drops against the baseline** (word-level), useful
  between near-identical outputs;
- columns: the reference (when the metric names one, else the baseline's), then each arm's
  output with its word count, the baseline's marked.

## Checklist for a change to the inspector

- `evh inspect` gives the same verdicts, conditions and breakdown, or gains the change too.
- The verdict and breakdown tables stay unpaged; the per-item table pages.
- No inline script or style (the pages run under a CSP without `'unsafe-inline'`).
- `make browser-check` passes (`harness/tests/test_inspector_browser.py`).

## Parity with the terminal

| on the page | in the terminal |
| --- | --- |
| choose arms, baseline, metric | `evh inspect --runs a,b [--baseline a] [--metric m]` (config ids are looked up under `--from`, default `runs`) |
| a round's arms (the goal page's **inspect** button on a round) | `evh inspect --round rN [--goal g]`: the goal's measure, against the round's leader; arms with no score on it are named and left out |
| filter, breakdown | `--where field:value` (repeatable), `--by field` |
| notes, verdicts, conditions, breakdown | printed in that order (notes as `NOTE:` lines) |
| the item view | `--item <item_id>`: fields, the item itself, the reference, each arm's output |
| the per-item table | `--items`: every item's score per arm, and each arm's Δ against the baseline |
| the analysis charts | `--analysis`: the spread per arm and the difference from the baseline, per item, as numbers; `--x <metric>` adds each arm's mean on a second metric (the scatter) |
