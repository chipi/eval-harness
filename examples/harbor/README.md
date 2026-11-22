# Harbor: agent trials as a system

[Harbor](https://pypi.org/project/harbor/) runs an agent on a task inside a container and a verifier gives its reward. This
example makes that an eval: Harbor tasks are the dataset's items, one `harbor run` trial per item is the system, and the
trial's directory is the item's artifact. The harness gets three generic hooks from it and nothing else; none of its code
names Harbor (`test_core_stays_generic` fails when one does).

| file | what it is |
|---|---|
| `source.py` | `Source`: a folder of Harbor tasks (or a registry dataset) as a dataset, one item per task |
| `importer.py` | `Importer`: Harbor job directories as a capture, then a dataset and a recorded arm; needs neither Docker nor Harbor |
| `adapter.py` | the system: one `harbor run -n 1 -r 0` trial per item, **called once** (`CALL_ONCE`), the trial as the artifact |
| `systems/` | `harbor_oracle_v1`, `harbor_nop_v1`, and `harbor_agent_template.yaml.example` (a template, never run) |
| `tasks/` | three tiny tasks of our own: `write-greeting`, `count-lines`, `make-script` |
| `fields.yaml` | the field set the source's fields need (`difficulty`, `category`, `agent_timeout_sec`) |
| `fixtures/jobs/` | job directories recorded from Harbor's `oracle` and `nop` agents on those tasks (and one agent timeout), scrubbed; one is synthetic |
| `fake_harbor.py`, `test_harbor.py` | a stand-in `harbor` and the tests: no Docker, no model, no network |
| `record_fixtures.py` | records the fixtures again (needs Docker and `harbor`; $0) |

Needs `harbor` on the PATH for a live run (`uv tool install harbor`; written against 0.26.0) and a container engine
(Docker). **Run it from the project's root**: the trials land under `artifacts/`, which the inspector serves, and an item's
artifact must lie inside the project.

## Run it for $0

Harbor's `oracle` agent runs the task's own `solution/solve.sh` in the task's container: no model is called, no key is
needed, and the run costs nothing. Its `nop` agent does nothing: the verifier then runs on an untouched container and
should fail every task, which proves a pass is not free. Together they are the ceiling and the floor of a real agent. The
tasks' image is `ubuntu:24.04`; the first run pulls it.

In a project that has this example at `examples/harbor` (copy it, or link it):

```bash
evh data-put --new --path validate.json --set 'systems=["examples/harbor/systems/harbor_*_v1.yaml"]'
evh data-put --new --path fields/harbor_tasks.yaml --file examples/harbor/fields.yaml
evh dataset-create --dataset-id harbor_tasks_v1 --source examples/harbor/source.py:Source \
    --query '{"path": "examples/harbor/tasks"}' --fieldset harbor_tasks
evh dataset-materialize --dataset-id harbor_tasks_v1
evh run --system harbor_oracle_v1 --dataset harbor_tasks_v1
evh run --system harbor_nop_v1 --dataset harbor_tasks_v1
```

What this printed, on the machine that made the fixtures (Harbor 0.26.0, Docker; 51 s a run, 17 s a trial, most of it
Harbor starting the container):

```text
  calls each item once (the adapter declares CALL_ONCE): no retry, a failure is a failed item, and --resume
  does not call a failed or in-doubt item again unless --recall-failed names them
  [1/3] count-lines pass=1 16.7s  about 33 s left
  [2/3] make-script pass=1 17.1s
  [3/3] write-greeting pass=1 16.6s
  harbor_oracle_v1_…  answered=1.0  cost_usd=0.0  latency_ms=16805.942  pass=1.0  reward=1.0  tests_passed_frac=1.0  total_cost_usd=0.0

  [1/3] count-lines pass=0 16.4s  about 33 s left
  [2/3] make-script pass=0 16.9s
  [3/3] write-greeting pass=0 16.3s
  harbor_nop_v1_…  answered=1.0  cost_usd=0.0  latency_ms=16525.676667  pass=0.0  reward=0.0  tests_passed_frac=0.0  total_cost_usd=0.0
```

The run prints "no reference set … quality cannot be scored" first. It is true and does not matter here: the verifier
scores a trial, so there is no reference to promote. `pass` is the primary metric, 1 when the verifier's reward is 1.0;
`reward` and `tests_passed_frac` (from the verifier's `ctrf.json`, when it writes one) are beside it.

Open a trial: `evh comparison-item --runs harbor_oracle_v1 --item write-greeting` prints

```text
== harbor_oracle_v1  (baseline)
(run harbor_oracle_v1_… · artifact artifacts/harbor_oracle_v1/write-greeting-20261120T202549-3462570-d86abf/write-greeting__oYFJTeo)
{"answered": true, "exception": null, "pass": true, "reward": 1.0, "task": "write-greeting", "tests": {...}, "trial": "write-greeting__oYFJTeo"}
```

and the inspector (`evh catalog-serve`) draws that path as a link to the directory, served read-only with `nosniff` and
`sandbox`: Harbor's `result.json`, the verifier's `ctrf.json` and `test-stdout.txt`, and, for an agent with a model, its
`agent/` folder and trajectory. The harness reads none of it; the link is how a person does.

## What the adapter does

- **Called once.** `CALL_ONCE = True`: the core never retries a trial, a timeout or "connection reset by peer" included, and
  the adapter passes `-r 0` to Harbor and does not retry either. `--resume` of a run does not call a failed item, or one the
  process died in, again unless `--recall-failed` names them ([RUNBOOK](../../harness/docs/RUNBOOK.md)).
- **Its own timeout.** Harbor's flags are multipliers, not seconds. The adapter gives each trial the task's agent, verifier
  and environment-build timeouts plus 120 s (`timeout_s` and `timeout_slack_s` change it), and on expiry sends SIGTERM to
  the process group, then SIGKILL after `kill_grace_s` (20 s). The item fails with `HarborTimeout`, and its trial directory
  is its artifact.
- **What a failure is.** A trial that ran and ended badly (Harbor wrote its `result.json`: a wrong answer, the agent's
  exception) is a scored 0 with the exception in its output: the agent failed the task, and a run of hard tasks is not
  stopped by the core's rule for a broken adapter. A call that gave no trial result (Harbor crashed, our timeout, no
  `result.json`) is a failed item, called once.
- **The cost.** 0.0 for `oracle` and `nop`, with `cost_source: no-model-agent`; for an agent with a model, the agent's own
  estimate from Harbor's `result.json`, `cost_source: harbor-agent-estimate`. A gateway's spend is not read: that is a
  project's own hook.

An item is `{"task", "path" or "dataset", "instruction"}`. A registry dataset works the same way (`--query
'{"dataset": "NAME@VERSION"}'`): the source runs `harbor dataset download` into `.build/harbor/` (network), and a run asks
Harbor for the task with `-d NAME@VERSION -i TASK`.

## A recorded arm: job directories already on disk

```bash
evh capture --importer examples/harbor/importer.py:Importer \
    --query '{"jobs_dir": "artifacts/harbor_oracle_v1"}' --capture harbor_oracle_jobs
evh dataset-from-capture --capture harbor_oracle_jobs --dataset-id harbor_hist_v1
evh dataset-materialize --dataset-id harbor_hist_v1
evh arm-from-capture --dataset-id harbor_hist_v1 --capture harbor_oracle_jobs --as harbor_recorded_v1 --like harbor_oracle_v1
```

One record per trial directory (its id is the trial's name), scored by the same `score` as a live trial, at cost 0. The
last command printed `pass=1.0  reward=1.0  tests_passed_frac=1.0` for the three oracle trials. A task run in several
trials is several items; `"pick": "first"` or `"last"` in the query keeps one per task.

## A model-backed agent

`systems/harbor_agent_template.yaml.example` is a template, not a system, and nothing here runs it: an agent with a model costs
money and needs a key. Copy it to `data/systems/<id>.yaml` (the `.example` suffix keeps `evh validate` from reading a file that is no system), fill it in, put the key in the environment file Harbor reads (`env_file`), set
`EVAL_MAX_COST_USD`, and check one task with `evh arm-smoke` first. `evh run --dry-run` cannot estimate a trial's cost: it is
the agent's own, known after the run.

## The tests, and what they are made of

`python examples/harbor/test_harbor.py` (the harness's self-test runs it) uses `fixtures/jobs/`, `fake_harbor.py` as
`harbor` on the PATH, and a temporary project. It checks: the fixtures hold no path, URL or key; the source, with fields and
no author; the importer; the live adapter and a recorded arm give the same output and score for the same trial; `harbor`
is called once per item, with `-r 0`, whatever the failure (a crash, "connection reset by peer", a hang); `--resume` does
not call a failed item again and `--recall-failed` calls it once; a hang ends at the timeout and leaves no process, SIGTERM
or not; the item's link is a directory the server serves read-only; the core names nothing of Harbor.

**Where the fixtures come from.** Seven are recorded, by `record_fixtures.py`, from the real `harbor run` (Harbor 0.26.0), with
`agent/`, the logs and the lock files left out and the machine's paths, `trial_uri`, `base_url`, `model_api_key_name` and the
home folder in a traceback scrubbed: `oracle-<task>` and `nop-<task>` for the three tasks, and `timeout-write-greeting`, the
`oracle` agent on a copy of `write-greeting` whose solution sleeps past its 3 s agent timeout (the fixture says the task is
the one in `tasks/`; its `task_checksum` is the copy's). Harbor ends that trial with an `AgentTimeoutError` and still runs the
verifier: reward 0, the exception and the reward in one `result.json`. **One is not recorded:** `exception-write-greeting`
is the `oracle` job edited to have the shape of a trial that never reached its verifier (an `EnvironmentStartTimeoutError` in
Harbor's `ExceptionInfo`, read from its source, and no verifier result), which no run here produced. It is the only fixture a
real failure should replace; `python examples/harbor/record_fixtures.py --exception-only` makes it again from the oracle one.

## What is not covered

Not run, here or in CI: a model-backed agent; a Harbor environment other than Docker (podman is not installed here); the
registry route against a live `harbor run -d … -i …` (`harbor dataset download NovitaAI/tb21-file-recovery -o DIR` was run
once by hand and put its nine tasks at `DIR/tb21-file-recovery/<task>/`, the layout the source reads; no trial of them was
run).

Measured once by hand against Harbor 0.26.0 and Docker, on a task whose solution sleeps: SIGTERM to Harbor's process group
ends the trial (its `result.json` records a `CancelledError`) and Harbor removes the container, in 10 to 15 s here, which is
why the adapter waits `kill_grace_s` (20 s) before SIGKILL; a **SIGKILLed Harbor leaves its container running**, so raise
`kill_grace_s` if your containers are slow to stop. A trial whose agent times out exits `harbor run` with 0 and an
`AgentTimeoutError` in its `result.json`: the adapter reads the trial's `result.json`, not the exit code, and treats a
missing one as a failed item.
