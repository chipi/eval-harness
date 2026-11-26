"""The folder source: every file of a local folder is an item (what `dataset-create --source-dir` reads in place).

    evh dataset-create --dataset-id D --source folder --query '{"path": "raw/tickets", "glob": "*.txt"}'

Query: `path` (required), `glob` (default `*`), `recursive` (default false), `exclude` (a list of globs, default none:
files they match are not items, each read against the path under the folder as `glob` is, as `--exclude` does for
`--source-dir`). A README and dotfiles are skipped, as `--source-dir` skips them. The files are copied into the dataset's items folder; the item id is the path without its
suffix.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

SKIPPED = {"readme.md", "readme.txt", "readme"}


class Source:
    """Items from a local folder."""

    def __init__(self, options: dict) -> None:
        self.options = options

    def _root(self, query: dict) -> Path:
        if not query.get("path"):
            raise ValueError("the folder source needs a path in its query")
        root = Path(query["path"])
        if not root.is_dir():
            raise ValueError(f"no folder {root}")
        return root

    def describe(self, query: dict) -> dict:
        """The folder, as a source block: nothing else is known about it."""
        return {"source": {"provider": "folder", "ref": str(query.get("path"))}}

    def items(self, query: dict) -> Iterator[dict]:
        """Each file under the folder, in name order."""
        root = self._root(query)
        walk = root.rglob if query.get("recursive") else root.glob
        patterns = query.get("exclude") or []
        if not isinstance(patterns, list) or not all(isinstance(g, str) for g in patterns):
            raise ValueError("the folder source's exclude is a list of globs")
        # the same walk as the glob, so an exclude reads a path under the folder exactly as the glob does
        excluded = {p for pattern in patterns for p in walk(pattern)}
        for p in sorted(walk(query.get("glob") or "*")):
            if p in excluded:
                continue
            if p.is_file() and not p.name.startswith(".") and p.name.lower() not in SKIPPED:
                yield {"item_id": p.relative_to(root).as_posix().rsplit(".", 1)[0], "file": str(p)}
