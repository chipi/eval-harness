# ADR-0011 — Long work runs as job sets, locally or over ssh (0.5.0)

**Status:** Accepted (2026-10-26), design; not yet built. Revision 2 (2026-10-27): the ssh host checks out the pushed commit with git; no manifest or build file.
**Date:** 2026-10-26
**Detail:** [PRD-010](../prd/PRD-010-runners.md), [RFC-011](../rfc/RFC-011-job-sets-and-runners.md)
(state, phases, the ssh runner, build identity)

## Context

`experiment-run` and `sweep` hold the terminal, so an agent's tool call times out first; nothing
runs jobs in parallel; and there is no remote execution. The podcast project switches its GPU
host's serving mode with its own script per phase and leaves the host idle afterwards. A remote
copy of a project has no git history, so its runs either name no build or a hand-set, unverified
one.

## Decision

- **A job set** lists jobs (config, dataset, repeat, labels, phase). `jobs-run` starts a detached
  supervisor that holds the set's lock and returns the id at once; `jobs-status`, `jobs-logs` and
  `jobs-stop` follow it. Jobs have standard states, timeouts and retries on transient exits;
  every attempt is a new run.
- **Phases** run a check, a `before` that can hand state (a GPU mode to restore) to an `after`,
  and the `after` always: its state is recorded, so it still runs after a crash. A phase on a
  shared host needs the person's consent.
- **Runners**: local (parallel workers) and ssh. The ssh host is a git clone that checks out the pushed
  commit; rsync carries the ignored data the jobs need; the same supervisor runs there, and the runs come
  back to be validated here.
- **A remote build is a real checkout**: git transfers and verifies the code, and the run's identity is
  read from the host's git as it is locally, never from an environment variable.

## Consequences

An agent starts long work and follows it with short calls. A queue service, Kubernetes and Slurm
are not needed for one person's tool; the runner interface (start, status, logs, stop, bring back)
admits them later.
