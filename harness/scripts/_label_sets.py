"""Label sets (RFC-023, ADR-0022): what the right answer for one item is, and who said it.

A label set is one labelling pass over one dataset by one source, never edited:

    data/labels/<dataset>/<set>/<item_id>.txt   the label, the text a scorer reads (as a reference item is)
    data/labels/<dataset>/<set>/labels.json     the dataset, the set, its source, when, the guideline it followed,
                                                and per item the label's sha256 and the item's (`source_sha256`)

The source is `person` (who), `model` (the run its outputs came from) or `rule` (a mapping over a capture's
recorded outcomes). Labels follow the item, not the dataset: a set records each item's sha256, so an item with the
same bytes in another dataset (a later version, a production dataset) has the same labels. (Not `_labels.py`: that
is the classification report's predicted and gold labels.)
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import hashlib
import re
from pathlib import Path
from typing import Any

from evaluation_harness._common import die, load_dataset, now, read_json, write_json

SOURCES = ("person", "model", "rule")
SET_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,99}$")


def labels_root() -> Path:
    """data/labels/ (the project's, resolved when first asked)."""
    from evaluation_harness import _common  # noqa: PLC0415

    return _common.LABELS


def set_dir(dataset_id: str, name: str) -> Path:
    """Where one set lives; its name is checked first, so it can never leave data/labels/."""
    if not SET_ID.match(name or ""):
        die(
            f"label set {name!r}: lowercase letters, digits, _ . - (at most 100), starting with a letter or digit"
        )
    return labels_root() / dataset_id / name


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def guideline_of(path: Path | None) -> dict[str, str] | None:
    """The guideline a set was labelled by, as it records it (its path within the project and its sha256)."""
    if path is None:
        return None
    if not path.is_file():
        die(f"--guideline: no file {path}")
    from evaluation_harness._common import ROOT  # noqa: PLC0415

    try:
        shown = str(path.resolve().relative_to(ROOT))
    except ValueError:
        shown = path.name
    return {"path": shown, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write_set(
    dataset_id: str,
    name: str,
    labels: dict[str, str],
    source: dict[str, Any],
    guideline: Path | None = None,
    notes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Write a new label set and return its record. Refused when the set exists (a set is never edited: a
    correction is a new set), when an item is not in the dataset, when a label is empty or the source is unknown."""
    if source.get("kind") not in SOURCES:
        die(f"a label's source is one of {', '.join(SOURCES)}, not {source.get('kind')!r}")
    out = set_dir(dataset_id, name)
    if out.exists() and any(out.iterdir()):
        die(f"{out} exists: a label set is never edited. A correction is a new set: name another.")
    ds = load_dataset(dataset_id)
    items = {it["item_id"]: it for it in ds.get("items") or []}
    unknown = sorted(set(labels) - set(items))
    if unknown:
        die(
            f"{len(unknown)} item(s) not in {dataset_id}: {', '.join(unknown[:8])}"
            + (" ..." if len(unknown) > 8 else "")
        )
    empty = sorted(i for i, t in labels.items() if not str(t).strip())
    if empty:
        die(
            f"{len(empty)} empty label(s): {', '.join(empty[:8])}. An item with no label is left out, not labelled empty."
        )
    if not labels:
        die("no labels: nothing written")
    out.mkdir(parents=True, exist_ok=True)
    rows: dict[str, dict[str, str]] = {}
    for iid in sorted(labels):
        text = str(labels[iid]).strip() + "\n"
        (out / f"{iid}.txt").write_text(text, encoding="utf-8")
        rows[iid] = {"sha256": _sha(text), "item_sha256": str(items[iid].get("source_sha256") or "")}
    doc: dict[str, Any] = {
        "dataset_id": dataset_id,
        "set": name,
        "source": source,
        "created_at": now(),
        "guideline": guideline_of(guideline),
        "n_items": len(rows),
        "items": rows,
    }
    kept = {k: v for k, v in sorted((notes or {}).items()) if k in rows and v}
    if kept:
        doc["notes"] = kept
    write_json(out / "labels.json", doc)
    return doc


def sets() -> list[dict[str, Any]]:
    """Every label set in the project, each its record with `_dir`; sorted by dataset, then set."""
    root = labels_root()
    found = []
    for f in sorted(root.glob("*/*/labels.json")) if root.is_dir() else []:
        doc = read_json(f)
        if isinstance(doc, dict):
            doc["_dir"] = f.parent
            found.append(doc)
    return found


def text_of(doc: dict[str, Any], item_id: str) -> str | None:
    """One label's text from a set, or None."""
    f = Path(doc["_dir"]) / f"{item_id}.txt"
    return f.read_text(encoding="utf-8").strip() if f.is_file() else None


def labels_for(dataset_id: str) -> dict[str, list[dict[str, Any]]]:
    """{item_id: [{set, dataset_id, source, text}]}: every label any set gives an item of this dataset, matched by
    the item's sha256, so labels made on another dataset with the same item count (they follow the item)."""
    ds = load_dataset(dataset_id)
    by_sha: dict[str, list[str]] = {}
    for it in ds.get("items") or []:
        if it.get("source_sha256"):
            by_sha.setdefault(it["source_sha256"], []).append(it["item_id"])
    out: dict[str, list[dict[str, Any]]] = {}
    for doc in sets():
        for iid, row in (doc.get("items") or {}).items():
            for mine in by_sha.get(row.get("item_sha256") or "", []):
                text = text_of(doc, iid)
                if text is not None:
                    out.setdefault(mine, []).append(
                        {
                            "set": doc["set"],
                            "dataset_id": doc["dataset_id"],
                            "source": doc.get("source") or {},
                            "text": text,
                        }
                    )
    return out


def coverage(dataset_id: str) -> list[dict[str, Any]]:
    """Per set covering this dataset's items (by hash): the set, its dataset, source, guideline, created, and the
    dataset's items it labels."""
    per: dict[tuple[str, str], dict[str, Any]] = {}
    for iid, rows in labels_for(dataset_id).items():
        for r in rows:
            k = (r["dataset_id"], r["set"])
            per.setdefault(
                k, {"set": r["set"], "dataset_id": r["dataset_id"], "source": r["source"], "items": set()}
            )
            per[k]["items"].add(iid)
    docs = {(d["dataset_id"], d["set"]): d for d in sets()}
    out = []
    for k, v in sorted(per.items()):
        d = docs.get(k) or {}
        out.append(
            {
                **v,
                "items": sorted(v["items"]),
                "guideline": d.get("guideline"),
                "created_at": d.get("created_at"),
            }
        )
    return out


def agreement(dataset_id: str) -> list[dict[str, Any]]:
    """For each pair of sets covering this dataset: on how many of its items both label, and on how many they agree."""
    per_item = labels_for(dataset_id)
    names = sorted({(r["dataset_id"], r["set"]) for rows in per_item.values() for r in rows})
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            both = agree = 0
            for rows in per_item.values():
                ta = next((r["text"] for r in rows if (r["dataset_id"], r["set"]) == a), None)
                tb = next((r["text"] for r in rows if (r["dataset_id"], r["set"]) == b), None)
                if ta is not None and tb is not None:
                    both += 1
                    agree += ta == tb
            if both:
                out.append({"a": "/".join(a), "b": "/".join(b), "both": both, "agree": agree})
    return out


def source_line(source: dict[str, Any]) -> str:
    """A source in words: "person · owner", "model · <run>", "rule · <capture>"."""
    kind = source.get("kind", "?")
    who = source.get("by") or source.get("run_id") or source.get("capture") or ""
    return f"{kind} · {who}" if who else kind
