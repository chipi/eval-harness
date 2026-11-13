"""Run fixtures in the store the suite runs in (RFC-025): EVAL_STORE, files by default.

What a test needs beyond `_outputs` and `_runs.item_rows`: raw rows text (a malformed line, an emptied file), every
line parsed, a run made with its scores, and a run copied with its outputs and scores' rows, in whichever store the
project is. A score's rows are in its directory (`runs/<id>/scores/<key>/`, model/runs), the run's outputs and its
checkpoint in the run's.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from evaluation_harness import _outputs, _store
from evaluation_harness.model import runs as model_runs


def sqlite() -> bool:
    """Whether the suite runs on the sqlite store."""
    return os.environ.get("EVAL_STORE", "").strip() == "sqlite"


def put_rows_text(run_dir: Path, text: str, partial: bool = False) -> None:
    """A score's rows (a run's checkpoint with `partial`) exactly as given, malformed lines included (a test of a
    reader's refusals)."""
    _store.mkdir(run_dir, parents=True, exist_ok=True)
    _outputs.store().put_rows(Path(run_dir), text, partial)


def rows(run_dir: Path, partial: bool = False) -> list[dict[str, Any]]:
    """A score's rows, each non-blank line parsed (a row without an item id included)."""
    text = _outputs.rows_text(Path(run_dir), partial) or ""
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def run_rows(run_dir: Path) -> list[dict[str, Any]]:
    """The rows of a run's first score: the measurement the pass made."""
    sd = model_runs.first_score(Path(run_dir))
    return rows(sd) if sd else []


def drop_rows(run_dir: Path, partial: bool = False) -> None:
    """A score's rows (or a run's checkpoint) removed."""
    _outputs.store().drop_rows(Path(run_dir), partial)


def make_run(
    runs: Path,
    run_id: str,
    run_rec: dict[str, Any],
    *,
    outputs: dict[str, str] | None = None,
    scores: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
) -> Path:
    """A run in `runs` (a project's data/runs, or a folder of a test's own), written as `model.runs` writes one:
    run.json (`run_rec`, with its run_id), its outputs, and each score of `scores` under it: {scorer, reference,
    label, first, metrics (what the score keeps beside run.json), rows}. Returns the run's directory."""
    d = Path(runs) / run_id
    _store.mkdir(d, parents=True, exist_ok=True)
    _store.write_text(d / model_runs.RUN, json.dumps({"run_id": run_id, **run_rec}, indent=2) + "\n")
    if outputs:
        _outputs.write_all(d, outputs, list(outputs))
    for sc in scores:
        sd = d / "scores" / model_runs.key(sc["scorer"], sc.get("reference"))
        _store.mkdir(sd, parents=True, exist_ok=True)
        meta = {"scorer": sc["scorer"], "reference": sc.get("reference"), "label": sc.get("label", "")}
        if sc.get("first"):
            meta["first"] = True
        _store.write_text(sd / model_runs.SCORE, json.dumps(meta, indent=2) + "\n")
        _store.write_text(sd / model_runs.METRICS, json.dumps(sc.get("metrics") or {}, indent=2) + "\n")
        if sc.get("rows") is not None:
            _outputs.write_rows(sd, sc["rows"])
    return d


def copy_run(src: Path, dst: Path) -> None:
    """A run copied, its directory and its outputs, its checkpoint and each score's rows, wherever each run's store
    keeps them."""
    _store.copy_tree(src, dst, files_only=True)  # its outputs and rows are copied below
    st = _outputs.store()
    outs = st.lines(Path(src))
    if outs:
        st.write_all(Path(dst), {o["item_id"]: o["text"] for o in outs}, [o["item_id"] for o in outs])
    for sd in model_runs.scores_of(Path(src)):
        for partial in (False, True):
            text = st.rows_text(sd, partial)
            if text is not None:
                st.put_rows(Path(dst) / "scores" / sd.name, text, partial)
    text = st.rows_text(Path(src), True)
    if text is not None:
        st.put_rows(Path(dst), text, True)


# ── a test project's data, read and written in its store ──────────────────────────────────────────────────────────
# A test that runs `evh` on a project of its own reads what the command wrote, and writes the fixtures it starts from,
# where the store keeps them: on disk in the files store, in data/project.sqlite in the sqlite store. These aim
# _store at that project for the call only (its EVAL_HOME), whatever this process's own project is, and refuse to
# touch anything when the project's data/ is not where they were told: a test must never write this repository's data.
_PROJECT_KEYS = ("EVAL_HOME", "EVAL_DATA_DIR", "EVAL_GOALS_DIR")


class _InProject:
    """`with _InProject(proj) as data:` _store's paths are the test project's for the block, then this process's again."""

    def __init__(self, proj: Path | str) -> None:
        self.proj = Path(proj).resolve()
        self.saved: dict[str, str | None] = {}

    def __enter__(self) -> Path:
        from evaluation_harness import _common  # noqa: PLC0415

        self.saved = {k: os.environ.get(k) for k in _PROJECT_KEYS}
        for k in _PROJECT_KEYS:
            os.environ.pop(k, None)
        os.environ["EVAL_HOME"] = str(self.proj)
        _common.project_root.cache_clear()  # both are kept for the process: a test that resolved its own first
        _common._paths.cache_clear()
        _outputs.reset()
        data = Path(_common.DATA).resolve()
        if data != self.proj / "data":
            self.__exit__(None, None, None)
            raise RuntimeError(
                f"the test project's data is {data}, not {self.proj / 'data'}: nothing touched"
            )
        return data

    def __exit__(self, *exc: object) -> None:
        from evaluation_harness import _common  # noqa: PLC0415

        _outputs.reset()
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        _common.project_root.cache_clear()
        _common._paths.cache_clear()


def read_text(proj: Path | str, rel: str) -> str:
    """A file of the test project's data/ (`rel` as under data/), from its store."""
    with _InProject(proj) as data:
        return _store.read_text(data / rel)


def read_bytes(proj: Path | str, rel: str) -> bytes:
    """A file of the test project's data/, its bytes."""
    with _InProject(proj) as data:
        return _store.read_bytes(data / rel)


def read_json(proj: Path | str, rel: str) -> Any:
    """A JSON file of the test project's data/, parsed."""
    return json.loads(read_text(proj, rel))


def write_text(proj: Path | str, rel: str, text: str) -> None:
    """A file written into the test project's data/ (a fixture, or a deliberately broken one), in its store."""
    with _InProject(proj) as data:
        _store.write_text(data / rel, text)


def write_bytes(proj: Path | str, rel: str, content: bytes) -> None:
    """A file's bytes written into the test project's data/."""
    with _InProject(proj) as data:
        _store.write_bytes(data / rel, content)


def record_of(proj: Path | str, run_id: str) -> dict[str, Any]:
    """The record of a run of the test project: its run.json with its first score's metrics over it (what a run's
    metrics.json held before RFC-032 step 4); the run's own when it has no score; {} when there is no such run."""
    with _InProject(proj) as data:
        d = data / "runs" / run_id
        sd = model_runs.first_score(d)
        return (model_runs.record(sd) if sd else model_runs.run(d)) or {}


def exists(proj: Path | str, rel: str) -> bool:
    """Whether the test project's data/ has this file or directory."""
    with _InProject(proj) as data:
        return _store.exists(data / rel)


def is_file(proj: Path | str, rel: str) -> bool:
    """Whether the test project's data/ has this file."""
    with _InProject(proj) as data:
        return _store.is_file(data / rel)


def listdir(proj: Path | str, rel: str) -> list[str]:
    """The names in a directory of the test project's data/, sorted (empty when it has none)."""
    with _InProject(proj) as data:
        d = data / rel
        return sorted(p.name for p in _store.iterdir(d)) if _store.is_dir(d) else []


def files_under(proj: Path | str, rel: str = "") -> list[str]:
    """Every file under a directory of the test project's data/, as paths relative to data/, sorted."""
    with _InProject(proj) as data:
        base = data / rel if rel else data
        return sorted(str(p.relative_to(data)) for p in _store.rglob(base, "*") if _store.is_file(p))


def unlink(proj: Path | str, rel: str) -> None:
    """A file of the test project's data/ removed."""
    with _InProject(proj) as data:
        _store.unlink(data / rel)


def rmtree(proj: Path | str, rel: str) -> None:
    """A directory of the test project's data/ removed, a run's outputs and rows with it."""
    with _InProject(proj) as data:
        _store.rmtree(data / rel)


def migrate_in(proj: Path | str) -> None:
    """In the sqlite store: a test project whose fixtures were written as files moved into its database (nothing in
    the files store), so a test can build its fixtures on disk and run every command on the store under test."""
    if not sqlite():
        return
    import subprocess  # noqa: PLC0415  # nosec B404
    import sys  # noqa: PLC0415

    env = {k: v for k, v in os.environ.items() if k not in _PROJECT_KEYS}
    env.update(EVAL_HOME=str(Path(proj).resolve()), EVAL_STORE="sqlite")
    r = subprocess.run(  # nosec B603 - this interpreter and the harness's own command
        [sys.executable, "-m", "evaluation_harness", "data-migrate", "--to", "sqlite"],
        env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False,
    )  # fmt: skip
    if r.returncode != 0:
        raise RuntimeError(f"data-migrate --to sqlite failed: {(r.stdout + r.stderr)[-500:]}")
