"""Three look-alike projects of the beta projects' shapes, built with invented names, numbers and text (RFC-041, PLAN
0.8.1 R2). No data of any real project is in them: only the SHAPES were read (which fields are null, how ids look, how
many arms, how a goal's measure is written).

    import _foreign
    facts = _foreign.imported(proj, env)     # or fleet(...), bakeoff(...)

  - `imported`: runs written by `evh import-run`, none naming a goal; free-text build refs with `dirty: null`; no
    reference; 64 arms on one dataset, a few on others; goals whose measures are prose and one `non_inferior`; `wer`
    with no declared direction on two datasets and declared lower on a third; 3 to 6 items (shape of the podcast
    eval-data project).
  - `fleet`: made by `evh run` on the echo provider ($0, offline): a `--repeat 3` set with one pass deleted, then a
    `--purpose repeat --of` run of the same config; a repeat with `of` on a changed setting; runs with no goal; two
    goals on one dataset with different baselines; a round with arms (shape of the fleet eval-data project).
  - `bakeoff`: a custom adapter.py declaring METRIC_KINDS and no METRIC_DIRECTIONS; zero-price systems; datasets of 3
    and 22 items; a goal on `pass`; two runs through a stub (shape of the bake-off project).

Run ids are given explicitly, so every build makes the same ids; each builder returns the names a test asserts on. The
runs are made by the harness's own commands, in the store EVAL_STORE names.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import _cli
import _runstore
from evaluation_harness import _format

KIT = Path(__file__).resolve().parents[1] / "tutorial"


class Build:
    """A project under construction: commands that must succeed, and files written through the store."""

    def __init__(self, proj: Path, env: dict[str, str]) -> None:
        self.proj, self.env = proj, env

    def evh(self, *args: Any) -> Any:
        """Run `evh <args>` in the project and give back the finished process."""
        return _cli.run(self.proj, self.env, *args)

    def must(self, *args: Any) -> Any:
        """Run `evh <args>`; raise RuntimeError with the output's tail when it exits non-zero."""
        r = self.evh(*args)
        if r.returncode != 0:
            raise RuntimeError(
                f"evh {' '.join(map(str, args))} failed ({r.returncode}): {(r.stdout + r.stderr)[-600:]}"
            )
        return r

    def put(self, rel: str, text: str) -> None:
        """Write a file of the project through the store, so a sqlite store holds it too."""
        _runstore.write_text(self.proj, rel, text)

    def init(self) -> None:
        """Write the format marker, and the systems folder a file store needs."""
        self.put(_format.NAME, f"format: {_format.FORMAT}\n")
        if not _runstore.sqlite():
            (self.proj / "data" / "systems").mkdir(parents=True, exist_ok=True)

    def source(self, dataset_id: str, items: dict[str, str]) -> None:
        """Items as files under sources/<id> and the dataset frozen from them."""
        d = self.proj / "sources" / dataset_id
        d.mkdir(parents=True)
        for name, text in items.items():
            (d / f"{name}.txt").write_text(text + "\n", encoding="utf-8")
        self.must("dataset-create", "--dataset-id", dataset_id, "--source-dir", d)
        self.must("dataset-materialize", "--dataset-id", dataset_id)


def _goal(gid: str, measure: str, direction: str, datasets: list[str], axes: str = "") -> str:
    ds = "".join(f"  - {{dataset_id: {d}, role: validation}}\n" for d in datasets)
    return (
        f'goal_id: {gid}\nschema_version: "0.1"\ntitle: {gid.replace("_", " ")}\nstatement: An invented goal for a fixture.\ndecision: An invented decision.\nstatus: active\n'
        f"success_criteria:\n  primary:\n    measure: {measure}\n    direction: {direction}\n{axes}"
        f"datasets:\n{ds}"
    )


# ── imported ─────────────────────────────────────────────────────────────────
IMPORTED_BIG = "meeting_clips_v1"
IMPORTED_NO_DIRECTION = ("meeting_clips_v1", "call_audio_v1")
IMPORTED_LOWER = "lecture_set_v1"
IMPORTED_ARMS = 64


def imported(proj: Path, env: dict[str, str]) -> dict[str, Any]:
    """Build the imported-shape project; return its run ids per dataset, its datasets and its goals."""
    b = Build(proj, env)
    b.init()
    sets = {
        "meeting_clips_v1": [f"clip_{i:02d}" for i in range(1, 6)],
        "call_audio_v1": [f"call_{i:02d}" for i in range(1, 5)],
        "lecture_set_v1": [f"talk_{i:02d}" for i in range(1, 4)],
    }
    for ds, ids in sets.items():
        b.source(
            ds, {i: f"Invented sample {i} of {ds}: a short passage read aloud, nothing more." for i in ids}
        )
    scores = proj / "scores"
    scores.mkdir()
    runs: dict[str, list[str]] = {ds: [] for ds in sets}

    pending: list[dict[str, Any]] = []

    def one(ds: str, n: int, system: str, asc: bool, with_der: bool, cli: bool = False) -> None:
        rows = []
        for k, item in enumerate(sets[ds]):
            row: dict[str, Any] = {"item_id": item, "wer": round(0.03 + ((n * 37 + k * 11) % 211) / 1000, 3)}
            if with_der:
                row["der"] = round(0.02 + ((n * 53 + k * 7) % 211) / 1000, 3)
            rows.append(row)
        f = scores / f"{system}.jsonl"
        f.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        run_id = f"{system}_20260901T{10 + n // 60:02d}{n % 60:02d}00Z"
        spec = {
            "dataset_id": ds, "system_id": system, "scores": str(f), "primary_metric": "wer", "asc": asc,
            "build_ref": f"model snapshot {n % 7}; scoring rev from {1 + n % 3} weeks back",
            "source": f"scratch/old_runs/{system}", "scorer_id": "wer_scorer via tools/rescore.py",
            "run_id": run_id,
        }  # fmt: skip
        if (
            cli
        ):  # the command itself; the rest go through its operation in one process (a process each took 0.8 s)
            b.must(
                "import-run", "--dataset-id", ds, "--system-id", system, "--scores", f, "--primary-metric", "wer",
                *(["--asc"] if asc else []), "--build-ref", spec["build_ref"], "--source", spec["source"],
                "--scorer-id", spec["scorer_id"], "--run-id", run_id,
            )  # fmt: skip
        else:
            pending.append(spec)
        runs[ds].append(run_id)

    for n in range(IMPORTED_ARMS):
        one(IMPORTED_BIG, n, f"q{n:02d}__small_en__beam_{n % 5}", False, False, cli=n == 0)
    for n in range(4):
        one("call_audio_v1", 100 + n, f"q{100 + n}__phone__cfg_{n}", False, True, cli=n == 0)
    for n in range(3):
        one(IMPORTED_LOWER, 200 + n, f"q{200 + n}__lecture__cfg_{n}", True, False, cli=n == 0)
    batch = proj / "import_specs.json"
    batch.write_text(json.dumps(pending), encoding="utf-8")
    r = subprocess.run(  # nosec B603 - this interpreter and the harness's own operation
        [sys.executable, str(Path(__file__).with_name("_foreign_import.py")), str(batch)],
        cwd=proj, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False, encoding="utf-8",
    )  # fmt: skip
    if r.returncode != 0:
        raise RuntimeError(f"batch import-run failed: {(r.stdout + r.stderr)[-600:]}")

    b.put(
        "goals/english_transcription.yaml",
        _goal(
            "english_transcription", "WER vs human transcript (ascii-v1)", "lower",
            ["meeting_clips_v1", "lecture_set_v1"], "  axes:\n    realtime_factor:\n      direction: higher\n",
        ),
    )  # fmt: skip
    b.put(
        "goals/speaker_attribution.yaml",
        _goal("speaker_attribution", "Diarization error (DER)", "lower", ["call_audio_v1"]),
    )
    b.put(
        "goals/regression_detection.yaml",
        _goal(
            "regression_detection", "score vs baseline on the baseline reference (paired test)",
            "non_inferior", ["meeting_clips_v1"],
        ),
    )  # fmt: skip
    return {
        "runs": runs,
        "datasets": sorted(sets),
        "goals": ["english_transcription", "regression_detection", "speaker_attribution"],
    }


# ── fleet-shaped ─────────────────────────────────────────────────────────────
FLEET_DS = "queue_triage_v1"


def _fleet_system(b: Build, name: str, sentences: int) -> str:
    sid = f"{name}_v1"
    b.put(f"systems/{sid}.yaml", f"system_id: {sid}\nparams:\n  provider: echo\n  sentences: {sentences}\n")
    return sid


def fleet(proj: Path, env: dict[str, str]) -> dict[str, Any]:
    """Build the fleet-shape project in git, with runs, a promoted baseline per goal and an open round; return the names a test asserts on."""
    b = Build(proj, env)
    b.init()
    # A project in git, as the fleet's is: a run records the commit and `dirty: true` (the data is not committed).
    for git in (
        ["init", "-q"],
        [
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "start",
        ],
    ):
        subprocess.run(["git", *git], cwd=proj, check=True, capture_output=True, stdin=subprocess.DEVNULL)  # nosec B603 B607
    shutil.copytree(KIT / "tickets", proj / "tickets")
    b.must("dataset-create", "--dataset-id", FLEET_DS, "--source-dir", "tickets")
    b.must("dataset-materialize", "--dataset-id", FLEET_DS)
    b.must(
        "label-import", "--sheet", str(KIT / "gold"), "--dataset-id", FLEET_DS, "--set", "g", "--by", "ana"
    )
    b.must(
        "reference-promote", "--dataset-id", FLEET_DS, "--labels", "g", "--tier", "gold",
        "--reason", "The hand-written summaries decide this queue.", "--by", "ana",
    )  # fmt: skip
    for gid in ("triage_a", "triage_b"):
        b.put(
            f"goals/{gid}.yaml",
            _goal(gid, "overlap_f1", "higher", [FLEET_DS]).replace(
                "measure: overlap_f1", "measure: overlap_f1"
            ),
        )

    x = _fleet_system(b, "arm_x", 2)
    base = "arm_x_v1_20261110T100000Z"
    b.must(
        "run", "--system", x, "--dataset", FLEET_DS, "--goal", "triage_a", "--repeat", "3", "--run-id", base
    )
    lost = f"{base}_r2"
    _runstore.rmtree(proj, f"runs/{lost}")
    joined = "arm_x_v1_20261110T110000Z"
    b.must(
        "run", "--system", x, "--dataset", FLEET_DS, "--goal", "triage_a", "--purpose", "repeat",
        "--of", f"{base}_r1", "--run-id", joined,
    )  # fmt: skip

    y = _fleet_system(b, "arm_y", 1)
    y_first = "arm_y_v1_20261110T120000Z"
    b.must("run", "--system", y, "--dataset", FLEET_DS, "--goal", "triage_a", "--run-id", y_first)
    _fleet_system(b, "arm_y", 3)  # the setting changes, then the "repeat"
    y_changed = "arm_y_v1_20261110T130000Z"
    changed = b.evh(
        "run", "--system", y, "--dataset", FLEET_DS, "--goal", "triage_a", "--purpose", "repeat",
        "--of", y_first, "--run-id", y_changed,
    )  # fmt: skip
    _fleet_system(b, "arm_y", 1)

    z = _fleet_system(b, "arm_z", 3)
    no_goal = "arm_z_v1_20261110T140000Z"
    b.must("run", "--system", z, "--dataset", FLEET_DS, "--run-id", no_goal)

    b.must(
        "run-promote",
        "--run",
        f"{base}_r1",
        "--goal",
        "triage_a",
        "--reason",
        "The first arm leads on goal a; the tree was dirty while it ran.",
        "--allow-dirty",
        "--by",
        "ana",
    )
    b.must(
        "run-promote",
        "--run",
        y_first,
        "--goal",
        "triage_b",
        "--reason",
        "Another arm leads on goal b; the tree was dirty while it ran.",
        "--allow-dirty",
        "--by",
        "ana",
    )

    b.must(
        "round-open", "--goal", "triage_a", "--dataset", FLEET_DS, "--hypothesis", "two sentences or one",
        "--keep", "arm_x_v1,arm_y_v1",
    )  # fmt: skip
    return {
        "dataset": FLEET_DS,
        "goals": ["triage_a", "triage_b"],
        "arm_lost": "arm_x_v1",
        "set": [f"{base}_r1", f"{base}_r3"],
        "lost": lost,
        "joined": joined,
        "arm_changed": "arm_y_v1",
        "changed_run": y_changed,
        "changed_ok": changed.returncode == 0,
        "changed_out": (changed.stdout + changed.stderr)[-400:],
        "first_y": y_first,
        "no_goal": no_goal,
        "baselines": {"triage_a": f"{base}_r1", "triage_b": y_first},
        "round": "r1",
    }


# ── bakeoff-shaped ───────────────────────────────────────────────────────────
BAKEOFF_ADAPTER = '''"""An adapter of a coding bake-off's shape, offline: it declares kinds and no directions."""
from evaluation_harness.adapter import Result

PRIMARY_METRIC = "pass"
METRIC_KINDS = {"answered": "descriptive", "turns": "descriptive", "checks_frac": "descriptive"}
METRIC_DESCRIPTIONS = {
    "pass": "1 when every check of the task passed, else 0",
    "answered": "1 when the stub returned an answer",
    "turns": "the stub's number of turns for the task",
}


def call_system(text, params):
    n = len(text.split())
    tin, tout = 40 + n, 12
    pin, pout = params.get("usd_per_mtok_in"), params.get("usd_per_mtok_out")
    usd = None if pin is None or pout is None else (tin * pin + tout * pout) / 1e6  # a price of 0 costs 0.0
    return Result(output=text[: 8 + n], tokens_in=tin, tokens_out=tout, cost_usd=usd, extra={"turns": 2.0 + n % 3})


def score(output, reference=None):
    ok = 1.0 if len(output) % 2 == 0 else 0.0
    return {"pass": ok, "answered": 1.0, "checks_frac": 0.5 + 0.5 * ok}
'''
BAKEOFF_SMALL, BAKEOFF_BIG = "task_set_small_v1", "task_set_wide_v1"


def bakeoff(proj: Path, env: dict[str, str]) -> dict[str, Any]:
    """Build the bake-off-shape project with a custom adapter and zero-price systems; return its runs, datasets, goals and systems."""
    b = Build(proj, {**env, "EVAL_BUILD_REF": "bakeoff-fixture-1"})
    b.init()
    (proj / "adapter.py").write_text(BAKEOFF_ADAPTER, encoding="utf-8")
    b.source(
        BAKEOFF_SMALL,
        {f"job_{i}": f"Invented task {i}: rename a helper across two files and report." for i in range(1, 4)},
    )
    b.source(
        BAKEOFF_BIG,
        {
            f"job_{i:02d}": f"Invented task {i}: read the log of batch {i * 13} and say how many lines."
            for i in range(1, 23)
        },
    )
    for name, host in (("local_alpha", "hosted_a"), ("local_beta", "hosted_b"), ("local_gamma", "hosted_c")):
        b.put(
            f"systems/{name}.yaml",
            f"system_id: {name}\n# {host}: a zero-price local model\nparams:\n  provider: stub\n  model: {name}-7b\n"
            "  usd_per_mtok_in: 0\n  usd_per_mtok_out: 0\n  max_context: 32768\n",
        )
    b.put(
        "goals/bakeoff_small.yaml",
        _goal("bakeoff_small", "pass", "higher", [BAKEOFF_SMALL]).replace(
            "pass\n    direction: higher\n", "pass\n    direction: higher\n  min_items: 3\n", 1
        ),
    )
    b.put("goals/bakeoff_wide.yaml", _goal("bakeoff_wide", "pass", "higher", [BAKEOFF_BIG]))
    runs = []
    for i, (sysid, ds) in enumerate((("local_alpha", BAKEOFF_SMALL), ("local_beta", BAKEOFF_BIG))):
        rid = f"{sysid}_20261120T1{i}0000Z"
        b.must("run", "--system", sysid, "--dataset", ds, "--run-id", rid)
        runs.append(rid)
    return {
        "runs": runs,
        "datasets": [BAKEOFF_SMALL, BAKEOFF_BIG],
        "goals": ["bakeoff_small", "bakeoff_wide"],
        "systems": ["local_alpha", "local_beta", "local_gamma"],
    }
