# MBPP+ code generation: does the function pass the tests?

Experiment 7. Every earlier experiment reads what a model wrote; this one **runs** it. Each
item is one MBPP task: a one-sentence instruction and one example assertion. The model
writes a Python function, and the referee is a test suite. Each function is run against
MBPP's original tests (`base`) and against EvalPlus's extended tests (`plus`), inside a
sandbox ([Austin et al. 2021](https://arxiv.org/abs/2108.07732);
[Liu et al. 2023](https://arxiv.org/abs/2305.01210)).

What makes it worth adding:

- **A referee that is not an annotator.** Every earlier experiment ended up adjudicating
  disputed gold labels. Here an answer is wrong when it raises or returns the wrong value,
  and anyone can rerun the check.
- **The likeliest place for "a free model was enough" to fail.** Writing code is
  generative and open-ended, unlike labelling. This experiment is meant to test that
  claim where it is weakest.
- **How much weak tests flatter a model.** One reply is scored twice, on base and on plus.
  The gap between the two is EvalPlus's finding, measured for each arm.

## What it breaks that the other six did not

| | |
|---|---|
| the answer | Python source, extracted from a chat reply |
| the metric | **pass@1 by execution**: `pass_plus` (base AND plus tests pass, EvalPlus's definition, the primary metric) and `pass_base` |
| the referee | a test suite: MBPP's ~3 assertions per task, then EvalPlus's extended inputs, checked against the canonical solution's outputs |
| the new risk | the scorer **executes model output**, so it only ever does that in a sandbox |

## The sandbox

The rule is **never execute outside the sandbox**. No flag turns it off.
[sandbox.py](sandbox.py) runs every execution in a fresh process:

| | Linux | macOS |
|---|---|---|
| isolation | new user, network, mount and pid namespaces (`unshare`) | `sandbox-exec` profile |
| network | none | denied |
| filesystem | whole tree read-only; a 64 MB tmpfs is the only writable place; chrooted | every write denied outside a fresh temp dir |
| processes | allowed, but trapped in the pid namespace and killed with it | `fork` denied |
| on both | CPU, memory, file-size and open-file limits; wall-clock timeout that kills the process group; empty environment (no API keys); `python -I` | |

**Warm-up probes the sandbox before any model is called.** It tries to reach the network,
write outside the scratch space and spin forever, and it checks that correct code passes
and wrong code fails. If anything leaks, the run refuses and nothing is spent. The probe's
results are recorded in every run's fingerprint. A machine with neither backend cannot run
this experiment, and that is deliberate.

The verdict comes back behind a random marker generated for each execution, so code that
prints cannot forge a pass. Code that calls `sys.exit` never reports one at all.

## Scoring, in order

1. **Extract.** Take the fenced code block that defines the function, else the first fenced
   block, else the whole reply. `code_found` records whether a block was fenced.
2. **Sanitise.** Keep top-level imports, functions, classes and assignments, and drop example
   calls and prints, as EvalPlus does. Code that isn't valid Python scores 0, with
   `syntax_ok` 0.
3. **Execute.** Run the base tests, then the plus tests only if base passed. A timeout
   scores 0 and is recorded in `timeout`, so a slow machine shows up instead of looking
   like wrong code.

## Data

`evalplus/mbppplus` (Apache-2.0), 378 tasks, all of them used. Nothing from it is
committed: `fetch.py` downloads it (see [docs/DATA.md](../../docs/DATA.md)).

```bash
python examples/code-mbpp-plus/fetch.py
examples/code-mbpp-plus/.venv/bin/python examples/code-mbpp-plus/canonical_check.py
```

`canonical_check.py` proves the instrument before any model is scored. It runs on every
task, through exactly the path a model's reply takes. The canonical solution must pass
base and plus, and a stub that returns `None` must fail, which proves no test is vacuous.
It records the slowest execution, which is the evidence behind the timeouts in
[adapter.py](adapter.py).

## Arms

| arm | what it is |
|---|---|
| 24 hosted models | the same 24 as every other experiment, shown EvalPlus's instruct prompt ([prompt.txt](prompt.txt)) at temperature 0 |
| `qwencoder_05b` … `qwencoder_32b` | the whole Qwen2.5-Coder-Instruct family (0.5B, 1.5B, 3B, 7B, 14B, 32B), local, greedy, using EvalPlus's chat prompt and response prefix. 0.5B and 1.5B run in fp32 on a 4-core CPU; 3B and up run in bf16 with `device: auto` (a CUDA GPU or Apple-silicon MPS if there is one), sized for a 128 GB machine |

Licences: Apache-2.0 for every size **except 3B**, which ships under the Qwen Research
License (non-commercial research only). It is measured here for the size curve; don't
deploy it commercially.

## Calibration

The [Qwen2.5-Coder technical report](https://arxiv.org/abs/2409.12186) publishes MBPP+
pass@1 (EvalPlus, greedy) for every size of the instruct family. Each one is measured here,
locally, on the same 378 tasks:

| Qwen2.5-Coder-Instruct | 0.5B | 1.5B | 3B | 7B | 14B | 32B |
|---|---|---|---|---|---|---|
| published MBPP+ | 43.7 | 59.4 | 62.4 | 71.7 | 72.8 | 75.1 |
| measured here | | | | | | |

Six calibration points instead of one: if the measured curve tracks the published one, the
prompt, extraction, sanitiser and sandbox reproduce EvalPlus; if it doesn't, one of them is
the difference.

## Running the local arms

From `harness/`, with `uv sync --extra local` done in this example:

```bash
for m in 05b 15b 3b 7b 14b 32b; do
  ../examples/code-mbpp-plus/.venv/bin/python scripts/experiment_run.py \
    --config ../examples/code-mbpp-plus/configs/arm_qwencoder_${m}_n378.yaml; done
```

The 32B downloads ~65 GB of weights and needs ~70 GB of memory in bf16.

## Running the hosted arms

You need `OPENROUTER_API_KEY` in `harness/.env` and a machine with a sandbox (Linux, or
macOS). From `harness/`:

```bash
for a in anthropic_s anthropic_m anthropic_l openai_s openai_m openai_l \
         deepseek_s deepseek_m deepseek_l gemma_s gemma_m gemma_l glm_s glm_m glm_l \
         llama_s llama_m llama_l mistral_s mistral_m mistral_l qwen_s qwen_m qwen_l; do
  ../examples/code-mbpp-plus/.venv/bin/python scripts/experiment_run.py \
    --config ../examples/code-mbpp-plus/configs/arm_${a}_n378.yaml; done
make leaderboard DATASET_ID=mbppplus_378
```

## What this cannot say

- **Contamination is near-certain.** MBPP has been public since 2021 and is in the training
  data of every recent model. A high score shows recall and skill together, and this
  experiment cannot separate them.
- **Expect a saturated top.** Frontier models sit near MBPP+'s practical ceiling, so the
  top of the table may not separate, as on DBpedia.
- **pass@1 at temperature 0 is one sample.** It does not measure how a model would do
  with retries.
- **The tests are imperfect too.** EvalPlus exists because MBPP's tests passed wrong code;
  its own tests are stronger, not complete.
