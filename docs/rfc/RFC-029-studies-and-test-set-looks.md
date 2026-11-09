# RFC-029: Studies, and the looks a test set allows

- **Status**: Draft (0.8.0), revision 2 (2026-11-09): the owner's answers to four questions, and an independent
  review's findings (Fable), each checked against the code; two questions left. Revision 1 the same day. Step 4.4 of
  `research/internal/PLAN_0.8.0.md`. It reworks the 0.5.0 drafts' RFC-010 (studies, revision 3), RFC-015's heldout
  looks and attainable p, and PRD-009 FR2-FR5 (not merged; on `backup/050-pre-rebase-20261028`) onto what shipped
  since: rounds, the sealed side of a split and its looks (the fleet's feedback 29), the contender test (A2), who
  acted and baselines in versions (RFC-027), jobs and spending caps (RFC-026), prompt versions (RFC-028).
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-004](RFC-004-eval-rounds.md) (rounds), [RFC-026](RFC-026-an-api-for-every-command.md) (a study
  is a job; its cap), [RFC-027](RFC-027-who-acted-and-baselines-per-goal.md) (a decision's evidence; the actor),
  [RFC-028](RFC-028-prompt-versions-and-code-ref.md) (a study makes prompt versions), ADR-0025 (a hypothesis in the
  config), `_seal.py` and `dataset_unseal.py` (a sealed side and its unseals)
- **The owner's decisions it keeps** (2026-10-26/27, on the drafts): one kind of study, research; evidence only from
  a separate confirmation with its rule given first; samplers a grid, a command (ask/tell, Optuna) or the calling
  agent; no code in the space of changes; no git writes; Karpathy's `results.tsv` imported; one dollar cap; a test
  set's looks front-loaded at α·6/(π²k²), a protective limit of 10, past it only the person's own consent; looks
  counted from decisions, not stored; use before the release not counted; aggregate-only measures allow the point
  rule only and cannot be confirmed.

## Abstract

A **study** is research: a spec and an append-only log. `evh study-run` opens a round and repeats ask/tell: a
**sampler** proposes a **trial** (parameter values or prompt versions, with a hypothesis), the harness runs the
baseline's config with those changes on the study's validation dataset, compares it with the best so far and with
the baseline, keeps or drops it by the spec's rule, and records it, until a stop rule fires. A study states no
evidence and never suggests promotion. Evidence is one separate step, **`evh study-confirm`**: the best trial against
the baseline on a test set, once, with the rule given before the test items are looked at, at that test set's next
**look** level. A test set's looks are counted from the decisions recorded on it, each at a stricter level, so
looking again and again cannot manufacture a result; a check refuses a look that could never meet its rule.

## What exists today (read 2026-11-09)

- Rounds record a sequence of arms with a hypothesis, retirements with reasons and a conclusion; one round of a goal
  is open at a time.
- `dataset-split --seal` holds a test side back; `dataset-unseal --config C` opens it to C and to the config C's
  committed hypothesis is `against` (`_seal.opened_for`), for a config on that dataset only (`dataset_unseal.py:67`),
  each unseal recorded as one look (`dataset_unseal.py:95`), with no level and no limit.
- `pair-test` decides at 5% two-sided (`pair_test.py:561`; the sign-flip and exact tests are two-sided,
  `stats.py:107`); `run-promote` freezes its verdict as the evidence (RFC-027, `promote_baseline.py:120`).
  `stats.min_attainable_p(n)` is `2/2**n` (two-sided) and reaches the catalog through `compare()` (`stats.py:824`), not
  `pair-test`. The contender test (`stats.noninferior`) runs Tango for 0/1 at any size and the bootstrap-t at half
  the level from 100 units, "too few" below.
- `run` has no option to run part of a dataset; configs are found in `data/configs/` (`_common.arm_config_files`).
- V5 fails two runs in one directory with byte-identical scores and items (`validate_tree.py:370`).
- Loops live outside the harness (the podcast project's `program_*.md` agents and its parameter sweep; Karpathy's
  autoresearch), with results in TSV files the catalog cannot read.

## Design: test-set looks

- **A test set** is a dataset a goal declares with `role: test`, or the sealed side of a split. Its looks are owned
  by its items' digest (`_seal.items_digest`), so a run on part of it spends the same budget and dropping an item does
  not make a fresh one.
- **A look is a decision written on it** (owner, 2026-11-09): a `dataset-unseal`, a `study-confirm`, and a
  `run-promote` or `round-close --promote` whose evidence is computed on it. Reads (`pair-test`, `rounds`, the pages)
  never take one: on a test set they show the nominal result labelled "nominal, not a look" and the next look's level.
- **One look per question, whatever records it**: a look is keyed by (the set's digest, the two arms' fingerprint
  hashes, the measure, the rule). A confirmation writes an unseal entry, its `confirm` line and, when promoted, a
  baseline version whose evidence carries the same key: one look. A decision whose key is already recorded reuses its
  number and verdict. A first promotion on a set (`compared_to: null`, nothing compared) is not a look.
- **Levels**: one-sided α = 2.5% per test set, spent front-loaded: look k at α·6/(π²k²) (1.52%, 0.38%, 0.17%,
  0.095%, ...; the sum over every look is α). Comparisons within one look share its level by Holm. The tests a look
  uses are one-sided at that level: the sign-flip and exact tests in the declared direction (`stats` gains the
  one-sided p, computed directly, not halved), the contender test as it is.
- **A protective limit** of 10 looks per test set (owner, 2026-11-09; a goal may declare `test_looks: K`, the smallest
  of the goals sharing the set applies): look 11 and later are refused unless the person running the command passes
  `--confirm-extra-look`; an agent cannot (an `agent:` actor is refused). Levels continue the series, so consent never
  inflates the error. Fresh items are the way out.
- **Counted, not stored**: the next look's number is one more than the distinct keys recorded on the set (unseal
  entries, confirm lines, baseline versions' evidence, each now carrying the key, the number and the harness version).
  Two decisions made at once on two clones can take one number; `validate` V25 reports a double-spent look, naming
  both. Within one clone a look is taken under the set's lock (`dataset:<id>`, RFC-026), so two commands there never
  share a number.
- **Before this release** nothing counts: an unseal entry without a harness version (made before 0.8.0) is shown as
  prior use, not a look; pages show how many configurations had runs on the set before, beside the levels.
- **Can these items show anything**: before a look, the smallest p the items can reach under the look's test, against
  the look's level divided by the family's size. Superiority: 1/2^n′ one-sided (n′ the non-zero paired differences;
  before any run, all items). Non-inferiority on 0/1: Tango's p in the best case (every discordant item favouring the
  arm). Non-inferiority on a continuous measure: below 100 units "too few" (the contender test's rule), refused at
  once. A look that could never meet its rule is refused (`no-possible-evidence`), unless the person overrides; the
  outcome is then labelled inconclusive. `stats.min_attainable_p` takes the differences and the test, not only n.
- `evh looks [--dataset D]` lists each test set's looks (number, level, key, who, verdict) and the next level; the goal
  page and the dataset page show the same.

## Design: studies

### Files (both stores, through `_store`)

- **The spec**, `data/studies/<goal>/<study_id>.yaml` (`schemas/study-spec.schema.json`): `dataset` (the validation
  dataset trials run on; a test set is refused), `baseline` (a baseline version, a run, or a trial of an earlier
  study), `measure` (a metric of the goal), `space`, `sampler` (`grid`, `command`, `agent`), `accept` (`point:
  {min_gain, relative}` or `test`), `limits` (`[{metric, direction, limit}]`), `stop` (`trials`, `usd`, `wall_h`,
  `patience`, `ask_timeout_h`, default 2), `repeats`, `frozen` (paths), `directions` (the person's instructions,
  autoresearch's `program.md`). With no `trials`, the study runs until stopped, and `usd` and `wall_h` are required.
- **The log**, `data/studies/<goal>/<study_id>.events.jsonl`, one JSON line per event: `start` (the spec's hash, the
  frozen files', the scorer's, the references', the actor and the instruction), `ask`, `trial` (k, the change, the
  hypothesis and rationale, its runs, the comparison with the best so far and with the baseline, kept, dropped,
  failed or no effect with the reason, the cost, the items shown to the sampler), `end` (the stop rule, a summary),
  `confirm`. The study's state is read from the log, never stored apart. Every write to it is under the study's lock
  (`study:<goal>/<study_id>`, RFC-026), since in the SQLite store an append is a read and a rewrite.
- **A trial's config**: see question 1.
- **The round**: `study-run` opens one with `study: <study_id>`; it closes when the study ends, never by hand, and does
  not count against the one-open-round rule. Each trial is an arm; a dropped trial is retired with its reason.
- **V5**: a trial that measures exactly as the best so far (a change the system does not read) is a finding: V5 notes
  it ("trial 7 measured the same as trial 4: no effect") instead of failing.

### The space of changes

Groups of parameters (dotted paths for nested ones), each enabled with a reason, tried in order a value at a time from
the best so far, a group ended after `move_on_after` trials without a kept one; or prompt names (RFC-028) that may
change, in order; `max_candidates` caps the study. Code is never in the space (the owner's decision).

### The loop (`evh study-run`, a job)

```text
open the round; append start; best so far = baseline
while no stop rule fires:
    the hashes against start (spec, frozen files, scorer, references): a change stops the study
    proposal = sampler.ask(state)                    # never test items
    record new prompt versions (RFC-028)
    run the trial's config on the dataset (`run` as a child, given what is left of the cap, RFC-026)
    compare with the best so far and the baseline (nominal p); decide; append the trial line
    sampler.tell(trial)
append end; close the round
```

- **Deciding a trial** (repeats averaged per item first): the point rule (the trial's mean beats the best so far's by
  `min_gain`; 0 is autoresearch's "improved") or the test rule (separated as better). In both, no limited metric may
  fall beyond its limit **against the baseline**, and a trial kept for being cheaper or faster, not better, must be
  non-inferior **to the baseline** by the goal's margin (the contender test), so concessions cannot accumulate. With
  small validation sets that is usually inconclusive and refused: expected. Every p is labelled nominal. A measure
  with one number per run (autoresearch's val_bpb) allows the point rule only, and its trials cannot be confirmed.
- **Stop rules**: trials, dollars (the study's own cap, EVAL_MAX_COST_USD or the job's `max_cost_usd`, over every
  trial; a round's budget applies to each trial's run as to any), wall time, patience. `study-run` is a job like any
  (RFC-026): detached, followed, stopped; `--resume` continues after the last finished trial; `--dry-run` calls
  nothing and prints the plan.
- **Samplers** (`ask(state) -> proposal`, `tell(trial)`; the state is the best so far, the baseline, the history, the
  space, the money left and the directions): `grid`; `command` (newline-delimited JSON over stdio; the Optuna example
  wraps `optuna.Study.ask/tell`); `agent`: `study-run` opens the study and returns; the agent calls `study-ask` (the
  state, with an `ask_id`) and `study-tell --ask ID --proposal FILE` (runs the trial). One ask is open at a time; a
  used ask, or one older than `ask_timeout_h`, is refused. Every item shown to a sampler is recorded, so a confirmation
  leaves it out.
- **Who acted**: a trial's records (its run, a prompt version it made) name the actor who started the study (a
  person, or an agent and its person, RFC-027) and, under `source`, the sampler and the trial. A sampler is not an
  actor of its own.

### The confirmation (`evh study-confirm`, a decision)

`evh study-confirm <study> --test <dataset> --rule superiority|noninferiority [--trial k] [--dry-run]`:

1. The rule is given on the command line before the test items are looked at, and never switched. The `confirm` line
   is written first, timestamped before any run it allows: it is the naming in advance (as an unseal's own entry is
   when the hypothesis is not yet committed, `dataset_unseal.py:80`).
2. The items: the test set's minus any in the validation dataset or shown to a sampler in any study of the goal; the
   count is recorded; none left refuses. `run` gains `--items FILE` (the item ids to run; the fingerprint's
   `items_sha256` is then the part's, and the look is still the whole set's, by its digest).
3. The configs: the trial's and the baseline's, each with `dataset_id` the test set (config ids `<id>-on-<test>`,
   written as the trial configs are, question 1); a sealed set is unsealed for exactly these two, as this look.
4. The look: its key, number and level; past the limit, the person's `--confirm-extra-look`; a look that could never
   meet the rule is refused.
5. The two run once on those items (jobs). The verdict at the look's level, one-sided: superiority, or
   non-inferiority by the goal's margin; the limits as non-inferiority in the same Holm family; a failed limit caps the
   outcome at inconclusive. Shown beside the trial's validation effect, so the optimizer's curse is visible.
6. The verdict is added to the `confirm` line; promotion is suggested only when the outcome meets the rule: see
   question 2.

### Commands (each with `--json`; RFC-026 serves them)

| command | served | locks |
| --- | --- | --- |
| `study-run SPEC` | job, spends | `study:<goal>/<id>`; each trial's run its own (`config`, `dataset` shared) |
| `study-ask STUDY` | job (it writes the ask), and an MCP tool | `study:<goal>/<id>` |
| `study-tell STUDY --ask ID --proposal FILE` | job, spends, `--proposal` an upload; and an MCP tool | `study:<goal>/<id>` |
| `study-stop STUDY` | job | `study:<goal>/<id>` |
| `study-confirm STUDY --test D --rule R` | job, spends, a decision (`by` required) | `study:<goal>/<id>`, `dataset:<test>` |
| `study-import FILE --goal G` | job (Karpathy's `results.tsv` as a closed study; its trials not confirmable) | `study:<goal>/<id>` |
| `studies [--goal G]`, `study-status STUDY`, `looks [--dataset D]` | reads | none |

`study-ask` and `study-tell` are MCP tools as well (owner, 2026-11-09: "also MCP tools"): the first writes on the MCP
server, an exception to RFC-027's read-only rule for the agent sampler alone. Each runs as the command does, through
the API's job path, with the agent's actor (`EVH_ACTOR=agent:...`, `EVH_FOR` the person) required. A study is named
`<goal>/<study_id>`, or by its id when one goal has it.

### The catalog

The goal page's round section shows a study's trials (k, the change, the hypothesis, the outcome, the decisive score,
the cost), its stop reason, its confirmations with their looks, and the summary; each trial links its runs and its
prompt diff. A test set's looks show on its dataset page and its goals' pages.

## Migration

None for data: looks are counted from records, and before this release nothing counts. `pair-test` and the pages gain
the "nominal, not a look" label on test sets; a goal's recommendation does not change.

## Alternatives considered

- **Exploratory and confirmatory studies** (the drafts' revisions 1 and 2): a confirmation after any study gives the
  same evidence with the rule fixed first, and one kind is simpler (the owner's revision 3).
- **Let a study promote its winner**: promotion stays a person's, or an agent's after asking.
- **An optimiser of the harness's own**: ask/tell lets Optuna's samplers plug in.
- **The agent edits files and the harness snapshots them**: the agent proposes text through `study-tell`; no tracked
  file is edited, and no code.
- **Each look at α/K** (the drafts' first rule): front-loading gives the first look the most power, which is when
  people look.
- **A look file or reservation**: two clones would each hold one; counting from decisions under a lock, and reporting
  a double spend across clones, is honest about what files can do.

## Testing

- `tests/test_looks.py`: levels 1.52%, 0.38%, ... from decisions; one confirmation and its promotion are one look; a
  read takes no look; a part of the set spends its budget; past the limit refused, an agent's consent refused, the
  person's taken; a double-spent look reported; `no-possible-evidence` on 5 items for a one-sided 1.52% look, and for
  continuous non-inferiority below 100 units; an unseal from before 0.8.0 shown as prior use.
- `tests/test_study.py` (a fake adapter, $0, both stores): a planted real gain kept and confirmed better; a chance gain
  on a tiny set dropped or not confirmed; a cheaper equal arm non-inferior to the baseline; a chain of small
  concessions cannot pass the baseline's margin; shown and validation items left out of the confirmation; a spec
  change mid-study stops it; the cap stops it; resume continues without re-running; `--dry-run` calls nothing; the
  agent ask/tell (a second tell of one ask refused, a lapsed ask refused) through the CLI and the MCP tools;
  `results.tsv` imported; V5 notes a no-effect trial.

## Decided by the owner (2026-11-09)

1. **Composite measures**: after 0.8.0.
2. **The agent sampler**: `study-ask` and `study-tell` on the command line, the API, and as MCP tools.
3. **Looks**: an unseal, a confirmation and a promotion on a test set each take one (one per key).
4. **The protective limit**: 10.

## Questions for the owner

1. **A trial's config: a file, or only a line in the log?** `run`, `validate`, the catalog and `dataset-unseal` find
   configs in `data/configs/` (`_common.arm_config_files`). The drafts' revision 2 kept a trial only as a line in the
   study's log, to be read back as a config. Proposed: write each trial's config once as a record,
   `data/studies/<goal>/<study_id>/t<k>.yaml`, and have config discovery read `data/studies/*/*/*.yaml` too: every
   command then sees a trial as any config, at the cost of one small file per trial beside the log. The other way:
   teach each command to build a config from a log line.
2. **What a confirmed trial promotes.** Baselines are a goal's on one dataset (RFC-027). Proposed: the trial's run on
   the test set (from the confirmation) is promoted on the test set, its evidence the confirmation (the same look),
   so the goal's baseline on its test set is the confirmed trial; the validation set's baseline is left alone. The
   other way: promote the trial's validation run, with the confirmation attached as its evidence.
