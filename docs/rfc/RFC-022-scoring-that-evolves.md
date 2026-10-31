# RFC-022: Scoring that evolves: preview it, re-score with it, or adopt it from the next round

- **Status**: Built for 0.6.0 (2026-10-31; see "As built"), on the owner's go of 2026-10-31: "the user can use the harness
  to develop new scoring and either rescore or apply it on the next round", "from the harness's perspective, with
  the triage fleet as the use case that validates it".
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-002](RFC-002-run-records-and-derived-runs.md) (derived runs: a re-score is its own record);
  [ADR-0004](../adr/ADR-0004-experiment-rounds.md) (rounds); [RFC-021](RFC-021-fingerprint-v5.md) (the instrument
  part, hashed by code); [RFC-019](RFC-019-datasets-from-production.md) §8 (the triage fleet, the acceptance case)

## Abstract

A project's scoring changes while it learns: a measure turns out to reward the wrong thing, a rule is missing, a
limit was set too late. The harness can already re-score stored outputs (`evh rescore`, $0), but nothing says
which scorer a round was judged by, a re-score lands wherever `--out` points, and a round carried into the next
keeps its old numbers. This RFC makes a scoring change a first-class step: **preview** it against a goal,
**re-score** a round with it, or **adopt** it when the next round opens, with every round recording the scorer
that judged it.

## Problem

Round 1 of the triage goal shows each gap (RFC-019 §8, `research/internal/TRIAGE_RESULTS_LIVE.md`):

- Its runs were scored by **seven versions** of the adapter's `score()`; the measured records disagree with one
  another, and only a hand re-score into a directory named for the occasion (`data/runs-triage-current`) put them
  on one scorer. A second hand set was needed for the repeats, and each one needed its own `.gitignore` block in
  this repository before git would keep it.
- Nothing records which scorer a round was judged by. The goal view reads the latest re-score (one row per arm,
  0.6.0), but a round's own page reads the measured arms, so the two disagree.
- The owner changed the scoring after round 1 (2026-10-31: a no-decision counts as a miss on a real problem and a
  false alarm on noise; the false-alarm ceiling becomes "no worse than the baseline arm, by the paired test"). To
  see what that changes before machines are booked there is no command: only another hand re-score.
- `round-open --keep` carries an arm "unchanged, not run again", so in a round that changed its scoring the
  carried arms would be compared on the old one.

## Design

### 1. The scorer a run was judged by

`scorer_of(metrics)`: for a derived run, `derived.with` (the adapter's `sha256` and path, a judge's scorer id); for
a measured run, the instrument's `adapter.sha256` (RFC-021: the instrument is hashed by its code). Shortened to 12
characters where it names a directory. Nothing new is recorded on the runs: every run already carries it.

### 2. One place for re-scores, designated by the tool

`evh rescore` without `--out` writes to **`data/runs-rescored/<scorer>/<source>/`**: `<scorer>` the 12-character id
of the scorer doing the re-scoring, `<source>` the runs directory the run came from (`runs`, `runs-repeats`, …),
so a repeat set never sits beside a first pass of the same config (V8). The catalog, `evh goals`, rounds and
`validate` read it like `runs-judged/<scorer>/`. A project made with `evh init` keeps it (nothing ignores it); this
repository re-allows it once in `.gitignore`, for every scorer to come. `--out` still names any other directory
(a re-score against another reference keeps its own name: `runs-adjudicated`, `runs-silver`).

`evh init`'s `.gitignore` also ignores the throwaway directories, `data/runs-smoke*/` and `data/runs-tune*/`, as
this repository does: without it a new project would commit its smoke passes and show them as results.

### 3. Preview: `evh score-preview --goal G [--round rN]`

Re-scores, in a temporary directory, every arm the goal (or the round) reads, with the scorer in the working tree,
and prints per arm the deciding measure before and after and whether it is still within the goal's limits; then the
decision before and after (the quality leader, the arms tied with it, the recommendation). It writes nothing to the
project and spends nothing: the tool for developing a scoring. `--json` as the other views.

### 4. Re-score a round: `evh rescore --goal G --round rN --why "…"`

Re-scores the round's arms (its own runs and the ones it carried) into §2's place, and appends to the round's record
a `scoring` entry: `{at, scorer, why, written}`. A closed round may be re-scored: its conclusion stays as written,
and its page then shows the scorer it was concluded under beside the one it is now read with.

### 5. Adopt it from the next round: `evh round-open --from rN --scoring "why"`

The new round records `scorer` (the working tree's) and the `why` among its `changes`. Every carried arm whose runs
were scored by another scorer is re-scored into §2's place before the round opens ($0), so the round compares like
with like; the round's page and `evh round-status` list each carried arm's deciding measure under the old scorer
and the new.

### 6. Rounds read what the goal reads

A round's evidence (`evh round-status`, its page) reads each arm through the same rule as the goal view: a measured
arm every run of which was re-scored against the same reference is read from its latest re-score.

### 7. A round says when its arms were judged by different scorers

`validate` notes a round whose arms' latest runs carry more than one scorer, naming them and the command that puts
them on one (`evh rescore --goal G --round rN`). A note, not a failure: a round opened before this RFC may have
been concluded that way on purpose.

### 8. Recording a round that was run before rounds were opened

`evh round-open --goal G --dataset D --adopt` (no `--from`): the arms already run on the dataset for the goal become
the round's (`carried`), so a goal whose first round was run as plain runs gets its r1 and can close it. Refused
when the goal already has a round.

### 9. A limit against the baseline

A goal's axis may set `limit: baseline` instead of a number: an arm is within it when the paired test does not find
it worse than the goal's baseline arm on that measure (the goal's paired test, p < 0.05, each arm on its own). Without a
promoted baseline the axis says so and applies no limit. `evh goals` and the goal page show "no worse than
<baseline> (paired test)" as the limit.

## The use case: the triage fleet

1. **r1, recorded.** `round-open --goal triage_orrery --dataset orrery_triage_v1_labelled --adopt`, then the
   existing hand sets move into `runs-rescored/cd35dc1ffccc/{runs,runs-repeats}/` (they are that scorer's
   re-scores), then `round-close` with what it showed (nothing separated at n = 65) and production's arm promoted as
   the baseline.
2. **The new rules, previewed.** `score-preview --goal triage_orrery` with the no-decision rule in the adapter and
   `false_alarm: {limit: baseline}` in the goal: what moves, and whether anything separates.
3. **r2, adopted.** `round-open --from r1 --scoring "a no-decision is wrong on both sides; the ceiling is the
   baseline"`: r1's arms are carried and re-scored automatically; the round shows them before and after. Its new
   arms (onboarded models, a larger gold) run under the new scorer.

## Not in scope

- Changing a measured run's record: a re-score is always its own derived run (RFC-002).
- Versioning a goal's criteria per round: a goal file changes in git, as today; a round records the scorer, and its
  `changes` say what else changed.
- A judge scorer's own evolution (ADR-0001): judged sets stay under `runs-judged/<scorer>/`.

## Alternatives considered

- **Re-score in place.** One directory, but the first measurement is lost from the record and two runs of one
  config disagree in git history only. Rejected (RFC-002).
- **A directory per occasion** (`runs-triage-current`), as round 1 did. Every one needs its name invented, a
  `.gitignore` block in a strict repository, and a reader who knows which is current. Replaced by §2.
- **A ceiling as a fixed count, fixed before the round.** Simple, but it does not follow the baseline as it changes,
  and round 1 showed how close arms sit to any fixed edge. Kept possible: a number still works as a limit.

## As built (0.6.0)

- **The scorer's identity is the adapter's code** (`_codeid`, by behaviour), so an edit to its calling code alone
  counts as a new scorer too. That is the conservative side: a re-score is never skipped for a scoring change, and
  `score-preview` says whether anything moved. `validate`'s note (§7) groups a round's arms **by adapter**: arms
  with different adapters (a hosted LLM's and a fine-tune's) were never one scorer.
- **`--keep all`** carries every arm of `--from` (the round's arms, as `evh rounds` lists them).
- **§9's paired test gates each arm on its own** (owner, 2026-10-31): p < 0.05 against the baseline, not corrected
  across the arms, as a numeric limit gates each arm. Built first with Holm across the group, it ruled out nothing in
  the triage round (56 arms, 31 noise items), not even the arm that escalates everything; per arm it rules out two.
  Holm stays where the decision claims one arm beats the others (the tie).
- **A round's evidence notes how many arms it reads from a re-score**, and `evh rounds` prints the round's scorer
  and each scoring change, as the goal page's round section lists them.
- **Found while building:** adapters and hooks were imported through Python's bytecode cache, which trusts a `.pyc`
  while the source's mtime (whole seconds) and size match; a scorer edited within the second to a value of the same
  length ran its old code while the re-score recorded the new code's hash. `load_module` now compiles from the
  source every time (a regression test in `test_scoring_evolves.py`).
- `rescore --dataset-id` without `--out` re-scores the measured runs of every runs directory git keeps (not only
  `data/runs`), each into its designated place.

## Testing

Each section gets a test that fails without it: the designated path and its V8 split; preview's before/after and
that it writes nothing; a round's `scoring` entry; `--scoring` re-scoring exactly the carried arms on another
scorer; round evidence reading the re-score; the validate note; `--adopt`; `limit: baseline` against a promoted
baseline and without one. The triage steps above are the end-to-end check.
