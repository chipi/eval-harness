# PRD-010: Runners: where experiments run

- **Status**: Draft (0.5.0), round 2
- **Authors**: Marko Dragoljevic
- **Related UX specs**: [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) (the commands)
- **Related RFC**: RFC-011 (job sets, the runner interface, local and ssh), to be written
- **Related PRDs**: [PRD-001](PRD-001-experiments-and-comparison.md),
  [PRD-009](PRD-009-prompts-and-optimisation.md) (loops run their trials through runners),
  [PRD-012](PRD-012-agent-ready.md), [PRD-013](PRD-013-identity-and-ties.md) (unique run ids, the
  host outside the hash)

## Summary

Experiments run where the compute is: a laptop for hosted-API arms, a GPU box for local models,
later a container platform or CI. Today `experiment-run` and `sweep` run in the local process, one
after another, holding the terminal. This PRD adds **job sets** (arm × dataset × repeat, each a
job) handed to a named **runner**, which runs them, detached, and brings back ordinary run
directories. Jobs have the states, retries, timeouts and logs that Slurm, Kubernetes Jobs and Ray
Jobs use. 0.5.0 ships the **local** runner (jobs in parallel, a lease lock, resume) and a simple
**ssh** runner (copy the project to a host, run the same command there, follow its log, bring the
run back, validate it here), with per-phase preparation commands for hosts whose GPU must be
switched. The run directory is the contract, so every later runner only moves one.

## Background & Context

- `experiment-run` resumes an interrupted run (0.4.0); `sweep` runs configs one after another and
  keeps going when one fails. Nothing runs jobs in parallel or detached, and nothing runs anywhere
  but here.
- A run id is the config id plus a timestamp to the second (`experiment_run.py:586`), and the run
  directory is created with `exist_ok=True`, so two jobs of one config started in the same second
  would share a directory silently ([PRD-013](PRD-013-identity-and-ties.md) fixes this first).
- The host a run used is inside the fingerprint's hash today, so a run made on a GPU host and one
  made on a laptop read as an uncontrolled comparison ([PRD-013](PRD-013-identity-and-ties.md)
  moves it beside the hash).
- In the podcast project most runs execute on the laptop and call model servers on its GPU host
  (the DGX) over HTTP; jobs that need torch run on the host. The host's GPU serves one model stack
  at a time, switched per phase (generate with one stack, judge with another) by an ssh command
  (`scripts/ops/dgx_gpu_mode.sh`, calling the host's `gpu-mode-swap.sh`); the GPU is shared with
  production serving.
- An agent's tool call times out long before a full run ends; it needs to start work and come
  back to it.

## Goals

- One command runs a job set anywhere a runner is configured, detached, with the same records as
  a local run.
- Local jobs run in parallel within limits; no two jobs ever write the same run.
- An ssh runner needs only ssh access and the project's environment installable on the host.
- A host is prepared before a phase and restored after it, with consent where the host is shared.
- Interrupted job sets resume; one job's failure does not lose the others; failed jobs retry when
  told to.
- A person and an agent start, follow, read the logs of and stop a job set the same way
  ([PRD-012](PRD-012-agent-ready.md)).

## Non-Goals

- No scheduler or cluster manager: no priorities, quotas or multi-user queues.
- No container, Kubernetes, cloud-batch or CI runner in 0.5.0; the interface admits them.
- Secrets never travel: a remote host uses its own keys and environment.
- No GPU management of its own: preparing a host is a command the project names.

## Personas

- **The engineer with a GPU box** who runs local-model arms there and hosted arms at home.
- **The agent** that launches a job set, does other work, and reports when it ends.

## User Stories

- _As an engineer, I name my GPU host once in the project config and run
  `evh jobs-run round3.yaml --runner dgx`; the runs appear in my runs directory when they finish._
- _As an engineer, I run six local jobs, three at a time; a job that hits a transient error is
  retried twice; one that runs past its timeout is marked timed out._
- _As an engineer, my job set switches the GPU host to the generation stack before its generation
  jobs and to the judge stack before its judging, and restores the host's mode afterwards; the
  record shows each command and its output._
- _As an agent, I start a job set, get its id, check its status and read a failed job's log later,
  without having watched it._

## Functional Requirements

### FR1: Job sets and jobs

- **FR1.1**: A job set lists jobs: config, dataset, repeat, optional runner, optional labels
  (`gpu`), optional phase. `sweep`, a round's arms and a loop's trials
  ([PRD-009](PRD-009-prompts-and-optimisation.md)) produce job sets; `sweep` becomes a job set run
  locally one at a time.
- **FR1.2**: `evh jobs-run <file> [--runner NAME] [--jobs N]` starts it detached and prints its id
  (`--wait` to block); `--dry-run` prints the jobs, where each will run, the preparation commands
  and the estimated cost and time, and spends nothing.
- **FR1.3**: Job states: queued, running, succeeded (with its run id), failed (with the reason),
  cancelled, timed out, skipped. `evh jobs-status <id>`, `evh jobs-logs <id> [--job J]` and
  `evh jobs-stop <id>` read, follow and stop it.
- **FR1.4**: Per job: `timeout`, `max_retries` (for failures the adapter marks transient).
- **FR1.5**: Re-running a job set skips succeeded jobs and resumes interrupted ones.
- **FR1.6**: Runs made in parallel are marked so; their latency is not compared with runs made
  alone (a speed axis flags it).

### FR2: The local runner

- **FR2.1**: Runs jobs in parallel up to `--jobs`; each run is held by a lease (a lock with a
  heartbeat) that lapses when its job dies.
- **FR2.2**: Is the default; a project with no runner configuration behaves as today, detaching
  only when asked.

### FR3: The ssh runner

- **FR3.1**: Configured in the project config under `runners:`: `type: ssh`, host, working
  directory, labels, `install` (the command that installs the project's environment, the system
  under test's dependencies included), `env` (names of variables the host must already have; their
  values are never sent).
- **FR3.2**: Phases: a job set may declare `before` and `after` commands per phase (run on the
  host, once per phase), and a host-wide lock so two job sets never prepare one host at once. A
  `before` command marked as touching a shared resource needs consent each time an agent runs it
  ([PRD-012](PRD-012-agent-ready.md)).
- **FR3.3**: Sends the project's code and the frozen data a job needs; runs `install` when the
  environment is missing or stale; runs `evh experiment-run` there with a log; follows it; brings
  the run directory back; runs `evh validate` on it here.
- **FR3.4**: Refuses to start, before spending anything, when the host's harness version differs
  from the project's pin or a declared variable is missing on the host.
- **FR3.5**: The run records the host it ran on (beside the hash, [PRD-013](PRD-013-identity-and-ties.md))
  and the job set records the runner, the phases and their commands' output.

## Success Criteria

- Six jobs on the local runner with `--jobs 3` produce the same metrics as one at a time, in
  less wall time, with no shared run directory.
- A job set on an ssh host (a container with sshd in CI) produces runs that validate and compare
  as controlled with local runs of the same arm; an interrupted set resumes; a timed-out job is
  marked so.
- The podcast project's torch jobs on its GPU host can move to the ssh runner, with its GPU-mode
  switch as phase commands (to be confirmed with that project).

## Related Documents

- RFC-011 (to be written). References: Slurm job states, Kubernetes Jobs (`backoffLimit`,
  `activeDeadlineSeconds`), Ray Jobs (submit, status, logs, stop), GitHub self-hosted runners
  (labels, secrets kept on the host), Inspect eval sets (a log directory as resumable state).
