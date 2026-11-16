#!/usr/bin/env python3
"""A deployment's copy of a project's data: what the catalog reads, and nothing it must not publish.

    python harness/scripts/_release.py copy-data harness/data <release>/inspector/data --store files|sqlite
    EVAL_HOME=<release>/inspector python harness/scripts/_release.py check <release>/inspector <tracked-refs-file>

Copies data/runs whole (each run with its scores) and the data the catalog and the inspector read (COPIED_DIRS,
COPIED_FILES), and refuses, before anything is written, a release that would carry text the
repository does not publish:
  - reference texts git does not track (a gold reference is not committed; a working copy may have
    fetched it), and run outputs git does not track (an outputs.jsonl, or the project.sqlite holding a shown run's);
    in the database, where no git says so, the texts of a reference whose manifest says they are not redistributed;
  - for a dataset marked `text: hidden` (RFC-019 §4): its arms' outputs and their predictions'
    `_meta` beyond the call (CALL_META), its references' texts (their manifests stay), the judge verdicts on it, its
    profile's text, labels and links, and its items' source URLs and text and URL field values; of a study run or
    confirmed on it, the prose of its spec and log (the instructions, hypotheses and rationales may quote the items
    shown); of a faithfulness record of a replay on it, what production and the replay answered and the named
    exceptions' causes (the item, its kind and who named it stay).
A hidden dataset's run.json is copied whole, so one whose `call` holds more than the run settings (RUN_SETTINGS) is
refused with the rest.
With the sqlite store (RFC-025) the copy's project.sqlite is the project's without a hidden dataset's runs, rebuilt so
their texts are in none of its pages. Captures are copied as their capture.json only: records never leave the project. Materialized items
are never copied. Judge validations are copied as their reports and their records without the judges' replies.
The copy is files; with `--store sqlite` it is then made one database (data/project.sqlite, moved by `data-migrate`).
The release's config.yaml names its store either way (a project with none is refused). With sqlite a release never changes, so the database is sealed (checkpointed,
out of write-ahead logging, written again whole at 16 KiB pages) and holds the only file under data/, which every reader opens read-only (`_store.readonly`).
`check` is render.sh's last word on a rendered release, read through the release's own store: no reference text git
does not track, no materialized item, the goals' tests kept, and a
sealed database (16 KiB pages) holding the only file.
render.sh calls this; the hidden-text test calls it directly.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import contextlib
import hashlib
import json
import os
import subprocess
from pathlib import Path

import yaml
from evaluation_harness import _common, _outputs, _release_store, _store
from evaluation_harness._visibility import hidden, public_profile
from evaluation_harness.model import studies as model_studies
from evaluation_harness.model.results import CALL_META, RUN_SETTINGS

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
    "judge-validation",
    "profiles",
    "fields",
    "captures",
    "models",
    "labels",
    "tags",
    "failure-modes",
    "exposure",
    "studies",
    "faithfulness",
)
#: The data's format (RFC-032): the deploy checks it; the systems a migration renamed: the catalog redirects them.
COPIED_FILES: tuple[str, ...] = ("project.yaml", "renames.json")


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
        is_hidden = hidden(_dataset_of_run(run), src / "datasets")
        if _store.is_file(f) and not is_hidden and str(f.relative_to(src)) not in tracked:
            bad.append(f"run output git does not track: {f.relative_to(src)}")
        if is_hidden:
            # run.json is copied whole, so its `call` is published as it stands: the run settings, nothing else
            call = json.loads(_store.read_text(run / "run.json", encoding="utf-8")).get("call")
            extra = sorted(k for k in call if k not in RUN_SETTINGS) if isinstance(call, dict) else []
            if call is not None and not isinstance(call, dict):
                extra = ["(not an object)"]
            if extra:
                bad.append(
                    f"hidden run's run.json call holds {', '.join(extra)}, not just the run settings: "
                    f"{(run / 'run.json').relative_to(src)}"
                )
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


#: What a person or an agent wrote about a study's trials, which may quote the items it was shown.
_STUDY_PROSE = ("hypothesis", "rationale", "instruction")


def _study_spec_public(text: str) -> str:
    """A hidden dataset's study spec: its instructions to an agent (what it was told about the items) and note gone."""
    doc = yaml.safe_load(text)
    if isinstance(doc, dict):
        doc = {k: HIDDEN_WHAT if k in ("directions", "note") else v for k, v in doc.items()}
    return yaml.safe_dump(doc, sort_keys=False)


def _study_log_public(text: str) -> str:
    """A hidden dataset's study log: the prose of each line (its hypothesis, rationale, instruction) a mark; the ids,
    numbers and reasons the log decides by stay."""
    out = []
    for line in text.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict):
            ev = {k: HIDDEN_WHAT if k in _STUDY_PROSE and v else v for k, v in ev.items()}
            out.append(json.dumps(ev, sort_keys=True))
    return "".join(x + "\n" for x in out)


def _faithfulness_record_public(doc: dict) -> dict:
    """A hidden dataset's faithfulness record: each disagreement keeps its item, kind and commit; what production and
    the replay answered, and the error text, are gone."""
    return {
        **doc,
        "disagreements": [
            {**d, "production": None, "replay": None, **({"error": HIDDEN_WHAT} if d.get("error") else {})}
            for d in doc.get("disagreements") or []
        ],
    }


def _faithfulness_exceptions_public(text: str) -> str:
    """A hidden dataset's named exceptions: who named which item and when stay; the cause is a person's words about the
    item, a mark."""
    out = []
    for line in text.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict):
            out.append(json.dumps({**ev, "cause": HIDDEN_WHAT}, sort_keys=True))
    return "".join(x + "\n" for x in out)


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
    counts = {
        "hidden_runs": 0,
        "hidden_refs": 0,
        "hidden_verdicts": 0,
        "hidden_studies": 0,
        "hidden_faithfulness": 0,
    }
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
                at = dst / held.relative_to(src)
                got = st.rows(held)
                if got is not None:
                    files.put_rows(at, got)
                text = st.rows_text(held, partial=True)
                if text is not None:
                    files.put_partial(at, text)
    for hidden_run in sorted(hidden_runs):
        out = dst / Path(hidden_run).relative_to(src.resolve())
        counts["hidden_runs"] += 1
        for held in (out, *_score_dirs(out)):
            got = files.rows(held)
            if got is not None:
                files.put_rows(held, [_call_only(r) for r in got])
            text = files.rows_text(held, partial=True)
            if text is not None:
                files.put_partial(held, "".join(_call_only_line(x) for x in text.splitlines() if x.strip()))
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
        elif name == "judge-validation":
            # The people's checks of a scorer's judges: each source's report whole, each record without the judge's
            # reply (its hash stays, as a withheld reply's does): the scorer's page counts them, never quotes them.
            for f in sorted(_store.glob(d, "*/*/report.json")) + sorted(_store.glob(d, "*/*/*/*.json")):
                out = dst / name / f.relative_to(d)
                _store.mkdir(out.parent, parents=True, exist_ok=True)
                if f.name == "report.json":
                    _store.copy_file(f, out)
                    continue
                rec = json.loads(_store.read_text(f, encoding="utf-8"))
                if "output" in rec:
                    said = rec.pop("output") or ""
                    rec.setdefault("output_sha256", hashlib.sha256(said.encode()).hexdigest())
                    rec["output_withheld"] = True
                _store.write_text(out, json.dumps(rec, indent=1) + "\n", encoding="utf-8")
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
        elif name == "studies":
            # A study's files whole (its trials' systems and confirmations hold ids, settings and counts); a hidden
            # dataset's study spec and log without the prose that may quote the items shown.
            for f in sorted(_store.rglob(d, "*")):
                if not _store.is_file(f):
                    continue
                rel = f.relative_to(d)
                out = dst / name / rel
                _store.mkdir(out.parent, parents=True, exist_ok=True)
                sid = (
                    f.name.removesuffix(".yaml").removesuffix(".events.jsonl")
                    if len(rel.parts) == 2
                    else None
                )
                if sid and model_studies.hidden(rel.parts[0], sid, src):
                    text = _store.read_text(f, encoding="utf-8")
                    if f.suffix == ".yaml":
                        counts["hidden_studies"] += 1
                        _store.write_text(out, _study_spec_public(text), encoding="utf-8")
                    else:
                        _store.write_text(out, _study_log_public(text), encoding="utf-8")
                else:
                    _store.copy_file(f, out)
        elif name == "faithfulness":
            # A replay's disagreements quote what production and the replay answered on an item: a hidden dataset's
            # records keep the item and its kind; its named exceptions keep who and when.
            for f in sorted(_store.rglob(d, "*")):
                if not _store.is_file(f):
                    continue
                out = dst / name / f.relative_to(d)
                _store.mkdir(out.parent, parents=True, exist_ok=True)
                record = f.with_name(f.name.split(".", 1)[0] + ".json")
                ds = None
                if _store.is_file(record):
                    with contextlib.suppress(ValueError, AttributeError):
                        ds = json.loads(_store.read_text(record, encoding="utf-8")).get("dataset_id")
                if f.suffix not in (".json", ".jsonl") or not hidden(ds, datasets):
                    _store.copy_file(f, out)
                elif f.suffix == ".json":
                    counts["hidden_faithfulness"] += 1
                    doc = json.loads(_store.read_text(f, encoding="utf-8"))
                    _store.write_text(
                        out,
                        json.dumps(_faithfulness_record_public(doc), indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                else:
                    _store.write_text(
                        out,
                        _faithfulness_exceptions_public(_store.read_text(f, encoding="utf-8")),
                        encoding="utf-8",
                    )
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


def check(root: Path, tracked: set[str]) -> list[str]:
    """What is wrong with a rendered release (the project at `root`, EVAL_HOME of this process), read through its
    own store, never by looking at files a database release does not have; [] when nothing. `tracked` is what git
    tracks under harness/data, relative to it: a reference text outside it is not public."""
    if _common.project_root().resolve() != root.resolve():
        _common.die(f"{root} is not this process's project: run it with EVAL_HOME={root}", "bad-argument")
    data = _common.DATA
    bad = []
    refs = _store.rglob(data / "references", "*") if _store.is_dir(data / "references") else []
    leaked = sorted(
        str(f.relative_to(data))
        for f in refs
        if _store.is_file(f) and f.name != "manifest.json" and str(f.relative_to(data)) not in tracked
    )
    if leaked:
        bad.append(
            f"{len(leaked)} reference text(s) git does not track in the release (not public), e.g.: "
            + ", ".join(leaked[:3])
        )
    if _store.exists(data / "materialized"):
        bad.append("materialized items in the release")
    cache = root / "cache"
    if not _store.is_file(cache / "evh-p.jsonl") or not _store.stat(cache / "evh-p.jsonl").st_size:
        bad.append(
            "the p cache (inspector/cache/evh-p.jsonl) is missing or empty: each MCP view takes ~50 s without it"
        )
    return bad + _release_store.layout_problems(data)


def main() -> int:
    """copy-data SRC DST --store files|sqlite; check ROOT TRACKED."""
    ap = argparse.ArgumentParser(prog="_release.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    cp = sub.add_parser("copy-data", help="a project's data/ into a release")
    cp.add_argument("src")
    cp.add_argument("dst")
    cp.add_argument("--store", choices=_common.STORES, required=True, help="the store the release is in")
    ck = sub.add_parser("check", help="a rendered release's last checks")
    ck.add_argument("root", help="the release's project (EVAL_HOME): its data/, config.yaml and cache/")
    ck.add_argument(
        "tracked", help="a file of the paths git tracks under harness/data/references, one a line"
    )
    args = ap.parse_args()
    if args.cmd == "check":
        os.environ.pop("EVAL_STORE", None)  # the release says which store it is (its config.yaml)
        os.environ["EVAL_STORE_READONLY"] = "1"  # checking changes nothing in what it checks
        tracked = {x for x in _store.read_text(Path(args.tracked), encoding="utf-8").splitlines() if x}
        problems = check(Path(args.root), tracked)
        for p in problems:
            print(f"::error::{p}")
        return 1 if problems else 0
    counts = copy_data(Path(args.src), Path(args.dst))
    if args.store == "sqlite":
        _release_store.to_sqlite(Path(args.dst))
    else:
        _release_store.name_store(Path(args.dst), args.store)
    print(
        f"copied {args.src} -> {args.dst} ({args.store})"
        + (
            f" (text kept back for hidden datasets: {counts['hidden_runs']} run(s), "
            f"{counts['hidden_refs']} reference(s), {counts['hidden_verdicts']} verdict set(s), "
            f"{counts['hidden_studies']} study(ies), {counts['hidden_faithfulness']} faithfulness record(s))"
            if any(counts.values())
            else ""
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
