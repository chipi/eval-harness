"""Adapters: finding one, loading it once, and what it declares.

Every example's adapter file is `adapter.py`. Two registries used to name loaded adapters:
`experiment_run` by file stem (`eval_adapter_adapter` for all of them) and `_common` by
stem plus path digest, and the metric-kind and primary-metric lookups read the first and
fell back to `import adapter`, the BUNDLED adapter. A process that loaded a project's
adapter through the second registry and then asked for its metric kinds got the bundled
adapter's, and rescore wrote them into new runs. Now there is one cache, keyed by the
resolved file, and the bundled adapter is the `adapter` module itself, so a test that
patches `adapter` patches what the harness runs.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

from _common import (
    BUNDLED_ADAPTER_ID,
    CODE,
    ROOT,
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
        cached = sys.modules.get("adapter")
        if key == BUNDLED.resolve() and (
            cached is None or Path(getattr(cached, "__file__", "") or "").resolve() == key
        ):
            # The `adapter` module itself, so a test that patches `adapter` patches what runs.
            sys.path.insert(0, str(CODE))
            import adapter  # noqa: PLC0415

            _LOADED[key] = adapter
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
    module = _module_or_none(adapter_path)
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
    for base in adapter_search_dirs()[:2]:
        try:
            return str(resolved.relative_to(base))
        except ValueError:
            continue
    return str(Path(*resolved.parts[-2:]))


def load_adapter(
    spec: str | None, config_path: Path | None = None
) -> tuple[Any, Any, str, Path | None, Any, Any]:
    """``(call_system, score, adapter_id)`` for the adapter a config names.

    Defaults to ``scripts/adapter.py`` — the single seam, unchanged for anyone who has one
    system to measure. A config may name its own instead:

        adapter: examples/summarization-cnn-dailymail/adapter.py

    That exists because an example is not just a different model, it is a different TASK:
    summarisation scores ROUGE, classification scores macro-F1, and neither is the token
    overlap the bundled adapter computes. One adapter file per task, selected by the arm,
    keeps "an arm is a YAML file" true.

    The returned id is recorded on the run. It has to be: a scorer is half of what a number
    means, so two runs sharing a config_id but scored by different adapters are no more
    comparable than two runs on different datasets. run-compare refuses across it.
    """
    if not spec:
        default = module_at(BUNDLED)
        return (
            default.call_system,
            default.score,
            BUNDLED_ADAPTER_ID,
            BUNDLED,
            getattr(default, "warmup", None),
            getattr(default, "fingerprint", None),
        )

    # Relative to the CONFIG first, then the harness root. An example's arm sits beside its
    # adapter and should be able to say `adapter: adapter.py` — the two travel together, and
    # a path written from the harness's point of view breaks the moment the example moves.
    path = Path(spec)
    candidates = []
    if path.is_absolute():
        candidates = [path]
    else:
        if config_path is not None:
            candidates.append(config_path.resolve().parent / path)
        candidates.append(ROOT / path)
    for candidate in candidates:
        if candidate.is_file():
            path = candidate
            break
    else:
        die(f"adapter not found: {spec}\n" + "".join(f"  looked in: {c}\n" for c in candidates))
    try:
        module = module_at(path)
    except ModuleNotLoadable:
        die(f"adapter is not importable: {path}")
    for required in ("call_system", "score"):
        if not hasattr(module, required):
            die(f"adapter {spec} defines no {required}()")
    adapter_id = _portable_id(path)
    return (
        module.call_system,
        module.score,
        adapter_id,
        path,
        getattr(module, "warmup", None),
        getattr(module, "fingerprint", None),
    )
