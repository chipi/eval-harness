# PRD-009: Prompts as data, and an optimisation loop

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related UX specs**: [UXS-001](../uxs/UXS-001-catalog.md) (the goal page, to show a loop),
  [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) (the commands)
- **Related RFCs**: RFC-009 (prompts as versioned data), RFC-010 (the loop and its proposers),
  both to be written; [RFC-004](../rfc/RFC-004-experiment-rounds.md) (rounds)
- **Related PRDs**: [PRD-005](PRD-005-goals-and-rounds.md) (goals, rounds, axes),
  [PRD-010](PRD-010-runners.md) (where the loop's runs run),
  [PRD-012](PRD-012-agent-ready.md)

## Summary

Once a project has chosen a model, the next gains come from tuning: the prompt, the decoding
parameters, the pipeline's settings. This PRD does two things. **Prompts become data** the
harness owns, like references: versioned files an arm names (`summary@v3`), hashed into the
fingerprint, with the history of which version came from which and why. And the harness gets
an **optimisation loop** that is not specific to prompts: from the current best arm, a
**proposer** suggests a candidate (a new prompt version, a parameter value, a model), the
harness runs it on the tuning items, accepts or drops it by the paired test and the goal's
axes, records each step as part of a round, stops on a budget or when gains run out, and
confirms the winner once on held-out items it was never tuned on. Proposers are pluggable:
grid, one-at-a-time and random are built in; an LLM that rewrites a prompt, or any command or
agent, plugs in.

## Background & Context

- The harness records params in the fingerprint, so a prompt counts only when it is written
  inline in a config. A prompt kept in a file the adapter reads is invisible to it.
- The podcast project keeps 207 versioned Jinja prompts in its library
  (`prompts/<provider>/<task>/<name>_vN.j2`), records their hashes in its own fingerprints, and
  ran two kinds of loops by hand: an agent following `program_*.md` that edits allowed prompt
  files, keeps a change on a gain over 1% (committing it) and stops after 15 steps or 3 without
  gain; and a greedy one-parameter-at-a-time sweep from a `param_space.yaml`. Its results live
  in TSV files; a later revision added a held-out benchmark set scored once per champion.
- Rounds (0.4.0) already record a sequence of arms with a hypothesis, retirements with reasons
  and a conclusion, and goals already weigh quality, cost and speed. A loop is a round whose
  arms come one at a time.
- Accepting on "a gain over 1%" on the tuning items alone over-fits: the more candidates tried,
  the likelier one wins by chance. The harness already has the tools to say whether a gain is
  real.

## Goals

- A prompt version is identified by its bytes; two arms that differ only by prompt version are
  provably that, and every run says which versions it used.
- One loop serves prompts, parameters, models and pipeline settings; what changes between uses
  is the proposer and the search space.
- Acceptance is by evidence (the paired test against the incumbent and the goal's axes), not by
  a fixed percentage.
- The winner of a loop is confirmed on held-out items before it can be promoted.
- A loop is resumable, budgeted, and readable afterwards: every step, why it was kept or
  dropped, what it cost.
- A person and an agent run the same loop with the same result in the records
  ([PRD-012](PRD-012-agent-ready.md)).

## Non-Goals

- The harness does not write prompts itself. An LLM proposer is a plug-in with its own key and
  budget; the harness only calls it and records what it proposed.
- No Bayesian or evolutionary optimiser in 0.5.0; the proposer interface admits one later.
- No templating engine of its own: a prompt file is text (or a template the project renders);
  the harness hashes and versions it, the project renders it.
- No automatic promotion: a confirmed winner is suggested for promotion, as rounds suggest.

## Personas

- **The engineer tuning a prompt** after choosing a model.
- **The ML engineer tuning parameters** (decoding, batch size, chunking, map-reduce settings).
- **The agent** given a goal and asked to "push this further" ([PRD-012](PRD-012-agent-ready.md)).

## User Stories

- _As an engineer, I create `summary@v4` from `summary@v3` with a note on what changed, point an
  arm at it, and the run records the version and its hash._
- _As an engineer, I see the history of a prompt: each version, its parent, the note, and the
  runs that used it with their scores._
- _As an ML engineer, I write a search space (num_beams 1..4, max_new_tokens 256/512/1024) and
  run a one-at-a-time loop from the current baseline with a $5 budget._
- _As an engineer, I run a loop whose proposer is an LLM that reads the current prompt and the
  worst-scored items and writes the next version; I read every step afterwards on the goal page._
- _As a team lead, I see that the loop's winner was confirmed on held-out items, and promote it
  with one command._

## Functional Requirements

### FR1: Prompts as data

- **FR1.1**: A prompt is `data/prompts/<prompt_id>/` with one file per version and a manifest
  per version: parent version, note, author (person, agent or proposer), date.
- **FR1.2**: A config names prompts by `<prompt_id>@<version>` under `prompts:`; the adapter
  receives their text (and path) with the params.
- **FR1.3**: The fingerprint records each prompt's id, version and content hash; a change of
  bytes under the same name is a different hash.
- **FR1.4**: `evh prompt-create --from <id>@<v> --note "…"` makes the next version;
  `evh prompts` lists them; `evh prompt-diff a b` shows the change; the catalog gains a prompt
  page (versions, lineage, runs that used each, their scores).
- **FR1.5**: `evh validate` checks prompt manifests, lineage, and that every run's recorded
  prompt hash matches the file it names.
- **FR1.6**: A project that keeps prompts elsewhere can still declare them (path and hash) so
  they enter the fingerprint, without moving them.

### FR2: The loop

- **FR2.1**: A loop is a spec: goal, dataset for tuning (a goal dataset role `dev`), held-out
  dataset (role `heldout`), the starting arm (default: the goal's baseline), the search space,
  the proposer, the acceptance rule, the stop rule and the budget.
- **FR2.2**: `evh loop-run <spec>` opens a round for the loop and repeats: propose a candidate,
  run it, compare it with the incumbent, accept or drop it with the reason, until a stop rule
  fires; each step is an arm in the round, so `evh rounds` and the goal page show it.
- **FR2.3**: Acceptance: the candidate is separated as better than the incumbent on the goal's
  measure (paired test) or, with the goal's strategy, ties it on quality and wins on its
  tie-break (cost, speed); candidates over a goal's limit are never accepted. The rule says how
  repeated tests are corrected.
- **FR2.4**: Stop rules: steps, budget (dollars), no accepted step in N, or the space exhausted.
- **FR2.5**: The loop's winner is run once on the held-out dataset; the loop's conclusion
  records both results and whether the gain held. Promotion is suggested only when it held.
- **FR2.6**: Built-in proposers: grid, one-at-a-time (from the incumbent, a parameter at a
  time), random. Plug-in proposers: a command (or MCP tool, [PRD-012](PRD-012-agent-ready.md))
  that receives the incumbent, the history and the worst items, and returns a candidate (params,
  or a new prompt version with its note). An LLM prompt proposer ships as an example plug-in.
- **FR2.7**: A loop resumes after an interruption from its round's records, without re-running
  finished steps.
- **FR2.8**: `--dry-run` prints the plan (steps at most, items per step, estimated cost) and
  spends nothing.

## Success Criteria

- The podcast project's prompt loop and its parameter sweep can each be expressed as a loop spec
  (the review with that project decides whether they move).
- A test loop on the example project accepts a planted real gain, drops a planted chance gain,
  stops on budget, resumes, and confirms on held-out items.
- Two arms differing only in prompt version differ in the fingerprint only in that prompt.

## Related Documents

- RFC-009, RFC-010 (to be written); [RFC-004](../rfc/RFC-004-experiment-rounds.md),
  [ADR-0006](../adr/ADR-0006-goal-axes-and-strategies.md).
