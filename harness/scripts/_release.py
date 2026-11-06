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
import shutil
import subprocess
from pathlib import Path

import yaml
from evaluation_harness import _outputs
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
    """The files git tracks under `src`, relative to it; None when it is not in a git checkout."""
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
        return json.loads(m.read_text(encoding="utf-8")).get("dataset_id") if m.is_file() else None
    except ValueError:
        return None


def _field_types(src: Path, fieldset_id: str | None) -> dict:
    f = src / "fields" / f"{fieldset_id}.yaml"
    if not fieldset_id or not f.is_file():
        return {}
    doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    return {x["name"]: x.get("type") for x in doc.get("fields") or []}


def plan_problems(src: Path) -> list[str]:
    """What would make the copy publish text the repository does not: untracked reference texts and
    run outputs (of datasets whose text is shown; a hidden dataset's are never copied)."""
    tracked = _tracked(src)
    if tracked is None:
        return [f"{src} is not in a git checkout: what the repository publishes cannot be told"]
    bad = []
    for f in sorted((src / "references").glob("*/*/*")) if (src / "references").is_dir() else []:
        if f.is_file() and f.name != "manifest.json":
            ds = _manifest_dataset(f.parent)
            if not hidden(ds, src / "datasets") and str(f.relative_to(src)) not in tracked:
                bad.append(f"reference text git does not track: {f.relative_to(src)}")
    for run in _run_dirs(src):
        f = run / _outputs.FILE
        if (
            f.is_file()
            and not hidden(_dataset_of_run(run), src / "datasets")
            and str(f.relative_to(src)) not in tracked
        ):
            bad.append(f"run output git does not track: {f.relative_to(src)}")
    shown = [k for k in _outputs.db_runs(src / _outputs.DB) if not _hidden_key(src, k)]
    if shown and _outputs.DB not in tracked:
        bad.append(
            f"run outputs git does not track: {_outputs.DB} holds {len(shown)} shown run(s)' outputs"
            " (a release publishes only what the repository commits)"
        )
    return bad


def _run_dirs(src: Path) -> list[Path]:
    """Every run directory under data/runs*, at the depth it sits: data/runs/<run>, data/runs-judged/<scorer>/<run>,
    data/runs-rescored/<scorer>/<source>/<run>. Whether a run's text is hidden is its own dataset's, so it is decided
    per run, never for the folder that holds it."""
    return sorted(
        {
            d
            for base in src.glob("runs*")
            if base.is_dir()
            for depth in ("*", "*/*", "*/*/*")
            for d in base.glob(depth)
            if d.is_dir() and (d / "metrics.json").is_file()
        }
    )


def _hidden_key(src: Path, key: str) -> bool:
    """Whether a runs-database run (its directory under data/) is of a hidden dataset."""
    d = Path(key) if Path(key).is_absolute() else src / key
    return hidden(_dataset_of_run(d), src / "datasets")


def _manifest_dataset(ref_dir: Path) -> str | None:
    m = ref_dir / "manifest.json"
    try:
        return json.loads(m.read_text(encoding="utf-8")).get("dataset_id") if m.is_file() else ref_dir.name
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
    dst.mkdir(parents=True, exist_ok=True)
    datasets = src / "datasets"
    counts = {"hidden_runs": 0, "hidden_refs": 0, "hidden_verdicts": 0}
    hidden_runs = {str(d.resolve()) for d in _run_dirs(src) if hidden(_dataset_of_run(d), datasets)}

    def leave_out(folder: str, names: list[str]) -> set[str]:
        """A hidden dataset's run is copied without its outputs."""
        return (
            {"outputs", _outputs.FILE} & set(names) if str(Path(folder).resolve()) in hidden_runs else set()
        )

    for base in sorted(p for p in src.glob("runs*") if p.is_dir()):
        shutil.copytree(base, dst / base.name, ignore=leave_out, dirs_exist_ok=True)
    files = _outputs.store_named("files")  # the copy of a files-store run is files
    for run in sorted(hidden_runs):
        out = dst / Path(run).relative_to(src.resolve())
        counts["hidden_runs"] += 1
        for partial in (False, True):
            text = files.rows_text(out, partial)
            if text is not None:
                files.put_rows(
                    out, "".join(_call_only_line(x) for x in text.splitlines() if x.strip()), partial
                )
    if (src / _outputs.DB).is_file():
        _outputs.db_copy(src / _outputs.DB, dst / _outputs.DB, lambda k: _hidden_key(src, k), _call_only_line)
    for name in COPIED_DIRS:
        d = src / name
        if not d.is_dir():
            continue
        if name == "references":
            for f in sorted(p for p in d.iterdir() if p.is_file()):
                (dst / name).mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst / name / f.name)
            for ref in sorted(p for p in d.glob("*/*") if p.is_dir()):
                out = dst / name / ref.relative_to(d)
                if hidden(_manifest_dataset(ref), datasets):
                    counts["hidden_refs"] += 1
                    out.mkdir(parents=True, exist_ok=True)
                    if (ref / "manifest.json").is_file():
                        shutil.copy2(ref / "manifest.json", out / "manifest.json")
                else:
                    shutil.copytree(ref, out)
        elif name == "judge-verdicts":
            for vdir in sorted(p for p in d.glob("*/*") if p.is_dir()):
                js = src / "judging-sets" / f"{vdir.name}.json"
                ds = json.loads(js.read_text(encoding="utf-8")).get("dataset_id") if js.is_file() else None
                if hidden(ds, datasets):
                    counts["hidden_verdicts"] += 1
                    continue
                shutil.copytree(vdir, dst / name / vdir.relative_to(d))
        elif name == "labels":
            # As captures: the record (source, counts, hashes: what the catalog reads), never a label's text.
            for rec in sorted(d.glob("*/*/labels.json")):
                out = dst / name / rec.parent.relative_to(d)
                out.mkdir(parents=True, exist_ok=True)
                doc = json.loads(rec.read_text(encoding="utf-8"))
                if "notes" in doc and hidden(doc.get("dataset_id"), datasets):
                    # A person's notes on a hidden dataset's items are its text (RFC-019 §4, adjudication notes).
                    doc.pop("notes")
                    (out / "labels.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
                else:
                    shutil.copy2(rec, out / "labels.json")
        elif name == "tags":
            # The modes counted on the goal page; a person's note on a hidden dataset's output is its text: dropped.
            for rec in sorted(d.glob("*/*/tags.json")):
                out = dst / name / rec.parent.relative_to(d)
                out.mkdir(parents=True, exist_ok=True)
                doc = json.loads(rec.read_text(encoding="utf-8"))
                if hidden(doc.get("dataset_id"), datasets):
                    for by_item in (doc.get("runs") or {}).values():
                        for t in by_item.values():
                            t.pop("note", None)
                    (out / "tags.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
                else:
                    shutil.copy2(rec, out / "tags.json")
        elif name == "captures":
            for cap in sorted(d.glob("*/capture.json")):
                (dst / name / cap.parent.name).mkdir(parents=True, exist_ok=True)
                shutil.copy2(cap, dst / name / cap.parent.name / "capture.json")
        elif name == "profiles":
            (dst / name).mkdir(parents=True, exist_ok=True)
            for f in sorted(d.glob("*")):
                if f.suffix == ".json" and hidden(f.stem, datasets):
                    p = json.loads(f.read_text(encoding="utf-8"))
                    (dst / name / f.name).write_text(
                        json.dumps(public_profile(p), indent=1) + "\n", encoding="utf-8"
                    )
                elif f.is_file():
                    shutil.copy2(f, dst / name / f.name)
        elif name == "datasets":
            (dst / name).mkdir(parents=True, exist_ok=True)
            for f in sorted(d.glob("*")):
                if f.suffix == ".json" and hidden(f.stem, datasets):
                    doc = json.loads(f.read_text(encoding="utf-8"))
                    types = _field_types(src, doc.get("fieldset"))
                    for it in doc.get("items") or []:
                        it.pop("source_url", None)
                        if it.get("fields"):
                            it["fields"] = {
                                k: v for k, v in it["fields"].items() if types.get(k) not in ("text", "url")
                            }
                    (dst / name / f.name).write_text(
                        json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                    )
                elif f.is_file():
                    shutil.copy2(f, dst / name / f.name)
        else:
            shutil.copytree(d, dst / name, dirs_exist_ok=True)
    for name in COPIED_FILES:
        if (src / name).is_file():
            shutil.copy2(src / name, dst / name)
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
