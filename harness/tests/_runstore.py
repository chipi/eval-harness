"""Run fixtures in the store the suite runs in (RFC-025): EVAL_STORE, files by default.

What a test needs beyond `_outputs` and `_runs.item_rows`: raw rows text (a malformed line, an emptied file), every
line parsed, and a run copied with its outputs and rows, in whichever store the project is.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from evaluation_harness import _outputs, _store


def sqlite() -> bool:
    """Whether the suite runs on the sqlite store."""
    return os.environ.get("EVAL_STORE", "").strip() == "sqlite"


def put_rows_text(run_dir: Path, text: str, partial: bool = False) -> None:
    """A run's rows exactly as given, malformed lines included (a test of a reader's refusals)."""
    _store.mkdir(run_dir, parents=True, exist_ok=True)
    _outputs.store().put_rows(Path(run_dir), text, partial)


def rows(run_dir: Path, partial: bool = False) -> list[dict[str, Any]]:
    """A run's rows, each non-blank line parsed (a row without an item id included)."""
    text = _outputs.rows_text(Path(run_dir), partial) or ""
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def drop_rows(run_dir: Path, partial: bool = False) -> None:
    """A run's rows (or its checkpoint) removed."""
    _outputs.store().drop_rows(Path(run_dir), partial)


def copy_run(src: Path, dst: Path) -> None:
    """A run copied, its directory and its outputs, rows and row checkpoint, wherever each run's store keeps them."""
    _store.copy_tree(src, dst, files_only=True)  # its outputs and rows are copied below
    st = _outputs.store()
    outs = st.lines(Path(src))
    if outs:
        st.write_all(Path(dst), {o["item_id"]: o["text"] for o in outs}, [o["item_id"] for o in outs])
    for partial in (False, True):
        text = st.rows_text(Path(src), partial)
        if text is not None:
            st.put_rows(Path(dst), text, partial)


# ── a test project's data, read and written in its store ──────────────────────────────────────────────────────────
# A test that runs `evh` on a project of its own reads what the command wrote, and writes the fixtures it starts from,
# where the store keeps them: on disk in the files store, in data/project.sqlite in the sqlite store. These aim
# _store at that project for the call only (its EVAL_HOME), whatever this process's own project is, and refuse to
# touch anything when the project's data/ is not where they were told: a test must never write this repository's data.
_PROJECT_KEYS = ("EVAL_HOME", "EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_GOALS_DIR")


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
