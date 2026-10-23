"""Shared helpers: paths and environment, metric semantics, adapter resolution, run grouping."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

#: Where the harness CODE lives: this directory. Schemas and sibling scripts are found
#: relative to it, so they travel with the code whether it runs from a checkout or from an
#: installed package.
CODE = Path(__file__).resolve().parent


def _project_root() -> Path:
    """Where the PROJECT lives: its data/, its .env, its git history.

    Run from a checkout of eval-harness, that is the harness/ directory beside this one,
    as it always was. Installed as a package (`pip install evaluation-harness @ git+...`), the code sits in
    site-packages and the project is wherever the user is working: `EVAL_HOME` if set,
    else the current directory. Kept apart from CODE because a project that depends on the
    harness must never write its data into site-packages.
    """
    import os  # noqa: PLC0415

    home = os.environ.get("EVAL_HOME", "").strip()
    if home:
        return Path(home).expanduser().resolve()
    checkout = CODE.parent
    if (checkout / "data").is_dir() and (checkout / "scripts").resolve() == CODE:
        return checkout
    return Path.cwd().resolve()


ROOT = _project_root()


def how(evh: str, make: str) -> str:
    """The command a hint should name: `evh …` when the harness runs as the installed tool,
    the Makefile target in a checkout. A pinned project has no Makefile, so a `make …` hint
    sends its user to a command that does not exist."""
    import os  # noqa: PLC0415

    return evh if os.environ.get("EVAL_VIA_EVH") else make


def load_dotenv(path: Path | None = None) -> int:
    """Read `.env` into the environment. No dependency, no surprises.

    Loaded by every script, so keys are never exported by hand and never pasted
    into a command that lands in shell history. An already-exported variable
    WINS — so `ANTHROPIC_API_KEY=... make experiment-run` overrides the file
    for one call without editing it.

    Copy `.env.example` to `.env` to start. `.env` is gitignored.
    """
    import os  # noqa: PLC0415

    env_path = path or (ROOT / ".env")
    if not env_path.is_file():
        return 0
    loaded = 0
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and val and key not in os.environ:
            os.environ[key] = val
            loaded += 1
    return loaded


DOTENV_LOADED = load_dotenv()


def env_float(name: str, default: float | None = None) -> float | None:
    """Parse an environment variable as a float, or return the default."""
    import os  # noqa: PLC0415

    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise SystemExit(f"ERROR: {name}={raw!r} is not a number") from None


def env_int(name: str, default: int) -> int:
    """Parse an environment variable as an integer, or return the default."""
    v = env_float(name, float(default))
    return int(v) if v is not None else default


# The data root. `EVAL_DATA_DIR` moves it, for a project whose own layout puts the
# harness's records somewhere other than <project>/data (a relative path is taken from
# the project root). Everything below is derived from it.
_data_override = os.environ.get("EVAL_DATA_DIR", "").strip()
DATA = (ROOT / Path(_data_override).expanduser()).resolve() if _data_override else ROOT / "data"
SOURCES = DATA / "sources"
DATASETS = DATA / "datasets"
MATERIALIZED = DATA / "materialized"
CONFIGS = DATA / "configs"
# Where run artifacts land. Redirectable via EVAL_RUNS_DIR so a throwaway pass -- a
# smoke check after a harness change -- cannot add repeats to the arms of a real sweep
# and silently move numbers that have already been reported. ONLY runs are redirected:
# sources, datasets and references stay shared, so a smoke run is scored against the
# same references as the real thing and is therefore actually a check of the real path.
_runs_override = os.environ.get("EVAL_RUNS_DIR", "").strip()
# Relative to the PROJECT root, as EVAL_DATA_DIR is: it resolved against the current
# directory, so with EVAL_HOME set a run written from one directory was read from another.
RUNS = ROOT / Path(_runs_override).expanduser() if _runs_override else DATA / "runs"
BASELINES = DATA / "baselines"
REFERENCES = DATA / "references"
#: What each evaluation is FOR (ADR-0002): one <goal_id>.yaml per goal, plus policy.yaml.
GOALS = DATA / "goals"
#: Field sets (ADR-0003): one <fieldset_id>.yaml each, declaring the fields items may carry.
FIELDS = DATA / "fields"
#: Items fetched from a source_url, by their sha256. Derived and gitignored, like materialized/.
ITEM_CACHE = ROOT / ".cache" / "items"

#: The JSON Schemas the harness validates against. Inside the installed package they sit
#: beside the code; in a checkout they are one level up, in harness/schemas.
SCHEMAS = next(
    (p for p in (CODE / "schemas", CODE.parent / "schemas") if p.is_dir()), CODE.parent / "schemas"
)


def data_rel(path: Path) -> str:
    """`path` relative to the project root, as git and the run records spell it. Falls
    back to the absolute path when the data root sits outside the project."""
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(Path(path).resolve())


class CostCapExceeded(RuntimeError):
    """Raised mid-run when EVAL_MAX_COST_USD is reached.

    Deliberately an abort rather than a pre-flight estimate: estimates are
    usually wrong (token counts vary, cache hits change pricing), and an abort
    stops the bill the moment the cap is hit. Callers catch it and write
    whatever they have, so a capped run still yields a usable partial report.
    """


def now() -> str:
    """Return the current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file's contents."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Any:
    """Parse and return the JSON object from a file."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_text_atomic(path: Path, text: str) -> None:
    """Write via a temp file in the same directory, then rename.

    `write_text` truncates the target and then writes into it, so a crash, a full disk
    or a kill signal partway leaves a SHORT FILE where a complete one should be. That
    matters here more than in most places, because `--resume` treats the presence of
    an output file as proof the item is done: a half-written output is replayed as if
    it were the model's answer, and scored. The failure looks like a bad answer rather
    than a broken file.

    `os.replace` is atomic on POSIX and on Windows, so a reader sees either the old
    file or the whole new one and never a partial. The temp file is created in the
    same directory because rename is only atomic within a filesystem.
    """
    _write_atomic(path, text, "w")


def write_bytes_atomic(path: Path, data: bytes) -> None:
    """`write_text_atomic` for bytes: a reader sees the old file or the whole new one."""
    _write_atomic(path, data, "wb")


def _write_atomic(path: Path, data: str | bytes, mode: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, mode, encoding=None if "b" in mode else "utf-8") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json(path: Path, obj: Any) -> None:
    """Write an object as formatted JSON to a file atomically."""
    write_text_atomic(path, json.dumps(obj, indent=2, sort_keys=True) + "\n")


def build_info() -> dict[str, Any]:
    """Identify the SYSTEM UNDER TEST.

    Three inputs decide what an eval means: the system under test, the
    instrument (this harness), and the data (`dataset_id`). Record the first
    here, or a delta cannot be attributed to a code change rather than an
    instrument change.

    Replace this with whatever identifies YOUR system — a package version, an
    image digest, a model id. The git SHA is only the default because most
    skeletons start life inside a repo.
    """
    # A drop-in often lives outside a git repo — a copied directory, a mounted
    # folder, a container. The first cold walk of this skeleton produced four
    # runs with ref="unknown" for exactly that reason, and `make validate`
    # (correctly) refused them. So identity is CONFIGURABLE, not code:
    #
    #     EVAL_BUILD_REF=v2.3.1              a release
    #     EVAL_BUILD_REF=sha256:ab12…        an image digest
    #     EVAL_BUILD_REF=$(pip show pkg …)   an installed version
    #
    # Falling back to this tree's git SHA only when nothing is declared.
    import os  # noqa: PLC0415

    declared = os.environ.get("EVAL_BUILD_REF")
    if declared:
        # `dirty` was hardcoded False here, which asserts "the thing under test was built
        # from a clean tree" on zero evidence -- we are being handed a string by an
        # environment variable and cannot see the tree it came from. None means unknown,
        # and unknown is the truth. It also sat in the same run record as
        # `instrument.harness.dirty: true`, two flags with the same name meaning different
        # things and appearing to contradict each other.
        return {"ref": declared, "dirty": None, "source": "EVAL_BUILD_REF"}

    def git(*args: str) -> str | None:
        try:
            out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=5)
            return out.stdout.strip() if out.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None

    ref = git("rev-parse", "HEAD")
    # The same rule as the instrument's flag: untracked run output is not code, so a
    # previous run's directory no longer marks the next run dirty. One rule, one place.
    from _fingerprint import tree_dirt  # noqa: PLC0415

    dirt = tree_dirt(ROOT, DATA)
    return {
        "ref": ref or "unknown",
        "dirty": bool(dirt),
        "source": "git",
    }


def load_goals() -> dict[str, dict[str, Any]]:
    """{goal_id: goal} from data/goals/*.yaml (policy.yaml is the policy, not a goal)."""
    import yaml  # noqa: PLC0415

    out: dict[str, dict[str, Any]] = {}
    for f in sorted(GOALS.glob("*.yaml")):
        if f.name != "policy.yaml":
            doc = yaml.safe_load(f.read_text(encoding="utf-8"))
            out[f.stem] = doc if isinstance(doc, dict) else {}
    return out


def goal_policy() -> dict[str, Any]:
    """data/goals/policy.yaml: `required_from: YYYY-MM-DD`, the date from which every run must
    name a goal. Absent, goals stay optional: a project upgrading changes nothing until it
    sets the date."""
    import yaml  # noqa: PLC0415

    f = GOALS / "policy.yaml"
    doc = yaml.safe_load(f.read_text(encoding="utf-8")) if f.is_file() else None
    return doc if isinstance(doc, dict) else {}


def load_dataset(dataset_id: str) -> dict[str, Any]:
    """Load a dataset by id from data/datasets, or raise SystemExit."""
    path = DATASETS / f"{dataset_id}.json"
    if not path.is_file():
        raise SystemExit(
            f"no such dataset: {dataset_id}\n"
            f"  expected {path}\n"
            f"  create one with: "
            + how(
                f"evh dataset-create --dataset-id {dataset_id} --source-dir …",
                f"make dataset-create DATASET_ID={dataset_id}",
            )
        )
    return read_json(path)


def dataset_item_ids(dataset_id: str) -> set:
    """The item ids a dataset freezes, read from its dataset file.

    Commands that exclude a dev slice (`--exclude-dataset`) used to glob
    `data/sources/<id>/*.txt` instead: empty for an item that is not a .txt file, for a
    dataset built from a manifest, and for a project whose sources live elsewhere, and
    "nothing excluded" was then reported as if it were true."""
    return {it["item_id"] for it in load_dataset(dataset_id).get("items") or []}


def read_item_ids(path: Path) -> set[str]:
    """The item ids an `--items` file lists, one per line (blank lines ignored)."""
    return {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()}


def item_selection(exclude_dataset: str | None, items_file: Path | None) -> tuple[set[str], set[str] | None]:
    """(drop, keep) for `--exclude-dataset` and `--items`: the ids another dataset contains, and
    the only ids to use (None: no restriction)."""
    drop = dataset_item_ids(exclude_dataset) if exclude_dataset else set()
    return drop, (read_item_ids(items_file) if items_file else None)


def item_path(dataset_id: str, item_id: str) -> Path | None:
    """Where an item's materialized copy is, or None when it is not materialized here."""
    try:
        ds = load_dataset(dataset_id)
    except SystemExit:
        return None
    it = next((x for x in ds.get("items") or [] if x.get("item_id") == item_id), None)
    if it is None:
        return None
    p = MATERIALIZED / dataset_id / (it.get("source_path") or item_id)
    return p if p.is_file() else None


#: The id a run records when it used the adapter bundled with the harness.
BUNDLED_ADAPTER_ID = "scripts/adapter.py"


def in_checkout() -> bool:
    """Whether this is a checkout of the eval-harness repository with its own data, rather
    than the package installed in a project. Only then do `<root>/..` and `<root>/../examples`
    mean anything: in a project, the root's parent is whatever directory the project sits in."""
    return (ROOT / "scripts").resolve() == CODE


def adapter_search_dirs() -> tuple[Path, ...]:
    """Where a recorded adapter id is looked for: the project, and in a checkout its parent
    and examples/ (the ids the examples record)."""
    return (ROOT, ROOT.parent, ROOT.parent / "examples") if in_checkout() else (ROOT,)


def resolve_adapter_path(spec: str | None) -> Path | None:
    """The file a run's recorded adapter id names, or None.

    Looked for under the project, its parent and `examples/` beside it (a checkout's
    layout), and, for the bundled adapter's id, in the package itself: a project that pins
    the package has no `scripts/adapter.py`, and every lookup that stopped at the project
    failed for it (rescore, silver-calibrate, the leaderboard's metric kinds, run-compare,
    the classification report's label parser)."""
    if not spec:
        return None
    # The bundled id names the package's own copy wherever a project runs it; a stray
    # `scripts/adapter.py` under the project is not the code that ran.
    if spec == BUNDLED_ADAPTER_ID and not in_checkout() and (CODE / "adapter.py").is_file():
        return CODE / "adapter.py"
    for base in adapter_search_dirs():
        cand = Path(spec) if Path(spec).is_absolute() else base / spec
        if cand.is_file():
            return cand
    if spec == BUNDLED_ADAPTER_ID and (CODE / "adapter.py").is_file():
        return CODE / "adapter.py"
    return None


class ModuleNotLoadable(ImportError):
    """The file cannot be loaded as a module at all (no import spec for it)."""


def load_module(path: Path, name: str) -> Any:
    """Import the file at `path` as module `name`. It is registered in sys.modules BEFORE it
    runs, because a module-level @dataclass resolves its own module through sys.modules and an
    unregistered one makes that None. ModuleNotLoadable when there is no spec for the file;
    anything the module raises while running propagates."""
    import importlib.util  # noqa: PLC0415
    import sys  # noqa: PLC0415

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ModuleNotLoadable(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def die(msg: str) -> NoReturn:
    """Refuse: `ERROR: msg` on stderr, exit 1. Every command refuses this way; four printed
    their refusal to stdout instead, where a caller reading stderr saw nothing."""
    raise SystemExit(f"ERROR: {msg}")


def no_options(doc: str | None, *flags: str) -> Any:
    """The command line of a command that takes no arguments but `flags` (each an on/off
    switch): -h/--help prints `doc`, anything else is refused with exit 2. Seven commands
    checked for --help by hand and ignored every other argument, so `evh validate --strict`
    ran the plain validation and said nothing."""
    import argparse  # noqa: PLC0415

    ap = argparse.ArgumentParser(description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)
    for flag in flags:
        ap.add_argument(flag, action="store_true")
    return ap.parse_args()


# ── what a metric MEANS ──────────────────────────────────────────────────────
# These lived in leaderboard.py, which used them to pick a sort key and to warn
# when someone ranked on a descriptive metric. compare_runs.py had no idea they
# existed and judged every metric with one hardcoded direction:
#
#     verdict = "better" if d > 0 else "worse"
#
# So a run that got FASTER was reported "worse", and one that got more EXPENSIVE
# would have been reported "better". Two scripts in the same harness disagreed
# about what a number means, which is worse than either being wrong alone —
# whichever one you read last is the one you believe.

#: Lower is better. Cost and token counts.
COST_KEYS = (
    "total_cost_usd",
    "cost_usd",
    "total_tokens_in",
    "total_tokens_out",
    "tokens_in",
    "tokens_out",
)
#: Lower is better. Wall time.
SPEED_KEYS = ("latency_ms",)
#: Neither better nor worse: they say what the output WAS, not whether it was
#: good. Ranking by one puts the most verbose arm on top — which is how a
#: leaderboard ends up confidently answering the wrong question. Comparing two
#: of them and calling the bigger one "better" is the same error, per-metric.
DESCRIPTIVE_KEYS = ("output_words", "output_chars", "lines", "chars", "n_items")


#: Per-item columns a run records that are bookkeeping, not a measurement: judge_score marks
#: whether each judge shares the judged arm's model family (`self_family_<judge>`). The catalog
#: lists no metric for them; the judging summary reads them.
BOOKKEEPING_PREFIXES = ("self_family_",)


def lower_is_better(metric: str) -> bool:
    """Whether a DECREASE in ``metric`` is an improvement (cost, tokens, latency)."""
    return metric in COST_KEYS or metric in SPEED_KEYS or metric.startswith("total_tokens")


def is_descriptive(metric: str) -> bool:
    """Whether ``metric`` describes the output rather than judging it.

    A direction cannot be assigned to these, so callers must say "changed"
    rather than "better" or "worse".
    """
    return metric in DESCRIPTIVE_KEYS


def verdict_for(metric: str, delta: float, kinds: dict[str, str] | None = None) -> str:
    """ "better" / "worse" / "changed" / "identical" for ``delta`` on ``metric``.

    The one place that decides what a movement MEANS. Descriptive metrics get
    "changed" on purpose: calling a longer output "better" is a claim the number
    cannot support, and it is exactly the claim a reader will take away.
    """
    if delta == 0:
        return "identical"
    # An adapter's own declaration wins over the built-in table, which only knows the
    # metrics the bundled adapter emits. Callers pass the `metric_kinds` recorded in the
    # run; without it every example metric was judged by the sign of the delta alone.
    declared = (kinds or {}).get(metric)
    if declared == "descriptive" or (declared is None and is_descriptive(metric)):
        return "changed"
    improved = delta < 0 if lower_is_better(metric) else delta > 0
    return "better" if improved else "worse"


def classify_metrics(extra_kinds: dict[str, str] | None = None) -> dict[str, str]:
    """metric -> "cost" | "speed" | "descriptive" | "quality", with adapter overrides.

    The built-in tuples only know the metrics the bundled adapter emits. An example that
    brings its own scorer brings its own vocabulary — `compression`, `length_vs_reference`,
    `summary_words` are descriptive; `grounding` and `rouge*` are quality — and the core
    cannot know that.

    It showed up as a wrong answer rather than a missing feature: the first real sweep
    ranked ten models by `compression`, because the sort key defaults to the first metric
    not otherwise classified and `compression` sorts before `grounding` and `rouge1`. The
    leaderboard's own "you are ranking on a descriptive metric" warning stayed silent,
    because by its tuples compression was a quality metric.
    """
    kinds: dict[str, str] = {}
    for k in COST_KEYS:
        kinds[k] = "cost"
    for k in SPEED_KEYS:
        kinds[k] = "speed"
    for k in DESCRIPTIVE_KEYS:
        kinds[k] = "descriptive"
    if extra_kinds:
        kinds.update(extra_kinds)
    return kinds
