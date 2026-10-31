# RFC-020: Onboarding a model before an experiment

- **Status**: Draft (second, 2026-10-31), for the owner's review; proposed for 0.6.0. The owner agreed the shape
  on 2026-10-31: one general command for every arm, `evh arm-smoke`, with an LLM layer on top.
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-019](RFC-019-datasets-from-production.md) (its triage example is where the gap showed);
  RUNBOOK §16 (the manual procedure this RFC turns into tooling)

## Abstract

An arm is a model *and how it is run*: its build, its device, its settings. Leave a setting unset and a server,
a provider or a library chooses it, differently for each model, and the experiment then compares those choices
as much as the models. Nothing today checks what an arm actually does before its full run spends the time or the
money. This RFC adds an **optional onboarding step**: `evh arm-smoke`, a short run of a few items that checks any
arm (an LLM, an ML model, a baseline) and projects what the full run will cost, with an **LLM layer** that turns
on when the arm makes LLM calls; and a **model record** that keeps each model's build and chosen settings with
the smoke behind them. Nothing changes for a project that skips it.

## Motivation

### An LLM experiment: triage, 2026-10-30/31

Forty-odd arms replayed the triage fleet's production request unchanged: no reply cap, no reasoning setting, a
90 s call limit (600 s for the self-hosted ones). Measured afterwards:

- Every reasoning-capable model reasoned at its server's default: 300-900 tokens per model turn against 55-145
  for the models that do not reason, so the table compared reasoning defaults as much as models.
- gemma4:12b reasoned in a loop and never answered; its run went on for hours. Set up normally (reasoning off,
  a 1024-token cap, a 30 s limit) it ran 65 decisions in 10 minutes and ranked eighth of 52 rows, with the same score
  on two machines.
- gpt-oss:20b returned an empty reply on 15-18 of 65 decisions on every machine; ministral-3:14b on Metal hit
  Ollama's token-repeat limit on one decision, every time.
- One tag named an MLX build on the Mac and a GGUF build elsewhere; one host held a June build of a model the
  others had current.
- A second pass of a self-hosted arm at temperature 0 was byte-identical to the first: the planned repeats would
  have measured nothing.

### An ML experiment: Few-NERD

`fn_span_marker` (a fine-tuned span tagger on CPU) had a build problem of the same kind: the pinned revision was
not passed on, so a pinned config downloaded `main` (`examples/ner-few-nerd/adapter.py`, the snapshot comment).
Its output is mapped from 66 fine types to eight coarse ones (`coarsen`); a wrong mapping keeps every prediction
a valid label while retyping all of them. Neither is about reasoning; both are what a smoke of a few items, with
the build and the output distribution printed, shows before the run.

## Proposal

### 1. `evh arm-smoke --config <arm> [--items 3]`

Runs the arm's first items the way `experiment-run` would and writes no run. The report has sections; each
appears when the arm gives it something to show.

**For every arm**, from what every run already produces (the `Result`: output, time, tokens, cost, extras):

| check | flags when |
|---|---|
| runs | an item raised, or produced no output |
| valid output | the scorer cannot read an output; the output's labels or shape are not the dataset's (a distribution of the smoke's outputs is printed) |
| time, and the **full-run projection** | "65 items: about 10 min, at worst 10.8 h; about $0.04" from the smoke's mean and slowest item, and the arm's limits |
| where it ran | the build is not pinned (no digest, revision or file hash recorded), or differs from the model record |
| determinism | item 1, run twice, gives a different output (or the same: then repeats on this machine will measure nothing; `--repeat` notes it) |
| cost | per item and projected for the run, against the arm's budget |

**For an arm that calls an LLM**, from the calls a built-in provider records, or an adapter reports
(`Result.meta["calls"]: [{s, tokens_out, reasoning_tokens, finish_reason, error}]`):

| check | flags when |
|---|---|
| reasoning | a call reasoned and the arm sets no `reasoning_effort` |
| slow call | a call used more than half its time limit |
| long reply | a reply far longer than the arm's normal ones |
| cut off | `finish_reason` length: raise `max_tokens` |
| no answer | an empty reply, or a failed or timed-out call |

**For an ML arm**, the facts its adapter reports (`Result.meta`: device, precision, load time, batch size)
are printed, and load time is kept apart from per-item time in the projection.

`SMOKE PASS` or `SMOKE CHECK` with the flags; exit 0 or 1. One command, no setup: an arm gets the sections that
apply to it. The inspector shows the latest smoke on the arm's page (CLI parity). The triage example's
`smoke.py` is the first, adapter-side version of the LLM section.

### 2. The model record: `data/models/<model_id>.yaml`

One file per model a project tests, with the fields that apply to it: the build (tag and digest, or revision,
or file hash), where it runs and on what (server and its settings; device, precision), the chosen settings (for
an LLM `reasoning_effort`, `max_tokens`, the call limit; for an ML model batch size, precision), and the smoke
that chose them (its report, date, machine). A config may name it (`model_record: <id>`); `validate` then checks
the config's settings and recorded build against the record's. The catalog lists the records with the arms that
use them.

### 3. Validation, advisory

`validate` warns, never fails: an arm that names a record but differs from it; an arm whose record marks a
reasoning model and that sets no `max_tokens`; an arm with no smoke on file. A project that keeps no records sees
no warnings.

### 4. Repeats

`experiment-run --repeat` on an arm whose smoke found it deterministic says the passes will be identical on that
machine, and points at other machines or builds for spread.

## Not in scope

- Choosing settings for a project: the smoke measures and flags; a person decides.
- Pulling models or managing servers.
- Tuning prompts (the triage goal's 0.7.0 work).

## Open questions for the owner

1. Model records in `data/models/`, or inside the arm configs only?
2. 0.6.0, with the capture lane, or its own release?
