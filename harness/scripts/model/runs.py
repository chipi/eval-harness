"""Runs and their scores (RFC-032 step 4): one collection, `data/runs/<run_id>/`, every pass of a system over a
dataset, each score of it under it.

    runs/<run_id>/run.json                        the pass: system, dataset, purpose, machine, settings, fingerprint
    runs/<run_id>/outputs.jsonl                   what the system answered, per item
    runs/<run_id>/scores/<key>/score.json         the scorer, the reference, the label it is read under
    runs/<run_id>/scores/<key>/metrics.json       the score: what it measured, where it differs from the run
    runs/<run_id>/scores/<key>/predictions.jsonl  its rows, per item

A score's key is `<scorer>@<reference>`: the scorer an adapter's 12 characters of sha256 or a judge scorer's id, the
reference `gold.<dataset>`, `silver.<dataset>`, `labels.<dataset>.<set>` or, for a judge, its judging set.

`record(score)` is what one record of a scored run says, the run's facts with the score's over them, as a run's
metrics.json said before this step: every reader takes `(score directory, record)` pairs. What a folder used to mean
is a field: the run's `purpose` (run, repeat, pair, retime) and `machine`, the score's `label` ("silver",
"rescored cd35dc1f", "judged/judge-summ-v1"). The arm a view reads is a system on a dataset under one label, the
score's and the run's purpose's joined ("rescored cd35dc1f, repeats")."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _store

RUN = "run.json"
SCORE = "score.json"
METRICS = "metrics.json"
ROWS = "predictions.jsonl"
OUTPUTS = "outputs.jsonl"

PURPOSES = ("run", "repeat", "pair", "retime")
#: What a run's purpose adds to the label of the arm it is read in (a re-timing is named by its machine).
PURPOSE_LABEL = {"run": "", "repeat": "repeats", "pair": "pair"}
#: Run fields that the record of a scored run did not hold before step 4: what a folder meant.
RUN_ONLY = ("purpose", "machine", "of")
#: Of a measured run's first record, what belongs to the score it made rather than to the pass.
SCORE_KEYS = (
    "scores",
    "primary_metric",
    "metric_kinds",
    "metric_directions",
    "metric_descriptions",
    "reference_tier",
    "rescore_dropped_metrics",
    "derived",
    "source_created_at",
)


def root(scratch: bool = False) -> Path:
    """data/runs; .build/scratch/runs for a throwaway pass (`evh run --scratch`), which nothing that reads runs sees."""
    return _common.SCRATCH_RUNS if scratch else _common.RUNS


def run_dir(run_id: str, scratch: bool = False) -> Path:
    """A run's directory."""
    return root(scratch) / run_id


def is_score(d: Path) -> bool:
    """Whether `d` is a score's directory (runs/<id>/scores/<key>)."""
    return Path(d).parent.name == "scores"


def run_of(score_dir: Path) -> Path:
    """The run a score is of."""
    return Path(score_dir).parent.parent


def reference_part(reference_id: str | None) -> str:
    """A reference id as it sits in a score's key: `gold/x` is `gold.x`; none is `none`."""
    return str(reference_id).replace("/", ".") if reference_id else "none"


def key(scorer: str, reference: str | None) -> str:
    """A score's key: `<scorer>@<reference>`."""
    if not scorer or "/" in scorer or "@" in scorer:
        raise ValueError(f"a score's scorer is a hash or a judge scorer's id, not {scorer!r}")
    return f"{scorer}@{reference_part(reference)}"


def scorer_of(rec: dict[str, Any]) -> str:
    """The scorer of a record, 12 characters (RFC-022): a re-score's `derived.with.sha256`, else the adapter's
    `sha256` its fingerprint's instrument records; "" when it records neither."""
    with_ = (rec.get("derived") or {}).get("with") or {}
    sha = with_.get("sha256") or (
        ((rec.get("fingerprint") or {}).get("instrument") or {}).get("adapter") or {}
    ).get("sha256")
    return str(sha or "")[:12]


def machine_of(fingerprint: dict | None) -> str:
    """The machine a run ran on, as its label says it: the operating system of its fingerprint's runner."""
    plat = str(((fingerprint or {}).get("runner") or {}).get("platform") or "")
    return plat.split("/", 1)[0].lower()


def _json(path: Path) -> dict[str, Any] | None:
    try:
        v = json.loads(_store.read_text(path, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return v if isinstance(v, dict) else None


def run(run_id_or_dir: str | Path) -> dict[str, Any] | None:
    """A run's run.json, or None."""
    d = run_id_or_dir if isinstance(run_id_or_dir, Path) else run_dir(run_id_or_dir)
    return _json(Path(d) / RUN)


def meta(score_dir: Path) -> dict[str, Any]:
    """A score's score.json: {scorer, reference, label}."""
    return _json(Path(score_dir) / SCORE) or {}


def record(score_dir: Path) -> dict[str, Any] | None:
    """What a scored run's record says: the run's facts with the score's over them (the keys the score unsets
    removed). None when either is missing or unreadable."""
    sd = Path(score_dir)
    r = run(run_of(sd)) if is_score(sd) else None
    s = _json(sd / METRICS)
    if r is None or s is None:
        return None
    unset = set(meta(sd).get("unset") or ())
    out = {k: v for k, v in r.items() if k not in unset}
    out.update(s)
    return out


def label(score_dir: Path, rec: dict[str, Any] | None = None) -> str:
    """The label of the arm a score is read in: the score's own and the run's purpose's, joined ("" for a run's first
    score of a plain run)."""
    rec = rec if rec is not None else record(score_dir) or {}
    purpose = rec.get("purpose") or "run"
    own = str(meta(score_dir).get("label") or "")
    by_purpose = (rec.get("machine") or "") if purpose == "retime" else PURPOSE_LABEL.get(purpose, purpose)
    return ", ".join(x for x in (own, by_purpose) if x)


def arm_prefix(lbl: str) -> str:
    """The first part of an arm's id: `runs` for a label of none, else the label as a slug (`rescored-cd35dc1f`)."""
    return "runs" if not lbl else re.sub(r"[^a-z0-9]+", "-", lbl.lower()).strip("-")


def arm_id(score_dir: Path, rec: dict[str, Any] | None = None) -> str:
    """`<prefix>/<dataset>/<system>`: the arm a score is read in."""
    rec = rec if rec is not None else record(score_dir) or {}
    return f"{arm_prefix(label(score_dir, rec))}/{rec.get('dataset_id')}/{rec.get('config_id')}"


def run_ids() -> list[str]:
    """Every run's id, sorted."""
    base = root()
    if not _store.is_dir(base):
        return []
    return sorted(d.name for d in _store.iterdir(base) if _store.is_file(d / RUN))


def scores_of(run_id_or_dir: str | Path) -> list[Path]:
    """A run's score directories, sorted by key."""
    d = run_id_or_dir if isinstance(run_id_or_dir, Path) else run_dir(run_id_or_dir)
    base = Path(d) / "scores"
    if not _store.is_dir(base):
        return []
    return sorted(s for s in _store.iterdir(base) if _store.is_file(s / METRICS))


def scored(
    dataset_id: str | None = None,
    *,
    label_is: str | None = "",
    system_id: str | None = None,
    match: str | None = None,
) -> list[tuple[Path, dict[str, Any]]]:
    """Every score with its record, by run id then key: optionally on one dataset, read under one label (`""`: the
    arm a plain run's first score is read in; None: any), of one system or of systems whose id contains `match`."""
    out = []
    for rid in run_ids():
        for sd in scores_of(rid):
            rec = record(sd)
            if rec is None or not rec.get("config_id"):
                continue
            if dataset_id is not None and rec.get("dataset_id") != dataset_id:
                continue
            if system_id is not None and rec.get("config_id") != system_id:
                continue
            if match and match not in str(rec["config_id"]):
                continue
            if label_is is not None and label(sd, rec) != label_is:
                continue
            out.append((sd, rec))
    return out


def labels() -> list[str]:
    """Every label a score is read under, "" (plain runs) first."""
    seen = {label(sd, rec) for sd, rec in scored(label_is=None)}
    return sorted(seen, key=lambda x: (x != "", x))


def first_score(run_id_or_dir: str | Path) -> Path | None:
    """The score a run made when it ran (its score.json says `first`), else None."""
    for sd in scores_of(run_id_or_dir):
        if meta(sd).get("first"):
            return sd
    return None


def split(rec: dict[str, Any], run_rec: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    """A scored run's record as the score keeps it beside its run's run.json: the keys whose value differs from the
    run's, and the run's keys the record does not hold (the score unsets them)."""
    base = {k: v for k, v in (run_rec or {}).items() if k not in RUN_ONLY}
    own = {k: v for k, v in rec.items() if k not in base or base[k] != v}
    unset = sorted(k for k in base if k not in rec)
    return own, unset


def run_part(rec: dict[str, Any]) -> dict[str, Any]:
    """Of a measured run's record, what the pass itself is (the record less what its score measured)."""
    return {k: v for k, v in rec.items() if k not in SCORE_KEYS}


def write_score(
    run_id: str,
    scorer: str,
    reference: str | None,
    rec: dict[str, Any],
    *,
    label_as: str = "",
    first: bool = False,
    scratch: bool = False,
) -> Path:
    """Write a score of a run from its full record (as `record` reads it back): score.json and metrics.json. The
    rows are the caller's to write in the returned directory (`_outputs`). Returns the score's directory."""
    run_rec = run(run_dir(run_id, scratch))
    if run_rec is None:
        raise ValueError(f"no run {run_id!r} to score")
    own, unset = split(rec, run_rec)
    sd = run_dir(run_id, scratch) / "scores" / key(scorer, reference)
    _store.mkdir(sd, parents=True, exist_ok=True)
    m: dict[str, Any] = {"scorer": scorer, "reference": reference, "label": label_as}
    if first:
        m["first"] = True
    if unset:
        m["unset"] = unset
    _store.write_text(sd / SCORE, json.dumps(m, indent=2, ensure_ascii=False) + "\n")
    _store.write_text(sd / METRICS, json.dumps(own, indent=2, ensure_ascii=False) + "\n")
    return sd


def write_run(run_id: str, rec: dict[str, Any], scratch: bool = False) -> Path:
    """Write a run's run.json; returns the run's directory."""
    if rec.get("purpose", "run") not in PURPOSES:
        raise ValueError(f"a run's purpose is one of {', '.join(PURPOSES)}, not {rec.get('purpose')!r}")
    d = run_dir(run_id, scratch)
    _store.mkdir(d, parents=True, exist_ok=True)
    _store.write_text(d / RUN, json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    return d


def iter_records() -> Iterator[tuple[Path, dict[str, Any]]]:
    """Every score with its record, any label (for checks that read them all)."""
    yield from scored(label_is=None)
