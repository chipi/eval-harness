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

VERSION 5 (RFC-021) splits the fingerprint by what each part identifies: the instrument and
the data (as in v4), the DEPLOYMENT (the system under test as it executed: weights, server,
hardware), the SETTINGS (how it was asked) and the RUNNER (where `evh` ran, outside the hash).
Each hashed part has its own sha256 and `hash` is one hash over the four, so "did anything move"
is one comparison and "what moved" is four.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any, Callable

from evaluation_harness._providers import PROVIDERS, identity_params

VERSION = 5

#: The parts the hash covers, in the order they are combined. `runner` and `arm` are recorded only.
PARTS = ("instrument", "data", "deployment", "settings")

#: Params that say WHERE and ON WHAT the model ran: they describe the deployment, so they are not
#: settings. Credentials (`api_key_env`, see `_providers.identity_params`) are in no part.
DEPLOYMENT_KEYS = (
    "model",
    "url",
    "base_url",
    "machine",
    "provider",
    "provider_routing",
    "revision",
    "device",
    "precision",
    "deployment",
    "model_record",
)

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


#: The commands that write a run, or a reference a run is scored against, and the bundled
#: adapter: _adapter loads it by path, so no import names it.
_PACKAGE = "evaluation_harness"
_PRODUCERS = (
    "experiment_run.py",
    "rescore.py",
    "judge_score.py",
    "import_run.py",
    "reference_create.py",
    "adapter.py",
)


def measuring_modules(here: Path | None = None, producers: tuple[str, ...] = _PRODUCERS) -> list[Path]:
    """The code a run's numbers can depend on: the run-writing commands and every module
    beside them they import, at any depth, lazily or not, read from the source.

    It was every .py file in the directory, tests and report checkers included, so editing a
    test between two runs made run-compare call them "not a controlled comparison" over a
    file that cannot touch a measurement. Derived rather than listed, so a new measuring
    module is covered the day it is imported. `producers` names other roots: family-test
    keys its result cache on its own closure the same way."""
    import ast  # noqa: PLC0415

    here = here or Path(__file__).resolve().parent
    seen: set[str] = set()
    todo = list(producers)
    while todo:
        name = todo.pop()
        p = here / name
        if name in seen or not p.is_file():
            continue
        seen.add(name)
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            # The package's own modules, as they import each other: `from evaluation_harness._x
            # import ...`, `from evaluation_harness import x`, `import evaluation_harness.x`.
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[1] for a in node.names if a.name.startswith(_PACKAGE + ".")]
            elif isinstance(node, ast.ImportFrom) and node.module == _PACKAGE:
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith(_PACKAGE + "."):
                mods = [(node.module or "").split(".")[1]]
            todo += [f"{m}.py" for m in mods if (here / f"{m}.py").is_file()]
    return sorted(here / n for n in seen)


def harness_code_sha256() -> str:
    """Content hash of the harness code that can affect a measurement (`measuring_modules`).

    The identity that survives installation. A project that depends on the harness has
    no git history for it, and an edited site-packages copy would otherwise be invisible.
    """
    from evaluation_harness._codeid import file_sha256  # noqa: PLC0415

    h = hashlib.sha256()
    for f in measuring_modules():
        h.update(f.name.encode())
        h.update(b"\x00")
        # By behaviour (_codeid): a docstring or a comment in the harness is not a new instrument.
        h.update((file_sha256(f) or "").encode())
        h.update(b"\x1e")
    return h.hexdigest()


def _harness_identity(root: Path, data_dir: Path | None = None) -> dict[str, Any]:
    """The INSTRUMENT: this harness's own code state, and the project it ran in.

    `commit` and `dirty` describe the PROJECT's git tree (in a checkout of eval-harness,
    that is the harness itself). `version` and `code_sha256` describe the harness code,
    and are the only reliable identity when the harness is an installed dependency.
    """
    from evaluation_harness._version import __version__  # noqa: PLC0415

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


def _adapter_identity(
    adapter_path: Path | None, adapter_id: str, sha256: str | None = None
) -> dict[str, Any]:
    """The INSTRUMENT's scoring half, by CONTENT rather than by path.

    A path is not an identity: the adapter holds `score()`, so editing it changes what
    every number means, and a run that recorded only `examples/x/adapter.py` would still
    claim a scorer that no longer exists as it was. A git commit would not catch an
    uncommitted edit either. Its code does, hashed by behaviour (_codeid): documentation (a
    docstring, a comment, METRIC_DESCRIPTIONS) can change at any time without making it a new
    scorer. With no file (an imported run), `sha256` is the scoring code's hash as the caller
    states it.
    """
    from evaluation_harness._codeid import file_sha256  # noqa: PLC0415

    return {
        "id": adapter_id,
        "sha256": file_sha256(adapter_path) if adapter_path else sha256,
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


#: Params that describe an arm for its readers and do not change what the system does: its prices
#: (cost is computed from them after the call) and its labels. Recorded as the arm's labels, outside the hash.
LABEL_KEYS = ("usd_per_mtok_in", "usd_per_mtok_out", "price_tier", "family", "label", "notes")


def settings_of(params: dict[str, Any] | None) -> dict[str, Any]:
    """How the system was asked: every param that changes what the system does, so neither a deployment
    key, a credential, nor a label (LABEL_KEYS)."""
    return {
        k: v
        for k, v in identity_params(dict(params or {})).items()
        if k not in DEPLOYMENT_KEYS and k not in LABEL_KEYS
    }


def labels_of(params: dict[str, Any] | None) -> dict[str, Any]:
    """The arm's labels and prices (LABEL_KEYS), recorded with the arm and outside every hash."""
    return {k: v for k, v in dict(params or {}).items() if k in LABEL_KEYS}


#: What an adapter's hook may declare about HOW the system was asked, not which system it is: settings.
DECLARED_SETTINGS = (
    "prompt_sha256",
    "system_prompt_sha256",
    "temperature",
    "reasoning",
    "reasoning_effort",
    "max_tokens",
)


def split_declared(deployment: dict[str, Any], settings: dict[str, Any]) -> None:
    """Move what the hook declared about how it asked (a prompt hash, a temperature, reasoning) from the
    deployment to the settings, under `declared`, so a prompt change moves the settings' hash, not the
    deployment's."""
    extra = deployment.get("declared") or {}
    moved = {k: extra.pop(k) for k in DECLARED_SETTINGS if k in extra}
    if moved:
        settings["declared"] = moved
    deployment["declared"] = extra or None


def _runner_identity(libraries: dict[str, str] | None) -> dict[str, Any]:
    """Where `evh` ran: the host, and the client libraries it called the system with (None when the
    model ran in this process: then they are the deployment's)."""
    return {**_host_identity(), "libraries": libraries}


def _split_server(text: Any) -> tuple[str | None, str | None]:
    """("ollama", "0.40.13") from a record's "ollama 0.40.13"."""
    name, _, version = str(text or "").strip().partition(" ")
    return (name or None), (version.strip() or None)


def _weights(**kw: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "digest": None,
        "revision": None,
        "revision_source": None,
        "file_hash": None,
        "quantization": None,
        "precision": None,
    }
    out.update({k: v for k, v in kw.items() if v is not None})
    return out


def _derived_id(model: Any, machine: Any) -> str | None:
    return "@".join(str(x) for x in (model, machine) if x) or None


def _record_deployment(record_id: str, entry: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """source: record. The deployment entry of a model record (data/models/<id>.yaml), as last onboarded."""
    ep = entry.get("endpoint") or {}
    name, version = _split_server(entry.get("server"))
    hosted = bool(
        entry.get("provider_id") or entry.get("provider_routing") or entry.get("backend") == "hosted"
    )
    return {
        "id": f"{record_id}@{entry['id']}",
        "model": params.get("model") or ep.get("model") or entry.get("tag") or entry.get("provider_id"),
        "source": "record",
        "weights": _weights(
            digest=entry.get("digest"),
            revision=entry.get("revision"),
            file_hash=entry.get("file_hash"),
            quantization=entry.get("quantization"),
        ),
        "server": {"name": name, "version": version, "settings": entry.get("server_settings"), "url": None},
        "where": {
            "machine": entry.get("where"),
            "backend": entry.get("backend"),
            "device": entry.get("device"),
        },
        "hosted": {
            "provider": entry.get("where"),
            "provider_id": entry.get("provider_id"),
            "route": entry.get("provider_routing"),
        }
        if hosted
        else None,
        "provider": ep.get("provider"),
        "in_process": False,
        "libraries": None,
        "declared": None,
    }


#: What an adapter's hook returns that has a home in the deployment; the rest is kept under `declared`.
_MAPPED = ("identity_declared", "error", "id", "revision", "revision_source", "device", "precision")


def _declared_extra(declared: dict[str, Any], model: Any) -> dict[str, Any] | None:
    """Whatever else the hook returned (weight files, a prompt hash, the upstream id behind an alias, ...)."""
    extra = {k: v for k, v in declared.items() if k not in _MAPPED}
    if declared.get("id") not in (None, model):
        extra["id"] = declared["id"]
    return extra or None


#: Providers that call a system somewhere else: the built-in hosted ones and an adapter's own gateway.
REMOTE_PROVIDERS = (*PROVIDERS, "gateway")


def is_remote(params: dict[str, Any]) -> bool:
    """The system under test runs somewhere else: the arm calls a URL, or a hosted provider or a gateway."""
    return bool(params.get("url") or params.get("base_url") or params.get("provider") in REMOTE_PROVIDERS)


def _adapter_deployment(
    declared: dict[str, Any], params: dict[str, Any], libraries: dict[str, str]
) -> dict[str, Any]:
    """source: adapter. The adapter's `fingerprint(params)` hook, in v4's vocabulary. In process (a local ML
    model) the runner's libraries ran the model, so they are the deployment's; called somewhere else (a
    hosted model, a gateway, a server) they only sent the request, so they stay the runner's."""
    in_process = not is_remote(params)
    model = params.get("model") or declared.get("id")
    provider = params.get("provider") or declared.get("provider")
    url = params.get("base_url") or params.get("url")
    hosted = (
        {
            "provider": provider,
            "provider_id": declared.get("id") if declared.get("id") not in (None, model) else None,
            "route": params.get("provider_routing") or declared.get("provider_routing"),
        }
        if provider in REMOTE_PROVIDERS and not url
        else None
    )
    return {
        "id": _derived_id(model, params.get("machine")),
        "model": model,
        "source": "adapter",
        "weights": _weights(
            revision=declared.get("revision"),
            revision_source=declared.get("revision_source"),
            precision=declared.get("precision"),
        ),
        # The server the adapter called, as the params name it: a hook says what the model is, not where.
        "server": {"name": None, "version": None, "settings": None, "url": url} if url else None,
        "where": {"machine": params.get("machine"), "backend": None, "device": declared.get("device")},
        "hosted": hosted,
        "provider": provider,
        "in_process": in_process,
        "libraries": libraries if in_process else None,
        "declared": _declared_extra(declared, model),
    }


def _params_deployment(params: dict[str, Any], declared: dict[str, Any] | None = None) -> dict[str, Any]:
    """source: params. Neither a record nor an adapter said who the system is: the deployment is what the
    params say, with no digest. Honest about the gap, as v4 was about a missing revision. What a hook
    returned while declining to claim an identity (a baseline's code hash) is kept under `declared`."""
    declared = declared or {}
    model = params.get("model") or declared.get("id")
    url = params.get("base_url") or params.get("url")
    routing = params.get("provider_routing")
    out: dict[str, Any] = {
        "id": _derived_id(model, params.get("machine")),
        "model": model,
        "source": "params",
        "weights": _weights(
            revision=params.get("revision"),
            revision_source=declared.get("revision_source"),
            precision=params.get("precision"),
        ),
        "server": {"name": None, "version": None, "settings": None, "url": url} if url else None,
        "where": {"machine": params.get("machine"), "backend": None, "device": params.get("device")},
        "hosted": {"provider": params.get("provider"), "provider_id": None, "route": routing}
        if routing
        else None,
        "provider": params.get("provider"),
        "in_process": False,
        "libraries": None,
        "declared": _declared_extra(declared, model),
    }
    if declared.get("error"):
        out["declared_error"] = declared["error"]
    return out


def deployment_of(
    *,
    params: dict[str, Any],
    cfg: dict[str, Any] | None,
    data_dir: Path,
    hook: Callable[[dict[str, Any]], dict[str, Any]] | None,
    libraries: dict[str, str],
) -> dict[str, Any]:
    """The deployment, from the best source there is: the model record and deployment the arm names,
    else the adapter's declared identity, else the params."""
    cfg = cfg or {}
    declared = _model_identity(hook, params)
    if cfg.get("model_record") and cfg.get("deployment"):
        from evaluation_harness import _models  # noqa: PLC0415

        rec = _models.find(data_dir, cfg["model_record"])
        entry = _models.deployment_of(rec, cfg["deployment"]) if rec else None
        if entry is not None:
            dep = _record_deployment(cfg["model_record"], entry, params)
            # The record says where and as which build; the hook still says what only the adapter knows
            # (its prompt's hash, the code it replays), so a record never hides those.
            dep["declared"] = _declared_extra(declared, dep["model"])
            return dep
    if declared.get("identity_declared"):
        return _adapter_deployment(declared, params, libraries)
    return _params_deployment(params, declared)


def part_sha256(part: Any) -> str:
    """The hash of one part. sort_keys so field order cannot change the answer; default=str so an
    unexpected type from an adapter's hook degrades to a stable string instead of raising."""
    return hashlib.sha256(json.dumps(part, sort_keys=True, default=str).encode()).hexdigest()


def hashed_view(part: str, value: Any) -> Any:
    """What of a part its hash covers. The instrument is its code, by behaviour: the harness's
    `code_sha256` and the adapter's `sha256`. The commit, a dirty tree, the version string, an installed
    copy and the adapter's path are provenance, recorded beside it: two runs of the same code made on
    different days are the same instrument. Every other part is hashed whole."""
    if part != "instrument" or not isinstance(value, dict):
        return value
    harness = value.get("harness") or {}
    adapter = value.get("adapter") or {}
    return {
        "harness": {"code_sha256": harness.get("code_sha256")},
        "adapter": {"sha256": adapter.get("sha256")},
    }


def seal(fp: dict[str, Any], *, whole: bool = True) -> dict[str, Any]:
    """Fill in each hashed part's sha256 and, when `whole`, the one hash over the four. A derived run
    (rescored, judged) keeps the whole hash null: its parts were not measured together."""
    for part in PARTS:
        fp[f"{part}_sha256"] = part_sha256(hashed_view(part, fp.get(part)))
    fp["hash"] = combined_hash(fp) if whole else None
    return fp


def combined_hash(fp: dict[str, Any]) -> str:
    """sha256 over the four parts' own hashes."""
    return part_sha256({part: fp.get(f"{part}_sha256") for part in PARTS})


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
    adapter_sha256: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The full fingerprint, with a sha256 per hashed part and one hash over the four. `data_dir` is
    the project's data root (`_common.DATA`, which honours EVAL_DATA_DIR); it defaults to
    `<root>/data`. `cfg` is the arm's resolved config: the model record and deployment it names
    (`model_record`, `deployment`) are where the deployment comes from, best first.

    The hash is the point: comparing two runs field by field is work nobody does, and a
    single differing hash answers "did anything else move?" at a glance. If it matches,
    you varied one thing. If it does not, you have not run the experiment you think you
    have — and the part hashes say which part drifted.
    """
    libraries = _installed_versions()
    deployment = deployment_of(
        params=dict(params or {}),
        cfg=cfg,
        data_dir=data_dir or root / "data",
        hook=model_hook,
        libraries=libraries,
    )
    fp: dict[str, Any] = {
        # v2 added data.references_sha256; v3 widened what it covers to every file in the reference
        # directory (a silver set's manifest says WHICH MODEL authored it); v4 (2026-10-24) hashed
        # code by behaviour (_codeid), so documentation never moves a fingerprint. v5 (2026-10-31,
        # RFC-021) splits the system under test into a deployment and settings and moves the host out
        # of the hash. Versions hash different things: the version says so rather than leaving a
        # reader to discover it from a mismatch.
        "version": VERSION,
        "instrument": {
            "harness": _harness_identity(root, data_dir),
            "adapter": _adapter_identity(adapter_path, adapter_id, adapter_sha256),
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
            # exists to prevent.
            "references_sha256": references_digest(root, reference_id, data_dir),
        },
        "deployment": deployment,
        "settings": settings_of(params),
        "runner": _runner_identity(None if deployment["in_process"] else libraries),
        "arm": {"config_id": config_id, "labels": labels_of(params) or None},
    }
    split_declared(fp["deployment"], fp["settings"])
    return seal(fp)


#: The manifest fields a reference's identity depends on: who (or what) authored its texts.
AUTHORSHIP = ("authored_by", "authored_with", "model", "system_under_test", "params", "from_run")


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
    # Of the manifest, only who authored the texts: the rest is documentation (the caveat, when
    # and how it was made or fetched, what it cost), derived from the texts (their checksums and
    # count) or the directory's own name (dataset, tier). A gold manifest then adds nothing, and
    # rewording, re-dating or re-fetching a reference never moves a run's hash.
    h = hashlib.sha256()
    for f in sorted(x for x in ref_dir.iterdir() if x.is_file()):
        data = f.read_bytes()
        if f.name == "manifest.json":
            try:
                doc = {k: v for k, v in json.loads(data).items() if k in AUTHORSHIP}
            except ValueError:
                doc = None
            if doc == {}:
                continue
            if doc is not None:
                data = json.dumps(doc, sort_keys=True).encode()
        h.update(f.name.encode())
        h.update(b"\x00")
        h.update(data)
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


def moved_parts(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """The hashed parts (`PARTS`) whose content differs between two fingerprints, from the parts
    themselves rather than their stored hashes."""
    return [p for p in PARTS if part_sha256(a.get(p)) != part_sha256(b.get(p))]


def differing_paths(a: dict[str, Any], b: dict[str, Any], _prefix: str = "") -> list[str]:
    """Dotted paths where two fingerprints disagree — what `run-compare` should name.

    "The hashes differ" is true and useless. "deployment.weights.digest differs"
    tells you whether you compared two models or two machines. The hashes themselves
    (`hash`, and each part's `<part>_sha256`) are the summary of the paths, not a path.
    """
    out: list[str] = []
    for key in sorted(set(a) | set(b)):
        if not _prefix and (key == "hash" or key in {f"{p}_sha256" for p in PARTS}):
            continue
        av, bv = a.get(key), b.get(key)
        path = f"{_prefix}{key}"
        if isinstance(av, dict) and isinstance(bv, dict):
            out.extend(differing_paths(av, bv, f"{path}."))
        elif av != bv:
            out.append(path)
    return out
