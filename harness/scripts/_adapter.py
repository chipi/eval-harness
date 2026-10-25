"""Adapters: finding one, loading it once, and what it declares.

Every example's adapter file is `adapter.py`. Two registries used to name loaded adapters:
`experiment_run` by file stem (`eval_adapter_adapter` for all of them) and `_common` by
stem plus path digest, and the metric-kind and primary-metric lookups read the first and
fell back to `import adapter`, the BUNDLED adapter. A process that loaded a project's
adapter through the second registry and then asked for its metric kinds got the bundled
adapter's, and rescore wrote them into new runs. Now there is one cache, keyed by the
resolved file, and the bundled adapter is the `evaluation_harness.adapter` module itself, so
a test that patches it patches what the harness runs.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import hashlib
import importlib
from pathlib import Path
from typing import Any

from evaluation_harness import _common
from evaluation_harness._common import (
    BUNDLED_ADAPTER_ID,
    CODE,
    ModuleNotLoadable,
    adapter_search_dirs,
    die,
    load_module,
    resolve_adapter_path,
)

#: The adapter bundled with the harness, used when a config names none.
BUNDLED = CODE / "adapter.py"

_LOADED: dict[Path, Any] = {}
#: Files that failed to import, so a reader asking per run does not re-run a broken module.
_FAILED: set[Path] = set()


def module_at(path: Path) -> Any:
    """The adapter module at `path`, imported once per process. Raises what the import raises
    (ModuleNotLoadable when the file has no import spec)."""
    key = Path(path).resolve()
    if key not in _LOADED:
        if key == BUNDLED.resolve():
            # The package's own module, so a test that patches `evaluation_harness.adapter`
            # patches what runs; never registered as a bare `adapter`, which is a project's name.
            _LOADED[key] = importlib.import_module("evaluation_harness.adapter")
        else:
            digest = hashlib.sha256(str(key).encode()).hexdigest()[:8]
            _LOADED[key] = load_module(key, f"evh_adapter_{key.stem}_{digest}")
    return _LOADED[key]


def _module_or_none(adapter_path: Path | None) -> Any:
    key = Path(adapter_path or BUNDLED).resolve()
    if key in _FAILED:
        return None
    try:
        return module_at(key)
    except Exception:  # noqa: BLE001 — an adapter that will not import declares nothing
        _FAILED.add(key)
        return None


def adapter_module(adapter_spec: str | None) -> Any:
    """The adapter a run recorded, or None when it cannot be found or imported (a machine
    without the example's environment, an adapter that moved). For the readers that degrade
    to what the run recorded: the leaderboard's and run-compare's metric kinds, the
    classification labels' parser."""
    cand = resolve_adapter_path(adapter_spec) if adapter_spec else None
    return _module_or_none(cand) if cand is not None else None


def metric_kinds(adapter_path: Path | None) -> dict[str, str]:
    """`METRIC_KINDS` from the adapter at `adapter_path` (None: the bundled one), or {}."""
    return _kinds_of(_module_or_none(adapter_path))


def recorded_metric_kinds(adapter_spec: str | None) -> dict[str, str] | None:
    """`METRIC_KINDS` as the adapter a run recorded declares them TODAY, or None when it
    cannot be found or imported. A run freezes the kinds declared when it was measured, and
    the current adapter is the authority on what its metrics mean, so the leaderboard and
    run-compare override the run's with these; None leaves the run's own."""
    module = adapter_module(adapter_spec)
    return None if module is None else _kinds_of(module)


def _kinds_of(module: Any) -> dict[str, str]:
    kinds = getattr(module, "METRIC_KINDS", None)
    out = dict(kinds) if isinstance(kinds, dict) else {}
    # Metrics the CORE emits, which no adapter declares because no adapter produces
    # them. Without this `resumed` lands among the quality columns, where a leaderboard
    # reads higher as better -- and "was not actually run this pass" would sort to the
    # top. Declared here rather than asked of every adapter, because the core owns them.
    out.setdefault("resumed", "descriptive")
    return out


def transient_markers(adapter_path: Path | None) -> tuple:
    """Extra "worth retrying" markers this adapter declares, as `TRANSIENT_MARKERS`.

    The core knows the shapes every HTTP provider shares (429, 503, "rate limit"). It
    cannot know that a particular local runtime says "CUDA out of memory" on a transient
    allocation, or that some SDK wraps a timeout in a bespoke class. The adapter can add
    to the list; it cannot shrink it, because the shapes in the core are not negotiable.
    """
    markers = getattr(_module_or_none(adapter_path), "TRANSIENT_MARKERS", None)
    return tuple(str(m) for m in markers) if isinstance(markers, (list, tuple)) else ()


def metric_directions(adapter_path: Path | None) -> dict[str, str]:
    """`METRIC_DIRECTIONS` from the adapter, {metric: "lower" | "higher"}: how an adapter says
    a quality metric goes down (WER, error rate), which METRIC_KINDS cannot. {} when absent."""
    declared = getattr(_module_or_none(adapter_path), "METRIC_DIRECTIONS", None)
    if not isinstance(declared, dict):
        return {}
    return {str(k): str(v) for k, v in declared.items() if v in ("lower", "higher")}


def metric_descriptions(adapter_path: Path | None) -> dict[str, Any]:
    """`METRIC_DESCRIPTIONS` from the adapter, {metric: what it measures}: recorded on every run,
    and the catalog's metric pages read it. A value is one line, or {"summary": one line,
    "details": how it is computed and read} for the metric's own page. {} when absent."""
    return _descriptions_of(_module_or_none(adapter_path))


def recorded_metric_descriptions(adapter_spec: str | None) -> dict[str, Any] | None:
    """`METRIC_DESCRIPTIONS` as the adapter a run recorded declares them TODAY, or None when it
    cannot be found or imported. A description is documentation, so the current adapter's
    overrides the one frozen on the run, as for metric kinds."""
    module = adapter_module(adapter_spec)
    return None if module is None else _descriptions_of(module)


def _descriptions_of(module: Any) -> dict[str, Any]:
    declared = getattr(module, "METRIC_DESCRIPTIONS", None)
    if not isinstance(declared, dict):
        return {}
    out: dict[str, Any] = {}
    for k, v in declared.items():
        if isinstance(v, str) and v.strip():
            out[str(k)] = v
        elif isinstance(v, dict) and isinstance(v.get("summary"), str) and v["summary"].strip():
            out[str(k)] = {
                "summary": v["summary"],
                **({"details": str(v["details"])} if v.get("details") else {}),
            }
    return out


def primary_metric(adapter_path: Path | None) -> str | None:
    """`PRIMARY_METRIC` from the adapter, or None.

    WHICH quality facet heads the table is a judgement the adapter author makes, not
    something to settle alphabetically. Without this the leaderboard sorted by whichever
    quality metric sorted first by name -- which, for a summariser declaring `coverage`
    and `concision`, is `concision`: brevity, quietly promoted to the headline. The same
    shape of accident once ranked a ten-model sweep by `compression`.
    """
    value = getattr(_module_or_none(adapter_path), "PRIMARY_METRIC", None)
    return value if isinstance(value, str) and value else None


def load_recorded_adapter(spec: str) -> tuple | None:
    """The adapter a finished run recorded, for scoring it again (rescore, silver-calibrate),
    or None if it cannot be found.

    Recorded ids are relative to the harness root for the bundled adapter
    ("scripts/adapter.py"), to the repository root for most examples
    ("examples/ner-few-nerd/adapter.py"), and to the examples root for the oldest sweep
    ("summarization-cnn-dailymail/adapter.py"). The bundled id is a checkout path: a project
    that pins the package has no such file, and the run was made by the package's own copy,
    so that is the one returned (found by a fresh project on 0.4.0)."""
    path = resolve_adapter_path(spec)
    if path is None:
        return None
    return load_adapter(None, None) if path == BUNDLED else load_adapter(str(path), None)


def score_wants_source(score: Any) -> bool:
    """Whether this adapter's `score()` takes the source text as a third argument.

    Arity, not configuration: the bundled adapter scores output against reference and has
    no use for the input, while a summarisation adapter needs it to measure grounding.
    Inspected once per run rather than guessed, so an adapter that does not want it is
    never handed an argument it cannot take.
    """
    import inspect  # noqa: PLC0415

    try:
        params = inspect.signature(score).parameters
    except (TypeError, ValueError):
        return False
    positional = [p for p in params.values() if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    return len(positional) >= 3 or any(p.kind is p.VAR_POSITIONAL for p in params.values())


def _portable_id(path: Path) -> str:
    """A path safe to write into a run record: relative, resolved, never a home directory.

    This is recorded in `metrics.json` and hashed into the fingerprint, so an absolute
    path both leaks the author's username into anything published and makes two identical
    runs on two machines look different.

    The old version tried `relative_to(ROOT)` on an UNRESOLVED path. Adapters live in
    sibling example directories, so that never matched -- `configs/../adapter.py` is not
    under the harness root -- and every run silently fell back to the absolute path.
    Resolve first, then widen the base one level so a sibling example resolves cleanly,
    and if even that fails keep only the last two components rather than emit a home path.
    """
    resolved = path.resolve()
    for base in adapter_search_dirs():
        try:
            return str(resolved.relative_to(base))
        except ValueError:
            continue
    return str(Path(*resolved.parts[-2:]))


def _find_adapter(spec: str, config_path: Path | None) -> Path:
    """The file an `adapter:` entry names: relative to the config first, then the project."""
    path = Path(spec)
    candidates = [path] if path.is_absolute() else []
    if not path.is_absolute():
        if config_path is not None:
            candidates.append(config_path.resolve().parent / path)
        candidates.append(_common.ROOT / path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    die(f"adapter not found: {spec}\n" + "".join(f"  looked in: {c}\n" for c in candidates))


def load_adapter(
    spec: str | None, config_path: Path | None = None
) -> tuple[Any, Any, str, Path | None, Any, Any]:
    """``(call_system, score, adapter_id)`` for the adapter a config names.

    A config names its adapter:

        adapter: adapter.py

    relative to the config first, then the project root. An example's arm sits beside its
    adapter, so the two travel together. A config that names none uses the project's own
    ``<project>/adapter.py`` when there is one, else the adapter bundled with the harness
    (``scripts/adapter.py``, token overlap: the worked example's).

    One adapter file per task, selected by the arm, keeps "an arm is a YAML file" true:
    summarisation scores ROUGE, classification macro-F1, and neither is the bundled overlap.

    The returned id is recorded on the run. It has to be: a scorer is half of what a number
    means, so two runs sharing a config_id but scored by different adapters are no more
    comparable than two runs on different datasets. run-compare refuses across it.
    """
    if spec:
        path = _find_adapter(spec, config_path)
    elif (_common.ROOT / "adapter.py").is_file():
        path = _common.ROOT / "adapter.py"
    else:
        default = module_at(BUNDLED)
        return (
            default.call_system,
            default.score,
            BUNDLED_ADAPTER_ID,
            BUNDLED,
            getattr(default, "warmup", None),
            getattr(default, "fingerprint", None),
        )
    try:
        module = module_at(path)
    except ModuleNotLoadable:
        die(f"adapter is not importable: {path}")
    for required in ("call_system", "score"):
        if not hasattr(module, required):
            die(f"adapter {path} defines no {required}()")
    adapter_id = _portable_id(path)
    return (
        module.call_system,
        module.score,
        adapter_id,
        path,
        getattr(module, "warmup", None),
        getattr(module, "fingerprint", None),
    )
