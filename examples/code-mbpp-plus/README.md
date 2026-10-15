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
   calls and prints, as EvalPlus does. A reply cut off mid-line (a small model writing
   test asserts until it runs out of tokens) keeps the complete code before the break, as
   EvalPlus's sanitiser does. A reply with no runnable code scores 0, with `syntax_ok` 0.
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
| 18 open coder models, local | six families, 0.5B to 34B, listed below; greedy, using each model's own chat template, EvalPlus's instruct prompt and its response prefix |

| arm | model | licence | runs on |
|---|---|---|---|
| `qwencoder_05b`, `_15b` | Qwen2.5-Coder-Instruct 0.5B, 1.5B | Apache-2.0 | 4-core CPU, fp32 |
| `dscoder_13b` | DeepSeek-Coder-1.3B-Instruct | DeepSeek License | 4-core CPU, fp32 |
| `yicoder_15b` | Yi-Coder-1.5B-Chat | Apache-2.0 | 4-core CPU, fp32 |
| `qwencoder_3b` | Qwen2.5-Coder-3B-Instruct | **Qwen Research (non-commercial)** | big machine, bf16 |
| `qwencoder_7b`, `_14b`, `_32b` | Qwen2.5-Coder-Instruct 7B, 14B, 32B | Apache-2.0 | big machine, bf16 |
| `codeqwen15_7b` | CodeQwen1.5-7B-Chat | Tongyi Qianwen License | big machine, bf16 |
| `dscoder_67b`, `_33b` | DeepSeek-Coder-Instruct 6.7B, 33B | DeepSeek License | big machine, bf16 |
| `dscoderv2_lite` | DeepSeek-Coder-V2-Lite-Instruct (16B MoE) | DeepSeek License | big machine, bf16 |
| `yicoder_9b` | Yi-Coder-9B-Chat | Apache-2.0 | big machine, bf16 |
| `starcoder2_15b` | StarCoder2-15B-Instruct-v0.1 | BigCode OpenRAIL-M | big machine, bf16 |
| `codellama_7b`, `_13b`, `_34b` | CodeLlama-Instruct 7B, 13B, 34B | Llama 2 Community | big machine, bf16 |
| `qwen3coder_30b` | Qwen3-Coder-30B-A3B-Instruct (MoE) | Apache-2.0 | big machine, bf16 |

"Big machine" means bf16 with `device: auto`, which uses a CUDA GPU or Apple-silicon MPS if
there is one and the CPU otherwise. The device actually used is recorded in the run. Every
model loads from safetensors at a pinned revision, and none runs remote code: all six
architectures are native to the pinned transformers.

The 3B Qwen model is non-commercial. Several others carry use-based conditions (DeepSeek,
Llama 2, OpenRAIL-M, Tongyi Qianwen). They are measured here; check each licence before
deploying one. Two models are left out on purpose: Codestral-22B, whose licence forbids
production use, and CodeLlama-70B, which doesn't fit 128 GB in bf16.

## Calibration

The [Qwen2.5-Coder technical report](https://arxiv.org/abs/2409.12186), Table 16, publishes
MBPP+ pass@1 (EvalPlus, greedy) for 17 of these 18 models under one setup. That gives a
calibration point for almost every arm, not just one per experiment:

| model | published MBPP+ | measured here |
|---|---|---|
| Qwen2.5-Coder-0.5B-Instruct | 43.7 | |
| CodeLlama-7B-Instruct | 44.4 | |
| CodeLlama-34B-Instruct | 50.5 | |
| CodeLlama-13B-Instruct | 51.1 | |
| DeepSeek-Coder-1.3B-Instruct | 54.8 | |
| Yi-Coder-1.5B-Chat | 57.7 | |
| Qwen2.5-Coder-1.5B-Instruct | 59.4 | |
| Qwen2.5-Coder-3B-Instruct | 62.4 | |
| StarCoder2-15B-Instruct-v0.1 | 65.1 | |
| DeepSeek-Coder-6.7B-Instruct | 65.6 | |
| CodeQwen1.5-7B-Chat | 67.2 | |
| Yi-Coder-9B-Chat | 69.0 | |
| DeepSeek-Coder-33B-Instruct | 70.1 | |
| DeepSeek-Coder-V2-Lite-Instruct | 70.4 | |
| Qwen2.5-Coder-7B-Instruct | 71.7 | |
| Qwen2.5-Coder-14B-Instruct | 72.8 | |
| Qwen2.5-Coder-32B-Instruct | 75.1 | |
| Qwen3-Coder-30B-A3B-Instruct | not published (newer than the report) | |

If the measured column tracks the published one across families, then the prompt,
extraction, sanitiser and sandbox reproduce EvalPlus. If one family drifts and the rest
don't, its chat template is the first suspect.

## Running the local arms

From `harness/`, after running `uv sync --extra local` in this example. These four are
small enough for a 4-core CPU:

```bash
for a in qwencoder_05b qwencoder_15b dscoder_13b yicoder_15b; do
  ../examples/code-mbpp-plus/.venv/bin/python scripts/experiment_run.py \
    --config ../examples/code-mbpp-plus/configs/arm_${a}_n378.yaml; done
```

The rest need a big machine. Together they download about 330 GB of weights; the largest
(34B) needs about 70 GB of memory in bf16:

```bash
for a in qwencoder_3b qwencoder_7b qwencoder_14b qwencoder_32b codeqwen15_7b \
         dscoder_67b dscoder_33b dscoderv2_lite yicoder_9b starcoder2_15b \
         codellama_7b codellama_13b codellama_34b qwen3coder_30b; do
  ../examples/code-mbpp-plus/.venv/bin/python scripts/experiment_run.py \
    --config ../examples/code-mbpp-plus/configs/arm_${a}_n378.yaml; done
```

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
