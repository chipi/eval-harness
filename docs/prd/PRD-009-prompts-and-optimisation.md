# PRD-009: Prompt versions, and optimisation studies

- **Status**: Draft (0.5.0), final review round
- **Authors**: Marko Dragoljevic
- **Related UX specs**: [UXS-001](../uxs/UXS-001-catalog.md) (the goal page, to show a study),
  [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) (the commands)
- **Related RFCs**: [RFC-009](../rfc/RFC-009-prompt-versions.md) (prompt versions), [RFC-010](../rfc/RFC-010-studies.md) (studies: types, trials, samplers, the
  statistics); [RFC-004](../rfc/RFC-004-experiment-rounds.md) (rounds)
- **Related PRDs**: [PRD-001](PRD-001-experiments-and-comparison.md) and
  [PRD-005](PRD-005-goals-and-rounds.md) (whose Non-Goals this PRD amends),
  [PRD-010](PRD-010-runners.md), [PRD-013](PRD-013-identity-and-ties.md) (non-inferiority, intervals,
  identifiers, look accounting), [PRD-012](PRD-012-agent-ready.md)

## Summary

Once a project has chosen a model, the next gains come from tuning: the prompt, the decoding
parameters, the pipeline's settings. This PRD does two things. **Prompts get versions**: an arm declares
its prompt files wherever the project keeps them; the harness hashes them into the arm and keeps a
content-addressed history. And the harness gets **optimisation studies**: an optimisation loop in the
spirit of Andrej Karpathy's [autoresearch](https://github.com/karpathy/autoresearch) (a person writes
the direction, the evaluation stays fixed, each try is kept or discarded, everything is logged),
recorded in the terms Optuna and Vizier use, a **study** of **trials**. From the incumbent, a
**sampler** proposes a trial (a new prompt version, a parameter value, a model, a pipeline setting); the
harness runs it on **validation** items and keeps or drops it; every trial is recorded in a round. A
study is driven by the harness (with a built-in grid, one-at-a-time, random or **LLM** sampler) or by
the user's **agent** (which proposes each trial itself). It is **exploratory** (search only, as
autoresearch is: no test items, no evidence, no promotion) or **confirmatory** (the best trial is
checked once against the starting arm on **test** items, with a rule declared before the study, and
the outcome is stated as superior, non-inferior, inconclusive or worse). Promotion stays a person's
decision.

## Background & Context

- **autoresearch** (Karpathy, 2026): an agent reads `program.md` (the person's instructions), edits one
  file (`train.py`), trains for a fixed five minutes, keeps the git commit if validation bits per byte
  improved and resets otherwise, logs `results.tsv` (commit, val_bpb, memory_gb, status, description),
  never stops until interrupted and never asks; `prepare.py` (data and evaluation) is read-only. It has
  no held-out test. This PRD keeps its shape and departs where the harness's purpose requires: studies
  change prompts and settings, not code; the record is the harness's, not git; and a claim that a
  winner is better needs a test check the search never saw.
- The fingerprint records an arm's params, so an inline prompt counts. A prompt kept in a file can be
  hashed today only through the adapter's `fingerprint(params)` hook, where it lands under the system's
  model identity rather than the arm, so `run-compare` cannot name a prompt change as the variable.
- The podcast project keeps 204 Jinja prompts in its pipeline library (`podcast_scraper/prompts/`, laid
  out by provider, task and sometimes model), loaded from one prompt directory the library can be
  pointed at (`set_prompt_dir`); production reads them from the library's source repository. It adapted
  autoresearch twice:
  - an agent following `program_*.md` (10 files): edit only allowed prompt files, user prompt first and
    the system prompt only after the user prompt has plateaued over at least five experiments; score a
    blend of ROUGE-L and two LLM judges; fall back to ROUGE-L alone when more than 40% of episodes have
    contested judgements; keep a change on a relative gain over 1% (and, for prompts shared between two
    tracks, only if the other track drops no more than 1%); commit it; stop after 15 trials or 3 without
    gain; results in TSV files of aggregates; a test set scored once per champion was added later;
  - a greedy one-parameter-at-a-time sweep from `param_space.yaml` (nested parameters such as
    `reduce_params.num_beams`, groups in order each enabled with a reason, `max_candidates`, a base that
    is the previous round's best config), which needs torch.
  Its validation set has 10 episodes and its test set 5.
- This repository's goals nest the validation slice inside the test set (for example 20 of the 200 CNN
  items); `evh holdout` already tests on the items outside the slice.
- Rounds (0.4.0) record a sequence of arms with a hypothesis, retirements with reasons and a conclusion;
  goals weigh quality, cost and speed. A study is a round whose arms come one at a time.
- **Choosing by repeated tests on the same items is adaptive**: Holm corrects a fixed family, not a
  sequence where each test is chosen after seeing the last (Dwork et al., 2015; Cawley and Talbot, 2010).
  With 5 test items the paired difference has no interval and only a one-sided test declared in advance
  can reach 0.05 (1/32, all five favourable). The best trial's validation gain is biased upwards (the
  optimizer's curse, Smith and Winkler, 2006).

## Goals

- A prompt version is identified by its bytes; two arms that differ only by prompt version are provably
  that, and every run says which versions it used, wherever the files live.
- One kind of study serves prompts, parameters, models and pipeline settings; what changes is the
  sampler and the search space.
- A project that wants autoresearch's loop gets it, exploratory and agent-driven, with a complete record.
- A claim that a study's winner is better rests on one check on test items, declared before the study,
  counted, and paid for; searching is labelled search.
- A study's winner cannot drift below where it started through a chain of small concessions
  ("biocreep").
- A study is resumable, budgeted (dollars and time), detachable, and readable afterwards.
- An LLM is involved only when a study asks for one; the harness core never needs one.
- A person and an agent run the same study with the same records ([PRD-012](PRD-012-agent-ready.md)).

## Non-Goals

- **No code as a search space.** Trials change prompts, parameters, models and pipeline settings; they
  never edit the system's code. (autoresearch edits `train.py`; this harness deliberately does not.)
- **No git writes.** The harness reads git (the build) and never commits, branches or resets; a winner
  leaves as files (`prompt-export`, the trial's parameters) for a person to commit.
- The harness does not write prompts itself; its LLM sampler asks a model the study names, with the
  study's key and budget.
- No prompt store the project must move into: prompts stay where the project keeps them.
- No templating engine: a prompt is a file the project renders; the harness hashes and versions its
  bytes.
- A study never promotes. A confirmed winner is suggested for promotion; a person promotes, or an agent
  after asking ([PRD-012](PRD-012-agent-ready.md) FR4.5).
- No Bayesian or evolutionary optimiser of the harness's own; ask/tell admits Optuna's.
- No harness-side scorer: the project's `score` stays the instrument, judges included.

**Amends**: [PRD-001](PRD-001-experiments-and-comparison.md)'s "not a prompt library" and "no automatic
choice of a winner", and [PRD-005](PRD-005-goals-and-rounds.md)'s "no automatic retirement", as
recorded in those PRDs: the harness versions declared prompt files; inside a study, trials are kept or
dropped by the study's declared rule, as search; nothing is promoted automatically.

## Personas

- **The engineer tuning a prompt** after choosing a model.
- **The ML engineer tuning parameters** (decoding, batch size, chunking, map-reduce settings).
- **The agent** given a goal and asked to "push this further", as in autoresearch
  ([PRD-012](PRD-012-agent-ready.md)).

## User Stories

- _As an engineer, my arm declares `summary/system` from my library's prompt directory; the run records
  the file, its version and its hash._
- _As an engineer, I make version 4 of that prompt from version 3 with a note, and see its lineage, the
  runs that used each version and their scores._
- _As an ML engineer, I write a search space (`reduce_params.num_beams` 1..4, then `max_new_tokens`
  256/512/1024) starting from last round's best trial, and run a one-at-a-time study with a $5 and
  two-GPU-hour budget, detached._
- _As an engineer, I run an exploratory study overnight with the built-in LLM sampler, which sees the
  current prompt and the scores and writes the next version; in the morning I read every trial on the
  goal page, then run a confirmation on test items for the best one._
- _As an agent, I drive the study myself, as in autoresearch: I ask for the incumbent and the history,
  propose the next prompt with my hypothesis, and the harness runs, scores, keeps or drops, and records
  it._
- _As a team lead, I see the best trial's validation gain and its test result side by side, that the
  test items had been used three times of their ten, and that the outcome is "superior"; I promote it._
- _As an engineer, I import my past autoresearch logs (`results.tsv`, a parameter space, best-config
  files); the goal page shows them as closed rounds, marked imported and untestable._

## Functional Requirements

### FR1: Prompt versions

- **FR1.1**: An arm declares prompts under `prompts:`, each a name and a file path inside the project or
  an installed library, or a prompt **root** (a directory the system loads prompts from) with the files
  that may change. The adapter receives the prompts' text and, for a root, the path of a per-trial
  overlay directory the harness builds (the root with the trial's files swapped in), so no tracked file
  is ever written and the tree stays clean.
- **FR1.2**: The fingerprint records each prompt under `arm`: name, version and content hash. Changing its
  bytes is a new version; `run-compare` names a prompt change as the variable.
- **FR1.3**: The harness keeps each declared prompt's history in the project: per version, the content,
  parent, note, author (person, agent or sampler, with whom it acted for) and date, named in the grammar
  of [PRD-013](PRD-013-identity-and-ties.md) FR7.
- **FR1.4**: `evh prompt-version` records a new version from a file or text, with its parent and note;
  `evh prompts [<name>]` lists versions and lineage; `evh prompt-diff <a> <b>` shows the change;
  `evh prompt-export <version> --to PATH` writes a version into a working checkout (it refuses a path
  inside an installed package). The catalog gains a prompt page.
- **FR1.5**: `evh validate` checks histories, lineage, and that every run's recorded prompt hash matches
  the version it names.

### FR2: Study types and the spec

- **FR2.1**: A study is a spec file of one of two **types**:
  - **exploratory** (test rule `none`): search only; it never reads test items, counts no look, and its
    outcome is "exploratory: no evidence"; its validation effects are labelled as selected; promotion is
    never suggested. Its metric may be an aggregate (one number per run, as autoresearch's val_bpb), in
    which case trials are kept or dropped by a point rule and are marked untestable.
  - **confirmatory**: as exploratory, plus a test rule declared before it starts (FR4); its outcome is
    evidence.
  A **confirmation** turns an exploratory study's best trial into evidence: a confirmatory check of that
  one trial against its starting arm on test items the search never saw (FR4), counted as one look.
- **FR2.2**: The spec declares:
  - the goal; the **validation** dataset and, for a confirmatory study, the **test** dataset;
  - one or more **tracks** (config, dataset, reference) every trial runs on, the first one deciding and
    the others guarding;
  - the starting arm: a baseline, a run, or a prior study's best trial;
  - the search space: parameters with nested paths, in groups, each enabled with a reason, with a
    move-on rule per group (after N trials without a kept one) and an optional cap on candidates; or the
    prompt names that may change, in order;
  - the sampler (FR3.4), its free-text **directions** (the person's instructions, autoresearch's
    `program.md`), what it may see (scores only, plus outputs, plus inputs; never test items) and
    whether that data may leave the machine;
  - the acceptance rule and the guardrail metrics (metric, direction, limit);
  - the contested-judgement policy: drop the item, drop the trial, or fall back to a named measure;
  - the test rule (FR4), stop rules, budgets, repeats per trial (repeats are averaged per item before any
    paired comparison), the keys per role, and the files that must not change (rubrics, judge configs).
- **FR2.3**: The spec is hashed when the study starts; a change to it, or to any file it freezes, the
  scorer, the references or the judges, stops the study with the reason.
- **FR2.4**: A study's measure may be a declared composite, computed per item from named metrics and
  weights, so it can be tested like any metric ([PRD-005](PRD-005-goals-and-rounds.md) gains the field in
  the goal schema).

### FR3: Running a study

- **FR3.1**: `evh study-run <spec>` opens a round and repeats ask/tell: the sampler proposes a trial with
  its hypothesis and rationale; the harness runs it on every track (through a runner,
  [PRD-010](PRD-010-runners.md), with `--runner`); compares it with the incumbent and with the starting
  arm; keeps or drops it with the reason; until a stop rule fires. Generated arms are stored with the
  study and resolved by `validate` and `run-compare` like configs.
- **FR3.2**: **Acceptance on validation is search, declared and labelled heuristic**, by one of: a point
  rule (the trial's mean beats the incumbent's by at least a stated amount, relative or absolute; zero is
  autoresearch's "improved"), or a test rule (separated as better). In both: no guardrail metric may drop
  beyond its limit **relative to the starting arm** on any track, so guardrail losses cannot accumulate;
  and a trial accepted on a tie-break (cheaper or faster, not better) must be **non-inferior to the
  starting arm** by the goal's declared margin ([PRD-013](PRD-013-identity-and-ties.md) FR3), never only to
  the incumbent. With today's validation sizes that test is usually inconclusive, so tie-break acceptance
  is usually refused: expected, not a fault. Per-trial p values are shown as nominal.
- **FR3.3**: Stop rules: trials, dollars, wall time, GPU time (wall time of `gpu`-labelled jobs between a
  phase's `before` and `after`, [PRD-010](PRD-010-runners.md)), no kept trial in N, the space exhausted,
  or **until interrupted** (autoresearch's "never stop"), always under a hard dollar and time cap.
  Budgets count the system, the judges and the sampler separately; `score` reports the judges' cost.
- **FR3.4**: **Samplers**:
  - built in, with no LLM: grid, one-at-a-time from the incumbent, random;
  - built in, **LLM**: the harness asks a model the spec names, through the provider layer it already has
    for judges (no new dependency), with a prompt that carries the directions, the incumbent, the history
    and, if allowed, the worst outputs; it returns the next trial with its hypothesis (in the manner of
    OPRO and APE); off unless a study names it;
  - **agent-driven**: the user's agent proposes each trial through `study-ask` and `study-tell` (MCP tools
    or CLI commands, [PRD-012](PRD-012-agent-ready.md)); the study waits for it;
  - plug-in: any command speaking ask/tell; an Optuna adapter ships as an example.
- **FR3.5**: **Data egress**: a sampler that would send outputs or inputs to a service outside the machine
  is refused unless the spec allows it for those datasets, and the record says what was sent where.
- **FR3.6**: A study is detachable (it runs as a job set, [PRD-010](PRD-010-runners.md)); `study-status`,
  `study-logs`, `study-stop`; it resumes after an interruption without re-running finished trials;
  `--dry-run` writes and calls nothing (no system, judge or sampler call).

### FR4: The test check (confirmatory studies and confirmations)

- **FR4.1**: The test rule is declared before the study runs: superiority, or non-inferiority by the
  goal's margin, one-sided, at the level of the look it will spend (FR4.4; 1.52% for a test dataset's
  first look, PRD-013 FR9.3). It is never switched afterwards.
- **FR4.2**: The best trial and the starting arm run once on the test items. Any test item also in the
  validation set, or seen by a sampler in an earlier study on the goal, is excluded, and the count used is
  stated; if none remain, the study is refused (FR4.5). Guardrails are tested there too, as non-inferiority
  against the starting arm at their limits, in the same Holm family as the primary measure; with several
  tracks, the first decides and the others are guardrails.
- **FR4.3**: The outcome, with Δ = best − start and α the look's level, is **superior**, **non-inferior**,
  **worse** or **inconclusive**, decided by [RFC-015](../rfc/RFC-015-noninferiority-looks-power.md)'s fixed sequence (non-inferiority first when a margin
  is declared, then superiority) and its tests. A failed guardrail makes the outcome at
  best inconclusive. The effect, its interval and p are shown beside the validation effect of the same
  trial, so the optimizer's curse is visible. Promotion is suggested only on an outcome that meets the
  declared rule.
- **FR4.4**: **Test looks are paid for**, as [PRD-013](PRD-013-identity-and-ties.md) FR9 defines: each test
  item set has a budget of looks; a look is tested at its share of α; when the budget is spent the set
  needs fresh items. Overriding needs the person's consent, never only an agent's
  ([PRD-012](PRD-012-agent-ready.md) FR4.5).
- **FR4.5**: **No confirmatory study without possible evidence**: the dry run and the start state the
  smallest p the test items can reach (PRD-013 FR6) against the look's level, and refuse a study whose
  check could never meet its rule; the person may override, and the outcome is then labelled
  inconclusive. An exploratory study is never refused for this: it makes no claim.
- **FR4.6**: The sampler never sees test items.

### FR5: Records

- **FR5.1**: **A trial**: hypothesis, sampler rationale, the change (a prompt diff or parameter values),
  per track the comparison with the incumbent and the start (n, effect, interval, nominal p), kept,
  dropped, contested or failed with the reason (a crash, timeout or truncation is recorded, never
  skipped), cost per role, wall and GPU time.
- **FR5.2**: **A study**: its type, the directions and the instruction verbatim and who gave them, who ran
  it (person or agent, acting for whom), the spec's hash, the starting arm's provenance, budget used, the
  stop reason, the test check (FR4.3) or "exploratory: no evidence", and a summary: what helped, what hurt,
  what to try next.
- **FR5.3**: `evh study-import` brings past loops in as closed exploratory rounds, marked imported: Karpathy's
  `results.tsv` (commit, val_bpb, memory_gb, status, description), and the podcast project's TSV,
  parameter-space and best-config files; trials with aggregates only are shown as untestable.

## Success Criteria

- autoresearch's loop runs as an exploratory, agent-driven study with a point rule of zero, an aggregate
  metric and "until interrupted" under a cap, and its `results.tsv` imports.
- The podcast project's prompt loop and its parameter sweep can each be written as a study spec: the blend
  as a composite, the shared-prompt guardrail as a second track, the 40%-contested fallback as the judgement
  policy, the user-then-system order as a move-on rule, the nested parameters and the previous round's best
  as the start (to be confirmed with that project; its blend weights differ between its goal and its
  scorer and must be settled first).
- A test confirmatory study on the example project keeps a planted real gain, drops a planted chance gain,
  refuses a test set that cannot reach its rule, excludes overlapping items, stops on budget, resumes, and
  reports superior on a planted gain and non-inferior on a planted cheaper equal arm.
- Two arms differing only in prompt version differ in the fingerprint only in that prompt.

## Related Documents

- [RFC-009](../rfc/RFC-009-prompt-versions.md), [RFC-010](../rfc/RFC-010-studies.md) (); [RFC-004](../rfc/RFC-004-experiment-rounds.md),
  [ADR-0006](../adr/ADR-0006-goal-axes-and-strategies.md).
- References ([INFLUENCES](../INFLUENCES.md)): Karpathy's autoresearch; Optuna (study, trial, ask/tell);
  MLflow Prompt Registry; DSPy optimizers, OPRO, APE; Dwork et al. 2015; Smith and Winkler 2006; Lakens
  2017; Kohavi, Tang and Xu 2020 (guardrail metrics).
