# Tutorial 2 · A hosted LLM, with your own key

A hosted model is one more arm in the same comparison: quality, cost and speed side by side with
the baseline and the local model of [tutorial 1](1-local-model.md). The harness calls hosted
models out of the box (the clients come with the one install); **which provider you use is your
choice, and you bring your own key.** The harness never ships, holds or shares one.

Nothing here is run by `make guide-check`: it calls a paid API.

## 1. Choose a provider

The adapter bundled with the harness (what an arm uses when the project has no `adapter.py`, and
what tutorial 1's adapter reaches through `PROVIDERS`) knows these providers. Each reads the
variables in its row, from the environment or from a `.env` file at the project root:

| `provider:` | what it calls | you set (`.env`) | in the arm's `params` |
|---|---|---|---|
| `openai` | OpenAI, or **any OpenAI-compatible endpoint** | `OPENAI_API_KEY`, or the variable `api_key_env` names | `model`; `base_url` for an endpoint other than OpenAI's (or `OPENAI_BASE_URL` in `.env`) |
| `openrouter` | OpenRouter (OpenAI-compatible), asking it for what it billed | `OPENROUTER_API_KEY` | `model` (an OpenRouter id, `vendor/model`) |
| `anthropic` | Anthropic | `ANTHROPIC_API_KEY` | `model` |
| `litellm` | your own [LiteLLM](https://docs.litellm.ai/) proxy: one key, many providers, spend tracked centrally | `LITELLM_BASE_URL` (the proxy's address) and `LITELLM_API_KEY` | `model`: the proxy's model name, not the upstream id |
| `echo` | nothing (offline, $0) | — | `sentences`, `noise` |

Every provider also takes `temperature` (default 0), `max_tokens` (default 600) and `prompt` (the
instruction put before each item). `openrouter` calls OpenRouter's address with `OPENROUTER_API_KEY`
by default; an arm's own `base_url` or `api_key_env` overrides either. A provider name the
adapter does not know is refused, never guessed.

`.env` is yours: `evh init` gitignores it, so a key in it is never committed. An exported
variable wins over the file. For example, with OpenRouter:

```text
# .env
OPENROUTER_API_KEY=sk-or-...
EVAL_MAX_COST_USD=1.00
```

`EVAL_MAX_COST_USD` is a ceiling on what one run may spend. A run that reaches it stops, keeps
everything it has, and prints the `--resume` command, so nothing is paid for twice. Then check
what the harness sees (for each key: whether it is set, its length and its last four characters;
in a checkout of this repository it also says where its example arms would be routed, a line a
project of your own does not print):

<!-- guide-check: skip -->
```bash
evh env-check
```

## 2. The arm

```yaml
# data/configs/briefs_mistral_small.yaml
config_id: briefs_mistral_small_v1
dataset_id: briefs_v1
params:
  provider: openrouter
  model: mistralai/mistral-small-3.2-24b-instruct
  temperature: 0.0
  max_tokens: 80
  prompt: "Summarise the following news brief in one sentence."
  usd_per_mtok_in: 0.1        # so the run records what it cost
  usd_per_mtok_out: 0.3
goal: brief_summary
```

With a LiteLLM proxy the same arm is `provider: litellm` and `model:` the proxy's name for it
(the newcomer scenario's was `eval-mistral-small`); with Anthropic directly, `provider:
anthropic` and an Anthropic model id. Prices live in the config, not in code: they change, and a
run records the prices it was costed at.

**What a run records as cost.** For each call, the provider's bill when the response carries one
(`usage.cost`), else the config's price table (tokens × `usd_per_mtok_in` / `usd_per_mtok_out`);
with neither, the cost is unknown, never zero:

| `provider:` | the run's cost |
|---|---|
| `openrouter` | OpenRouter's bill (the provider asks for it on every call) |
| `litellm` | the proxy's bill when it passes `usage.cost` through, as the newcomer scenario's proxy did; else the price table |
| `openai` | the price table: OpenAI's API reports tokens, not a cost (an OpenAI-compatible endpoint that returns `usage.cost` is billed) |
| `anthropic` | the price table |

So set the prices even where a bill is expected: they are the fallback, and `--dry-run` estimates
from them. The bill is what you paid; the price table is a guess, and in this repository's runs
the two differed by 0.67× to 3.76× per arm.

## 3. Price it, then run it

<!-- guide-check: skip -->
```bash
git add -A && git commit -qm "briefs: the hosted arm"
evh experiment-run --config data/configs/briefs_mistral_small.yaml --dry-run    # calls nothing
evh experiment-run --config data/configs/briefs_mistral_small.yaml --repeat 3
evh leaderboard --dataset-id briefs_v1
evh cost-report
```

The dry run prints the calls, the estimated cost and the cap. `--repeat 3` measures the arm's own
noise: a hosted model at temperature 0 is often not deterministic, and a difference smaller than
its spread is not a difference. If outputs stop at `max_tokens`, `experiment-run` warns and names
the items: they are scored as if complete, so raise `max_tokens` in a new `config_id`.

The leaderboard now shows each arm's quality, `total_cost_usd` and `latency_ms`, and its
**frontier**: the arms no other arm beats on quality, cost and speed together. `experiment-run`
prints what the command spent over every repeat (`spent $0.001063 (price table x tokens, or the
provider's bill where it sends one)`), and the repeat spread names cost and speed as what they
are (`cost, not a quality metric`), not as determinism. Each item that was billed keeps the
bill in its `_meta.usage.cost`, and `cost-report` sets each run's bill, summed from those, against
the cost it recorded, listing apart the runs with no bill (priced from the table). Runs made
before the bundled adapter kept the bill there (commit `f0c2ed3c`) read as price table only
([RUNBOOK §4](../../harness/docs/RUNBOOK.md#4-point-the-harness-at-your-system)). Then compare and choose as
before (`family-test`, `run-promote`), with the cost in the reason: "as good as X at a tenth of
the price" is a decision; "scored higher" is not yet one.

## When a run stops partway

A 429 that outlasts the retries, a crash, or the cost cap leaves the finished items on disk; each
output is written as it arrives. The run prints which run stopped, after how many items, and the
exact command to continue it:

<!-- guide-check: skip -->
```bash
evh experiment-run --config data/configs/briefs_mistral_small.yaml --resume <run_id>
```

A resumed pass calls the model only for the items that are missing. Or delete the run directory;
until one or the other, `evh validate` fails on it (V7). Retries wrap every call
(`EVAL_MAX_RETRIES`, `EVAL_RETRY_MAX_DELAY`); every variable and exit code:
[RUNBOOK](../../harness/docs/RUNBOOK.md#environment-variables).

Next: [tutorial 3](3-frontier-reference-and-judging.md) runs an expensive frontier model once and
makes its run the reference the cheaper arms are measured against.
