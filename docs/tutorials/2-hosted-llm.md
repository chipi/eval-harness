# Tutorial 2 · A hosted LLM, with your own key

A hosted model is one more arm in the same comparison: quality, cost and speed side by side with
the baseline and the local model of [tutorial 1](1-local-model.md). The harness calls hosted
models out of the box (the clients come with the one install); **which provider you use is your
choice, and you bring your own key.** The harness never ships, holds or shares one.

Nothing here is run by `make guide-check`: it calls a paid API.

## 1. Choose a provider

The adapter bundled with the harness (what an arm uses when the project has no `adapter.py`, and
what tutorial 1's adapter reaches through `PROVIDERS`) knows these providers. The same providers
are used by judges (in `judge-score` and the judge panel). Each provider reads the variables
in its row, from the environment or from a `.env` file at the project root. Arms read `<NAME>`;
judges read `EVAL_JUDGE_<NAME>` first (for their own keys or spending), then fall back to `<NAME>`
when judging shares the arms' credentials.

| `provider:` | what it calls | arms read | judges read |
|---|---|---|---|
| `openai` | OpenAI, or **any OpenAI-compatible endpoint** | `OPENAI_API_KEY`; `OPENAI_BASE_URL` (optional, else the default endpoint) | `EVAL_JUDGE_OPENAI_API_KEY` or `OPENAI_API_KEY`; `EVAL_JUDGE_OPENAI_BASE_URL` or `OPENAI_BASE_URL` |
| `openrouter` | OpenRouter (OpenAI-compatible), asking it for what it billed | `OPENROUTER_API_KEY` | `EVAL_JUDGE_OPENROUTER_API_KEY` or `OPENROUTER_API_KEY` |
| `anthropic` | Anthropic | `ANTHROPIC_API_KEY`; `ANTHROPIC_BASE_URL` (optional) | `EVAL_JUDGE_ANTHROPIC_API_KEY` or `ANTHROPIC_API_KEY`; `EVAL_JUDGE_ANTHROPIC_BASE_URL` or `ANTHROPIC_BASE_URL` |
| `litellm` | your own [LiteLLM](https://docs.litellm.ai/) proxy: one key, many providers, spend tracked centrally | `LITELLM_API_KEY`; `LITELLM_BASE_URL` (required; the proxy's address) | `EVAL_JUDGE_LITELLM_API_KEY` or `LITELLM_API_KEY`; `EVAL_JUDGE_LITELLM_BASE_URL` or `LITELLM_BASE_URL` |
| `echo` (arms only) | nothing (offline, $0) | — | — |
| `fake` (judges only) | a stand-in for testing (offline, $0) | — | — |

Every provider takes `model`, `temperature` (default 0), `max_tokens`, `base_url` (an address
that overrides the environment's) and `api_key_env` (another variable to read the key from).
`model` is the provider's own name for it: on OpenRouter the id on the model's page; on an
OpenAI-compatible endpoint or a LiteLLM proxy, an id its model list returns
(`curl -s -H "Authorization: Bearer $LITELLM_API_KEY" "$LITELLM_BASE_URL/v1/models"`).
The OpenAI-shaped ones (`openai`, `openrouter`, `litellm`) also send `reasoning`,
`reasoning_effort` and `provider_routing` in the request body; `anthropic` refuses them. An arm
also takes `prompt`, the instruction put before each item. A provider name the harness does not
know is refused, never guessed.

`.env` is yours: `evh init` gitignores it, so a key in it is never committed. An exported
variable wins over the file. For example, with OpenRouter:

```text
# .env
OPENROUTER_API_KEY=sk-or-...
EVAL_JUDGE_OPENROUTER_API_KEY=sk-or-...    # judges' own key (optional; omit to share the arms')
EVAL_MAX_COST_USD=1.00
```

`EVAL_MAX_COST_USD` is a ceiling on what one run may spend. A run that reaches it stops, keeps
everything it has, and prints the `--resume` command, so nothing is paid for twice. Then check
what the harness sees: for each provider and variable, whether arms can call it, which key
judges use (their own EVAL_JUDGE_* key, the arms' key, or nothing):

<!-- guide-check: skip -->
```bash
evh env-check
```

With only the `.env` above (and the judges' own OpenRouter key), its provider table reads:

```text
  provider    variable             arms                               judges
  openai      OPENAI_API_KEY       not set                            not set
              OPENAI_BASE_URL      not set (the default address)      not set (the default address)
  anthropic   ANTHROPIC_API_KEY    not set                            not set
              ANTHROPIC_BASE_URL   not set (the default address)      not set (the default address)
  openrouter  OPENROUTER_API_KEY   set (73 chars, ends …a1b2)         own: set (73 chars, ends …c3d4)
  litellm     LITELLM_API_KEY      not set                            not set
              LITELLM_BASE_URL     not set                            not set
  arms can call: openrouter
  judges can call: openrouter
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
