# RFC-011: Job sets and runners: local and ssh

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-010](../prd/PRD-010-runners.md), [PRD-012](../prd/PRD-012-agent-ready.md) (FR4.4, FR4.5)
- **Related RFCs**: RFC-014 (run ids), RFC-013 (config, exit codes, consent), RFC-016 (jobs as MCP job ids), RFC-010
  (studies run their trials as jobs)
- **Code**: new `harness/scripts/_jobs.py`, `jobs_supervisor.py`, `jobs_run.py` (`evh jobs-run`), `jobs_status.py`,
  `jobs_logs.py`, `jobs_stop.py`, `_runner_local.py`, `_runner_ssh.py`; `sweep.py` (a job set); `_common.build_info`;
  `schemas/job-set.schema.json`

## Abstract

A **job set** lists jobs (config, dataset, repeat, labels, phase). `evh jobs-run` starts a **supervisor** in its own
session that runs the jobs on a **runner** and returns the set's id at once; `jobs-status`, `jobs-logs` and `jobs-stop`
follow it. Jobs have standard states, timeouts and retries; every attempt is its own run (RFC-014); a lease with a
heartbeat keeps two jobs from ever writing one run. **Phases** run a `before` and an always-run `after` command once per
phase, can carry state from one to the other (a GPU mode to restore), and can wait on an external status check. The
**local** runner runs jobs in parallel; the **ssh** runner copies the project at the local commit to a host, verifies the
copy, runs the same supervisor there, follows it and brings the runs back to validate them here.

## Problem Statement

- `experiment-run` and `sweep` hold the terminal; an agent's tool call times out first.
- Nothing runs jobs in parallel; run ids collide within a second (fixed by RFC-014).
- There is no remote execution; the podcast project switches its GPU host's serving mode with its own ssh script per
  phase, and leaves the host idle afterwards.
- A remote copy of a project has no git history, so its runs record an unknown build (`_common.build_info` falls back to
  `ref: unknown`), and `run-promote` refuses them.

## Design

### The job set

```yaml
id: round3-cnn                      # default: <name>_<timestamp>
runner: local                       # or a name from config.yaml runners:
jobs_in_parallel: 3
phases:
  generate:
    before: "scripts/ops/dgx_gpu_mode.sh code"      # stdout is kept as the phase's state
    after:  'scripts/ops/dgx_gpu_mode.sh "$EVH_PHASE_STATE_MODE"'
    check:  "scripts/ops/dgx_gpu_mode.sh status"     # must exit 0 before `before` runs
    shared: true                                      # touches a shared host: consent (RFC-013/016)
jobs:
  - {config: data/configs/cnn_qwen_m.yaml, repeat: 2, phase: generate, labels: [gpu], timeout_s: 3600, max_retries: 2}
  - {config: data/configs/cnn_bart_l.yaml, phase: generate}
```

`schemas/job-set.schema.json` validates it. `sweep --configs …` builds a job set with `jobs_in_parallel: 1` and
`--wait`, so its behaviour is unchanged; a round's arms and a study's trials (RFC-010) build job sets too.

### State and the supervisor

- State lives in `.evh/jobs/<set id>/` (gitignored): `set.json` (the set, its hash, the actor, the runner), `state.json`
  (per job: state, attempts with run ids, exit codes, reasons, timings), `logs/<job>/<attempt>.log`, `supervisor.pid`.
- `evh jobs-run <file> [--runner R] [--jobs N] [--wait] [--dry-run]` validates, runs the pre-flight, writes `set.json`,
  starts `python -m evaluation_harness.jobs_supervisor <set id>` in a new session (`start_new_session=True`), prints the
  id (and with `--wait`, follows until it ends and exits with the set's outcome code). `--dry-run` prints the jobs, where
  each runs, the phases' commands, the estimated cost and time, and starts nothing.
- The supervisor runs each job as `evh experiment-run --config … --run-id <attempt run id> --actor …` (with
  `--resume <previous attempt>` when retrying an interrupted attempt), capturing output to the attempt's log.
- **States**: queued, running, succeeded (with the run id), failed (reason), cancelled, timed_out, skipped, lost.
  `jobs-status <id> [--json]` reads `state.json`; `jobs-logs <id> [--job J] [--follow]`; `jobs-stop <id>` sends SIGTERM to
  the supervisor, which stops running jobs (their process groups) and runs the pending `after` commands, then marks them
  cancelled.
- **Timeouts and retries**: a job past `timeout_s` is killed (its process group) and marked timed_out; a job whose
  attempt exits with a transient code (69, 75: RFC-013) is retried up to `max_retries`, each retry a new attempt resuming
  from the last. Exit 3 (nothing measured), 1 (refused) and 4 (budget) are not retried.
- **Leases**: an attempt's run directory holds `.lease` (supervisor pid, host, heartbeat time), refreshed every 10 s; a
  supervisor that finds a lease older than 60 s on a run it was not running treats it as lost and takes over by starting a
  new attempt (never writing into the old run). Run directories are never shared: RFC-014 refuses an existing directory.
- **Re-running a set**: `jobs-run --resume <set id>` skips succeeded jobs and continues the others from their last
  attempts.
- **Parallel runs** are marked (`run.json` `parallel: {jobs: N, set: id}`); latency comparisons with runs made alone are
  flagged (PRD-010 FR1.6); a host declared `shared: true` in `config.yaml` flags its runs too.
- **MCP**: RFC-016's long-running tools call `jobs-run` and return the id; state mapping: queued and running → working,
  succeeded and skipped → completed, failed, timed_out and lost → failed, cancelled → cancelled.

### Phases

Jobs run phase by phase in the set's order. For each phase: `check` must exit 0 (else the phase fails, with its output);
then `before` runs, its stdout's `KEY=VALUE` lines become `EVH_PHASE_STATE_<KEY>` in the phase's environment (so `before`
can print `MODE=prod` before switching, and `after` restores it); then the phase's jobs; then `after`, always (on success,
failure, cancellation and timeout, from a `finally`). A phase marked `shared` needs consent once for the set (RFC-013
`--confirm`, RFC-016 elicitation), with the number of times its commands will run. Phases run where the jobs run (locally
or on the host). GPU time (PRD-009 FR3.3) is the wall time of `gpu`-labelled jobs between a phase's `before` and `after`.

### The local runner

The default. Runs the supervisor on this machine with `jobs_in_parallel` workers. A project with no runner configured and
no job set behaves exactly as in 0.4.0.

### The ssh runner

```yaml
runners:
  dgx:
    type: ssh
    host: dgx-llm-1
    workdir: ~/evh/podcast-eval
    install: "uv sync --frozen && uv pip install -e ."   # makes the project's environment, system under test included
    install_check: "uv pip check"                          # exit 0 when the environment is current
    env: [OPENAI_API_KEY, VLLM_API_KEY]                    # must exist on the host; values never sent
    labels: [gpu]
    host_lock: ~/.evh-host.lock
```

- **Pre-flight** (also in `--dry-run`, before anything is spent): `ssh host true`; `install_check` (else `install`, then
  the check again); the host's `evh --version` equals the project's pinned harness version; each name in `env` is set on
  the host (`test -n "$NAME"`); each phase's `check`. Any failure refuses the set with the reason (code
  `runner-preflight`).
- **Sending**: the tracked files at the local commit (`git ls-files`), plus the frozen data the jobs need that git ignores
  (materialized datasets, reference texts), with a manifest of every file's sha256; the remote verifies the files against
  the manifest before running and refuses on a mismatch.
- **Build identity**: jobs run with `EVAL_BUILD_REF=<local commit>` and `EVAL_BUILD_SOURCE=runner:ssh`, and the
  supervisor sets `EVAL_BUILD_VERIFIED=<manifest sha256>` only after the check passes; `build_info` records
  `{"ref": commit, "dirty": false, "source": "runner:ssh", "verified": manifest_sha}` in that case (and `dirty: true` when the
  local tree was dirty when sent, which the pre-flight also reports).
- **Running**: the remote supervisor runs under `flock <host_lock>`, so two sets never prepare one host at once; the
  local `jobs-status` reads the remote `state.json` over ssh; if ssh drops, running jobs are shown as lost until the next
  status read reconciles them from the remote state.
- **Bringing back**: each succeeded attempt's run directory is copied back into the local runs directory and validated
  here (`evh validate --runs <dir>`); a run that fails validation is marked failed with the reason.

## Migration

None. `sweep` keeps its command line.

## Alternatives Considered

- **A queue service (Redis, Celery).** Rejected: a dependency and a service for a single-user tool.
- **Kubernetes Jobs or Slurm now.** Deferred: the runner interface (start, status, logs, stop, bring back) admits them;
  0.5.0 needs local and ssh.
- **Run remote jobs over one long ssh session.** Rejected: a dropped connection would kill them; a remote supervisor in its
  own session survives it.
- **Trust the remote tree's git state.** Rejected: the copy has no history; a verified manifest of the sent files is
  stronger evidence than a remote `git status`.

## Testing

- `harness/tests/test_jobs.py`: six fake-adapter jobs, three at a time: same metrics as one at a time; states and attempts;
  a timeout kills and marks timed_out; a transient exit retries from the last attempt; stop runs `after`; resume skips
  succeeded jobs; a stale lease is taken over with a new attempt; parallel runs are marked.
- `harness/tests/test_phases.py`: `check` gates, state passed from `before` to `after`, `after` on failure.
- `harness/tests/test_runner_ssh.py` (CI, a container with sshd): pre-flight refusals (no host, missing variable, version
  mismatch); a set runs, runs come back and validate, the build is the local commit and verified; a dropped connection
  shows lost and reconciles.

## Decisions (ADR candidates)

1. Long work runs as job sets under a detached supervisor; jobs have standard states, timeouts, retries and leases; every
   attempt is a new run.
2. Phases with a check, a before that can hand state to an always-run after, and consent for shared hosts.
3. The ssh runner sends the tracked files and needed frozen data with a manifest, verifies them on the host, and records
   the local commit as a verified build.
