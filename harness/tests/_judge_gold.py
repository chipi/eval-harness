"""A project with a judge validated against people's ratings, for the tests of "the judge disagrees with the gold" (F1).

    info = build(proj, env)     # `evh` in `proj` with `env`; free: the judge is the seeded random one, no model is called

A rated dataset `rated_v1` of 12 items (four outputs each, the people's ratings the reference) and the system
`gj_pick_v1__random__validation` (the adapter `judge-validate` writes, provider random: seeded verdicts of the mode's shape)
run over it. A pick of one in four is right by chance a quarter of the time, so the run has items where the judge's pick
is among the people's best and items where it is not. Returns {"dataset", "system", "arm", "items"}.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

DATASET = "rated_v1"
SYSTEM = "gj_pick_v1__random__validation"
N = 12
TASK = {"source_label": "TICKET", "output_label": "REPLIES", "dimensions": ["accuracy"], "scale": [1, 5]}

SOURCE_PY = f"""
import json


class Source:
    def __init__(self, options):
        self.options = options

    def describe(self, query):
        return {{"source": {{"provider": "test"}}}}

    def items(self, query):
        for i in range({N}):
            outs = [f"reply {{i}} {{k}} " + "w " * k for k in range(4)]
            ratings = [float((i + k) % 4 + 1) for k in range(4)]
            yield {{"item_id": f"r{{i:02d}}", "text": json.dumps({{"source": f"Ticket {{i}}", "outputs": outs}}),
                    "answer": json.dumps({{"ratings": {{"accuracy": ratings}}}})}}
"""


def evh(proj: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    """`evh` in `proj` with `env`, its output captured."""
    return subprocess.run(
        [sys.executable, "-m", "evaluation_harness", *args],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=600,
    )


def build(proj: Path, env: dict) -> dict[str, Any]:
    """The rated dataset, the judge and its run; returns {"dataset", "system", "arm", "items"}."""
    (proj / "rated_source.py").write_text(SOURCE_PY)
    for args in (
        ("init", "--store", "files"),
        (
            "dataset-create",
            "--dataset-id",
            DATASET,
            "--source",
            "rated_source.py:Source",
            "--query",
            '{"answer": "answer"}',
        ),
        ("dataset-materialize", "--dataset-id", DATASET),
        (
            "reference-promote",
            "--dataset-id",
            DATASET,
            "--labels",
            "answers",
            "--tier",
            "gold",
            "--reason",
            "people rated them",
            "--by",
            "tester",
        ),
    ):
        r = evh(proj, env, *args)
        if r.returncode:
            raise SystemExit(f"{' '.join(args)}: {r.stdout}{r.stderr}")
    systems = proj / "data" / "systems"
    systems.mkdir(parents=True, exist_ok=True)
    params = {
        "provider": "random",
        "scorer": "gj_pick_v1",
        "judge": "random",
        "mode": "pick",
        "outputs_per_call": 4,
        "task": TASK,
        "seed": 7,
    }
    (systems / f"{SYSTEM}.yaml").write_text(
        yaml.safe_dump(
            {"system_id": SYSTEM, "adapter": "scripts/judge_validation.py", "params": params}, sort_keys=False
        )
    )
    r = evh(proj, env, "run", "--system", SYSTEM, "--dataset", DATASET)
    if r.returncode:
        raise SystemExit(f"run: {r.stdout}{r.stderr}")
    return {
        "dataset": DATASET,
        "system": SYSTEM,
        "arm": f"runs/{DATASET}/{SYSTEM}",
        "items": [f"r{i:02d}" for i in range(N)],
    }


def verdict_of(text: str) -> dict:
    """A judge reply's verdict, read as JSON."""
    return json.loads(text)
