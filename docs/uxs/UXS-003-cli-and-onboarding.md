# UXS-003: The command line and the first evaluation

- **Status**: Active
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-001](../prd/PRD-001-evals-and-comparison.md) (evals),
  [PRD-007](../prd/PRD-007-packaging-and-providers.md) (one install), [PRD-004](../prd/PRD-004-catalog-and-inspector.md) (parity),
  [PRD-005](../prd/PRD-005-goals-and-rounds.md) (rounds)
- **Related RFC**: [RFC-004](../rfc/RFC-004-eval-rounds.md) (the round commands)
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
eval round.

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
| 0 | set up a project with the tutorial kit | `pip install …`, `evh init --store files --tutorial` |
| 1 | freeze a dataset | `evh dataset-create --dataset-id tickets_v1 --source-dir tutorial/tickets` |
| 2 | materialize | `evh dataset-materialize --dataset-id tickets_v1` |
| 3 | describe the arms, say what the evaluation is for, commit | `cp tutorial/systems/tickets_*.yaml data/systems/`, `cp tutorial/goals/tickets_summary.yaml data/goals/` |
| 4 | run the best arm first (a dry run prices it); the run names its goal | `evh run --system tickets_author_v1 --dataset tickets_v1 --goal tickets_summary [--dry-run]` |
| 5 | optional: make its outputs the reference (its outputs become a model's labels, which you promote) | `evh label-from-run --run <run_id> --set author_v1`, then `evh reference-promote --dataset-id tickets_v1 --labels author_v1 --tier silver --reason "…" --by <you>` |
| 6 | run the other arms, three times each (a system that already has a plain run on the dataset refuses `--repeat`; it repeats the run it has) | `evh run --system … --dataset … --goal … --repeat 3`; for the system that has a run: `evh run --system … --dataset … --purpose repeat --of <run_id>` |
| 7 | compare | `evh leaderboard`, `evh pair-test`, `evh family-test` |
| 8 | choose: promote a baseline, then validate | `evh run-promote --run … --reason "…"`, `evh baselines`, `evh validate` |

The [tutorials](../tutorials/1-local-model.md) take it on from there: a local model and its own
adapter (1), a hosted model with the user's own key (2), gold, `silver-calibrate` and an LLM judge
(3), rounds and dataset versions (4), the catalog, the inspector and fields (5), datasets from
production (6), setting up a model before it is tested (7) and the Workbench (8). `make guide-check`
runs tutorials 3, 4, 5, 6 and 8.

Goals appear at step 3 and rounds only in tutorial 4: a newcomer can ignore both. Deeper material is
tiered behind the GUIDE: [Concepts](../../harness/docs/CONCEPTS.md) (why),
[Runbook](../../harness/docs/RUNBOOK.md) (every flag), [Integration](../../harness/docs/INTEGRATION.md)
(your own system), [Scenario](../../harness/docs/SCENARIO.md) (a newcomer's trial with hosted
models).

## How a command speaks

- **Refusals:** `ERROR (<kind>): <why>` on stderr and exit 1, e.g.
  `ERROR (not-found): no goal 'x': one of …` or "round r1 of g is still open: close it first (evh
  round-close …)". The kind is one of a fixed list ([Runbook: refusals](../../harness/docs/RUNBOOK.md#refusals)),
  for a script or an agent to branch on. An unknown command or argument prints the usage and exits 2.
- **Exit codes** ([Runbook: exit codes](../../harness/docs/RUNBOOK.md#exit-codes)): one meaning
  each: 0 done; 1 refused; 2 a usage error; 3 a judge scorer not validated; 4 stopped early by the cost
  cap, the partial results kept and resumable; 5 some runs of a sweep failed; 6 the checks ran and some
  failed; 7 nothing measured; 70 an error nothing caught; 75 a server not reached; 130 interrupted.
- **Who acted:** a command that writes takes `--by person:NAME` (or `agent:NAME` with
  `EVH_FOR=person:NAME`); the default is `EVH_ACTOR`, else the terminal's user, and `unknown` with
  no terminal. A decision (promote, roll back, close a round, unseal) refuses `unknown`.
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
| home: the tiles with their trends, goals at a glance, activity and spend, coverage, what was recorded | `evh overview-show [--period P]` | |
| the activity page: runs, spend and tokens by dataset, arm and kind | `evh activity-show [--period P] [--arms N]` | |
| any page's period (the chips): its in-period columns, new rows, trends | `--period P` on `evh dataset-list`, `goal-list`, `reference-list`, `metric-list`, `arm-list` | `ARGS='--period 30d'` |
| the datasets page | `evh dataset-list` | |
| a dataset page: arms with their cost and speed, baseline, versions, references | `evh dataset-show <id>` | |
| a dataset page's what's inside: items, words, the gold's shape, each item's row at its source | `evh dataset-items <id> [--item ID]` (written by `evh dataset-profile`) | `make dataset-items DATASET_ID=<id>` |
| the goals page | `evh goal-list` | |
| a goal page: the answer so far, arms per dataset and group (a judge's group on its score), retired marks, one line per round | `evh goal-leaderboard <id>` | |
| a goal page: one line per round, with its conclusion | `evh round-list <id>` | |
| a goal page: a round as recorded (hypothesis, changes, harness, scorer, each arm's entry and runs, retirements, conclusion) | `evh round-show <id> rN` | |
| a goal page: a round's evidence (leader, tests, spend against the budget, suggestions each with its command; each suggestion's copy button copies that command) | `evh round-evidence <id> rN` | |
| a goal page's trend chart and "The evidence, drawn" (gain-cost, intervals, latency, items, rank stability, agreement) | `evh chart <kind> --goal <id> [--round rN] [--svg FILE]` | |
| a goal page's studies | `evh study-list <id>`, `evh study-show <id> <study>` | |
| a goal page: a round's **inspect** button | `evh comparison-show --round rN [--goal <id>]` | |
| the arms page: every arm, grouped, filtered (local / hosted, price tier) | `evh arm-list [--where local\|hosted] [--tier T]` (grouped by dataset, three a group, with `evh dataset-arm-list D` for the rest) | |
| the arms page: the systems, with their rank on each goal | `evh arm-list --systems 1` | |
| an arm page: metrics, cost and speed, runs, system, conditions, rounds | `evh arm-show LABEL DATASET <arm id or system id>` | |
| the models page: every model record, its deployments, settings, onboarding, arms | `evh model-list [--kind K] [--where self-hosted\|hosted] [--status vetted\|onboarded\|check\|none]` | |
| a model page: its deployments and their onboarding, settings history, arms | `evh model-show <id>` | |
| (no page action) onboarding a model's deployment, smoking an arm before its run | `evh model-onboard --model-id <id> --deployment <d>`, `evh arm-smoke --system <id> --dataset <id>` | |
| (no page action) resuming an arm that calls each item once (its adapter's `CALL_ONCE`): what may already have had its effect is listed and not called; calling those again, once each | `evh run --system <id> --dataset <id> --resume <run>`, then `… --resume <run> --recall-failed` | |
| reference set pages | `evh reference-show <tier> <name>` | |
| the Captures page | `evh capture-show ID [--json]` | |
| (no page) the project's data: the overview, a folder, find | `evh data-ls [PATH] [--find TEXT]` | |
| (no page) a file; a setting's fields | `evh data-show PATH [--fields]` | |
| (no page) saving or creating a setting | `evh data-put --path PATH --set KEY=VALUE … [--unset KEY …] [--new] [--check]`, or a whole file: `evh data-put --path PATH --file FILE` | |
| (no page) deleting a setting, or a whole run | `evh data-rm --path PATH [--dry-run]` | |
| the Labels page; a dataset page's labels | `evh label-set-list D` | |
| a dataset's failure modes (they are kept per dataset): the tag sets and how often each mode was tagged per arm | `evh tag-set-list D` | |
| (no page action) labelling: a sheet to fill, then its import | `evh label-sheet --dataset-id D --out sheet.csv [--items …] [--item ID …]`, `evh label-import --sheet sheet.csv --dataset-id D --set S --by NAME` | |
| (no page action) a run's outputs, or outcome rules, as labels | `evh label-from-run --run R --set S`, `evh label-from-capture --dataset-id D --capture C --map rules.yaml --set S` | |
| a reference's "promoted from" | `evh reference-promote --dataset-id D --labels S [--items …] --tier gold\|silver --reason "…"` | |
| scored against a label set | `evh rescore --labels D/S`, `evh run --labels D/S` | |
| a recorded arm's badge | `evh arm-from-capture --dataset-id D --capture C --as NAME` | |
| the inspector's sheet, its downloads; its selection's commands | `evh sheet-export --dataset-id D --runs A,B … [--csv FILE [--fill label\|pick\|scores]]`; `evh pick --dataset-id D --item … [--for V] [--tag k=v] [--note "…"]` | |
| (no page action) a sheet filled elsewhere, read back | `evh sheet-import --sheet sheet.csv --dataset-id D --by WHO [--kind person\|model] [--set S] [--scorer S]` | `make sheet-import ARGS="--sheet …"` |
| a dataset page's picks waiting; its selection's command | `evh picks [--for V] [--tag k=v]`, `evh pick --dataset-id D --item ITEM --drop`; `evh dataset-extend --dataset V1 --dataset-id V2 --picks`, `evh dataset-extend --dataset V1 --dataset-id V2 --pick ITEM` | |
| a promoted arm's deploy sheet | `evh deploy-sheet ARM [--capture C]` | |
| the metrics page | `evh metric-list [--dataset <id>]` | |
| a metric page: summary, details, goals, per-dataset strip chart and arms | `evh metric-show <metric> [--dataset <id>]` | |
| the prompts page; a prompt's versions; two versions compared | `evh prompt-list`, `evh prompt-show --name N [--text]`, `evh prompt-diff A B` | |
| the scorers page; a scorer's page | `evh scorer-list`, `evh scorer-show <id>` | |
| the baselines: a dataset page's baseline box and its history | `evh baselines [--goal G] [--dataset D] [--all-versions]` | |
| a test set's looks | `evh looks [--dataset D]` | |
| a model's deployed periods | `evh periods <model>` | |
| inspector: a comparison | `evh comparison-show --runs a,b [--baseline a] [--metric m]` | |
| inspector: filter, breakdown | `evh comparison-show --runs … --where field:value --by field` | |
| inspector: one item | `evh comparison-item --runs … --item <item_id>` | |
| inspector: the per-item table | `evh sheet-show D --runs …` (the sheet; `--scores-only`) | |
| inspector: the analysis charts, as numbers | `evh comparison-show --runs … --analysis [--x <metric>]` | |
| the catalog's global search | `evh search <text>` | |
| "promote its run" (a goal page with no decision) | `evh run-promote --run <run_id> --reason "…"` | `make run-promote` |
| a suggested retirement | `evh round-retire --goal g --round rN --arm <system> --reason "…"` | `make round-retire` |
| a suggested close | `evh round-close --goal g --round rN --conclusion "…" [--promote <run_id>]` | `make round-close` |
| (no page action) opening a round | `evh round-open --goal g --dataset d … [--adopt] [--keep all] [--scoring "…"]` | `make round-open` |
| a round's scorer and its scoring changes (the goal page's round section) | `evh round-show g rN` | |
| (no page action) what a scoring change would move | `evh score-preview --goal g [--round rN]` | |
| (no page action) re-scoring a round | `evh rescore --goal g --round rN --why "…"` | `make rescore` |
| building and serving the pages | `evh catalog`, `evh catalog-serve` | `make catalog`, `make catalog-serve` |

Every row has a command. Adding a view means adding its command in the same change.

**For an agent, the same rows are MCP tools**
([RFC-018](../rfc/RFC-018-read-only-mcp-server.md)): every read operation above is a tool with the
command's own options as its arguments, answering what the command prints (with `--json` where
the command has it); `leaderboard`, `pair-test`, `family-test`, `rank-stability` and
`run-compare` are tools too. A new read command is either a tool or listed, with its reason, as
not one (`mcp_server.NOT_TOOLS`); a test fails otherwise. Not tools: the commands that write,
spend or run a model (among them the work operations `bootstrap-test`, `holdout` and
`cost-report`), the `jobs-*` commands, `init`, `catalog-serve` and the like.

## The round flow

Rounds are optional ([PRD-005](../prd/PRD-005-goals-and-rounds.md)). The commands, in the order
a round goes:

```bash
evh round-open --goal tickets_summary --dataset tickets_v1 \
    --hypothesis "how many leading sentences summarise a ticket best" \
    --keep tickets_lead1_v1,tickets_lead2_v1 --budget-usd 1
# commit the round file, then run each new system in it: evh run --system <id> --dataset tickets_v1 --goal tickets_summary --round r1
evh round-list tickets_summary
evh round-show tickets_summary r1
evh round-evidence tickets_summary r1
evh round-retire --goal tickets_summary --round r1 --arm tickets_lead1_v1 --reason "…"
evh round-close --goal tickets_summary --round r1 --conclusion "…" --promote <run_id>
```

- `round-open` prints the round file it wrote and "round rN of G, open", then "It starts from X."
  (the baseline run; without one, "It starts from no baseline run (none promoted; --baseline names
  one)."), "On harness V … code …" (the harness version, its commit when it is a checkout, the
  first 12 characters of its code hash), and, when it carried arms in: "Carried in as they are,
  their runs already count: <arms> (they need not run again).", then "A NEW system joins it by
  running in it: evh run --system <id> --dataset D --goal G --round rN; then: evh round-evidence G
  rN" and "Commit the round file before the runs: an uncommitted file makes them dirty." An arm of
  the round before is carried with its runs only when that round was on the same dataset; any
  other system is read through its plain runs on the round's dataset.
- `evh round-list G` prints a line per round (status, dataset, arms in play and retired), with its
  conclusion under it. `evh round-show G rN` prints one round as recorded: its hypothesis,
  changes, harness, scorer, each arm (how it entered, its runs, its retirement) and its
  conclusion. `evh round-evidence G rN` prints what the evidence says: "rN on <measure>: n arm(s)
  in play, leader <arm>", each other arm's verdict against the leader with Δ and p (four
  decimals, as every command prints a p), the tests of the leader against earlier arms, `NOTE:`
  lines (the spend against the budget, runs made "since then" that the round does not read), and
  `next:` lines, each suggestion followed by its command, ready to paste. The close suggestion
  carries `--promote <run_id>` only when the leader is not already the baseline and the evidence puts it ahead ("close
  the round with what it showed (<arm> is already the baseline)", otherwise "promoting nothing: <arm> is <reason>").
- A reason or a conclusion shorter than three words is refused: it must be a sentence.
- `--promote` runs `run-promote` with the conclusion as the reason; if the promotion is refused,
  the round stays open.
