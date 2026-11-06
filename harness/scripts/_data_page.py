"""A project's data, browsed and its settings managed (PRD-016, UXS-004): what the data page and `evh data-*` call.

Every path is relative to data/ and read and written through `_store`, so the same calls work whether the project
keeps its data as files or in its database (RFC-025). A **setting** (an arm config, a goal, a fieldset, a judge
scorer, a model record, a failure-mode list, the validate policy) is what a person decides: it can be created,
changed and deleted, each change checked first. A **run** can be deleted whole. Everything else is what the harness
wrote, and is shown, never changed; Python is never edited here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from evaluation_harness import _common, _outputs, _store

#: The settings, by folder: (what one is, its schema, the key that is its id, whether that id must be the file name).
#: An arm config's config_id is not its file name (data/configs/tickets_lead1.yaml holds tickets_lead1_v1); the others
#: are found by it (validate checks goals, scorers, models and failure-mode lists; a fieldset is read as <id>.yaml).
SETTINGS: dict[str, tuple[str, str, str, bool]] = {
    "configs": ("arm config", "config.schema.json", "config_id", False),
    "goals": ("goal", "goal.schema.json", "goal_id", True),
    "fields": ("fieldset", "fieldset.schema.json", "fieldset_id", True),
    "scorers": ("judge scorer", "scorer.schema.json", "scorer_id", True),
    "models": ("model record", "model.schema.json", "model_id", True),
    "failure-modes": ("failure-mode list", "failure-modes.schema.json", "failure_modes_id", True),
}
#: The validate policy: a setting of its own, JSON, with no schema.
POLICY = "validate.json"
#: What a folder of harness-written data is, and the command that writes it.
WRITERS: dict[str, tuple[str, str]] = {
    "datasets": ("datasets", "the dataset-* commands (dataset-create, dataset-extend, dataset-split, ...)"),
    "sources": ("dataset sources", "the harness's commands and the examples' fetch.py"),
    "materialized": ("materialized items", "evh dataset-materialize"),
    "references": ("reference sets", "evh reference-promote"),
    "labels": ("label sets", "the label-* commands and evh sheet-import"),
    "judging-sets": ("judging sets", "evh judge-score"),
    "judge-verdicts": ("judge verdicts", "evh judge-score"),
    "judge-validation": (
        "judge validations",
        "the judge-validation tools (harness/tools/validate_judge_*.py)",
    ),
    "captures": ("captures", "evh capture"),
    "profiles": ("dataset profiles", "evh dataset-profile"),
    "rounds": ("rounds", "the round-* commands (round-open, round-retire, round-close)"),
    "baselines": ("baselines", "evh run-promote"),
    "tags": ("tag sets", "evh sheet-import"),
    "corpora": ("corpora", "the example's fetch.py"),
}
TEMPLATES: dict[str, str] = {
    "configs": "config_id: {id}\ndataset_id: \nparams:\n  provider: \n",
    "goals": ("goal_id: {id}\ntitle: \nstatement: \ndecision: \nsuccess_criteria: \ndatasets:\n  - \n"),
    "fields": "fieldset_id: {id}\nfields: []\n",
    "scorers": "scorer_id: {id}\nkind: judge\ndataset_id: \njudges: []\nprompt: \nprotocol: \n",
    "models": "model_id: {id}\nkind: llm\naliases: []\n",
    "failure-modes": "failure_modes_id: {id}\nmodes: []\n",
}
PAGE = 500
LIMIT = 200


class Refused(Exception):
    """What the page and the commands refuse, with the words both say; `kind` is the refusal's (`_common.REFUSALS`)."""

    def __init__(self, message: str, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


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
    return _store.is_file(resolve(rel)[1])


def kind_of(rel: str) -> str:
    """`setting`, `run`, `run-file` (a file of a run), `code`, or `data` (harness-written)."""
    if rel.endswith(".py"):
        return "code"
    parts = rel.split("/")
    if rel == POLICY or (len(parts) == 2 and parts[0] in SETTINGS and parts[1].endswith((".yaml", ".yml"))):
        return "setting"
    if parts[0].startswith("runs"):
        d = _data() / rel
        if _store.is_dir(d) and (_store.is_file(d / "metrics.json") or _store.is_file(d / "run.json")):
            return "run"
        if _store.is_file(d) and len(parts) >= 2:
            return "run-file"
    return "data"


def writer_of(rel: str) -> str:
    """The command that writes a harness-written file."""
    top = rel.split("/")[0]
    if top.startswith("runs"):
        return "evh run and the commands that derive runs (rescore, judge-score, sheet-import, import-run)"
    return WRITERS.get(top, ("", "the harness's commands"))[1]


def _files_under(d: Path) -> int:
    return sum(1 for f in _store.rglob(d, "*") if _store.is_file(f))


def overview() -> dict[str, Any]:
    """The store, the settings folders with their counts, and every other folder of data/ with its count."""
    data = _data()
    db = data / _store.DB
    store = _common.store()
    tops = sorted(p.name for p in _store.iterdir(data)) if _store.is_dir(data) else []
    settings = []
    for folder, (word, _schema, _key, _named) in SETTINGS.items():
        d = data / folder
        settings.append({"folder": folder, "kind": word, "files": _files_under(d) if _store.is_dir(d) else 0})
    settings.append(
        {"folder": POLICY, "kind": "validate policy", "files": int(_store.is_file(data / POLICY))}
    )
    other = []
    for name in tops:
        if name in SETTINGS or name == POLICY or name.startswith(_store.DB) or not _store.is_dir(data / name):
            continue
        word = WRITERS.get(name, ("runs" if name.startswith("runs") else name, ""))[0]
        other.append({"folder": name, "kind": word, "files": _files_under(data / name)})
    return {
        "store": store,
        "database": str(db.relative_to(_common.ROOT)) if store == "sqlite" else None,
        "database_bytes": _store.stat(db).st_size if store == "sqlite" and _store.is_file(db) else None,
        "settings": settings,
        "data": other,
    }


def _run_row(d: Path) -> dict[str, Any]:
    rec = _store.read_text(d / "metrics.json") if _store.is_file(d / "metrics.json") else None
    rec = (
        rec
        if rec is not None
        else (_store.read_text(d / "run.json") if _store.is_file(d / "run.json") else "{}")
    )
    try:
        m = json.loads(rec)
    except ValueError:
        m = {}
    return {
        "dataset": m.get("dataset_id"),
        "items": m.get("n_items"),
        "made": _iso_when(m.get("created_at") or m.get("started_at")),
        "finished": _store.is_file(d / "metrics.json"),
    }


def listing(rel: str, offset: int = 0) -> dict[str, Any]:
    """A folder's entries: sub-folders (with their file counts, runs with their record), then files; paged."""
    norm, d = resolve(rel)
    if (
        not _store.is_dir(d) and norm not in SETTINGS
    ):  # a settings folder not made yet is empty: its first file makes it
        raise Refused(f"No folder {norm or 'data/'} in the project's data.", "not-found")
    entries = []
    for p in sorted(
        _store.iterdir(d) if _store.is_dir(d) else [], key=lambda q: (not _store.is_dir(q), q.name)
    ):
        child = f"{norm}/{p.name}" if norm else p.name
        if _store.is_dir(p):
            k = kind_of(child)
            row: dict[str, Any] = {"name": p.name, "path": child, "type": "run" if k == "run" else "folder"}
            row.update(_run_row(p) if k == "run" else {"files": _files_under(p)})
            entries.append(row)
        elif not (not norm and p.name.startswith(_store.DB)):
            st = _store.stat(p)
            entries.append(
                {
                    "name": p.name,
                    "path": child,
                    "type": "file",
                    "kind": kind_of(child),
                    "size": st.st_size,
                    "modified": _when(st.st_mtime),
                }
            )
    folder = norm.split("/")[0] if norm else ""
    return {
        "path": norm,
        "settings_folder": folder if norm in SETTINGS else None,
        "kind": SETTINGS[norm][0] if norm in SETTINGS else None,
        "total": len(entries),
        "offset": offset,
        "entries": entries[offset : offset + PAGE],
    }


def _iso_when(iso: Any) -> str | None:
    """A run record's ISO time (`created_at` in metrics.json, `started_at` in run.json) as the page shows times."""
    try:
        from datetime import datetime  # noqa: PLC0415

        return _when(datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _when(ts: float) -> str:
    from datetime import datetime, timezone  # noqa: PLC0415

    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def runs_of_config(config_id: str) -> int:
    """How many runs were made with this arm config (their records name it)."""
    n = 0
    data = _data()
    for base in _store.glob(data, "runs*"):
        for m in _store.rglob(base, "metrics.json"):
            try:
                n += json.loads(_store.read_text(m)).get("config_id") == config_id
            except ValueError:
                continue
    return n


def show(rel: str) -> dict[str, Any]:
    """A file: its text (or that it is binary), size, date, sha256, kind, and who writes it."""
    norm, f = resolve(rel)
    if not _store.is_file(f):
        if _store.is_dir(f):
            raise Refused(f"{norm} is a folder: list it instead.", "bad-argument")
        raise Refused(f"No file {norm} in the project's data.", "not-found")
    raw = _store.read_bytes(f)
    try:
        text: str | None = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    k = kind_of(norm)
    out: dict[str, Any] = {
        "path": norm,
        "kind": k,
        "size": len(raw),
        "modified": _when(_store.stat(f).st_mtime),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "text": text,
        "editable": k == "setting",
    }
    if k != "setting":
        out["written_by"] = "never edited here (code)" if k == "code" else writer_of(norm)
    if k == "run-file":
        run_dir = norm.rsplit("/", 1)[0]
        out["run"] = run_dir
    if k == "setting" and norm.startswith("configs/"):
        out["runs_made"] = runs_of_config(PurePosixPath(norm).stem)
    return out


def check(rel: str, text: str) -> list[str]:
    """What is wrong with this text as the setting at `rel`; [] when it may be saved."""
    norm, _f = resolve(rel)
    if kind_of(norm) != "setting":
        raise Refused(_not_edited(norm), "not-allowed")
    if norm == POLICY:
        try:
            doc = json.loads(text)
        except ValueError as exc:
            return [f"not JSON: {exc}"]
        return [] if isinstance(doc, dict) else ["the validate policy is a JSON object"]
    import yaml  # noqa: PLC0415

    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
        return [f"not YAML{where}: {getattr(exc, 'problem', None) or exc}"]
    if not isinstance(doc, dict):
        return ["a setting is a YAML mapping (key: value lines)"]
    folder, name = norm.split("/", 1)
    _word, schema_name, key, named = SETTINGS[folder]
    problems = []
    stem = PurePosixPath(name).stem
    if named and doc.get(key) != stem:
        problems.append(f"{key} is {doc.get(key)!r}: it must be the file name, {stem!r}")
    try:
        import jsonschema  # noqa: PLC0415

        schema = json.loads(_store.read_text(_common.SCHEMAS / schema_name))
        for err in sorted(
            jsonschema.Draft202012Validator(schema).iter_errors(doc), key=lambda e: list(e.path)
        ):
            where = ".".join(str(x) for x in err.path) or "(top)"
            problems.append(f"{where}: {err.message}")
    except ImportError:  # pragma: no cover - jsonschema is a dependency
        problems.append("jsonschema is not installed: the setting cannot be checked")
    return problems


def checked(rel: str) -> str:
    """What the check of this setting checks, as the page and `data-put --check` say it on a pass."""
    norm, _f = resolve(rel)
    if norm == POLICY:
        return "it is a JSON object"
    folder = norm.split("/", 1)[0]
    _word, schema_name, key, named = SETTINGS[folder]
    return f"it parses, matches {schema_name}" + (f", and its {key} is its file name" if named else "")


def _not_edited(norm: str) -> str:
    k = kind_of(norm)
    if k == "code":
        return f"{norm} is code: code is never edited here."
    return f"{norm} is written by {writer_of(norm)}; it is not edited here."


def template(folder: str, setting_id: str) -> str:
    """A new setting's starting text."""
    if folder not in TEMPLATES:
        raise Refused(f"{folder} is not a folder of settings.", "bad-argument")
    return TEMPLATES[folder].format(id=setting_id)


def put(rel: str, text: str, new: bool = False) -> dict[str, Any]:
    """Save a setting: checked first, nothing written on a problem; `new` refuses a name already taken."""
    norm, f = resolve(rel)
    problems = check(norm, text)
    if new and _store.is_file(f):
        raise Refused(f"{norm} exists: open it to edit it.", "would-overwrite")
    if problems:
        raise Refused(f"{norm} not saved:\n  " + "\n  ".join(problems), "invalid-file")
    _store.mkdir(f.parent, parents=True, exist_ok=True)
    _common.write_text_atomic(f, text)
    return show(norm)


def deletable(rel: str) -> str:
    """The kind (`setting` or `run`) of something `remove` may delete; refuses anything else, as `remove` would,
    touching nothing."""
    norm, f = resolve(rel)
    k = kind_of(norm)
    if k == "setting" and _store.is_file(f):
        return k
    if k == "run":
        return k
    if not _store.exists(f):
        raise Refused(f"No file {norm} in the project's data.", "not-found")
    if k == "run-file":
        raise Refused(f"{norm} is part of a run: delete the run instead.", "not-allowed")
    raise Refused(_not_edited(norm), "not-allowed")


def remove(rel: str) -> dict[str, Any]:
    """Delete a setting, or a whole run (its files, outputs and rows); anything else is refused."""
    norm, f = resolve(rel)
    k = kind_of(norm)
    if k == "setting":
        if not _store.is_file(f):
            raise Refused(f"No file {norm} in the project's data.", "not-found")
        _store.unlink(f)
        return {"deleted": norm, "kind": "setting"}
    if k == "run":
        outs = len(_outputs.lines(f))
        rows = len((_outputs.rows_text(f) or "").splitlines())
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
    return {
        "path": norm,
        "files": _files_under(d),
        "outputs": len(_outputs.lines(d)),
        "rows": len((_outputs.rows_text(d) or "").splitlines()),
    }


def search(text: str) -> dict[str, Any]:
    """Every file under data/ whose path holds `text` (case ignored), the first LIMIT of them."""
    q = (text or "").strip().lower()
    if not q:
        return {"query": "", "total": 0, "paths": []}
    data = _data()
    hits = sorted(
        str(p.relative_to(data))
        for p in _store.rglob(data, "*")
        if _store.is_file(p) and q in str(p.relative_to(data)).lower() and not p.name.startswith(_store.DB)
    )
    return {"query": text, "total": len(hits), "paths": hits[:LIMIT]}
