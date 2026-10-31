# UXS-003: The command line and the first evaluation

- **Status**: Active
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-001](../prd/PRD-001-experiments-and-comparison.md) (experiments),
  [PRD-007](../prd/PRD-007-packaging-and-providers.md) (one install), [PRD-004](../prd/PRD-004-catalog-and-inspector.md) (parity),
  [PRD-005](../prd/PRD-005-goals-and-rounds.md) (rounds)
- **Related RFC**: [RFC-004](../rfc/RFC-004-experiment-rounds.md) (the round commands)
- **Related UX specs**: [UXS-001](UXS-001-catalog.md), [UXS-002](UXS-002-inspector.md)
- **Implementation paths**: `harness/scripts/cli.py` (`COMMANDS`: every command, one line of
  help each), `harness/Makefile` (the same scripts as `make` targets), `docs/GUIDE.md` (the
  onboarding path, run as written by `make guide-check`)

## Summary

The harness's main surface is the terminal. One command, `evh`, with one subcommand per verb;
`evh --help` lists them and `--help` after any command gives its flags. In a checkout of this
repository each is also a `make` target running the same script. This spec covers the order in
which a newcomer meets the commands, how every command speaks (refusals, hints, exit codes), the
**parity table** that maps every catalog view and action to its command, and the flow of an
experiment round.

## Principles

- **The terminal can do everything the pages can.** The pages are a comfort ([UXS index, rule
  2](index.md#the-rules-every-surface-keeps)).
- **Refuse loudly, then say what to do.** A refusal names what is wrong and, where there is one,
  the command that fixes it.
- **The next step is printed.** A command that leads somewhere ends with the command to run next,
  in the form the user has: an evh command through `evh`, a make target in a checkout.
- **Nothing billed by surprise.** Paid commands have a `--dry-run`, a cost cap, and a printed
  `--resume`.

## Scope

**In scope:** the onboarding order, command conventions, the parity table, the round flow.

**Non-goals:** a TUI or interactive prompts; shell completion; colour in the output.

## The first evaluation (onboarding)

The [GUIDE](../GUIDE.md) is the onboarding path, offline and keyless, in the user's own project.
Every command in it was run as written, and `make guide-check` runs it again in a fresh project
on every change, comparing each quoted output. Its order is the order a newcomer meets the ideas:

| step | what the user does | commands |
| --- | --- | --- |
| 0 | set up a project with the tutorial kit | `pip install …`, `evh init --tutorial` |
| 1 | freeze a dataset | `evh dataset-create --dataset-id tickets_v1 --source-dir tutorial/tickets` |
| 2 | materialize | `evh dataset-materialize --dataset-id tickets_v1` |
| 3 | describe the arms, name the goal, commit | copy configs, `goal: tickets_summary` |
| 4 | run the best arm first (a dry run prices it) | `evh experiment-run --config data/configs/tickets_author.yaml [--dry-run]` |
| 5 | optional: make its run the reference | `evh reference-create --dataset-id tickets_v1 --from-run <run_id>` |
| 6 | run the other arms, three times each | `evh experiment-run --config … --repeat 3` |
| 7 | compare | `evh leaderboard`, `evh pair-test`, `evh family-test` |
| 8 | choose: promote a baseline, then validate | `evh run-promote --run … --reason "…"`, `evh runs-list --baselines`, `evh validate` |

The [tutorials](../tutorials/1-local-model.md) take it on from there: a local model and its own
adapter (1), a hosted model with the user's own key (2), gold, `silver-calibrate` and an LLM judge
(3, run by `make guide-check`), rounds and dataset versions (4, run), and the catalog, the
inspector and fields (5, run).

Goals appear at step 3 and rounds only in tutorial 4: a newcomer can ignore both. Deeper material is
tiered behind the GUIDE: [Concepts](../../harness/docs/CONCEPTS.md) (why),
[Runbook](../../harness/docs/RUNBOOK.md) (every flag), [Integration](../../harness/docs/INTEGRATION.md)
(your own system), [Scenario](../../harness/docs/SCENARIO.md) (a newcomer's trial with hosted
models).

## How a command speaks

- **Refusals:** `ERROR: <why>` on stderr and exit 1, e.g.
  `ERROR: no goal 'x': one of …` or "round r1 of g is still open: close it first (evh
  round-close …)". An unknown command or argument prints the usage and exits 2.
- **Exit codes** ([Runbook: exit codes](../../harness/docs/RUNBOOK.md#exit-codes)): 0 done; 1
  refused or nothing measured; 2 a usage error, or a run stopped by the cost cap with its partial
  results kept and resumable; 3 a judge scorer not validated.
- **Hints:** a command that creates something ends with `Next: <command>`, e.g. after
  `dataset-create`: `Next: evh dataset-materialize --dataset-id tickets_v1`. Through `evh` the
  hint names an evh command; in a checkout, a make target.
- **Notes:** caveats the user must read before the numbers are printed as `NOTE: …` lines (a
  filtered comparison, a spend against a budget, a rounding warning).
- **Tables:** plain aligned columns with a dashed rule, no colour, so output can be pasted and
  diffed.
- **Help:** `evh --help` lists every command with one line each (from `cli.py`'s `COMMANDS`);
  `--help` after a command lists its flags. `evh --version` prints the version.

## The parity table

Every view and action in the catalog and the inspector, and the command that gives the same
answer. Where the page has a `make` target in a checkout, it runs the same script.

| in the catalog or inspector | command | make target |
| --- | --- | --- |
| home: the tiles with their trends, goals at a glance, activity and spend, coverage, what was recorded | `evh overview [--period P]` | `make overview` |
| the activity page: runs, spend and tokens by dataset, arm and kind | `evh activity [--period P] [--arms N]` | `make activity` |
| any page's period (the chips): its in-period columns, new rows, trends | `--period P` on `evh datasets`, `goals`, `references`, `metrics`, `arms` | `ARGS='--period 30d'` |
| the datasets page | `evh datasets` | `make datasets` |
| a dataset page: arms with their cost and speed, baseline, versions, references | `evh datasets --dataset-id <id>` | `make datasets DATASET_ID=<id>` |
| a dataset page's what's inside: items, words, the gold's shape, each item's row at its source | `evh dataset-items --dataset-id <id> [--item ID]` (written by `evh dataset-profile`) | `make dataset-items DATASET_ID=<id>` |
| the goals page | `evh goals` | `make goals` |
| a goal page: the answer so far, arms per dataset and group (a judge's group on its score), retired marks, one line per round | `evh goals --goal <id>` | `make goals GOAL=<id>` |
| a goal page: its rounds and suggestions (each suggestion's copy button copies its command) | `evh rounds --goal <id> [--round rN]` | `make rounds GOAL=<id>` |
| a goal page: a round's **inspect** button | `evh inspect --round rN [--goal <id>]` | |
| the arms page: every arm, grouped, filtered (local / hosted, price tier) | `evh arms [--by dataset\|config\|model\|provider\|scored] [--where local\|hosted] [--tier T]` | `make arms` |
| the arms page: the configs, with their rank on each goal | `evh arms --configs` | `make arms ARGS=--configs` |
| an arm page: metrics, cost and speed, runs, config, conditions, rounds | `evh arms --arm <arm id or config id>` | `make arms ARM=<id>` |
| the models page: every model record, its deployments, settings, onboarding, arms (0.6.0, RFC-020) | `evh models [--kind K] [--where self-hosted\|hosted] [--status vetted\|check\|none]` | |
| a model page: its deployments and their onboarding, settings history, arms | `evh models --model <id>` | |
| (no page action) onboarding a model's deployment, smoking an arm before its run | `evh model-onboard <id> --deployment <d>`, `evh arm-smoke --config <arm>` | |
| reference pages | `evh references [--reference-id <id>]` | `make references` |
| the metrics page | `evh metrics [--dataset-id <id>]` | `make metrics` |
| a metric page: summary, details, goals, per-dataset strip chart and arms | `evh metrics --metric <metric>` | `make metrics METRIC=<metric>` |
| inspector: a comparison | `evh inspect --runs a,b [--baseline a] [--metric m]` | `make inspect RUNS=a,b` |
| inspector: filter, breakdown | `evh inspect --runs … --where field:value --by field` | |
| inspector: one item | `evh inspect --runs … --item <item_id>` | |
| inspector: the per-item table | `evh inspect --runs … --items` | |
| inspector: the analysis charts, as numbers | `evh inspect --runs … --analysis [--x <metric>]` | |
| the catalog's global search | `evh search <text>` | |
| "promote its run" (a goal page with no decision) | `evh run-promote --run <run_id> --reason "…"` | `make run-promote` |
| a suggested retirement | `evh round-retire --goal g --round rN --arm <config> --reason "…"` | `make round-retire` |
| a suggested close | `evh round-close --goal g --round rN --conclusion "…" [--promote <run_id>]` | `make round-close` |
| (no page action) opening a round | `evh round-open --goal g --dataset d …` | `make round-open` |
| building and serving the pages | `evh catalog`, `evh catalog-serve` | `make catalog`, `make catalog-serve` |

Every row has a command. Adding a view means adding its command in the same change.

**For an agent, the same rows are MCP tools** (0.5.0, `evh mcp`,
[RFC-018](../rfc/RFC-018-read-only-mcp-server.md)): every read command above is a tool with the
command's own options as its arguments, answering what the command prints (with `--json` where
the command has it). A new read command is either a tool or listed, with its reason, as not one
(`mcp_server.NOT_TOOLS`); a test fails otherwise. Not tools in 0.5.0: the commands that write,
spend or run a model, and, not yet, the report and statistics commands (`leaderboard`,
`pair-test`, `family-test`, `bootstrap-test`, `holdout`, `rank-stability`, `run-compare`,
`cost-report`).

## The round flow

Rounds are optional ([PRD-005](../prd/PRD-005-goals-and-rounds.md)). The commands, in the order
a round goes:

```bash
evh round-open --goal tickets_summary --dataset tickets_v1 \
    --hypothesis "how many leading sentences summarise a ticket best" \
    --keep tickets_lead1_v1,tickets_lead2_v1 --budget-usd 1
# add `round: r1` beside `goal:` in each new arm's config, commit, then run them
evh rounds --goal tickets_summary
evh round-retire --goal tickets_summary --round r1 --arm tickets_lead1_v1 --reason "…"
evh round-close --goal tickets_summary --round r1 --conclusion "…" --promote <run_id>
```

- `round-open` prints the round file it wrote, then, when it carried arms in: "Carried in as
  they are, their runs already count: <arms> (their configs need no change and they need not run
  again)", then "A NEW arm names the round in its config (round: r1, beside goal:
  tickets_summary) and runs; then: evh rounds --goal tickets_summary" and "Commit the round file
  before the runs: an uncommitted file makes them dirty."
- `evh rounds --goal G` prints one line per round, then the open round in full: its hypothesis,
  "on <measure>: n arm(s) in play, leader <arm>", each other arm's verdict against the leader
  with Δ and p (four decimals, as every command prints a p), `NOTE:` lines (the spend against
  the budget), and **suggested next**, each suggestion followed by its command, ready to paste.
  The close suggestion carries `--promote <run_id>` only when the leader is not already the
  baseline ("close the round with what it showed (<arm> is already the baseline)").
- A reason or a conclusion shorter than three words is refused: it must be a sentence.
- `--promote` runs `run-promote` with the conclusion as the reason; if the promotion is refused,
  the round stays open.
