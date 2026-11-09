# RFC-027: Who acted on every record, and baselines per goal

- **Status**: Draft (0.8.0, 2026-11-09), for the owner's review. Its three open questions decided by the owner the
  same day ("1 no, 2 run without goal is OK", 3: "drop it"). Step 4.1 of `research/internal/PLAN_0.8.0.md`.
- **Authors**: Marko Dragoljevic
- **Related**: the 0.5.0 drafts it reworks (PRD-011 and RFC-012, the evidence registry; PRD-012 and RFC-013 D5/D8, the
  actor and consent; not merged), [RFC-026](RFC-026-an-api-for-every-command.md) (its jobs pass `by` and `reason` to
  the commands; the commands that take neither get them here), [RFC-023](RFC-023-labels-and-references.md) (`--by` on
  labels and references today), `deploy-sheet` (the reproduce block), CONCEPTS "What an agent may do" (the owner's
  rule of 2026-11-04)

## Abstract

Every record a command writes says who acted: a person, or an agent and the person who asked it. A baseline belongs
to a goal on a dataset, not to the dataset alone; promoting writes a new version beside the old ones, never over them;
the comparison that justified it is frozen into that version; a rollback is another version. `evh baselines` lists them
with how to reproduce each (the `deploy-sheet` block) and their history, and with `--json` is the export a production
system reads.

## Problem statement

- **Who acted is recorded in eight commands only**, as free text (`--by` on labels, references, picks, splits). A run,
  a promotion, a round, an unseal or a model record says nothing of who made it. The owner's rule lets an agent
  promote, label and run "when its operator asked for that task"; nothing records that it was an agent, or for whom.
- **One baseline per dataset, overwritten.** Two goals on one dataset share it, and `run-promote` replaces the file
  ("git keeps it", `promote_baseline.py:141`). There is no history in the project, no rollback but `git revert`, and
  nothing of the comparison that justified a promotion: re-running `pair-test` later reads new runs under today's
  rules, so the evidence drifts.

## Design

### D1. Who acted

- `_record.actor()` gives `{"type": "person" | "agent" | "unknown", "name": …, "for": …}` (PROV's
  `actedOnBehalfOf` as `for`). It reads, in order: `--by` where a command has it; `EVH_ACTOR` (`person:NAME` or
  `agent:NAME`) with `EVH_FOR` (`person:NAME`, required with an agent); else `person:<OS user>` when stdin is a
  terminal and `unknown:<OS user>` when it is not (an agent's shell, a script, CI).
- **Every record a command writes carries `actor`**: runs (`metrics.json`), baselines, references, label sets (their
  `--by` becomes the actor's name, the field renamed once by migration), rounds (open, retire, close), picks, dataset
  records (create, split, extend, unseal, lineage), model records, judged runs and verdicts. One function, called by
  `run_record`, `derived_record` and the writers that have no record builder.
- **`--by` is accepted by every command that writes**, beside the environment, so a person names themselves once per
  command or once per shell. RFC-026's job passes its `by` the same way.
- **No consent machinery.** The drafts refused an agent's promotion and made the person rerun it with `--confirm`.
  The owner's rule is the opposite: an agent acts when its operator asked. So the harness records, it does not
  refuse: an agent's decision carries `for` (whose decision it was) and its `--reason` says what was asked.
- **A decision needs a named actor** (owner, 2026-11-09): `run-promote`, `baseline-rollback`, `round-close` and
  `dataset-unseal` refuse an `unknown` actor, saying how to name one (`--by`, or `EVH_ACTOR` with `EVH_FOR`). Runs,
  labels and every other record take `unknown` and go ahead.

### D2. Baselines per goal, versioned

- A baseline is `data/baselines/<goal_id>/<dataset_id>/<n>.json`, `n` from 1, written once. The current one is the
  newest version. A rollback is a new version that names the version it restores (`restores: 3`) and copies its run. `promoted_from`, `scores`, `build` and the
  rest stay as they are; new: `version`, `goal`, `actor`, `reason` (required), `replaces` (the version it replaced,
  none for the first), `evidence` (D3).
- `evh run-promote --run R --reason "…"` promotes into the run's own goal (its config's `goal:`); `--goal G` names
  another of the dataset's goals.
- **A baseline with no goal** (owner, 2026-11-09: ad-hoc experiments need not be tied to a goal): a run whose config
  names none is promoted into the dataset's own baselines, `data/baselines/_dataset/<dataset_id>/<n>.json`, versioned,
  evidenced and rolled back the same way; `--no-goal` puts a goal's run there too. A goal never reads them; a command
  asked about the dataset without a goal (`pair-test` with no `--goal`) does.
- `evh baseline-rollback --goal G --dataset D --to N --reason "…"` writes the next version restoring N, with its own
  evidence (N against what is current now).
- Readers move to `_baselines.current(goal, dataset)`: `pair-test` (its default B), `rounds` (the round's starting
  run), the goal axes' `reference: baseline` (A6), `deploy-sheet`, `runs-list --baselines`, the catalog and validate.
  A dataset with baselines under two goals is read per goal; nothing reads "the dataset's baseline" any more.

### D3. The evidence, frozen at promotion

Before writing a version, `run-promote` computes and stores the comparison that justifies it, against the version it
replaces, on the goal's primary measure:

```json
"evidence": {
  "compared_to": 3, "measure": "f1", "n": 200, "items_sha256": "…",
  "verdict": {"outcome": "better", "delta": 0.021, "interval": [0.009, 0.033], "p": 0.0012, "method": "sign-flip"},
  "axes": {"cost_usd_per_item": [0.0011, 0.0024]},
  "round": "r3",
  "computed_with": {"harness": "0.8.0", "stats_sha256": "…"}
}
```

- The verdict is what `pair-test` answers for the two runs today (the same function, with the goal's cluster and
  reducer). It is never recomputed: a later `pair-test` is another question, not the evidence.
- A first version has `compared_to: null` and no verdict. Two runs that are not comparable (another reference digest,
  scorer or item set) record `verdict: null` and `not_comparable: [the fields]`, and the command says so before
  writing.
- A promotion is not refused for a verdict that is "not significant" or "worse": the record and the catalog show it.
  Test-set looks (whether this comparison spent one) come with 4.4; until then the field is absent.

### D4. `evh baselines [--goal G] [--dataset D] [--all-versions] [--json]`

Per goal and dataset: the current version, who promoted it and why, its evidence, how to reproduce it (the block
`deploy-sheet` prints for its run, one definition), and its history (each version: when, by whom, why, what it
replaced or restored). `--json` is the export a production system reads: deterministic (sorted, no timestamp of its
own, no harness version in a header), so two outputs with no new promotion are byte-identical; the goal's context and
decision ride along as the intended use. It replaces `runs-list --baselines`, which goes. The goal page shows the same.

### D5. Validation

V6 (baselines) checks each version: its run exists and its scores match; `replaces` is the version current when it
was written; `restores` names an earlier version; the evidence's `items_sha256` is the dataset's. A new check names
records with no `actor`, after the migration has written one on every record.

## Migration (no backward compatibility)

`evh baselines-migrate` (or `data-migrate`, which the project already runs for format changes) moves each
`data/baselines/<dataset>_baseline.json` to `<goal>/<dataset>/1.json` under the goal its record names, with `evidence:
null` and `migrated: true` ("promoted before 0.8.0, evidence not recorded"), and writes `actor: {"type": "unknown",
"name": "before 0.8.0"}` on every existing record, the label sets' `by` becoming the actor's name. This repository's
eight baselines: seven name a goal and move under it; `smoke_v1`'s names none and moves to the dataset's own
baselines. No reader keeps the old path.

## Alternatives considered

- **Keep one baseline per dataset and add history to it.** Rejected: a goal names its datasets, and two goals on one
  dataset ask different questions with different primary measures, so one baseline answers one of them. (No dataset
  in this repository has two goals yet; a project with a noise goal and a recall goal on one capture would.)
- **Recompute the evidence on demand.** Rejected: it drifts with new runs and rules; promotion is when the decision
  was made.
- **The drafts' consent (`--confirm` by a person).** Rejected by the owner's rule: an agent acts when asked, and the
  record names whose decision it was.
- **A record store with an id grammar for every kind (the drafts' RFC-017).** Not needed: baselines are addressed by
  goal, dataset and version.
- **`evh evidence-check FILE`** (the drafts' RFC-012): checking that a project's own citation file names baselines,
  runs and rounds that exist and are current. Dropped from 0.8.0 (owner, 2026-11-09): no project cites a harness id
  today (the podcast project's `registry_refs.yaml` cites eval reports by path, and its own script checks them), so it
  would only repeat that check. Added when a project cites harness ids; the versioned baselines and `evh baselines
  --json` it would read are built here.

## Testing

- `test_actor.py`: every writing command records the actor; `EVH_ACTOR=agent:x` without `EVH_FOR` is refused; no
  terminal and no actor gives `unknown`; `--by` wins over the environment; RFC-026's job passes its `by`.
- `test_baselines.py`: promotion writes version n+1 and never touches n; two goals on one dataset keep their own; the
  evidence is the `pair-test` verdict at promotion and stays when new runs arrive; not comparable records the fields;
  rollback restores and compares; readers (pair-test, rounds, A6, deploy-sheet) read the goal's current version;
  `baselines --json` is byte-identical twice; the migration moves this repository's baselines.
- All of it in both stores.

## Open questions (the owner's, decided 2026-11-09)

1. May an `unknown` actor make a decision? No (D1).
2. A run with no goal? Promoted into the dataset's own baselines (D2).
3. `evidence-check` in 0.8.0? Dropped (Alternatives considered).

## Decisions (ADR candidates)

1. Every record says who acted, and for whom when an agent did; the harness records, it does not ask for consent.
2. A baseline belongs to a goal on a dataset, in write-once versions; a rollback is a version.
3. The comparison that justified a promotion is frozen into it and never recomputed.
