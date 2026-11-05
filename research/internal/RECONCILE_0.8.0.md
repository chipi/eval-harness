# 0.8.0: what was planned, against what shipped

**Status:** 2026-11-05, input for planning 0.8.0. Compares the agent-ready drafts on branch `080-plan` (was `070`) (written
2026-10-26..29 against 0.4.4: PRD-008..013, RFC-007..017, ADR-0007..0017, UXS-004/005, NEXT_STEPS_0.8.0) with
main at v0.7.2 (branch `080`). Three read-only reviews mapped every requirement; each SHIPPED or PARTLY cites
code on main, each NOT BUILT a repo-wide search that came back empty. Nine of their claims were re-checked by
hand (listed at the end); none was wrong.

## Summary

**Most of the drafts are not built, and none can be built as written.** What shipped since they were written:

- the read-only MCP server (0.5.0);
- `--json` on about 26 of 67 commands, skills and `evh skills-install`, `AGENTS.md` (0.7.0);
- fingerprint v5 (0.6.0), with a different design from the drafts' v5;
- run-id collisions fixed (0.7.0), in a different way from the drafts.

Everything else is unbuilt: stages, the process adapter, job sets and runners, prompt versions, studies,
per-goal baselines with frozen evidence, non-inferiority ties, test looks, the exit-code table, coded refusals,
the actor on records, the record store.

**Every draft must be rewritten before use:**

- **Vocabulary 0.6.0 retired:** `experiment-run`, `dev`/`heldout`, `separated`, `tied`.
- **Paths that are gone:** `experiment_run.py`, `reference_create.py`, `data/models.yaml`.
- **The target release:** they said "0.7.0" (renamed to 0.8.0 on 2026-11-05).
- **Taken validate codes:** they reuse V17–V20, which main gave to captures, model records, label sets and
  hypotheses.
- **Decisions main went against:**
  - consent: the drafts refuse every promotion to an agent; the owner's rule of 2026-11-04 lets an agent promote
    when its operator asked;
  - "prefer the MCP tools": main made the shell the agent's main path;
  - the fingerprint v5 layout;
  - a migration script: main has `evh fingerprint-migrate` instead.

**One finding is a correctness issue, not a missing feature.** Main still decides ties with a 2%-of-the-leader
margin (`axes.py:59`). The drafts' simulations found that rule invalid for 0/1 measures. Those simulations exist
only on branch 080-plan (`research/internal/stats-0.8.0/`).

## What is worth carrying into 0.8.0

Grouped by how ready each is. The owner decides what goes in; this list only sorts the drafts.

**Small, self-contained, no design left open:**

1. **An exit-code table and coded refusals** (PRD-012 FR2.2/2.3, RFC-013 D3/D4).
   - Today exit 2 is both a usage error and the cost cap (`run.py:810`).
   - A refusal is an `ERROR:` line with no code (`_common.py:633`).
   - The MCP server already relies on "exit 1 + ERROR line", so a code would carry through to it.
2. **Help that names the command** (PRD-012 FR2.6).
   - 43 of 67 commands print the script's name: `run-promote --help` says `usage: promote_baseline.py`.
   - 38 of 67 show no example.
3. **A cancelled MCP call kills its child process** (RFC-016). The server runs children, and nothing stops one
   when its call is cancelled.
4. **Docs main already needs:**
   - the goal page's links bullet in UXS-001 (the code has it);
   - `model_facts`/`models` in RFC-003, rewritten for `data/models/`;
   - PRD-001's non-goal "quality over time", which contradicts 0.4.2's period trends;
   - INFLUENCES' agents-and-machines block (MCP, Agent Skills).
5. **`validate` recomputes every stored fingerprint hash** (PRD-013 FR2.3). Nothing checks them today.

**Real features with a design that needs revisiting first:**

6. **Non-inferiority ties** (PRD-013 FR3, RFC-015 D1–D2). This replaces the 2% rule above.
   - It needs the simulations brought over from 080-plan and re-run against main's `stats.py`.
   - It needs a decision on how existing goals and their contenders change.
7. **Baselines per goal, with frozen evidence and `evidence-check`** (PRD-011, PRD-013 FR1).
   - Today two goals on one dataset share one baseline, and promotion overwrites it (`promote_baseline.py:141`).
   - Versions, a frozen comparison and rollback are all unbuilt.
   - The reproduce block should reuse `deploy-sheet` instead of a second definition.
8. **Job sets with a detached supervisor, plus `jobs-status` and `jobs-logs`** (PRD-010, RFC-011 D1). This is the
   agent-ready premise: `evh run` holds the terminal, and an agent's tool call times out before a run ends.
9. **Item failures** (RFC-007 D4).
   - One failed item still stops the whole pass (`run.py:1093-1097`).
   - Any redesign must keep 0.6.0's deliberate stop when a server is unreachable.
10. **The actor on records, and consent** (PRD-012 FR3.1/FR4.5, RFC-013 D5/D8).
    - Main hands consent to 0.8.0 (`CONCEPTS.md:288`).
    - The design must start from the owner's operator-asked rule, not the drafts' refusal.
11. **Prompt versions** (PRD-009 FR1, RFC-009 D1/D3). Self-contained; they would give `deploy-sheet` a version to
    name instead of a bare hash.
12. **Per-command result schemas, then `outputSchema` on MCP tools** (PRD-012 FR1.3, RFC-016). They replace
    `_jsonout`'s generic `blocks`, which `_jsonout.py:11` already promises to do.
13. **A standard `code_ref` in the fingerprint hook** (PRD-008 FR4.4). The mechanism exists, and the triage example
    declares `fleet_commit`. What's missing is the standard name and the docs.

**Large, dependent on other unbuilt pieces, or with no user in sight:**

14. **Studies** (PRD-009 FR2–FR5, RFC-010). They need job sets, actor/consent, the record store and test looks
    first. Reusable on main: ADR-0025 hypotheses, the 0.7.0 Bonferroni correction for a tool-picked leader,
    `limit: baseline`.
15. **Test-set looks and power** (PRD-013 FR6/FR9, RFC-015 D3/D4): the look budget, attainable p, MDE. Needed by
    studies and the registry.
16. **The id grammar and the record store** (PRD-013 FR7, RFC-017). Only if per-goal baselines, prompt versions and
    studies come back.
17. **Stages, OTLP import, the process adapter** (PRD-008, RFC-007/008). Nothing on main depends on them or asks
    for them. The fleet's Track A, deterministic code evaluated as black boxes, works without them.
18. **The ssh runner and phases** (PRD-010 FR1.7/FR3). Their user, the podcast project's GPU-mode switching, was
    marked "to be confirmed" in the drafts, and nothing shows it was.

**Drop:**

- **ADR-0014's v5 design, the `migrate_0_5_0` script and its "keep v4" step, and "roles not renamed".** A different
  v5 shipped; `evh fingerprint-migrate` exists; v4 is not kept; the roles were renamed.
- **RFC-008's `arm.system` and RFC-009 D2's prompts in the arm's hash.** In v5 the system is `deployment`, and a
  prompt hash lives under `settings.declared`.
- **The "prefer MCP" skill rule, and the study and job skills.** Main chose the shell; studies and jobs don't exist.
- **NEXT_STEPS_0.8.0 as a status record.** Every "where it stands" line predates 0.5.0.

## Shipped since the drafts, with no draft behind it

These shipped without any of the drafts, and the 0.8.0 plan should build on them, not around them:

- captures and datasets from production (0.6.0);
- labels and label sets (0.6.0);
- judging modes and the sheet (0.6.0);
- model records and onboarding (0.6.0);
- `deploy-sheet` (0.6.0);
- `capture-restore`, `pair-test --b-dataset` and `inspect --crosstab` (0.7.0);
- the hypothesis block (0.7.0, ADR-0025);
- `--write-answers` (0.6.2/0.7.2).

## The detail, by draft

### Pipelines, any language, runners (PRD-008, RFC-007/008, ADR-0007/0008, PRD-010, RFC-011, ADR-0011)

- **Shipped:**
  - Run ids can't collide (0.7.0).
  - The host is outside the hash: v5 `runner` (0.6.0).
- **Partly:**
  - A code ref declared through the `fingerprint(params)` hook, kept under `deployment.declared`
    (`_fingerprint.py:447-456`); no standard name.
  - Single-run `--resume`, with no queue.
  - The atomic `<item>.txt` already serves as resume's commit marker.
- **Not built** (each searched repo-wide):
  - stages and stage metrics, per-stage references, OTLP import, `inspect --stages`;
  - JSON outputs; item fields passed to the adapter; batch mode;
  - the process adapter (JSON-RPC over stdio, `.process.yaml`, `adapter-check`);
  - declared system identity, a "wrapping a runner" recipe;
  - item failures;
  - job sets, `jobs-run`, job states, per-job timeouts, parallel runs, phases, the ssh runner, exit codes 70/75;
  - "declared, not verified" for `EVAL_BUILD_REF`.

  `sweep` is still a plain loop (`sweep.py:67-79`).
- **Superseded:**
  - `reference-create --stages`: the command was removed in 0.6.0.
  - `models.yaml` per stage: model records replaced it.
  - `arm.system`: v5 puts the system in `deployment`.
  - Every "Code:" path.

### Prompts and studies (PRD-009, RFC-009/010, ADR-0009/0010)

- **Shipped:** a hook-declared prompt hash under `settings.declared` (0.6.0), so a prompt change moves the settings
  hash. `deploy-sheet` compares it with production.
- **Not built:**
  - declared prompt files and versions, `prompt-diff`, `prompt-export`;
  - the whole study system: spec, ask/tell, samplers, stop rules, `study-confirm`, trial and study records,
    `study-import`.
- **Superseded:** RFC-009 D2 (prompts in the arm's hash).

### The evidence registry (PRD-011, RFC-012, ADR-0012)

- **Partly:**
  - `runs-list --baselines --json`;
  - `deploy-sheet` gives one promoted arm's reproduce block;
  - the goal page shows the promotion's reason.
- **Not built:** baselines per goal, write-once versions, rollback, frozen evidence, `evidence-check`, an export.
  Today it's one baseline per dataset, overwritten on promotion with "git keeps it" (`promote_baseline.py:141-145`).

### Identity, ties, looks (PRD-013, RFC-014/015, ADR-0014/0015)

- **Shipped differently:** fingerprint v5 (0.6.0, RFC-021).
  - The whole host, Python included, sits outside the hash; the draft kept Python inside.
  - The hash is over four named parts, an inclusion list rather than an exclusion list.
  - run-compare reports a runner difference, and flags speed across runners.
- **Superseded:**
  - the migration script, by `evh fingerprint-migrate`;
  - "keep v4 beside v5": v4 isn't kept;
  - "roles not renamed": they were renamed.
- **Partly:**
  - Run ids: no millisecond or random suffix.
  - The effect is printed, but the interval only appears in the inspector and forest views.
- **Not built:**
  - validate recomputing hashes;
  - baselines per goal;
  - non-inferiority ties: the 2% rule stands;
  - attainable p from non-zero differences; MDE;
  - test looks; the id grammar.

### Agent-ready, MCP, skills, record store (PRD-012, RFC-013/016/017, ADR-0013/0016/0017, UXS-004/005)

- **Shipped:**
  - `evh mcp` on the official SDK, read tools only: 23 tools, 22 with `--public`.
  - Tool schemas generated from the argparse parsers, not from a manifest.
  - The not-tools rule and its test.
  - Capped output and timeouts.
  - No command waits on a terminal.
  - Three skills, `skills-install`, and a test that runs each skill's commands.
  - A glossary, as REFERENCE.md "The same words elsewhere".
  - Python 3.10.
- **Partly:**
  - `--json` on about 26 of 67 commands, all with a generic envelope.
  - Results on stdout, except `run`'s progress without `--json`.
  - `--dry-run` on 4 commands.
  - The actor as free-text `--by` on label and reference commands only.
  - `config.yaml` read only for `catalog.adapter`.
- **Not built:**
  - one declaration per command, `evh commands --json`;
  - the exit-code table, RFC 9457 refusals, `--confirm`;
  - the actor, `EVH_ACTOR`, `--agent`;
  - the limits file, budgets;
  - writing MCP tools, cancel → kill, `outputSchema`;
  - `llms.txt`, the agent scenario test, `evh config`;
  - the record store.
- **Conflicts:** consent (the operator-asked rule against the drafts' refusal), and "prefer MCP" (the shell is
  main's path).

### 080-plan's edits to existing docs

None is on main:

- PRD-001's non-goals;
- PRD-005's amendments;
- RFC-003's `model_facts`;
- UXS-001's goal links, plus its "0.8.0 changes (draft)" section;
- UXS-002/003's draft sections;
- INFLUENCES' "The standards 0.8.0 follows" (~105 lines).

Worth porting now: the four doc items in "Small" above. The rest ports only with its feature, and only after the
vocabulary is rewritten.

## Not covered by this reconciliation

- **The test suites were not run** for any claim. "Tested" means the test file exists and is registered in
  `self_test.py`.
- **Some counts are heuristic:**
  - `--json` (≈26 of 67): from grepping `--json` in scripts plus the MCP `JSON` set;
  - help examples (38 of 67 missing): by a pattern, `evh <word>` or `make <word>` in the help text.
- **`harness/data` and most of `harness/tests` were left out** of the "not built" searches.
- **Unverified:**
  - whether the docs build still rewrites broken links to GitHub URLs (NEXT_STEPS_0.8.0 noted it);
  - NEXT_STEPS' four infra items (GlitchTip token, Umami probe rows, the podcast pin, `VLLM_API_KEY`);
  - whether 0.6.0's `HF_DATASETS_0.6.0.md` already maps Datasheets or Croissant. That is for phase 3 (datasets),
    and was not read here.
- **Not mapped:** the mockups and UXS screenshots in `research/internal/mockups-0.8.0/`.

**Re-checked by hand** (2026-11-05), each against main's code:

- `cli.py` has no `jobs-*` or `adapter-check` command.
- `Result` has no stages field (`adapter.py:41-56`).
- `identity_files`, `n_failed` and `BATCH_KEY` have no hits.
- Undeclared hook output is kept under `declared` (`_fingerprint.py:447-456`).
- V17–V20 are captures, model records, label sets and hypotheses (`validate_tree.py:35-41`).
- There is one baseline per dataset (`promote_baseline.py:141`).
- `DEFAULT_MARGIN = 0.02` (`axes.py:59`).
- Exit code 2 means the cost cap (`run.py:810`).
- `run-promote --help` prints `usage: promote_baseline.py`.
- `AGENTS.md:35-38` holds the operator-asked rule.
- `mcp_server.py` has no `outputSchema`.
