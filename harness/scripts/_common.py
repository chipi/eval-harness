"""Shared helpers. Deliberately tiny — the skeleton should be readable in one sitting."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, List

ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Optional[Path] = None) -> int:
    """Read `.env` into the environment. No dependency, no surprises.

    Loaded by every script, so keys are never exported by hand and never pasted
    into a command that lands in shell history. An already-exported variable
    WINS — so `ANTHROPIC_API_KEY=... make experiment-run` overrides the file
    for one call without editing it.

    Copy `.env.example` to `.env` to start. `.env` is gitignored.
    """
    import os

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


def env_float(name: str, default: Optional[float] = None) -> Optional[float]:
    import os

    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise SystemExit(f"ERROR: {name}={raw!r} is not a number")


def env_int(name: str, default: int) -> int:
    v = env_float(name, float(default))
    return int(v) if v is not None else default
DATA = ROOT / "data"
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
RUNS = Path(_runs_override).expanduser() if _runs_override else DATA / "runs"
BASELINES = DATA / "baselines"
REFERENCES = DATA / "references"


class CostCapExceeded(RuntimeError):
    """Raised mid-run when EVAL_MAX_COST_USD is reached.

    Deliberately an abort rather than a pre-flight estimate: estimates are
    usually wrong (token counts vary, cache hits change pricing), and an abort
    stops the bill the moment the cap is hit. Callers catch it and write
    whatever they have, so a capped run still yields a usable partial report.
    """


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> Any:
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
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
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
    write_text_atomic(path, json.dumps(obj, indent=2, sort_keys=True) + "\n")


def build_info() -> Dict[str, Any]:
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
    import os

    declared = os.environ.get("EVAL_BUILD_REF")
    if declared:
        # `dirty` was hardcoded False here, which asserts "the thing under test was built
        # from a clean tree" on zero evidence -- we are being handed a string by an
        # environment variable and cannot see the tree it came from. None means unknown,
        # and unknown is the truth. It also sat in the same run record as
        # `instrument.harness.dirty: true`, two flags with the same name meaning different
        # things and appearing to contradict each other.
        return {"ref": declared, "dirty": None, "source": "EVAL_BUILD_REF"}

    def git(*args: str) -> Optional[str]:
        try:
            out = subprocess.run(
                ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=5
            )
            return out.stdout.strip() if out.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None

    ref = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    return {
        "ref": ref or "unknown",
        "dirty": bool(status),
        "source": "git",
    }


def load_dataset(dataset_id: str) -> Dict[str, Any]:
    path = DATASETS / f"{dataset_id}.json"
    if not path.is_file():
        raise SystemExit(
            f"no such dataset: {dataset_id}\n"
            f"  expected {path}\n"
            f"  create one with: make dataset-create DATASET_ID={dataset_id}"
        )
    return read_json(path)


def iter_runs() -> Iterable[Path]:
    if not RUNS.is_dir():
        return []
    return sorted(p for p in RUNS.iterdir() if (p / "metrics.json").is_file())


def die(msg: str) -> "NoReturn":  # type: ignore[valid-type]
    raise SystemExit(f"ERROR: {msg}")


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


def lower_is_better(metric: str) -> bool:
    """Whether a DECREASE in ``metric`` is an improvement (cost, tokens, latency)."""
    return metric in COST_KEYS or metric in SPEED_KEYS or metric.startswith("total_tokens")


def is_descriptive(metric: str) -> bool:
    """Whether ``metric`` describes the output rather than judging it.

    A direction cannot be assigned to these, so callers must say "changed"
    rather than "better" or "worse".
    """
    return metric in DESCRIPTIVE_KEYS


def verdict_for(metric: str, delta: float,
                kinds: Optional[Dict[str, str]] = None) -> str:
    """"better" / "worse" / "changed" / "identical" for ``delta`` on ``metric``.

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


def classify_metrics(extra_kinds: Optional[Dict[str, str]] = None) -> Dict[str, str]:
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
    kinds: Dict[str, str] = {}
    for k in COST_KEYS:
        kinds[k] = "cost"
    for k in SPEED_KEYS:
        kinds[k] = "speed"
    for k in DESCRIPTIVE_KEYS:
        kinds[k] = "descriptive"
    if extra_kinds:
        kinds.update(extra_kinds)
    return kinds

class AmbiguousRuns(Exception):
    """Two runs claim the same config_id and nothing says which one to read."""


def runs_by_arm(base: Path, dataset_id: str, prefix: str = "",
                strip: str = "") -> Dict[str, List[Path]]:
    """config_id -> the run directories that produced it, deterministically ordered.

    WHY THIS EXISTS RATHER THAN A GLOB AT EACH CALL SITE.

    Five places in `check_report_claims.py` globbed for a run and took whichever came
    back -- three took the last hit, two the first, and one of them had a different
    exclusion rule from the others. That is fine while every config_id is unique. Three
    SciFact arms were re-run, so three were not, and the checker's answer then depended
    on the order the filesystem returned directories in: green on APFS, red on ext4.
    `make ci` was reported green for a week on the only machine anyone had run it on.

    REPEATS ARE NOT AMBIGUITY. `--repeat 3` writes `<id>_r1.._r3`, all one measurement
    of one arm, and averaging them is the point. Those come back together. Anything
    ELSE sharing a config_id is two different measurement occasions wearing one name,
    and this raises rather than picking one, because there is no correct pick.
    """
    groups: Dict[str, List[Path]] = {}
    for mj in sorted(base.glob("*/metrics.json")):
        try:
            m = json.loads(mj.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if m.get("dataset_id") != dataset_id:
            continue
        cid = m.get("config_id")
        if not cid or (prefix and not cid.startswith(prefix)):
            continue
        key = cid[len(prefix):] if prefix else cid
        if strip and key.endswith(strip):
            key = key[: -len(strip)]
        groups.setdefault(key, []).append(mj.parent)

    for key, dirs in groups.items():
        if len(dirs) < 2:
            continue
        # A repeat set: every directory is "<something>_rN" off the same stem.
        stems = {re.sub(r"_r\d+$", "", d.name) for d in dirs}
        if len(stems) == 1 and all(re.search(r"_r\d+$", d.name) for d in dirs):
            continue
        raise AmbiguousRuns(
            f"{len(dirs)} runs under {base.name}/ claim config_id {key!r} on "
            f"{dataset_id}: {sorted(d.name for d in dirs)}.\n"
            f"  These are different measurement occasions sharing one name, so any "
            f"tool reading them picks one by filesystem order.\n"
            f"  Move the ones that are not the record out of this directory "
            f"(data/runs-repeats/ is where the SciFact re-runs live)."
        )
    return {k: sorted(v) for k, v in sorted(groups.items())}
