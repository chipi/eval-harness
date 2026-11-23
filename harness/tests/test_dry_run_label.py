#!/usr/bin/env python3
"""`evh run --dry-run` says what runs: the project's adapter, or the provider the system names (RFC-041's class: a default
read as a fact).

  EVAL_STORE=files python tests/test_dry_run_label.py        (and EVAL_STORE=sqlite)

A system with its own adapter and no `provider` was labelled `(echo)`, the bundled adapter's default, though the bundled
adapter does not run. Now: the bundled adapter's system names its provider (echo by default); a project's adapter is named,
with the provider and model its system sets when it sets them; the JSON says the same.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HERE))
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-dry-label-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-dry-label", EVAL_MAX_RETRIES="0")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)

ADAPTER = """
from evaluation_harness.adapter import Result

def call_system(text, params):
    return Result(output=text, tokens_in=1, tokens_out=1, cost_usd=0.0)

def score(output, reference):
    return {"words_out": float(len(output.split()))}
"""


def evh(*args):
    return _cli.run(proj, env, *args)


def system(name: str, body: str) -> None:
    _runstore.write_text(proj, f"systems/{name}.yaml", f"system_id: {name}\n{body}")


def system_line(name: str) -> str:
    r = evh("run", "--system", name, "--dataset", "tickets_v1", "--dry-run")
    return next(
        (ln.strip() for ln in r.stdout.splitlines() if ln.strip().startswith("system ")), r.stderr[-300:]
    )


try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (proj / "data" / "systems").mkdir(parents=True)
        (proj / "data" / "models").mkdir()
    shutil.copytree(HARNESS / "tutorial" / "tickets", proj / "tutorial" / "tickets")
    (proj / "adapters").mkdir()
    (proj / "adapters" / "mine.py").write_text(ADAPTER)
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: a frozen dataset", r.returncode == 0, r.stderr[-300:])
    system("bundled_v1", "params:\n  max_tokens: 50\n")
    system("bundled_model_v1", "params:\n  provider: openai\n  model: gpt-x\n")
    system("custom_v1", "adapter: adapters/mine.py\nparams:\n  words: 6\n")
    system("custom_provider_v1", "adapter: adapters/mine.py\nparams:\n  provider: openai\n  model: gpt-x\n")
    system("custom_model_v1", "adapter: adapters/mine.py\nparams:\n  model: alias-x\n")

    check(
        "bundled adapter, no provider: echo, the bundled adapter's default",
        system_line("bundled_v1") == "system      bundled_v1  (echo)",
        system_line("bundled_v1"),
    )
    check(
        "bundled adapter, a provider and model: those",
        system_line("bundled_model_v1") == "system      bundled_model_v1  (openai / gpt-x)",
        system_line("bundled_model_v1"),
    )
    line = system_line("custom_v1")
    check(
        "a project's adapter and no provider: the adapter is named, echo is not",
        "adapters/mine.py" in line and "echo" not in line,
        line,
    )
    line = system_line("custom_provider_v1")
    check(
        "a project's adapter whose system names a provider: both are named",
        "adapters/mine.py" in line and "openai" in line and "gpt-x" in line and "echo" not in line,
        line,
    )
    # The bake-off's shape (R8, 2026-11-24): a project's adapter whose system sets a model and no provider. 0.8.0 named
    # the model; the adapter label must not drop it, since systems that differ only in their model differ only there.
    line = system_line("custom_model_v1")
    check(
        "a project's adapter whose system names a model and no provider: the adapter and the model are named",
        line == "system      custom_model_v1  (adapter adapters/mine.py / alias-x)",
        line,
    )
    r = evh("run", "--system", "custom_v1", "--dataset", "tickets_v1", "--dry-run", "--json")
    val = (json.loads(r.stdout).get("result") or {}) if r.returncode == 0 and r.stdout.strip() else {}
    val = (val.get("values") or {}).get("dry_run") or {}
    check(
        "--json: the adapter is named and the provider is not made up",
        val.get("adapter") == "adapters/mine.py" and val.get("provider") in (None, ""),
        {k: val.get(k) for k in ("adapter", "provider")} or r.stderr[-300:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
