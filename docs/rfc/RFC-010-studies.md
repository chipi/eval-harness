# RFC-010: Studies: exploratory and confirmatory, trials, samplers, the test check

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-009](../prd/PRD-009-prompts-and-optimisation.md) (FR2 to FR5)
- **Related RFCs**: RFC-009 (prompt versions), RFC-011 (job sets), RFC-015 (verdicts, non-inferiority, test looks),
  RFC-013 (commands, actor, consent), RFC-016 (`study-ask`/`study-tell` as tools), [RFC-004](RFC-004-experiment-rounds.md)
  (rounds)
- **Code**: new `harness/scripts/_study.py` (the loop), `_samplers/` (`grid.py`, `one_at_a_time.py`, `random_.py`,
  `llm.py`, `command.py`), commands `study_run.py`, `study_status.py`, `study_ask.py`, `study_tell.py`,
  `study_import.py`, `view_studies.py`, `study_supervisor.py`; `rounds.py` and `_rounds.py` (a study's round: the
  one-open-round rule, tracks); `_providers.py` (the `sampler` role); `experiment_run.py` and `_common` (a config's
  `reference:`); `validate_tree.py` (V5 and studies); `_scoring.py` (composites); catalog goal pages;
  `schemas/study-spec.schema.json`, `study.schema.json`, `trial.schema.json`, `round.schema.json` (`study`, `tracks`),
  `goal.schema.json` (`composites`), `config.schema.json` (`reference`); `harness/examples/samplers/optuna_sampler.py`

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
  `start` (`champion:<goal>/<dataset>@current`, a run, or a trial of an earlier study, `trial:<goal>/<study>/<k>`),
  `measure` (a metric or a composite of the goal, below), `space` (below), `sampler` (below), `accept`
  (`point: {min_gain, relative}` or `test`), `guardrails` (`[{metric, direction, limit}]`), `contested` (`{policy:
  drop_item|drop_trial|fallback, metric: <fallback metric>, when_share_over: 0.4}`), `test_rule`
  (`superiority|noninferiority|none`), `stop`
  (`trials`, `usd`, `wall_h`, `gpu_h`, `patience`, `until_interrupted`), `budgets` (per role: `system`, `judge`,
  `sampler`), `repeats`, `keys` (env names per role), `frozen` (paths), `directions` (free text), `instruction`.
- **Records**: `data/studies/<goal>/<study_id>/`: `spec.lock.json` (the spec as run, its hash, the frozen files' hashes,
  the scorer's adapter hash, the references' digest, the judges' hashes), `study.json` (state, incumbent, budget used
  per role, stop reason, test check, summary, actor, instruction), `trials/<k>.json` (`schemas/trial.schema.json`:
  PRD-009 FR5.1's fields), `trials/<k>/<track>.config.yaml` (one generated config per track, and `test.config.yaml`
  for the test check: the starting config with the trial's parameter overrides and prompt versions, the track's
  `dataset_id` and its `reference`; config id `<study_id>-t<k>-<track>`). `_common.find_config` looks in
  `data/studies/*/*/trials/` after `data/configs/`, so `validate`, the catalog, the round checks and the commands that
  take a config id resolve them like any config; `run-compare` compares their runs as usual.
- **A config's reference**: a config may name its reference (`reference: gold/<dataset>` or `silver/<id>`); without one,
  `experiment-run` picks gold, then silver, as today (`experiment_run.py:189-199`). Tracks and the test check use it, so
  no command-line override is needed.
- **Shown items**: `data/studies/<goal>/shown.jsonl`, append-only, one line per item content hash shown to a sampler
  (with the study and trial), written before the sampler is called.
- **The round**: `data/rounds/<goal>/<round_id>.yaml` with `study: <study_id>` and `tracks: [{dataset_id, reference}]`
  (`round.schema.json` gains both); its `dataset_id` is the decisive track's. The round belongs to the study: it opens
  when the study starts and closes when it ends, never by hand. The one-open-round rule (`rounds.py:77-81`) counts only
  rounds without `study`, so a study blocks no other round, and several studies may run on a goal at once (their test
  looks share the test dataset's budget, RFC-015). The config-to-round check (`_rounds.py:150-155`) accepts, for a study's
  round, a config on any of its tracks' datasets. Each kept or dropped trial is an arm of the round, dropped trials
  retired with the study's reason, so `evh rounds` and the goal page show the study as they show a round.
- **Duplicates (V5)**: a trial that changes nothing the system reads gives the same per-item results as its
  incumbent, which is a finding, not a copied run. V5 reports two runs of trials of one study with different configs as
  a note ("trial 7 measured the same as trial 4: no effect"), not an error, and the trial records `no_effect: true`.

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
counted. The podcast project's "ROUGE-L alone when more than 40% of episodes have contested judgements" is the study's
`contested: {policy: fallback, metric: rouge_l, when_share_over: 0.4}`: when the share of contested items in a trial
passes the threshold, the trial is decided on the fallback metric, and the trial records that it was.

### The loop (`_study.run`)

```text
open the study's round; lock the spec (spec.lock.json); incumbent = start
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

**Budgets and stop rules.** System cost from the runs; judge cost from the harness's judges' verdict files
(`judge_score.stored_cost`) and, for a scorer that calls a judge itself, the reserved metric `judge.cost_usd` it reports
per item (`judge` is a reserved name, never a stage: RFC-007); sampler cost from its calls. `until_interrupted` runs
until `study-stop` or a cap, and always needs a dollar and a time cap. GPU time is counted from the job sets' phases
(RFC-011).

**Who runs the loop.** `study-run` validates and locks the spec, then starts `python -m
evaluation_harness.study_supervisor <study>` detached, as RFC-011 starts a job set's supervisor (the same `_detach`
helper: a new session, stdin from `/dev/null`, output to the study's log, descriptors closed), prints the study id and
returns; `--wait` follows it. The study supervisor runs the loop, starts each trial's job set and waits on it, enforces
`wall_h` and the budgets, and writes `study.json` after every step, so `--resume` continues from the last finished
trial. A study with the agent sampler has no loop process: every study command first checks `wall_h` and an open ask's
age, and closes a lapsed study or ask with the time it lapsed.

### Samplers (`_samplers/`)

`class Sampler: ask(state) -> Proposal; tell(trial) -> None`. `state` is the incumbent, the start, the history (trials
with their changes, outcomes and the decisive scores), the space, the budget left and the directions; never test items.

- `grid`, `one_at_a_time` (from the incumbent, a parameter at a time, groups in order), `random` (seeded by the spec's
  hash).
- `llm`: a model named in the spec (`sampler: {kind: llm, provider: anthropic, model: …}`) through the provider layer
  the judges use. `_providers.ROLES` gains `sampler` (`_providers.py:41`), so its key is read from the `EVAL_SAMPLER_`
  prefix (`EVAL_SAMPLER_ANTHROPIC_API_KEY`), as the judge's is from `EVAL_JUDGE_` (ADR-0005). The provider call gains a
  system message and a JSON response mode where the provider has one (and a parse of the text where it has not). Its
  prompt (in the package, hashed into `spec.lock.json`) carries the directions, the current prompt or parameters, the
  history and, when `sees` allows, the worst outputs; it must answer JSON `{hypothesis, rationale, change: {prompts:
  {name: text}} | {params: {path: value}}}`. A malformed answer is a failed trial, recorded; three in a row stop the
  study.
- `command`: an external sampler speaking newline-delimited JSON (`{"ask": state}` → a proposal; `{"tell": trial}` → `{}`)
  over stdio, as RFC-008's framing; the Optuna example wraps `optuna.Study.ask/tell` this way.
- `agent`: no sampler process. A spec with `sampler: {kind: agent}` makes `study-run` open the study and return. The
  agent calls `evh study-ask <study>`, which prints the state as JSON with an `ask_id` and opens one ask, then
  `evh study-tell <study> --ask <ask_id> --proposal FILE`, which records and runs the trial and returns its outcome, or
  the trial's job set id when it runs long.
  - One ask is open at a time. A tell with an unknown, used or lapsed `ask_id` is refused (`ask-closed`), so two agents
    can never tell the same ask.
  - `study-ask` while a trial is still running answers with the running trial and its job set id and opens no ask
    (code `trial-running`, exit 75: try again later).
  - An ask left open past `stop.ask_timeout_h` (default 2) lapses; the study ends at `stop.wall_h`.

**Data egress** (PRD-009 FR3.5): a sampler is remote unless its endpoint is local (a localhost or tailnet address the
config marks local); a remote sampler that `sees` outputs or inputs needs `allow_egress: [<dataset>, …]` in the spec and
consent (RFC-013/016); each trial records what was sent where. Items shown to a sampler are appended to the goal's
`shown.jsonl` before the call, so a later study's test check can exclude them.

### The test check (confirmatory)

1. The test items: the test dataset's items minus any in the validation dataset (by content hash) and minus any in the
   goal's `shown.jsonl`; the count is recorded; none left refuses the check (`no-test-items`). An imported study has no
   record of what its loop showed, so the items of the datasets it names are excluded too; an imported study that names
   no dataset adds a caveat to every later test check on the goal ("study X was imported; what it showed is unknown").
2. The look: `_looks.reserve(test dataset, key)` (RFC-015) creates the look exclusively before anything runs and
   returns its level; past the protective limit it needs the person's consent (kind `extra_look`). A check that dies
   after this leaves the look reserved and spent.
3. Run the best trial and the start once on those items (a job set; repeats as the spec says).
4. The verdict: RFC-015's fixed sequence at the look's level, for the declared `test_rule`; guardrails as non-inferiority
   against the start in the same Holm family; a failed guardrail caps the outcome at inconclusive.
5. Write the verdict into the reserved look; write the outcome beside the trial's validation effect; suggest promotion
   only on an outcome that meets the rule (`evh run-promote …` as the suggestion, never run). Promoting that trial
   against the same champion reuses this look (RFC-012).

**A confirmation** (PRD-009 FR2.1) turns an exploratory study's best trial into evidence after the fact:
`evh study-confirm <study> --test <dataset> --rule superiority|noninferiority [--trial k]` runs the same five steps on
a closed exploratory study (its best trial, or trial k, against its start), recorded in the study as its test check
and labelled a confirmation. The rule is given on the command line before anything runs, and the study's search had
no access to those items (the shown items and the validation dataset are excluded, as above).

**No study without possible evidence**: before the first trial, a confirmatory study computes the smallest attainable p on
its test items and the look's level (RFC-015) and refuses (`no-possible-evidence`) when the rule can never be met; the
person may override (consent of kind `override_refusal`, RFC-013), and the outcome is then labelled inconclusive. For a
continuous measure under non-inferiority the check is by power (RFC-015) and runs again before the test look.

### Commands

`study-run <spec> [--runner R] [--wait] [--dry-run] [--resume <id>]`, `study-status`, `study-logs`, `study-stop`,
`study-ask`, `study-tell`, `study-confirm`, `studies [--goal G]`, `study-import`, each with `--json`. A study is named as
`study:<goal>/<study_id>`, or by its bare id when only one goal has a study by that name. `--dry-run` writes and calls nothing:
it prints the plan (the largest number of trials, the items per trial, the estimated cost per role, the attainable p and
the look's level), and calls neither the system, the judges nor the sampler.

### Importing past loops (`study-import`)

- **Karpathy's `results.tsv`** (`commit, val_bpb, memory_gb, status, description`): one closed exploratory study; each row
  a trial with the aggregate metric, `status` keep/discard/crash mapped to kept/dropped/failed, `description` as the
  hypothesis; marked imported and untestable.
- **Any other TSV** through a column map, since every loop wrote its own shape (the podcast project's files differ by
  directory: `experiment_id, score, delta, status, notes, …` with `baseline/kept/kept-CHAMPION`, and
  `date, variant, variant_sha256, pass, …` with per-count columns). `evh study-import FILE --map MAP.yaml`:

  ```yaml
  trial: experiment_id            # the column naming the trial
  metrics: {score: score}         # harness metric <- column; non-numeric cells ("—") are empty
  hypothesis: notes
  status: {baseline: start, kept: kept, kept-CHAMPION: kept, discard: dropped, crash: failed}
  dataset: dataset_ref            # optional
  code_ref: commit_sha            # optional
  ```

  A status not in the map refuses the import with the line, so nothing is guessed.
- `--space FILE` and `--best FILE` attach a space and a best config when they are in the harness's formats (a space as
  above, a config). The podcast project's `param_space.yaml` (keyed by model pair, with `candidates` and `enabled`) is
  converted by a short script in that project; the harness reads its own formats only.

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
- `harness/tests/test_study_import.py`: Karpathy's `results.tsv`, and both podcast TSV shapes through their maps, import
  as closed, untestable exploratory studies; an unmapped status is refused.
- Rounds: a study's round does not block a plain round; two studies on one goal run at once and share the look budget;
  a track's config with its own dataset and reference is accepted by the round check; V5 notes a no-effect trial.
- Agent ask/tell: a second tell of one ask is refused; an ask during a running trial answers `trial-running`; a lapsed
  ask is closed by the next command.
- Composites: computed per item, a missing component leaves the item out; the contested fallback switches a trial to the
  fallback metric past the threshold.

## Decisions (ADR candidates)

1. Studies are rounds driven by an ask/tell loop, exploratory or confirmatory; keeping a trial is search, the single
   counted test check is evidence, and a study never promotes.
2. Samplers are pluggable through one ask/tell interface: built-in (including an LLM through the existing providers), a
   command, or the calling agent; code is never in the search space.
3. Guardrails and tie-break acceptance are judged against the starting arm, so concessions cannot accumulate.
4. Items shown to a sampler and items in the validation set are excluded from the test check.
5. A study owns its round, which does not count against the one-open-round rule; trials are generated configs per track,
   each naming its dataset and reference.
6. The loop runs in a detached study supervisor; the agent sampler is driven by `study-ask`/`study-tell` with an ask id.
