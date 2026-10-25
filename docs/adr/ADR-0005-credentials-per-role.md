# ADR-0005 — One provider layer; credentials per role, never identity (0.4.0)

**Status:** Accepted (2026-10-25), as built.
**Date:** 2026-10-25
**Detail:** [PRD-007](../prd/PRD-007-packaging-and-providers.md) (packaging and providers),
[tutorial 2](../tutorials/2-hosted-llm.md#1-choose-a-provider) (the providers and the variables
each role reads), [RUNBOOK §12](../../harness/docs/RUNBOOK.md#12-re-measure-with-a-validated-judge)
(judge-score)

## Context

The harness called hosted models three ways. The bundled adapter dispatched on an arm's
`provider:` (`openai`, `anthropic`, `openrouter`, `litellm`). Judge-score's judges ignored the
`provider:` their scorer declared: a judge went to a LiteLLM proxy when `LITELLM_BASE_URL` was
set, else to OpenRouter with its model looked up in a `models.json` alias table, while its
records named the declared provider. The judge panel (`evh judge`) called only Anthropic, priced
every call at Sonnet's prices written in the code, and ran its fake judge when
`ANTHROPIC_API_KEY` was missing.

The harness promises that the provider is the user's choice and the keys are their own
(PRD-007). An operator also keeps separate keys for running experiments and for judging, so
each has its own budget and spend log; the harness offered no way to do that short of an
`api_key_env` in every config, which entered every run's fingerprint.

## Decision

- **One provider layer** (`evaluation_harness._providers`) for arms, judge-score's judges and
  the judge panel: the same providers, options, cost rule (the bill, else the declared prices,
  else unknown) and refusals. A call goes where its `provider:` says and nowhere else; every
  judge declares one (the scorer schema requires it).
- **Keys by role.** A judge reads every variable as `EVAL_JUDGE_<NAME>` first, then `<NAME>`;
  an arm reads `<NAME>`. With no `EVAL_JUDGE_` variable set, judging shares the experiments'
  keys, as before.
- **A credential is not identity.** `api_key_env` is left out of a run's fingerprint and a
  judge's: the same model asked the same way is the same measurement whichever key paid.
  `provider`, `model`, `base_url` and the request options stay in identity.
- **No alias routing in the core.** A judge's `model` is sent as written to its provider. The
  examples' own arms keep their routing helper (`examples/_shared/gateway.py`), which is this
  repository's concern, not the package's.

## Consequences

- Positive: a judge's record says where it was called, truthfully; judging can run on its own
  keys with no change to any scorer or config; `evh env-check` and judge-score show which key
  each role will use before anything is spent; Anthropic, OpenRouter, a LiteLLM proxy and any
  OpenAI-compatible endpoint work for judges as for arms.
- Negative: re-running the committed scorers (`provider: litellm`) needs a LiteLLM proxy;
  OpenRouter alone no longer reaches them. A scorer that relied on the alias route must name
  `provider: openrouter` and an OpenRouter id, which is a new judge identity.
- Neutral: no committed hash moved; no committed config used `api_key_env`, and every committed
  verdict's `judge_fp` is unchanged (checked by `tests/test_judge_score.py`).

## Alternatives considered

1. **`api_key_env` in every config and scorer.** Already possible; it repeats the choice in every
   file and, as it was, moved every run's fingerprint when a key changed.
2. **Keep the alias route for judges as a named feature.** It lets one OpenRouter key reach the
   committed `provider: litellm` judges, but the record would name a provider the call did not
   use, and the validation gate compares the provider.
3. **A per-project role table** (a file mapping roles to keys). More flexible than a prefix, but a
   second place to look for credentials that the environment already covers.
