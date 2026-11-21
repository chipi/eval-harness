"""A project's data, browsed and its settings managed (PRD-016, UXS-004): what the data page and `evh data-*` call.

Every path is relative to data/ and read and written through `_store`, so the same calls work whether the project
keeps its data as files or in its database (RFC-025). A **setting** (a system, a goal, a fieldset, a judge
scorer, a model record, a failure-mode list, the validate policy) is what a person decides: it can be created,
changed and deleted, each change checked first. A **run** can be deleted whole. Everything else is what the harness
wrote, and is shown, never changed; Python is never edited here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

from evaluation_harness import _common, _outputs, _store
from evaluation_harness.model import runs as model_runs

#: The settings, by folder: (what one is, its schema, the key that is its id, whether that id must be the file name).
#: Each is found by its id (validate checks systems, goals, scorers, models and failure-mode lists; a fieldset is read
#: as <id>.yaml).
SETTINGS: dict[str, tuple[str, str, str, bool]] = {
    "systems": ("system", "system.schema.json", "system_id", True),
    "goals": ("goal", "goal.schema.json", "goal_id", True),
    "fields": ("fieldset", "fieldset.schema.json", "fieldset_id", True),
    "scorers": ("judge scorer", "scorer.schema.json", "scorer_id", True),
    "models": ("model record", "model.schema.json", "model_id", True),
    "failure-modes": ("failure-mode list", "failure-modes.schema.json", "failure_modes_id", True),
}
#: The validate policy: a setting of its own, JSON (schemas/validate.schema.json).
POLICY = "validate.json"
#: The goal policy: goals/policy.yaml is not a goal, but the date from which every run must name one.
GOAL_POLICY = "goals/policy.yaml"
#: What a folder of harness-written data is, and the command that writes it.
WRITERS: dict[str, tuple[str, str]] = {
    "datasets": ("datasets", "the dataset-* commands (dataset-create, dataset-extend, dataset-split, ...)"),
    "sources": ("dataset sources", "the harness's commands and the examples' fetch.py"),
    "materialized": ("materialized items", "evh dataset-materialize"),
    "references": ("reference sets", "evh reference-promote"),
    "labels": ("label sets", "the label-* commands and evh sheet-import"),
    "judging-sets": ("judging sets", "evh judge-score"),
    "judge-verdicts": ("judge verdicts", "evh judge-score"),
    "judge-summaries": ("judge summaries", "evh judge-score"),
    "judge-validation": (
        "judge validations",
        "a validation of the judges: evh run of each judge against the people's labels (the news-summary judge's own scripts stay in the harness repository)",
    ),
    "captures": ("captures", "evh capture"),
    "profiles": ("dataset profiles", "evh dataset-profile"),
    "rounds": ("rounds", "the round-* commands (round-open, round-retire, round-close)"),
    "baselines": ("baselines", "evh run-promote, evh baseline-rollback"),
    "tags": ("tag sets", "evh sheet-import"),
    "corpora": ("corpora", "the example's fetch.py"),
}
PAGE = 500
LIMIT = 200


class Refused(Exception):
    """What the page and the commands refuse, with the words both say; `kind` is the refusal's (`_common.REFUSALS`)."""

    def __init__(self, message: str, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


def refuse(exc: Refused) -> NoReturn:
    """The commands' exit on a refusal: `die` with its kind, each kind named as it is (test_refusal_kinds)."""
    from evaluation_harness._common import die  # noqa: PLC0415

    msg = str(exc)
    if exc.kind == "not-found":
        die(msg, "not-found")
    if exc.kind == "not-allowed":
        die(msg, "not-allowed")
    if exc.kind == "would-overwrite":
        die(msg, "would-overwrite")
    if exc.kind == "invalid-file":
        die(msg, "invalid-file")
    if exc.kind == "failed":
        die(msg, "failed")
    die(msg, "bad-argument")


def _data() -> Path:
    return _common.DATA


def resolve(rel: str) -> tuple[str, Path]:
    """A path relative to data/ (posix), and the path it names; one that leaves data/ is refused."""
    text = (rel or "").strip().strip("/")
    pp = PurePosixPath(text) if text else PurePosixPath(".")
    if pp.is_absolute() or ".." in pp.parts or "\\" in text:
        raise Refused("That path is outside the project's data.", "not-allowed")
    norm = "" if str(pp) == "." else str(pp)
    return norm, _data() / norm if norm else _data()


def is_file(rel: str) -> bool:
    """Whether the path names a file of the project's data."""
    norm, f = resolve(rel)
    return _store.is_file(f) or _held_text(norm) is not None


def in_tables() -> dict[str, list[str]]:
    """{folder under data/: the files it holds as rows of the sqlite store's tables}: a run's outputs, a score's rows
    and a checkpoint, each named as the file `data-migrate --to files` writes from them. {} on the files store, where
    they are files; so a folder lists, counts and shows the same files in either store."""
    st = _outputs.store()
    if not isinstance(st, _outputs.SqliteStore):
        return {}
    held: dict[str, list[str]] = {}
    for key in st.runs():
        held.setdefault(key, []).append(_outputs.FILE)
    for key, partial in st.row_runs():
        held.setdefault(key, []).append(_outputs.ROWS if partial else _outputs.PREDICTIONS)
    return held


def _held_text(norm: str) -> str | None:
    """The text of a file the sqlite store holds as table rows (in_tables), byte for byte what `data-migrate --to files`
    writes; None when the path is no such file."""
    folder, _, name = norm.rpartition("/")
    if not folder or name not in (_outputs.FILE, _outputs.PREDICTIONS, _outputs.ROWS):
        return None
    st = _outputs.store()
    if st.name != "sqlite":
        return None
    d = _data() / folder
    if name == _outputs.FILE:
        lines = st.lines(d)
        return "".join(_outputs._line(o["item_id"], o["text"]) + "\n" for o in lines) if lines else None
    if name == _outputs.PREDICTIONS:
        return st.stored_text(d, errors="replace") if st.has_rows(d) else None
    return st.rows_text(d, partial=True, errors="replace")


def _held_mtime(d: Path) -> float | None:
    """When a held file was written, as near as the store knows: the database keeps no time for rows, so the time of
    the file written beside them (a score's score.json, a run's run.json), else of the folder's newest file."""
    for name in ("score.json", "run.json"):
        if _store.is_file(d / name):
            return _store.stat(d / name).st_mtime
    times = (
        [_store.stat(p).st_mtime for p in _store.iterdir(d) if _store.is_file(p)] if _store.is_dir(d) else []
    )
    return max(times) if times else None


def kind_of(rel: str) -> str:
    """`setting`, `run`, `run-file` (a file of a run), `code`, or `data` (harness-written)."""
    if rel.endswith(".py"):
        return "code"
    parts = rel.split("/")
    if rel in (POLICY, GOAL_POLICY) or (
        len(parts) == 2 and parts[0] in SETTINGS and parts[1].endswith((".yaml", ".yml"))
    ):
        return "setting"
    if parts[0] == "runs":
        d = _data() / rel
        if len(parts) == 2 and _store.is_dir(d) and _store.is_file(d / "run.json"):
            return "run"
        if len(parts) >= 3 and (_store.is_file(d) or _held_text(rel) is not None):
            return "run-file"
    return "data"


def writer_of(rel: str) -> str:
    """The command that writes a harness-written file."""
    top = rel.split("/")[0]
    if top == "runs":
        return "evh run and the commands that score runs (rescore, judge-score, sheet-import, import-run)"
    return WRITERS.get(top, ("", "the harness's commands"))[1]


def _files_under(d: Path, held: dict[str, list[str]] | None = None) -> int:
    """The files under a folder, the ones the sqlite store holds as table rows counted too (in_tables)."""
    held = in_tables() if held is None else held
    rel = _store.rel(d) or ""
    in_rows = sum(len(v) for k, v in held.items() if not rel or k == rel or k.startswith(rel + "/"))
    return sum(1 for f in _store.rglob(d, "*") if _store.is_file(f)) + in_rows


def overview() -> dict[str, Any]:
    """The store, the settings folders with their counts, and every other folder of data/ with its count."""
    data = _data()
    db = data / _store.DB
    store = _common.store()
    tops = sorted(p.name for p in _store.iterdir(data)) if _store.is_dir(data) else []
    held = in_tables()
    settings = []
    for folder, (word, _schema, _key, _named) in SETTINGS.items():
        d = data / folder
        settings.append(
            {"folder": folder, "kind": word, "files": _files_under(d, held) if _store.is_dir(d) else 0}
        )
    settings.append(
        {"folder": POLICY, "kind": "validate policy", "files": int(_store.is_file(data / POLICY))}
    )
    other = []
    for name in tops:
        if name in SETTINGS or name == POLICY or name.startswith(_store.DB) or not _store.is_dir(data / name):
            continue
        word = WRITERS.get(name, (name, ""))[0]
        other.append({"folder": name, "kind": word, "files": _files_under(data / name, held)})
    return {
        "store": store,
        "database": str(db.relative_to(_common.ROOT)) if store == "sqlite" else None,
        "database_bytes": _store.stat(db).st_size if store == "sqlite" and _store.is_file(db) else None,
        "settings": settings,
        "data": other,
    }


def _run_row(d: Path) -> dict[str, Any]:
    m = model_runs.run(d) or {}
    return {
        "dataset": m.get("dataset_id"),
        "items": m.get("n_items"),
        "made": _iso_when(m.get("created_at") or m.get("started_at")),
        "finished": bool(model_runs.scores_of(d)),
    }


def listing(rel: str, offset: int = 0) -> dict[str, Any]:
    """A folder's entries: sub-folders (with their file counts, runs with their record), then files; paged."""
    norm, d = resolve(rel)
    if (
        not _store.is_dir(d) and norm not in SETTINGS
    ):  # a settings folder not made yet is empty: its first file makes it
        raise Refused(f"No folder {norm or 'data/'} in the project's data.", "not-found")
    held = in_tables()
    entries = []
    files = []
    for p in sorted(
        _store.iterdir(d) if _store.is_dir(d) else [], key=lambda q: (not _store.is_dir(q), q.name)
    ):
        child = f"{norm}/{p.name}" if norm else p.name
        if _store.is_dir(p):
            k = kind_of(child)
            row: dict[str, Any] = {"name": p.name, "path": child, "type": "run" if k == "run" else "folder"}
            row.update(_run_row(p) if k == "run" else {"files": _files_under(p, held)})
            entries.append(row)
        elif not (not norm and p.name.startswith(_store.DB)):
            st = _store.stat(p)
            files.append(
                {
                    "name": p.name,
                    "path": child,
                    "type": "file",
                    "kind": kind_of(child),
                    "size": st.st_size,
                    "modified": _when(st.st_mtime),
                }
            )
    for name in held.get(norm, []):
        text = _held_text(f"{norm}/{name}")
        if text is not None and name not in {f["name"] for f in files}:
            when = _held_mtime(d)
            files.append(
                {
                    "name": name,
                    "path": f"{norm}/{name}",
                    "type": "file",
                    "kind": kind_of(f"{norm}/{name}"),
                    "size": len(text.encode("utf-8")),
                    "modified": _when(when) if when is not None else None,
                }
            )
    entries += sorted(files, key=lambda f: f["name"])
    folder = norm.split("/")[0] if norm else ""
    return {
        "path": norm,
        "settings_folder": folder if norm in SETTINGS else None,
        "kind": SETTINGS[norm][0] if norm in SETTINGS else None,
        # the goal policy is made from the goals folder, when the project has none
        "also_new": GOAL_POLICY if norm == "goals" and not _store.is_file(_data() / GOAL_POLICY) else None,
        "total": len(entries),
        "offset": offset,
        "entries": entries[offset : offset + PAGE],
    }


def _iso_when(iso: Any) -> str | None:
    """A run record's ISO time (`created_at`, or `started_at` of a pass not finished) as the page shows times."""
    try:
        from datetime import datetime  # noqa: PLC0415

        return _when(datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _when(ts: float) -> str:
    from datetime import datetime, timezone  # noqa: PLC0415

    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def runs_of_system(system_id: str) -> int:
    """How many runs were made with this system (their records name it)."""
    return sum(1 for rid in model_runs.run_ids() if (model_runs.run(rid) or {}).get("system_id") == system_id)


def show(rel: str) -> dict[str, Any]:
    """A file: its text (or that it is binary), size, date, sha256, kind, and who writes it."""
    norm, f = resolve(rel)
    held = None if _store.is_file(f) else _held_text(norm)
    if not _store.is_file(f) and held is None:
        if _store.is_dir(f):
            raise Refused(f"{norm} is a folder: list it instead.", "bad-argument")
        raise Refused(f"No file {norm} in the project's data.", "not-found")
    raw = _store.read_bytes(f) if held is None else held.encode("utf-8")
    when = _store.stat(f).st_mtime if held is None else _held_mtime(f.parent)
    try:
        text: str | None = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    k = kind_of(norm)
    out: dict[str, Any] = {
        "path": norm,
        "kind": k,
        "size": len(raw),
        "modified": _when(when) if when is not None else None,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "text": text,
        "editable": k == "setting",
    }
    if k != "setting":
        out["written_by"] = "never edited here (code)" if k == "code" else writer_of(norm)
    if k == "run-file":
        out["run"] = "/".join(norm.split("/")[:2])
    if k == "setting":
        out["setting_kind"] = (
            "validate policy"
            if norm == POLICY
            else "goal policy"
            if norm == GOAL_POLICY
            else SETTINGS[norm.split("/", 1)[0]][0]
        )
    if k == "setting" and norm.startswith("systems/") and text is not None:
        import yaml  # noqa: PLC0415

        try:
            cid = (yaml.safe_load(text) or {}).get("system_id")
        except (yaml.YAMLError, AttributeError):
            cid = None
        out["runs_made"] = runs_of_system(str(cid)) if cid else 0
    return out


def refuse_used_scorer(norm: str, what: str) -> None:
    """Refuse to change or delete (`what`) the judge scorer at `norm` when it made judged scores: every one records the
    scorer as it was, so a new version is a new scorer (a new id, `supersedes`). Anything else passes."""
    parts = norm.split("/")
    if len(parts) != 2 or parts[0] != "scorers" or not parts[1].endswith(".yaml"):
        return
    from evaluation_harness.model import scorers  # noqa: PLC0415

    if why := scorers.frozen(parts[1][: -len(".yaml")]):
        raise Refused(f"{norm} is not {what}: {why}", "not-allowed")


def check(rel: str, text: str) -> list[str]:
    """What is wrong with this text as the setting at `rel`; [] when it may be saved. The form's own check
    (`_settings_form.problems`) once the text parses."""
    from evaluation_harness import _settings_form  # noqa: PLC0415

    norm, _f = resolve(rel)
    if kind_of(norm) != "setting":
        raise Refused(_not_edited(norm), "not-allowed")
    if norm == POLICY:
        try:
            doc = json.loads(text)
        except ValueError as exc:
            return [f"not JSON: {exc}"]
    else:
        import yaml  # noqa: PLC0415

        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
            return [f"not YAML{where}: {getattr(exc, 'problem', None) or exc}"]
        if doc is None and norm == GOAL_POLICY:
            doc = {}
    if not isinstance(doc, dict):
        return ["a setting is a mapping of keys (key: value lines)"]
    if norm.startswith("scorers/") and _store.is_file(_f):
        from evaluation_harness.model import scorers  # noqa: PLC0415

        if scorers.content_hash(doc) != scorers.current_sha256(Path(norm).stem):
            refuse_used_scorer(norm, "changed")
    return [
        f"{'.'.join(map(str, p['path'])) or '(top)'}: {p['message']}"
        for p in _settings_form.problems(norm, _settings_form.plain(doc))
    ]


def checked(rel: str) -> str:
    """What the check of this setting checks, as the page and `data-put --check` say it on a pass."""
    norm, _f = resolve(rel)
    if norm == POLICY:
        return "it matches validate.schema.json"
    if norm == GOAL_POLICY:
        return "it matches goal-policy.schema.json"
    folder = norm.split("/", 1)[0]
    _word, schema_name, key, named = SETTINGS[folder]
    return f"it parses, matches {schema_name}" + (f", and its {key} is its file name" if named else "")


def _not_edited(norm: str) -> str:
    k = kind_of(norm)
    if k == "code":
        return f"{norm} is code: code is never edited here."
    return f"{norm} is written by {writer_of(norm)}; it is not edited here."


def put(rel: str, text: str, new: bool = False) -> dict[str, Any]:
    """Save a setting: checked first, nothing written on a problem; `new` refuses a name already taken. Under the
    settings' one lock from the check of the name to the write (two new ones of one name: the second refused)."""
    from evaluation_harness import _settings_form  # noqa: PLC0415

    norm, f = resolve(rel)
    problems = check(norm, text)
    with _settings_form.WRITES:
        if new and _store.is_file(f):
            raise Refused(f"{norm} exists: open it to edit it.", "would-overwrite")
        if problems:
            raise Refused(f"{norm} not saved:\n  " + "\n  ".join(problems), "invalid-file")
        _settings_form.guarded_write(norm, f, text)
    return show(norm)


def _run_counts(d: Path) -> tuple[int, int]:
    """A run's outputs, and the rows of all its scores."""
    rows = sum(len(_outputs.rows(sd, errors="replace", meta=False) or ()) for sd in model_runs.scores_of(d))
    return len(_outputs.lines(d)), rows


def deletable(rel: str) -> str:
    """The kind (`setting` or `run`) of something `remove` may delete; refuses anything else, as `remove` would,
    touching nothing."""
    norm, f = resolve(rel)
    k = kind_of(norm)
    if k == "setting" and _store.is_file(f):
        refuse_used_scorer(norm, "deleted")
        return k
    if k == "run":
        return k
    if not _store.exists(f):
        raise Refused(f"No file {norm} in the project's data.", "not-found")
    if k == "run-file":
        raise Refused(f"{norm} is part of a run: delete the run instead.", "not-allowed")
    raise Refused(_not_edited(norm), "not-allowed")


def remove(rel: str) -> dict[str, Any]:
    """Delete a setting, or a whole run (its files, outputs and rows); anything else is refused. Never while a save is
    checking the project (one write at a time, `_settings_form.WRITES`)."""
    from evaluation_harness import _settings_form  # noqa: PLC0415

    with _settings_form.WRITES:
        try:
            return _remove(rel)
        finally:
            _settings_form.forget_baseline()


def _remove(rel: str) -> dict[str, Any]:
    norm, f = resolve(rel)
    k = kind_of(norm)
    if k == "setting":
        if not _store.is_file(f):
            raise Refused(f"No file {norm} in the project's data.", "not-found")
        refuse_used_scorer(norm, "deleted")
        _store.unlink(f)
        return {"deleted": norm, "kind": "setting"}
    if k == "run":
        outs, rows = _run_counts(f)
        files = _files_under(f)
        _store.rmtree(f)
        return {"deleted": norm, "kind": "run", "files": files, "outputs": outs, "rows": rows}
    if not _store.exists(f):
        raise Refused(f"No file {norm} in the project's data.", "not-found")
    raise Refused(_not_edited(norm) if k != "run-file" else f"{norm} is part of a run: delete the run instead.",
                  "not-allowed")  # fmt: skip


def run_summary(rel: str) -> dict[str, Any]:
    """What deleting a run takes with it: its files, outputs and rows."""
    norm, d = resolve(rel)
    if kind_of(norm) != "run":
        raise Refused(f"{norm} is not a run.", "bad-argument")
    outs, rows = _run_counts(d)
    return {"path": norm, "files": _files_under(d), "outputs": outs, "rows": rows}


def search(text: str) -> dict[str, Any]:
    """Every file under data/ whose path holds `text` (case ignored), the first LIMIT of them."""
    q = (text or "").strip().lower()
    if not q:
        return {"query": "", "total": 0, "paths": []}
    data = _data()
    on_disk = (
        str(p.relative_to(data))
        for p in _store.rglob(data, "*")
        if _store.is_file(p) and not p.name.startswith(_store.DB)
    )
    held = (
        f"{folder}/{name}" for folder, names in in_tables().items() for name in names
    )  # as a folder lists them
    hits = sorted({rel for rel in (*on_disk, *held) if q in rel.lower()})
    return {"query": text, "total": len(hits), "paths": hits[:LIMIT]}
