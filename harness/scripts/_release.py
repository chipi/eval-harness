#!/usr/bin/env python3
"""A deployment's copy of a project's data: what the catalog reads, and nothing it must not publish.

    python harness/scripts/_release.py copy-data harness/data <release>/inspector/data

Copies data/runs whole (each run with its scores) and the data the catalog and the inspector read (COPIED_DIRS,
COPIED_FILES), and refuses, before anything is written, a release that would carry text the
repository does not publish:
  - reference texts git does not track (a gold reference is not committed; a working copy may have
    fetched it), and run outputs git does not track (an outputs.jsonl, or the project.sqlite holding a shown run's);
    in the database, where no git says so, the texts of a reference whose manifest says they are not redistributed;
  - for a dataset marked `text: hidden` (RFC-019 §4): its arms' outputs and their predictions'
    `_meta` beyond the call (CALL_META), its references' texts (their manifests stay), the judge verdicts on it, its
    profile's text, labels and links, and its items' source URLs and text and URL field values.
With the sqlite store (RFC-025) the copy's project.sqlite is the project's without a hidden dataset's runs, rebuilt so
their texts are in none of its pages. Captures are copied as their capture.json only: records never leave the project. Materialized items
are never copied. render.sh calls this; the hidden-text test calls it directly.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import json
import subprocess
from pathlib import Path

import yaml
from evaluation_harness import _common, _outputs, _store
from evaluation_harness._visibility import hidden, public_profile

#: The directories of data/ the catalog and the inspector read (tests/test_render_data.py checks it
#: against catalog_adapter.py), copied besides data/runs.
#: An exposure row's `what` on a hidden dataset, in the deployment's copy.
HIDDEN_WHAT = "(not published: the dataset's text is hidden)"
COPIED_DIRS = (
    "references",
    "datasets",
    "goals",
    "baselines",
    "rounds",
    "systems",
    "scorers",
    "judging-sets",
    "judge-verdicts",
    "judge-summaries",
    "profiles",
    "fields",
    "captures",
    "models",
    "labels",
    "tags",
    "failure-modes",
    "exposure",
)
#: The data's format (RFC-032): the deploy checks it; the systems a migration renamed: the catalog redirects them.
COPIED_FILES: tuple[str, ...] = ("project.yaml", "renames.json")
#: What a hidden dataset's prediction rows keep of `_meta`: what describes the call (its cost, model,
#: finish), never what the system answered or the parser made of it (`predicted`, `llm_raw`, ...).
CALL_META = (
    "provider",
    "response_model",
    "usage",
    "finish_reason",
    "reasoning_tokens_reported",
    "system_fingerprint",
    "generation_config",
    "generation_requested",
    "encoder_window",
    "resumed_from_disk",
)


def _tracked(src: Path) -> set[str] | None:
    """The files git tracks under `src`, relative to it; None when it is not in a git checkout. With the sqlite
    store (RFC-025) the files the database holds: it is the record git is for files."""
    if _common.store() == "sqlite":
        return {str(Path(p).relative_to(src)) for p in _store.rglob(src, "*") if _store.is_file(p)}
    try:
        top = subprocess.run(
            ["git", "-C", str(src), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        out = subprocess.run(
            ["git", "-C", top, "ls-files", "-z", "--", str(src.resolve().relative_to(Path(top).resolve()))],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None
    rel = src.resolve().relative_to(Path(top).resolve())
    return {str(Path(p).relative_to(rel)) for p in out.split("\0") if p}


def _dataset_of_run(run: Path) -> str | None:
    m = run / "run.json"
    try:
        return (
            json.loads(_store.read_text(m, encoding="utf-8")).get("dataset_id") if _store.is_file(m) else None
        )
    except ValueError:
        return None


def _field_types(src: Path, fieldset_id: str | None) -> dict:
    f = src / "fields" / f"{fieldset_id}.yaml"
    if not fieldset_id or not _store.is_file(f):
        return {}
    doc = yaml.safe_load(_store.read_text(f, encoding="utf-8")) or {}
    return {x["name"]: x.get("type") for x in doc.get("fields") or []}


def plan_problems(src: Path) -> list[str]:
    """What would make the copy publish text the repository does not: untracked reference texts and
    run outputs (of datasets whose text is shown; a hidden dataset's are never copied)."""
    tracked = _tracked(src)
    if tracked is None:
        return [f"{src} is not in a git checkout: what the repository publishes cannot be told"]
    bad = []
    in_db = _common.store() == "sqlite"
    for f in sorted(_store.glob(src / "references", "*/*/*")) if _store.is_dir(src / "references") else []:
        if _store.is_file(f) and f.name != "manifest.json":
            ds = _manifest_dataset(f.parent)
            if hidden(ds, src / "datasets"):
                continue
            why = _not_redistributed(f.parent) if in_db else None
            if why:
                # no git in the database to keep these out: the manifest's word is what says so (their licence)
                bad.append(f"reference text {why}: {f.relative_to(src)}")
            elif str(f.relative_to(src)) not in tracked:
                bad.append(f"reference text git does not track: {f.relative_to(src)}")
    for run in _run_dirs(src):
        f = run / _outputs.FILE
        if (
            _store.is_file(f)
            and not hidden(_dataset_of_run(run), src / "datasets")
            and str(f.relative_to(src)) not in tracked
        ):
            bad.append(f"run output git does not track: {f.relative_to(src)}")
    return bad


def _not_redistributed(ref_dir: Path) -> str | None:
    """Why a reference set's texts may not be published, or None: its manifest says they are not redistributed
    (reference-manifest --not-redistributed, a promotion of such labels), or the manifest cannot say (missing, not
    JSON, `redistributed` not true or false). In the database nothing else keeps them out, so what cannot be read
    is refused, never published."""
    m = ref_dir / "manifest.json"
    if not _store.is_file(m):
        return "with no manifest to say it may be published"
    try:
        doc = json.loads(_store.read_text(m, encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        return "whose manifest cannot be read"
    if not isinstance(doc, dict):
        return "whose manifest cannot be read"
    r = doc.get("redistributed", True)
    if r is False:
        return "not redistributed (its manifest)"
    if r is not True:
        return f"whose manifest's redistributed is {r!r}, not true or false"
    return None


def _run_dirs(src: Path) -> list[Path]:
    """Every run directory, data/runs/<run>. Whether a run's text is hidden is its own dataset's, so it is decided
    per run."""
    base = src / "runs"
    return (
        sorted(d for d in _store.iterdir(base) if _store.is_file(d / "run.json"))
        if _store.is_dir(base)
        else []
    )


def _score_dirs(run: Path) -> list[Path]:
    """A run's score directories, runs/<run>/scores/<key>: where its rows are."""
    base = run / "scores"
    return sorted(d for d in _store.iterdir(base) if _store.is_dir(d)) if _store.is_dir(base) else []


def _hidden_key(src: Path, key: str) -> bool:
    """Whether a runs-database run (its directory under data/) is of a hidden dataset."""
    d = Path(key) if Path(key).is_absolute() else src / key
    return hidden(_dataset_of_run(d), src / "datasets")


def _manifest_dataset(ref_dir: Path) -> str | None:
    m = ref_dir / "manifest.json"
    try:
        return (
            json.loads(_store.read_text(m, encoding="utf-8")).get("dataset_id")
            if _store.is_file(m)
            else ref_dir.name
        )
    except ValueError:
        return ref_dir.name


def _call_only(row: dict) -> dict:
    """A hidden dataset's prediction row: its scores and the call's description; `_extra` (the
    adapter's numbers) kept, `_meta` cut to CALL_META, every other `_` key gone."""
    out = {k: v for k, v in row.items() if not k.startswith("_") or k == "_extra"}
    if isinstance(row.get("_meta"), dict):
        out["_meta"] = {k: v for k, v in row["_meta"].items() if k in CALL_META}
    return out


def _call_only_line(line: str) -> str:
    """One row line of a hidden dataset's run, cut to _call_only; a line that is not a row is dropped."""
    try:
        row = json.loads(line)
    except ValueError:
        return ""
    return json.dumps(_call_only(row)) + "\n" if isinstance(row, dict) else ""


def copy_data(src: Path, dst: Path) -> dict:
    """Copy `src` (a project's data/) into `dst`; refuse first if it would publish untracked text."""
    bad = plan_problems(src)
    if bad:
        from evaluation_harness._common import die  # noqa: PLC0415

        die(
            "refusing the release:\n  "
            + "\n  ".join(bad[:10])
            + (f"\n  (+{len(bad) - 10})" if len(bad) > 10 else ""),
            "not-allowed",
        )
    _store.mkdir(dst, parents=True, exist_ok=True)
    datasets = src / "datasets"
    counts = {"hidden_runs": 0, "hidden_refs": 0, "hidden_verdicts": 0}
    hidden_runs = {str(d.resolve()) for d in _run_dirs(src) if hidden(_dataset_of_run(d), datasets)}

    # Every file of every run, a hidden dataset's run without its outputs; read through the store, so a project in its
    # database (RFC-025) is released as the same files layout as a project in files.
    for base in [src / "runs"] if _store.is_dir(src / "runs") else []:
        for f in sorted(_store.rglob(base, "*")):
            if not _store.is_file(f):
                continue
            run_of = next((r for r in (f.parent, f.parent.parent) if str(r.resolve()) in hidden_runs), None)
            if run_of is not None and (f.name == _outputs.FILE or f.parent.name == _outputs.OLD_DIR):
                continue
            out = dst / f.relative_to(src)
            _store.mkdir(out.parent, parents=True, exist_ok=True)
            _store.copy_file(f, out)
    files = _outputs.store_named("files")  # the copy is files, whichever the project's store
    if _common.store() == "sqlite":  # a run's outputs and rows are in the database's per-item tables
        st = _outputs.store()
        for run in _run_dirs(src):
            out = dst / run.relative_to(src)
            outs = st.lines(run)
            if outs and str(run.resolve()) not in hidden_runs:
                files.write_all(out, {o["item_id"]: o["text"] for o in outs}, [o["item_id"] for o in outs])
            for held in (
                run,
                *_score_dirs(run),
            ):  # the pass's checkpoint is the run's, a score's rows its own
                for partial in (False, True):
                    text = st.rows_text(held, partial)
                    if text is not None:
                        files.put_rows(dst / held.relative_to(src), text, partial)
    for hidden_run in sorted(hidden_runs):
        out = dst / Path(hidden_run).relative_to(src.resolve())
        counts["hidden_runs"] += 1
        for held in (out, *_score_dirs(out)):
            for partial in (False, True):
                text = files.rows_text(held, partial)
                if text is not None:
                    files.put_rows(
                        held, "".join(_call_only_line(x) for x in text.splitlines() if x.strip()), partial
                    )
    for name in COPIED_DIRS:
        d = src / name
        if not _store.is_dir(d):
            continue
        if name == "references":
            for f in sorted(p for p in _store.iterdir(d) if _store.is_file(p)):
                _store.mkdir(dst / name, parents=True, exist_ok=True)
                _store.copy_file(f, dst / name / f.name)
            for ref in sorted(p for p in _store.glob(d, "*/*") if _store.is_dir(p)):
                out = dst / name / ref.relative_to(d)
                if hidden(_manifest_dataset(ref), datasets):
                    counts["hidden_refs"] += 1
                    _store.mkdir(out, parents=True, exist_ok=True)
                    if _store.is_file(ref / "manifest.json"):
                        _store.copy_file(ref / "manifest.json", out / "manifest.json")
                else:
                    _store.copy_tree(ref, out)
        elif name == "judge-verdicts":
            for vdir in sorted(p for p in _store.glob(d, "*/*") if _store.is_dir(p)):
                js = src / "judging-sets" / f"{vdir.name}.json"
                ds = (
                    json.loads(_store.read_text(js, encoding="utf-8")).get("dataset_id")
                    if _store.is_file(js)
                    else None
                )
                if hidden(ds, datasets):
                    counts["hidden_verdicts"] += 1
                    continue
                _store.copy_tree(vdir, dst / name / vdir.relative_to(d))
        elif name == "labels":
            # As captures: the record (source, counts, hashes: what the catalog reads), never a label's text.
            for rec in sorted(_store.glob(d, "*/*/labels.json")):
                out = dst / name / rec.parent.relative_to(d)
                _store.mkdir(out, parents=True, exist_ok=True)
                doc = json.loads(_store.read_text(rec, encoding="utf-8"))
                if "notes" in doc and hidden(doc.get("dataset_id"), datasets):
                    # A person's notes on a hidden dataset's items are its text (RFC-019 §4, adjudication notes).
                    doc.pop("notes")
                    _store.write_text(out / "labels.json", json.dumps(doc, indent=1) + "\n", encoding="utf-8")
                else:
                    _store.copy_file(rec, out / "labels.json")
        elif name == "tags":
            # The modes counted on the goal page; a person's note on a hidden dataset's output is its text: dropped.
            for rec in sorted(_store.glob(d, "*/*/tags.json")):
                out = dst / name / rec.parent.relative_to(d)
                _store.mkdir(out, parents=True, exist_ok=True)
                doc = json.loads(_store.read_text(rec, encoding="utf-8"))
                if hidden(doc.get("dataset_id"), datasets):
                    for by_item in (doc.get("runs") or {}).values():
                        for t in by_item.values():
                            t.pop("note", None)
                    _store.write_text(out / "tags.json", json.dumps(doc, indent=1) + "\n", encoding="utf-8")
                else:
                    _store.copy_file(rec, out / "tags.json")
        elif name == "exposure":
            # Which items were read and by whom; what a person wrote of a hidden dataset's item may be its text: kept
            # as a mark (the register's rows name what was read).
            _store.mkdir(dst / name, parents=True, exist_ok=True)
            for f in sorted(_store.glob(d, "*.jsonl")):
                if hidden(f.stem, datasets):
                    rows = [
                        json.loads(x) for x in _store.read_text(f, encoding="utf-8").splitlines() if x.strip()
                    ]
                    text = "".join(json.dumps({**r, "what": HIDDEN_WHAT}) + "\n" for r in rows)
                    _store.write_text(dst / name / f.name, text, encoding="utf-8")
                else:
                    _store.copy_file(f, dst / name / f.name)
        elif name == "captures":
            for cap in sorted(_store.glob(d, "*/capture.json")):
                _store.mkdir(dst / name / cap.parent.name, parents=True, exist_ok=True)
                _store.copy_file(cap, dst / name / cap.parent.name / "capture.json")
        elif name == "profiles":
            _store.mkdir(dst / name, parents=True, exist_ok=True)
            for f in sorted(_store.glob(d, "*")):
                if f.suffix == ".json" and hidden(f.stem, datasets):
                    p = json.loads(_store.read_text(f, encoding="utf-8"))
                    _store.write_text(
                        dst / name / f.name, json.dumps(public_profile(p), indent=1) + "\n", encoding="utf-8"
                    )
                elif _store.is_file(f):
                    _store.copy_file(f, dst / name / f.name)
        elif name == "datasets":
            _store.mkdir(dst / name, parents=True, exist_ok=True)
            for f in sorted(_store.glob(d, "*")):
                if f.suffix == ".json" and hidden(f.stem, datasets):
                    doc = json.loads(_store.read_text(f, encoding="utf-8"))
                    types = _field_types(src, doc.get("fieldset"))
                    for it in doc.get("items") or []:
                        it.pop("source_url", None)
                        if it.get("fields"):
                            it["fields"] = {
                                k: v for k, v in it["fields"].items() if types.get(k) not in ("text", "url")
                            }
                    _store.write_text(
                        dst / name / f.name,
                        json.dumps(doc, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                elif _store.is_file(f):
                    _store.copy_file(f, dst / name / f.name)
        else:
            _store.copy_tree(d, dst / name)
    for name in COPIED_FILES:
        if _store.is_file(src / name):
            _store.copy_file(src / name, dst / name)
    return counts


def main() -> int:
    """copy-data SRC DST."""
    if len(_sys.argv) != 4 or _sys.argv[1] != "copy-data":
        print(__doc__)
        return 2
    counts = copy_data(Path(_sys.argv[2]), Path(_sys.argv[3]))
    print(
        f"copied {_sys.argv[2]} -> {_sys.argv[3]}"
        + (
            f" (text kept back for hidden datasets: {counts['hidden_runs']} run(s), "
            f"{counts['hidden_refs']} reference(s), {counts['hidden_verdicts']} verdict set(s))"
            if any(counts.values())
            else ""
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
