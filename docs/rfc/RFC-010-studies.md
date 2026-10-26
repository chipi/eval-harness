# RFC-010: Studies: exploratory and confirmatory, trials, samplers, the test check

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-009](../prd/PRD-009-prompts-and-optimisation.md) (FR2 to FR5)
- **Related RFCs**: RFC-009 (prompt versions), RFC-011 (job sets), RFC-015 (verdicts, non-inferiority, test looks),
  RFC-013 (commands, actor, consent), RFC-016 (`study-ask`/`study-tell` as tools), [RFC-004](RFC-004-experiment-rounds.md)
  (rounds)
- **Code**: new `harness/scripts/_study.py` (the loop), `_samplers/` (`grid.py`, `one_at_a_time.py`, `random_.py`,
  `llm.py`, `command.py`), commands `study_run.py`, `study_status.py`, `study_ask.py`, `study_tell.py`,
  `study_import.py`, `view_studies.py`; `rounds.py` (a round may belong to a study); catalog goal pages;
  `schemas/study-spec.schema.json`, `study.schema.json`, `trial.schema.json`; `harness/examples/samplers/optuna_sampler.py`

## Abstract

A study is a spec file and a directory of records. `evh study-run` opens a round for it and runs an ask/tell loop: a
**sampler** proposes a **trial** (parameter values or prompt versions, with a hypothesis), the harness builds the trial's
config, runs it on every **track** as a job set, compares it with the incumbent and the starting arm, keeps or drops it
by the spec's declared rule, tells the sampler, and repeats until a stop rule fires. An **exploratory** study ends there
("no evidence"); a **confirmatory** one then runs its single **test check**: the best trial against the start on test
items the search never saw, at its look's level (RFC-015). Samplers are built in (grid, one at a time, random, an LLM),
an external command, or the calling **agent** through `study-ask` and `study-tell`, which is how Karpathy's autoresearch
loop runs here. Every trial and the study itself are records the catalog shows.

## Problem Statement

PRD-009's loops exist today only as scripts outside the harness (the podcast project's `program_*.md` agents and
`ml_param_tuning/sweep.py`), with results in TSV files the catalog cannot show, acceptance by a fixed 1% on the tuning
items, and no protected test check.

## Design

### Files

- **The spec**: `data/studies/<goal>/<study_id>.yaml` (`schemas/study-spec.schema.json`), PRD-009 FR2.2's fields:
  `type: exploratory|confirmatory`, `validation`, `test`, `tracks` (config, dataset, reference; the first decides),
  `start` (`champion:<goal>/<dataset>@current`, a run, or `study:<goal>/<id>@best`), `space` (below), `sampler`
  (below), `accept` (`point: {min_gain, relative}` or `test`), `guardrails` (`[{metric, direction, limit}]`),
  `contested` (`drop_item|drop_trial|fallback: <metric>`), `test_rule` (`superiority|noninferiority|none`), `stop`
  (`trials`, `usd`, `wall_h`, `gpu_h`, `patience`, `until_interrupted`), `budgets` (per role: `system`, `judge`,
  `sampler`), `repeats`, `keys` (env names per role), `frozen` (paths), `directions` (free text), `instruction`.
- **Records**: `data/studies/<goal>/<study_id>/`: `spec.lock.json` (the spec as run, its hash, the frozen files' hashes,
  the scorer's adapter hash, the references' digest, the judges' hashes), `study.json` (state, incumbent, budget used
  per role, stop reason, test check, summary, actor, instruction), `trials/<k>.json` (`schemas/trial.schema.json`:
  PRD-009 FR5.1's fields), `trials/<k>.config.yaml` (the generated config: the starting config with the trial's
  parameter overrides and prompt versions; config id `<study_id>-t<k>`; `validate` and `run-compare` resolve it like a
  config in `data/configs/`).
- **The round**: `data/rounds/<goal>/<round_id>.yaml` with `study: <study_id>`; each kept or dropped trial is an arm of
  the round, dropped trials retired with the study's reason, so `evh rounds` and the goal page show the study as they
  show a round.

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

Nested parameter paths are dotted; a group is tried in order; `move_on_after` ends a group; `max_candidates` caps the
whole study. Code is never part of the space (PRD-009 Non-Goals).

### The loop (`_study.run`)

```text
open round; lock the spec (spec.lock.json); incumbent = start
while no stop rule fires:
    verify the lock (spec, frozen files, scorer, references, judges); a change stops the study
    proposal = sampler.ask(state)            # params and/or prompt texts, hypothesis, rationale
    record new prompt versions (RFC-009, author = the sampler and whom it acts for)
    write trials/<k>.config.yaml and trials/<k>.json (state: proposed)
    run it: a job set of the tracks × repeats on the validation dataset (RFC-011)
    per track: verdicts against the incumbent and against the start (RFC-015, nominal p)
    decide (below); record kept / dropped / contested / failed with the reason
    sampler.tell(trial)
    if kept: incumbent = trial
if confirmatory: the test check (below)
write the summary and close the round
```

**Deciding a trial.** Repeats are averaged per item first.
- **Point rule**: the decisive track's mean beats the incumbent's by `min_gain` (relative or absolute; 0 is "improved").
- **Test rule**: the trial is separated as better than the incumbent on the decisive track.
- In both: every guardrail metric, on every track, is no worse than the **start** by more than its limit.
- **A tie-break acceptance** (not better, but cheaper or faster) needs the trial to be non-inferior to the **start** by the
  goal's margin (RFC-015), so concessions cannot accumulate. With small validation sets this is usually inconclusive and
  refused: expected.
- **Contested judgements** follow the spec's policy, by the scorer's per-item `contested` flag (a 0/1 metric).
- **Aggregate-only metrics** (one number per run, as autoresearch's val_bpb), in exploratory studies only, allow the point
  rule only; such trials are marked untestable.

**Budgets and stop rules.** System cost from the runs; judge cost from the scorer's `judge.cost_usd` per item (a metric
the scorer reports); sampler cost from its calls. `until_interrupted` runs until `study-stop` or a cap, and always needs a
dollar and a time cap. GPU time is counted from the job sets' phases (RFC-011).

### Samplers (`_samplers/`)

`class Sampler: ask(state) -> Proposal; tell(trial) -> None`. `state` is the incumbent, the start, the history (trials
with their changes, outcomes and the decisive scores), the space, the budget left and the directions; never test items.

- `grid`, `one_at_a_time` (from the incumbent, a parameter at a time, groups in order), `random` (seeded by the spec's
  hash).
- `llm`: a model named in the spec (`sampler: {kind: llm, provider: anthropic, model: …, key: EVAL_SAMPLER_ANTHROPIC_API_KEY}`)
  through the provider layer the judges use. Its prompt (in the package, hashed into `spec.lock.json`) carries the
  directions, the current prompt or parameters, the history and, when `sees` allows, the worst outputs; it must answer
  JSON `{hypothesis, rationale, change: {prompts: {name: text}} | {params: {path: value}}}`. A malformed answer is a
  failed trial, recorded; three in a row stop the study.
- `command`: an external sampler speaking newline-delimited JSON (`{"ask": state}` → a proposal; `{"tell": trial}` → `{}`)
  over stdio, as RFC-008's framing; the Optuna example wraps `optuna.Study.ask/tell` this way.
- `agent`: no sampler process. `study-run --sampler agent` opens the study and returns; the agent calls
  `evh study-ask <study>` (prints the state as JSON, opens one ask) and `evh study-tell <study> --proposal FILE` (records
  and runs the trial, returns its outcome, or a job id when it runs long). One ask is open at a time; an ask left open past
  `stop.wall_h` lapses.

**Data egress** (PRD-009 FR3.5): a sampler is remote unless its endpoint is local (a localhost or tailnet address the
config marks local); a remote sampler that `sees` outputs or inputs needs `allow_egress: [<dataset>, …]` in the spec and
consent (RFC-013/016); each trial records what was sent where. Items shown to a sampler are recorded per study, so a later
study's test check can exclude them.

### The test check (confirmatory)

1. The test items: the test dataset's items minus any in the validation dataset (by content hash) and minus any shown to a
   sampler in a study on the goal; the count is recorded; none left refuses the check (`no-test-items`).
2. The look: `_looks.next_level(item set)` (RFC-015); a spent budget needs the person's consent.
3. Run the best trial and the start once on those items (a job set; repeats as the spec says).
4. The verdict: RFC-015's fixed sequence at the look's level, for the declared `test_rule`; guardrails as non-inferiority
   against the start in the same Holm family; a failed guardrail caps the outcome at inconclusive.
5. Record the look; write the outcome beside the trial's validation effect; suggest promotion only on an outcome that meets
   the rule (`evh run-promote …` as the suggestion, never run).

**No study without possible evidence**: before the first trial, a confirmatory study computes the smallest attainable p on
its test items and the look's level (RFC-015) and refuses (`no-possible-evidence`) when the rule can never be met; the
person may override (`--confirm`), and the outcome is then labelled inconclusive.

### Commands

`study-run <spec> [--runner R] [--detach] [--dry-run] [--resume <id>]`, `study-status`, `study-logs`, `study-stop`,
`study-ask`, `study-tell`, `studies [--goal G]`, `study-import`, each with `--json`. `--dry-run` writes and calls nothing:
it prints the plan (the largest number of trials, the items per trial, the estimated cost per role, the attainable p and
the look's level), and calls neither the system, the judges nor the sampler.

### Importing past loops (`study-import`)

- **Karpathy's `results.tsv`** (`commit, val_bpb, memory_gb, status, description`): one closed exploratory study; each row
  a trial with the aggregate metric, `status` keep/discard/crash mapped to kept/dropped/failed, `description` as the
  hypothesis; marked imported and untestable.
- The podcast project's `results_*.tsv`, `param_space.yaml` and `*_best_config.yaml`: the same, with the space and the
  best config as the study's start and incumbent.

### The catalog

The goal page's round section shows a study's trials as a table (k, change, hypothesis, outcome, the decisive score
against the incumbent, cost), the stop reason, the test check with its look count, and the summary; each trial links its
generated config, its runs and its prompt diff. Every view has its command.

## Migration

None. A project's old loops can be brought in with `study-import`.

## Alternatives Considered

- **Let the study promote its winner.** Rejected (owner's decision): promotion stays a person's, or an agent's after
  asking.
- **Accept by "a gain over 1%" alone.** Kept only as a declared point rule labelled heuristic, never as evidence.
- **An optimiser of the harness's own (Bayesian, evolutionary).** Rejected: ask/tell lets Optuna's samplers plug in.
- **The agent edits files and the harness snapshots them.** Rejected: the agent proposes prompt text through
  `study-tell`; the harness writes versions; no tracked file is edited, and no code (PRD-009 Non-Goals).

## Testing

- `harness/tests/test_study.py` (fake adapter, fake provider): a planted real gain is kept and confirmed superior; a planted
  chance gain on a tiny validation set is dropped or fails the test check; a cheaper equal arm is non-inferior to the
  start; a chain of small concessions cannot pass the start's margin; overlapping and sampler-seen test items are excluded;
  a spec or scorer change mid-study stops it; budgets per role stop it; resume continues without re-running trials;
  `--dry-run` calls nothing (asserted by a provider that fails if called); a study with no possible evidence is refused.
- `harness/tests/test_samplers.py`: grid, one-at-a-time with groups and move-on rules, random seeded; the LLM sampler's
  JSON contract and failure handling; the command sampler protocol; the agent ask/tell flow.
- `harness/tests/test_study_import.py`: Karpathy's `results.tsv` and the podcast formats import as closed, untestable
  exploratory studies.

## Decisions (ADR candidates)

1. Studies are rounds driven by an ask/tell loop, exploratory or confirmatory; keeping a trial is search, the single
   counted test check is evidence, and a study never promotes.
2. Samplers are pluggable through one ask/tell interface: built-in (including an LLM through the existing providers), a
   command, or the calling agent; code is never in the search space.
3. Guardrails and tie-break acceptance are judged against the starting arm, so concessions cannot accumulate.
4. Items shown to a sampler and items in the validation set are excluded from the test check.
