# PRD-009: Prompt versions, and an optimisation loop

- **Status**: Draft (0.5.0), round 2
- **Authors**: Marko Dragoljevic
- **Related UX specs**: [UXS-001](../uxs/UXS-001-catalog.md) (the goal page, to show a study),
  [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) (the commands)
- **Related RFCs**: RFC-009 (prompt versions), RFC-010 (the study: trials, samplers, the
  statistics), both to be written; [RFC-004](../rfc/RFC-004-experiment-rounds.md) (rounds)
- **Related PRDs**: [PRD-001](PRD-001-experiments-and-comparison.md) and
  [PRD-005](PRD-005-goals-and-rounds.md) (whose Non-Goals this PRD amends),
  [PRD-010](PRD-010-runners.md), [PRD-013](PRD-013-identity-and-ties.md) (ties as equivalence),
  [PRD-012](PRD-012-agent-ready.md)

## Summary

Once a project has chosen a model, the next gains come from tuning: the prompt, the decoding
parameters, the pipeline's settings. This PRD does two things. **Prompts get versions**: an arm
declares its prompt files wherever the project keeps them, the harness hashes them into the arm
and keeps a content-addressed history (`summary/3` is a fixed version, `summary@champion` a moving
pointer, as in MLflow's registries) with each version's parent, note and author. And the harness
gets an **optimisation loop**, recorded as a **study** of **trials** (the terms Optuna and Vizier use) that is not specific to prompts:
from the incumbent, a **sampler** proposes a **trial** (a new prompt version, a parameter value, a
model), the harness runs it on the **validation** items and keeps or drops it, records every trial
as part of a round, stops on a budget, and checks the best trial **once** on **test** items it was
never tuned on. Samplers use ask/tell, so grid, one-at-a-time and random ship built in and Optuna,
DSPy or an LLM that rewrites prompts plug in. Keeping or dropping a trial is search, not proof:
the single test check is the evidence, and promotion stays a person's decision.

## Background & Context

- The fingerprint records an arm's params, so an inline prompt counts. A prompt kept in a file can
  be hashed today only through the adapter's `fingerprint(params)` hook, where it lands under the
  system's model identity rather than the arm, so `run-compare` cannot name a prompt change as the
  variable that moved.
- The podcast project keeps 204 Jinja prompts in its pipeline library
  (`podcast_scraper/prompts/`, laid out by provider, task and sometimes model, e.g.
  `shared/kg_graph_extraction/v3.j2`, `ollama/deepseek-r1_14b/summarization/long_v1.j2`), records
  their hashes in its own fingerprints, and production reads them from the library. It ran two
  loops by hand:
  - an agent following `program_*.md`: edit only allowed prompt files (user prompt before
    system prompt), score a blend of ROUGE-L and two LLM judges, reject a contested judgement,
    keep a change on a gain over 1% if the other track does not drop more than 1%, commit it, stop
    after 15 trials or 3 without gain; results in TSV files; a later revision added a test set
    scored once per champion;
  - a greedy one-parameter-at-a-time sweep from `param_space.yaml` (nested parameters such as
    `reduce_params.num_beams`, groups in order, each group enabled with a reason).
  Its validation set has 10 episodes and its test set 5.
- Rounds (0.4.0) record a sequence of arms with a hypothesis, retirements with reasons and a
  conclusion; goals weigh quality, cost and speed. A study is a round whose arms come one at a
  time.
- **Choosing by repeated tests on the same items is adaptive**: Holm corrects a fixed family, not
  a sequence where each test is chosen after seeing the last (Dwork et al., *The reusable
  holdout*, 2015; Cawley & Talbot 2010). With 10 validation items and 15 trials, a corrected
  threshold is near the smallest p a sign-flip test can reach on 10 items; with 5 test items no
  test can reach 0.05. The statistics must be designed, not assumed.

## Goals

- A prompt version is identified by its bytes; two arms that differ only by prompt version are
  provably that, and every run says which versions it used, wherever the files live.
- One study serves prompts, parameters, models and pipeline settings; what changes is the sampler
  and the search space.
- The evidence for a study's result is one check on test items, counted and never reused
  silently; keeping or dropping trials on validation items is labelled as search.
- A study's winner is never allowed to drift below where it started by a chain of small ties.
- A study is resumable, budgeted (dollars and time), and readable afterwards: every trial, its
  hypothesis, what changed, the test against the incumbent, why it was kept or dropped, what it
  cost.
- A person and an agent run the same study with the same records ([PRD-012](PRD-012-agent-ready.md)).

## Non-Goals

- The harness does not write prompts. An LLM sampler is a plug-in with its own key and budget.
- No prompt store the project must move into: prompts stay where the project keeps them.
- No templating engine: a prompt is a file the project renders; the harness hashes and versions
  its bytes.
- The study never promotes and never touches git. A confirmed winner is suggested for promotion;
  a person promotes, or an agent after asking ([PRD-012](PRD-012-agent-ready.md) FR2.5).
- No Bayesian or evolutionary optimiser of the harness's own; ask/tell admits Optuna's.

**Amends**: [PRD-001](PRD-001-experiments-and-comparison.md)'s "not a prompt library" becomes
"not a prompt store: the harness versions declared prompt files"; [PRD-005](PRD-005-goals-and-rounds.md)'s
"no automatic retirement" becomes "no automatic retirement outside a study; inside one, trials are
kept or dropped by the study's declared rule, and nothing is promoted automatically".

## Personas

- **The engineer tuning a prompt** after choosing a model.
- **The ML engineer tuning parameters** (decoding, batch size, chunking, map-reduce settings).
- **The agent** given a goal and asked to "push this further" ([PRD-012](PRD-012-agent-ready.md)).

## User Stories

- _As an engineer, my arm declares `prompts/summary/system.j2` from my library; the run records
  the file, its version number and its hash._
- _As an engineer, I make version 4 of that prompt from version 3 with a note, and see its
  lineage, the runs that used each version and their scores._
- _As an ML engineer, I write a search space (`reduce_params.num_beams` 1..4, `max_new_tokens`
  256/512/1024, in that order) and run a one-at-a-time study from the current baseline with a $5
  and two-GPU-hour budget._
- _As an engineer, I run a study whose sampler is an LLM that sees the current prompt, the scores
  and (because I allowed it) the worst outputs, and writes the next version; I read every trial
  afterwards on the goal page._
- _As a team lead, I see that the best trial held on the test items, how many times those items
  had been used, and promote it with one command._
- _As an engineer, I import my past loops' result files, so the goal page shows them as closed
  rounds._

## Functional Requirements

### FR1: Prompt versions

- **FR1.1**: An arm declares prompts under `prompts:`, each a name and a file path inside the
  project or its installed libraries; the adapter receives their text and path with the params.
- **FR1.2**: The fingerprint records each prompt under `arm`: name, version and content hash.
  Changing its bytes is a new version; `run-compare` names a prompt change as the variable.
- **FR1.3**: The harness keeps each declared prompt's history in the project: per version, the
  content (so an old version can be restored and diffed), parent, note, author (person, agent or
  sampler, with whom it acted for) and date. `name/N` is a fixed version; `name@<alias>` a moving
  pointer (`@champion` set by promotion).
- **FR1.4**: `evh prompt-version <name> --from <name/N> --file F --note "…"` records a new version
  (and writes the file when asked); `evh prompts [<name>]` lists versions and lineage;
  `evh prompt-diff <a> <b>` shows the change; `evh prompt-export <name/N> --to PATH` writes a
  version to where the project's production reads it. The catalog gains a prompt page.
- **FR1.5**: A system that cannot take a prompt path from its params needs an override hook of
  its own; the wrapping recipe ([PRD-008](PRD-008-pipelines-and-any-language.md) FR5) shows one.
- **FR1.6**: `evh validate` checks histories, lineage, and that every run's recorded prompt hash
  matches the version it names.

### FR2: The study

- **FR2.1**: A study is a spec: goal; validation dataset and test dataset (goal dataset roles
  `validation` and `test`); the starting arm (default: the goal's baseline on that dataset); the
  search space (parameters with nested paths, groups in order, each enabled with a reason; or
  prompt names that may change, in order); the sampler; the acceptance rule; guardrail metrics;
  stop rules; budgets; repeats per trial; and what the sampler may see.
- **FR2.2**: `evh loop-run <spec>` opens a round and repeats ask/tell: the sampler proposes a
  trial (with its hypothesis and rationale), the harness runs it on the validation items, compares
  it with the incumbent and keeps or drops it with the reason, until a stop rule fires. Each trial
  is an arm in the round; generated arms are stored with the study, not as hand-written configs.
- **FR2.3**: **Acceptance on validation is search.** The rule is declared in the spec and
  recorded as heuristic: the trial beats the incumbent on the goal's measure (or a declared
  composite of measures), no guardrail metric drops beyond its limit, and a contested or failed
  judgement drops the trial with that reason. Ties are decided as in
  [PRD-013](PRD-013-identity-and-ties.md) (the paired difference's confidence interval inside a
  margin), and the margin is anchored to the **starting** arm, so a chain of ties cannot drift
  below it.
- **FR2.4**: **The test check is the evidence.** At the end, the best trial and the starting arm
  run once on the test items; the round's conclusion records the paired result (effect, interval,
  p) and whether the gain held, by the rule the spec declared before the study started (a
  significance test when the test set can reach it; otherwise non-inferiority within a stated
  noise margin, said plainly). Promotion is suggested only when it held.
- **FR2.5**: **Test items are protected**: `loop-run` refuses a test dataset that shares items
  with the validation dataset; the harness counts every look at a test dataset per goal, shows the
  count, and refuses another study's confirmation on the same items unless overridden with a
  reason; the sampler never sees test items.
- **FR2.6**: **Small samples are said before spending**: `--dry-run` (and the start of a study)
  states the smallest p the validation and test sets can reach and refuses a rule that can never
  fire, unless overridden with a reason.
- **FR2.7**: Stop rules: trials, dollars, wall or GPU time, no kept trial in N, or the space
  exhausted. Budgets cover the system, the judges and the sampler, each counted separately.
- **FR2.8**: The scorer, references and judges are fixed for the study: a change to their hash
  mid-study stops it.
- **FR2.9**: Built-in samplers: grid, one-at-a-time from the incumbent, random. Plug-in samplers
  speak ask/tell through a command or an MCP tool ([PRD-012](PRD-012-agent-ready.md)); an LLM
  prompt sampler and an Optuna adapter ship as examples. The spec declares what a sampler sees:
  scores only, plus outputs, plus inputs; nothing from test items, ever.
- **FR2.10**: Each role (system, judge, sampler) uses its own key, named in the spec.
- **FR2.11**: A study resumes after an interruption from its records, without re-running finished
  trials; `--dry-run` prints the plan and spends nothing, calling neither the system nor the
  sampler.
- **FR2.12**: **The record of a trial**: hypothesis, sampler rationale, the change (a prompt diff
  or parameter values), the comparison with the incumbent (n, effect, interval, p), kept, dropped,
  contested or failed with the reason (a crash or truncation is recorded, never skipped), cost per
  role, wall and GPU time. **The record of a study**: the instruction and who gave it, who ran it
  (person or agent, acting for whom), the incumbent's provenance at the start, budget used, the
  stop reason, the test result, and a summary (what helped, what hurt, what to try next).
- **FR2.13**: `evh loop-import` brings past loops in from their result files (TSV, a best-config
  file) as closed rounds, marked imported.

## Success Criteria

- The podcast project's prompt loop and its parameter sweep can each be written as a study spec,
  including the blended measure, the guardrail, the contested-judge rule and the nested
  parameters (to be confirmed with that project).
- A test study on the example project keeps a planted real gain, drops a planted chance gain,
  refuses overlapping validation and test sets, warns on a set too small to separate, stops on
  budget, resumes, and confirms on test items.
- Two arms differing only in prompt version differ in the fingerprint only in that prompt.

## Related Documents

- RFC-009, RFC-010 (to be written); [RFC-004](../rfc/RFC-004-experiment-rounds.md),
  [ADR-0006](../adr/ADR-0006-goal-axes-and-strategies.md).
- References: Optuna and Vizier (study, trial, ask/tell); MLflow Prompt Registry (versions and
  aliases); DSPy optimizers, OPRO, APE (prompt optimisation); Dwork et al. 2015 (reusable
  holdout); Lakens 2017 (equivalence tests).
