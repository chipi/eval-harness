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
in its row, from the environment or from a `.env` file at the project root. Arms and judges read the
same variables, so judging shares the arms' credentials unless a judge is given its own (below).

| `provider:` | what it calls | reads |
|---|---|---|
| `openai` | OpenAI, or **any OpenAI-compatible endpoint** | `OPENAI_API_KEY`; `OPENAI_BASE_URL` (optional, else the default endpoint) |
| `openrouter` | OpenRouter (OpenAI-compatible), asking it for what it billed | `OPENROUTER_API_KEY` |
| `anthropic` | Anthropic | `ANTHROPIC_API_KEY`; `ANTHROPIC_BASE_URL` (optional) |
| `litellm` | your own [LiteLLM](https://docs.litellm.ai/) proxy: one key, many providers, spend tracked centrally | `LITELLM_API_KEY`; `LITELLM_BASE_URL` (required; the proxy's address) |
| `echo` (arms only) | nothing (offline, $0) | — |
| `fake` (judges only) | a stand-in for testing (offline, $0) | — |

**One address variable.** `LITELLM_BASE_URL` is the one variable the harness reads for a LiteLLM proxy's
address; there is no second name for it. A key file minted by the homelab carries it beside the key, so a
system that names that file as its `key_file` needs no `base_url`. A key file that lacks `LITELLM_BASE_URL`
needs the address from elsewhere: `base_url:` in the system's params, or the variable in the shell or `.env`.

**A key of its own: `key_file`.** A system, or a judge, may name `key_file: PATH` in its params: a file in
dotenv format (`NAME=value` per line; a path from the project root, or absolute; `~` is expanded) that is the only
place its provider's key is read from. A `key_file` that lacks the key variable is refused before any call,
naming the file and the variable: the shell's or `.env`'s key is never used in its place (0.8.3; 0.8.2 fell
through to it). That is how judging pays from its own key and budget: a judge is a system, so it names its own
`key_file`, or names a system that does (`system: <system_id>` in the scorer). Name the system rather than
writing `key_file` into a scorer that has judged scores: a scorer is hashed as written, and a changed scorer is
a new scorer. Where a key is kept is in no fingerprint: the judge's is the same with its key in a file or in the
environment.

`EVAL_JUDGE_<NAME>` (a judge's own variable, read before `<NAME>`) is the old way and is **deprecated**: still
read, with one warning per run that names the `key_file` way, and removed in 0.9.0.

Every provider takes `model`, `temperature` (default 0), `max_tokens`, `base_url` (an address
that overrides the environment's) and `api_key_env` (another variable to read the key from).
`model` is the provider's own name for it: on OpenRouter the id on the model's page; on an
OpenAI-compatible endpoint or a LiteLLM proxy, an id its model list returns
(`curl -s -H "Authorization: Bearer $LITELLM_API_KEY" "$LITELLM_BASE_URL/v1/models"`). The ids
are the proxy's own, set by whoever runs it, and a proxy can serve dozens: list them, do not guess.
The OpenAI-shaped ones (`openai`, `openrouter`, `litellm`) also send `reasoning`,
`reasoning_effort` and `provider_routing` in the request body; `anthropic` refuses them. An arm
also takes `prompt`, the instruction put before each item. A provider name the harness does not
know is refused, never guessed.

`.env` is yours: `evh init` gitignores it, so a key in it is never committed. An exported
variable wins over the file. For example, with OpenRouter:

```text
# .env
OPENROUTER_API_KEY=sk-or-...
EVAL_MAX_COST_USD=1.00
```

`EVAL_MAX_COST_USD` is a ceiling on what one run may spend. A run that reaches it stops, keeps
everything it has, and prints the `--resume` command, so nothing is paid for twice. Then check
what the harness sees: for each provider and variable, whether arms can call it, whether judges
can (with the arms' key, or the deprecated `EVAL_JUDGE_*` one), and, for each system or judge
that names a `key_file`, where its key comes from:

<!-- guide-check: skip -->
```bash
evh env-check
```

With only the `.env` above, its provider table reads:

```text
.env: loaded 2 var(s)   (/path/to/your/project/.env)

hosted providers (a system's `provider:`): an arm reads <NAME>; a judge its own `key_file`, else
EVAL_JUDGE_<NAME> (deprecated, removed in 0.9.0) first and the arms' <NAME> when that is not set
  provider    variable             arms                                           judges
  openai      OPENAI_API_KEY       not set                                        not set
              OPENAI_BASE_URL      not set (the default address)                  not set (the default address)
  anthropic   ANTHROPIC_API_KEY    not set                                        not set
              ANTHROPIC_BASE_URL   not set (the default address)                  not set (the default address)
  openrouter  OPENROUTER_API_KEY   set (73 chars, ends …a1b2) (.env)              the arms'
  litellm     LITELLM_API_KEY      not set                                        not set
              LITELLM_BASE_URL     not set                                        not set
  arms can call: openrouter
  judges can call: openrouter
```

## 2. The system

```yaml
# data/systems/briefs_mistral_small_v1.yaml
system_id: briefs_mistral_small_v1
params:
  provider: openrouter
  model: mistralai/mistral-small-3.2-24b-instruct
  temperature: 0.0
  max_tokens: 80
  prompt: "Summarise the following news brief in one sentence."
  usd_per_mtok_in: 0.1        # so the run records what it cost
  usd_per_mtok_out: 0.3
```

A `prompt:` that contains `: ` (a colon and a space) must stay quoted, as this one is: unquoted, the
file is not YAML and `evh run` refuses it (`invalid-file`, naming the file and the line). For example,
`prompt: "Answer in two lines: label: <intent>"`.

With a LiteLLM proxy the same system is `provider: litellm` and `model:` the proxy's name for it
(for example `eval-mistral-small`, `eval-opus-5`, `eval-gemma-31b`, `eval-qwen-flash` or
`eval-llama-scout`); with Anthropic directly, `provider:
anthropic` and an Anthropic model id. Prices live in the system, not in code: they change, and a
run records the prices it was costed at.

**What a run records as cost.** For each call, the provider's bill when the response carries one
(`usage.cost`), else the system's price table (tokens × `usd_per_mtok_in` / `usd_per_mtok_out`);
with neither, the cost is unknown, never zero:

| `provider:` | the run's cost |
|---|---|
| `openrouter` | OpenRouter's bill (the provider asks for it on every call) |
| `litellm` | the proxy's bill when it passes `usage.cost` through; else the price table |
| `openai` | the price table: OpenAI's API reports tokens, not a cost (an OpenAI-compatible endpoint that returns `usage.cost` is billed) |
| `anthropic` | the price table |

So set the prices even where a bill is expected: they are the fallback, and `--dry-run` estimates
from them. The bill is what you paid; the price table is a guess, and in this repository's runs
the two differed by 0.67× to 3.76× per arm.

## 3. Price it, then run it

<!-- guide-check: skip -->
```bash
git add -A && git commit -qm "briefs: the hosted system"
evh run --system briefs_mistral_small_v1 --dataset briefs_v1 --goal brief_summary --dry-run    # calls nothing
evh run --system briefs_mistral_small_v1 --dataset briefs_v1 --goal brief_summary --repeat 3
evh leaderboard briefs_v1
evh cost-report
```

The dry run prints the calls, the estimated cost and the cap. `--repeat 3` measures the arm's own
noise: a hosted model at temperature 0 is often not deterministic, and a difference smaller than
its spread is not a difference. If outputs stop at `max_tokens`, `evh run` warns and names
the items: they are scored as if complete, so raise `max_tokens` in a new `system_id`.

The leaderboard now shows each arm's quality, `total_cost_usd` and `latency_ms`, and its
**frontier**: the arms no other arm beats on quality, cost and speed together. `evh run`
prints what the command spent over every repeat (`spent $0.001063 (the provider's bill)` or `(the system's price table: tokens x usd_per_mtok_in / usd_per_mtok_out, the provider sent no bill)`), and the repeat spread names cost and speed as what they
are (`cost, not a quality metric`), not as determinism. When the bill is more than 1.2× off the declared prices, `evh run` and `judge-score` print a NOTE saying so. Each item that was billed keeps the
bill in its `_meta.usage.cost`, and `cost-report` sets each run's bill, summed from those, against
the cost it recorded, listing apart the runs with no bill (priced from the table)
([RUNBOOK §4](../../harness/docs/RUNBOOK.md#4-point-the-harness-at-your-system)). Then compare and choose as
before (`family-test`, `run-promote`), with the cost in the reason: "as good as X at a tenth of
the price" is a decision; "scored higher" is not yet one.

## When a run stops partway

A 429 that outlasts the retries, a crash, or the cost cap leaves the finished items on disk; each
output is written as it arrives. (One item the provider refuses does not stop it: that item is scored 0, listed in
the run's `failed_items`, and called again on resume.) The run prints which run stopped, after how many items, and the
exact command to continue it:

<!-- guide-check: skip -->
```bash
evh run --system briefs_mistral_small_v1 --dataset briefs_v1 --goal brief_summary --resume <run_id>
```

A resumed pass calls the model only for the items that are missing. Or delete the run directory;
until one or the other, `evh validate` fails on it (V7). Retries wrap every call
(`EVAL_MAX_RETRIES`, `EVAL_RETRY_MAX_DELAY`); every variable and exit code:
[RUNBOOK](../../harness/docs/RUNBOOK.md#environment-variables).

Next: [tutorial 3](3-frontier-reference-and-judging.md) runs an expensive frontier model once and
makes its run the reference the cheaper arms are measured against.
