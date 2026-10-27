# RFC-010: Studies: search, trials, samplers, and the confirmation that is evidence

- **Status**: Draft (0.5.0), revision 3 (2026-10-27): one kind of study (search); evidence is always a separate
  confirmation (`study-confirm`); one dollar cap; no data-egress settings. Revision 2: one dev dataset, three samplers
  (grid, a command, the agent), a spec and one append-only event log ([RFC-017](RFC-017-record-store.md))
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-009](../prd/PRD-009-prompts-and-optimisation.md) (FR2 to FR5)
- **Related RFCs**: RFC-009 (prompt versions), RFC-011 (job sets), RFC-015 (verdicts, non-inferiority, heldout looks),
  RFC-013 (commands, actor, consent), RFC-016 (`study-ask`/`study-tell` as tools), RFC-017 (the record store),
  [RFC-004](RFC-004-experiment-rounds.md) (rounds)
- **Code**: new `harness/scripts/_study.py` (the loop, and the state read back from the log), `_samplers/` (`grid.py`,
  `command.py`), commands `study_run.py`, `study_status.py`, `study_ask.py`, `study_tell.py`, `study_confirm.py`,
  `study_import.py`, `view_studies.py`, `study_supervisor.py`; `rounds.py` and `_rounds.py` (a study's round and the
  one-open-round rule); `_common.find_config` (a trial's config); `validate_tree.py` (V5 and studies); `_scoring.py`
  (composites); catalog goal pages; `schemas/study-spec.schema.json`, `study-event.schema.json`,
  `round.schema.json` (`study`), `goal.schema.json` (`composites`); `harness/examples/samplers/optuna_sampler.py`

## Abstract

A study is a search: a spec file and an event log. `evh study-run` opens a round for it and runs an ask/tell loop: a
**sampler** proposes a **trial** (parameter values or prompt versions, with a hypothesis), the harness runs the baseline
config with the trial's changes on the study's dev dataset, compares it with the best so far and the baseline, keeps or
drops it by the spec's declared rule, tells the sampler, and repeats until a stop rule fires. A study's results are
search, never evidence. Evidence is one explicit step afterwards: **`evh study-confirm`** tests the best trial against
the baseline on heldout items the search never saw, with a rule given before those items are looked at, at its look's
level (RFC-015). Samplers are a grid over the space, an external command (Optuna through ask/tell), or the calling
**agent** through `study-ask` and `study-tell`, which is how Karpathy's autoresearch loop runs here. Every step is a
line in the study's log; the catalog and the commands read the study's state from it.

## Problem Statement

PRD-009's loops exist today only as scripts outside the harness (the podcast project's `program_*.md` agents and
`ml_param_tuning/sweep.py`), with results in TSV files the catalog cannot show, acceptance by a fixed 1% on the tuning
items, and no protected heldout check.

## Design

### Files

- **The spec**: `data/studies/<goal>/<study_id>.yaml` (`schemas/study-spec.schema.json`), written by the person or
  the agent: `dev` (the dataset trials run on), `baseline` (`baseline:<goal>/<dataset>@current`, a run, or a trial of
  an earlier study, `trial:<goal>/<study>/<k>`; its config is what trials change), `measure` (a metric or a composite
  of the goal, below), `space` (below), `sampler` (`grid`, `command`, `agent`), `accept` (`point: {min_gain, relative}`
  or `test`), `limits` (`[{metric, direction, limit}]`; the goal's guardrails stay words, never computed), `stop`
  (`trials`, `usd`, `wall_h`, `gpu_h`, `patience`), `repeats`, `frozen` (paths), `directions` (free text),
  `instruction`. With no `trials`, the study runs until stopped, and then `usd` and `wall_h` are required.
- **The log**: `data/studies/<goal>/<study_id>.events.jsonl`, append-only (`schemas/study-event.schema.json`), one
  JSON line per event:
  - `start`: the spec's hash, the frozen files' hashes, the scorer's adapter hash, the references' digest, the judges'
    hashes, the actor and the instruction;
  - `ask` (agent sampler): the `ask_id`;
  - `trial`: k, the change (parameter overrides, prompt versions), hypothesis, rationale, the runs, the verdicts
    against the best so far and the baseline (nominal), the outcome (`kept`, `dropped`, `failed`, `no effect`) with
    its reason, the cost, and the content hashes of the items shown to the sampler;
  - `end`: the stop rule that fired, the summary;
  - `confirm`: a confirmation (below): the trial, the rule, the items used and excluded, the look's number and level,
    the verdict.
  The study's state (running, waiting, stopped; the best so far; the money spent) is read from the log, never stored
  apart. It is the typed form of Karpathy's `results.tsv`: one line per thing that happened.
- **A trial's config** is the baseline's config with the trial's changes, written in its `trial` line, not as a file.
  Its config id is `<study_id>-t<k>`; `_common.find_config` builds it from the log, so `validate`, the catalog and the
  round checks resolve it like any config. To run it, the loop writes it to a temporary file under `.evh/` (ignored by
  git).
- **The round**: `data/rounds/<goal>/<round_id>.yaml` with `study: <study_id>` (`round.schema.json` gains it); its
  `dataset_id` is the study's dev dataset. The round belongs to the study: it opens when the study starts and closes
  when it ends, never by hand. The one-open-round rule (`rounds.py:77-81`) counts only rounds without `study`, so a
  study blocks no other round. Each kept or dropped trial is an arm of the round, dropped trials retired with the
  study's reason, so `evh rounds` and the goal page show the study as they show a round.
- **Duplicates (V5)**: a trial that changes nothing the system reads gives the same per-item results as the best so
  far, which is a finding, not a copied run. V5 reports it as a note ("trial 7 measured the same as trial 4: no
  effect"), not an error.

### The search space

```yaml
space:
  groups:
    - name: decoding
      enabled: true
      reason: "beams and length moved ROUGE in round 2"
      move_on_after: 3              # trials without a kept one
      params:
        reduce_params.num_beams: [1, 2, 3, 4]
        reduce_params.length_penalty: {low: 0.6, high: 1.4, step: 0.2}
    - name: prompts
      prompts: [summary/user, summary/system]    # in order: user first
      move_on_after: 5
  max_candidates: 40
```

Nested parameter paths are dotted; groups are tried in order, one value at a time from the best so far (so the grid
sampler is the podcast project's greedy sweep); `move_on_after` ends a group; `max_candidates` caps the whole study.
Code is never part of the space (PRD-009 Non-Goals).

### Composite measures (PRD-009 FR2.4)

A goal may declare composites, which any study, comparison or goal decision can name like a metric:

```yaml
success_criteria:
  composites:
    - name: summary_blend
      weights: {rouge_l: 0.4, judge_a.score: 0.3, judge_b.score: 0.3}
      direction: higher
```

The harness computes it per item, after scoring, from the row's metrics (`_scoring.composite`), and records it in the
row like any metric, so the paired tests apply. An item missing a component has no composite value and is left out,
counted.

### The loop (`_study.run`)

```text
open the study's round; append start (the hashes); best so far = baseline
while no stop rule fires:
    check the hashes against start (spec, frozen files, scorer, references, judges); a change stops the study
    proposal = sampler.ask(state)            # params and/or prompt texts, hypothesis, rationale
    record new prompt versions (RFC-009, author = the sampler and whom it acts for)
    run the trial's config on the dev dataset, repeats as the spec says (a job set, RFC-011)
    verdicts against the best so far and against the baseline (RFC-015, nominal p)
    decide (below); append the trial line with its outcome and reason
    sampler.tell(trial)
    if kept: best so far = trial
append end; close the round
```

**Deciding a trial.** Repeats are averaged per item first.
- **Point rule**: the trial's mean beats the best so far's by `min_gain` (relative or absolute; 0 is "improved").
- **Test rule**: the trial is separated as better than the best so far.
- In both: every limited metric is no worse than the **baseline** by more than its limit.
- **A tie-break acceptance** (not better, but cheaper or faster) needs the trial to be non-inferior to the **baseline**
  by the goal's margin (RFC-015), so concessions cannot accumulate. With small dev sets this is usually inconclusive
  and refused: expected.
- **Aggregate-only metrics** (one number per run, as autoresearch's val_bpb) allow the point rule only; such trials
  cannot be confirmed.

**Stop rules.** Trials, dollars (the system's and the judges' cost together: the runs' recorded cost, and the
harness's judges' verdict files, `judge_score.stored_cost`, or the reserved metric `judge.cost_usd` a scorer that calls
a judge reports per item), wall time, GPU time (counted from the job sets' phases, RFC-011), and patience (no kept
trial in N).

**Who runs the loop.** `study-run` validates the spec and appends `start`, then starts `python -m
evaluation_harness.study_supervisor <study>` detached, as RFC-011 starts a job set's supervisor (the same `_detach`
helper), prints the study id and returns; `--wait` follows it. The supervisor runs the loop and enforces the stop
rules; `--resume` reads the log and continues after the last finished trial. A study with the agent sampler has no loop
process: every study command first checks `wall_h` and an open ask's age, and appends the lapse when it finds one.

### Samplers (`_samplers/`)

`class Sampler: ask(state) -> Proposal; tell(trial) -> None`. `state` is the best so far, the baseline, the history
(trials with their changes, outcomes and the decisive scores), the space, the money left and the directions; never
heldout items.

- `grid`: the space's groups in order, a value at a time from the best so far (above).
- `command`: an external sampler speaking newline-delimited JSON (`{"ask": state}` → a proposal; `{"tell": trial}` →
  `{}`) over stdio, as RFC-008's framing; the Optuna example wraps `optuna.Study.ask/tell` this way, and any other
  optimiser (an LLM of the project's choosing included) can be plugged in the same way. What it sends where is the
  project's code and the project's decision.
- `agent`: no sampler process. A spec with `sampler: agent` makes `study-run` open the study and return. The agent calls
  `evh study-ask <study>`, which prints the state as JSON with an `ask_id` and appends the ask, then
  `evh study-tell <study> --ask <ask_id> --proposal FILE`, which runs the trial and returns its outcome, or the trial's
  job set id when it runs long.
  - One ask is open at a time. A tell with an unknown, used or lapsed `ask_id` is refused (`ask-closed`), so two agents
    can never tell the same ask.
  - `study-ask` while a trial is still running answers with the running trial and its job set id and opens no ask
    (code `trial-running`, exit 75: try again later).
  - An ask left open past `stop.ask_timeout_h` (default 2) lapses; the study ends at `stop.wall_h`.

Every item shown to a sampler is recorded in its trial line (`shown`), so confirmations exclude it.

### The confirmation (`study-confirm`)

`evh study-confirm <study> --heldout <dataset> --rule superiority|noninferiority [--trial k] [--dry-run]` turns a
study's best trial (or trial k) into evidence. The rule is given on the command line, before the heldout items are
looked at, so it is fixed before any result it judges exists.

1. **Possible evidence**: the smallest attainable p on the heldout items is compared with the next look's level
   (RFC-015); a confirmation that could never meet its rule is refused (`no-possible-evidence`), unless the person
   overrides (consent of kind `override_refusal`, RFC-013), and the outcome is then labelled inconclusive.
   `--dry-run` prints this and the cost, and runs nothing.
2. **The heldout items**: the heldout dataset's items minus any in the dev dataset (by content hash) and minus any item
   shown to a sampler in any study on the goal (the `shown` hashes of their trial lines); the count is recorded; none
   left refuses (`no-heldout-items`). An imported study has no record of what its loop showed, so the items of the
   dataset it names are excluded too; an imported study that names none adds a caveat to every later confirmation on
   the goal ("study X was imported; what it showed is unknown").
3. **The look**: its number is one more than the decisions already recorded on the heldout dataset, and its level
   follows (RFC-015); past the protective limit it needs the person's consent (kind `extra_look`).
4. **Run** the trial and the baseline once on those items (a job set; repeats as the spec says).
5. **The verdict**: RFC-015's fixed sequence at the look's level, for the given rule; the limits as non-inferiority
   against the baseline in the same Holm family; a failed limit caps the outcome at inconclusive.
6. **Record** a `confirm` line in the study's log, the outcome beside the trial's dev effect; suggest promotion only
   on an outcome that meets the rule (`evh run-promote …` as the suggestion, never run). Promoting that trial against
   the same baseline reuses this look (RFC-012).

### Commands

`study-run <spec> [--runner R] [--wait] [--dry-run] [--resume <id>]`, `study-status`, `study-logs`, `study-stop`,
`study-ask`, `study-tell`, `study-confirm`, `studies [--goal G]`, `study-import`, each with `--json`. A study is named as
`study:<goal>/<study_id>`, or by its bare id when only one goal has a study by that name. `study-run --dry-run` writes
and calls nothing: it prints the plan (the largest number of trials, the items per trial, the estimated cost), and
calls neither the system, the judges nor the sampler.

### Importing past loops (`study-import`)

**Karpathy's `results.tsv`** (`commit, val_bpb, memory_gb, status, description`): one closed study; each row a trial
with the aggregate metric, `status` keep/discard/crash mapped to kept/dropped/failed, `description` as the hypothesis;
marked imported, and its trials cannot be confirmed. Other formats (the podcast project's TSVs, which differ from
directory to directory) are converted to this one by a short script in the project that has them.

### The catalog

The goal page's round section shows a study's trials as a table (k, change, hypothesis, outcome, the decisive score
against the best so far, cost), the stop reason, its confirmations with their looks, and the summary; each trial links
its runs and its prompt diff. Every view has its command.

## Deferred (after 0.5.0)

Several datasets per study (tracks), a built-in LLM sampler (the agent sampler covers the case, and a project can plug
one in as a command), contested-judgement policies (dropping or falling back when judges disagree on too many items),
imports through a column map, budgets per role, and settings for what a sampler may see and send out. Each is
additive: the spec and the log gain fields, nothing changes shape.

## Migration

None. A project's old loops can be brought in with `study-import`.

## Alternatives Considered

- **Let the study promote its winner.** Rejected (owner's decision): promotion stays a person's, or an agent's after
  asking.
- **Accept by "a gain over 1%" alone.** Kept only as a declared point rule labelled heuristic, never as evidence.
- **An optimiser of the harness's own (Bayesian, evolutionary).** Rejected: ask/tell lets Optuna's samplers plug in.
- **The agent edits files and the harness snapshots them.** Rejected: the agent proposes prompt text through
  `study-tell`; the harness writes versions; no tracked file is edited, and no code (PRD-009 Non-Goals).
- **Two kinds of study, exploratory and confirmatory** (revisions 1 and 2), the confirmatory one ending in its own
  heldout check. Rejected in revision 3: a confirmation after any study gives the same evidence with the rule still
  fixed before the heldout items are seen, and one kind of study is simpler to read and to run.
- **A directory of trial files and generated configs** (revision 1). Rejected in revision 2: one log per study is what
  a person reads, merges cleanly, and holds the same information.

## Testing

- `harness/tests/test_study.py` (fake adapter): a planted real gain is kept and confirmed separated: better; a planted
  chance gain on a tiny dev set is dropped or fails its confirmation; a cheaper equal arm is non-inferior to the
  baseline; a chain of small concessions cannot pass the baseline's margin; overlapping and sampler-seen heldout items
  are excluded; a spec or scorer change mid-study stops it; the dollar cap stops it; resume continues from the log
  without re-running trials; the state read from the log matches what happened; `--dry-run` calls nothing; a
  confirmation with no possible evidence is refused.
- `harness/tests/test_samplers.py`: grid with groups and move-on rules; the command sampler protocol; the agent ask/tell
  flow (a second tell of one ask refused, `trial-running`, a lapsed ask).
- `harness/tests/test_study_import.py`: Karpathy's `results.tsv` imports as a closed study whose trials cannot be
  confirmed.
- Rounds: a study's round does not block a plain round; a trial's config resolves from the log; V5 notes a no-effect
  trial. Composites: computed per item, a missing component leaves the item out.

## Decisions (ADR candidates)

1. A study is a search driven by an ask/tell loop; keeping a trial is search, a confirmation on heldout items is the only
   evidence, and a study never promotes.
2. Samplers are pluggable through one ask/tell interface: a grid, a command, or the calling agent; code is never in the
   search space.
3. Limits and tie-break acceptance are judged against the baseline, so concessions cannot accumulate.
4. Items shown to a sampler and items in the dev set are excluded from a confirmation.
5. A study is a spec and one append-only event log; its state and its trials' configs are read from the log.
6. The loop runs in a detached study supervisor; the agent sampler is driven by `study-ask`/`study-tell` with an ask id.
