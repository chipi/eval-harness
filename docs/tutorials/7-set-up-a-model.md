# Tutorial 7 · Set up a model before you test it

An arm is a model *and how it is called*. A server chooses for everything an arm leaves unset: whether the
model reasons before it answers, how long a reply may run, which build of the weights a tag names. Those
defaults differ from model to model, so an arm that leaves them unset compares the defaults as much as the
models. This tutorial sets a model up once, in a **model record**, checks it where it runs, then smokes an arm
on a few items before its full run. The design is [RFC-020](../rfc/RFC-020-onboarding-a-model.md); every
command is in the [RUNBOOK §16](../../harness/docs/RUNBOOK.md#16-set-up-a-model-before-you-test-it).

It runs on your own machine, at no cost, with [Ollama](https://ollama.com) and a small model:

```bash
ollama pull llama3.1:8b
```

Start from the project the [GUIDE](../GUIDE.md) leaves (the tickets frozen and materialized). A server on
this machine, or on Ollama's port anywhere, needs no key: the harness asks for `OPENAI_API_KEY` only for
another address.

## 1 · A record for the model

One file per model, in `data/models/`. It says what the model is, and lists its **deployments**: each place and
build it runs, here one, on this laptop.

```yaml
# data/models/llama3.1-8b.yaml
model_id: llama3.1-8b
kind: llm
name: Llama 3.1 8B
aliases:
- llama3.1:8b          # the names runs record for it
weights: open
licence: Llama 3.1 Community License
deployments:
- id: laptop           # an arm names it with `deployment:`
  where: laptop
  tag: llama3.1:8b
  endpoint:
    provider: openai   # Ollama speaks the OpenAI API
    base_url: http://127.0.0.1:11434/v1
    model: llama3.1:8b
```

A model that runs in several places (a laptop, a GPU server, a hosted route) gets one deployment each, because
the same tag can be a different build on each, and each is checked on its own.

## 2 · Onboard it

```bash
evh model-onboard llama3.1-8b --deployment laptop
```
```text
model-onboard: llama3.1-8b (llm)
  build: the server reports 46e0c10c039e, the record None
  default settings: 2.86 s, 19 tokens out, reasoned: False, end stop
  record's settings (none): 0.46 s, 19 tokens out, reasoned: False, end stop
  JSON valid: True  deterministic: True  tokens/s: 41.5
ONBOARD PASS
  written into data/models/llama3.1-8b.yaml (deployment laptop)
```

It called the deployment the way an arm would and wrote what it found into the record: the **digest** of the
build the server is serving (so a later run can tell when it changed), whether the model **reasoned** at the
server's default and with the record's settings, whether it returns **valid JSON**, whether the same question
twice gives the **same answer**, and its speed. Your digest and timings will differ.

Llama 3.1 does not reason first, so it needs no settings. A model that does (gpt-oss, Gemma 4, Qwen 3) is set
in the record, with why, and onboarded again:

```yaml
settings:
  reasoning_effort: none
settings_why:
  reasoning_effort: it reasoned by default on the onboarding probe; off unless a task needs it
```

What a model cannot change (gpt-oss reasons at every setting; `low` is the least it takes) is accepted, with
why, so it is reported and passes rather than failing every check: `accepted: {reasoning: "<why>"}`, on the
record, or on one deployment for what only that one raises (a hosted gateway has no build to pin).

## 3 · An arm that names it

```yaml
# data/configs/tickets_llama.yaml
config_id: tickets_llama_v1
dataset_id: tickets_v1
model_record: llama3.1-8b
deployment: laptop
params:
  provider: openai
  model: llama3.1:8b
  base_url: http://127.0.0.1:11434/v1
  prompt: "Summarise this support ticket in one or two sentences."
  max_tokens: 200          # a summary is two sentences; 200 bounds a runaway
```

The record supplies the model's own settings; the arm adds the task's (its reply cap, its call limit), with a
comment saying why. A record refuses those: they would reach every other experiment's arms. Commit the record
and the arm before running, so the run records a clean tree:

```bash
git add -A && git commit -qm "llama3.1-8b, set up; an arm that names it"
```

## 4 · Smoke it

```bash
evh arm-smoke --config data/configs/tickets_llama.yaml
```
```text
arm-smoke: tickets_llama_v1 on tickets_v1, 3 item(s)
  settings: {'model': 'llama3.1:8b', 'max_tokens': 200}  · model record llama3.1-8b
  t01_login                                           2.14 s  out    381 ch  1 call(s)
      call    2.1 s  out    77 tok  reasoning      0  end stop
  ...  (t02_invoice, t03_export the same way)
  full run: 6 items, about 0.2 min (slowest item x all: 0.2 min), about $0.0
  determinism: item 1 twice gave the same output: repeats on this machine will be identical
SMOKE PASS
  written into data/models/llama3.1-8b.yaml
```

Three items, the arm's own settings, no run written: each item's time and output, whether the scorer can read
it, a projection of the full run, and every model call (tokens out, whether it reasoned, how it ended). A
`SMOKE CHECK` lists what to look at first:

| flag | means | usually |
|---|---|---|
| reasoning | a call reasoned and the arm sets no `reasoning_effort` | set it in the record |
| cut off | a reply hit `max_tokens` | raise the cap (a reasoning model counts its thinking) |
| no answer | a call failed or came back empty | the server, the model's format, or a call limit too short |
| long reply | past half the reply cap (with no cap, far past the arm's usual reply) | a cap too tight, or a model that rambles |
| slow call | over half its time limit | raise `call_timeout_s`, or a smaller model |
| determinism | the same item twice gave different outputs | expected for a hosted model; repeats will vary |

A passed smoke makes the model **vetted**: onboarded, and shown to work on a task's own items.

## 5 · Run it, and see it

```bash
evh experiment-run --config data/configs/tickets_llama.yaml
evh models
```
```text
  model        kind  where        weights  build                     deployments  settings  onboarding       arms
  llama3.1-8b  llm   self-hosted  open     llama3.1:8b@46e0c10c039e  laptop       defaults  pass 2026-10-31  1
```

The run's fingerprint takes the weights, the server and where it ran from the record's deployment, so two
runs of this arm on different builds cannot pass for one measurement. `evh models --model llama3.1-8b` prints
the record in full: each deployment, its onboarding, the settings' history, and the arms that use it. The
catalog shows the same on its **Models** page and a page per model (`evh catalog`, then
[tutorial 5](5-catalog-and-inspector.md)).
