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
| the goals page | `evh goals` | `make goals` |
| a goal page: the answer so far, arms per dataset and group (a judge's group on its score), retired marks, one line per round | `evh goals --goal <id>` | `make goals GOAL=<id>` |
| a goal page: its rounds and suggestions (each suggestion's copy button copies its command) | `evh rounds --goal <id> [--round rN]` | `make rounds GOAL=<id>` |
| a goal page: a round's **inspect** button | `evh inspect --round rN [--goal <id>]` | |
| the arms page: every arm, grouped, filtered (local / hosted, price tier) | `evh arms [--by dataset\|config\|model\|provider\|scored] [--where local\|hosted] [--tier T]` | `make arms` |
| the arms page: the configs, with their rank on each goal | `evh arms --configs` | `make arms ARGS=--configs` |
| an arm page: metrics, cost and speed, runs, config, conditions, rounds | `evh arms --arm <arm id or config id>` | `make arms ARM=<id>` |
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

## 0.5.0 changes (draft)

Draft until 0.5.0 is built; then they replace the sections above they name.

### How a command speaks (replaces the section above)

- **Results on stdout, everything else on stderr.** Progress, notes, hints and warnings go to stderr;
  stdout holds the result: the table, or with `--json` the envelope `{"command", "version", "result"}`.
  `evh <command> --json | jq .result` always works.
- **Refusals**: on stderr, `ERROR (<code>): <title>` then the detail and `fix: <command>` indented;
  with `--json`, the problem details object on stdout. The code is stable and listed on the refusals
  page. A consent refusal names the exact command the person runs, with `--confirm`:

  ```text
  ERROR (consent-required): This needs the person's consent
    Promoting run:runs/cnn_bart_l_v1_20261026T153757.123Z_7f3a to baseline of news_summary_cnn on
    cnn_dailymail_200 (replacing version 2).
    fix: evh run-promote --run run:runs/cnn_bart_l_v1_20261026T153757.123Z_7f3a --reason '…' --confirm
  ```

  The person running that command is the consent; nothing is stored in between.
- **Exit codes**: 0 done; 1 refused; 2 usage; 3 a judge scorer not validated (as in 0.4.0); 4 stopped by a
  budget or the cost cap, partial results kept; 5 partly failed (some jobs or trials); 6 a check found problems (`validate`,
  `evidence-check`, `adapter-check`, `skills-check`); 7 nothing measured; 70 an internal error; 75 try again later;
  130 interrupted. The table is printed by `evh --help` and in the Runbook.
- **Who acted**: a command that writes prints, on stderr, "recorded as person:marko" (or "agent:claude
  for person:marko", or "unknown:marko: set EVH_ACTOR to name yourself"), once.
- **`--dry-run`** on every command that writes or spends prints the plan and "nothing was written or
  called".
- **Help**: `evh --help` lists every command with its purpose and effects; `evh <command> --help`
  prints `usage: evh <command> …`, the purpose, the full description, the examples and the effects;
  `evh commands --json` is the manifest.
- Hints and notes as in 0.4.0, on stderr.

### The parity table (rows added)

| in the catalog or inspector | command |
| --- | --- |
| a goal page's baselines (now, evidence, how to reproduce, history) | `evh baselines --goal G [--dataset D] [--all-versions]` |
| (no page: a document) what a production system reads | `evh baselines --json` |
| the studies page | `evh studies [--goal G] [--period P]` |
| a study's page | `evh study-status <study> [--trials]` |
| the prompts page, a prompt's page, its changes | `evh prompts [<name>] [--period P]`, `evh prompt-diff <a> <b>` |
| the arms page's study grouping and trial rows | `evh arms --by study` |
| the arms page's quality chips | `evh arms --quality noninferior\|inconclusive\|below` |
| the goal page's heldout looks | `evh goals --goal <id> --looks` |
| the arm page's stages, prompts, build, failed items | `evh arms --arm <id>` (the same sections) |
| the inspector's stages panel | `evh inspect … --stages --item <id>` |
| a study page's confirmation | `evh study-confirm <study> --heldout <dataset> --rule <rule>` |
| a study page's suggested promotion | `evh run-promote --run <run> --reason "…" --confirm` |
| (no page) jobs | `evh jobs-status <id>`, `evh jobs-logs <id>`, `evh jobs-stop <id>` |

### The study flow

```bash
evh study-run data/studies/news_summary_cnn/s2.yaml --dry-run   # the plan and the cost
evh study-run data/studies/news_summary_cnn/s2.yaml             # returns the study id at once
evh study-status study:news_summary_cnn/s2            # trials so far, money spent, stop rule
evh study-stop study:news_summary_cnn/s2              # if needed
evh study-confirm study:news_summary_cnn/s2 --heldout cnn_dailymail_200 --rule noninferiority --dry-run
evh study-confirm study:news_summary_cnn/s2 --heldout cnn_dailymail_200 --rule noninferiority
evh run-promote --run <the suggested run> --reason "…" --confirm # the person's decision
```

- `study-run --dry-run` prints the largest number of trials, the items per trial and the estimated cost.
- `study-status` prints the outcome first (UXS-004's box, as lines), then the trials table, the money spent
  and the stop rule.
- `study-confirm --dry-run` prints the heldout items left after exclusions, the smallest p they can reach,
  the look's level and its cost, and whether it would be refused (`no-possible-evidence`).
- With `sampler: agent`: `evh study-ask study:news_summary_cnn/s2` prints the state as JSON and an `ask_id`; `evh
  study-tell study:news_summary_cnn/s2 --ask <ask_id> --proposal proposal.json` runs the trial and prints kept or dropped and
  why. A person can drive a study this way too.

### Jobs

- `evh jobs-run set.yaml` prints "job set round3-cnn started: 6 jobs, 3 at a time, on local. Follow:
  evh jobs-status round3-cnn" and returns.
- `evh jobs-status <id>` prints one line per job (state, attempts, run id, time) and the phases ("generate:
  entered; after pending" when the supervisor is gone).
- `--wait` follows until the set ends, printing each job as it finishes, and exits with the set's code.

### Onboarding

Unchanged: the GUIDE's eight steps do not meet studies, stages, jobs or the server. A tutorial 6
(a study, first driven by a built-in sampler, then by an agent through the server) follows tutorial 5.
