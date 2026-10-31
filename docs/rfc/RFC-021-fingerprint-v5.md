# RFC-021: Fingerprint v5: the deployment, the settings, and the runner

- **Status**: Draft (first, 2026-10-31), being built for 0.6.0 on the owner's go of 2026-10-31 ("let's do this
  refactor now, before we proceed"). Supersedes [RFC-001](RFC-001-fingerprint-and-code-identity.md)'s `host` and
  `system_under_test` parts; keeps its code identity (`_codeid`) and its data part as they are.
- **Authors**: Marko Dragoljevic
- **Related**: [PRD-015](../prd/PRD-015-models-onboarded-once.md), [ADR-0021](../adr/ADR-0021-a-deployment-is-vetted.md); [RFC-020](RFC-020-onboarding-a-model.md) (model records; their builds become deployments here);
  [RFC-002](RFC-002-run-records-and-derived-runs.md) (the run record that carries the fingerprint);
  0.7.0's plan to run experiments on other machines (the runner)

## Abstract

Version 4 hashes the instrument, the system under test, the data, the **host** and the arm into one number. It was
designed when the model ran inside the harness's process on the machine that ran `evh`. Most systems under test now
run elsewhere: a model on Ollama on another machine, on vLLM, behind a hosted provider. For those, v4 fingerprints
the wrong machine: the runner's platform and libraries are in the hash, the machine and server that produced the
outputs are not. Version 5 splits the fingerprint by what each part identifies: the **instrument** (what measured),
the **data** (what it measured on), the **deployment** (the system under test as it executed: weights, build,
server, hardware, host), the **settings** (how it was asked), and the **runner** (where `evh` ran), recorded but
outside the comparison hash.

## Motivation

Measured on the triage experiment, 2026-10-30/31:

- The same weights, at temperature 0, gave byte-identical outputs on one machine and different decisions on
  another (Bolt e4b: 10-14 of 65 decisions differ between X3, the DGX and the Mac). The hardware that served the
  model is part of what a number depended on. v4 does not record it; it records the laptop that sent the requests.
- One run of gpt-oss:120b used a June build and another the current one; one tag named an MLX build on the Mac.
  The weights that ran are part of what a number depended on. The triage adapter declares no identity, so v4's
  `system_under_test.model` reads `identity_declared: false` for 40-odd runs.
- The same deployment run from two machines is the same measurement. v4 gives it two hashes (its `host` differs)
  and calls the comparison "not the same conditions".
- `system_under_test.libraries` lists the runner's torch, transformers and openai. For a served model what moves a
  number is the server's software (Ollama 0.40.13, vLLM 26.05) and its backend (CUDA, ROCm, Metal).

## Design

### The parts

| part | identifies | fields | in the hash |
|---|---|---|---|
| `instrument` | what measured | `harness` and `adapter` as in v4 (code by behaviour, `_codeid`) | yes, by its code only: `harness.code_sha256` and `adapter.sha256`; the commit, a dirty tree and the version are recorded beside it |
| `data` | what it measured on | as in v4: `dataset_id`, `items_sha256`, `n_items`, `reference_id`, `reference_tier`, `references_sha256` | yes |
| `deployment` | the system under test as it executed | below | yes |
| `settings` | how the system was asked | the arm's params that change behaviour: everything in `params` that is neither a deployment key, a label nor a credential (`reasoning_effort`, `max_tokens`, `temperature`, a call limit, a task option), and under `declared` what the adapter's hook says about how it asked (a prompt's hash) | yes |
| `runner` | where `evh` ran | v4's `host` (label, platform, release, processor, cpu count, python) and the runner's client libraries | **no**: recorded as conditions |
| `arm` | the config | `config_id`, and `labels`: the params that describe the arm without changing what runs (prices `usd_per_mtok_*`, `price_tier`, `family`, `label`, `notes`) | no (a name and its labels) |

`hash` is the sha256 over the four hashed parts' own hashes (`instrument_sha256`, `data_sha256`,
`deployment_sha256`, `settings_sha256`, each also recorded), so "did anything move" stays one comparison and "what
moved" is four.

### The deployment

```yaml
deployment:
  id: gemma4-12b@dgx                # model record @ deployment, when the arm names them; else derived
  model: gemma4:12b                  # what was asked for (params.model)
  source: record | adapter | params  # where these facts came from, best first
  weights: {digest: 6114515d63c1…, revision: null, file_hash: null, quantization: Q4_K_M}
  server: {name: ollama, version: 0.40.13, settings: {context_length: 32768}}
  where: {machine: dgx, backend: cuda, device: null}
  hosted: null                       # or {provider: openrouter, route: [nebius], upstream_seen: [nebius], quantization: fp8}
  in_process: false                  # true: the model ran in the runner's process (an ML adapter on CPU)
  libraries: null                    # for in_process: the runner's torch, transformers, ... (they ran the model)
```

- **source: record**: the arm names a model record and a deployment (`model_record: gemma4-12b`,
  `deployment: dgx`); the fields come from the record's deployment entry, as last onboarded.
- **source: adapter**: the adapter's `fingerprint(params)` hook (v4's vocabulary: `id`, `revision`,
  `revision_source`, `device`, `precision`). It is **in process only when the arm calls nothing elsewhere** (no
  `url` or `base_url`, and a provider that is neither a built-in hosted one nor `gateway`); then the runner's
  libraries ran the model and go in `deployment.libraries`. Called elsewhere, they only sent the request and stay
  `runner.libraries`, so a runner's upgrade never moves a hosted deployment's hash; a hosted one records
  `hosted: {provider, provider_id: the upstream id the gateway resolved, route}`.
- **What a hook declares about how it asked** (`prompt_sha256`, `system_prompt_sha256`, `temperature`,
  `reasoning`, `reasoning_effort`, `max_tokens`) is a setting, kept as `settings.declared`: a new prompt moves the
  settings' hash, not the deployment's. Whatever else it declares (weight files, the labels, a baseline's code
  hash) stays `deployment.declared`.
- **source: params**: neither: the deployment is what the params say (`model`, `url` or `base_url`, `machine`,
  `provider`), with `weights.digest: null`. Honest about the gap, as v4 was about a missing revision.

**Deployment keys** (moved out of `settings`): `model`, `url`, `base_url`, `machine`, `provider`,
`provider_routing`, `revision`, `device`, `precision`, `deployment`, `model_record`. **Credentials**
(`api_key_env`) are in no part.

### Model records: builds become deployments

RFC-020's `builds[]` is renamed `deployments[]`, each with an `id` unique in the record (`mac`, `dgx`, `x3`,
`openrouter-nebius`), its fingerprint fields as above, its own `onboarding` (no longer one per record), and its
`endpoint`. An arm names one (`deployment: dgx`); `evh model-onboard <id> --deployment dgx` probes and writes that
one. A hosted deployment pins its route (`provider_routing`); the run records the upstream provider each call
reported, and a call served by another host is flagged by `evh arm-smoke`.

### The runner

v4's `host` becomes `runner`, outside the hash. Latency is the deployment's, measured from the runner: a run
records both, and a comparison of speed across runners says so. 0.7.0 runs experiments on other machines; the
runner is then simply the machine that ran them, with nothing else to change.

### Migration: every committed run to v5

No v4 fingerprint is kept (0.6.0's rule: formats nobody depends on are migrated, never shimmed). A one-time
migration rewrites each committed run's `fingerprint`:

- `instrument` and `data`: copied.
- `runner`: v4's `host`, and v4's `system_under_test.libraries` when the deployment was not in-process.
- `deployment`: from v4's `system_under_test.model` when the adapter declared one (`source: adapter`, in process
  by the rule above, with v4's libraries when it was); else from the run's params (`source: params`).
- `settings`: the run's params minus deployment keys, labels and credentials, plus what the hook declared about
  how it asked; the labels go to `arm.labels`.
- The hashes are recomputed; `version: 5`.

The migration is `evh fingerprint-migrate` (`scripts/fingerprint_migrate.py`, packaged so a pinned project can run it), idempotent; this repository's counts are committed beside the tools
(`migrate_fingerprint_v5.out.txt`: 344 tracked runs and 37 local ones, 304 from an adapter and 77 from params, 85 in
process; 5 baselines' `fingerprint_hash` follow). Derived runs (rescored, judged) take their source run's
deployment, settings and runner and keep `hash: null`. *Not done as first written:* filling the triage runs' digests
from the model records (`source: record`): no committed run names a record yet, so none is `record`; the triage
runs of round 2 will be. Two silver manifests keep their v4 `from_run.fingerprint_hash`: they sit inside the
reference digest, and rewriting them would move every run scored against them.

## What changes

- `_fingerprint.build_fingerprint` returns v5; `compare_runs`, `run-compare` and the inspector's conditions check
  read the four sub-hashes and name the part that moved ("deployment differs: dgx vs mac").
- `experiment-run` resolves the arm's record and deployment (RFC-020's `resolve`), passes the deployment to the
  fingerprint, and records `deployment_id`.
- `evh arm-smoke` flags a hosted call served by another upstream than the route pins.
- The catalog's arm page shows the deployment beside the conditions; the Models page shows each deployment's own
  onboarding.
- RFC-001 is marked superseded in its host and system-under-test parts.

## Not in scope

- Measuring a remote machine's hardware from the runner beyond what its server reports (Ollama reports the digest;
  the backend is recorded from the deployment record).
- Running `evh` on other machines (0.7.0); v5 only makes the record ready for it.
