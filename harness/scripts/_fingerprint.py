"""What a number depended on, captured so "we varied one thing" can be checked.

An eval measures three things — the SYSTEM UNDER TEST, the INSTRUMENT (the adapter: its
`call_system` and its `score`) and the DATA (dataset + reference). A number is only
interpretable if all three are identified, and a COMPARISON is only valid if exactly one
of them moved. Without a fingerprint that is an assertion; with one it is checkable.

STDLIB ONLY, deliberately. This module must never import torch, transformers,
scikit-learn or any provider SDK. Someone evaluating a pure-LLM system, or a regex
baseline, should never install an ML framework to use this harness — the experiment
brings its own weight, and the core only knows how to ASK.

Which is why the model half is inverted: the core defines a VOCABULARY, not a mechanism.
An adapter may expose

    def fingerprint(params) -> dict

and return whatever identifies ITS system, in this shape:

    {"id": ..., "revision": ..., "revision_source": ..., "device": ..., "precision": ...}

`revision_source` is never parsed here — it exists for whoever reads the run later, and
says HOW the revision was determined: "hf-snapshot", "ollama-digest", "gguf-sha256",
"sklearn-artifact", "api-model-string". A HuggingFace cache layout is a HuggingFace
concept and has no business in this file.

A missing revision is recorded as missing. The core does not invent one — two runs of
"the same model" that cannot prove they used the same weights should say so rather than
imply a reproducibility they do not have.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Callable

#: Reported when installed, WITHOUT importing them. importlib.metadata reads distribution
#: metadata off disk, so the core can say "torch 2.2.2" while having no torch dependency
#: and never loading it into the process. That distinction is the whole point of this file.
_WATCHED_DISTRIBUTIONS = (
    "torch",
    "transformers",
    "scikit-learn",
    "sentence-transformers",
    "numpy",
    "openai",
    "anthropic",
    "datasets",
    "rouge-score",
)


def _installed_versions() -> dict[str, str]:
    """Versions of anything watched that is installed. No imports of the packages."""
    from importlib.metadata import PackageNotFoundError, version  # stdlib  # noqa: PLC0415

    out: dict[str, str] = {}
    for dist in _WATCHED_DISTRIBUTIONS:
        try:
            out[dist] = version(dist)
        except PackageNotFoundError:
            continue
    return out


def _git(root: Path, *args: str) -> str | None:
    """A git command's stdout, or None when git/repo is absent. Never raises."""
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def filter_dirt(status: str, data_rel: str | None) -> list:
    """`git status --porcelain` lines that make a tree dirty, minus untracked run output.

    EVERY RUN AFTER THE FIRST WAS RECORDED DIRTY. A finished run directory under
    `data/runs*/` is an untracked file until someone commits it, and any untracked file
    used to count -- so the second run on a machine always said `dirty: true` about code
    byte-identical to the recorded commit, and "commit before you run" really meant
    "commit after every run". All six local ML arms of 2026-09-30 needed
    `EVAL_RUNS_DIR` pointed outside the tree to get an honest flag.

    Run output is not code. An UNTRACKED path under `<data_rel>runs*` is ignored;
    anything else still counts -- a modified tracked file anywhere (a committed run
    included), and untracked files outside the runs directories, which could be code.
    Pure, so the rule is tested without a git tree.
    """
    dirt = []
    for line in (status or "").splitlines():
        path = line[3:].strip().strip('"')
        if (
            line.startswith("?? ")
            and data_rel
            and path.startswith(data_rel)
            and path[len(data_rel) :].startswith("runs")
        ):
            continue
        dirt.append(line)
    return dirt


def tree_dirt(root: Path, data_dir: Path | None = None) -> list | None:
    """The lines that make `root`'s git tree dirty, or None when git cannot say. Untracked
    run output under `data_dir` (the project's data root, `EVAL_DATA_DIR`; default
    `<root>/data`) does not count."""
    status = _git(root, "status", "--porcelain")
    if status is None:
        return None
    top = _git(root, "rev-parse", "--show-toplevel")
    try:
        data_rel = (
            (data_dir or root / "data").resolve().relative_to(Path(top).resolve()).as_posix() + "/"
            if top
            else None
        )
    except ValueError:
        data_rel = None
    return filter_dirt(status, data_rel)


#: The commands that write a run, or a reference a run is scored against.
_PRODUCERS = ("experiment_run.py", "rescore.py", "judge_score.py", "import_run.py", "reference_create.py")


def measuring_modules(here: Path | None = None) -> list[Path]:
    """The code a run's numbers can depend on: the run-writing commands and every module
    beside them they import, at any depth, lazily or not, read from the source.

    It was every .py file in the directory, tests and report checkers included, so editing a
    test between two runs made run-compare call them "not a controlled comparison" over a
    file that cannot touch a measurement. Derived rather than listed, so a new measuring
    module is covered the day it is imported."""
    import ast  # noqa: PLC0415

    here = here or Path(__file__).resolve().parent
    seen: set[str] = set()
    todo = list(_PRODUCERS)
    while todo:
        name = todo.pop()
        p = here / name
        if name in seen or not p.is_file():
            continue
        seen.add(name)
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module.split(".")[0]]
            todo += [f"{m}.py" for m in mods if (here / f"{m}.py").is_file()]
    return sorted(here / n for n in seen)


def harness_code_sha256() -> str:
    """Content hash of the harness code that can affect a measurement (`measuring_modules`).

    The identity that survives installation. A project that depends on the harness has
    no git history for it, and an edited site-packages copy would otherwise be invisible.
    """
    h = hashlib.sha256()
    for f in measuring_modules():
        h.update(f.name.encode())
        h.update(b"\x00")
        h.update(f.read_bytes())
        h.update(b"\x1e")
    return h.hexdigest()


def _harness_identity(root: Path, data_dir: Path | None = None) -> dict[str, Any]:
    """The INSTRUMENT: this harness's own code state, and the project it ran in.

    `commit` and `dirty` describe the PROJECT's git tree (in a checkout of eval-harness,
    that is the harness itself). `version` and `code_sha256` describe the harness code,
    and are the only reliable identity when the harness is an installed dependency.
    """
    from _version import __version__  # noqa: PLC0415

    commit = _git(root, "rev-parse", "--short=12", "HEAD")
    dirt = tree_dirt(root, data_dir)
    here = Path(__file__).resolve().parent
    return {
        "commit": commit,
        # A dirty tree is not a version. Recorded rather than only refused, so a number
        # produced from one carries the caveat instead of implying reproducibility.
        # Untracked run output does not count (see filter_dirt).
        "dirty": bool(dirt) if dirt is not None else None,
        "version": __version__,
        "code_sha256": harness_code_sha256(),
        "installed": not (here.parent / "Makefile").is_file(),
    }


def sha256_file(path: Path) -> str | None:
    """Content hash of one file, or None if unreadable."""
    try:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _adapter_identity(adapter_path: Path | None, adapter_id: str) -> dict[str, Any]:
    """The INSTRUMENT's scoring half, by CONTENT rather than by path.

    A path is not an identity: the adapter holds `score()`, so editing it changes what
    every number means, and a run that recorded only `examples/x/adapter.py` would still
    claim a scorer that no longer exists as it was. A git commit would not catch an
    uncommitted edit either. The file's sha256 does.
    """
    return {
        "id": adapter_id,
        "sha256": sha256_file(adapter_path) if adapter_path else None,
    }


def _host_identity() -> dict[str, Any]:
    """The machine. Wall-clock is machine-dependent, which makes the machine part of
    what a latency number MEANS — so it is recorded, not assumed.

    `label` is overridable because the auto-detected string cannot tell two Macs apart
    and the operator can: EVAL_HOST_LABEL=m4pro / mini-intel / dgx.
    """
    uname = platform.uname()
    return {
        "label": os.environ.get("EVAL_HOST_LABEL") or None,
        "platform": f"{uname.system}/{uname.machine}",
        "release": uname.release,
        "processor": platform.processor() or None,
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
    }


def _model_identity(
    hook: Callable[[dict[str, Any]], dict[str, Any]] | None, params: dict[str, Any]
) -> dict[str, Any]:
    """Whatever the adapter says identifies its system under test.

    Absent hook -> `{"identity_declared": False}`. That is honest: an echo arm has no model,
    and a
    fingerprint claiming otherwise would be worse than one admitting the gap.

    A hook that raises is caught. Fingerprinting must never be the reason a run fails —
    it is a description of the run, not a precondition for it.
    """
    if hook is None:
        return {"identity_declared": False}
    try:
        declared = hook(params) or {}
    except Exception as exc:  # noqa: BLE001 - a broken hook must not kill the run
        return {"identity_declared": False, "error": f"{type(exc).__name__}: {exc}"}
    if not isinstance(declared, dict):
        return {"identity_declared": False, "error": "fingerprint() did not return a dict"}
    # `identity_declared` is a FLAG -- did the adapter tell us what its system under
    # test is -- not the identity itself. It was called `declared`, which reads like it
    # holds a value, and it was identical across 24 different models because it means
    # "yes". The identity lives in the keys the adapter returns, beside it.
    out: dict[str, Any] = {"identity_declared": True, **declared}
    # Say the quiet part: no revision means no proof two runs used the same weights.
    if not declared.get("revision"):
        out.setdefault("revision", None)
        out.setdefault("revision_source", "unavailable")
    return out


def build_fingerprint(
    *,
    root: Path,
    dataset: dict[str, Any],
    reference_id: str | None,
    reference_tier: str | None,
    config_id: str,
    params: dict[str, Any],
    adapter_id: str,
    adapter_path: Path | None,
    model_hook: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """The full fingerprint, plus one hash over all of it. `data_dir` is the project's data
    root (`_common.DATA`, which honours EVAL_DATA_DIR); it defaults to `<root>/data`.

    The hash is the point: comparing two runs field by field is work nobody does, and a
    single differing hash answers "did anything else move?" at a glance. If it matches,
    you varied one thing. If it does not, you have not run the experiment you think you
    have — and the fields say which part drifted.
    """
    fp: dict[str, Any] = {
        # v2 adds data.references_sha256. A v1 fingerprint cannot be compared to a v2
        # one on the hash alone, because v2 hashes strictly more -- the version says so
        # rather than leaving a reader to discover it from a mismatch.
        # VERSION 3 as of 2026-09-30. v2 added `data.references_sha256`; v3 changed
        # what that digest covers -- every file in the reference directory, not just
        # `*.txt`, so a silver set's manifest.json (which records WHICH MODEL authored
        # it) is inside the hash. A v2 and a v3 digest over the same directory differ
        # whenever a non-.txt file is present, so they are not comparable and the
        # version must say so. Left at 2 when the rule changed; found by external
        # review.
        "version": 3,
        "instrument": {
            "harness": _harness_identity(root, data_dir),
            "adapter": _adapter_identity(adapter_path, adapter_id),
        },
        "system_under_test": {
            "model": _model_identity(model_hook, params),
            "libraries": _installed_versions(),
        },
        "data": {
            "dataset_id": dataset.get("dataset_id"),
            # The item hashes ARE the dataset's identity — dataset_id is a name, and a
            # name can be reused over different bytes.
            "items_sha256": items_digest(dataset),
            "n_items": len(dataset.get("items") or []),
            "reference_id": reference_id,
            "reference_tier": reference_tier,
            # THE REFERENCE BYTES, not just its name. Without this you can edit a gold
            # file, get different scores, and the fingerprint stays identical --
            # `compare_runs` then reports "reference identical" while comparing two
            # different measurements. That is the exact failure this whole structure
            # exists to prevent, and it applied to references for as long as the
            # comment two fields above has been telling you a name is not an identity.
            "references_sha256": references_digest(root, reference_id, data_dir),
        },
        "host": _host_identity(),
        "arm": {"config_id": config_id, "params": dict(params or {})},
    }
    fp["hash"] = _hash_of(fp)
    return fp


def references_digest(root: Path, reference_id: str | None, data_dir: Path | None = None) -> str | None:
    """One hash over every reference file's bytes, by filename order. The references live
    under `data_dir` (default `<root>/data`): hard-coding `<root>/data` recorded None, "not
    scored against anything", for every run of a project that moves its data root.

    None when the run has no references -- distinguishable from a hash, so "not scored
    against anything" and "scored against these bytes" never look alike.
    """
    if not reference_id:
        return None
    ref_dir = (data_dir or root / "data") / "references" / reference_id
    if not ref_dir.is_dir():
        return None
    # EVERY FILE, not just *.txt. A silver reference directory also carries
    # manifest.json, which records WHICH MODEL authored those references and whether
    # its provenance is complete -- and this hashed only the texts, so that record
    # could change without the fingerprint moving. For a reference tier whose whole
    # caveat is "these were written by a model, and which model matters", leaving the
    # statement of which model outside the hash is the wrong half to omit. Found by
    # external review.
    h = hashlib.sha256()
    for f in sorted(x for x in ref_dir.iterdir() if x.is_file()):
        h.update(f.name.encode())
        h.update(b"\x00")
        h.update(f.read_bytes())
        h.update(b"\x1e")
    return h.hexdigest()


def items_digest(dataset: dict[str, Any]) -> str | None:
    """One hash over every item's frozen sha256, in item order."""
    items = dataset.get("items") or []
    if not items:
        return None
    h = hashlib.sha256()
    for item in items:
        h.update(str(item.get("item_id", "")).encode())
        h.update(str(item.get("source_sha256", "")).encode())
    return h.hexdigest()


def _hash_of(fingerprint: dict[str, Any]) -> str:
    """SHA256 over the fingerprint, minus the hash field itself.

    sort_keys so field order cannot change the answer; default=str so an unexpected type
    from an adapter's hook degrades to a stable string instead of raising.
    """
    body = {k: v for k, v in fingerprint.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def differing_paths(a: dict[str, Any], b: dict[str, Any], _prefix: str = "") -> list[str]:
    """Dotted paths where two fingerprints disagree — what `run-compare` should name.

    "The hashes differ" is true and useless. "system_under_test.model.revision differs"
    tells you whether you compared two models or two machines.
    """
    out: list[str] = []
    for key in sorted(set(a) | set(b)):
        if key == "hash":
            continue
        av, bv = a.get(key), b.get(key)
        path = f"{_prefix}{key}"
        if isinstance(av, dict) and isinstance(bv, dict):
            out.extend(differing_paths(av, bv, f"{path}."))
        elif av != bv:
            out.append(path)
    return out
