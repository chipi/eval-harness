"""Shared helpers: paths and environment, metric semantics, adapter resolution, run grouping."""

from __future__ import annotations

import sys as _sys
from collections import OrderedDict
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import functools
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

#: Where the harness CODE lives: this directory. Schemas and sibling scripts are found
#: relative to it, so they travel with the code whether it runs from a checkout or from an
#: installed package.
CODE = Path(__file__).resolve().parent


@functools.cache
def project_root() -> Path:
    """Where the PROJECT lives: its data/, its .env, its git history.

    Run from a checkout of eval-harness, that is the harness/ directory beside this one,
    as it always was. Installed as a package (`pip install evaluation-harness @ git+...`), the code sits in
    site-packages and the project is wherever the user is working: `EVAL_HOME` if set, else
    the nearest directory from here up that has a `data/` folder (what `evh init` makes), so
    a command run from a subfolder finds its project; else the current directory. Kept apart
    from CODE because a project that depends on the harness must never write its data into
    site-packages.

    Resolved on first use, not at import: a program that imports the harness as a library
    (an adapter, a notebook) can set `EVAL_HOME` or change directory first.
    """
    home = os.environ.get("EVAL_HOME", "").strip()
    if home:
        return Path(home).expanduser().resolve()
    checkout = CODE.parent
    if (checkout / "data").is_dir() and (checkout / "scripts").resolve() == CODE:
        return checkout
    here = Path.cwd().resolve()
    return next((d for d in (here, *here.parents) if (d / "data").is_dir()), here)


#: Where a project's own ports start (ADR-0024): catalog-serve in 18000-18999, mcp --http in 19000-19999, the same
#: offset in each, so a project's two servers read as a pair.
PORT_BASE = {"catalog": 18000, "mcp": 19000}


def port_offset(root: Path) -> int:
    """Where in each port range a project's servers sit: from its root's resolved path, 0 to 999."""
    return int(hashlib.sha256(str(root.resolve()).encode()).hexdigest(), 16) % 1000


def project_port(kind: str, root: Path | None = None) -> int:
    """A port of the project's own for a local server (ADR-0024): the offset of its root's path in the kind's
    range, so the same project gets the same URL every time and two projects do not take one port; the next free
    one when another program holds it."""
    base = PORT_BASE[kind]
    off = port_offset(root or project_root())
    for k in range(1000):
        port = base + (off + k) % 1000
        with socket.socket() as s:
            # As the servers bind (HTTPServer's allow_reuse_address): a port a stopped server left in TIME_WAIT
            # is still the project's; one another program listens on is not.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    die(f"no free port in {base}-{base + 999}: pass --port N", "failed")


def stray_home() -> str:
    """A warning when EVAL_HOME names one project and the folder you are in belongs to another (ADR-0024): a
    shell left pointing at a project would otherwise send every command there without a word; "" otherwise."""
    home = os.environ.get("EVAL_HOME", "").strip()
    if not home:
        return ""
    here = Path.cwd().resolve()
    mine = next((d for d in (here, *here.parents) if (d / "data").is_dir()), None)
    target = Path(home).expanduser().resolve()
    if mine is None or mine == target:
        return ""
    return f"note: EVAL_HOME is {target}, so this command acts on that project, not on {mine} where you are"


def how(evh: str, make: str) -> str:
    """The command a hint should name: `evh …` when the harness runs as the installed tool,
    the Makefile target in a checkout. A pinned project has no Makefile, so a `make …` hint
    sends its user to a command that does not exist."""
    return evh if os.environ.get("EVAL_VIA_EVH") else make


def load_dotenv(path: Path | None = None) -> int:
    """Read `.env` into the environment. No dependency, no surprises.

    Loaded when a harness command starts (below), so keys are never exported by hand and
    never pasted into a command that lands in shell history. An already-exported variable
    WINS — so `ANTHROPIC_API_KEY=... make run` overrides the file for one call
    without editing it.

    Create `.env` in the project with the keys your providers read (`evh env-check` lists
    them). `evh init` gitignores it.
    """
    env_path = path or (project_root() / ".env")
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


def _is_harness_command() -> bool:
    """Whether this process is one of the harness's own commands: a script in this directory
    run directly (the Makefile) or through `evh` (which points argv[0] at the script before
    running it). Importing the package from anything else changes no one's environment."""
    return bool(sys.argv and sys.argv[0]) and Path(sys.argv[0]).resolve().parent == CODE


#: How many variables `.env` set when this command started; 0 for a library import.
DOTENV_LOADED = load_dotenv() if _is_harness_command() else 0


def env_float(name: str, default: float | None = None) -> float | None:
    """Parse an environment variable as a float, or return the default."""

    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        die(f"{name}={raw!r} is not a number", "not-configured")


def env_int(name: str, default: int) -> int:
    """Parse an environment variable as an integer, or return the default."""
    v = env_float(name, float(default))
    return int(v) if v is not None else default


@functools.cache
def _paths() -> dict[str, Path]:
    root = project_root()
    # The data root. `EVAL_DATA_DIR` moves it, for a project whose own layout puts the
    # harness's records somewhere other than <project>/data (a relative path is taken from
    # the project root). Everything below is derived from it.
    data_override = os.environ.get("EVAL_DATA_DIR", "").strip()
    data = (root / Path(data_override).expanduser()).resolve() if data_override else root / "data"
    # Where run artifacts land. Redirectable via EVAL_RUNS_DIR so a throwaway pass -- a
    # smoke check after a harness change -- cannot add repeats to the arms of a real sweep
    # and silently move numbers that have already been reported. ONLY runs are redirected:
    # sources, datasets and references stay shared, so a smoke run is scored against the
    # same references as the real thing and is therefore actually a check of the real path.
    # Relative to the PROJECT root, as EVAL_DATA_DIR is.
    runs_override = os.environ.get("EVAL_RUNS_DIR", "").strip()
    # Goals can live outside the data root: a project whose harness records sit in a
    # subdirectory keeps one copy of its goals where the rest of its tooling reads them.
    # Relative to the project root, as EVAL_RUNS_DIR is.
    goals_override = os.environ.get("EVAL_GOALS_DIR", "").strip()
    return {
        "ROOT": root,
        "DATA": data,
        "SOURCES": data / "sources",
        "DATASETS": data / "datasets",
        "MATERIALIZED": data / "materialized",
        "CONFIGS": data / "configs",
        "RUNS": root / Path(runs_override).expanduser() if runs_override else data / "runs",
        "BASELINES": data / "baselines",
        "REFERENCES": data / "references",
        # What each evaluation is FOR (ADR-0002): one <goal_id>.yaml per goal, plus policy.yaml.
        "GOALS": root / Path(goals_override).expanduser() if goals_override else data / "goals",
        # Field sets (ADR-0003): one <fieldset_id>.yaml each, declaring the fields items may carry.
        "FIELDS": data / "fields",
        # Eval rounds (ADR-0004), optional: data/rounds/<goal_id>/<round_id>.yaml.
        "ROUNDS": data / "rounds",
        # Items fetched from a source_url, by their sha256. Derived and gitignored, like materialized/.
        "ITEM_CACHE": root / ".cache" / "items",
        # Captures from production systems (RFC-019): data/captures/<capture_id>/.
        "CAPTURES": data / "captures",
        # Label sets (RFC-023): data/labels/<dataset>/<set>/, what is right for an item and who said it.
        "LABELS": data / "labels",
    }


# The project's paths, read as module attributes (`_common.DATA`, `from _common import DATA`)
# and resolved on the first read, after `.env` has had its say on EVAL_DATA_DIR/EVAL_RUNS_DIR.
ROOT: Path
DATA: Path
SOURCES: Path
DATASETS: Path
MATERIALIZED: Path
CONFIGS: Path
RUNS: Path
BASELINES: Path
REFERENCES: Path
GOALS: Path
FIELDS: Path
ROUNDS: Path
ITEM_CACHE: Path
CAPTURES: Path
LABELS: Path


def __getattr__(name: str) -> Path:
    # The name is checked before anything resolves: `from _common import x` probes
    # `__path__` through here, and that probe must not fix the project's paths.
    if not (name.isupper() and name in __annotations__):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return _paths()[name]


#: The JSON Schemas the harness validates against. Inside the installed package they sit
#: beside the code; in a checkout they are one level up, in harness/schemas.
SCHEMAS = next(
    (p for p in (CODE / "schemas", CODE.parent / "schemas") if p.is_dir()), CODE.parent / "schemas"
)


def data_rel(path: Path) -> str:
    """`path` relative to the project root, as git and the run records spell it. Falls
    back to the absolute path when the data root sits outside the project."""
    try:
        return Path(path).resolve().relative_to(project_root()).as_posix()
    except ValueError:
        return str(Path(path).resolve())


def _report_spent() -> None:
    from evaluation_harness import _spend  # noqa: PLC0415

    _spend._report()


#: Where this process writes what it spent at exit, when a command that runs others (sweep, model-onboard) asked;
#: taken out of the environment so a process this one starts does not write over it.
SPENT_TO = os.environ.pop("EVH_SPENT_TO", "")
if SPENT_TO:
    # Said however the command ends, a refusal before any call included (RFC-026 step 5): 0 then, not all it was
    # given.
    import atexit

    atexit.register(_report_spent)


class CostCapExceeded(RuntimeError):
    """Raised mid-run when EVAL_MAX_COST_USD is reached.

    Deliberately an abort rather than a pre-flight estimate: estimates are
    usually wrong (token counts vary, cache hits change pricing), and an abort
    stops the bill the moment the cap is hit. Callers catch it and write
    whatever they have, so a capped run still yields a usable partial report.
    """


def ignored_by_git(path: Path) -> bool:
    """Whether git ignores `path` (a runs directory, say): runs written there are not committed, and a
    published catalog, which copies only what git tracks, will not show them. False outside a checkout."""
    import subprocess  # noqa: PLC0415

    # A run's metrics file, not the directory: the re-allow blocks admit `<dir>/<run>/metrics.json`
    # under a denied `data/runs-*/`, so only that path answers the question. Absolute, because `-C`
    # moves git's working directory and a relative probe would then name some other file.
    target = Path(path).resolve()
    # In the database a run's place is its key under data/, wherever the database file is (a copy under .build/,
    # make serve STORE=sqlite): asked as the project's own data/<key>, a copy shows what the project shows.
    data = _paths()["DATA"].resolve()
    if store() == "sqlite" and target.is_relative_to(data):
        target = _paths()["ROOT"].resolve() / "data" / target.relative_to(data)
    probe = target / "_probe_run" / "metrics.json"
    anchor = next((p for p in probe.parents if p.exists()), Path.cwd())
    try:
        r = subprocess.run(
            ["git", "-C", str(anchor), "check-ignore", "-q", str(probe)], capture_output=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


#: Directory names that are throwaway by convention (.gitignore denies them by glob): writing there is the point.
THROWAWAY_RUNS = ("runs-smoke", "runs-tune")


def warn_if_ignored(runs_dir: Path, data_dir: Path | None = None) -> None:
    """Say, loudly, when runs are about to land where they will not be kept or read: a directory git ignores, or
    one outside the project's data (`data_dir`, default the project's). Silent for the throwaway directories
    (runs-smoke*, runs-tune*), where not keeping them is the intent."""
    runs_dir = Path(runs_dir)
    if runs_dir.name.startswith(THROWAWAY_RUNS):
        return
    where = Path(data_dir) if data_dir else _paths()["DATA"]
    outside = not runs_dir.resolve().is_relative_to(where.resolve())
    if not outside and not ignored_by_git(runs_dir):
        return
    why = (
        f"is outside the project's data ({where}): no catalog, goal or validate reads it"
        if outside
        else "is ignored by git: its runs are not committed, so no clone, CI run or catalog (this one included) has them"
    )
    print(
        f"  WARNING: {runs_dir} {why}. Measured runs go in data/runs (the default: leave EVAL_RUNS_DIR unset). "
        "A derived set (re-scored, re-judged) keeps the measured runs' config_ids, so it needs its own "
        "data/runs-<name> directory, re-allowed in .gitignore beside the others under '--- re-allowed'. Throwaway "
        "passes go in data/runs-smoke*."
    )


def now() -> str:
    """Return the current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file's contents."""
    from evaluation_harness import _store  # noqa: PLC0415

    h = hashlib.sha256()
    with _store.open_file(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Any:
    """Parse and return the JSON object from a file."""
    from evaluation_harness import _store  # noqa: PLC0415

    return json.loads(_store.read_text(path, encoding="utf-8"))


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
    from evaluation_harness import _store  # noqa: PLC0415

    if (
        _store.rel(path) is not None
    ):  # RFC-025: the sqlite store writes one committed statement, atomic already
        _store.write_bytes(path, data.encode("utf-8") if isinstance(data, str) else data)
        return
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
            out = subprocess.run(
                ["git", *args], cwd=project_root(), capture_output=True, text=True, timeout=5
            )
            return out.stdout.strip() if out.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None

    ref = git("rev-parse", "HEAD")
    # The same rule as the instrument's flag: untracked run output is not code, so a
    # previous run's directory no longer marks the next run dirty. One rule, one place.
    from evaluation_harness._fingerprint import tree_dirt  # noqa: PLC0415

    dirt = tree_dirt(project_root(), _paths()["DATA"])
    return {
        "ref": ref or "unknown",
        "dirty": bool(dirt),
        "source": "git",
    }


def arm_config_files() -> list[Path]:
    """Every arm config of the project: data/configs, and the globs `configs` in <data>/validate.json names
    (relative to the project root), for a project that keeps its arms elsewhere (this repository's are in
    examples/). Here, not in validate_tree, because measuring code reads it (a hypothesis's `against`) and
    the validator is not part of what a run's code hash covers."""
    from evaluation_harness import _store  # noqa: PLC0415

    p = _paths()
    found = set(_store.glob(p["CONFIGS"], "*.yaml"))
    # A study's trials (RFC-029): written once under data/studies/<goal>/<study>/, found like any config.
    studies = p["DATA"] / "studies"
    if _store.is_dir(studies):
        found |= {f for f in _store.glob(studies, "*/*/t*.yaml") if _store.is_file(f)}
        found |= {f for f in _store.glob(studies, "*/*/confirm/*.yaml") if _store.is_file(f)}
    policy_file = p["DATA"] / "validate.json"
    for pattern in (read_json(policy_file).get("configs") or []) if _store.is_file(policy_file) else []:
        found |= {f for f in _store.glob(p["ROOT"], pattern) if _store.is_file(f)}
    return sorted(found)


#: {goals dir: (each goal file's (name, mtime_ns, size), the goals)}: the inspector asks for the goals on every
#: comparison (a goal's cluster field, ADR-0002), and parsing every goal's YAML each time was 32 ms of each answer
#: (budget-check, 2026-11-06). Read again when a goal file is added, removed or changed.
_GOALS_READ: dict[str, tuple[tuple, dict[str, dict[str, Any]]]] = {}


def load_goals(goals_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """{goal_id: goal} from <data>/goals/*.yaml (policy.yaml is the policy, not a goal), keyed
    by the goal's `goal_id`, the file stem when it names none. The catalog keyed them that way
    and this by stem alone; V14 requires the two to agree."""
    import copy  # noqa: PLC0415

    import yaml  # noqa: PLC0415
    from evaluation_harness import _store  # noqa: PLC0415

    base = goals_dir or _paths()["GOALS"]
    files = (
        [f for f in sorted(_store.glob(base, "*.yaml")) if f.name != "policy.yaml"]
        if _store.is_dir(base)
        else []
    )
    stamps = tuple((f.name, _store.stat(f).st_mtime_ns, _store.stat(f).st_size) for f in files)
    hit = _GOALS_READ.get(str(base))
    if hit is None or hit[0] != stamps:
        out: dict[str, dict[str, Any]] = {}
        for f in files:
            doc = yaml.safe_load(_store.read_text(f, encoding="utf-8"))
            doc = doc if isinstance(doc, dict) else {}
            out[str(doc.get("goal_id") or f.stem)] = doc
        hit = _GOALS_READ[str(base)] = (stamps, out)
    return copy.deepcopy(hit[1])


def goal_policy() -> dict[str, Any]:
    """data/goals/policy.yaml: `required_from: YYYY-MM-DD`, the date from which every run must
    name a goal. Absent, goals stay optional: a project upgrading changes nothing until it
    sets the date."""
    import yaml  # noqa: PLC0415
    from evaluation_harness import _store  # noqa: PLC0415

    f = _paths()["GOALS"] / "policy.yaml"
    doc = yaml.safe_load(_store.read_text(f, encoding="utf-8")) if _store.is_file(f) else None
    return doc if isinstance(doc, dict) else {}


#: A dataset id: a file name under data/, never a path (`../x` or `/etc/x` would read outside it).
DATASET_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def dataset_id_ok(dataset_id: str) -> str:
    """The id, or SystemExit when it is not a plain name (a path would leave data/)."""
    if not DATASET_ID.fullmatch(dataset_id or "") or ".." in dataset_id:
        die(f"not a dataset id: {dataset_id[:60]!r} (letters, digits, '.', '_', '-')", "bad-argument")
    return dataset_id


def load_dataset(dataset_id: str) -> dict[str, Any]:
    """Load a dataset by id from data/datasets, or raise SystemExit."""
    from evaluation_harness import _store  # noqa: PLC0415

    path = _paths()["DATASETS"] / f"{dataset_id_ok(dataset_id)}.json"
    if not _store.is_file(path):
        die(
            f"no such dataset: {dataset_id}\n"
            f"  expected {path}\n"
            f"  create one with: "
            + how(
                f"evh dataset-create --dataset-id {dataset_id} --source-dir …",
                f"make dataset-create DATASET_ID={dataset_id}",
            ),
            "not-found",
        )
    return read_json(path)


def goal_cluster(goal: dict, dataset_id: str) -> str | None:
    """The item field a goal clusters this dataset's tests by (`datasets[].cluster`), or None."""
    return next(
        (d.get("cluster") for d in goal.get("datasets") or [] if d.get("dataset_id") == dataset_id), None
    )


def item_clusters(dataset_id: str, field: str) -> dict:
    """{item_id: cluster key}: each item's value of `field`, for the clustered paired test
    (stats.clustered). Refused when no item carries the field: a typo would test item by item."""
    keys = {
        it["item_id"]: (it.get("fields") or {}).get(field)
        for it in load_dataset(dataset_id).get("items") or []
    }
    keys = {i: v for i, v in keys.items() if v not in (None, "")}
    if not keys:
        die(
            f"--cluster {field}: no item of {dataset_id} carries that field (evh dataset-profile lists them)",
            "not-found",
        )
    return keys


def dataset_item_ids(dataset_id: str) -> set:
    """The item ids a dataset freezes, read from its dataset file.

    Commands that exclude a pilot slice (`--exclude-dataset`) used to glob
    `data/sources/<id>/*.txt` instead: empty for an item that is not a .txt file, for a
    dataset built from a manifest, and for a project whose sources live elsewhere, and
    "nothing excluded" was then reported as if it were true."""
    return {it["item_id"] for it in load_dataset(dataset_id).get("items") or []}


def read_item_ids(path: Path) -> set[str]:
    """The item ids an `--items` file lists, one per line (blank lines ignored)."""
    from evaluation_harness import _store  # noqa: PLC0415

    return {ln.strip() for ln in _store.read_text(path, encoding="utf-8").splitlines() if ln.strip()}


def item_selection(exclude_dataset: str | None, items_file: Path | None) -> tuple[set[str], set[str] | None]:
    """(drop, keep) for `--exclude-dataset` and `--items`: the ids another dataset contains, and
    the only ids to use (None: no restriction)."""
    drop = dataset_item_ids(exclude_dataset) if exclude_dataset else set()
    return drop, (read_item_ids(items_file) if items_file else None)


#: What a run scored against a label set records as its reference_id: "labels/<dataset>/<set>" (RFC-023), and as its
#: tier, so it is never read as gold or silver.
LABELS_PREFIX = "labels/"
LABELS_TIER = "labels"


def scored_against_dir(reference_id: str | None) -> Path | None:
    """Where what a run is scored against lives: a label set ("labels/<dataset>/<set>", under data/labels) or a
    reference ("<tier>/<name>", under data/references); None when it is scored against nothing."""
    if not reference_id:
        return None
    if reference_id.startswith(LABELS_PREFIX):
        return _paths()["LABELS"] / reference_id[len(LABELS_PREFIX) :]
    return _paths()["REFERENCES"] / reference_id


def labels_reference(spec: str, dataset_id: str) -> str:
    """The reference_id a run scored against labels records, from `SET` or `DATASET/SET`; refused when the set is on
    another dataset (its item ids are that dataset's) or does not exist."""
    from evaluation_harness import _store  # noqa: PLC0415

    set_ds, _, name = spec.rpartition("/")
    set_ds = set_ds or dataset_id
    if set_ds != dataset_id:
        die(
            f"--labels {spec}: a set on {set_ds}, not {dataset_id}. Scoring reads labels by this dataset's item ids: "
            f"promote them (evh reference-promote --dataset-id {dataset_id} --labels {spec} …) or label this dataset",
            "mismatch",
        )
    rid = f"{LABELS_PREFIX}{dataset_id}/{name}"
    d = scored_against_dir(rid)
    if d is None or not _store.is_file(d / "labels.json"):
        die(
            f"--labels {spec}: no label set at data/labels/{dataset_id}/{name} (evh labels --dataset-id {dataset_id})",
            "not-found",
        )
    return rid


#: Each dataset's items by id ({item_id: its file under materialized/<dataset>/}), kept while its record is unchanged
#: (path, mtime, size): a sheet asks for every item, and reading the record each time was quadratic (S1: 1,002 loads
#: of a 1,000-item record for one sheet). A few datasets at a time.
_ITEM_INDEX: OrderedDict[str, tuple[tuple, dict[str, str]]] = OrderedDict()
_ITEM_INDEX_MAX = 16


def _item_index(dataset_id: str) -> dict[str, str] | None:
    from evaluation_harness import _store  # noqa: PLC0415

    try:
        path = _paths()["DATASETS"] / f"{dataset_id_ok(dataset_id)}.json"
    except SystemExit:
        return None
    if not _store.is_file(path):
        return None
    st = _store.stat(path)
    stamp = (str(path), st.st_mtime_ns, st.st_size)
    hit = _ITEM_INDEX.get(dataset_id)
    if hit is not None and hit[0] == stamp:
        _ITEM_INDEX.move_to_end(dataset_id)
        return hit[1]
    try:
        ds = load_dataset(dataset_id)
    except SystemExit:
        return None
    index: dict[str, str] = {}
    for x in ds.get("items") or []:
        if x.get("item_id"):  # the first item with an id, as the search over the items found it
            index.setdefault(x["item_id"], x.get("source_path") or x["item_id"])
    _ITEM_INDEX[dataset_id] = (stamp, index)
    while len(_ITEM_INDEX) > _ITEM_INDEX_MAX:
        _ITEM_INDEX.popitem(last=False)
    return index


def item_path(dataset_id: str, item_id: str) -> Path | None:
    """Where an item's materialized copy is, or None when it is not materialized here."""
    from evaluation_harness import _store  # noqa: PLC0415

    index = _item_index(dataset_id)
    if index is None or item_id not in index:
        return None
    p = _paths()["MATERIALIZED"] / dataset_id / index[item_id]
    return p if _store.is_file(p) else None


#: The id a run records when it used the adapter bundled with the harness.
BUNDLED_ADAPTER_ID = "scripts/adapter.py"


def in_checkout() -> bool:
    """Whether this is a checkout of the eval-harness repository with its own data, rather
    than the package installed in a project. Only then do `<root>/..` and `<root>/../examples`
    mean anything: in a project, the root's parent is whatever directory the project sits in."""
    return (project_root() / "scripts").resolve() == CODE


def adapter_search_dirs() -> tuple[Path, ...]:
    """Where a recorded adapter id is looked for: the project, and in a checkout the
    repository root (the examples record `examples/<example>/adapter.py`)."""
    root = project_root()
    return (root, root.parent) if in_checkout() else (root,)


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
    import importlib.machinery  # noqa: PLC0415
    import importlib.util  # noqa: PLC0415
    import sys  # noqa: PLC0415

    class _FromSource(importlib.machinery.SourceFileLoader):
        # Compiled from the source every time, never from __pycache__: a .pyc is trusted while the source's
        # mtime (whole seconds) and size match, so a scorer edited within the second to a same-length value
        # (BONUS = 0.0 -> 0.5) ran its old code while the run recorded the new code's hash (RFC-022).
        def get_code(self, fullname):
            del fullname  # the loader passes it; the path is all this needs
            return compile(self.get_data(self.path), self.path, "exec", dont_inherit=True)

    loader = _FromSource(name, str(path)) if str(path).endswith(".py") else None
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    if spec is None or spec.loader is None:
        raise ModuleNotLoadable(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


#: Exit codes, one meaning each (RUNBOOK "Exit codes"), so a caller branches on the number and never
#: has to read the text: 2 was both a usage error and the cost cap, 1 both a refusal and "validate
#: found problems".
EXIT_OK = 0
EXIT_REFUSED = 1  # refused: `ERROR: <why>` on stderr, nothing done
EXIT_USAGE = 2  # an unknown command or argument; the usage is printed
EXIT_UNVALIDATED = 3  # a judge scorer that is not validated (--unvalidated runs it, labelled)
EXIT_STOPPED = 4  # stopped early (the cost cap, a failing judge call): partial results kept, resumable
EXIT_PARTLY = 5  # some of several runs failed (sweep); the others are kept
EXIT_PROBLEMS = 6  # the command's checks ran and some failed (validate, importer-check, arm-smoke, ...)
EXIT_NOTHING = 7  # it ran and measured nothing
EXIT_INTERNAL = 70  # an error nothing caught, in the harness or the project's code: a traceback on stderr
EXIT_TRY_LATER = 75  # a server could not be reached: run the same command again later, it resumes
EXIT_INTERRUPTED = 130  # Ctrl-C


#: What kind of refusal it is (RUNBOOK, Refusals): the word in `ERROR (<kind>): ...`, which a script or an
#: agent reads instead of the message, so a message can be reworded without breaking it.
REFUSALS = {
    "not-found": "the dataset, run, arm, goal, file or other thing named does not exist",
    "bad-argument": "an option is missing, malformed, or not allowed with another",
    "would-overwrite": "what it would write is already there; it is never overwritten",
    "mismatch": "two things that must agree do not: datasets, hashes, a run and its config",
    "invalid-file": "a file the project wrote (a config, a scorer, a sheet, records) is malformed",
    "not-materialized": "the data is not on this machine: fetch or materialize it first",
    "not-enough": "too little to work on: too few items, arms or outputs",
    "not-public": "the text asked for is not shown on a public server or for a hidden dataset",
    "not-allowed": "a rule refuses it: a dirty build, a closed round, a bind beyond this machine",
    "not-configured": "a key, a cost cap, a build ref or an endpoint is not set",
    "failed": "something outside the command failed: an importer, a server, a hook, the warm-up",
    "missing-dependency": "a package or a part of the installation is missing",
    "over-budget": "a round's budget is spent (what its runs spent and its running commands reserved)",
}


#: Where a project keeps its data (RFC-025): `files` (the default) or `sqlite` (everything under data/ in one database).
STORES = ("files", "sqlite")
_STORE_SEEN: list[Any] = []


def store() -> str:
    """The project's store: `EVAL_STORE`, else `store` in its config.yaml, else `files`."""
    env = os.environ.get("EVAL_STORE", "").strip()
    root = _paths()["ROOT"]
    # Asked for every path a reader touches (25,000 times a comparison), so the answer is kept for the process: a
    # stat of config.yaml on each call was 8 ms of every inspector answer (budget-check, 2026-11-06), and building the
    # config's path to compare was most of the 2.4 µs a call still cost (architecture review): the key is the
    # setting and the root object, which _paths keeps until the project moves. A project changes its store with
    # data-migrate, between processes; a test that rewrites config.yaml calls _outputs.reset(), which forgets it.
    if _STORE_SEEN and _STORE_SEEN[0] == env and _STORE_SEEN[1] is root:
        return str(_STORE_SEEN[2])
    cfg = root / "config.yaml"
    try:
        mtime = cfg.stat().st_mtime_ns if not env else None
    except OSError:
        mtime = None
    if env:
        chosen, where = env, "EVAL_STORE"
    else:
        chosen, where = "files", f"store in {cfg}"
        if mtime is not None:
            import yaml  # noqa: PLC0415

            try:
                doc = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                doc = {}
            chosen = str((doc.get("store") if isinstance(doc, dict) else None) or "files")
    if chosen not in STORES:
        said = f"{where}: {chosen!r} is not a store, one of {', '.join(STORES)}"
        if env:
            die(said, "bad-argument")
        die(said, "invalid-file")
    _STORE_SEEN[:] = [env, root, chosen]
    return chosen


def die(msg: str, kind: str) -> NoReturn:
    """Refuse: `ERROR (<kind>): msg` on stderr, exit 1, `kind` one of REFUSALS. Every command refuses
    this way; four printed their refusal to stdout instead, where a caller reading stderr saw nothing."""
    if kind not in REFUSALS:
        raise ValueError(f"no refusal kind {kind!r}: one of {', '.join(REFUSALS)}")
    raise SystemExit(f"ERROR ({kind}): {msg}")


def reference_texts(root: Path, dataset_id: str, tier: str = "gold") -> list[Path]:
    """A reference directory's item files, sorted. Refuses when the directory is missing, or holds
    only its manifest.json: a repository may commit a reference's checksums and not its texts
    (V16), which come with the public data. Read as empty, every arm matched nothing and the
    report tools printed zeros as if they were results."""
    from evaluation_harness import _store  # noqa: PLC0415

    if not _store.is_dir(root):
        die(f"no {tier} references at {root}", "not-found")
    files = sorted(_store.glob(root, "*.txt"))
    if not files and _store.is_file(root / "manifest.json"):
        die(
            f"the {tier} references for {dataset_id} are not on this machine: {root} holds their "
            "checksums only (manifest.json). Fetch the dataset first, as the eval's README and "
            "docs/REPRODUCE.md say (`make data EXP=<eval>`, or the example's fetch.py).",
            "not-materialized",
        )
    return files


def evh_prog() -> str | None:
    """`evh <command>` for the script running now, as `--help` should name it (None: argparse's
    own, the script's file name, for a script that is no evh command)."""
    import os  # noqa: PLC0415

    try:
        from evaluation_harness.cli import COMMANDS  # noqa: PLC0415
    except ImportError:
        return None
    me = os.path.basename(sys.argv[0] if sys.argv else "")
    return next((f"evh {name}" for name, (script, *_r) in COMMANDS.items() if script == me), None)


def no_options(doc: str | None, *flags: str) -> Any:
    """The command line of a command that takes no arguments but `flags` (each an on/off
    switch): -h/--help prints `doc`, anything else is refused with exit 2. Seven commands
    checked for --help by hand and ignored every other argument, so `evh validate --strict`
    ran the plain validation and said nothing."""
    import argparse  # noqa: PLC0415

    ap = argparse.ArgumentParser(
        prog=evh_prog(), description=doc, formatter_class=argparse.RawDescriptionHelpFormatter
    )
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
SPEED_KEYS = ("latency_ms", "latency_s")
#: Neither better nor worse: they say what the output WAS, not whether it was
#: good. Ranking by one puts the most verbose arm on top — which is how a
#: leaderboard ends up confidently answering the wrong question. Comparing two
#: of them and calling the bigger one "better" is the same error, per-metric.
#: `reasoning_tokens` too, as every committed run that records it declares: how long a model
#: thought, which its cost already counts.
DESCRIPTIVE_KEYS = ("output_words", "output_chars", "lines", "chars", "n_items", "reasoning_tokens")


#: Per-item columns a run records that are bookkeeping, not a measurement: judge_score marks
#: whether each judge shares the judged arm's model family (`self_family_<judge>`), and
#: evh run whether an item was replayed by --resume (`resumed`, whose mean is the share
#: replayed). They stay in the record; no table, menu or spread lists them as metrics.
BOOKKEEPING_PREFIXES = ("self_family_", "resumed", "failed")


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
