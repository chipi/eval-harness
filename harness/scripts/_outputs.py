"""A run's outputs: one file, `outputs.jsonl`, read and written only here (RFC-024).

    {"item_id": "t00042", "text": "...the output, exactly...", "sha256": "<sha256 of the text's UTF-8 bytes>"}

A measured run appends a line per item as it is produced (`writer`), so a stopped run keeps every finished output and
`--resume` reads them back; a torn last line (a kill mid-append) is not an output, so that item is called again.
`finish` rewrites the file in dataset order when the run completes. A derived run (a re-score, a judging, a sheet
import) writes no outputs of its own: `output()` and `outputs()` follow its `derived.from` to the run whose they are.
Every module reads outputs through this one: a test fails on an `outputs/` path built anywhere else.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from evaluation_harness import _common

FILE = "outputs.jsonl"
#: The checkpoint of rows a pass appends as it goes (a crashed run has no predictions.jsonl yet); deleted by finish().
ROWS = "rows.partial.jsonl"
_CACHE: dict[str, tuple[float, dict[str, str]]] = {}
_NAMES: dict[str, list[Path]] = {}


def sha256(text: str) -> str:
    """The sha256 of an output's UTF-8 bytes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read(path: Path) -> dict[str, str]:
    """{item_id: text} of one outputs.jsonl, a torn last line skipped; kept for the process by path and mtime."""
    key, mtime = str(path), path.stat().st_mtime
    hit = _CACHE.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    out: dict[str, str] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue  # a torn final line from a kill mid-append: that item is not done
            if (
                isinstance(row, dict)
                and isinstance(row.get("item_id"), str)
                and isinstance(row.get("text"), str)
            ):
                out[row["item_id"]] = row["text"]
    _CACHE[key] = (mtime, out)
    return out


def _runs_named(name: str) -> list[Path]:
    """Every run directory with this name under the project's runs trees (data/runs*, and EVAL_RUNS_DIR)."""
    if not _NAMES:
        roots = {*sorted(p for p in _common.DATA.glob("runs*") if p.is_dir()), _common.RUNS}
        for root in roots:
            if not root.is_dir():
                continue
            for depth in ("*", "*/*", "*/*/*"):
                for d in root.glob(depth):
                    if d.is_dir() and ((d / "metrics.json").is_file() or (d / FILE).is_file()):
                        _NAMES.setdefault(d.name, []).append(d)
    return _NAMES.get(name, [])


def _derived_from(d: Path) -> str | None:
    """The run a derived run names in `derived.from`, None for a measured run (or an unreadable record)."""
    m = d / "metrics.json"
    try:
        frm = (
            (json.loads(m.read_text(encoding="utf-8")).get("derived") or {}).get("from")
            if m.is_file()
            else None
        )
    except ValueError:
        return None
    return str(frm) if frm else None


def _from_dir(d: Path) -> Path | None:
    """The source's exact directory a derived run recorded (`derived.from_dir`, under the data directory), if any."""
    m = d / "metrics.json"
    try:
        rel = (
            (json.loads(m.read_text(encoding="utf-8")).get("derived") or {}).get("from_dir")
            if m.is_file()
            else None
        )
    except ValueError:
        return None
    return _common.DATA / rel if rel else None


def source(run_dir: Path) -> Path | None:
    """The run directory whose outputs.jsonl holds this run's outputs: its own, or (a derived run) its source's,
    followed as far as it goes; None when there is none."""
    seen: set[Path] = set()
    d = Path(run_dir)
    while d not in seen:
        seen.add(d)
        if (d / FILE).is_file():
            return d
        frm = _derived_from(d)
        if not frm:
            return None
        exact = _from_dir(d)
        if exact is not None:
            if exact.resolve() == d.resolve():
                return None
            d = exact
            continue
        cands = [c for c in _runs_named(Path(str(frm)).name) if c.resolve() != d.resolve()]
        with_file = [c for c in cands if (c / FILE).is_file()]
        # The measured run first (no `derived.from` of its own), never a derived run of the same name that kept its own
        # (different) outputs; then the one directly under data/runs; then by path.
        pick = sorted(
            with_file, key=lambda c: (_derived_from(c) is not None, c.parent != _common.DATA / "runs", str(c))
        )
        pick = pick or cands
        if not pick:
            return None
        d = pick[0]
    return None


def outputs(run_dir: Path) -> dict[str, str]:
    """{item_id: text} of a run (its source's for a derived run); {} when it has none."""
    src = source(run_dir)
    return dict(_read(src / FILE)) if src else {}


def output(run_dir: Path, item_id: str) -> str | None:
    """One item's output, or None when the run has none for it."""
    src = source(run_dir)
    return _read(src / FILE).get(item_id) if src else None


def old_layout(run_dir: Path) -> bool:
    """Whether a run is still in the layout before 0.8.0 (an `outputs/` folder of <item>.txt): `evh run-migrate` moves it."""
    return (Path(run_dir) / "outputs").is_dir()


def has_outputs(run_dir: Path) -> bool:
    """Whether the run (or its source) has an outputs file."""
    return source(run_dir) is not None


def signature(run_dir: Path) -> str:
    """V5's digest of what a run wrote: each output as `<item_id>.txt` and its bytes, by item id (the value the
    per-item files gave). Runs without outputs share "<no-outputs>": what they wrote cannot tell them apart."""
    outs = outputs(run_dir)
    if not outs:
        return "<no-outputs>"
    h = hashlib.sha256()
    for item in sorted(outs, key=lambda i: f"{i}.txt"):
        h.update(f"{item}.txt".encode() + b"\0" + outs[item].encode("utf-8") + b"\x1e")
    return h.hexdigest()


class Writer:
    """Appends a run's outputs as they are produced; each line is flushed to disk before the next item."""

    def __init__(self, run_dir: Path) -> None:
        self.path = Path(run_dir) / FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, item_id: str, text: str) -> None:
        """One item's output, appended and synced."""
        line = json.dumps({"item_id": item_id, "text": text, "sha256": sha256(text)}, ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())


def writer(run_dir: Path) -> Writer:
    """The run's appending writer."""
    return Writer(run_dir)


def write_all(run_dir: Path, texts: dict[str, str], order: Iterable[str]) -> None:
    """The run's whole outputs file at once, in `order` (the dataset's), atomically: items not in `texts` are left out."""
    lines = []
    for item in order:
        if item in texts:
            t = texts[item]
            lines.append(
                json.dumps({"item_id": item, "text": t, "sha256": sha256(t)}, ensure_ascii=False) + "\n"
            )
    path = Path(run_dir) / FILE
    _common.write_text_atomic(path, "".join(lines))
    _CACHE.pop(str(path), None)


def finish(run_dir: Path, texts: dict[str, str], order: Iterable[str]) -> None:
    """A completed run: its outputs in dataset order, the row checkpoint gone (predictions.jsonl has the rows)."""
    write_all(run_dir, texts, order)
    (Path(run_dir) / ROWS).unlink(missing_ok=True)


def count(run_dir: Path) -> int:
    """How many outputs a run has written so far."""
    p = Path(run_dir) / FILE
    return len(_read(p)) if p.is_file() else 0


def lines(run_dir: Path) -> list[dict[str, Any]]:
    """The outputs file's rows as written (item_id, text, sha256), for a release or a check that needs the sha256."""
    p = Path(run_dir) / FILE
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out
