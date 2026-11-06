"""A setting as a form (UXS-004): its kind's schema, its values, what the project can suggest, and the save that keeps
the file's comments.

The page never edits YAML text. It gets the schema (references inlined) and the setting's values as JSON, builds one
field per key, and sends the values back. Saving merges them into the file as ruamel.yaml read it, so comments,
blank lines and key order stay, and only the values that changed are written. `evh data-put --set` goes through the
same merge.
"""

from __future__ import annotations

import copy
import datetime as _dt
import io
import json
import re
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Any

from evaluation_harness import _common, _data_page, _store

#: The schema of the validate policy, which validate reads without one (written from `validate_tree.policy`).
POLICY_SCHEMA = "validate.schema.json"
#: Keys shown as a box of a few lines rather than one line.
LONG = {
    "statement",
    "decision",
    "description",
    "notes",
    "why",
    "rule",
    "usage",
    "what",
    "differs_from_this_use",
}
#: Fields a command writes, by kind: a dotted path (`*` any list index or key) and the command. The form shows them
#: and keeps them as they are.
WRITTEN: dict[str, dict[str, str]] = {
    "models": {
        "capabilities": "evh model-onboard",
        "deployments.*.onboarding": "evh model-onboard",
        "deployments.*.checked_at": "evh model-onboard",
        "smokes": "evh arm-smoke",
    },
}
#: Fields that name other data, by kind: a dotted path and the list of the project's values it suggests.
REFS: dict[str, dict[str, str]] = {
    "configs": {
        "dataset_id": "datasets",
        "goal": "goals",
        "model_record": "models",
        "deployment": "deployments",
        "hypothesis.against": "config_ids",
    },
    "goals": {
        "datasets.*.dataset_id": "datasets",
        "superseded_by": "goals",
        "references.*.reference_id": "references",
    },
    "scorers": {"dataset_id": "datasets", "validation.dataset_id": "datasets", "supersedes": "scorers"},
    "fields": {},
    "models": {},
    "failure-modes": {},
    _data_page.POLICY: {"committed.*": "runs_folders", "scorer_sources.*.dir": "runs_folders"},
}
#: A new setting's values, before its id is filled in.
NEW: dict[str, dict[str, Any]] = {
    "configs": {"config_id": "", "dataset_id": "", "params": {"provider": ""}},
    "goals": {
        "goal_id": "",
        "title": "",
        "statement": "",
        "decision": "",
        "success_criteria": {"primary": {"measure": "", "direction": "higher"}},
        "datasets": [{"dataset_id": ""}],
    },
    "fields": {"fieldset_id": "", "fields": []},
    "scorers": {
        "scorer_id": "",
        "kind": "judge",
        "dataset_id": "",
        "judges": [],
        "prompt": {"file": ""},
        "protocol": {"outputs_per_call": 1, "position_check_fraction": 0.0, "noise_check_fraction": 0.1},
    },
    "models": {"model_id": "", "kind": "llm", "aliases": []},
    "failure-modes": {"failure_modes_id": "", "modes": []},
    _data_page.POLICY: {"committed": [], "floors": {}},
}


def folder_of(norm: str) -> str:
    """The settings folder a setting's path is in (the policy is its own)."""
    return _data_page.POLICY if norm == _data_page.POLICY else norm.split("/", 1)[0]


def _inline(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            target = dict(defs[ref.rsplit("/", 1)[1]])
            target.update({k: v for k, v in node.items() if k != "$ref"})
            return _inline(target, defs)
        return {k: _inline(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_inline(v, defs) for v in node]
    return node


def schema_of(folder: str) -> dict[str, Any]:
    """The kind's schema with its `$defs` references inlined, as the form builds from it."""
    name = POLICY_SCHEMA if folder == _data_page.POLICY else _data_page.SETTINGS[folder][1]
    raw = json.loads(_store.read_text(_common.SCHEMAS / name))
    return dict(_inline(raw, raw.get("$defs") or {}))


def plain(x: Any) -> Any:
    """A parsed value as JSON can carry it: a YAML date or time as its ISO text."""
    if isinstance(x, (_dt.date, _dt.datetime)):
        return x.isoformat()
    if isinstance(x, dict):
        return {str(k): plain(v) for k, v in x.items()}
    if isinstance(x, list):
        return [plain(v) for v in x]
    return x


def values_of(norm: str) -> dict[str, Any]:
    """A setting's values, as the form shows them."""
    text = _store.read_text(_data_page.resolve(norm)[1])
    if norm == _data_page.POLICY:
        doc = json.loads(text)
    else:
        import yaml  # noqa: PLC0415

        doc = yaml.safe_load(text)
    if not isinstance(doc, dict):
        raise _data_page.Refused(f"{norm} is not a mapping of keys: open it as text.", "invalid-file")
    return dict(plain(doc))


def _stems(folder: str) -> list[str]:
    d = _common.DATA / folder
    return sorted(p.stem for p in _store.glob(d, "*.yaml")) if _store.is_dir(d) else []


def options() -> dict[str, Any]:
    """What the project has, for the fields that name it: datasets, goals, model records and their deployments, arm
    configs' ids, scorers, reference sets, runs folders."""
    import yaml  # noqa: PLC0415

    data = _common.DATA
    out: dict[str, Any] = {
        "datasets": sorted(p.stem for p in _store.glob(data / "datasets", "*.json"))
        if _store.is_dir(data / "datasets")
        else [],
        "goals": _stems("goals"),
        "models": _stems("models"),
        "scorers": _stems("scorers"),
    }
    deployments: dict[str, list[str]] = {}
    for p in _store.glob(data / "models", "*.yaml") if _store.is_dir(data / "models") else []:
        try:
            doc = yaml.safe_load(_store.read_text(p)) or {}
        except yaml.YAMLError:
            continue
        deployments[p.stem] = [str(d.get("id")) for d in doc.get("deployments") or [] if isinstance(d, dict)]
    out["deployments"] = deployments
    ids = []
    for p in _store.glob(data / "configs", "*.yaml") if _store.is_dir(data / "configs") else []:
        try:
            cid = (yaml.safe_load(_store.read_text(p)) or {}).get("config_id")
        except (yaml.YAMLError, AttributeError):
            continue
        if cid:
            ids.append(str(cid))
    out["config_ids"] = sorted(set(ids))
    refs: set[str] = set()
    for tier in ("gold", "silver"):
        d = data / "references" / tier
        if _store.is_dir(d):
            refs.update(p.name for p in _store.iterdir(d) if _store.is_dir(p))
    out["references"] = sorted(refs)
    folders = []
    for top in sorted(_store.glob(data, "runs*")) if _store.is_dir(data) else []:
        if not _store.is_dir(top):
            continue
        folders.append(top.name)
        for sub in sorted(_store.iterdir(top)):
            if _store.is_dir(sub) and _data_page.kind_of(f"{top.name}/{sub.name}") != "run":
                folders.append(f"{top.name}/{sub.name}")
    out["runs_folders"] = folders
    return out


def form(rel: str, new_in: str | None = None) -> dict[str, Any]:
    """Everything the page builds a setting's form from. `new_in` (a settings folder, or the policy) starts a new one
    from its kind's values; otherwise `rel` is an existing setting."""
    if new_in is not None:
        folder = new_in
        if folder not in _data_page.SETTINGS and folder != _data_page.POLICY:
            raise _data_page.Refused(f"{folder} is not a folder of settings.", "bad-argument")
        norm = _data_page.POLICY if folder == _data_page.POLICY else ""
        values = copy.deepcopy(NEW[folder])
    else:
        norm, f = _data_page.resolve(rel)
        if _data_page.kind_of(norm) != "setting":
            raise _data_page.Refused(_data_page._not_edited(norm), "not-allowed")
        if not _store.is_file(f):
            raise _data_page.Refused(f"No file {norm} in the project's data.", "not-found")
        folder = folder_of(norm)
        values = values_of(norm)
    word, key, named = (
        ("validate policy", None, False)
        if folder == _data_page.POLICY
        else (_data_page.SETTINGS[folder][0], _data_page.SETTINGS[folder][2], _data_page.SETTINGS[folder][3])
    )
    out: dict[str, Any] = {
        "path": norm,
        "folder": folder,
        "kind": word,
        "new": new_in is not None,
        "schema": schema_of(folder),
        "values": values,
        "id_key": key,
        "id_is_file_name": named,
        "long": sorted(LONG),
        "written": WRITTEN.get(folder, {}),
        "refs": REFS.get(folder, {}),
        "options": options(),
    }
    if folder == "configs" and values.get("config_id"):
        out["runs_made"] = _data_page.runs_of_config(str(values["config_id"]))
    return out


def problems(rel: str, values: Any) -> list[dict[str, Any]]:
    """What is wrong with these values as the setting at `rel`, each with the field it is at; [] when they may be
    saved."""
    norm, _f = _data_page.resolve(rel)
    if _data_page.kind_of(norm) != "setting":
        raise _data_page.Refused(_data_page._not_edited(norm), "not-allowed")
    if not isinstance(values, dict):
        return [{"path": [], "message": "a setting is a mapping of keys"}]
    folder = folder_of(norm)
    out: list[dict[str, Any]] = []
    if folder != _data_page.POLICY:
        _word, _schema, key, named = _data_page.SETTINGS[folder]
        stem = PurePosixPath(norm).stem
        if named and values.get(key) != stem:
            out.append(
                {"path": [key], "message": f"it must be the file name, {stem!r} (it is {values.get(key)!r})"}
            )
    import jsonschema  # noqa: PLC0415

    for err in sorted(
        jsonschema.Draft202012Validator(schema_of(folder)).iter_errors(values), key=lambda e: list(e.path)
    ):
        out.append(_said(err))
    return out


#: A JSON type as the form calls it.
WORDS = {"string": "text", "number": "a number", "integer": "a whole number", "boolean": "yes or no",
         "array": "a list", "object": "a group of fields", "null": "null"}  # fmt: skip


def _said(err: Any) -> dict[str, Any]:
    """A schema error as the form says it, at the field it is about."""
    path, v = list(err.path), err.validator
    if v == "required":
        m = re.match(r"'(.+)' is a required property", err.message)
        if m:
            return {"path": [*path, m.group(1)], "message": "required"}
    if v == "minLength" and err.instance == "":
        return {"path": path, "message": "required: it cannot be empty"}
    if v == "type":
        want = [err.validator_value] if isinstance(err.validator_value, str) else list(err.validator_value)
        return {"path": path, "message": f"must be {' or '.join(WORDS.get(w, w) for w in want)}"}
    if v == "enum":
        return {"path": path, "message": "must be one of: " + ", ".join(map(str, err.validator_value))}
    if v == "const":
        return {"path": path, "message": f"must be {err.validator_value}"}
    if v == "pattern":
        return {"path": path, "message": f"{err.instance!r} does not have the form {err.validator_value}"}
    if v == "minimum":
        return {"path": path, "message": f"must be at least {err.validator_value}"}
    if v == "additionalProperties":
        m = re.search(r"\((.+) (?:was|were) unexpected\)", err.message)
        return {"path": path, "message": f"not a field of this setting: {m.group(1) if m else err.message}"}
    return {"path": path, "message": err.message}


def _yaml(style: tuple[int, int, int, int] = (2, 4, 2, 4096)) -> Any:
    from ruamel.yaml import YAML  # noqa: PLC0415

    y = YAML()
    y.preserve_quotes = True
    y.width = style[3]
    y.indent(mapping=style[0], sequence=style[1], offset=style[2])
    y.representer.add_representer(
        type(None), lambda r, _d: r.represent_scalar("tag:yaml.org,2002:null", "null")
    )
    return y


#: The styles a settings file is written in: lists indented under their key (`  - x`) or not (`- x`), and long text
#: on one line (a person's file) or wrapped at 80 columns (one PyYAML wrote: a model record after `evh model-onboard`).
STYLES = ((2, 4, 2, 4096), (2, 2, 0, 4096), (2, 4, 2, 80), (2, 2, 0, 80))


def _dump(y: Any, doc: Any) -> str:
    buf = io.StringIO()
    y.dump(doc, buf)
    return buf.getvalue()


def _style_of(text: str) -> tuple[int, int, int, int]:
    """The style that writes the file back as it is, or the one closest to it."""
    best, least = STYLES[0], None
    for style in STYLES:
        y = _yaml(style)
        back = _dump(y, y.load(text)).splitlines()
        lines = text.splitlines()
        diff = sum(a != b for a, b in zip(back, lines)) + abs(len(back) - len(lines))
        if diff == 0:
            return style
        if least is None or diff < least:
            best, least = style, diff
    return best


def _same(old: Any, new: Any) -> bool:
    if isinstance(old, bool) or isinstance(new, bool):
        return isinstance(old, bool) and isinstance(new, bool) and old == new
    return plain(old) == new and not isinstance(new, (dict, list))


def merge(old: Any, new: Any, order: list[str] | None = None) -> Any:
    """`new` written over `old` (as ruamel.yaml read it): a key or item that is unchanged keeps its node, so its
    comments and its style stay; a removed key goes; a new key goes after the last key before it in `order`."""
    from ruamel.yaml.comments import CommentedMap, CommentedSeq  # noqa: PLC0415

    if isinstance(old, CommentedMap) and isinstance(new, dict):
        for k in [k for k in old if k not in new]:
            del old[k]
        rank = {k: i for i, k in enumerate(order or [])}
        for k, v in new.items():
            if k in old:
                old[k] = merge(old[k], v)
                continue
            pos = len(old)
            if k in rank:
                before = [i for i, ok in enumerate(old) if rank.get(ok, len(rank)) < rank[k]]
                pos = before[-1] + 1 if before else 0
            old.insert(pos, k, v)
        return old
    if isinstance(old, CommentedSeq) and isinstance(new, list):
        while len(old) > len(new):
            old.pop()
        for i, v in enumerate(new):
            if i < len(old):
                old[i] = merge(old[i], v)
            else:
                old.append(v)
        return old
    return old if _same(old, new) else new


def _at(ops: Sequence[tuple[str, int, int, int, int]], x: int) -> int:
    """Where line `x` of the first text is in the second, by their opcodes; `x` is never inside a changed block."""
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal" and i1 <= x <= i2:
            return j1 + (x - i1)
        if x == i1:
            return j1
        if x == i2:
            return j2
    return ops[-1][4] if ops else 0


def patch(ours: str, base: str, theirs: str) -> str:
    """The edits that turn `base` into `theirs`, made to `ours`.

    `base` is the file as ruamel.yaml writes it back unchanged, `theirs` the same with the new values, `ours` the file
    as it is. Lines the edit does not touch come from `ours`, byte for byte; where an edit meets a line ruamel.yaml
    would have written differently anyway (a list it reflows, text it unwraps), that stretch is taken from `theirs`.
    """
    from difflib import SequenceMatcher  # noqa: PLC0415

    o, b, t = ours.splitlines(keepends=True), base.splitlines(keepends=True), theirs.splitlines(keepends=True)
    bo = SequenceMatcher(None, b, o, autojunk=False).get_opcodes()
    bt = SequenceMatcher(None, b, t, autojunk=False).get_opcodes()
    edits = [(i1, i2) for tag, i1, i2, _j1, _j2 in bt if tag != "equal"]
    if not edits:
        return ours
    blocks = [(i1, i2) for tag, i1, i2, _j1, _j2 in bo if tag != "equal"] + edits

    def touches(a: tuple[int, int], z: tuple[int, int]) -> bool:
        return z[0] < max(a[1], a[0] + 1) and max(z[1], z[0] + 1) > a[0]

    regions: list[list[int]] = []
    for e in sorted(edits):
        lo, hi = e
        grown = True
        while grown:
            grown = False
            for z in blocks:
                if touches((lo, hi), z) and (z[0] < lo or z[1] > hi):
                    lo, hi, grown = min(lo, z[0]), max(hi, z[1]), True
        if regions and lo <= regions[-1][1]:
            regions[-1][1] = max(regions[-1][1], hi)
        else:
            regions.append([lo, hi])
    out, x = [], 0
    for lo, hi in regions:
        out += o[_at(bo, x) : _at(bo, lo)]
        out += t[_at(bt, lo) : _at(bt, hi)]
        x = hi
    out += o[_at(bo, x) :]
    return "".join(out)


def text_for(norm: str, values: dict[str, Any], before: str | None) -> str:
    """The file's text with these values; with `before` (its text now), only the lines the change touches move."""
    folder = folder_of(norm)
    if folder == _data_page.POLICY:
        theirs = json.dumps(values, indent=2, ensure_ascii=False) + "\n"
        if before is None:
            return theirs
        return patch(before, json.dumps(json.loads(before), indent=2, ensure_ascii=False) + "\n", theirs)
    order = list((schema_of(folder).get("properties") or {}).keys())
    from ruamel.yaml.comments import CommentedMap  # noqa: PLC0415

    if before is None:
        return _dump(_yaml(), merge(CommentedMap(), values, order))
    y = _yaml(_style_of(before))
    base = _dump(y, y.load(before))
    return patch(before, base, _dump(y, merge(y.load(before), values, order)))


def save(rel: str, values: dict[str, Any], new: bool = False) -> dict[str, Any]:
    """Save a setting's values: checked first, nothing written on a problem or when nothing changed; `new` refuses a
    name already taken."""
    norm, f = _data_page.resolve(rel)
    if new and _store.is_file(f):
        raise _data_page.Refused(f"{norm} exists: open it to edit it.", "would-overwrite")
    found = problems(norm, values)
    if found:
        raise _data_page.Refused(
            f"{norm} not saved:\n  "
            + "\n  ".join(f"{'.'.join(map(str, p['path'])) or '(top)'}: {p['message']}" for p in found),
            "invalid-file",
        )
    before = _store.read_text(f) if _store.is_file(f) else None
    if before is not None and values_of(norm) == values:
        return {**_data_page.show(norm), "unchanged": True}
    _store.mkdir(f.parent, parents=True, exist_ok=True)
    _common.write_text_atomic(f, text_for(norm, values, before))
    return {**_data_page.show(norm), "unchanged": False}


def _steps(key: str) -> list[Any]:
    return [int(s) if s.isdigit() else s for s in key.split(".") if s != ""]


def set_values(values: dict[str, Any], sets: list[tuple[str, Any]], unsets: list[str]) -> dict[str, Any]:
    """`values` with each dotted key set (a missing group or list item is made) and each unset key removed."""
    out = copy.deepcopy(values)
    for key, value in sets:
        steps = _steps(key)
        if not steps:
            raise _data_page.Refused(f"{key!r} names no field.", "bad-argument")
        node: Any = out
        for here, nxt in zip(steps, steps[1:]):
            if isinstance(node, list):
                if not isinstance(here, int) or here > len(node):
                    raise _data_page.Refused(
                        f"{key}: {here} is not an item of the list (it has {len(node)}).", "bad-argument"
                    )
                if here == len(node):
                    node.append([] if isinstance(nxt, int) else {})
                node = node[here]
            else:
                if not isinstance(node.get(here), (dict, list)):
                    node[here] = [] if isinstance(nxt, int) else {}
                node = node[here]
        last = steps[-1]
        if isinstance(node, list):
            if not isinstance(last, int) or last > len(node):
                raise _data_page.Refused(
                    f"{key}: {last} is not an item of the list (it has {len(node)}).", "bad-argument"
                )
            if last == len(node):
                node.append(value)
            else:
                node[last] = value
        else:
            node[last] = value
    for key in unsets:
        steps = _steps(key)
        node = out
        for here in steps[:-1]:
            try:
                node = node[here]
            except (KeyError, IndexError, TypeError):
                raise _data_page.Refused(f"{key}: no such field.", "bad-argument") from None
        try:
            del node[steps[-1]]
        except (KeyError, IndexError, TypeError):
            raise _data_page.Refused(f"{key}: no such field.", "bad-argument") from None
    return out


def flat(values: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Every value of a setting with its dotted key, as `evh data-show --fields` prints them."""
    if isinstance(values, dict) and values:
        return [kv for k, v in values.items() for kv in flat(v, f"{prefix}{k}.")]
    if isinstance(values, list) and values:
        return [kv for i, v in enumerate(values) for kv in flat(v, f"{prefix}{i}.")]
    return [(prefix[:-1], values)]
