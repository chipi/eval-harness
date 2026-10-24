"""Gold labels, predicted labels and per-class precision / recall: the classification
pieces `bootstrap_test` (core) and `classification_report` (a report) both need. They lived in
the report, so a core command imported a showcase script."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

from collections import defaultdict

from evaluation_harness import _common
from evaluation_harness._adapter import adapter_module
from evaluation_harness._common import die
from evaluation_harness._runs import item_rows, runs_on

#: Predictions the adapter could not parse into a label are counted, never dropped. An arm
#: that returns prose on a fifth of the items has a real problem, and silently excluding
#: those items would raise its precision by removing its failures from the denominator.
UNPARSED = "<unparsed>"


def reference_labels(dataset_id: str, tier: str) -> dict:
    """item_id -> label, from the reference files of one tier (`gold`, `silver`)."""
    root = _common.REFERENCES / tier / dataset_id
    if not root.is_dir():
        die(f"no {tier} references at {root}")
    return {p.stem: p.read_text(encoding="utf-8").strip() for p in root.glob("*.txt")}


def label_parser(adapter_spec: str | None):
    """The example's own `parse_label`, if its adapter can be imported.

    Returns None when it cannot -- on a machine without the example's venv, or for a
    run whose adapter has moved -- and the caller then falls back to the frozen
    `_meta.predicted`. Degrading to the old behaviour is correct; silently reporting
    two different parsers in one table was not.
    """
    task = getattr(adapter_module(adapter_spec), "TASK", None)
    return getattr(task, "parse_label", None) if task is not None else None


def predictions(dataset_id: str, match: str | None) -> dict:
    """config_id -> {item_id: predicted label}, over every matching run on disk."""
    out: dict = defaultdict(dict)
    for d, m in runs_on(dataset_id, match=match):
        cid = m["config_id"]
        parse = label_parser(m.get("adapter"))
        for row in item_rows(d):
            item = row["item_id"]
            if not item:
                continue
            # RE-PARSE FROM THE STORED OUTPUT when it is available, exactly as
            # `score()` does. `_meta.predicted` is the parse FROZEN AT RUN TIME, so
            # after a parser change plus `make rescore`, accuracy reflected the new
            # parser and macro-F1 the old one -- two numbers in the same report
            # measuring two different systems. Parser changes are precisely what this
            # repo studies (one was worth 8.6 accuracy points), so this was the worst
            # possible field to freeze. Found by external review.
            pred = None
            if parse is not None:
                out_f = d / "outputs" / f"{item}.txt"
                if out_f.is_file():
                    pred = parse(out_f.read_text(encoding="utf-8"))
            if pred is None:
                pred = (row.get("_meta") or {}).get("predicted")
            out[cid][item] = pred if pred else UNPARSED
    return out


def per_class(pairs: list, labels: list) -> dict:
    """precision / recall / f1 / support per class, from (gold, predicted) pairs."""
    stats = {}
    for label in labels:
        tp = sum(1 for g, p in pairs if g == label and p == label)
        fp = sum(1 for g, p in pairs if g != label and p == label)
        fn = sum(1 for g, p in pairs if g == label and p != label)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        stats[label] = {"p": prec, "r": rec, "f1": f1, "support": tp + fn}
    return stats
