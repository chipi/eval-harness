#!/usr/bin/env python3
"""A deployment's copy of a project's data: what the catalog reads, and nothing it must not publish.

    python harness/scripts/_release.py copy-data harness/data <release>/inspector/data

Copies the run directories (runs*) and the data the catalog and the inspector read (COPIED_DIRS,
COPIED_FILES), and refuses, before anything is written, a release that would carry text the
repository does not publish:
  - reference texts git does not track (a gold reference is not committed; a working copy may have
    fetched it), and run outputs git does not track;
  - for a dataset marked `text: hidden` (RFC-019 §4): its arms' outputs and their predictions'
    `_meta` beyond the call (CALL_META), its references' texts (their manifests stay), the judge verdicts on it, its
    profile's text, labels and links, and its items' source URLs and text and URL field values.
Captures are copied as their capture.json only: records never leave the project. Materialized items
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
    for run in sorted(p for base in src.glob("runs*") if base.is_dir() for p in base.iterdir() if p.is_dir()):
        if hidden(_dataset_of_run(run), src / "datasets"):
            continue
        for f in sorted((run / "outputs").glob("*")) if (run / "outputs").is_dir() else []:
            if str(f.relative_to(src)) not in tracked:
                bad.append(f"run output git does not track: {f.relative_to(src)}")
                break  # one per run is enough to name it
    return bad


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


def copy_data(src: Path, dst: Path) -> dict:
    """Copy `src` (a project's data/) into `dst`; refuse first if it would publish untracked text."""
    bad = plan_problems(src)
    if bad:
        raise SystemExit(
            "refusing the release:\n  "
            + "\n  ".join(bad[:10])
            + (f"\n  (+{len(bad) - 10})" if len(bad) > 10 else "")
        )
    dst.mkdir(parents=True, exist_ok=True)
    datasets = src / "datasets"
    counts = {"hidden_runs": 0, "hidden_refs": 0, "hidden_verdicts": 0}
    for base in sorted(p for p in src.glob("runs*") if p.is_dir()):
        for run in sorted(p for p in base.iterdir() if p.is_dir()):
            out = dst / base.name / run.name
            if hidden(_dataset_of_run(run), datasets):
                counts["hidden_runs"] += 1
                shutil.copytree(run, out, ignore=shutil.ignore_patterns("outputs"))
                pred = out / "predictions.jsonl"
                if pred.is_file():
                    rows = [json.loads(x) for x in pred.read_text(encoding="utf-8").splitlines() if x.strip()]
                    pred.write_text("".join(json.dumps(_call_only(r)) + "\n" for r in rows), encoding="utf-8")
            else:
                shutil.copytree(run, out)
        for f in sorted(p for p in base.iterdir() if p.is_file()):
            (dst / base.name).mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst / base.name / f.name)
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
