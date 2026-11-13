"""An entity of the model (RFC-032): where its records live, its schema, the ids it links to, and the four things done
with a record: read, check, save (an edit: only changed values written, a file keeping its comments), and its history.

An edit is checked against the entity's schema and its links (every id it names exists) and written at once, under the
entity's lock; the project's full check (`evh validate`) is a job, not part of a save (owner, 2026-11-13). Every save
records who made it and when, with the record as it was, so a change can be seen and undone.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _format, _store

ID = re.compile(r"[a-z0-9][a-z0-9_.-]*")
#: How many saves of one record its history keeps.
HISTORY = 50


class Problem(Exception):
    """A request the model refuses: its message, the refusal kind (`_common.REFUSALS`) and, for a record that does not
    check, each problem with the field it is at."""

    def __init__(self, message: str, kind: str, problems: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.problems = problems or []


@dataclass(frozen=True)
class Entity:
    """One kind of record: `folder` under data/ (its files `<id><suffix>`), `id_field` naming it inside, `links`
    checking the ids it names."""

    name: str
    plural: str
    folder: str
    id_field: str
    suffix: str = ".yaml"
    skip: frozenset[str] = frozenset()
    links: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None

    def base(self) -> Path:
        """Where its records are: the goals' folder may be moved (EVAL_GOALS_DIR), the others are data/<folder>."""
        return _common.GOALS if self.folder == "goals" else _common.DATA / self.folder

    def path(self, rid: str) -> Path:
        """The record's file; an id that is not one is refused before any path is made of it."""
        if not isinstance(rid, str) or not ID.fullmatch(rid):
            raise Problem(
                f"{rid!r} is not a {self.name} id (lowercase letters, digits, . _ -)", "bad-argument"
            )
        return self.base() / f"{rid}{self.suffix}"

    def norm(self, rid: str) -> str:
        """The record's place as the settings code names it (its schema, its key order)."""
        return f"{self.folder}/{rid}{self.suffix}"

    def ids(self) -> list[str]:
        """Every record's id, sorted."""
        _format.require()
        base = self.base()
        if not _store.is_dir(base):
            return []
        return sorted(
            f.name[: -len(self.suffix)]
            for f in _store.glob(base, f"*{self.suffix}")
            if f.name not in self.skip and ID.fullmatch(f.name[: -len(self.suffix)])
        )

    def get(self, rid: str) -> dict[str, Any]:
        """The record as stored (dates as ISO text); a missing one is refused, naming those there are."""
        _format.require()
        f = self.path(rid)
        if not _store.is_file(f):
            have = self.ids()
            raise Problem(
                f"no {self.name} {rid!r}"
                + (f": one of {', '.join(have)}" if have else f": there are no {self.plural}"),
                "not-found",
            )
        import yaml  # noqa: PLC0415
        from evaluation_harness import _settings_form  # noqa: PLC0415

        try:
            doc = yaml.safe_load(_store.read_text(f, encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise Problem(f"{self.norm(rid)}: not YAML ({exc})", "invalid-file") from None
        if not isinstance(doc, dict):
            raise Problem(f"{self.norm(rid)}: not a mapping of keys", "invalid-file")
        return dict(_settings_form.plain(doc))

    def all(self) -> list[dict[str, Any]]:
        """Every record."""
        return [self.get(i) for i in self.ids()]

    def problems(self, rid: str, record: Any) -> list[dict[str, Any]]:
        """What is wrong with `record` as the record `rid`: its schema, its id, its links; [] when it may be saved."""
        from evaluation_harness import _settings_form  # noqa: PLC0415

        out = list(_settings_form.problems(self.norm(rid), record))
        if not out and self.links:
            out += self.links(record)
        return out

    def save(self, rid: str, record: dict[str, Any], by: str, new: bool = False) -> dict[str, Any]:
        """Check and write the record (only the lines a change touches move, its comments kept), under its lock; record
        who and when, with the record as it was. `new` refuses an id that is taken. Nothing is written when nothing
        changed."""
        from evaluation_harness import _jobs, _settings_form  # noqa: PLC0415

        _format.require()
        f = self.path(rid)
        try:
            with _jobs.holding([(f"{self.name}:{rid}", True)], f"{self.name}-save"):
                exists = _store.is_file(f)
                if new and exists:
                    raise Problem(
                        f"{self.name} {rid!r} exists: change it with its own command", "would-overwrite"
                    )
                found = self.problems(rid, record)
                if found:
                    raise Problem(
                        f"{self.norm(rid)} not saved:\n  "
                        + "\n  ".join(
                            f"{'.'.join(map(str, p['path'])) or '(top)'}: {p['message']}" for p in found
                        ),
                        "invalid-file",
                        found,
                    )
                before = _store.read_text(f, encoding="utf-8") if exists else None
                old = self.get(rid) if exists else None
                if old == record:
                    return {"id": rid, "changed": False, "record": record}
                _store.mkdir(f.parent, parents=True, exist_ok=True)
                _common.write_text_atomic(f, _settings_form.text_for(self.norm(rid), record, before))
                self._remember(rid, old, by)
        except _jobs.Busy as exc:
            raise Problem(
                f"{self.name} {rid!r} is being written by {exc.holder or 'a job'}: try again when it ends",
                "not-allowed",
            ) from None
        return {"id": rid, "changed": True, "record": record}

    def patch(self, rid: str, sets: list[tuple[str, Any]], unsets: list[str], by: str) -> dict[str, Any]:
        """The record with each dotted key set and each unset key removed, saved."""
        from evaluation_harness import _data_page, _settings_form  # noqa: PLC0415

        try:
            changed = _settings_form.set_values(self.get(rid), sets, unsets)
        except _data_page.Refused as exc:
            raise Problem(str(exc), "bad-argument") from None
        return self.save(rid, changed, by)

    def _history_file(self, rid: str) -> Path:
        return _common.DATA / "history" / self.plural / f"{rid}.jsonl"

    def _remember(self, rid: str, old: dict[str, Any] | None, by: str) -> None:
        f = self._history_file(rid)
        lines = _store.read_text(f, encoding="utf-8").splitlines() if _store.is_file(f) else []
        when = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines.append(json.dumps({"at": when, "by": by, "was": old}, ensure_ascii=False, sort_keys=True))
        _store.mkdir(f.parent, parents=True, exist_ok=True)
        _common.write_text_atomic(f, "\n".join(lines[-HISTORY:]) + "\n")

    def history(self, rid: str) -> list[dict[str, Any]]:
        """The record's saves, newest first: when, by whom, and what it was before (None: it was made then)."""
        self.path(rid)
        f = self._history_file(rid)
        if not _store.is_file(f):
            return []
        return [
            json.loads(x) for x in reversed(_store.read_text(f, encoding="utf-8").splitlines()) if x.strip()
        ]
