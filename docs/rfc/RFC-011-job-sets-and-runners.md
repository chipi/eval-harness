# RFC-011: Job sets and runners: local and ssh

- **Status**: Draft (0.5.0), revision 3 (2026-10-27): phases are a `before` and an always-run `after`, marked `gpu`
  for GPU time; no check command, no state passed between them, no labels. Revision 2 (2026-10-27): the ssh host checks out the pushed commit with git and rsync
  carries the ignored data; no manifest, delta sync or build file
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-010](../prd/PRD-010-runners.md), [PRD-012](../prd/PRD-012-agent-ready.md) (FR4.4, FR4.5)
- **Related RFCs**: RFC-014 (run ids), RFC-013 (config, exit codes, consent), RFC-016 (jobs as MCP job ids), RFC-010
  (studies run their trials as jobs)
- **Code**: new `harness/scripts/_jobs.py`, `jobs_supervisor.py`, `jobs_run.py` (`evh jobs-run`), `jobs_status.py`,
  `jobs_logs.py`, `jobs_stop.py`, `_runner_local.py`, `_runner_ssh.py`, `_detach.py` (shared with RFC-010's study
  supervisor); `sweep.py` (a job set); `_common.build_info` and `_fingerprint._harness_identity` (unchanged: the host is a git checkout);
  `experiment_run.py` (exit 75); `schemas/job-set.schema.json`, `job-state.schema.json`

## Abstract

A **job set** lists jobs (config, dataset, repeat, phase). `evh jobs-run` starts a **supervisor** in its own
session that runs the jobs on a **runner** and returns the set's id at once; `jobs-status`, `jobs-logs` and `jobs-stop`
follow it. Jobs have standard states, timeouts and retries; every attempt is its own run (RFC-014); a lease with a
lock held by the set's supervisor keeps two supervisors from ever running one set. **Phases** run a `before` and an
always-run `after` command once per phase (to switch a GPU host's mode and switch it back). The **local** runner runs
jobs in parallel; the **ssh** runner checks out the pushed commit on a host, runs the same supervisor there, follows it
and brings the runs back to validate them here.

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
    before: "scripts/ops/gpu_phase.sh enter code"    # remembers the mode it found, then switches; fails if the GPU is busy
    after:  "scripts/ops/gpu_phase.sh leave"         # switches back to the mode it remembered
    gpu: true                                         # its time counts as GPU time
    shared: true                                      # touches a shared host: consent (RFC-013/016)
jobs:
  - {config: data/configs/cnn_qwen_m.yaml, repeat: 2, phase: generate, timeout_s: 3600, max_retries: 2}
  - {config: data/configs/cnn_bart_l.yaml, phase: generate}
```

The phase commands are the project's, and so is any state they keep: a `before` that must know what to restore
writes it where its `after` reads it. The podcast project's `scripts/ops/dgx_gpu_mode.sh` switches the mode but does not
remember the previous one and, run on the host itself, connects to itself over ssh unless `DGX_LOCAL_MODE=1`; it needs
a small wrapper like `gpu_phase.sh` above (remember the current mode, refuse when the GPU is busy, switch; and switch
back). `repeat: 2` expands into two jobs, one
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
  the set's outcome: 0 when every job succeeded, 7 when none did, 4 when a budget stopped it, and 5 (partly failed,
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
  attempt exits with a transient code (75: RFC-013) is retried up to `max_retries`, each retry a new attempt resuming
  from the last. `experiment-run` exits 75 when its items failed only on transient errors after retries (RFC-007's item
  failures), so the code is produced, not assumed. Exit 7 (nothing measured), 3 (a judge not validated), 1 (refused), 4 (budget) and 70 (an
  internal error) are not retried.
- **Re-running a set**: `jobs-run --resume <set id>` runs pending `after` commands first, then skips succeeded jobs and
  continues the others from their last attempts.
- **Parallel runs** are marked in `metrics.json` (`parallel: {jobs: N, set: id}`; `run.json` is gitignored,
  `harness/.gitignore:59`, so a mark only there would not travel); latency comparisons with runs made alone are flagged
  (PRD-010 FR1.6); a host declared `shared: true` in `config.yaml` flags its runs too.
- **MCP**: RFC-016's long-running tools call `jobs-run` and return the id; state mapping: queued and running → working,
  succeeded and skipped → completed, failed, timed_out and lost → failed, cancelled → cancelled.

### Phases

Jobs run phase by phase in the set's order. For each phase: `before` runs (a non-zero exit fails the phase, with its
output, and its jobs are skipped); the phase is marked `entered` in `state.json` before any job starts; then the phase's
jobs; then `after`, on success, failure, cancellation and timeout.

A `finally` does not survive SIGKILL or a reboot, so `after` does not rest on it alone: a phase stays `entered` in
`state.json` until its `after` has run, and whatever finds it so (the supervisor's own `finally`, `jobs-stop`, `jobs-run
--resume`) runs `after`. `jobs-status` reports an `entered` phase whose supervisor is gone as
"after pending: run `evh jobs-stop <id>`"; it is a read command and never runs it.

A phase marked `shared` needs consent once for the set (RFC-013), with the number of times its commands will run.
Phases run where the jobs run (locally or on the host). GPU time (PRD-009 FR3.3) is the wall time of a phase marked
`gpu: true`, from the end of `before` to the start of `after`: the time the host was held, counted once however many
jobs ran in parallel.

### The local runner

The default. Runs the supervisor on this machine with `jobs_in_parallel` workers. A project with no runner configured and
no job set behaves exactly as in 0.4.0.

### The ssh runner

```yaml
runners:
  dgx:
    type: ssh
    host: dgx-llm-1
    workdir: ~/evh/podcast-eval                          # a git clone of the project, made once
    install: "uv sync --frozen && uv pip install -e ."   # makes the project's environment, system under test included
    install_check: "uv pip check"                          # exit 0 when the environment is current
    also_send: [cache/podcast_scraper]                     # gitignored paths the jobs need (the system's checkout)
    env: [OPENAI_API_KEY, VLLM_API_KEY]                    # must exist on the host; values never sent
    host_lock: ~/.evh-host.lock
```

- **Pre-flight** (also in `--dry-run`, before anything is spent): `ssh host true`; `install_check` (else `install`, then
  the check again); the host's `evh --version` equals the project's pinned harness version; each name in `env` is set on
  the host (`test -n "$NAME"`). Any failure refuses the set with the reason (code
  `runner-preflight`).
- **The code is a git checkout.** The host's `workdir` is a clone of the project. The runner refuses a dirty local tree
  and a commit the project's remote does not have (it must be pushed), then runs on the host `git fetch origin <commit>`
  and `git checkout --detach <commit>`, and checks that `git rev-parse HEAD` is the commit and `git status --porcelain`
  is empty. Git does the transfer (only what changed) and the verification (the commit's hash covers every tracked
  file), so the harness sends no manifest of its own.
- **The ignored data**: the frozen data the jobs' configs need that git ignores (their materialized datasets and
  reference texts) and the runner's `also_send` paths (a system's checkout the project keeps out of git) go by `rsync
  -a --checksum --delete` of exactly those paths. They are verified where they are used, as they are locally: a
  materialized item is checked against the dataset's sha256 for it, a reference against its digest, and the run's
  fingerprint records both. The system's own checkout is identified by the code ref its adapter declares (PRD-008
  FR4.4).
- **Build identity**: the host's tree is a real git checkout at the local commit, so `build_info` and
  `_harness_identity` read git there exactly as they do locally (`{"ref": commit, "dirty": false, "source": "git"}`),
  and a remote run's fingerprint equals a local run's of the same arm. Nothing is taken from an environment variable:
  `EVAL_BUILD_REF` keeps its 0.4.0 meaning (a declared, unverified ref), and the catalog labels such builds "declared,
  not verified".
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
- **Copy the files with a manifest of hashes and send only the changes** (the first draft). Rejected in revision 2:
  it rebuilds what git already does (transfer of changes, a hash over every tracked file), and needs a build file to
  carry the identity a checkout has by itself. The price: the commit must be pushed before a remote set runs.

## Testing

- `harness/tests/test_jobs.py`: six fake-adapter jobs, three at a time: same metrics as one at a time; states and attempts;
  `jobs-run` captured with `subprocess.run(capture_output=True)` returns at once; a timeout kills the job's process
  group and marks timed_out; a transient exit (75) retries from the last attempt; stop runs `after`; resume skips
  succeeded jobs; a SIGKILLed supervisor leaves a free lock, its jobs show lost, and resume continues with new
  attempts; a repeat-2 job is two jobs; `parallel` is in `metrics.json`; `--wait` exit codes.
- `harness/tests/test_phases.py`: a failing `before` fails the phase and skips its jobs, `after` on failure, `after` run by
  `jobs-stop` and by `--resume` after a SIGKILL, GPU time counted once for parallel jobs.
- `harness/tests/test_runner_ssh.py` (CI, a container with sshd, in the integration tier of `harness/docs/TESTING.md`;
  its workflow job is named when it is built): pre-flight refusals (no host, missing variable, version
  mismatch, a dirty tree, an unpushed commit); a set runs, runs come back and validate, the build is the local commit
  and the fingerprint equals a local run's; a changed file in the host's checkout is refused; a tampered materialized
  item fails its sha256; a dropped connection shows lost and reconciles.

## Decisions (ADR candidates)

1. Long work runs as job sets under a detached supervisor holding the set's lock; jobs have standard states, timeouts
   and retries; every attempt is a new run.
2. Phases with a `before` and an `after`, recorded so the after runs even after a crash, marked `gpu` for GPU time, and
   consent for shared hosts.
3. The ssh runner checks out the pushed commit with git on the host and carries the ignored data with rsync; the build
   is the host's git checkout, read as it is locally, never taken from the environment.
