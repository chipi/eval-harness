# ADR-0021 — A deployment, not a model, is what is vetted and fingerprinted (0.6.0)

**Status:** Proposed (2026-10-31)
**Date:** 2026-10-31
**Detail:** [RFC-020](../rfc/RFC-020-onboarding-a-model.md) (records, onboarding),
[RFC-021](../rfc/RFC-021-fingerprint-v5.md) (fingerprint v5), [PRD-015](../prd/PRD-015-models-onboarded-once.md)

## Context

A model a project tests runs in several places: an Ollama tag on three machines, a vLLM build, a hosted alias on
two providers. In the triage experiment the same weights at temperature 0 gave identical outputs on one machine
and different decisions on another; one tag named an MLX build on one machine; a hosted alias can be served by
different upstream hosts. The fingerprint (v4) recorded the machine that ran `evh`, which for a served model is
not the machine that answered.

## Decision (proposed)

- The unit that is onboarded, smoked and fingerprinted is a **deployment**: a model at one place, as one build,
  behind one server or route. A model record holds several; each has its own onboarding. A record whose every
  deployment passed its onboarding is *onboarded*; it is *vetted* once an arm that names it has also passed its
  smoke on the task's own items (the onboarding probe is one toy question: it registers a model, it does not
  vet it).
- Determinism, speed and the build are a deployment's facts, never a model's: `--repeat` reads the named
  deployment's onboarding, and a record's `capabilities` hold only what is true wherever it runs.
- The fingerprint's `deployment` part is that deployment (from the record when the arm names it); the machine
  that ran `evh` is the `runner`, outside the comparison hash. A model runs **in process** only when its arm calls
  nothing elsewhere (no URL, no hosted provider or gateway); only then are the runner's libraries the deployment's.

## Consequences

- The same deployment run from two runners is one measurement; a run on another machine or build is a different
  deployment, and `run-compare` says so.
- Onboarding a model on three machines is three onboardings; a record with one failed deployment is "to check".
- Hosted arms no longer move when the runner upgrades a client library.
- Nothing is learned about a deployment that was never onboarded: its runs are `source: adapter` or `params`, with
  what their params and hook could say.

## Alternatives considered

- **Vet the model once, wherever.** Rejected: measured, the same weights differ by machine.
- **Keep the host in the hash, add the deployment beside it.** Rejected: one deployment run from two laptops would
  still be two measurements.
- **Treat every adapter-declared model as in process (as v4 did).** Rejected: a hosted arm's hash then depends on the
  runner's numpy and openai versions.
