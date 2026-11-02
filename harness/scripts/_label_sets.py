"""Label sets (RFC-023, ADR-0022): what the right answer for one item is, and who said it.

A label set is one labelling pass over one dataset by one source, never edited:

    data/labels/<dataset>/<set>/<item_id>.txt   the label, the text a scorer reads (as a reference item is)
    data/labels/<dataset>/<set>/labels.json     the dataset, the set, its source, when, the guideline it followed,
                                                and per item the label's sha256 and the item's (`source_sha256`)

A label is one right answer, or several when more than one is right for the item, written
{"accept": ["escalate", "file"]} (`answers` reads either; two labels agree when they accept the same answers: `compare`).

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
import json
import re
from collections import Counter
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


def answers(label: str) -> list[str]:
    """The answers a label (or a reference) accepts: several when it is written {"accept": ["escalate", "file"]} (an
    item with more than one right answer), else the label itself."""
    text = label.strip()
    if text.startswith('{"accept"'):
        try:
            got = json.loads(text).get("accept")
        except ValueError:
            got = None
        if isinstance(got, list) and got and all(isinstance(a, str) and a.strip() for a in got):
            return [a.strip() for a in got]
    return [text]


def label_text(accepted: list[str]) -> str:
    """How a label accepting these answers is written: the answer itself when there is one, else
    {"accept": [...]}, sorted and without repeats, so one meaning has one text (and one hash)."""
    got = sorted({a.strip() for a in accepted if a.strip()})
    return got[0] if len(got) == 1 else json.dumps({"accept": got}, ensure_ascii=False) if got else ""


def label_line(label: str) -> str:
    """A label as a view shows it: its answer, or its answers joined by "or"."""
    return " or ".join(answers(label))


#: Labels are compared as categories when the two sets use at most CATEGORY_MAX distinct answers, each of at most
#: CATEGORY_WORDS words and CATEGORY_CHARS characters on one line; otherwise they are free text, and exact text says
#: nothing about agreement.
CATEGORY_MAX, CATEGORY_WORDS, CATEGORY_CHARS = 50, 3, 40


def _masi(a: frozenset[str], b: frozenset[str]) -> float:
    """MASI distance between two answer sets (Passonneau 2006): 0 the same, 1 nothing shared; a subset or a
    partial overlap in between."""
    if a == b:
        return 0.0
    shared = len(a & b)
    if not shared:
        return 1.0
    monotonicity = 2 / 3 if a <= b or b <= a else 1 / 3
    return 1 - shared / len(a | b) * monotonicity


def compare(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    """How two label sets compare on the items both label, `pairs` their two labels per item.

    `both` the items; `kind` "categories" or "free text" (CATEGORY_MAX); for categories, `same` the items whose labels
    accept the same answers, `share` those whose labels share at least one (a label accepting several agrees more
    easily: shown apart, never as agreement), `kappa` Cohen's kappa on the labels, `alpha` Krippendorff's alpha
    (nominal, or with MASI distance when a label accepts several answers: `alpha_distance`) and `confusion` {a's
    label: {b's label: n}}. A coefficient is None when it is undefined (every label the same)."""
    sets_ = [(frozenset(answers(a)), frozenset(answers(b))) for a, b in pairs]
    every = {x for a, b in sets_ for x in (*a, *b)}
    out: dict[str, Any] = {"both": len(pairs)}
    if len(every) > CATEGORY_MAX or any(
        len(x) > CATEGORY_CHARS or "\n" in x or len(x.split()) > CATEGORY_WORDS for x in every
    ):
        return {**out, "kind": "free text"}
    shown = [(label_line(label_text(list(a))), label_line(label_text(list(b)))) for a, b in sets_]
    confusion: dict[str, dict[str, int]] = {}
    for a, b in shown:
        confusion.setdefault(a, {}).setdefault(b, 0)
        confusion[a][b] += 1
    n = len(pairs)
    po = sum(a == b for a, b in sets_) / n if n else 0.0
    pa, pb = Counter(a for a, _ in shown), Counter(b for _, b in shown)
    pe = sum(pa[k] * pb[k] for k in pa) / (n * n) if n else 0.0
    several = any(len(a) > 1 or len(b) > 1 for a, b in sets_)
    dist = _masi if several else lambda a, b: 0.0 if a == b else 1.0
    values = [v for pair in sets_ for v in pair]
    m = len(values)
    observed = sum(dist(a, b) for a, b in sets_) / n if n else 0.0
    expected = (
        sum(dist(values[i], values[j]) for i in range(m) for j in range(m) if i != j) / (m * (m - 1))
        if m > 1
        else 0.0
    )
    return {
        **out,
        "kind": "categories",
        "same": sum(a == b for a, b in sets_),
        "share": sum(bool(a & b) for a, b in sets_),
        "kappa": None if not n or pe >= 1 else round((po - pe) / (1 - pe), 4),
        "alpha": None if not expected else round(1 - observed / expected, 4),
        "alpha_distance": "MASI" if several else "nominal",
        "confusion": confusion,
    }


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
    rebuild: str | None = None,
) -> dict[str, Any]:
    """Write a new label set and return its record. Refused when the set exists (a set is never edited: a
    correction is a new set), when an item is not in the dataset, when a label is empty or the source is unknown.
    `rebuild`: the texts are kept out of git (a .gitignore beside them), and this command writes them again."""
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
    bad = sorted(
        i
        for i, t in labels.items()
        if answers(str(t)) == [str(t).strip()] and str(t).strip().startswith('{"accept"')
    )
    if bad:
        die(
            f'{len(bad)} label(s) start {{"accept" but are not a list of answers: {", ".join(bad[:8])}. '
            'Several right answers are written {"accept": ["escalate", "file"]}.'
        )
    out.mkdir(parents=True, exist_ok=True)
    rows: dict[str, dict[str, str]] = {}
    for iid in sorted(labels):
        text = label_text(answers(str(labels[iid]))) + "\n"
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
    if rebuild:
        doc["redistributed"] = False
        doc["rebuild"] = rebuild
        (out / ".gitignore").write_text(
            "# the label texts are not redistributed (labels.json says how to rebuild them)\n*.txt\n"
        )
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
    """For each pair of sets covering this dataset that both label an item: {a, b, **compare(...)}."""
    per_item = labels_for(dataset_id)
    names = sorted({(r["dataset_id"], r["set"]) for rows in per_item.values() for r in rows})
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            pairs = []
            for rows in per_item.values():
                ta = next((r["text"] for r in rows if (r["dataset_id"], r["set"]) == a), None)
                tb = next((r["text"] for r in rows if (r["dataset_id"], r["set"]) == b), None)
                if ta is not None and tb is not None:
                    pairs.append((ta, tb))
            if pairs:
                out.append({"a": "/".join(a), "b": "/".join(b), **compare(pairs)})
    return out


def source_line(source: dict[str, Any]) -> str:
    """A source in words: "person · owner", "model · <run>", "rule · <capture>"."""
    kind = source.get("kind", "?")
    who = source.get("by") or source.get("run_id") or source.get("capture") or ""
    return f"{kind} · {who}" if who else kind
