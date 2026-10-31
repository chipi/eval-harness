# RFC-020: Onboarding a model before an experiment

- **Status**: Draft (first, 2026-10-31), for the owner's review; proposed for 0.6.0.
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-019](RFC-019-datasets-from-production.md) (its triage example is where the gap showed);
  RUNBOOK §16 (the manual procedure this RFC turns into tooling)

## Abstract

An arm is a model *and how it is called*. Today the harness lets a config set `max_tokens`,
`reasoning_effort` and `temperature` (`_providers.py`), but nothing asks a project to settle them, and
nothing checks what a model actually does with the settings it was given before the full run spends its
time or money. This RFC adds an **optional onboarding step**: a short **smoke** of an arm that measures
every model call and flags what to revisit, and a **model record** that keeps each model's chosen settings
and the smoke behind them. Nothing changes for a project that skips it.

## Motivation: the triage experiment, 2026-10-30/31

Forty-odd arms replayed the triage fleet's production request unchanged: no reply cap, no reasoning
setting, a 90 s call limit (600 s for the self-hosted ones). What the defaults did, measured afterwards:

- Every reasoning-capable model reasoned at its server's default: 300-900 tokens per model turn against
  55-145 for the models that do not reason, so the table compared reasoning defaults as much as models.
- gemma4:12b reasoned in a loop ("Wait, I'll try `metric`… Actually, I'll just file it.") and never
  answered; a run of it ran for hours. With `reasoning_effort: none` the same call answered in 7.7 s.
- gpt-oss:20b returned an empty reply on 15-18 of 65 decisions on every machine.
- ministral-3:14b on Metal hit Ollama's token-repeat limit on one decision, every time (temperature 0).
- One tag named an MLX build on the Mac and a GGUF build elsewhere; the DGX held a June build of a model
  the others had current.

Each was found late, by a person reading logs. Three items of smoke per arm would have shown each of them
before the run.

## Proposal

### 1. `evh smoke --config <arm> [--items 3]`

Runs the arm's first items the way `experiment-run` would, writes no run, and reports per item and per
model call: time, tokens in and out, whether the model reasoned (reasoning text or tokens, where the
provider returns them), whether an answer came back, and why the reply ended (`finish_reason`). It flags:

| flag | when | what to revisit |
|---|---|---|
| reasoning | a call returned reasoning and the arm sets no `reasoning_effort` | set it on purpose |
| slow call | a call used more than half its time limit | the limit, or the setting that makes it slow |
| long reply | a reply far longer than the arm's normal ones | reasoning, the reply cap |
| cut off | `finish_reason` length | `max_tokens` |
| no answer | an empty reply, a failed or timed-out call | reasoning, the model, the server |

`SMOKE PASS` or `SMOKE CHECK` with the flags; exit 0 or 1. CLI first; the inspector shows a smoke's
report on the arm's page (CLI parity).

**Built-in providers** are measured by the harness itself. **An adapter** that calls its own system (the
triage example replays an agent's code) opts in by reporting its calls on the `Result`
(`meta["calls"]: [{s, tokens_out, reasoning_tokens, finish_reason, error}]`); without that, the smoke
reports per item only and says so.

### 2. The model record: `data/models/<model_id>.yaml`

One file per model a project tests: the build (tag, digest, quantization, where it runs, the server and its
settings), the call settings chosen (`reasoning_effort`, `max_tokens`, call limit) and the smoke that chose
them (its report, date, machine). A config may name it (`model_record: <id>`); `validate` then checks that
the config's settings match the record's, and that a self-hosted arm's digest matches where it is recorded.
The catalog lists the records with the arms that use them.

### 3. Validation, advisory

`validate` warns, never fails, on an arm with no `max_tokens` whose model the record marks as reasoning,
and on an arm with no smoke on file. A project that keeps no records sees no warnings.

### 4. Repeats

`experiment-run --repeat` on a self-hosted arm at temperature 0 notes that its passes will be identical on
one machine (measured: 65 of 65 outputs byte-identical), and points at other machines or builds for spread.

## Not in scope

- Choosing settings for a project: the smoke reports and flags; a person decides.
- Model discovery, pulling, or managing servers.
- Tuning prompts (the triage goal's 0.7.0 work).

## Open questions for the owner

1. The command's name: `evh smoke`, or `evh arm-smoke` beside `experiment-run`?
2. Model records in `data/models/`, or inside the arm configs only?
3. 0.6.0, as part of the capture lane's release, or its own release?
