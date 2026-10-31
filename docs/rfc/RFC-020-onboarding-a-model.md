# RFC-020: Onboarding models, once, for every experiment

- **Status**: Built for 0.6.0 (2026-10-31), from its third draft. The owner's decisions of 2026-10-31: a model is
  onboarded once for the project and reused by every experiment; records live in `data/models/`; one general
  command checks an arm on its own task, `evh arm-smoke`, with an LLM layer on top; the catalog gets a Models
  page; it ships in 0.6.0.
- **Authors**: Marko Dragoljevic
- **Related**: [PRD-015](../prd/PRD-015-models-onboarded-once.md), [ADR-0021](../adr/ADR-0021-a-deployment-is-vetted.md); [RFC-019](RFC-019-datasets-from-production.md) (its triage example is where the gap showed);
  [UXS-001](../uxs/UXS-001-catalog.md) (the Models page); RUNBOOK §16 (the procedure)

## Abstract

An arm is a model *and how it is run*: its build, where it runs, its settings. Leave a setting unset and a
server, a provider or a library chooses it, differently for each model, and the experiment then compares those
choices as much as the models. This RFC makes setting a model up a project's own, reusable step, in two levels:

1. **Onboard a model, once.** `evh model-onboard` writes its **model record** (`data/models/<id>.yaml`): the
   build on every machine that runs it, what it can do, the settings chosen for it, and a task-independent smoke
   behind them. The model is then ready for any experiment, and listed on the catalog's **Models** page.
2. **Use it in an experiment.** An arm names the record and inherits its build and settings, overriding only what
   its task needs; **`evh arm-smoke`** checks the arm on its own task's items (valid output for its scorer, time,
   a projection of the full run) before the run spends anything.

Both are optional: a project that onboards nothing and smokes nothing sees no change.

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

### 1. The model record: `data/models/<model_id>.yaml`

One file per model the project uses, with the fields that apply to its kind (`llm`, `ml`, `baseline`):

- **deployments** (RFC-021), one per place and way it runs, each with an `id` (`mac`, `dgx`,
  `openrouter-nebius`): where (the machine or host), the server and its settings (version, context length, KV
  cache) or the device and backend, the build there (the tag and digest, the revision, or a file hash; the
  quantization or precision), for a hosted model the provider id and the route it is pinned to, the endpoint to
  probe it through, when it was last checked, and **its own onboarding**: the same weights behave differently on
  different hardware, so each deployment is vetted on its own.
- **capabilities**, measured: for an LLM whether it reasons and whether reasoning can be turned off (and how:
  `reasoning_effort: none`, or only low / medium / high), JSON mode, context length; for an ML model its labels
  or output shape.
- **settings**, chosen: what holds whatever the task. For an LLM `reasoning_effort` (or `reasoning`); for an ML
  model device, precision, batch size. With one line on why each was chosen. A reply cap, a call limit and a
  temperature are a task's, so its arms set them; the schema refuses them in a record (review, 2026-10-31: a
  record's triage-sized cap would otherwise reach every other experiment's arms).
- **history**: each change of build or settings, with its date and why.

`validate` checks the schema, and that every arm naming a record exists in `data/models/`.

**It replaces `data/models.yaml`.** That file keys each model a run records (`params.model`) to its weights (open
or proprietary) and licence, for the arms page's weights filter (`models.schema.json`). Its entries move into the
records (`weights`, `licence`, and `aliases`: the ids runs record for the model, `eval-gemma-31b` and
`gemma4:31b` alike), the file and its schema go, and the weights filter reads the records. No second file and no
shim: the committed data is migrated (0.6.0's rule for formats nobody depends on yet).

### 2. Onboarding: `evh model-onboard <model_id> --deployment <id>`

Task-independent, once per deployment, and again when its build changes. It probes the model through that
deployment's endpoint with a few fixed requests of its kind and writes the result into the deployment (an ML
model or a baseline is onboarded through an arm that runs it, `--config <arm.yaml>`):

| probe | what it records, and flags |
|---|---|
| build | the digest, revision or hash on each machine; **differs between machines** is flagged |
| speed | tokens per second (LLM), items per second and load time (ML) |
| reasoning (LLM) | whether it reasons by default; whether the record's setting turns it off; a loop or an unbounded reply is flagged |
| format (LLM) | whether JSON mode returns valid JSON |
| determinism | the same request twice gives the same output, or not (repeats on that machine measure nothing, or something) |
| cut off | the probe's reply against the probe's own 1024-token cap; a task's caps and call limits are its arms', checked by `evh arm-smoke` (long, slow, cut off) |

`ONBOARD PASS` or `ONBOARD CHECK` with the flags. A hosted model is onboarded the same way, through its gateway.

### 3. An arm uses a record: `model_record: <model_id>` and `deployment: <id>`

An arm's config names the record instead of repeating it, and the deployment it runs on; its `params` inherit
the record's settings, override what the task must, and add its own (its reply cap, its call limit). The run
records `model_record` and `deployment_id`, and its fingerprint's deployment part comes from that deployment
(RFC-021), so a result can always be traced to the build and the machine it ran on.

### 4. `evh arm-smoke --config <arm> [--items 3]`

Task-specific, once per arm before its first full run: runs the arm's first items the way `experiment-run`
would and writes no run. Every arm gets the general checks, from what every run already produces (the `Result`):

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
| long reply | a reply past half the arm's `max_tokens`; with no cap, far longer than the arm's normal ones |
| cut off | `finish_reason` length: raise `max_tokens` |
| no answer | an empty reply, or a failed or timed-out call |

**For an ML arm**, the facts its adapter reports (`Result.meta`: device, precision, load time, batch size)
are printed, and load time is kept apart from per-item time in the projection.

`SMOKE PASS` or `SMOKE CHECK` with the flags; exit 0 or 1. One command, no setup: an arm gets the sections that
apply to it. The inspector shows the latest smoke on the arm's page (CLI parity). The triage example's
`smoke.py` was the first, adapter-side version of the LLM section; `evh arm-smoke` replaced it.

The report is written into the record's `smokes`, by the arm's config id, so the Models page can show which
arms were smoked, and a model counts as vetted once one of them passed.

### 5. The catalog: a Models page, and a page per model (UXS-001)

- **Models** (`models.html`): one row per record: the model and its kind, its deployments' builds (marked when
  the same tag is a different build on two deployments), where it runs, the chosen settings, the onboarding
  (vetted when every deployment's onboarding passed and an arm's smoke passed; onboarded when the onboarding
  passed and no arm has been smoked; to check when an onboarding flagged something; not onboarded otherwise), the
  arms and goals
  that use it, and their best result. Filters: kind, self-hosted / hosted, open / proprietary, onboarding status,
  builds differ.
- **A model's page**: each deployment with its build, its server or device, whether it matches, and its own
  onboarding report; the settings' history (`at`, `what`, `from`, `to`, `why`); its arms, each with its arm smoke.
- **The arms page** gets a badge per arm that has a record: its record and deployment, and "smoked", "smoke:
  check" or "not smoked".
- **CLI parity**: `evh models [--kind] [--where] [--status]` lists the same; `evh models --model <id>` shows one.

*Added while onboarding the triage models (2026-10-31):* a record's `accepted` names flag kinds a person accepted
as the model's own nature, with why (gpt-oss cannot stop reasoning; `low` is the least it takes): onboarding and arm
smokes report them as `accepted` and pass. A deployment may accept kinds of its own (a hosted gateway: `where it ran`,
no build to pin; `determinism`, repeats vary), read only for that deployment's smokes. A reply cap sets what is long
(past half the cap): against the median, an agent's short probe calls made every answer long. Commands that write a record re-read it under a lock and change only their
part (`_models.update_record`), since probing one model on three machines at once is ordinary.

*Not built as first written:* the settings history has no "smoke / result before and after" columns (a history
entry links to neither); an arm whose model has no record is not a row on the Models page.

### 6. Validation, advisory

`validate` notes, never fails: an arm never smoked; a reasoning model's arm with no `max_tokens`; a tag that is a
different build on two deployments. A project that keeps no records sees no notes. (*Not built:* a note for an arm
whose settings differ from its record's: an arm overriding a record is allowed, and the run records both.)

### 7. Repeats

`experiment-run --repeat` on an arm whose record found its model deterministic on that machine says the passes
will be identical there, and points at other machines or builds for spread.

## Not in scope

- Choosing settings for a project: onboarding and the smoke measure and flag; a person decides.
- Pulling models or managing servers.
- Tuning prompts (the triage goal's 0.7.0 work).

## The first records

The triage experiment's models, about 25, are onboarded from what is already measured and a probe each where it
is not: their builds on X3, the DGX and the Mac, their reasoning, and the settings round 2 of `triage_orrery`
runs them with.
