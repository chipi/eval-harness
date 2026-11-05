"""Failure modes and the tags on outputs (PLAN_0.8.0 D1): how an arm fails, counted, not only how often.

A project names its failure modes once, `data/failure-modes/<id>.yaml` (like a field set). A person or an agent tags
outputs in a sheet (`evh inspect --sheet … --fill tags --modes <id>`: one `failure_modes: <arm>` column per arm,
cells `mode|mode`), and `evh sheet-import … --tags <name> --modes <id>` reads it back into a tag set,
`data/tags/<dataset>/<name>/tags.json`: who tagged, when, from which sheet, and per run and item the modes. A tag set
is never edited (a correction is a new set). `evh tags` and the goal page count the modes per arm.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import re
from collections import Counter
from pathlib import Path
from typing import Any

from evaluation_harness import _common
from evaluation_harness._common import die, now, read_json, write_json

SET_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,99}$")
#: A sheet's tag columns: `failure_modes: <arm token>`; cells name modes separated by `|` (or `,`). `ok` says the output
#: was read and has none; a blank cell was not read and is not recorded, so an unfinished sheet never reads as "fine".
COLUMN = "failure_modes: "
OK = "ok"


def modes_root() -> Path:
    """data/failure-modes/: the project's failure-mode lists."""
    return _common.DATA / "failure-modes"


def tags_root() -> Path:
    """data/tags/: the tag sets, one folder per dataset and set."""
    return _common.DATA / "tags"


def load_modes(modes_id: str) -> dict[str, Any]:
    """A failure-mode list by id; refused when it does not exist or names a mode twice."""
    import yaml  # noqa: PLC0415

    if not SET_ID.match(modes_id or ""):
        die(f"--modes {modes_id!r}: lowercase letters, digits, _ . - (at most 100)", "bad-argument")
    f = modes_root() / f"{modes_id}.yaml"
    if not f.is_file():
        die(
            f"no failure modes {modes_id!r}: write {f.relative_to(_common.ROOT)} first (failure_modes_id, modes)",
            "not-found",
        )
    doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    ids = [m.get("id") for m in doc.get("modes") or [] if isinstance(m, dict)]
    if not ids or len(set(ids)) != len(ids):
        die(f"{f.name}: modes must be a list of distinct ids", "invalid-file")
    return doc


def mode_ids(doc: dict[str, Any]) -> list[str]:
    """The ids of a failure-mode list, in its order."""
    return [m["id"] for m in doc.get("modes") or []]


def parse_cell(cell: str) -> list[str] | None:
    """The modes a sheet cell names: `invented-fact|too-long`, commas too, order kept, once each; [] for `ok` (read,
    nothing wrong); None for a blank cell (not read)."""
    if not (cell or "").strip():
        return None
    if cell.strip().lower() == OK:
        return []
    out: list[str] = []
    for x in re.split(r"[|,]", cell or ""):
        x = x.strip()
        if x and x not in out:
            out.append(x)
    return out


def set_dir(dataset_id: str, name: str) -> Path:
    """Where one tag set lives; its name is checked first, so it can never leave data/tags/."""
    if not SET_ID.match(name or ""):
        die(
            f"tag set {name!r}: lowercase letters, digits, _ . - (at most 100), starting with a letter or digit",
            "bad-argument",
        )
    return tags_root() / dataset_id / name


def write_tags(
    dataset_id: str,
    name: str,
    modes_id: str,
    tags: dict[str, dict[str, dict[str, Any]]],
    source: dict[str, Any],
) -> dict[str, Any]:
    """Write a new tag set. `tags`: {run_id: {item_id: {"modes": [...], "note": str?}}}. Refused when the set
    exists (never edited), an item is not in the dataset, or a mode is not in the list."""
    out = set_dir(dataset_id, name)
    if out.exists() and any(out.iterdir()):
        die(
            f"{out} exists: a tag set is never edited. A correction is a new set: name another.",
            "would-overwrite",
        )
    known = set(mode_ids(load_modes(modes_id)))
    items = {it["item_id"] for it in _common.load_dataset(dataset_id).get("items") or []}
    bad = [
        f"{run}/{i}: {m}"
        for run, by_item in tags.items()
        for i, t in by_item.items()
        for m in t["modes"]
        if m not in known
    ]
    if bad:
        die(
            f"{len(bad)} tag(s) name no mode of {modes_id} ({', '.join(sorted(known))}): {', '.join(bad[:8])}",
            "invalid-file",
        )
    alien = sorted({i for by_item in tags.values() for i in by_item if i not in items})
    if alien:
        die(f"{len(alien)} item(s) not in {dataset_id}: {', '.join(alien[:8])}", "not-found")
    doc = {
        "kind": "tag-set",
        "dataset_id": dataset_id,
        "set": name,
        "failure_modes": modes_id,
        "source": source,
        "created_at": now(),
        "n_tagged": sum(len(v) for v in tags.values()),
        "runs": tags,
    }
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "tags.json", doc)
    return doc


def tag_sets(dataset_id: str | None = None) -> list[dict[str, Any]]:
    """Every tag set (of one dataset), each its record; sorted by dataset, then set."""
    root = tags_root()
    pat = f"{dataset_id}/*/tags.json" if dataset_id else "*/*/tags.json"
    found = []
    for f in sorted(root.glob(pat)) if root.is_dir() else []:
        doc = read_json(f)
        if isinstance(doc, dict):
            found.append(doc)
    return found


def counts(dataset_id: str, run_config: dict[str, str] | None = None) -> dict[str, Any]:
    """Per arm (its config_id, when `run_config` maps run ids to them; else the run), how many outputs were tagged and
    how many times each mode was: {arm: {"tagged": n, "outputs": m, "modes": {mode: n}}}, across every tag set of the
    dataset. `outputs` counts the outputs read (`ok` ones included: read and found fine)."""
    out: dict[str, dict[str, Any]] = {}
    for doc in tag_sets(dataset_id):
        for run, by_item in (doc.get("runs") or {}).items():
            arm = (run_config or {}).get(run, run)
            slot = out.setdefault(arm, {"tagged": 0, "outputs": 0, "modes": Counter()})
            for t in by_item.values():
                slot["outputs"] += 1
                if t.get("modes"):
                    slot["tagged"] += 1
                slot["modes"].update(t["modes"])
    return {a: {**v, "modes": dict(v["modes"].most_common())} for a, v in sorted(out.items())}


def by_run(dataset_id: str) -> dict[str, dict[str, list[str]]]:
    """{run: {item: modes}} over every tag set of the dataset (a later set's modes added after an earlier one's,
    once each); `ok` is []. What the sheet shows per item and arm."""
    out: dict[str, dict[str, list[str]]] = {}
    for doc in tag_sets(dataset_id):
        for run, by_item in (doc.get("runs") or {}).items():
            for item, t in by_item.items():
                have = out.setdefault(run, {}).setdefault(item, [])
                have += [m for m in t.get("modes") or [] if m not in have]
    return out


def tag_sheet(
    model: dict[str, Any], rows: list[dict[str, Any]], modes: dict[str, Any]
) -> tuple[list, list, dict]:
    """A sheet to tag in: (header, rows, key). Per item its text, each arm's output and a `failure_modes: <arm>` cell
    beside it (not blind: a tag is about whose output it is). The first row lists the modes (`item_id` `#modes`).
    The key names each column's run and each cell's text hash, so a sheet edited after it was written is refused."""
    from evaluation_harness._sheet import NOT_AN_ITEM, text_sha256  # noqa: PLC0415
    from evaluation_harness._sheets import NOTE  # noqa: PLC0415
    from evaluation_harness.label_sheet import view  # noqa: PLC0415

    arms = model["arms"]
    head = ["item_id", "item"]
    for a in arms:
        head += [f"output: {a['token']}", f"{COLUMN}{a['token']}"]
    head.append(NOTE)
    legend = "; ".join(
        f"{m['id']}: {m.get('description') or m.get('label') or ''}".strip() for m in modes["modes"]
    )
    body: list[list[Any]] = [
        [f"{NOT_AN_ITEM}modes", f"{legend}; ok: read, nothing wrong", *[""] * (len(head) - 2)]
    ]
    key_rows: dict[str, dict[str, str]] = {}
    for r in rows:
        outs = {a["token"]: (r["decisions"].get(a["token"]) or "").strip() for a in arms}
        if not any(outs.values()):
            continue
        key_rows[r["item"]] = {t: text_sha256(o) for t, o in outs.items() if o}
        line = [r["item"], view(model["dataset_id"], r["item"], None)]
        for a in arms:
            line += [outs[a["token"]], ""]
        body.append([*line, ""])
    key = {
        "kind": "sheet-key",
        "dataset_id": model["dataset_id"],
        "fill": "tags",
        "failure_modes": modes["failure_modes_id"],
        "arms": [
            {"arm": a["token"], "run": a["run"], "path": a["path"], "config_id": a["config_id"]} for a in arms
        ],
        "rows": key_rows,
    }
    return head, body, key


def tags_from_sheet(rows: list[dict[str, str]], key: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """{run: {item: {"modes", "note"?}}} from a filled tag sheet, checked against its key: a row that is not the
    key's, or an output edited since, is refused; blank cells are not read and not recorded."""
    from evaluation_harness._sheet import text_sha256  # noqa: PLC0415
    from evaluation_harness._sheets import NOTE  # noqa: PLC0415

    run_of = {a["arm"]: a["run"] for a in key["arms"]}
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for r in rows:
        item = r["item_id"]
        if item not in key["rows"]:
            die(f"row {item!r} is not in the sheet's key (another sheet's?)", "mismatch")
        for token, sha in key["rows"][item].items():
            if text_sha256((r.get(f"output: {token}") or "").strip()) != sha:
                die(f"{item}: the output of {token} is not the one the sheet was written with", "mismatch")
            modes = parse_cell(r.get(f"{COLUMN}{token}") or "")
            if modes is None:
                continue
            entry: dict[str, Any] = {"modes": modes}
            if (r.get(NOTE) or "").strip():
                entry["note"] = r[NOTE].strip()
            out.setdefault(run_of[token], {})[item] = entry
    return out
