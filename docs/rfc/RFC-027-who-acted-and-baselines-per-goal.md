# RFC-027: Who acted on every record, and baselines per goal

- **Status**: Draft (0.8.0, 2026-11-09), for the owner's review; revision 2 the same day, after an independent review
  (Fable) and the owner's answers to it. Its questions decided by the owner ("1 no, 2 run without goal is OK", 3:
  "drop it"; then "2 go with recommendation, 4 agree, 5 yes"). Step 4.1 of `research/internal/PLAN_0.8.0.md`.
- **Authors**: Marko Dragoljevic
- **Related**: the 0.5.0 drafts it reworks (PRD-011 and RFC-012, the evidence registry; PRD-012 and RFC-013 D5/D8, the
  actor and consent; not merged), [RFC-026](RFC-026-an-api-for-every-command.md) (its jobs carry `by` and set the
  actor; its lock table holds this RFC's commands), [RFC-023](RFC-023-labels-and-references.md) (`source.by` on
  labels and references), `deploy-sheet` (the reproduce block), CONCEPTS "What an agent may do" (the owner's rule of
  2026-11-04)

## Abstract

Every record a command writes says who acted: a person, or an agent and the person it acted for. A baseline belongs
to a goal on a dataset (or, for a run with no goal, to the dataset alone); promoting writes a new version beside the
old ones, never over them; the comparison that justified it is frozen into that version; a rollback is another
version. `evh baselines` lists them with how to reproduce each (the `deploy-sheet` block) and their history, and with
`--json` is the export a production system reads.

## Problem statement

- **Who acted is recorded by five commands only**, as free text: `--by` on `label-import`, `sheet-import`, `pick`,
  `reference-manifest` and `reference-promote` (labels keep it as `source.by`). A run, a promotion, a round, an unseal
  or a model record says nothing of who made it. The owner's rule lets an agent promote, label and run "when its
  operator asked for that task"; nothing records that it was an agent, or for whom.
- **One baseline per dataset, overwritten.** Two goals on one dataset share it, and `run-promote` replaces the file
  ("git keeps it", `promote_baseline.py:141`). There is no history in the project, no rollback but `git revert`, and
  nothing of the comparison that justified a promotion: re-running `pair-test` later reads new runs under today's
  rules, so the evidence drifts.

## Design

### D1. Who acted

- `_record.actor()` gives `{"type": "person" | "agent" | "unknown", "name": …, "for": …}` (PROV's
  `actedOnBehalfOf` as `for`). It reads, in order: `--by` where a command has it (`person:NAME`, `agent:NAME`, or a
  bare name, read as a person); `EVH_ACTOR` with `EVH_FOR` (`person:NAME`, required with an agent); else
  `person:<OS user>` (`getpass.getuser()`) when stdin is a terminal and `unknown:<OS user>` when it is not (an
  agent's shell, a script, CI, a job).
- **The actor is a recorded claim, not an identity.** Anyone can type `--by` or set `EVH_ACTOR`; the record shows
  what was claimed and how (`from`: `flag`, `environment` or `terminal`). That is the owner's rule: the harness
  records whose decision it was, it does not authenticate. Real identities and permissions come with a multi-user
  design (PRD-017's "later question"), not here.
- **Every record a command writes carries `actor`**: runs (`metrics.json`), baselines, references, label sets,
  rounds (open, retire, close), picks, dataset records (create, split, extend, unseal, lineage), model records, judged
  runs and verdicts. One function, called by `run_record`, `derived_record` and the writers that have no record
  builder. A label set's or reference's `source.by` (who labelled) stays as it is: `actor` beside it is who ran the
  command (they differ when a person imports another's sheet).
- **`--by` means who acted, on every command that writes.** `dataset-split`'s split rule, `--by hash|time` today, is
  renamed `--split-by` (owner, 2026-11-09), and the record's `split.by` follows (`split.split_by`; migrated). The
  inspector's and compare's `--by` (a breakdown field) stay: they write nothing, so they take no actor.
- **No consent machinery.** The drafts refused an agent's promotion and made the person rerun it with `--confirm`.
  The owner's rule is the opposite: an agent acts when its operator asked. An agent's decision carries `for` (whose
  decision it was) and its reason says what was asked.
- **A decision needs a named actor** (owner, 2026-11-09): `run-promote`, `baseline-rollback`, `round-close` (also when
  it promotes) and `dataset-unseal` refuse an `unknown` actor, saying how to name one (`--by`, or `EVH_ACTOR` with
  `EVH_FOR`). Runs, labels and every other record take `unknown` and go ahead. An RFC-026 job has no terminal: its
  supervisor sets `EVH_ACTOR` / `EVH_FOR` from the job's `by`, and the API refuses a decision job without `by`.
- **The MCP server stays read-only.** Agents promote and label through the command line or RFC-026 jobs, never
  through `evh mcp`; its `NOT_TOOLS` reasons ("a decision: a person's") become "a decision: recorded with who acted".
  CONCEPTS "What an agent may do" replaces "Consent recorded by the harness itself … is 0.8.0's to design" with this
  section's rule.

### D2. Baselines per goal, versioned

- A baseline is `data/baselines/<goal_id>/<dataset_id>/<n>.json`, `n` from 1, written once. The current one is the
  highest `n` (compared as numbers: `10` after `9`). A rollback is a new version that names the version it restores
  (`restores: 3`) and copies its run. `promoted_from`, `scores`, `build` and the rest stay as they are; new:
  `version`, `goal` (null for the dataset's own), `actor`, `reason` (required), `replaces` (the version it replaced,
  none for the first), `evidence` (D3). `baseline_id` goes: a baseline is named by goal, dataset and version.
- **Written once, even by two promotions at once.** A version is created exclusively (`O_EXCL` in a files project; an
  `INSERT` that fails on an existing key, in a `BEGIN IMMEDIATE` transaction, in SQLite), and a promotion that finds
  its `n` taken reads the new current version and computes again against it. A promotion from the terminal is not
  under RFC-026's locks, so the write itself must hold.
- `evh run-promote --run R --reason "…"` promotes into the run's own goal (its config's `goal:`); `--goal G` names
  another of the dataset's goals. `round-close --promote` passes the round's goal, its `--by` and the round.
- **A baseline with no goal** (owner, 2026-11-09: ad-hoc experiments need not be tied to a goal): a run whose config
  names none is promoted into the dataset's own baselines, `data/baselines/_dataset/<dataset_id>/<n>.json`, with
  `goal: null`; versioned, evidenced and rolled back the same way; `--no-goal` puts a goal's run there too. A goal
  never reads them. Their readers (owner, 2026-11-09): `evh baselines`, the inspector's comparison (its default
  baseline when the arms answer no goal) and `deploy-sheet`.
- `evh baseline-rollback (--goal G | --no-goal) --dataset D --to N --reason "…"` writes the next version restoring N,
  with its own evidence (N against what is current now).
- **Every reader moves to `_baselines`** (`current(goal, dataset)`, `versions(goal, dataset)`, numbers sorted as
  numbers, each with a `current` flag), and none keeps the old path:
  - `round-open` (the round's starting run, `rounds.py:131`) and `round-close --promote` (`rounds.py:286-299`);
  - the goal axes' `reference: baseline` (A6) and the catalog: `catalog_build.py` (its goal pages at :1215 and :2744
    keep only the goal's own baselines, the "no goal" branch dropped; :990, :1909 and :4018 take the goal's current
    version, not the dataset list's last), `catalog_adapter.baselines()` (:1030, versions sorted by number);
  - the comparison's fallback to a promoted arm (`catalog_serve.py:499-501`): the dataset's own current baseline;
  - `deploy-sheet` (keyed by `--config`): it scans the current versions across goals for the arm's run and prints the
    goal and version in its block and `--json`;
  - `list_runs.py` (`runs-list --baselines` goes: `evh baselines` replaces it), the data page (`_data_page.py:50`),
    `fingerprint-migrate` (`fingerprint_migrate.py:169`, a flat glob today), `validate_tree.py` (:208, :501, :1178,
    flat globs today), `promote_baseline.py`;
  - `data/baselines/README.md` and the docs that describe one baseline per dataset (UPGRADING, RUNBOOK, SCENARIO,
    README, GUIDE, UXS-003).
  - `pair-test` reads no baseline (its B is `--b`, or a round's starting run): unchanged.

### D3. The evidence, frozen at promotion

Before writing a version, `run-promote` computes and stores the comparison that justifies it, against the version it
replaces, on the goal's primary measure, exactly as `pair-test` answers it (owner, 2026-11-09):

```json
"evidence": {
  "compared_to": 3, "measure": "f1", "n": 200, "items_sha256": "…",
  "verdict": {"outcome": "better", "delta": 0.021, "interval": [0.009, 0.033], "p": 0.0012, "method": "sign-flip"},
  "axes": {"cost_usd_per_item": [0.0011, 0.0024]},
  "round": "r3",
  "computed_with": {"harness": "0.8.0", "stats_sha256": "…", "runs_a": ["…"], "runs_b": ["…"],
                    "reduce": "mean", "cluster": "fingerprint", "permutations": 10000, "seed": 0}
}
```

- **Arm against arm, as `pair-test` reads them.** `pair-test` compares arms, not single runs: it pools every run of
  each config on the dataset and reduces repeats per item. The evidence is that comparison between the promoted run's
  arm and the current version's arm; with a round (the promotion's own, or `--round`), as `pair-test --round` reads
  it, a re-scored arm's latest re-score standing in for its runs. `computed_with` records the run ids pooled on each
  side, the reducer, the cluster field, the permutations and seed, so the verdict can be traced to its inputs.
- `n` and `items_sha256` are over the items compared (the shared items, less any excluded), not the dataset's.
- It is never recomputed: a later `pair-test` is another question, not the evidence.
- A first version has `compared_to: null` and no verdict. Two arms that are not comparable (another reference digest,
  scorer or item set) record `verdict: null` and `not_comparable: [the fields]`, and the command says so before
  writing. A promotion is not refused for a verdict that is "not significant" or "worse": the record and the
  catalog show it. Test-set looks (whether this comparison spent one) come with 4.4; until then the field is absent.

### D4. `evh baselines [--goal G | --no-goal] [--dataset D] [--all-versions] [--json]`

Per goal and dataset: the current version, who promoted it and why, its evidence, how to reproduce it (the block
`deploy-sheet` prints for its run, one definition), and its history (each version: when, by whom, why, what it
replaced or restored). `--json` is the export a production system reads: deterministic (sorted, no timestamp of its
own, no harness version in a header), so two outputs with no new promotion are byte-identical; the goal's context and
decision ride along as the intended use. It replaces `runs-list --baselines`, which goes. The goal page shows the
same. It is a read tool of `evh mcp` (`READ_TOOLS`, `JSON`); `baseline-rollback` and `baselines-migrate` are in
`NOT_TOOLS`.

### D5. Validation

V6 (baselines) checks each version: its run exists and its scores match; the `replaces` chain is contiguous (each
version replaces the one before it, a rollback included); `restores` names an earlier version; the evidence's
`items_sha256` is the hash of the items its `n` counts. A new check names records with no `actor`, after the
migration has written one on every record.

## Migration (no backward compatibility)

One command, `evh baselines-migrate` (or a step of `data-migrate`, which the project already runs for format
changes), with `--dry-run`:

- each `data/baselines/<dataset>_baseline.json` moves to `<goal>/<dataset>/1.json` under the goal its record names,
  or to `_dataset/<dataset>/1.json` with `goal: null` when it names none, with `evidence: null` and `migrated: true`
  ("promoted before 0.8.0, evidence not recorded"), `baseline_id` dropped. This repository's eight: seven name a goal
  and move under it; `smoke_v1`'s moves to the dataset's own baselines;
- every existing record gets `actor: {"type": "unknown", "name": "before 0.8.0", "from": "migration"}`: runs in every
  runs directory (`runs*`), baselines, references, label sets, rounds, picks, dataset records, model records;
  label sets' and references' `source.by` stays;
- `split.by` becomes `split.split_by` on every split side;
- the schemas that refuse unknown keys (`additionalProperties: false`: metrics, round, reference, dataset, baseline,
  label set, model, pick and the rest) gain `actor`; baseline gains `version`, `goal` null, `replaces`, `restores`,
  `evidence`, `migrated` and loses `baseline_id`;
- before it is built: check whether a run's fingerprint hash covers any field the run rewrite touches (it must not
  move a hash; `actor` is outside the fingerprint by design, as `goal` and `round` are).

No reader keeps the old path or the old key.

## Alternatives considered

- **Keep one baseline per dataset and add history to it.** Rejected: a goal names its datasets, and two goals on one
  dataset ask different questions with different primary measures, so one baseline answers one of them. (No dataset
  in this repository has two goals yet; a project with a noise goal and a recall goal on one capture would.)
- **Recompute the evidence on demand.** Rejected: it drifts with new runs and rules; promotion is when the decision
  was made.
- **The evidence as one run against one run.** Rejected (owner, 2026-11-09): every other test reads an arm, its
  repeats pooled; a promotion's evidence that answered another question than `pair-test` would disagree with it.
- **The drafts' consent (`--confirm` by a person).** Rejected by the owner's rule: an agent acts when asked, and the
  record names whose decision it was.
- **Rename `source.by` to the actor.** Rejected: who labelled and who ran the command are two facts.
- **A record store with an id grammar for every kind (the drafts' RFC-017).** Not needed: baselines are addressed by
  goal, dataset and version.
- **`evh evidence-check FILE`** (the drafts' RFC-012): checking that a project's own citation file names baselines,
  runs and rounds that exist and are current. Dropped from 0.8.0 (owner, 2026-11-09): no project cites a harness id
  today (the podcast project's `registry_refs.yaml` cites eval reports by path, and its own script checks them), so it
  would only repeat that check. Added when a project cites harness ids; the versioned baselines and `evh baselines
  --json` it would read are built here.

## Testing

- `test_actor.py`: every writing command records the actor, with `from`; `EVH_ACTOR=agent:x` without `EVH_FOR` is
  refused; no terminal and no actor gives `unknown`; `--by` wins over the environment; `source.by` and `actor` both
  kept on a label set; a decision with an `unknown` actor is refused; an RFC-026 job's actor comes from its `by`;
  `dataset-split --split-by` (and `--by` refused there).
- `test_baselines.py`: promotion writes version n+1 and never touches n; two promotions at once both land, as n+1
  and n+2, the second against the first; two goals on one dataset keep their own; a run with no goal goes to the
  dataset's own and no goal page shows it; version 10 is current after 9; the evidence equals `pair-test`'s answer
  for the two arms at promotion (with a round, as `--round` reads them) and stays when new runs arrive; not
  comparable records the fields; rollback restores and compares; every reader in D2 reads the right version;
  `baselines --json` is byte-identical twice; the migration moves this repository's baselines and writes `actor` on
  every record without moving a fingerprint hash.
- All of it in both stores.

## Open questions (the owner's, decided 2026-11-09)

1. May an `unknown` actor make a decision? No (D1).
2. A run with no goal? Promoted into the dataset's own baselines (D2), read by `evh baselines`, the comparison and
   `deploy-sheet`.
3. `evidence-check` in 0.8.0? Dropped (Alternatives considered).
4. The evidence? `pair-test`'s arm comparison, as a round reads it (D3).
5. `--by` on `dataset-split`? Renamed `--split-by`; `--by` means who acted (D1).

## Decisions (ADR candidates)

1. Every record says who acted, and for whom when an agent did; the actor is a recorded claim; the harness records,
   it does not ask for consent.
2. A baseline belongs to a goal on a dataset (or to the dataset alone, for a run with no goal), in write-once
   versions; a rollback is a version.
3. The comparison that justified a promotion is `pair-test`'s, frozen into it and never recomputed.
