# Reproduce it

Everything this repository claims can be checked by someone who is not its author, at
whatever depth they have time and money for. Five levels, each optional, each a few
commands from the repository root.

| level | what you check | you need | costs |
|---|---|---|---|
| **0 · verify** | every number in every report, recomputed from the committed predictions | a clone | $0, ~15 min |
| **1 · data** | the public data still matches what was measured, byte for byte | network | $0, minutes |
| **2 · local** | rerun every local model and baseline on your own CPU | disk for models | $0, CPU hours |
| **3 · hosted** | rerun the 24 hosted LLMs | one OpenRouter key | what `make plan` says, ≈ $0.60–$7.03 per experiment as billed when measured; prices move |
| **4 · extend** | measure a model of your own against the whole committed field | a config file | your model |

You need `git`, `make`, Python ≥ 3.11 and [uv](https://docs.astral.sh/uv/) (`curl -LsSf
https://astral.sh/uv/install.sh | sh`). Each worked example has its own uv environment so
its pinned libraries cannot disturb another's.

```bash
git clone https://github.com/chipi/eval-harness && cd eval-harness
make list                         # the seven measurements, their arms, what they billed
```

## 0 · Verify — trust nothing, recompute everything ($0)

```bash
make verify
```

Rebuilds the harness environment and runs `make ci`: validates every committed run
against its schema and fingerprint, re-derives every figure quoted in the reports from the
stored predictions (`check_report_claims`), checks every link, every model fact against
its captured evidence, and that the public site matches a fresh build from the runs. The
checks are themselves tested: the suite plants a wrong number in a report and fails if the
check does not catch it.

This proves the reports say what the runs say. It does not prove the runs are right —
that is what the next levels are for.

## 1 · Data — is it still the same data? ($0)

```bash
make data EXP=scifact             # or any experiment from `make list`
```

Creates the example's environment, downloads its slice of the public benchmark from the
Hugging Face datasets API (no corpus is committed — licences), and hashes every item
against the committed dataset file. A mismatch stops here: a rerun on different bytes
would be a different experiment wearing the same name.

## 2 · Local — rerun the free arms ($0)

```bash
make plan      EXP=scifact LEVEL=local     # arms, how long each took, what is installed
make reproduce EXP=scifact LEVEL=local
make compare   EXP=scifact
```

`LEVEL=baselines` runs only the floors (seconds); `ARMS=bm25,e5_base` picks arms by name.
Reruns go to `harness/data/runs-repro/<experiment>/`, which is gitignored and never
mixed with the committed runs — those stay the record.

Model weights download from Hugging Face on first use, at the revision the committed run
pinned (sizes in [REFERENCE](REFERENCE.md)). Five of them were measured from pickle
checkpoints (`pytorch_model.bin`), which execute code when loaded and which torch < 2.6
refuses; for those a rerun loads the model's **safetensors conversion** instead, pinned by
commit in `examples/local_models.json`. Each was rerun that way on 2026-10-15 and scored
identically to its committed run on every item, all 200 or 280 (lab notebook entry 63; an
earlier adapter-level check covered the two BARTs on 20 items only). The sixth pickle model,
`bart_s`, has no exact conversion; rerun at the fp32 its config declares, it matches 199 of
200 items on CNN and 187 of 200 on DailyMail. On Linux, `uv` installs the CUDA build of
PyTorch, about 5 GB; nothing here needs a GPU.

**What to expect.** A local model with pinned weights and a fixed input should give the
same answers, and the replication card reports exact agreement item by item. Small
differences can come from a different CPU or library build; the card then shows whether
they are distinguishable from the committed run (a paired permutation test) and whether
any finding moved. Latency depends on your hardware and is not compared.

## 3 · Hosted — rerun the LLMs (one key)

Put an [OpenRouter](https://openrouter.ai/) key in `harness/.env`:

```bash
cp harness/.env.example harness/.env       # then set OPENROUTER_API_KEY=sk-or-...
make -C harness env-check                  # says which route the hosted arms will take
make plan      EXP=ag-news LEVEL=hosted    # what it billed when measured, arm by arm
make reproduce EXP=ag-news LEVEL=hosted
make compare   EXP=ag-news
```

The example configs name models by alias (`eval-claude-sonnet`); `examples/models.json`
maps each alias to the OpenRouter model it named when the runs were made, and the request
goes straight to OpenRouter. If you run a [LiteLLM](https://docs.litellm.ai/) proxy instead,
`examples/litellm.config.yaml` serves the same aliases; set `LITELLM_BASE_URL` and
`LITELLM_API_KEY` and the proxy route is used.

Each hosted arm is capped at twice what it was billed when measured
(`EVAL_MAX_COST_USD`, enforced on actual spend); a run that hits the cap stops, keeps what
it has, and prints a `--resume` line so nothing is paid for twice.

**What to expect.** Not the same digits. A hosted model is not deterministic even at
temperature 0; OpenRouter may route the request to a different provider than it did; and
a model can be updated or retired under the same id. So the card asks the question the
reports actually make claims about: **does every separation and every tie still hold?** It
substitutes your reruns for the committed runs and re-tests the leader against the same
family, with the same Holm correction. Per arm it also reports whether your rerun is
distinguishable from the committed one, whether the upstream model id changed, and which
provider served it.

## 4 · Extend — your model against the field

Copy any hosted config in the experiment's `configs/` directory, give it a new
`config_id` (keep the prefix and suffix, e.g. `sf_mymodel_n200_v1`), and set `model:` to
any OpenRouter id (`vendor/model`). Then:

```bash
make reproduce EXP=scifact CONFIG=examples/retrieval-scifact/configs/arm_mymodel_n200.yaml
make compare   EXP=scifact
```

The card ranks your arm in the committed field and tests it against every committed arm,
Holm-corrected — so "better than X" means *separated from* X, not *scored above* it. For a
system that is not an OpenAI-compatible endpoint, write an adapter instead:
[INTEGRATION](../harness/docs/INTEGRATION.md) is the four-function contract.

## The replication card

`make compare` writes `harness/data/runs-repro/<experiment>/REPLICATION.md`:

| column | meaning |
|---|---|
| committed / rerun | the arm's mean score on the items both runs scored |
| identical items | items scored exactly the same |
| paired p | can the rerun be told apart from the committed run? (sign-flip permutation, 10,000 draws) |
| upstream | for a hosted arm, whether the model id behind the alias changed |
| status | `exact` · `consistent` (hosted, not distinguishable) · `within noise, not exact` (local) · `DIFFERS` |

Then the verdicts: how many arms are separated from the leader and how many tied, in the
committed record and with your reruns substituted in, and any arm that moved. `make
compare` exits non-zero when a verdict moved or an arm differs.

## What a rerun cannot reproduce

- **Retired models.** When a hosted model is withdrawn, its committed predictions remain
  the only record of it. That is why they are committed.
- **Silent upstream updates.** OpenRouter can update a model in place. The card's upstream
  column catches a changed id, not changed weights under the same id; a `DIFFERS` on a
  hosted arm with the same id is the signature of one.
- **The provider route.** Open-weight models are served by several providers, sometimes at
  different precisions. Every response records which provider answered; pin one with
  `provider_routing` in the config if you need to.
- **Latency.** Hardware- and load-dependent. Reported, never compared.

Found something that does not hold? That is the most useful thing this repository can
receive — open an issue with your `REPLICATION.md`.
