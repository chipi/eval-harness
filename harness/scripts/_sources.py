"""Dataset sources (PLAN_0.8.0 E5): where a dataset's items are read from, one interface for every place.

A source is a class `Source(options)` with
  - `describe(query) -> dict`: what it says about the dataset: `source` (the E1 block, at least `provider`), and when
    it knows them `licence`, `description`, `card` (E4 keys) and `features` ({name: type}, for E8);
  - `items(query) -> Iterator[dict]`: one per item: `item_id` and its bytes as one of `text` (written to the items
    folder), `file` (a path, copied there) or `source_url` (fetched by materialize; `source_sha256` pins it), with
    `row` (its place at the source, for `source.item_url`) and `fields` when it has them;
  - optionally `publish(record, items_dir, query)`: put a dataset back where it came from (P).
`evh dataset-create --source NAME --query JSON` reads one; `--source-dir` and `--manifest` stay its shortcuts for the
two built-in sources, `folder` and `manifest`.

Where a source comes from, by name, as the capture importers do:
  - a built-in one, `evaluation_harness/sources/<NAME>.py`;
  - the project's own: <data>/dataset_sources/<NAME>.py, class `Source`;
  - a path: path/to/file.py:Class.
"""

from __future__ import annotations

import hashlib
import importlib
import re
from pathlib import Path

from evaluation_harness._common import CODE, DATA, die, load_module

NAME = re.compile(r"[a-z0-9][a-z0-9_]*")


def builtin_names() -> list[str]:
    """The sources that come with the harness."""
    return sorted(p.stem for p in (CODE / "sources").glob("*.py") if not p.stem.startswith("_"))


def resolve(name: str) -> tuple[type, Path]:
    """(the source class, the file it is defined in) for `--source NAME`."""
    if name in builtin_names():
        mod = importlib.import_module(f"evaluation_harness.sources.{name}")
        return mod.Source, Path(mod.__file__ or "")
    if ":" in name:
        file, _, cls_name = name.rpartition(":")
        path = Path(file).expanduser()
        if not path.is_absolute():
            here, project = (Path.cwd() / path).resolve(), (DATA.parent / path).resolve()
            path = here if here.is_file() or not project.is_file() else project
    else:
        if not NAME.fullmatch(name):
            die(
                f"--source {name!r}: lowercase letters, digits and _, or path/to/source.py:Class",
                "bad-argument",
            )
        path, cls_name = DATA / "dataset_sources" / f"{name}.py", "Source"
        if not path.is_file():
            die(
                f"--source {name}: not a built-in source ({', '.join(builtin_names())}), and no {path} with a "
                "class Source; or name a file: path/to/source.py:Class",
                "not-found",
            )
    if not path.is_file():
        die(f"--source {name}: no file {path}", "not-found")
    mod = load_module(path, f"evh_source_{hashlib.sha256(str(path).encode()).hexdigest()[:12]}")
    cls = getattr(mod, cls_name, None)
    if cls is None or not all(callable(getattr(cls, m, None)) for m in ("describe", "items")):
        die(
            f"--source {name}: {path} has no class {cls_name} with describe(query) and items(query)",
            "invalid-file",
        )
    return cls, path
