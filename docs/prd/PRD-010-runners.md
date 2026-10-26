# PRD-010: Runners: where experiments run

- **Status**: Draft (0.5.0)
- **Authors**: Marko Dragoljevic
- **Related UX specs**: [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) (the commands)
- **Related RFC**: RFC-011 (the runner interface, local and ssh), to be written
- **Related PRDs**: [PRD-001](PRD-001-experiments-and-comparison.md),
  [PRD-009](PRD-009-prompts-and-optimisation.md) (loops dispatch through runners),
  [PRD-012](PRD-012-agent-ready.md)

## Summary

Experiments run where the compute is: a laptop for hosted-API arms, a GPU box for local models,
later a container platform or CI. Today `experiment-run` and `sweep` run in the local process,
one after another. This PRD adds **runners**: a plan of jobs (arm × dataset × repeat) is handed
to a named runner, which runs them and brings back ordinary run directories. 0.5.0 ships the
**local** runner (jobs in parallel, a lock, resume) and a simple **ssh** runner (copy the
project to a host, run the same command there, follow its log, copy the run back, validate it
here). Because the run directory is the contract, every later runner only has to move one.

## Background & Context

- `experiment-run` resumes an interrupted run (0.4.0); `sweep` runs configs one after another
  and keeps going when one fails. Nothing runs jobs in parallel, nothing prevents two runs from
  writing the same files, and nothing runs anywhere but here.
- The podcast project reaches its GPU host (the DGX, over Tailscale) with its own ssh and rsync
  scripts, switches the GPU's serving mode before a run with an ssh command, and has no queue or
  lock. Its long jobs were interrupted by tool timeouts and once by two runs writing the same
  files.
- A run directory (`run.json`, `predictions.jsonl`, `metrics.json`, its fingerprint) is
  self-contained and validated by `evh validate`; the host it ran on is in its fingerprint.

## Goals

- One command runs a plan anywhere a runner is configured, with the same records as a local run.
- Local plans run in parallel within limits, and two jobs never write the same run.
- An ssh runner needs only ssh access and the harness installed (or installable) on the host.
- A job can prepare its host first (switch a GPU mode, start a server) and the record says what
  it ran.
- Interrupted plans resume; a runner's failure on one job does not lose the others.
- A person and an agent start, follow and stop a plan the same way, and an agent can follow one
  without holding a terminal open ([PRD-012](PRD-012-agent-ready.md)).

## Non-Goals

- No scheduler or cluster manager: no priorities, quotas or multi-user queues.
- No container, Kubernetes, cloud-batch or CI runner in 0.5.0; the interface admits them later.
- Secrets never travel: a remote host uses its own keys and environment.
- No remote GPU management of its own: a host's preparation is a command the project names.

## Personas

- **The engineer with a GPU box** who runs local-model arms there and hosted arms at home.
- **The agent** that launches a plan, does other work, and reports when it finishes.

## User Stories

- _As an engineer, I name my GPU host once in the project config and run `evh plan-run
  plans/round3.yaml --runner dgx`; the runs appear in my runs directory when they finish._
- _As an engineer, I run a local plan with four jobs at a time and two others refused because a
  run with the same id is already being written._
- _As an engineer, my host switches its GPU mode before the first job, and the plan's record
  shows the command and its output._
- _As an agent, I start a plan, get its id, check its status later, and read the failures
  without having watched it._

## Functional Requirements

### FR1: Plans and jobs

- **FR1.1**: A plan lists jobs: config, dataset, repeat, optional runner. `sweep`, a round's
  arms and a loop's steps ([PRD-009](PRD-009-prompts-and-optimisation.md)) all produce plans.
- **FR1.2**: `evh plan-run <plan> [--runner NAME] [--jobs N]` runs it; `--dry-run` prints the
  jobs, where each will run and the estimated cost, and spends nothing.
- **FR1.3**: A plan has an id and a state file: each job queued, running, done (with its run
  id), failed (with the reason) or skipped; `evh plan-status <id>` and `evh plan-stop <id>`
  read and stop it. A plan runs detached, so the command that starts it returns at once
  (`--wait` to block).
- **FR1.4**: Re-running a plan skips done jobs and resumes interrupted ones.

### FR2: The local runner

- **FR2.1**: Runs jobs in parallel up to `--jobs`; one job per run directory, held by a lock
  that a crashed job releases.
- **FR2.2**: Is the default; a project with no runner configuration behaves as today.

### FR3: The ssh runner

- **FR3.1**: Configured in the project config under `runners:`: `type: ssh`, host, working
  directory, optional `before` command (run once per plan on the host) and `env` (names of
  variables the host must already have; their values are never sent).
- **FR3.2**: Sends the project's code and the frozen data a job needs; installs or checks the
  harness version the project pins; runs `evh experiment-run` there in the background with a log;
  follows the log; brings the run directory back; runs `evh validate` on it here.
- **FR3.3**: Refuses to start when the host's harness version differs from the project's pin,
  or a declared variable is missing on the host, before spending anything.
- **FR3.4**: The run's fingerprint records the host it ran on (as today) and the plan records
  the runner.

## Success Criteria

- A plan of six jobs on the local runner with `--jobs 3` finishes in about half the time of
  `sweep`, with identical metrics.
- A plan on an ssh host (a container with sshd in CI) produces run directories that validate
  and compare like local ones; an interrupted plan resumes.
- The podcast project's DGX runs can move to an ssh runner with its GPU-mode switch as the
  `before` command (the review with that project decides whether they do).

## Related Documents

- RFC-011 (to be written).
