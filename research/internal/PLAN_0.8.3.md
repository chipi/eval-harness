# 0.8.3: the plan

**Status:** 2026-11-26, a first draft, written the day 0.8.2 was released (tag `v0.8.2` on `bf8d2eeb4`, GitHub Release
with the wheel and sdist, production deployed from the same commit, run `45867991495`). Branch `083`, from `origin/main`
at `bf8d2eeb4`. Everything below is what 0.8.2 left open, found while building, gating and releasing it. Nothing in it
is built. The owner decides scope and order; items marked **open** wait for the owner's word.

## How this release is worked (carried over from 0.8.1 and 0.8.2)

- Quality, consistency and completeness come before the timeline. Every finding is fixed, the nits included.
- The docs describe what exists now, and every documented command works (`check_commands`, `check_shown_commands`,
  `guide-check`).
- The work goes to subagents on a lower tier (Sonnet implementers and reviewers, Haiku for mechanical work, Fable for the
  advisor). A subagent's "passes" is checked by running it again.
- Each finding gets a failing test first, then the fix.
- **The gates run on a committed tree, and nothing is committed while they run.** On 0.8.2 two commits landed during
  the store matrix and failed `test_fingerprint_v5` once (the instrument's commit moved between its two builds).
- Real calls go through the homelab LiteLLM gateway, with the release-check key
  (`~/.config/eval-harness/release-litellm.env`: `eval-gpt-mini` and `eval-claude-haiku`, $1 cap). Keys are homelab's
  to mint.
- The release follows `harness/docs/RELEASING.md`, the newcomer scenario included when the newcomer's path changed
  (0.8.2 skipped it; see S5). `make release-smoke ARGS=--release` before the merge and after the deploy.

## The order (recommended)

1. **K. Keys and addresses**: one variable per provider, keys by system (the owner, 2026-11-26).
2. **S. What 0.8.2 left open**: the small items, each with its test.
3. **A. An assessment**: MLflow and TensorBoard, side by side with evh (the owner, 2026-11-26). Reading and writing,
   no code.

A patch release should not move a result. Each item says whether it can. One that does goes to 0.9.0 or the owner
decides. Scenarios (RFC-035, RFC-036, RFC-037, all Draft) are 0.9.0 and not in this plan.

## K. Keys and addresses (owner, 2026-11-26)

The owner's question, verbatim in substance: what do we gain from two names for one thing, and can we simplify so the
question is never asked?

What exists in 0.8.2:

- Each provider reads a key variable and an address variable: `LITELLM_API_KEY` and `LITELLM_BASE_URL`, `OPENAI_*`,
  `ANTHROPIC_*`, `OPENROUTER_API_KEY`.
- A judge reads `EVAL_JUDGE_<NAME>` first, then `<NAME>`. That was the only way for judging to spend from another key,
  budget or provider than the arms.
- A system may name `key_file: PATH` (0.8.2), read before the shell and `.env`.
- Every homelab LiteLLM key file names the address `LITELLM_API_BASE`, so a `key_file` pointing at one gives the key and
  no address; a system needs `base_url` too (found by 0.8.2's real-call check).

| Item | What | Done when | Moves a result |
| --- | --- | --- | --- |
| K1 | A judge is a system with its own `key_file`, so judging's own key needs no prefix | a judge with a `key_file` sends that file's key; the judge fingerprint is unchanged by where its key is kept | no |
| K2 | `EVAL_JUDGE_<NAME>` deprecated: read, with a warning naming the `key_file` way; removed in 0.9.0 | env-check, the dry run and `judge-score` say where each judge key came from; the warning once per run | no |
| K3 | One address variable per provider. **Open:** accept `LITELLM_API_BASE` as a second name, or ask homelab to write `LITELLM_BASE_URL` into the key files it mints for the harness. The owner leans to not having two names | the chosen one documented in tutorial 2 and RUNBOOK; a key file from homelab works with no `base_url` | no |
| K4 | **Open:** a `key_file` that lacks its provider's key falls through to the shell (0.8.2's default). Refuse instead? | the choice tested both ways in `test_key_file.py` | no |

## S. What 0.8.2 left open

| Item | What | Done when | Moves a result |
| --- | --- | --- | --- |
| S1 | UPGRADING's "From 0.8.1 to 0.8.2" leaves out two changes that can stop a run that worked: a budgeted round refuses an unpriced arm, and a provider's 401 stops the run. The eval agents were told in the upgrade message; the shipped docs still lack them | both named in UPGRADING (the 0.8.2 section, corrected, and the 0.8.3 one says so); a check that each CHANGELOG "Changed" or "Fixed" bullet that stops a run has an UPGRADING line | no |
| S2 | Retries stack: the SDK's own tries (3) times the harness's (`EVAL_MAX_RETRIES`, default 8) is up to 24 calls per item on a persistent 429 or 500 | one layer retries (the SDK's set to 0, or the harness's counts the SDK's); a test counts the calls against the fake API | no (cost only) |
| S3 | A 403 is not treated as a key refusal; only a 401 stops the run | a 403 stops it too, naming the key variable, or the reason it should not is written down | no |
| S4 | `env-check` and the dry run show a `key_file`'s key but not the address it brings (`LITELLM_BASE_URL`) | both lines say where the address came from, as for the key | no |
| S5 | The newcomer scenario was not run for 0.8.2, although the newcomer's path changed (`evh --help`, `evh docs`, the dry run's lines, the unpriced refusal). release-smoke's newcomer section and the real-call run covered part | the scenario run on 0.8.3's candidate (under $1, through the gateway); its "Still open" list rechecked | no |
| S6 | **Open:** ids take no combining marks (`isalnum`), so a word that needs a vowel sign (Devanagari) cannot be an id. Allowing them needs the `regex` dependency or a generated range class | the owner's choice; if allowed, the 35-id table in `test_unicode_ids.py` grows a row each way | no |
| S7 | Full-page screenshots repeat the sticky header mid-page (the scenario's "Still open") | the header is not repeated in a full-page capture, or the screenshot helper captures without it | no |
| S8 | The inspector's Conditions header reported to leave out `t5_small_v1` (not reproduced) | reproduced and fixed, or closed with the screenshot that shows it is there | no |
| S9 | The direct OpenAI, Anthropic and OpenRouter paths are covered offline only (`test_providers_wire.py`, real SDKs against fakes). The owner's machines reach models through the LiteLLM gateway only | **open:** whether a real direct call is ever wanted; if not, the scenario's "Not exercised" line says why | no |
| S10 | The `o11y-prod` skill has no profile for eval-harness; 0.8.2's production check queried GlitchTip by hand (`evals-web`, `evals-inspector`, `evals-mcp`) | a profile in the skill (the operator's), or a `make prod-check` here that does the same read-only queries | no |

## A. MLflow and TensorBoard, side by side (owner, 2026-11-26)

Both are tools people reach for to track and compare model runs. The assessment reads their docs and, where it helps,
installs them in a throwaway venv (an approval first: a new dependency in a shared environment).

- **What each records:** MLflow's runs, params, metrics, artifacts, model registry, and its LLM evaluation and
  tracing; TensorBoard's scalars, histograms and embeddings.
- **How each stores and serves it,** and what a team does with it day to day.
- **Where each overlaps with evh and where it does not:** fingerprints and code identity, references and their tiers,
  judges measured against people, rounds and goals, held-out discipline, the catalog and the Workbench, the
  statistics.
- **What evh could learn or borrow,** and whether evh should import or export either's format.

Done when: a note in `research/internal/` with a table per question and the owner's decisions on what, if anything,
goes into 0.9.0.

## Not in this plan

- **Scenarios** (RFC-035, RFC-036, RFC-037): 0.9.0.
- **The X3 CI runner** (`agentic-ai-homelab` `infra/x3/x3-ci-runner-setup.sh`, RFC-0011 there): homelab's, not the
  harness's. The owner asked on 2026-11-26 where it came from, having dropped the idea weeks before.

## Where the evidence is

- **The release:** PR #39 (the 0.8.2 squash, its description and the checklist comment); release run on the tag
  `v0.8.2`; the deploy run `45867991495` and its dry run `45867438165`.
- **The real-call check:** two systems on `eval-gpt-mini` and `eval-claude-haiku`, 6 items each, $0.0040 in all, keys
  from `key_file`.
- **Plans:** this plan's predecessor for 0.8.1 is [PLAN_0.8.1.md](PLAN_0.8.1.md); 0.8.2 was planned in conversation and
  its CHANGELOG section is its record.
