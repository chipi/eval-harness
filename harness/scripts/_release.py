#!/usr/bin/env python3
"""A deployment's copy of a project's data: what the catalog reads, and nothing it must not publish.

    python harness/scripts/_release.py copy-data harness/data <release>/inspector/data

Copies the run directories (runs*) and the data the catalog and the inspector read (COPIED_DIRS,
COPIED_FILES), and refuses, before anything is written, a release that would carry text the
repository does not publish:
  - reference texts git does not track (a gold reference is not committed; a working copy may have
    fetched it), and run outputs git does not track (an outputs.jsonl, or a runs.sqlite holding a shown run's);
  - for a dataset marked `text: hidden` (RFC-019 §4): its arms' outputs and their predictions'
    `_meta` beyond the call (CALL_META), its references' texts (their manifests stay), the judge verdicts on it, its
    profile's text, labels and links, and its items' source URLs and text and URL field values.
With the sqlite store (RFC-025) the copy's runs.sqlite is the project's without a hidden dataset's runs, rebuilt so
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
#: against catalog_adapter.py), copied besides every runs* directory.
COPIED_DIRS = (
    "references",
    "datasets",
    "goals",
    "baselines",
    "rounds",
    "configs",
    "scorers",
    "judging-sets",
    "judge-verdicts",
    "profiles",
    "fields",
    "captures",
    "models",
    "labels",
    "tags",
    "failure-modes",
)
COPIED_FILES: tuple[str, ...] = ()
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
    m = run / "metrics.json"
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
    for f in sorted(_store.glob(src / "references", "*/*/*")) if _store.is_dir(src / "references") else []:
        if _store.is_file(f) and f.name != "manifest.json":
            ds = _manifest_dataset(f.parent)
            if not hidden(ds, src / "datasets") and str(f.relative_to(src)) not in tracked:
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


def _run_dirs(src: Path) -> list[Path]:
    """Every run directory under data/runs*, at the depth it sits: data/runs/<run>, data/runs-judged/<scorer>/<run>,
    data/runs-rescored/<scorer>/<source>/<run>. Whether a run's text is hidden is its own dataset's, so it is decided
    per run, never for the folder that holds it."""
    return sorted(
        {
            d
            for base in _store.glob(src, "runs*")
            if _store.is_dir(base)
            for depth in ("*", "*/*", "*/*/*")
            for d in _store.glob(base, depth)
            if _store.is_dir(d) and _store.is_file(d / "metrics.json")
        }
    )


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

    # Every file of every runs folder, a hidden dataset's run without its outputs; read through the store, so a
    # project in its database (RFC-025) is released as the same files layout as a project in files.
    for base in sorted(p for p in _store.glob(src, "runs*") if _store.is_dir(p)):
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
            for partial in (False, True):
                text = st.rows_text(run, partial)
                if text is not None:
                    files.put_rows(out, text, partial)
    for hidden_run in sorted(hidden_runs):
        out = dst / Path(hidden_run).relative_to(src.resolve())
        counts["hidden_runs"] += 1
        for partial in (False, True):
            text = files.rows_text(out, partial)
            if text is not None:
                files.put_rows(
                    out, "".join(_call_only_line(x) for x in text.splitlines() if x.strip()), partial
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
