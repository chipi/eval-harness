# RFC-011: Job sets and runners: local and ssh

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-010](../prd/PRD-010-runners.md), [PRD-012](../prd/PRD-012-agent-ready.md) (FR4.4, FR4.5)
- **Related RFCs**: RFC-014 (run ids), RFC-013 (config, exit codes, consent), RFC-016 (jobs as MCP job ids), RFC-010
  (studies run their trials as jobs)
- **Code**: new `harness/scripts/_jobs.py`, `jobs_supervisor.py`, `jobs_run.py` (`evh jobs-run`), `jobs_status.py`,
  `jobs_logs.py`, `jobs_stop.py`, `_runner_local.py`, `_runner_ssh.py`, `_detach.py` (shared with RFC-010's study
  supervisor); `sweep.py` (a job set); `_common.build_info` and `_fingerprint._harness_identity` (the verified build);
  `experiment_run.py` (exit 75); `schemas/job-set.schema.json`, `job-state.schema.json`

## Abstract

A **job set** lists jobs (config, dataset, repeat, labels, phase). `evh jobs-run` starts a **supervisor** in its own
session that runs the jobs on a **runner** and returns the set's id at once; `jobs-status`, `jobs-logs` and `jobs-stop`
follow it. Jobs have standard states, timeouts and retries; every attempt is its own run (RFC-014); a lease with a
lock held by the set's supervisor keeps two supervisors from ever running one set. **Phases** run a `before` and an
always-run `after` command once per
phase, can carry state from one to the other (a GPU mode to restore), and can wait on an external status check. The
**local** runner runs jobs in parallel; the **ssh** runner copies the project at the local commit to a host, verifies the
copy, runs the same supervisor there, follows it and brings the runs back to validate them here.

## Problem Statement

- `experiment-run` and `sweep` hold the terminal; an agent's tool call times out first.
- Nothing runs jobs in parallel; run ids collide within a second (fixed by RFC-014).
- There is no remote execution; the podcast project switches its GPU host's serving mode with its own ssh script per
  phase, and leaves the host idle afterwards.
- A remote copy of a project has no git history. Its runs either record an unknown build (`run-promote` refuses them),
  or someone sets `EVAL_BUILD_REF` by hand, which records the ref with `dirty: None` (`_common.py:293-301`); promotion
  refuses only a truthy `dirty` (`promote_baseline.py:125`), so a hand-set ref promotes with nothing verified. The
  harness's own identity (`instrument.harness.commit`, `_fingerprint.py:210-218`) comes from git separately and is
  None on the copy, so a remote run's fingerprint differs from a local run of the same arm.

## Design

### The job set

```yaml
id: round3-cnn                      # default: <name>_<timestamp>
runner: local                       # or a name from config.yaml runners:
jobs_in_parallel: 3
phases:
  generate:
    before: "scripts/ops/gpu_phase.sh enter code"    # prints MODE=<mode before>, then switches
    after:  'scripts/ops/gpu_phase.sh leave "$EVH_PHASE_STATE_MODE"'
    check:  "scripts/ops/gpu_phase.sh can-enter"     # must exit 0 before `before` runs
    shared: true                                      # touches a shared host: consent (RFC-013/016)
jobs:
  - {config: data/configs/cnn_qwen_m.yaml, repeat: 2, phase: generate, labels: [gpu], timeout_s: 3600, max_retries: 2}
  - {config: data/configs/cnn_bart_l.yaml, phase: generate}
```

The phase commands are the project's. The podcast project's `scripts/ops/dgx_gpu_mode.sh` switches the mode but prints
no `MODE=` line and, run on the host itself, connects to itself over ssh unless `DGX_LOCAL_MODE=1`; it needs a small
wrapper like `gpu_phase.sh` above (print the current mode, then switch). What its `status` exits with was not checked
for this RFC; the wrapper's `can-enter` must exit non-zero when the GPU is busy. `repeat: 2` expands into two jobs, one
per repeat, so each can be retried and resumed on its own (`experiment-run` refuses `--resume` with `--repeat` above 1,
`experiment_run.py:700-707`).

`schemas/job-set.schema.json` validates it. `sweep --configs …` builds a job set with `jobs_in_parallel: 1` and
`--wait`, so its behaviour is unchanged; a round's arms and a study's trials (RFC-010) build job sets too.

### State and the supervisor

- State lives in `.evh/jobs/<set id>/` (gitignored): `set.json` (the set, its hash, the actor, the runner), `state.json`
  (`schemas/job-state.schema.json`; per job: state, attempts with run ids, exit codes, reasons, timings; per phase: its
  state and the `before` state it captured), `logs/<job>/<attempt>.log`, `supervisor.log`, `supervisor.lock`.
  `state.json` is rewritten atomically after every change.
- `evh jobs-run <file> [--runner R] [--jobs N] [--wait] [--dry-run]` validates, runs the pre-flight, writes `set.json`,
  starts `python -m evaluation_harness.jobs_supervisor <set id>` detached (`_detach.start`: a new session, stdin from
  `/dev/null`, stdout and stderr to `supervisor.log`, `close_fds=True`), prints the id and returns. Detaching the
  descriptors matters: a caller that captures `jobs-run`'s output (RFC-016's tools) would otherwise wait until the
  supervisor closed the pipe, which is when the set ends. With `--wait` it follows until the set ends and exits with
  the set's outcome: 0 when every job succeeded, 3 when none did, 4 when a budget stopped it, and 5 (partly failed,
  RFC-013) when some failed. `--dry-run` prints the jobs, where each runs, the phases' commands, the estimated cost and
  time, and starts nothing.
- **One supervisor per set**: the supervisor holds an exclusive `flock` on `supervisor.lock` for its whole life. The
  operating system releases it when the process dies, however it dies, so a free lock with jobs in `running` means
  the supervisor is gone: `jobs-status` shows those jobs as `lost`, and `jobs-run --resume` takes the lock and
  continues. Each attempt runs in a new run directory (RFC-014 refuses an existing one), so a lost attempt's directory
  is never written again.
- The supervisor runs each job as `evh experiment-run --config … --run-id <attempt run id> --actor …` (with
  `--resume <previous attempt>` when retrying an interrupted attempt), capturing output to the attempt's log.
- **States**: queued, running, succeeded (with the run id), failed (reason), cancelled, timed_out, skipped, lost.
  `jobs-status <id> [--json]` reads `state.json` (and adds `next_check_s`, a suggested wait for a caller polling it); `jobs-logs <id> [--job J] [--follow]`; `jobs-stop <id>` sends SIGTERM to
  the supervisor, which stops running jobs (their process groups) and runs the pending `after` commands, then marks them
  cancelled. When the supervisor is already gone, `jobs-stop` runs the pending `after` commands itself, from the state
  `state.json` kept.
- Each job runs in its own process group (`start_new_session=True` for the job's process), so a kill reaches the job's
  children and nothing else.
- **Timeouts and retries**: a job past `timeout_s` is killed (its process group) and marked timed_out; a job whose
  attempt exits with a transient code (69, 75: RFC-013) is retried up to `max_retries`, each retry a new attempt resuming
  from the last. `experiment-run` exits 75 when its items failed only on transient errors after retries (RFC-007's item
  failures), so the code is produced, not assumed. Exit 3 (nothing measured), 1 (refused), 4 (budget) and 70 (an
  internal error) are not retried.
- **Re-running a set**: `jobs-run --resume <set id>` runs pending `after` commands first, then skips succeeded jobs and
  continues the others from their last attempts.
- **Parallel runs** are marked in `metrics.json` (`parallel: {jobs: N, set: id}`; `run.json` is gitignored,
  `harness/.gitignore:59`, so a mark only there would not travel); latency comparisons with runs made alone are flagged
  (PRD-010 FR1.6); a host declared `shared: true` in `config.yaml` flags its runs too.
- **MCP**: RFC-016's long-running tools call `jobs-run` and return the id; state mapping: queued and running → working,
  succeeded and skipped → completed, failed, timed_out and lost → failed, cancelled → cancelled.

### Phases

Jobs run phase by phase in the set's order. For each phase: `check` must exit 0 (else the phase fails, with its output);
then `before` runs, its stdout's `KEY=VALUE` lines become `EVH_PHASE_STATE_<KEY>` in the phase's environment (so `before`
can print `MODE=prod` before switching, and `after` restores it), and are written to `state.json` with the phase marked
`entered` before any job starts; then the phase's jobs; then `after`, on success, failure, cancellation and timeout.

A `finally` does not survive SIGKILL or a reboot, so `after` does not rest on it alone: a phase stays `entered` in
`state.json` until its `after` has run, and whatever finds it so (the supervisor's own `finally`, `jobs-stop`, `jobs-run
--resume`) runs `after` with the recorded state. `jobs-status` reports an `entered` phase whose supervisor is gone as
"after pending: run `evh jobs-stop <id>`"; it is a read command and never runs it.

A phase marked `shared` needs consent once for the set (RFC-013), with the number of times its commands will run.
Phases run where the jobs run (locally or on the host). GPU time (PRD-009 FR3.3) is a phase's wall time from the end of
`before` to the start of `after`, for a phase with `gpu`-labelled jobs: the time the host was held, counted once
however many jobs ran in parallel.

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
    also_send: [cache/podcast_scraper]                     # gitignored paths the jobs need (the system's checkout)
    env: [OPENAI_API_KEY, VLLM_API_KEY]                    # must exist on the host; values never sent
    labels: [gpu]
    host_lock: ~/.evh-host.lock
```

- **Pre-flight** (also in `--dry-run`, before anything is spent): `ssh host true`; `install_check` (else `install`, then
  the check again); the host's `evh --version` equals the project's pinned harness version; each name in `env` is set on
  the host (`test -n "$NAME"`); each phase's `check`. Any failure refuses the set with the reason (code
  `runner-preflight`).
- **What is sent**: the files of the local commit as git stores them (`git archive <commit>`, never the working tree),
  the frozen data the jobs' configs need that git ignores (their materialized datasets and reference texts), and the
  runner's `also_send` paths (a system's checkout that the project keeps out of git), with a manifest of every file's
  path and sha256. A dirty tree is refused unless `--allow-dirty`, which sends the working tree and records the build
  as dirty.
- **Only what changed**: the host keeps the last manifest it verified (`<workdir>/.evh/manifest.json`); the runner sends
  only files whose sha256 differs, as one tar stream over ssh, and removes files the new manifest no longer has. The
  podcast project's tracked tree is 1.8 GB in 9,164 files, so the first set sends it once and later sets send the
  change.
- The remote supervisor verifies every file against the manifest before running anything and refuses on a mismatch.
- **Build identity**: after the check, the remote supervisor writes `<workdir>/.evh/build.json` (`{"ref": commit,
  "dirty": false|true, "manifest_sha256": …, "source": "runner:ssh"}`). `build_info` and `_harness_identity` read that
  file when it exists, and only then report a verified build (`"verified": manifest_sha256`); `instrument.harness.commit`
  comes from the same file, so a remote run's fingerprint equals a local run's of the same arm. Identity is never taken
  from an environment variable here: a variable can be set by hand, a file written after a check cannot be confused
  with one. `EVAL_BUILD_REF` keeps its 0.4.0 meaning (a declared, unverified ref), and the catalog labels such builds
  "declared, not verified".
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
  `jobs-run` captured with `subprocess.run(capture_output=True)` returns at once; a timeout kills the job's process
  group and marks timed_out; a transient exit (75) retries from the last attempt; stop runs `after`; resume skips
  succeeded jobs; a SIGKILLed supervisor leaves a free lock, its jobs show lost, and resume continues with new
  attempts; a repeat-2 job is two jobs; `parallel` is in `metrics.json`; `--wait` exit codes.
- `harness/tests/test_phases.py`: `check` gates, state passed from `before` to `after`, `after` on failure, `after` run by
  `jobs-stop` and by `--resume` after a SIGKILL, GPU time counted once for parallel jobs.
- `harness/tests/test_runner_ssh.py` (CI, a container with sshd): pre-flight refusals (no host, missing variable, version
  mismatch, a dirty tree); a set runs, runs come back and validate, the build is the local commit and verified and the
  fingerprint equals a local run's; a second set sends only changed files; a tampered file on the host is refused; a
  dropped connection shows lost and reconciles.

## Decisions (ADR candidates)

1. Long work runs as job sets under a detached supervisor holding the set's lock; jobs have standard states, timeouts
   and retries; every attempt is a new run.
2. Phases with a check, a before that can hand state to an after, recorded so the after runs even after a crash, and
   consent for shared hosts.
3. The ssh runner sends the commit's files and the needed ignored data with a manifest, sends only changes, verifies them
   on the host, and records the build from a file written after the check, never from the environment.
