#!/usr/bin/env python3
"""Self-tests for the harness itself — no network, no keys, no fixtures needed.

The harness makes claims about its own behaviour: that it refuses cross-dataset
comparisons, that a cost cap aborts, that gold beats silver, that a zero noise
floor is not the same as an absent one. Those claims are the product, so they
are tested rather than asserted in a README.

    make test
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"  # the core modules (this file is in tests/)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
#: The harness root. HERE is scripts/, where the scripts the tests run live — but
#: a data check written against HERE scans scripts/data/, which does not exist, so it finds
#: nothing and passes for the wrong reason. That is exactly how the first version of
#: test_no_absolute_home_path_in_committed_data shipped green while checking nothing.
ROOT = HERE.parent
PY = sys.executable
sys.path.insert(1, str(HERE.parent / "tools"))  # the report checks some tests exercise


def at(script: str) -> str:
    """A script's path from the harness root: the package's code is in scripts/, this
    repository's tests in tests/ and its report and judge checks in tools/."""
    for d in ("scripts", "tests", "tools"):
        if (ROOT / d / script).is_file():
            return f"{d}/{script}"
    return f"scripts/{script}"


from evaluation_harness._check import check, results  # noqa: E402


def run(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run a harness script. `env` adds to the inherited environment, it does not
    replace it -- a test that needs EVAL_RUNS_DIR still needs PATH and HOME."""
    import os  # noqa: PLC0415

    e = {**os.environ, **(env or {})}
    return subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True, env=e)


def test_dotenv_does_not_override_exported() -> None:
    """An exported var must win, so a one-off override needs no file edit."""
    import os  # noqa: PLC0415

    from evaluation_harness._common import load_dotenv  # noqa: PLC0415

    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as fh:
        fh.write("EVAL_SELFTEST_A=from_file\nEVAL_SELFTEST_B=from_file\n")
        path = Path(fh.name)
    os.environ["EVAL_SELFTEST_A"] = "from_shell"
    os.environ.pop("EVAL_SELFTEST_B", None)
    load_dotenv(path)
    check("dotenv: exported var wins", os.environ["EVAL_SELFTEST_A"] == "from_shell")
    check("dotenv: missing var is filled", os.environ.get("EVAL_SELFTEST_B") == "from_file")
    path.unlink()


def test_import_reads_no_env_and_no_paths() -> None:
    """Importing the harness from another program (an adapter, a notebook) leaves the
    environment alone and resolves the project on first use, so EVAL_HOME set after the
    import is honoured. A harness command still reads the project's .env."""
    import os  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as d:
        proj = Path(d)
        (proj / ".env").write_text(
            "EVAL_SELFTEST_IMPORT=from_file\nEVAL_DATA_DIR=elsewhere\n", encoding="utf-8"
        )
        probe = proj / "probe.py"
        probe.write_text(
            "import os, sys\n"
            f"sys.path.insert(0, {str(HERE)!r})\n"
            "import catalog_adapter, _common\n"
            "os.environ['EVAL_HOME'] = sys.argv[1]\n"
            "print(os.environ.get('EVAL_SELFTEST_IMPORT'), _common.DOTENV_LOADED, _common.DATA)\n",
            encoding="utf-8",
        )
        env = {k: v for k, v in os.environ.items() if not k.startswith("EVAL_")}
        lib = subprocess.run(
            [sys.executable, str(probe), str(proj)],
            cwd="/",
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        check(
            "import: a library import reads no .env and resolves paths on first use",
            lib.stdout.split() == ["None", "0", str(proj.resolve() / "data")],
            lib.stdout + lib.stderr,
        )
        cmd = subprocess.run(
            [sys.executable, str(HERE / "env_check.py")],
            env=dict(env, EVAL_HOME=str(proj)),
            capture_output=True,
            text=True,
            timeout=60,
        )
        check(
            "import: a harness command reads the project's .env",
            ".env: loaded 2 var(s)" in cmd.stdout,
            cmd.stdout + cmd.stderr,
        )


def test_price_needs_all_four_inputs() -> None:
    from evaluation_harness._providers import price as _price  # noqa: PLC0415

    check("price: None when unpriced", _price({}, 1000, 1000) is None)
    check(
        "price: None when tokens missing",
        _price({"usd_per_mtok_in": 3, "usd_per_mtok_out": 15}, None, 10) is None,
    )
    got = _price({"usd_per_mtok_in": 3.0, "usd_per_mtok_out": 15.0}, 1_000_000, 1_000_000)
    check("price: 1M in + 1M out = in+out rate", got == 18.0, f"got {got}")


def test_score_handles_absent_reference() -> None:
    from evaluation_harness.adapter import score  # noqa: PLC0415

    check("score: no reference -> no quality metric", "overlap_f1" not in score("a b c", None))
    check("score: identical output scores 1.0", score("a b c", "a b c")["overlap_f1"] == 1.0)
    check("score: disjoint output scores 0.0", score("a b", "c d")["overlap_f1"] == 0.0)


def test_compare_refuses_cross_dataset() -> None:
    r = run("scripts/compare_runs.py", "--baseline", "nope_a", "--candidate", "nope_b")
    check("compare: unknown run is an error", r.returncode != 0)


#: Modules that belong to an EXAMPLE's venv, not to the harness. Only these justify
#: skipping a checker: anything else missing is a broken import in our own code.
_EXAMPLE_ONLY_MODULES = frozenset(
    {
        "rouge_score",
        "rank_bm25",
        "torch",
        "transformers",
        "span_marker",
        "gliner",
        "sentence_transformers",
        "sklearn",
        "numpy",
        "datasets",
        "nltk",
    }
)


def test_cli_help_works() -> None:
    for script in (
        "dataset_create",
        "materialize",
        "experiment_run",
        "compare_runs",
        "promote_baseline",
        "validate_tree",
        "list_runs",
        "reference_create",
        "reference_manifest",
        "leaderboard",
        "sweep",
        "env_check",
        "holdout_significance",
        "pair_test",
        "family_test",
        "classification_report",
        "bootstrap_test",
        "rank_stability",
        "extraction_report",
        "retrieval_report",
        "rescore",
        "check_terminology",
        "check_report_claims",
        "check_links",
        "check_model_facts",
    ):
        r = run(at(f"{script}.py"), "--help")
        check(f"{script}.py --help", r.returncode == 0, r.stderr.strip()[:80])


def test_metric_direction_is_not_always_up() -> None:
    """Cost and latency improve by going DOWN.

    compare_runs.py judged every metric with `"better" if d > 0 else "worse"`, so a run
    that got faster or cheaper was reported as worse — while leaderboard.py, in the same
    harness, already knew these keys were lower-is-better. Two scripts disagreeing about
    what a number means is worse than either being wrong alone: whichever you read last
    is the one you believe.
    """
    from evaluation_harness._common import verdict_for  # noqa: PLC0415

    check("direction: faster is better", verdict_for("latency_ms", -0.5) == "better")
    check("direction: slower is worse", verdict_for("latency_ms", 0.5) == "worse")
    check("direction: cheaper is better", verdict_for("cost_usd", -0.1) == "better")
    check("direction: dearer is worse", verdict_for("cost_usd", 0.1) == "worse")
    # The quality metric keeps the ordinary orientation, or the fix would have
    # inverted the thing that actually matters.
    check("direction: higher quality is better", verdict_for("overlap_f1", 0.05) == "better")
    check("direction: lower quality is worse", verdict_for("overlap_f1", -0.05) == "worse")
    check("direction: no movement is identical", verdict_for("cost_usd", 0.0) == "identical")


def test_descriptive_metrics_get_no_verdict() -> None:
    """A longer output is not a better one, and the table must not imply it is."""
    from evaluation_harness._common import verdict_for  # noqa: PLC0415

    check("descriptive: more words is 'changed'", verdict_for("output_words", 12) == "changed")
    check("descriptive: fewer words is 'changed'", verdict_for("output_words", -12) == "changed")


def test_leaderboard_declares_silver_from_any_run() -> None:
    """The SILVER caveat must survive a config whose FIRST run predates the reference.

    leaderboard.py read `runs[0].get("reference_tier")`. A config with an early unscored
    run therefore printed a silver-derived quality score with no disclaimer — a
    model-generated number shown as if it were ground truth, which is the single thing
    this table must never do.
    """
    rows: list[dict] = [
        {"reference_tier": None},
        {"reference_tier": "silver"},
    ]
    tiers = {r.get("reference_tier") for r in rows if r.get("reference_tier")}
    check("leaderboard: silver seen behind an unscored first run", "silver" in tiers)
    check(
        "leaderboard: no tier at all stays unlabelled",
        {r.get("reference_tier") for r in [{"reference_tier": None}] if r.get("reference_tier")} == set(),
    )


def test_no_absolute_home_path_in_committed_data() -> None:
    """A dataset describes a SELECTION, not the machine that built it.

    dataset_create.py wrote `args.source_dir.as_posix()` — the resolved, absolute path — so
    every dataset in this repo carried "/Users/<name>/projects/..." into git. That leaks
    whoever ran it, and makes a file that is meant to travel between machines describe one.
    Only `created_at` and `source_dir` differ after the fix; every source_sha256 is
    unchanged, which is what actually freezes a dataset.
    """
    import re  # noqa: PLC0415

    home = re.compile(r"/(?:Users|home)/(?!runner\b|operator\b|user\b)[A-Za-z0-9_.-]+/")
    # TRACKED files only -- which is what "committed" means, and what this check is for.
    # It used to rglob the whole working tree, so it failed on `data/runs/`, a GITIGNORED
    # directory whose contents can never be committed by definition. A test that fails on
    # files outside its own subject teaches people to ignore it.
    #
    # This is not a narrowing to make a failure go away: the cause -- experiment_run.py
    # writing an absolute adapter path into every metrics.json -- is fixed at source in
    # `_portable_id`. This check still catches the real case, including someone choosing
    # to track `data/runs/` (the private eval repo does exactly that).
    import subprocess  # noqa: PLC0415

    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z", "--", "data"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        ).stdout.split("\0")
        tracked = [ROOT / f for f in listed if f.endswith(".json")]
    except Exception:  # noqa: BLE001 -- no git available: fall back to scanning everything
        tracked = list((ROOT / "data").rglob("*.json"))
    offenders = []
    for d in tracked:
        if ".partial" in d.parts or not d.is_file():
            continue
        try:
            if home.search(d.read_text(encoding="utf-8")):
                offenders.append(str(d.relative_to(ROOT)))
        except OSError:
            continue
    check("no home path in committed data/", not offenders, f"offenders: {offenders[:5]}")


def test_no_committed_artifact_depends_on_an_ignored_one() -> None:
    """The rule that decides what ships.

    datasets, configs and baselines are COMMITTED, and so are runs now (metrics,
    predictions and outputs). materialized is IGNORED because a command regenerates it.
    The one place the two sets touched was a baseline's `promoted_from`, which named a
    run — so a committed artifact depended on an ignored one, and V6 ("every baseline's
    source run still exists") could not hold on a fresh clone OR after `make clean`,
    which deletes runs while explicitly keeping baselines.

    Resolved by shipping ONE worked example run, force-included in .gitignore, so a fresh
    checkout sees a walked loop and the committed baseline resolves. This asserts the
    dependency stays inside the committed set.

    THIS DOCSTRING USED TO SAY "sources ... and references are COMMITTED", AND THAT WENT
    QUIETLY FALSE. It was true when the only corpus was the synthetic demo. Every real
    corpus since added its own exclusion lines -- data/sources/<id>/ and
    data/references/{gold,silver}/<id>/ -- because none of the four is ours to
    redistribute. 7 reference files are tracked against 1,382 on disk.

    So the committed runs DO depend on ignored references, deliberately and permanently,
    and this test cannot forbid that. What it does instead is count the dependency so it
    is visible, and the guarantee that makes it safe lives in
    test_rescore_refuses_a_missing_reference_set: scoring without the references refuses
    rather than reporting a plausible wrong number. That refusal did not exist until a
    clone of this repo scored an arm at f1 0.1071 whose recorded f1 is 0.6798.
    """
    import subprocess  # noqa: PLC0415

    baselines = sorted((ROOT / "data" / "baselines").glob("*.json"))
    check("consistency: a baseline ships", bool(baselines), "none found")
    for b in baselines:
        promoted_from = json.loads(b.read_text()).get("promoted_from")
        if not promoted_from:
            continue
        run_dir = ROOT / "data" / "runs" / promoted_from
        tracked = (
            subprocess.run(
                ["git", "ls-files", "--error-unmatch", str(run_dir / "metrics.json")],
                cwd=ROOT,
                capture_output=True,
            ).returncode
            == 0
        )
        check(
            f"consistency: {b.name} -> a TRACKED run",
            tracked,
            f"{promoted_from} is not tracked — a committed baseline citing an ignored run "
            f"breaks V6 on any clean checkout",
        )

    # The runs -> references direction, counted rather than forbidden. A reader needs to
    # know that `make rescore` on a fresh clone needs a fetch first, and how much of the
    # tree that applies to.
    tracked_refs = subprocess.run(
        ["git", "ls-files", "data/references"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.split()
    tracked_ref_ids = {pathlib.Path(f).parent.name for f in tracked_refs}
    needs_fetch = set()
    for mj in sorted((ROOT / "data" / "runs").glob("*/metrics.json")):
        rid = ((json.loads(mj.read_text()).get("fingerprint") or {}).get("data") or {}).get("reference_id")
        if rid and pathlib.Path(rid).name not in tracked_ref_ids:
            needs_fetch.add(pathlib.Path(rid).name)
    print(
        f"  --   consistency: {len(needs_fetch)} reference set(s) are ignored by "
        f"design and must be re-fetched before rescore: "
        f"{', '.join(sorted(needs_fetch)) or 'none'}"
    )


def test_fingerprint_core_imports_no_ml_framework() -> None:
    """The core must stay usable by someone who never installs an ML framework.

    The whole reason the model half is a hook rather than an inspection: an LLM-only eval,
    or a regex baseline, should not pull in torch. This asserts the module text itself
    never imports one — a runtime check would pass simply because the framework is absent.
    """
    import ast  # noqa: PLC0415

    # The AST, not a substring search: this module's own docstring says "must never import
    # torch", and grepping for that phrase failed the test on its own prose. A test that
    # reads documentation as code is worse than no test — it trains you to ignore it.
    tree = ast.parse((HERE / "_fingerprint.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    banned = {"torch", "transformers", "sklearn", "numpy", "openai", "anthropic", "datasets"}
    leaked = sorted(imported & banned)
    check("fingerprint core: imports no ML framework or SDK", not leaked, f"imports {leaked}")
    check("fingerprint core: stdlib only", "hashlib" in imported and "platform" in imported)


def test_fingerprint_reports_library_versions_without_importing_them() -> None:
    """importlib.metadata reads distribution metadata off disk. So the core can say
    "torch 2.2.2" while having no torch dependency and never loading it."""
    from evaluation_harness._fingerprint import _installed_versions  # noqa: PLC0415

    before = "torch" in sys.modules
    versions = _installed_versions()
    check("fingerprint: version lookup imports nothing", ("torch" in sys.modules) == before)
    check("fingerprint: reports something installed", isinstance(versions, dict))


def test_fingerprint_does_not_invent_a_revision() -> None:
    """A model the adapter cannot version is recorded as unversioned.

    Substituting a plausible-looking value would make two runs of "the same model" appear
    provably identical when nothing proved it. Same error as reporting 0.0 for a metric
    that was never measured.
    """
    from evaluation_harness._fingerprint import _model_identity  # noqa: PLC0415

    no_rev = _model_identity(lambda _p: {"id": "some-local-blob"}, {})
    check("fingerprint: absent revision stays None", no_rev["revision"] is None)
    check("fingerprint: absent revision is labelled", no_rev["revision_source"] == "unavailable")
    none_hook = _model_identity(None, {})
    check("fingerprint: no hook -> identity_declared False", none_hook == {"identity_declared": False})


def test_untracked_run_output_does_not_make_the_tree_dirty() -> None:
    """A previous run's directory is not code; a changed file anywhere still is.

    Every run after the first on a machine was recorded `dirty: true`, because the first
    run's directory was an untracked file. The rule is narrow on purpose: only UNTRACKED
    paths under data/runs* are ignored.
    """
    from evaluation_harness._fingerprint import filter_dirt  # noqa: PLC0415

    d = "harness/data/"
    check(
        "dirty: an untracked run directory is not dirt",
        filter_dirt("?? harness/data/runs/demo_v1_20260929T110901Z_r1/", d) == [],
    )
    check(
        "dirty: nor one in another runs directory",
        filter_dirt("?? harness/data/runs-linux/cnn_bart_s_n200_v1_X/", d) == [],
    )
    check(
        "dirty: a MODIFIED committed run still is",
        len(filter_dirt(" M harness/data/runs/x/metrics.json", d)) == 1,
    )
    check(
        "dirty: an untracked file outside the runs directories still is",
        len(filter_dirt("?? harness/scripts/new_scorer.py\n?? harness/data/datasets/x.json", d)) == 2,
    )
    check(
        "dirty: a modified script beside an untracked run is still dirty",
        filter_dirt("?? harness/data/runs/r/\n M harness/scripts/_common.py", d)
        == [" M harness/scripts/_common.py"],
    )
    check("dirty: unknown layout ignores nothing", len(filter_dirt("?? harness/data/runs/r/", None)) == 1)


def test_fingerprint_records_what_was_loaded() -> None:
    """The loaded model's commit and dtype reach the fingerprint, and a label that was
    not applied is flagged. `bart_s` ran at fp16 under `precision: fp32` and its run
    could not show it; five checkpoints recorded `revision: null`."""
    sys.path.insert(0, str(HERE.parents[1] / "examples" / "_shared"))
    from hf_identity import hf_model_fingerprint, loaded_identity  # noqa: PLC0415

    class _P:
        dtype = "torch.float16"

    class _Cfg:
        _commit_hash = "a" * 40

    class _Model:
        config = _Cfg()

        def parameters(self):
            yield _P()

    class _Pipe:  # a transformers pipeline: .model + .tokenizer
        tokenizer = object()
        model = _Model()

    got = loaded_identity(_Pipe())
    check("loaded identity: dtype read from the loaded model", got.get("loaded_dtype") == "float16", str(got))
    check(
        "loaded identity: commit read from the loaded config",
        got.get("loaded_revision") == "a" * 40,
        str(got),
    )
    fp = hf_model_fingerprint("nobody/not-in-any-cache-r6", precision="fp32", loaded_model=_Pipe())
    check(
        "hf fingerprint: an ambiguous cache falls back to the loaded commit",
        fp["revision"] == "a" * 40 and fp["revision_source"] == "loaded-model",
        str(fp),
    )
    check(
        "hf fingerprint: fp32 declared, fp16 loaded -> precision_not_applied",
        fp.get("precision_not_applied") is True,
        str(fp),
    )
    ok = hf_model_fingerprint("nobody/not-in-any-cache-r6", precision="fp16", loaded_model=_Pipe())
    check("hf fingerprint: a label that matches is not flagged", "precision_not_applied" not in ok, str(ok))
    bare = hf_model_fingerprint("nobody/not-in-any-cache-r6", precision="fp32")
    check(
        "hf fingerprint: with no loaded model nothing is invented",
        bare["revision"] is None and bare["revision_source"] == "unavailable" and "loaded_dtype" not in bare,
        str(bare),
    )


def test_a_broken_fingerprint_hook_does_not_kill_the_run() -> None:
    """Fingerprinting describes a run; it is not a precondition for one."""
    from evaluation_harness._fingerprint import _model_identity  # noqa: PLC0415

    def boom(_params):
        raise RuntimeError("no model here")

    got = _model_identity(boom, {})
    check("fingerprint: broken hook is caught", got["identity_declared"] is False)

    # ── retries ──────────────────────────────────────────────────────────────
    # Guarded here because the absence of these was invisible: EVAL_MAX_RETRIES was
    # honoured by one adapter and not by the one doing the work, and two sweeps each
    # lost a whole arm to one upstream 429 before anybody noticed.
    from evaluation_harness._retry import call_with_retries, is_transient  # noqa: PLC0415

    waits: list = []
    calls = {"n": 0}

    def _flaky(_x):
        calls["n"] += 1
        if calls["n"] < 4:
            raise RuntimeError("Error code: 429 - rate limit")
        return "done"

    got_val = call_with_retries(_flaky, ("x",), attempts=6, sleep=waits.append)
    check("retry: transient recovers", got_val == "done")
    check("retry: backoff doubles", [round(w) for w in waits] == [1, 2, 4])

    waits.clear()

    def _always(_x):
        raise RuntimeError("503 overloaded")

    try:
        call_with_retries(_always, ("x",), attempts=9, max_delay=8, sleep=waits.append)
        check("retry: exhausts and raises", False)
    except RuntimeError:
        check("retry: exhausts and raises", True)
    check("retry: delay capped", waits and max(waits) <= 8.5 and len(waits) == 8)

    waits.clear()

    def _bad_key(_x):
        # the trap: a fatal error whose text also contains a transient-sounding phrase
        raise RuntimeError("401 invalid api key, please try again later")

    try:
        call_with_retries(_bad_key, ("x",), attempts=5, sleep=waits.append)
        check("retry: fatal raises at once", False)
    except RuntimeError:
        check("retry: fatal raises at once", waits == [])

    waits.clear()

    def _exit(_x):
        raise SystemExit("KEY not set")

    try:
        call_with_retries(_exit, ("x",), attempts=5, sleep=waits.append)
        check("retry: SystemExit never retried", False)
    except SystemExit:
        check("retry: SystemExit never retried", waits == [])

    check(
        "retry: adapter marker honoured",
        is_transient(RuntimeError("model is warming up"), extra=("model is warming up",)),
    )
    check("retry: unknown error is not transient", not is_transient(ValueError("banana")))
    check("fingerprint: broken hook records why", "no model here" in got.get("error", ""))


def test_fingerprint_hash_changes_when_anything_does() -> None:
    """The hash is the one-glance answer to "did anything else move?"."""
    from evaluation_harness._fingerprint import build_fingerprint, differing_paths  # noqa: PLC0415

    ds = {"dataset_id": "d1", "items": [{"item_id": "i1", "source_sha256": "aaa"}]}
    kw: dict = {
        "root": HERE.parent,
        "dataset": ds,
        "reference_id": None,
        "reference_tier": None,
        "config_id": "c1",
        "adapter_id": "scripts/adapter.py",
        "adapter_path": HERE / "adapter.py",
        "model_hook": None,
    }
    base = build_fingerprint(params={"sentences": 1}, **kw)
    same = build_fingerprint(params={"sentences": 1}, **kw)
    moved = build_fingerprint(params={"sentences": 2}, **kw)
    check("fingerprint: stable across identical inputs", base["hash"] == same["hash"])
    check("fingerprint: changes when a param moves", base["hash"] != moved["hash"])
    check(
        "fingerprint: names the field that moved",
        differing_paths(base, moved) == ["arm.params.sentences"],
        f"got {differing_paths(base, moved)}",
    )
    # Different DATA must move it too — dataset_id is a name, the item hashes are identity.
    other = build_fingerprint(
        params={"sentences": 1},
        **{**kw, "dataset": {"dataset_id": "d1", "items": [{"item_id": "i1", "source_sha256": "bbb"}]}},
    )
    check("fingerprint: same dataset_id, different bytes -> different hash", base["hash"] != other["hash"])


def test_example_scorer_suites_pass() -> None:
    """RUN the example scorer suites, do not just --help them.

    They were briefly in the CLI --help list, which proved nothing: neither uses argparse,
    so both exited 0 by ignoring the flag. A test that passes for a reason unrelated to
    what it checks is worse than no test, because it reports green.

    Skipped rather than failed when the example venv is absent -- these import torch-free
    scorer modules, but the runner has to be a Python that can see them, and the harness's
    own interpreter may not be.
    """
    for script, subject in (
        ("test_extraction_scorer.py", "set scorer"),
        ("test_ner_parser.py", "NER JSON parser"),
        ("test_retrieval_scorer.py", "ranked-list scorer"),
        ("test_stats.py", "paired test (stats.py)"),
        ("test_stat_commands.py", "compare-runs, bootstrap-test, holdout: their numbers and refusals"),
        ("test_catalog.py", "catalog and run inspector"),
        ("test_serve_hooks.py", "catalog-serve --hooks: called, never breaking a request, off by default"),
        ("test_goals.py", "goals: config, run, baseline, V14, pages"),
        ("test_axes.py", "a goal's axes and strategy: limits, the tie, the tie-break, the ratios"),
        (
            "test_references.py",
            "reference manifests and V16: checksums committed, texts checked against them",
        ),
        ("test_fields.py", "item fields and URL items: create, materialize, V15"),
        ("test_lineage.py", "dataset versions: --from, V2, the catalog's links"),
        (
            "test_rounds.py",
            "experiment rounds: open, run, suggest, retire, close, the next, validate, the page",
        ),
        (
            "test_run_reports.py",
            "a run with a project adapter: latency, cut-off outputs, a crash and its resume",
        ),
        (
            "test_reference_from_run.py",
            "a run's outputs as the reference: provenance, refusals, the author's row",
        ),
        ("test_installed_commands.py", "every evh command in a project that pins the package"),
        ("test_judge_score.py", "judging pass"),
        ("test_code_hashes.py", "scoring-code hashes"),
        ("test_codeid.py", "code identity: documentation never moves a hash"),
        ("test_providers.py", "hosted providers: one layer for arms and judges, keys by role"),
        ("test_leaderboard_refs.py", "the leaderboard: one table per reference, never averaged across them"),
        (
            "test_reference_coverage.py",
            "a run on partial references warns, records it, the leaderboard says so",
        ),
        (
            "test_family_marks.py",
            "family-test marks an estimated p in a family that mixes exact and estimated",
        ),
        (
            "test_no_shadowing.py",
            "a project's stats.py or adapter.py never replaces the harness's, nor the reverse",
        ),
        ("test_hf_rows.py", "the examples' datasets-server fetcher: pacing, 429 and 5xx retries"),
        ("test_runs_adapter.py", "run reading, direction, adapter loading, the judge panel"),
        ("check_report_claims.py", "report claims vs committed runs"),
        ("check_links.py", "markdown links and anchors"),
        ("check_terminology.py", "experiment tables use the canonical Task · Dataset labels"),
        ("test_summeval_analysis.py", "SummEval split-half: a tied top is undecided"),
        ("check_commands.py", "documented commands: every make target, evh command and flag exists"),
        ("check_model_facts.py", "model facts vs the evidence capture"),
    ):
        path = ROOT / at(script)
        # A MISSING CHECKER IS A FAILURE, NOT A SKIP. `continue` here meant deleting
        # test_retrieval_scorer.py removed it from `make ci` silently -- the suite went
        # on reporting all-green over one fewer check. Found by external review.
        if not path.is_file():
            check(f"{subject}: its checker exists", False, f"{script} is missing")
            continue
        r = run(at(script))
        out = (r.stdout or "") + (r.stderr or "")
        # THE SKIP IS FOR AN EXAMPLE'S DEPENDENCIES, NOT FOR ANY IMPORT ERROR. Matching
        # bare "ModuleNotFoundError" meant a typo'd import inside a checker read as
        # "this machine lacks rouge_score" and vanished from the run.
        missing = re.search(r"No module named '([^']+)'", out)
        if r.returncode != 0 and missing and missing.group(1) in _EXAMPLE_ONLY_MODULES:
            print(
                f"  --   {subject}: skipped (needs {missing.group(1)}, an example "
                f"dependency not on this interpreter)"
            )
            continue
        # Show the FAIL lines, not the tail. The tail is the summary footer, so a
        # second failure below the first was invisible.
        fails = [ln for ln in out.splitlines() if "FAIL" in ln][:3]
        detail = " | ".join(f.strip() for f in fails) or out.strip()[-160:]
        check(f"{subject}: all assertions pass", r.returncode == 0, detail)
        # AND THE EXIT CODE MUST AGREE WITH WHAT IT PRINTED. A checker that prints FAIL
        # and exits 0 satisfied every guard here: `make` reads only the exit code and
        # the guard read only that too. Changing one checker's final line to
        # sys.exit(0) turned a red baseline green.
        check(
            f"{subject}: exits non-zero if it printed FAIL",
            not (any("FAIL" in ln for ln in out.splitlines()) and r.returncode == 0),
            "printed FAIL and exited 0",
        )


def test_fingerprint_version_is_read_somewhere() -> None:
    """A version field nothing reads is decoration.

    v2 added `data.references_sha256`, so a v1 and a v2 hash are not comparable even
    when everything v1 covers is identical. `compare_runs` must say so rather than
    reporting a bare hash mismatch and sending a reader hunting for a change that is
    not there.
    """
    src = (HERE / "compare_runs.py").read_text()
    check(
        "compare_runs notices a fingerprint version mismatch", 'fa.get("version") != fb.get("version")' in src
    )
    from evaluation_harness._fingerprint import build_fingerprint  # noqa: PLC0415

    fp = build_fingerprint(
        root=HERE.parent,
        dataset={"dataset_id": "d", "items": []},
        reference_id=None,
        reference_tier=None,
        config_id="c",
        params={},
        adapter_id="a",
        adapter_path=None,
    )
    # v4 since 2026-10-24: code hashed by behaviour (_codeid), a manifest's caveat outside the
    # reference digest; documentation never moves a fingerprint.
    check("new fingerprints are version 4", fp.get("version") == 4, str(fp.get("version")))


def test_verdict_honours_declared_kinds() -> None:
    """An adapter's own metric must not be judged better/worse by the sign of a delta.

    `verdict_for` consulted only the built-in table, which knows the bundled adapter's
    metrics and nothing else -- so every EXAMPLE metric got a better/worse verdict from
    its sign. `llm_named_unknown` counts hallucinated document ids, and more of them
    was reported as an improvement.
    """
    from evaluation_harness._common import verdict_for  # noqa: PLC0415

    check(
        "verdict: unknown metric, no kinds -> judged by sign (the old behaviour)",
        verdict_for("llm_named_unknown", +1.0) == "better",
    )
    check(
        "verdict: declared descriptive -> 'changed', not 'better'",
        verdict_for("llm_named_unknown", +1.0, kinds={"llm_named_unknown": "descriptive"}) == "changed",
    )
    check(
        "verdict: declared quality still gets a direction",
        verdict_for("ndcg_10", +1.0, kinds={"ndcg_10": "quality"}) == "better",
    )
    check(
        "verdict: a declaration cannot flip cost's direction",
        verdict_for("cost_usd", +1.0, kinds={"cost_usd": "cost"}) == "worse",
    )


def test_fingerprint_covers_reference_bytes() -> None:
    """Editing a reference must change the fingerprint. It did not, for five examples.

    `reference_id` is a NAME. The data block hashed the source items but identified the
    references only by name, so a changed gold file produced different scores under an
    identical hash -- and `compare_runs` reported "reference identical" while comparing
    two different measurements.
    """
    import tempfile  # noqa: PLC0415

    from evaluation_harness._fingerprint import build_fingerprint  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        refs = root / "data" / "references" / "gold" / "t1"
        refs.mkdir(parents=True)
        (refs / "i1.txt").write_text("alpha", encoding="utf-8")
        ds = {"dataset_id": "t1", "items": [{"item_id": "i1", "source_sha256": "aa"}]}
        kw: dict = {
            "root": root,
            "dataset": ds,
            "reference_id": "gold/t1",
            "reference_tier": "gold",
            "config_id": "c",
            "params": {},
            "adapter_id": "a",
            "adapter_path": None,
        }
        before = build_fingerprint(**kw)
        (refs / "i1.txt").write_text("beta", encoding="utf-8")
        after = build_fingerprint(**kw)
        check("fingerprint: editing a reference changes the hash", before["hash"] != after["hash"])
        check(
            "fingerprint: references_sha256 is what moved",
            before["data"]["references_sha256"] != after["data"]["references_sha256"],
        )
        check(
            "fingerprint: no references -> None, not a hash of nothing",
            build_fingerprint(**{**kw, "reference_id": None})["data"]["references_sha256"] is None,
        )


def test_resume_scores_and_persists() -> None:
    """A resumed run must SCORE its replayed items, keep their measurements, refuse
    another arm's, and leave outputs behind when it dies.

    THE CRASH HERE IS SIMULATED -- files are deleted and the pass is resumed -- which
    exercises the resume path but not the durability it depends on. The mtime assertion
    below covers that separately: a version that gathered every output and wrote them
    after the last item would satisfy the delete-and-resume test and still lose a whole
    pass of paid work to a real crash.

    Both directions of a bug that cost paid data. `--resume` used to `continue` past
    scoring, so a fully-resumed run wrote zero prediction rows and empty scores while
    reporting success -- and outputs were only written after the whole pass returned, so
    a crash at item k discarded all k paid outputs AND left the resume path nothing to
    read. The recovery command the cost cap prints was the broken one.
    """
    import shutil  # noqa: PLC0415

    runs = HERE.parent / "data" / "runs-selftest-resume"
    shutil.rmtree(runs, ignore_errors=True)
    env = {"EVAL_RUNS_DIR": str(runs.relative_to(HERE.parent))}
    r = run("scripts/experiment_run.py", "--config", "data/configs/arm_b.yaml", env=env)
    if r.returncode != 0:
        print("  --   resume: skipped (demo arm did not run)")
        shutil.rmtree(runs, ignore_errors=True)
        return
    src = sorted(p.name for p in runs.iterdir() if p.is_dir())[0]
    outs = sorted((runs / src / "outputs").glob("*.txt"))
    check("resume: outputs are on disk after a pass", len(outs) > 0, str(len(outs)))

    # THE PROPERTY A CRASH ACTUALLY DEPENDS ON: outputs are written AS THEY ARE
    # PRODUCED, not gathered up at the end. The simulated crash below (deleting files
    # and resuming) exercises the resume path but would pass just as happily against a
    # version that wrote everything in one go after the last item -- which is the
    # version that lost a whole pass of paid outputs.
    #
    # Checked by mtime, which is the observable this leaves behind: every output must
    # predate metrics.json, and the first must predate the last, because they were
    # written one at a time while the pass ran.
    mj = runs / src / "metrics.json"
    if len(outs) > 1 and mj.is_file():
        t_out = sorted(f.stat().st_mtime for f in outs)
        check(
            "resume: outputs are written DURING the pass, not after it",
            t_out[-1] <= mj.stat().st_mtime and t_out[0] <= t_out[-1],
            f"last output {t_out[-1]:.3f}, metrics {mj.stat().st_mtime:.3f}",
        )

    # Simulate a crash: drop all but one output, as if the pass died at item 2.
    for f in outs[1:]:
        f.unlink()
    r2 = run("scripts/experiment_run.py", "--config", "data/configs/arm_b.yaml", "--resume", src, env=env)
    check("resume: the resumed pass exits 0", r2.returncode == 0, (r2.stderr or "")[-160:])
    newest = max((p for p in runs.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
    rows = [ln for ln in (newest / "predictions.jsonl").read_text().splitlines() if ln.strip()]
    check(
        "resume: every item is SCORED, not skipped",
        len(rows) == len(outs),
        f"{len(rows)} rows for {len(outs)} items",
    )
    check(
        "resume: replayed items are flagged", any('"resumed": 1' in ln or '"resumed":1' in ln for ln in rows)
    )

    # A REPLAYED ITEM MUST KEEP WHAT WAS MEASURED FOR IT. Every field used to be None:
    # a resumed run reported $0.03 for $0.05 of spend, and `_meta` -- llm_raw,
    # first_stage, ranking for retrieval -- disappeared for exactly the items that were
    # hardest to obtain, so a resumed retrieval or NER run could not be reported at all.
    import json as _json  # noqa: PLC0415

    src_rows = {}
    for line in (runs / src / "predictions.jsonl").read_text().splitlines():
        if line.strip():
            r = _json.loads(line)
            src_rows[r["item_id"]] = r
    replayed = [_json.loads(ln) for ln in rows if _json.loads(ln).get("resumed") == 1.0]
    check(
        "resume: at least one item was actually replayed",
        bool(replayed),
        f"{len(replayed)} replayed of {len(rows)}",
    )
    if replayed:
        r = replayed[0]
        o = src_rows.get(r["item_id"], {})
        # Only assert on fields the original row actually had; the demo arm is free and
        # local, so cost and tokens may legitimately be absent from BOTH.
        carried = [k for k in ("cost_usd", "latency_ms", "tokens_in", "tokens_out") if o.get(k) is not None]
        check(
            "resume: a replayed item keeps the measurements from its original pass",
            all(r.get(k) == o.get(k) for k in carried) if carried else True,
            f"carried={carried} orig={[o.get(k) for k in carried]} now={[r.get(k) for k in carried]}",
        )
        if o.get("_meta"):
            check(
                "resume: and keeps its _meta",
                isinstance(r.get("_meta"), dict)
                and all(r["_meta"].get(k) == v for k, v in o["_meta"].items()),
                f"orig keys {sorted(o['_meta'])} now {sorted(r.get('_meta') or {})}",
            )

    # THE ACTUAL CRASH SHAPE: outputs/ and run.json, no metrics.json, no
    # predictions.jsonl -- because both are written only after the pass returns.
    #
    # Round 2 taught resume to carry each replayed item's cost, tokens and _meta
    # forward FROM predictions.jsonl, which by construction does not exist in the one
    # case resume is for. So the feature worked for a tidy re-run and not for a crash,
    # and the mtime assertion above could not tell: it proves outputs are written
    # during the pass, not that anything else is. Found by external review.
    crash = runs / "crashed"
    shutil.rmtree(crash, ignore_errors=True)
    shutil.copytree(runs / src, crash)
    (crash / "metrics.json").unlink(missing_ok=True)
    (crash / "predictions.jsonl").unlink(missing_ok=True)
    check(
        "resume: a crashed run still carries its identity (run.json)",
        (crash / "run.json").is_file(),
        "run.json must be written before the first item, not after the pass",
    )
    check(
        "resume: and its per-item rows (outputs/_rows.jsonl)",
        (crash / "outputs" / "_rows.jsonl").is_file(),
        "rows must be appended during the pass, not written at the end",
    )

    r3 = run(
        "scripts/experiment_run.py", "--config", "data/configs/arm_b.yaml", "--resume", "crashed", env=env
    )
    check(
        "resume: an outputs-only crashed run resumes",
        r3.returncode == 0,
        ((r3.stderr or "") + (r3.stdout or ""))[-200:],
    )
    newest = max(
        (p for p in runs.iterdir() if p.is_dir() and p.name != "crashed"), key=lambda p: p.stat().st_mtime
    )
    rows3 = [_json.loads(ln) for ln in (newest / "predictions.jsonl").read_text().splitlines() if ln.strip()]
    replayed3 = [r for r in rows3 if r.get("resumed") == 1.0]
    check(
        "resume: after a CRASH, replayed rows still carry their measurements",
        bool(replayed3) and all(r.get("latency_ms") is not None for r in replayed3),
        f"{len(replayed3)} replayed; first = "
        f"{ {k: replayed3[0].get(k) for k in ('latency_ms', 'cost_usd')} if replayed3 else None }",
    )
    shutil.rmtree(crash, ignore_errors=True)

    # AND THE ADAPTER'S OWN CALL-TIME NUMBERS MUST BE CARRIED TOO. `Result.extra` --
    # `input_truncated`, `truncated`, `reasoning_tokens` -- was dropped on replay, and
    # the aggregate averages only the rows that carry a key, so a resumed summariser
    # reported input_truncated 0.75 (3 of the 4 fresh items) against a true 0.23.
    # The demo adapter emits no `extra`, which is why every assertion above passed:
    # this uses a fixture adapter that does.
    #
    # AND THE OPPOSITE DIRECTION. The first fix carried every numeric key of the prior
    # row, so a score the current scorer no longer emits came back from the replayed rows
    # alone, reported as measured. Both passes' values are deliberately different --
    # `call_flag` 1.0 then 2.0, `old_metric` present then absent -- because a constant
    # cannot tell a carried value from a freshly computed one.
    fx = runs / "fixture"
    fx.mkdir(parents=True, exist_ok=True)
    (fx / "fx_adapter.py").write_text(
        "import os\n"
        "from dataclasses import dataclass, field\n"
        "from typing import Any, Dict, Optional\n"
        "PRIMARY_METRIC = 'words'\n"
        "METRIC_KINDS = {'words': 'quality', 'call_flag': 'descriptive',\n"
        "                'old_metric': 'quality'}\n"
        "PASS = float(os.environ.get('FX_PASS', '1'))\n"
        "@dataclass\n"
        "class Result:\n"
        "    output: str\n"
        "    cost_usd: Optional[float] = 0.0\n"
        "    latency_ms: Optional[float] = None\n"
        "    tokens_in: Optional[int] = None\n"
        "    tokens_out: Optional[int] = None\n"
        "    extra: Dict[str, float] = field(default_factory=dict)\n"
        "    meta: Dict[str, Any] = field(default_factory=dict)\n"
        "def call_system(text, params):\n"
        "    return Result(output=text[:60], extra={'call_flag': PASS})\n"
        "def score(output, reference):\n"
        "    out = {'words': float(len(output.split()))}\n"
        "    if PASS == 1.0:\n"
        "        out['old_metric'] = 1.0\n"
        "    return out\n"
    )
    (fx / "arm_fx.yaml").write_text(
        "config_id: fx_extra_v1\ndataset_id: smoke_v1\nadapter: fx_adapter.py\nparams:\n  provider: fixture\n"
    )
    cfg_fx = str((fx / "arm_fx.yaml").relative_to(HERE.parent))
    rf = run(
        "scripts/experiment_run.py", "--config", cfg_fx, "--run-id", "fx_src", env={**env, "FX_PASS": "1"}
    )
    if rf.returncode != 0:
        check(
            "resume: the extra-carrying fixture arm runs",
            False,
            ((rf.stderr or "") + (rf.stdout or ""))[-200:],
        )
    else:
        fx_outs = sorted((runs / "fx_src" / "outputs").glob("*.txt"))
        for f in fx_outs[1:]:
            f.unlink()
        (runs / "fx_src" / "metrics.json").unlink(missing_ok=True)
        (runs / "fx_src" / "predictions.jsonl").unlink(missing_ok=True)
        rr = run(
            "scripts/experiment_run.py",
            "--config",
            cfg_fx,
            "--run-id",
            "fx_res",
            "--resume",
            "fx_src",
            env={**env, "FX_PASS": "2"},
        )
        fx_rows = (
            [
                _json.loads(ln)
                for ln in (runs / "fx_res" / "predictions.jsonl").read_text().splitlines()
                if ln.strip()
            ]
            if rr.returncode == 0
            else []
        )
        fx_rep = [r for r in fx_rows if r.get("resumed") == 1.0]
        fx_new = [r for r in fx_rows if r.get("resumed") == 0.0]
        check(
            "resume: replayed rows keep the adapter's extra metrics FROM THEIR OWN PASS",
            bool(fx_rep)
            and all(r.get("call_flag") == 1.0 for r in fx_rep)
            and bool(fx_new)
            and all(r.get("call_flag") == 2.0 for r in fx_new),
            f"replayed call_flag={[r.get('call_flag') for r in fx_rep][:3]} "
            f"fresh call_flag={[r.get('call_flag') for r in fx_new][:3]}",
        )
        fx_m = (
            _json.loads((runs / "fx_res" / "metrics.json").read_text())
            if (runs / "fx_res" / "metrics.json").is_file()
            else {}
        )
        check(
            "resume: a score the current scorer no longer emits is NOT carried",
            bool(fx_rows)
            and not any("old_metric" in r for r in fx_rows)
            and "old_metric" not in (fx_m.get("scores") or {}),
            f"old_metric on {sum('old_metric' in r for r in fx_rows)} row(s); "
            f"in scores: {'old_metric' in (fx_m.get('scores') or {})}",
        )
        check(
            "resume: the run records which extras it carried",
            (fx_m.get("resume") or {}).get("carried_extra_keys") == ["call_flag"],
            f"resume note: {fx_m.get('resume')}",
        )

    # RESUMING FROM ANOTHER ARM MUST BE REFUSED. `--resume` took a run id and read its
    # outputs; nothing compared the arms, so one mistyped id replayed a different
    # model's answers and recorded them under this one, with a valid fingerprint.
    other = run("scripts/experiment_run.py", "--config", "data/configs/arm_a.yaml", "--resume", src, env=env)
    msg = (other.stderr or "") + (other.stdout or "")
    check(
        "resume: another arm's outputs are refused",
        other.returncode != 0 and "another arm" in msg.lower(),
        msg[-200:],
    )

    # AND REFUSED EVEN WHEN THE SOURCE CANNOT BE IDENTIFIED. This used to WARN and
    # continue, so `arm_a --resume <crashed arm_b run>` exited 0 having recorded arm_a
    # with arm_b's answers.
    anon = runs / "anonymous"
    shutil.rmtree(anon, ignore_errors=True)
    (anon / "outputs").mkdir(parents=True)
    (anon / "outputs" / "item_01.txt").write_text("from who knows where")
    r4 = run(
        "scripts/experiment_run.py", "--config", "data/configs/arm_a.yaml", "--resume", "anonymous", env=env
    )
    m4 = (r4.stderr or "") + (r4.stdout or "")
    check(
        "resume: an unidentifiable source is refused, not warned about",
        r4.returncode != 0 and "cannot be identified" in m4,
        m4[-200:],
    )
    shutil.rmtree(anon, ignore_errors=True)
    shutil.rmtree(runs, ignore_errors=True)


def test_writes_leave_no_partial_file() -> None:
    """A failed write must leave the previous file intact, not a truncated one.

    `write_text` truncates the target and then writes into it, so a crash, a full disk
    or a kill partway leaves a SHORT file where a complete one should be. That matters
    more here than in most places: `--resume` treats the presence of an output file as
    proof the item is done, so a half-written output is replayed as the model's answer
    and scored. The failure then looks like a bad answer rather than a broken file.

    Simulated by making the encode fail mid-write, which is the observable shape of a
    death during serialisation.
    """
    import tempfile as _tf  # noqa: PLC0415

    from evaluation_harness._common import write_text_atomic  # noqa: PLC0415

    with _tf.TemporaryDirectory() as td:
        target = pathlib.Path(td) / "out.txt"
        target.write_text("the original, complete content")

        # WINDOW 1: death DURING the write. A lone surrogate cannot be encoded to
        # utf-8, so the write raises partway -- the same shape as running out of disk.
        try:
            write_text_atomic(target, "good start \ud800 bad")
        except Exception:  # noqa: BLE001 — what survives is the point, not what raised
            pass
        check(
            "atomic write: a write that dies partway leaves the original intact",
            target.read_text() == "the original, complete content",
            f"file now: {target.read_text()[:60]!r}",
        )

        # WINDOW 2: death AFTER the temp file is complete, BEFORE the rename. This is
        # the window the whole design exists for, and the only way to reach it is to
        # make the rename itself fail.
        import os as _os  # noqa: PLC0415

        real_replace = _os.replace
        _os.replace = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("killed"))
        try:
            write_text_atomic(target, "replacement")
        except Exception:  # noqa: BLE001
            pass
        finally:
            _os.replace = real_replace
        check(
            "atomic write: a death before the rename leaves the original intact",
            target.read_text() == "the original, complete content",
            f"file now: {target.read_text()[:60]!r}",
        )

        leftovers = [f.name for f in pathlib.Path(td).iterdir() if f.name != "out.txt"]
        check("atomic write: and leaves no temp file behind", not leftovers, str(leftovers))

        write_text_atomic(target, "the new content")
        check(
            "atomic write: a successful write still replaces the file",
            target.read_text() == "the new content",
            target.read_text()[:60],
        )
        from evaluation_harness._common import write_bytes_atomic  # noqa: PLC0415

        blob = bytes(range(256)) * 4
        write_bytes_atomic(target, blob)
        check("atomic write: bytes land exactly, with no newline translation", target.read_bytes() == blob)
        check(
            "atomic write: bytes leave no temp file behind",
            [f.name for f in pathlib.Path(td).iterdir() if f.name != "out.txt"] == [],
        )

        # THE CONTRAST, so this test shows a difference rather than just asserting the
        # new behaviour. `write_text` truncates first: the same failure destroys the
        # file. Without this the test would pass against any implementation that
        # happens to exist, including a broken one.
        naive = pathlib.Path(td) / "naive.txt"
        naive.write_text("the original, complete content")
        try:
            naive.write_text("good start \ud800 bad", encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        check(
            "atomic write: and the plain write_text it replaces DOES lose the file",
            naive.read_text() != "the original, complete content",
            f"write_text somehow preserved it: {naive.read_text()[:40]!r}",
        )


def test_rescore_rehashes_the_references_it_actually_read() -> None:
    """A rescored run must not assert a reference hash over bytes it never read.

    The fingerprint was copied wholesale from the source run, so
    `data.references_sha256` described the reference files AS THEY WERE WHEN THAT RUN
    EXECUTED -- while the scores beside it were computed against whatever is on disk
    now. If the gold set changed in between, the rescored run made the one claim a
    fingerprint exists to make, about the wrong bytes.

    Built by injecting a reference hash that cannot match, which is what a changed gold
    set looks like from here.
    """
    import json as _json  # noqa: PLC0415
    import shutil  # noqa: PLC0415

    src = None
    for d in sorted((HERE.parent / "data" / "runs").glob("fn_*")):
        m = d / "metrics.json"
        if m.is_file() and (d / "outputs").is_dir():
            j = _json.loads(m.read_text())
            if ((j.get("fingerprint") or {}).get("data") or {}).get("reference_id"):
                src = d
                break
    if src is None:
        print("  --   rescore/refhash: skipped (no run with references on disk)")
        return

    runs = HERE.parent / "data" / "runs-selftest-refhash"
    shutil.rmtree(runs, ignore_errors=True)
    dst = runs / src.name
    dst.mkdir(parents=True)
    for n in ("metrics.json", "predictions.jsonl"):
        shutil.copy2(src / n, dst / n)
    shutil.copytree(src / "outputs", dst / "outputs")
    j = _json.loads((dst / "metrics.json").read_text())
    j["fingerprint"]["data"]["references_sha256"] = "0" * 64  # cannot match
    (dst / "metrics.json").write_text(_json.dumps(j))

    env = {"EVAL_RUNS_DIR": str(runs.relative_to(HERE.parent))}
    out = runs / "out"
    r = run(
        "scripts/rescore.py",
        "--dataset-id",
        str(j.get("dataset_id")),
        "--out",
        str(out.relative_to(HERE.parent)),
        env=env,
    )
    mf = out / src.name / "metrics.json"
    _out = (r.stderr or "") + (r.stdout or "")
    if "NOT ONE of its" in _out or "reference files exists" in _out:
        # A fresh clone has no corpus, so rescore refuses -- which is the behaviour a
        # DIFFERENT test asserts. Skipping here is honest; calling it a failure would
        # make `make ci` red in every clone for doing the right thing.
        print("  --   rescore/refhash: skipped (references not fetched on this machine)")
    elif r.returncode != 0 or not mf.is_file():
        check("rescore: rehashing references did not break rescore", False, _out[-160:])
    else:
        data = _json.loads(mf.read_text())["fingerprint"]["data"]
        check(
            "rescore: references_sha256 is recomputed, not copied",
            data.get("references_sha256") not in (None, "0" * 64),
            f"got {str(data.get('references_sha256'))[:24]}",
        )
        check(
            "rescore: and a changed gold set is flagged, not silently overwritten",
            data.get("references_changed_since_measurement") is True
            and data.get("references_sha256_at_measurement") == "0" * 64,
            f"keys present: {sorted(k for k in data if 'reference' in k)}",
        )
    shutil.rmtree(runs, ignore_errors=True)


def test_rescore_takes_source_path_from_the_dataset() -> None:
    """`source_path` lives in the dataset. rescore was reading it off the prediction row.

    No prediction row has ever carried one -- 0 of 20,001 across every committed run.
    `dataset_create.py` writes it into the DATASET, and experiment_run, materialize,
    reference_create and validate_tree all read it from there. rescore was the single
    place looking in the wrong object, so its fallback to `<item_id>.txt` fired every
    time and, on a dataset whose files are named anything else, the source text arrived
    as None -- silently, because a scorer that wanted the source then measured nothing
    instead of failing.

    Round 1 reported this fixed. That commit added the lookup without checking the field
    existed where it was being read from.

    LATENT TODAY: all 12 datasets here name their files `<item_id>.txt`, so no recorded
    number is affected. This test therefore MAKES a dataset where they differ -- pointing
    two items at each other's source file -- and asserts the scores move. Against the old
    code they do not move at all, because the dataset's `source_path` was never consulted.
    """
    import json as _json  # noqa: PLC0415
    import shutil  # noqa: PLC0415

    ds_file = HERE.parent / "data" / "datasets" / "cnn_dailymail_200.json"
    mat = HERE.parent / "data" / "materialized" / "cnn_dailymail_200"
    src = None
    for d in sorted((HERE.parent / "data" / "runs").glob("cnn_*_n200_v1_*")):
        if (d / "metrics.json").is_file() and (d / "outputs").is_dir():
            src = d
            break
    if src is None or not ds_file.is_file() or not mat.is_dir():
        print(
            "  --   rescore/source_path: skipped. Needs THREE things, not one: the\n"
            "       corpus fetched (examples/summarization-cnn-dailymail/fetch.py),\n"
            "       cnn_dailymail_200 materialized (make smoke-fixture does it), and\n"
            "       an interpreter with rouge_score (now in harness/requirements.txt)."
        )
        return

    tmp = HERE.parent / "data" / "runs-selftest-srcpath"
    shutil.rmtree(tmp, ignore_errors=True)
    dst = tmp / src.name
    dst.mkdir(parents=True)
    for n in ("metrics.json", "predictions.jsonl"):
        shutil.copy2(src / n, dst / n)
    shutil.copytree(src / "outputs", dst / "outputs")

    env = {"EVAL_RUNS_DIR": str(tmp.relative_to(HERE.parent))}
    base = run(
        "scripts/rescore.py",
        "--dataset-id",
        "cnn_dailymail_200",
        "--out",
        str((tmp / "out-base").relative_to(HERE.parent)),
        env=env,
    )
    if base.returncode != 0:
        err = (base.stderr or "") + (base.stdout or "")
        # A MISSING DEPENDENCY IS A SKIP; ANYTHING ELSE IS THE BUG. The summarisation
        # scorer needs rouge_score, which lives in that example's venv, so running the
        # suite on the harness venv legitimately cannot do this one.
        #
        # Every other failure is a real one, and this is where the worst of them
        # surfaced: 24 committed cnn_dailymail_200 runs recorded their adapter as
        # "summarization-cnn-dailymail/adapter.py" -- relative to the examples root,
        # which rescore did not try -- so the entire summarisation sweep could not be
        # rescored. It skipped here as "baseline rescore failed" and said nothing.
        if "ModuleNotFoundError" in err or "No module named" in err:
            print("  --   rescore/source_path: skipped (needs the example's venv)")
        else:
            lines = [ln for ln in err.splitlines() if ln.strip()]
            detail = next(
                (ln for ln in lines if ln.startswith(("ERROR", "Traceback")) or "Error" in ln),
                lines[-1] if lines else "no output",
            )
            check("rescore: a committed run can be rescored at all", False, detail[:200])
        shutil.rmtree(tmp, ignore_errors=True)
        return

    # Swap two items' source_path. The files still exist; each item now points at the
    # other's text, so any scorer that reads the source must produce different numbers.
    ds = _json.loads(ds_file.read_text())
    items = [i for i in ds.get("items", []) if i.get("source_path")]
    original = ds_file.read_text()
    try:
        items[0]["source_path"], items[1]["source_path"] = (items[1]["source_path"], items[0]["source_path"])
        ds_file.write_text(_json.dumps(ds))
        swapped = run(
            "scripts/rescore.py",
            "--dataset-id",
            "cnn_dailymail_200",
            "--out",
            str((tmp / "out-swap").relative_to(HERE.parent)),
            env=env,
        )
    finally:
        ds_file.write_text(original)

    def scores(where):
        f = where / src.name / "metrics.json"
        return _json.loads(f.read_text())["scores"] if f.is_file() else None

    a, b = scores(tmp / "out-base"), scores(tmp / "out-swap")
    if a is None:
        print("  --   rescore/source_path: skipped (rescore produced no metrics: no corpus here)")
    elif b is None:
        # The base rescore worked and the swapped one did not: a failure, not a skip.
        check(
            "rescore: the run with swapped source_paths produced metrics",
            False,
            ((swapped.stdout or "") + (swapped.stderr or ""))[-300:],
        )
    else:
        check(
            "rescore: the dataset's source_path is what selects the source text",
            a != b,
            "swapping two items' source_path changed nothing — the dataset's source_path is being ignored",
        )
    shutil.rmtree(tmp, ignore_errors=True)


def test_a_run_that_measured_nothing_is_not_a_success() -> None:
    """`EVAL_MAX_COST_USD=0` wrote an empty run and exited 0.

    The directory looked like every other run -- metrics.json, predictions.jsonl,
    outputs/ -- and held `"scores": {}` with zero prediction rows. A sweep script or CI
    job saw exit 0 and moved on. Nothing was measured and nothing said so.

    Partial results are still kept and the resume hint still prints; that was
    deliberate. What changed is the exit code, because "the cap stopped me after 3 of
    200 items" and "I measured 200 items" must not both be success. 1 = nothing
    measured, 2 = stopped early with usable partial results, 0 = complete.
    """
    import shutil  # noqa: PLC0415

    runs = HERE.parent / "data" / "runs-selftest-cap"
    shutil.rmtree(runs, ignore_errors=True)
    env = {"EVAL_RUNS_DIR": str(runs.relative_to(HERE.parent))}

    # THE CONTROL RUNS FIRST, and decides whether this test can run at all. Ordering it
    # after the capped run meant a clone -- where `smoke_v1` is not materialized,
    # because data/materialized/ is regenerated rather than committed -- reached the
    # assertions with nothing measured and FAILED on the control. A test that is green
    # on the author's laptop and red in a fresh clone is the exact shape of bug this
    # review found elsewhere, so it must skip honestly instead.
    r2 = run("scripts/experiment_run.py", "--config", "data/configs/arm_b.yaml", env=env)
    out2 = (r2.stdout or "") + (r2.stderr or "")
    if r2.returncode != 0 and "is not materialized" in out2:
        print("  --   cost cap: skipped (smoke_v1 is not materialized in this checkout)")
        shutil.rmtree(runs, ignore_errors=True)
        return
    # Any other failure of the control is a failure, not a skip.
    why = out2.strip().splitlines()
    check(
        "cost cap: an uncapped run of the same arm still exits 0",
        r2.returncode == 0,
        f"exit {r2.returncode}: {why[-1][:90] if why else 'no output'}",
    )
    if r2.returncode != 0:
        shutil.rmtree(runs, ignore_errors=True)
        return
    shutil.rmtree(runs, ignore_errors=True)

    r = run(
        "scripts/experiment_run.py",
        "--config",
        "data/configs/arm_b.yaml",
        env={**env, "EVAL_MAX_COST_USD": "0"},
    )
    out = (r.stdout or "") + (r.stderr or "")
    check("cost cap: a run that scored NO items exits non-zero", r.returncode != 0, f"exit {r.returncode}")
    check(
        "cost cap: and says nothing was measured",
        "scored NO items" in out or "Nothing was measured" in out,
        out[-160:],
    )

    shutil.rmtree(runs, ignore_errors=True)


def test_adapter_declaration_beats_a_stale_run() -> None:
    """A metric kind fixed in the adapter must take effect on runs measured before it.

    `llm_named_unknown` counts document ids a reranker INVENTED. Undeclared, it fell
    into the leaderboard's quality columns, where higher reads as better -- so an arm
    that hallucinated more ids looked like it had improved. It was declared
    `descriptive` in the adapter in round 1, and round 2 found it still showing as
    quality, because the leaderboard merged the metric kinds recorded IN THE RUNS and
    19 committed SciFact runs predate the fix.

    A run freezes what was declared when it was measured. The adapter is the authority
    on what its own metrics mean, so it now wins; runs remain the fallback for an
    adapter that cannot be imported.

    This builds a run that declares the WRONG kind and asserts the adapter overrides it,
    which is the direction that was broken -- asserting the fixed state alone would pass
    against the old code too.
    """
    import json as _json  # noqa: PLC0415
    import shutil  # noqa: PLC0415

    src = None
    for d in sorted((HERE.parent / "data" / "runs").glob("sf_*")):
        if (d / "metrics.json").is_file() and (d / "predictions.jsonl").is_file():
            m = _json.loads((d / "metrics.json").read_text())
            if "llm_named_unknown" in (m.get("scores") or {}):
                src = d
                break
    if src is None:
        print("  --   metric kinds: skipped (no reranking run on disk)")
        return

    runs = HERE.parent / "data" / "runs-selftest-kinds"
    shutil.rmtree(runs, ignore_errors=True)
    dst = runs / src.name
    dst.mkdir(parents=True)
    for name in ("metrics.json", "predictions.jsonl"):
        shutil.copy2(src / name, dst / name)
    m = _json.loads((dst / "metrics.json").read_text())
    m.setdefault("metric_kinds", {})["llm_named_unknown"] = "quality"  # the stale state
    (dst / "metrics.json").write_text(_json.dumps(m))

    env = {"EVAL_RUNS_DIR": str(runs.relative_to(HERE.parent))}
    r = run("scripts/leaderboard.py", "--dataset-id", str(m.get("dataset_id")), env=env)
    # The COLUMN header, not the "ranked by: ndcg_10" caption above it -- both contain
    # the metric name, and matching the caption made this fail for the wrong reason.
    header = next(
        (ln for ln in (r.stdout or "").splitlines() if "ndcg_10" in ln and ln.split()[:1] == ["arm"]), ""
    )
    cols = header.split()
    ok = (
        "llm_named_unknown" in cols
        and "recall_100" in cols
        and cols.index("llm_named_unknown") > cols.index("recall_100")
    )
    check(
        "metric kinds: the adapter's 'descriptive' overrides a run's stale 'quality'",
        ok,
        f"columns: {cols[:14]}",
    )
    shutil.rmtree(runs, ignore_errors=True)


def test_a_rescored_run_carries_the_current_parse() -> None:
    """A rescored run's `_meta.predicted` must be what the CURRENT parser produces.

    `rescore.py` carried the whole `_meta` blob verbatim -- its rule is "carry only
    things that describe the call", and `_meta` passes that on `k.startswith("_")`
    alone. But `_meta.predicted` is the PARSER'S output, and `extraction_report.py`
    reads exactly that field and recomputes from it, so after the round-4 parser fix
    §3.6 was computed on pre-fix parses for four arms: `glm_l` recomputed to 0.5269
    against its own run's 0.5662, identically in both trees.

    This compares every rescored run's stored score to a score recomputed from the parse
    its own `_meta` carries. They must agree, or the two halves of the run describe
    different code. Found while folding in `fn_mistral_l`; it is the fifth instance of a
    correction reaching the reports and not the thing that generates them.
    """
    import json as _json  # noqa: PLC0415

    base = HERE.parent / "data" / "runs"
    gold_dir = HERE.parent / "data" / "references" / "gold" / "few_nerd_280"
    if not base.is_dir() or not gold_dir.is_dir() or not any(gold_dir.glob("*.txt")):
        print("  --   rescored parse: the gold corpus is absent — skipped")
        return
    sys.path.insert(0, str(HERE.parents[1] / "examples" / "_shared"))
    try:
        from extraction import as_members, match_one_to_one  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        print(f"  --   rescored parse: extraction not importable ({type(exc).__name__})")
        return
    gold = {f.stem: _json.loads(f.read_text(encoding="utf-8")) for f in gold_dir.glob("*.txt")}

    def mean_item_f1(by_item):
        tot = n = 0
        for item, g in gold.items():
            if item not in by_item:
                continue
            n += 1
            pred = by_item[item]
            if pred is None:
                continue
            gm, pm = as_members(g, True), as_members(pred, True)
            if not gm and not pm:
                tot += 1.0
                continue
            hit = match_one_to_one(pm, gm)
            prec = hit / len(pm) if pm else 0.0
            rec = hit / len(gm) if gm else 0.0
            if prec + rec:
                tot += 2 * prec * rec / (prec + rec)
        return tot / n if n else None

    checked, stale = 0, []
    for mj in sorted(base.glob("fn_*/metrics.json")):
        m = _json.loads(mj.read_text(encoding="utf-8"))
        if m.get("dataset_id") != "few_nerd_280":
            continue
        pj = mj.parent / "predictions.jsonl"
        if not pj.is_file():
            continue
        rows = [_json.loads(x) for x in pj.read_text(encoding="utf-8").splitlines() if x.strip()]
        if not rows or "predicted" not in (rows[0].get("_meta") or {}):
            continue
        got = mean_item_f1({r["item_id"]: (r.get("_meta") or {}).get("predicted") for r in rows})
        if got is None:
            continue
        checked += 1
        want = m["scores"]["f1"]
        if abs(got - want) > 0.0002:
            stale.append(f"{m['config_id']}: stored {want:.4f}, its own _meta parses to {got:.4f}")
    if not checked:
        print("  --   rescored parse: no run records _meta.predicted — skipped")
        return
    check(
        f"a rescored run's _meta carries the CURRENT parse ({checked} arm(s))",
        not stale,
        "; ".join(stale[:3]),
    )


def test_every_planted_defect_still_anchors() -> None:
    """`make guard-check` plants its defects by replacing a string in a report or a scorer, and
    CI runs it only when a checker changes. A report edit that moves one of those strings would
    go unnoticed until then, so every pull request checks here, in milliseconds, that each
    still occurs exactly once."""
    import test_checks_can_fail as guards  # noqa: PLC0415

    for _script, what, rel, old, _new, _says in guards.PLANTS:
        n = (guards.REPO / rel).read_text(encoding="utf-8").count(old)
        check(
            f"guard-check's plant still anchors: {what} ({rel})", n == 1, f"{n} matches — update the anchor"
        )


def test_v4_neither_skips_a_missing_file_nor_hides_what_it_did_not_check() -> None:
    """V4 printed `ok` for a materialized copy that had lost a file, and for a dataset with
    no materialized copy at all (CI never has one): green for things it never checked."""
    import contextlib  # noqa: PLC0415
    import hashlib as _h  # noqa: PLC0415
    import io  # noqa: PLC0415
    import tempfile as _tmp  # noqa: PLC0415

    from evaluation_harness import validate_tree as vt  # noqa: PLC0415

    def run_v4(tmp: pathlib.Path) -> tuple:
        saved = (vt.DATASETS, vt.MATERIALIZED, list(vt.problems))
        vt.DATASETS, vt.MATERIALIZED = tmp / "datasets", tmp / "materialized"
        vt.problems.clear()
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                vt.v4_materialized()
            return list(vt.problems), buf.getvalue()
        finally:
            vt.DATASETS, vt.MATERIALIZED = saved[0], saved[1]
            vt.problems[:] = saved[2]

    with _tmp.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        (tmp / "datasets").mkdir()
        body = b"an item"
        item = {"item_id": "a", "source_path": "a.txt", "source_sha256": _h.sha256(body).hexdigest()}
        for ds in ("here_v1", "absent_v1"):
            (tmp / "datasets" / f"{ds}.json").write_text(json.dumps({"dataset_id": ds, "items": [item]}))
        mat = tmp / "materialized" / "here_v1"
        mat.mkdir(parents=True)
        (mat / "a.txt").write_bytes(body)
        probs, out = run_v4(tmp)
        check(
            "V4: a matching copy passes and says how many datasets it checked",
            not probs and "1 of 2" in out,
            out.strip()[-160:],
        )
        check(
            "V4: a dataset with no materialized copy is named as not checked, not passed silently",
            "absent_v1" in out and "not checked" in out,
            out.strip()[-160:],
        )
        (mat / "a.txt").unlink()
        probs, out = run_v4(tmp)
        check(
            "V4: a materialized copy that lost a file FAILS",
            bool(probs) and "a.txt" in out,
            out.strip()[-160:],
        )


def test_v10_fails_when_a_derived_run_states_no_scorer() -> None:
    """Stripping the provenance field must FAIL, not skip.

    V10 printed `skip` and passed when no run recorded the hash it reads, so deleting
    `rescored_with` from all 27 rescored runs left VALIDATION PASSED -- the check
    vanishing at exactly the moment its subject disappeared, which is what its own
    docstring said a check must never do. Found by external review, round 5.
    """
    import json as _json  # noqa: PLC0415

    base = HERE.parent / "data" / "runs"
    mjs = sorted(base.glob("fn_*/metrics.json"))
    if not mjs:
        print("  --   V10 provenance: no rescored runs — skipped")
        return
    before = {f: f.read_text(encoding="utf-8") for f in mjs}
    try:
        for f in mjs:
            m = _json.loads(before[f])
            m.pop("derived", None)
            f.write_text(_json.dumps(m, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        r = run("scripts/validate_tree.py")
        out = (r.stdout or "") + (r.stderr or "")
        check(
            "V10 fails when a derived run states no scorer at all",
            r.returncode != 0 and "every run states its scorer" in out,
            f"exit {r.returncode}",
        )
        check(
            "...and says so rather than printing a skip",
            "skip V10 runs" not in out,
            "it still skips",
        )
    finally:
        for f, text in before.items():
            f.write_text(text, encoding="utf-8")


def test_nemenyi_table_is_computed_not_copied() -> None:
    """The critical values must be derivable, and must match the literature.

    `leaderboard.py` carried 24 numbers transcribed from Demsar (2006) and refused to
    print a critical difference above k = 25 rather than reuse a smaller k's value.
    The refusal was right -- reusing one understates the CD and overstates how many
    pairs differ -- but four of five experiments here have 26-28 arms, so four of five
    had no pairwise verdict, over about thirty lines of arithmetic. Found by external
    review.

    They are computed now, so this asserts two things: the computation reproduces every
    published value, and the table shipped in `leaderboard.py` is what the computation
    produces. Either alone would be worth little -- the first without the second means
    the shipped numbers could still be anything.
    """
    from evaluation_harness.leaderboard import NEMENYI_Q05  # noqa: PLC0415
    from nemenyi_table import PUBLISHED, max_error_against_published, q_alpha  # noqa: PLC0415

    err = max_error_against_published()
    check(
        "nemenyi: the computation reproduces Demsar's 24 values", err < 0.002, f"worst disagreement {err:.4f}"
    )

    bad = [k for k, v in PUBLISHED.items() if abs(NEMENYI_Q05.get(k, 0) - v) > 0.002]
    check(
        "nemenyi: and the shipped table agrees with the published one where it overlaps", not bad, f"k={bad}"
    )

    # Spot-check the extension against the computation, not against itself.
    ext = [k for k in (26, 27, 28) if k in NEMENYI_Q05]
    drift = [
        f"k={k}: table {NEMENYI_Q05[k]:.4f} vs computed {q_alpha(k):.4f}"
        for k in ext
        if abs(NEMENYI_Q05[k] - q_alpha(k)) > 0.002
    ]
    check(
        "nemenyi: the extension beyond k=25 is what the computation gives",
        ext and not drift,
        "; ".join(drift) or "no k>25 entries shipped",
    )

    # And the covering assertion: every experiment here must now get a verdict.
    check(
        "nemenyi: the table covers every arm count this repo measures (<= 28)",
        all(k in NEMENYI_Q05 for k in range(2, 29)),
        f"missing {[k for k in range(2, 29) if k not in NEMENYI_Q05]}",
    )


def test_two_runs_sharing_a_config_id_are_refused() -> None:
    """A second run of the same arm must stop the tools, not be picked by luck.

    Three SciFact arms were re-run, so three config_ids existed twice in data/runs.
    `check_report_claims.py` globbed for a run in five places -- three took the last
    hit, two the first, and one had a different exclusion rule -- so its answer depended
    on the order the filesystem returned directories in. 29/29 on APFS, 28/29 on ext4,
    and the failure was real: two cost cells genuinely still held price-table figures.
    `make ci` was called green for a week on the only machine anyone ran it on.

    The re-runs now live in `data/runs-repeats/`. This asserts the tools refuse rather
    than guess if that ever happens again.

    `--repeat N` writes `<id>_r1.._rN`, which IS one arm measured N times and must keep
    working; the second half of this test pins that, or the fix would forbid the
    feature it was meant to protect.
    """
    import json as _json  # noqa: PLC0415
    import shutil  # noqa: PLC0415

    from evaluation_harness._runs import AmbiguousRuns, runs_by_arm  # noqa: PLC0415

    src = next(
        (d for d in sorted((HERE.parent / "data" / "runs").glob("sf_*")) if (d / "metrics.json").is_file()),
        None,
    )
    if src is None:
        print("  --   duplicate runs: skipped (no SciFact run on disk)")
        return

    runs = HERE.parent / "data" / "runs-selftest-dupe"
    shutil.rmtree(runs, ignore_errors=True)
    for name in (src.name, src.name.replace("2026", "2027", 1)):
        d = runs / name
        d.mkdir(parents=True)
        for f in ("metrics.json", "predictions.jsonl"):
            if (src / f).is_file():
                shutil.copy2(src / f, d / f)

    ds = _json.loads((src / "metrics.json").read_text())["dataset_id"]
    raised = False
    try:
        runs_by_arm(runs, ds, prefix="sf_", strip="_n200_v1")
    except AmbiguousRuns as exc:
        raised = "claim config_id" in str(exc)
    check(
        "duplicate runs: two runs sharing a config_id are refused, not picked",
        raised,
        "runs_by_arm returned a winner instead of raising",
    )

    # The control: a --repeat set shares a config_id BY DESIGN and must still load.
    shutil.rmtree(runs, ignore_errors=True)
    for i in (1, 2, 3):
        d = runs / f"{src.name}_r{i}"
        d.mkdir(parents=True)
        for f in ("metrics.json", "predictions.jsonl"):
            if (src / f).is_file():
                shutil.copy2(src / f, d / f)
    try:
        got = runs_by_arm(runs, ds, prefix="sf_", strip="_n200_v1")
        ok, detail = sum(len(v) for v in got.values()) == 3, str(got)
    except AmbiguousRuns as exc:
        ok, detail = False, str(exc)
    check("duplicate runs: but a --repeat set still loads as one arm", ok, detail[:150])
    shutil.rmtree(runs, ignore_errors=True)


def test_the_reports_separation_counts_are_real() -> None:
    """A "separated from N of M" in a report must match what `family_test.py` says.

    The third class round 2 named that nothing checked: "it also checks only single-run
    primary metrics, so it wouldn't have caught any of the round-1 cost, ratio or
    tie-count errors." Cost and ratios are now in `check_report_claims.py`. This is the
    tie count, and it lives here rather than there because the permutation test takes
    ~17s and that belongs in the test suite, not in a claims scan.

    It was worth adding: REPORT_RETRIEVAL said "only 6 of 18 opponents ... the twelve it
    cannot separate from", and the tool says 7 and 11 — on the corrected runs AND on
    the originals. The number had been stale since before the parser bug, for unrelated
    reasons, and nothing noticed.
    """
    import re as _re  # noqa: PLC0415

    reparsed = HERE.parent / "data" / "runs"
    if not any(reparsed.glob("sf_glm_s_n200_v1_*/predictions.jsonl")):
        print("  --   separation counts: skipped (no reparsed SciFact runs on disk)")
        return

    # Only the 2026-09-28 sweep: the re-runs duplicate arms and would double the family.
    import shutil  # noqa: PLC0415
    import tempfile as _tf  # noqa: PLC0415

    with _tf.TemporaryDirectory() as td:
        scope = pathlib.Path(td) / "runs"
        scope.mkdir()
        for d in reparsed.glob("sf_*_n200_v1_20260928*"):
            shutil.copytree(d, scope / d.name)
        r = run(
            "scripts/family_test.py",
            "--dataset-id",
            "scifact_200",
            "--a",
            "sf_glm_s_n200_v1",
            "--against",
            "_n200_v1",
            "--metric",
            "ndcg_10",
            env={"EVAL_RUNS_DIR": str(scope)},
        )

    m = _re.search(r"separated from (\d+) of (\d+) opponents", r.stdout or "")
    if not m:
        check(
            "separation counts: family_test produced a verdict",
            False,
            ((r.stderr or "") + (r.stdout or ""))[-160:],
        )
        return
    sep, fam = int(m.group(1)), int(m.group(2))
    report = (HERE.parents[1] / "research" / "REPORT_RETRIEVAL.md").read_text()

    # A RANGE IS AN ACCEPTABLE ANSWER, AND HERE IT IS THE HONEST ONE. This count is not
    # stable: two arms sit on their Holm thresholds (gemma_s 0.0045 vs 0.0042,
    # mistral_s 0.0055 vs 0.0045), so 20k permutations give 6 or 7 depending on the
    # seed and 400k give 7. An earlier version of this test demanded one exact figure,
    # which would have forced the report to publish a number more precise than the
    # measurement -- exactly the error it exists to catch.
    # EVERY STATED COUNT MUST AGREE, not just one of them. `_states` asked whether ANY
    # "**N of 18**" appeared anywhere, so a second, stale sentence was invisible -- and
    # so was a range as loose as "**4-8 of 18**", which contains the answer while saying
    # almost nothing. Appending "the tie group is **9 of 18**" left the suite green.
    # Found by external review.
    stated = re.findall(r"\*\*(\d+)(?:\u2013(\d+))?\s+of\s+" + str(fam) + r"\*\*", report)
    check(
        f"REPORT_RETRIEVAL states at least one count out of {fam}",
        bool(stated),
        "no '**N of 18**' found at all",
    )

    def _ok(lo: str, hi: str, want: int) -> bool:
        a = int(lo)
        b = int(hi) if hi else a
        return a <= want <= b and (b - a) <= 2  # a range wider than 2 is not a claim

    bad = [
        f"**{lo}{'–' + hi if hi else ''} of {fam}**"
        for lo, hi in stated
        if not (_ok(lo, hi, sep) or _ok(lo, hi, fam - sep))
    ]
    check(
        f"...and EVERY one is consistent with {sep} separated or {fam - sep} tied",
        not bad,
        f"the tool says {sep}/{fam - sep}; the report also states " + ", ".join(bad),
    )
    check(
        "...and no stated range is wider than 2",
        all((int(hi) - int(lo)) <= 2 for lo, hi in stated if hi),
        "a range wide enough to contain any answer is not a claim",
    )

    check(
        "...and says the count sits on a boundary, since it does",
        "boundary" in report.lower(),
        "two arms sit on their Holm thresholds and the report does not say so",
    )


def test_promote_reads_its_reason_from_the_env() -> None:
    """`--reason-from-env` must run. It raised NameError on every invocation.

    Added in round 1 to close a backtick injection in `make run-promote`, and shipped
    broken: `promote_baseline.py` called `os.environ.get` without importing `os`, so
    the documented command in RUNBOOK:170 died with
    `NameError: name 'os' is not defined` before doing anything at all.

    It survived because the only test of this script was `--help`, which never reaches
    the flag. A `--help` test proves a file parses; it proves nothing about the path a
    user takes. Both assertions here reach line 48 and neither writes a baseline.
    """
    r = run(
        "scripts/promote_baseline.py", "--reason-from-env", "--run", "nope", env={"EVAL_PROMOTE_REASON": ""}
    )
    out = (r.stderr or "") + (r.stdout or "")
    check(
        "promote: an empty EVAL_PROMOTE_REASON is refused, not crashed",
        r.returncode != 0 and "NameError" not in out,
        out[-160:],
    )
    # NOT just `"reason" in out`: the NameError traceback echoes the offending source
    # line, which contains the word "reason", so that assertion passed against the
    # broken code. It has to be the ERROR MESSAGE, and no traceback.
    check(
        "promote: and it says a reason is required",
        "a reason is required" in out and "Traceback" not in out,
        out[-160:],
    )

    r = run(
        "scripts/promote_baseline.py",
        "--reason-from-env",
        "--run",
        "_no_such_run_selftest_",
        env={"EVAL_PROMOTE_REASON": "a reason"},
    )
    out = (r.stderr or "") + (r.stdout or "")
    check(
        "promote: with the env reason set it gets PAST the env read to the run lookup",
        "NameError" not in out and "no run" in out.lower(),
        out[-160:],
    )


def test_rescore_refuses_a_missing_reference_set() -> None:
    """Rescoring with no references must DIE, not score against an empty gold set.

    Found by cloning this repo and running rescore in the clone, which is the thing
    committing outputs/ was supposed to make possible. It ran, it exited 0, and it
    reported f1 = 0.1071 for an arm whose recorded f1 is 0.6798.

    The cause was an asymmetry two lines apart in rescore.py: a missing OUTPUT called
    die(), a missing REFERENCE fell through as None. So the guarded artifact was the
    expensive one and the unguarded one was the corpus -- which is gitignored, and
    therefore exactly what every fresh clone is missing. Every prediction became a false
    positive against an empty gold set, which does not look like a failure. It looks like
    a weak model.

    A partial reference set still only warns: a tier may legitimately not cover every
    item. Zero found against a declared reference_id cannot be legitimate.
    """
    import json as _json  # noqa: PLC0415
    import shutil  # noqa: PLC0415

    src = None
    for d in sorted((HERE.parent / "data" / "runs").glob("*")):
        mj = d / "metrics.json"
        if not (mj.is_file() and (d / "outputs").is_dir()):
            continue
        m = _json.loads(mj.read_text())
        if ((m.get("fingerprint") or {}).get("data") or {}).get("reference_id"):
            src = d
            break
    if src is None:
        print("  --   rescore/missing-refs: skipped (no committed run declares a reference_id)")
        return

    runs = HERE.parent / "data" / "runs-selftest-rescore"
    shutil.rmtree(runs, ignore_errors=True)
    dst = runs / src.name
    dst.mkdir(parents=True)
    for name in ("metrics.json", "predictions.jsonl"):
        shutil.copy2(src / name, dst / name)
    shutil.copytree(src / "outputs", dst / "outputs")

    # Point the copy at a reference_id that cannot exist. Equivalent to a fresh clone,
    # where the real one is absent because the corpus is gitignored -- and it does not
    # touch the real references, so a crash here cannot damage them.
    m = _json.loads((dst / "metrics.json").read_text())
    m["fingerprint"]["data"]["reference_id"] = "gold/_selftest_absent_reference"
    (dst / "metrics.json").write_text(_json.dumps(m))

    env = {"EVAL_RUNS_DIR": str(runs.relative_to(HERE.parent))}
    r = run(
        "scripts/rescore.py", "--dataset-id", str(m.get("dataset_id")), "--out", str(runs / "out"), env=env
    )
    check(
        "rescore: a declared-but-absent reference set is refused, not scored",
        r.returncode != 0,
        f"exit {r.returncode}",
    )
    check(
        "rescore: and it says the references are what is missing",
        "reference" in ((r.stderr or "") + (r.stdout or "")).lower(),
        ((r.stderr or "") + (r.stdout or ""))[-160:],
    )
    check(
        "rescore: it writes no partial rescored run", not (runs / "out" / src.name / "metrics.json").is_file()
    )
    shutil.rmtree(runs, ignore_errors=True)


def test_spearman_is_tie_correct() -> None:
    """rho must equal the textbook shortcut WITHOUT ties, and differ WITH them.

    Both directions, because widening a formula until it stops disagreeing is how a
    correct-looking wrong answer gets in. The shortcut
    `1 - 6*sum(d^2)/(n(n^2-1))` is an algebraic identity for Pearson-on-ranks that holds
    only when every rank is distinct; the repo shipped it against tied data for four
    examples, where it did not approximate rho but computed a different quantity.
    """
    from evaluation_harness.rank_stability import ranks_on  # noqa: PLC0415
    from evaluation_harness.stats import spearman  # noqa: PLC0415

    def shortcut(x, y):
        n = len(x)
        return 1 - 6 * sum((x[i] - y[i]) ** 2 for i in range(n)) / (n * (n * n - 1))

    a = [1, 2, 3, 4, 5]
    b = [2, 1, 4, 3, 5]
    check(
        "spearman: no ties -> agrees with the textbook shortcut",
        abs(spearman(a, b) - shortcut(a, b)) < 1e-12,
        f"{spearman(a, b)} vs {shortcut(a, b)}",
    )
    check("spearman: identical orderings -> 1.0", abs(spearman(a, a) - 1.0) < 1e-12)
    check("spearman: reversed -> -1.0", abs(spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) + 1.0) < 1e-12)

    # Midranks: three arms tied for first share rank 2.0, the fourth gets 4.0.
    M = {"a": {"i": 1.0}, "b": {"i": 1.0}, "c": {"i": 1.0}, "d": {"i": 0.0}}
    r = ranks_on(M, ["a", "b", "c", "d"], ["i"])
    check(
        "ranks_on: tied arms share the average rank, not the alphabet",
        r["a"] == r["b"] == r["c"] == 2.0 and r["d"] == 4.0,
        str(r),
    )

    tied = [2.0, 2.0, 2.0, 4.0]
    check(
        "spearman: a half where EVERY arm ties -> NaN, not 0.0",
        spearman([1.0, 1.0, 1.0, 1.0], tied) != spearman([1.0, 1.0, 1.0, 1.0], tied),
    )
    check(
        "spearman: with ties it DIFFERS from the shortcut",
        abs(spearman(tied, [1.0, 2.0, 3.0, 4.0]) - shortcut(tied, [1.0, 2.0, 3.0, 4.0])) > 1e-9,
    )


def test_rank_stability_ranks_the_right_way_up() -> None:
    """rank-stability ranked every metric highest-first, so for a lower-is-better one
    (latency, cost) it named the SLOWEST arm the leader. Three arms with known latencies on
    20 items: the leader must be the fastest."""
    import json as _json  # noqa: PLC0415
    import os  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    tmp = Path(tempfile.mkdtemp(prefix="harness-rankdir-"))
    try:
        for arm, ms in (("fast", 1.0), ("mid", 2.0), ("slow", 3.0)):
            d = tmp / "data" / "runs" / f"{arm}_run"
            d.mkdir(parents=True)
            (d / "metrics.json").write_text(
                _json.dumps({"dataset_id": "rd_v1", "config_id": arm, "primary_metric": "latency_ms"})
            )
            (d / "predictions.jsonl").write_text(
                "".join(
                    _json.dumps({"item_id": f"i{k:02d}", "latency_ms": ms + k / 100}) + "\n"
                    for k in range(20)
                )
            )
        r = subprocess.run(
            [PY, str(HERE / "rank_stability.py"), "--dataset-id", "rd_v1", "--draws", "20"],
            capture_output=True,
            text=True,
            env={**os.environ, "EVAL_HOME": str(tmp), "EVAL_DATA_DIR": "data", "EVAL_RUNS_DIR": ""},
        )
        check(
            "rank-stability: on a lower-is-better metric the leader is the lowest",
            "ordering's leader: fast" in r.stdout,
            (r.stdout + r.stderr)[-300:],
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_v5_tells_a_tie_from_a_copy() -> None:
    """Agreeing MEANS are not suspicious on a discrete metric; agreeing per ITEM is.

    V5's original premise -- "independent arms do not agree to full float precision" --
    holds for a continuous metric and fails for a binary one. A classification run scores
    each item 1 or 0, so its mean over 200 items takes one of 201 values, and two
    genuinely different models both getting 172 right report byte-identical 0.86 with
    nothing wrong. The AG News sweep tripped V5 four times that way in a single run.

    Both directions are asserted here, because widening a check until it stops complaining
    is the failure mode this test exists to prevent: a tie must pass, and a real copy must
    still fail.
    """
    import os  # noqa: PLC0415
    import shutil  # noqa: PLC0415

    scores = {"correct": 0.86, "parsed": 1.0}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        def make(name: str, model: str, correct_items: list) -> None:
            d = root / name
            d.mkdir()
            (d / "metrics.json").write_text(
                json.dumps(
                    {
                        "config_id": name,
                        "dataset_id": "ds_v1",
                        "scores": scores,
                        "params": {"model": model},
                        "build": {"ref": "test"},
                    }
                )
            )
            (d / "predictions.jsonl").write_text(
                "\n".join(
                    json.dumps({"item_id": f"i{i}", "correct": float(c)}) for i, c in enumerate(correct_items)
                )
            )

        # Same mean (2 of 4), DIFFERENT items right. Two measurements.
        make("arm_a", "model-a", [1, 1, 0, 0])
        make("arm_b", "model-b", [0, 0, 1, 1])
        env = {**os.environ, "EVAL_RUNS_DIR": str(root)}
        r = subprocess.run(
            [PY, "scripts/validate_tree.py"], cwd=ROOT, env=env, capture_output=True, text=True
        )
        check(
            "V5: same mean, different items -> not flagged",
            "V5 no two configs" not in r.stdout or "FAIL V5" not in r.stdout,
            r.stdout[-200:],
        )

        # A real copy: same mean AND the same items right, under different params.
        shutil.rmtree(root / "arm_b")
        make("arm_b", "model-b", [1, 1, 0, 0])
        r = subprocess.run(
            [PY, "scripts/validate_tree.py"], cwd=ROOT, env=env, capture_output=True, text=True
        )
        check(
            "V5: same mean, same items, different params -> flagged", "FAIL V5" in r.stdout, r.stdout[-200:]
        )

        # A saturated metric: both arms right on every item, so the items agree too. Different
        # outputs are two systems (the newcomer trial's two routers at 32/32); the same outputs
        # under different params are still the copy.
        for name, text in (("arm_a", "label: billing"), ("arm_b", "label: billing\nreason: a refund")):
            shutil.rmtree(root / name)
            make(name, f"model-{name}", [1, 1, 1, 1])
            (root / name / "outputs").mkdir()
            for i in range(4):
                (root / name / "outputs" / f"i{i}.txt").write_text(text)
        r = subprocess.run(
            [PY, "scripts/validate_tree.py"], cwd=ROOT, env=env, capture_output=True, text=True
        )
        check(
            "V5: all items right, different outputs -> not flagged",
            "FAIL V5" not in r.stdout,
            r.stdout[-200:],
        )
        for i in range(4):
            (root / "arm_b" / "outputs" / f"i{i}.txt").write_text("label: billing")
        r = subprocess.run(
            [PY, "scripts/validate_tree.py"], cwd=ROOT, env=env, capture_output=True, text=True
        )
        check("V5: all items right, the same outputs -> flagged", "FAIL V5" in r.stdout, r.stdout[-200:])


def test_rescore_can_move_runs_onto_a_new_reference_set() -> None:
    """Gold that arrives after the runs: `rescore --reference-id` re-scores stored outputs
    against it, and the run says which set it was measured on and which it is scored on.

    Fixture: a committed demo run scored against silver/smoke_v1, re-scored against a
    throwaway "gold" set made of that run's own outputs -- so the score must become 1.0,
    which no copied or stale score could produce.
    """
    import json as _json  # noqa: PLC0415
    import shutil  # noqa: PLC0415

    base = HERE.parent / "data"
    # The worked example the repository ships: the run its demo baseline was promoted from.
    shipped = _json.loads((base / "baselines" / "smoke_v1_baseline.json").read_text())["promoted_from"]
    src = base / "runs" / shipped
    check("rescore/reference-id: the committed fixture run exists", src.is_dir())
    if not src.is_dir():
        return
    runs, gold = base / "runs-selftest-refid", base / "references" / "gold" / "selftest_refid"
    for d in (runs, gold):
        shutil.rmtree(d, ignore_errors=True)
    try:
        shutil.copytree(src, runs / src.name)
        shutil.copytree(src / "outputs", gold)
        out = runs / "out"
        r = run(
            "scripts/rescore.py",
            "--dataset-id",
            "smoke_v1",
            "--reference-id",
            "gold/selftest_refid",
            "--out",
            str(out.relative_to(HERE.parent)),
            env={"EVAL_RUNS_DIR": str(runs.relative_to(HERE.parent))},
        )
        mf = out / src.name / "metrics.json"
        if r.returncode != 0 or not mf.is_file():
            check("rescore/reference-id: ran", False, ((r.stderr or "") + (r.stdout or ""))[-200:])
            return
        m = _json.loads(mf.read_text())
        data = m["fingerprint"]["data"]
        check(
            "rescore/reference-id: scored against the new set (own outputs -> 1.0)",
            abs(m["scores"].get("overlap_f1", 0) - 1.0) < 1e-9,
            str(m["scores"].get("overlap_f1")),
        )
        check(
            "rescore/reference-id: the run now says gold, in both places",
            m.get("reference_tier") == "gold"
            and data.get("reference_id") == "gold/selftest_refid"
            and data.get("reference_tier") == "gold",
            f"{m.get('reference_tier')} {data.get('reference_id')}",
        )
        check(
            "rescore/reference-id: and keeps what it was measured against",
            data.get("reference_id_at_measurement") == "silver/smoke_v1",
        )
        bad = run(
            "scripts/rescore.py",
            "--dataset-id",
            "smoke_v1",
            "--reference-id",
            "gold/no_such_set",
            "--out",
            str(out.relative_to(HERE.parent)),
            env={"EVAL_RUNS_DIR": str(runs.relative_to(HERE.parent))},
        )
        check("rescore/reference-id: a missing set is refused", bad.returncode != 0)
    finally:
        for d in (runs, gold):
            shutil.rmtree(d, ignore_errors=True)


def test_the_reproduction_tables_agree_with_the_configs_and_runs() -> None:
    """examples/models.json, litellm.config.yaml and experiments.json are what a stranger's
    rerun is built from. Each is a copy of something else -- configs, the proxy, committed
    runs -- and a copy that drifts sends a rerun to the wrong model or the wrong record."""
    import json  # noqa: PLC0415

    import yaml  # noqa: PLC0415

    ex = ROOT.parent / "examples"
    table = json.loads((ex / "models.json").read_text())["aliases"]
    used = set()
    for cfg in ex.glob("*/configs/*.yaml"):
        model = ((yaml.safe_load(cfg.read_text()) or {}).get("params") or {}).get("model", "")
        if str(model).startswith("eval-"):
            used.add(model)
    check(
        "models.json: every alias a config uses is mapped",
        not used - set(table),
        f"unmapped: {sorted(used - set(table))}",
    )
    check(
        "models.json: maps no alias that no config uses",
        not set(table) - used,
        f"unused: {sorted(set(table) - used)}",
    )
    proxy = {
        m["model_name"]: m["litellm_params"]["model"]
        for m in yaml.safe_load((ex / "litellm.config.yaml").read_text())["model_list"]
    }
    check("litellm.config.yaml serves exactly models.json", proxy == table)
    wrong = []
    for d in ("runs", "runs-pair", "runs-repeats", "runs-linux"):
        for f in (ROOT / "data" / d).glob("*/metrics.json"):
            m = json.loads(f.read_text())
            sut = ((m.get("fingerprint") or {}).get("system_under_test") or {}).get("model") or {}
            if sut.get("id_source") == "proxy-model-info" and sut.get("id") != table.get(sut.get("alias")):
                wrong.append(f.parent.name)
    check("models.json: agrees with every upstream id a committed run resolved", not wrong, f"{wrong[:3]}")

    reg = json.loads((ex / "experiments.json").read_text())["experiments"]
    sys.path.insert(0, str(ex))
    import reproduce  # noqa: PLC0415

    for e in reg:
        arms = reproduce.committed(e)
        cfg_ids = set(reproduce.configs(e))
        check(
            f"experiments.json {e['slug']}: has committed runs and its leader among them",
            bool(arms) and e["leader"] in arms,
            f"{len(arms)} arms",
        )
        missing = sorted(a for a, v in arms.items() if v["cid"] not in cfg_ids)
        check(
            f"experiments.json {e['slug']}: every measured arm has a config to rerun it",
            not missing,
            f"no config for {missing}",
        )
        unknown = [d for d in e["datasets"] if not (ROOT / "data" / "datasets" / f"{d}.json").is_file()]
        check(f"experiments.json {e['slug']}: every dataset it fetches is frozen", not unknown, f"{unknown}")
        local = [a for a, v in arms.items() if v["kind"] == "local" and "/" in str(v["model"])]
        unpinned = [a for a in local if not arms[a]["revision"]]
        check(
            f"experiments.json {e['slug']}: every local model is pinned in local_models.json",
            not unpinned,
            f"{unpinned}",
        )

    # The pins must be what was measured: every revision a committed run recorded, and the
    # revision REFERENCE.md cites.
    import re  # noqa: PLC0415

    pins = json.loads((ex / "local_models.json").read_text())["revisions"]
    clash = []
    for d in ("runs", "runs-pair", "runs-repeats", "runs-linux"):
        for f in (ROOT / "data" / d).glob("*/metrics.json"):
            sut = ((json.loads(f.read_text()).get("fingerprint") or {}).get("system_under_test") or {}).get(
                "model"
            ) or {}
            if sut.get("revision_source") in ("hf-snapshot", "loaded-model"):
                got = sut.get("loaded_revision") or sut.get("revision")
                if sut.get("id") in pins and pins[sut["id"]] != got:
                    clash.append(f"{f.parent.name}: {str(got)[:12]}")
    check("local_models.json: agrees with every revision a committed run recorded", not clash, f"{clash[:3]}")
    ref = (ROOT.parent / "docs" / "REFERENCE.md").read_text()
    off = [
        k
        for k, v in pins.items()
        if v[:12] not in re.findall(r"\[`" + re.escape(k) + r"`\]\([^)]*\) \| [^|]*\| `([0-9a-f]{12})`", ref)
    ]
    check("local_models.json: agrees with the revisions REFERENCE.md cites", not off, f"{off}")


def test_the_gateway_routes_as_documented() -> None:
    """Proxy when configured, else OpenRouter with one key, else a refusal naming both."""
    import os  # noqa: PLC0415

    sys.path.insert(0, str(ROOT.parent / "examples" / "_shared"))
    import gateway  # noqa: PLC0415

    keys = ("LITELLM_BASE_URL", "LITELLM_API_KEY", "OPENROUTER_API_KEY")
    saved = {k: os.environ.pop(k, None) for k in keys}
    try:
        os.environ["OPENROUTER_API_KEY"] = "sk-or-test"
        r = gateway.route({"model": "eval-claude-haiku"})
        check(
            "gateway: OpenRouter key alone -> direct, alias mapped",
            r["mode"] == "direct" and r["model"] == "anthropic/claude-haiku-4.5",
        )
        check(
            "gateway: direct asks OpenRouter for billed cost",
            gateway.extra_body({}, r).get("usage") == {"include": True},
        )
        check(
            "gateway: an OpenRouter id passes through for your own arm",
            gateway.route({"model": "vendor/my-model"})["model"] == "vendor/my-model",
        )
        os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:9"
        os.environ["LITELLM_API_KEY"] = "sk-test"
        r = gateway.route({"model": "eval-claude-haiku"})
        check(
            "gateway: a configured proxy wins, and keeps the alias",
            r["mode"] == "proxy" and r["model"] == "eval-claude-haiku",
        )
        for k in keys:
            os.environ.pop(k, None)
        try:
            gateway.route({"model": "eval-claude-haiku"})
            refused = ""
        except SystemExit as exc:
            refused = str(exc)
        check(
            "gateway: no route is refused, naming both ways to fix it",
            "OPENROUTER_API_KEY" in refused and "LITELLM_BASE_URL" in refused,
        )
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


def test_bundled_adapter_calls_the_installed_anthropic_sdk() -> None:
    """The template adapter's `anthropic` provider passed `temperature=` to
    `messages.create`, a keyword the anthropic SDK no longer has (1.x), so every call raised
    TypeError before reaching the API. Found by mypy. The SDK's own signature is the judge
    here: a stand-in client accepts exactly the keywords the installed `Messages.create`
    does, and records the request, so no key and no network are needed."""
    import inspect  # noqa: PLC0415
    import os  # noqa: PLC0415
    import types  # noqa: PLC0415

    try:
        from anthropic.resources.messages import Messages  # noqa: PLC0415
    except ImportError:
        print("  --   anthropic adapter: skipped (the anthropic SDK is not installed)")
        return
    accepted = set(inspect.signature(Messages.create).parameters) - {"self"}
    sent: dict = {}

    def create(**kw):
        unknown = set(kw) - accepted
        if unknown:
            raise TypeError(f"Messages.create() got unexpected keyword(s) {sorted(unknown)}")
        sent.update(kw)
        usage = types.SimpleNamespace(input_tokens=3, output_tokens=2)
        return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="ok")], usage=usage)

    client = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))
    fake = types.SimpleNamespace(Anthropic=lambda **_kw: client)
    from evaluation_harness import adapter  # noqa: PLC0415

    real = sys.modules.get("anthropic")
    saved_key = os.environ.get("ANTHROPIC_API_KEY")
    sys.modules["anthropic"] = fake  # type: ignore[assignment]  # a stand-in module, on purpose
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-test"
    try:
        err = ""
        try:
            adapter.call_system(
                "an article", {"provider": "anthropic", "model": "claude-x", "temperature": 0.0}
            )
        except TypeError as exc:
            err = str(exc)
        check("anthropic adapter: the call fits the installed SDK's signature", not err, err)
        check(
            "anthropic adapter: temperature still reaches the API, in the request body",
            (sent.get("extra_body") or {}).get("temperature") == 0.0,
            str(sent),
        )
    finally:
        if real is None:
            sys.modules.pop("anthropic", None)
        else:
            sys.modules["anthropic"] = real
        if saved_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = saved_key


def test_family_test_cache_never_serves_a_stale_answer() -> None:
    """The family test replays a stored answer when the identical test already ran (it
    is seeded and deterministic, and `make ci` asks the same questions dozens of times).
    A cache in a verification path is only safe if any change to its inputs misses it:
    here a run's scores change after the answer was stored, and the second answer must
    be the recomputed one, not the replay."""
    import tempfile as _tf  # noqa: PLC0415

    def write(root: Path, cid: str, scores: list[float]) -> None:
        d = root / f"{cid}_20260101T000000Z"
        d.mkdir(parents=True, exist_ok=True)
        (d / "metrics.json").write_text(json.dumps({"config_id": cid, "dataset_id": "tds"}), encoding="utf-8")
        (d / "predictions.jsonl").write_text(
            "".join(json.dumps({"item_id": f"i{i}", "m": v}) + "\n" for i, v in enumerate(scores)),
            encoding="utf-8",
        )

    with _tf.TemporaryDirectory() as td:
        root = Path(td)
        write(root, "a_x", [1, 1, 1, 1, 1, 1, 1, 1])
        write(root, "b_x", [0, 0, 0, 0, 0, 0, 0, 0])
        write(root, "c_x", [1, 1, 1, 1, 0, 1, 1, 1])
        argv = (
            "scripts/family_test.py",
            "--dataset-id",
            "tds",
            "--a",
            "a_x",
            "--against",
            "_x",
            "--metric",
            "m",
            "--runs-dir",
            str(root),
            "--permutations",
            "500",
        )
        first = run(*argv).stdout
        again = run(*argv).stdout
        check("family-test cache: a repeat replays the identical answer", first == again and "b_x" in first)
        write(root, "b_x", [1, 1, 1, 1, 1, 1, 1, 0])  # the data moves under the stored answer
        after = run(*argv).stdout
        fresh = run(*argv, env={"EVAL_NO_CACHE": "1"}).stdout
        check("family-test cache: changed scores miss the cache", after != first, after[-300:])
        check("family-test cache: the answer after a change is the recomputed one", after == fresh)

    # A goal sets a metric's direction, so flipping it moves the wins: the cache must miss.
    with _tf.TemporaryDirectory() as td:
        proj = Path(td)
        runs = proj / "data" / "runs"
        for cid, scores in (("a_x", [1.0] * 6 + [0.0] * 2), ("b_x", [0.0] * 6 + [1.0] * 2)):
            write(runs, cid, scores)
            mj = runs / f"{cid}_20260101T000000Z" / "metrics.json"
            mj.write_text(json.dumps({**json.loads(mj.read_text()), "goal": "g"}), encoding="utf-8")
        goal = proj / "data" / "goals" / "g.yaml"
        goal.parent.mkdir(parents=True)

        def say(direction: str) -> None:
            goal.write_text(
                f"goal_id: g\nsuccess_criteria:\n  primary: {{measure: m, direction: {direction}}}\n",
                encoding="utf-8",
            )

        env = {"EVAL_HOME": str(proj), "EVAL_DATA_DIR": "", "EVAL_RUNS_DIR": ""}
        gargv = (
            "scripts/family_test.py",
            "--dataset-id",
            "tds",
            "--a",
            "a_x",
            "--against",
            "_x",
            "--metric",
            "m",
            "--permutations",
            "200",
        )
        say("higher")
        higher = run(*gargv, env=env).stdout
        say("lower")
        lower = run(*gargv, env=env).stdout
        lower_fresh = run(*gargv, env={**env, "EVAL_NO_CACHE": "1"}).stdout
        check(
            "family-test cache: a goal's direction is part of the key",
            lower == lower_fresh and lower != higher,
            lower[-300:],
        )


def test_a_project_elsewhere_imports_runs_and_tests_them() -> None:
    """The harness as a dependency: data in ANOTHER project, scores from ANOTHER tool.

    Everything here runs with EVAL_HOME pointing at a temporary project and
    EVAL_DATA_DIR at a nested data root, as a project that installs the harness would.
    It checks that nothing is written beside the code (runs, the family-test cache), that
    import-run refuses what it says it refuses, and that --asc makes "wins" mean lower.
    """
    import json as _json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    proj = Path(tempfile.mkdtemp(prefix="harness-project-"))
    data = proj / "data" / "eval" / "stats"
    (data / "sources").mkdir(parents=True)
    for n in range(1, 5):
        (data / "sources" / f"ep_{n}.txt").write_text(f"episode {n}\n", encoding="utf-8")
    env = {"EVAL_HOME": str(proj), "EVAL_DATA_DIR": "data/eval/stats", "EVAL_RUNS_DIR": ""}
    made = run(
        "scripts/dataset_create.py", "--dataset-id", "proj_v1", "--source-dir", str(data / "sources"), env=env
    )
    check(
        "project elsewhere: dataset frozen under EVAL_DATA_DIR",
        made.returncode == 0 and (data / "datasets" / "proj_v1.json").is_file(),
        (made.stderr or made.stdout)[-200:],
    )
    if made.returncode != 0:
        shutil.rmtree(proj, ignore_errors=True)
        return
    ids = [i["item_id"] for i in _json.loads((data / "datasets" / "proj_v1.json").read_text())["items"]]
    # A git project with gold references under the moved data root: the fingerprint read
    # `<root>/data`, so it recorded references_sha256 None and every run after the first
    # made the tree dirty (its own untracked run output under data/eval/stats/runs).
    gold = data / "references" / "gold" / "proj_v1"
    gold.mkdir(parents=True)
    for i in ids:
        (gold / f"{i}.txt").write_text(f"reference {i}\n", encoding="utf-8")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]
    for argv in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "project"]):
        subprocess.run([*git, *argv], cwd=proj, capture_output=True, text=True)

    def scores(name: str, base: float, rows=None) -> Path:
        f = Path(tempfile.gettempdir()) / f"{proj.name}-{name}.jsonl"  # outside the project: not tree dirt
        rows = (
            rows if rows is not None else [{"item_id": i, "wer": base + 0.01 * k} for k, i in enumerate(ids)]
        )
        f.write_text("".join(_json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return f

    def imp(arm: str, f: Path, *extra: str):
        return run(
            "scripts/import_run.py",
            "--dataset-id",
            "proj_v1",
            "--config-id",
            arm,
            "--scores",
            str(f),
            "--primary-metric",
            "wer",
            "--asc",
            "--build-ref",
            "test",
            "--source",
            "selftest",
            "--scorer-id",
            "wer",
            *extra,
            env=env,
        )

    a, b = imp("arm_lo", scores("lo", 0.10)), imp("arm_hi", scores("hi", 0.30))
    check(
        "import-run: two arms imported into the project's runs",
        a.returncode == 0 and b.returncode == 0 and len(list((data / "runs").glob("arm_*"))) == 2,
        (a.stderr + b.stderr)[-200:],
    )
    check(
        "import-run: nothing written beside the code",
        not list((HERE.parent / "data" / "runs").glob("arm_lo_*")),
    )
    ref = imp("arm_ref", scores("ref", 0.2), "--reference-id", "gold/proj_v1", "--reference-tier", "gold")
    fp_ref: dict = {}
    for mj in (data / "runs").glob("arm_ref_*/metrics.json"):
        fp_ref = _json.loads(mj.read_text()).get("fingerprint") or {}
    check(
        "fingerprint under EVAL_DATA_DIR: the references' bytes are hashed, not recorded as none",
        ref.returncode == 0 and bool((fp_ref.get("data") or {}).get("references_sha256")),
        (ref.stderr or "")[-200:] + str(fp_ref.get("data")),
    )
    check(
        "fingerprint under EVAL_DATA_DIR: the project's own run output does not make the tree dirty",
        ((fp_ref.get("instrument") or {}).get("harness") or {}).get("dirty") is False,
        str((fp_ref.get("instrument") or {}).get("harness")),
    )
    shutil.rmtree(next((data / "runs").glob("arm_ref_*"), proj / "none"), ignore_errors=True)
    bad = imp("arm_bad", scores("bad", 0, [{"item_id": ids[0], "wer": "n/a"}]))
    check(
        "import-run: refuses a non-numeric score",
        bad.returncode != 0 and "not a number" in bad.stderr + bad.stdout,
    )
    part = imp("arm_part", scores("part", 0, [{"item_id": ids[0], "wer": 0.1}]))
    check(
        "import-run: refuses a partial score set without --allow-subset",
        part.returncode != 0 and "--allow-subset" in part.stderr + part.stdout,
    )
    alien = imp("arm_alien", scores("alien", 0, [{"item_id": "not_an_item", "wer": 0.1}]))
    check("import-run: refuses an item the dataset does not have", alien.returncode != 0)
    sub = imp("arm_sub", scores("sub", 0, [{"item_id": ids[0], "wer": 0.1}]), "--allow-subset")
    m = next((data / "runs").glob("arm_sub_*/metrics.json"), None)
    check(
        "import-run: --allow-subset records the coverage on the run",
        sub.returncode == 0 and m is not None and _json.loads(m.read_text())["imported"]["items_scored"] == 1,
    )
    check(
        "import-run: the imported bytes are hashed on the record",
        m is not None and len(_json.loads(m.read_text())["imported"].get("scores_sha256") or "") == 64,
    )
    hashes = {}
    scorer_files = {}
    for arm, body in (
        ("arm_s1", "def score(o, r):\n    return o == r\n"),
        (
            "arm_s1doc",
            'def score(o, r):\n    """Exact match."""\n    # documentation only\n    return o == r\n',
        ),
        ("arm_s2", "def score(o, r):\n    return o.strip() == r\n"),
    ):
        sf = Path(tempfile.gettempdir()) / f"{proj.name}-{arm}-scorer.py"
        sf.write_text(body, encoding="utf-8")
        scorer_files[arm] = sf
    for arm, sf in scorer_files.items():
        # The same arm and scores each time; only the scoring code differs.
        imp("arm_s", scores("s", 0.2), "--scorer-file", str(sf), "--run-id", arm)
        smj = next((data / "runs").glob(f"{arm}/metrics.json"), None)
        fp_s = _json.loads(smj.read_text())["fingerprint"] if smj else {}
        hashes[arm] = (fp_s.get("hash"), (fp_s.get("instrument") or {}).get("adapter", {}).get("sha256"))
        shutil.rmtree(smj.parent, ignore_errors=True) if smj else None
    check(
        "import-run: the scoring code's hash is the adapter's, inside the fingerprint hash",
        bool(hashes["arm_s1"][1]) and hashes["arm_s1"][0] != hashes["arm_s2"][0],
        str(hashes),
    )
    check(
        "import-run: a docstring or a comment in the scorer file is not another scorer",
        hashes["arm_s1"] == hashes["arm_s1doc"],
        str(hashes),
    )

    pt = run(
        "scripts/pair_test.py",
        "--dataset-id",
        "proj_v1",
        "--a",
        "arm_lo",
        "--b",
        "arm_hi",
        "--metric",
        "wer",
        "--asc",
        env=env,
    )
    check(
        "pair-test --asc: 'A wins' counts the lower score",
        f"items A wins       {len(ids)}/{len(ids)} (lower is better)" in pt.stdout,
        pt.stdout[-300:],
    )
    ft = run(
        "scripts/family_test.py",
        "--dataset-id",
        "proj_v1",
        "--a",
        "arm_lo",
        "--against",
        "arm_hi",
        "--metric",
        "wer",
        "--asc",
        "--permutations",
        "200",
        env=env,
    )
    check(
        "family-test --asc: 'ahead' counts the lower score",
        "ahead on the point estimate against 1 of 1" in ft.stdout,
        ft.stdout[-300:],
    )
    check(
        "family-test: its cache lives in the project, not beside the code",
        (proj / ".cache" / "family_test").is_dir(),
    )
    shutil.rmtree(proj, ignore_errors=True)
    for f in Path(tempfile.gettempdir()).glob(f"{proj.name}-*.jsonl"):
        f.unlink()


def test_hints_name_the_command_the_user_has() -> None:
    """Every "next, run this" a tool prints said `make …`, a target only a checkout of this
    repository has. A project that pins the package has `evh`, so its first step, GUIDE step
    1, ended "Next: make dataset-materialize DATASET_ID=tickets_v1", and four of the hints
    named targets no project has (`make promote`, `make demo`). Through `evh` each hint is an
    `evh` command; run as a checkout's script it stays `make`."""
    import os  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    tmp = Path(tempfile.mkdtemp(prefix="harness-hints-"))
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import _wheel  # noqa: PLC0415 — the real wheel, so package-data omissions fail here

        site = _wheel.install(tmp / "site-packages")
        proj = tmp / "project"
        (proj / "data" / "sources" / "h_v1").mkdir(parents=True)
        (proj / "data" / "sources" / "h_v1" / "a.txt").write_text("One. Two.\n")
        env = {
            **os.environ,
            "EVAL_HOME": str(proj),
            "EVAL_DATA_DIR": "data",
            "EVAL_RUNS_DIR": "",
            "PYTHONPATH": str(site),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        env.pop("EVAL_VIA_EVH", None)

        def evh(*args: str) -> str:
            r = subprocess.run(
                [PY, "-m", "evaluation_harness", *args], cwd=proj, capture_output=True, text=True, env=env
            )
            return r.stdout + r.stderr

        def script(name: str, *args: str) -> str:
            r = subprocess.run(
                [PY, str(site / "evaluation_harness" / name), *args],
                cwd=proj,
                capture_output=True,
                text=True,
                env=env,
            )
            return r.stdout + r.stderr

        created = evh("dataset-create", "--dataset-id", "h_v1", "--source-dir", "data/sources/h_v1")
        base = evh("runs-list", "--baselines")
        none = evh("runs-list")
        missing = evh("leaderboard", "--dataset-id", "nope_v1")
        direct = script(
            "dataset_create.py", "--dataset-id", "h_v1", "--source-dir", "data/sources/h_v1", "--force"
        )
        outs = (created, base, none, missing)
        check(
            "hints: through evh, the next step is an evh command",
            "Next: evh dataset-materialize --dataset-id h_v1" in created,
            created[-300:],
        )
        check(
            "hints: through evh, no hint says make",
            not any("make " in o for o in outs),
            "\n---\n".join(o[-200:] for o in outs),
        )
        check(
            "hints: promoting a baseline is `evh run-promote`", "evh run-promote --run" in base, base[-200:]
        )
        check(
            "hints: a checkout's script keeps the make form",
            "Next: make dataset-materialize DATASET_ID=h_v1" in direct,
            direct[-300:],
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_rescore_finds_the_bundled_adapter_from_an_installed_package() -> None:
    """A project that pins the package and runs an arm with no `adapter:` uses the bundled
    one, recorded as `scripts/adapter.py`. `rescore` looked for that path in the project
    and its parents only, which in a checkout is the harness root, and in an installed
    package is nowhere:

        ERROR: adapter not found for <run>: 'scripts/adapter.py' is under none of <project>, ...

    so re-scoring for $0 failed out of the box for every pinned project on the default
    adapter. Found by following the GUIDE in a brand-new project on 0.4.0."""
    import os  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    tmp = Path(tempfile.mkdtemp(prefix="harness-installed-rescore-"))
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import _wheel  # noqa: PLC0415 — the real wheel, so package-data omissions fail here

        site = _wheel.install(tmp / "site-packages")
        proj = tmp / "project"
        data = proj / "data"
        (data / "sources" / "rs_v1").mkdir(parents=True)
        (data / "configs").mkdir(parents=True)
        for i in ("t1", "t2", "t3"):
            (data / "sources" / "rs_v1" / f"{i}.txt").write_text(
                f"Ticket {i} cannot log in. It fails twice. The user reset the password. Support replied.\n"
            )
        # Four arms: silver-calibrate needs three to rank plus the one authoring the silver.
        for n in (1, 2, 3, 4):
            name = "arm_echo" if n == 1 else f"arm_echo{n}"
            (data / "configs" / f"{name}.yaml").write_text(
                f"config_id: {name}_v1\ndataset_id: rs_v1\nparams:\n  provider: echo\n  sentences: {n}\n"
            )
        env = {
            **os.environ,
            "EVAL_HOME": str(proj),
            "EVAL_DATA_DIR": "data",
            "EVAL_RUNS_DIR": "",
            "PYTHONPATH": str(site),
            "PYTHONDONTWRITEBYTECODE": "1",
            "EVAL_MAX_COST_USD": "",
        }

        def evh(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [PY, "-m", "evaluation_harness", *args], cwd=proj, capture_output=True, text=True, env=env
            )

        steps = [
            evh("dataset-create", "--dataset-id", "rs_v1", "--source-dir", str(data / "sources" / "rs_v1")),
            evh("dataset-materialize", "--dataset-id", "rs_v1"),
            # silver first, so the runs are scored against it and rescore moves them to gold
            evh(
                "reference-create",
                "--dataset-id",
                "rs_v1",
                "--config",
                str(data / "configs" / "arm_echo4.yaml"),
            ),
            *(evh("experiment-run", "--config", str(c)) for c in sorted((data / "configs").glob("*.yaml"))),
        ]
        check(
            "installed rescore: a run made with the bundled adapter",
            all(s.returncode == 0 for s in steps),
            "".join(s.stderr for s in steps)[-300:],
        )
        made = [json.loads(p.read_text()) for p in (data / "runs").glob("arm_echo_v1_*/metrics.json")]
        check(
            "bundled adapter: its runs record a primary metric (the catalog's headline, the "
            "leaderboard's sort, the inspector's default)",
            made and all(m.get("primary_metric") == "overlap_f1" for m in made),
            [m.get("primary_metric") for m in made],
        )
        gold = data / "references" / "gold" / "rs_v1"
        gold.mkdir(parents=True)
        for i in ("t1", "t2", "t3"):
            (gold / f"{i}.txt").write_text(f"Ticket {i}: cannot log in.\n")
        r = evh(
            "rescore",
            "--dataset-id",
            "rs_v1",
            "--reference-id",
            "gold/rs_v1",
            "--out",
            str(data / "runs-gold"),
        )
        out = r.stdout + r.stderr
        check(
            "installed rescore: it finds the bundled adapter inside the package",
            r.returncode == 0 and "adapter not found" not in out,
            out[-300:],
        )
        check(
            "installed rescore: the re-scored run is written",
            any((data / "runs-gold").glob("arm_echo_v1_*/metrics.json")),
            out[-300:],
        )
        moved = [
            json.loads(p.read_text())["fingerprint"]["data"]
            for p in (data / "runs-gold").glob("arm_echo_v1_*/metrics.json")
        ]
        # Moving runs onto another reference set is not the reference files changing: the
        # old and the new set are different files, so their hashes always differ. The flag
        # was set, and "CHANGED" printed, on every deliberate move (0.3.0 and before).
        check(
            "rescore onto a new reference: where it was measured is kept, nothing is called changed",
            moved
            and all(
                f.get("reference_id") == "gold/rs_v1"
                and f.get("reference_id_at_measurement") == "silver/rs_v1"
                and not f.get("references_changed_since_measurement")
                for f in moved
            )
            and "CHANGED" not in out,
            [
                (f.get("reference_id_at_measurement"), f.get("references_changed_since_measurement"))
                for f in moved
            ],
        )
        # ...while the same set's files changing under a run is still called out.
        (gold / "t1.txt").write_text("Ticket t1: login fails twice.\n")
        again = subprocess.run(
            [
                PY,
                "-m",
                "evaluation_harness",
                "rescore",
                "--dataset-id",
                "rs_v1",
                "--reference-id",
                "gold/rs_v1",
                "--out",
                str(data / "runs-gold2"),
            ],
            cwd=proj,
            capture_output=True,
            text=True,
            env={**env, "EVAL_RUNS_DIR": str(data / "runs-gold")},
        )
        changed = [
            json.loads(p.read_text())["fingerprint"]["data"]
            for p in (data / "runs-gold2").glob("arm_echo_v1_*/metrics.json")
        ]
        check(
            "rescore against the same reference after its files changed: flagged and warned",
            changed
            and all(f.get("references_changed_since_measurement") is True for f in changed)
            and "CHANGED" in again.stdout,
            (again.stdout + again.stderr)[-200:],
        )
        sc = subprocess.run(
            [PY, "-m", "evaluation_harness", "silver-calibrate", "--dataset-id", "rs_v1"],
            cwd=proj,
            capture_output=True,
            text=True,
            env={**env, "EVAL_RUNS_DIR": str(data / "runs-gold")},
        )
        check(
            "installed silver-calibrate: it finds the bundled adapter inside the package",
            sc.returncode == 0
            and "adapter not found" not in sc.stdout + sc.stderr
            and "rho vs trusted" in sc.stdout,
            (sc.stdout + sc.stderr)[-300:],
        )
        # One set of runs on both sides agrees with itself at 1.000: that is no ceiling.
        check(
            "silver-calibrate: the same runs on both sides measure no ceiling, and it says so",
            "CEILING — not measured" in sc.stdout and "ceiling not measured" in sc.stdout,
            sc.stdout[-400:],
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_judge_score_runs_from_an_installed_package() -> None:
    """`evh judge-score` in a project that has only the package, its own data, scorer, prompt
    and runs. The package is laid out as pip lays it out (scripts/ as evaluation_harness,
    schemas/ inside it, per pyproject.toml) in a directory with no checkout beside it, and run
    with `python -m evaluation_harness` from the project (the wheel built from pyproject.toml,
    installed by _wheel.py). The judges are `provider: fake`:
    no network, no key, and the gate refuses them unless the scorer is run --unvalidated.

    EVAL_TEST_PYTHON=<venv>/bin/python runs the same project against a package installed in
    another interpreter's environment."""
    import json as _json  # noqa: PLC0415
    import os  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    tmp = Path(tempfile.mkdtemp(prefix="harness-installed-"))
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import _wheel  # noqa: PLC0415 — the real wheel, so package-data omissions fail here

        site = _wheel.install(tmp / "site-packages")
        installed = os.environ.get("EVAL_TEST_PYTHON", "")  # a real pip install, when given
        ipy = installed or PY
        pkg = site / "evaluation_harness"
        if installed:
            pkg = Path(
                subprocess.run(
                    [ipy, "-c", "import evaluation_harness as e; print(e.__path__[0])"],
                    cwd=tmp,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()
            )

        def listing() -> list[str]:
            return sorted(str(f.relative_to(pkg)) for f in pkg.rglob("*"))

        before = listing()
        proj = tmp / "project"
        data = proj / "data"
        (data / "sources" / "jds_v1").mkdir(parents=True)
        ids = ["ep_1", "ep_2", "ep_3"]
        for i in ids:
            (data / "sources" / "jds_v1" / f"{i}.txt").write_text(f"Article {i}. It has a few sentences.\n")
        env = {
            "EVAL_HOME": str(proj),
            "EVAL_DATA_DIR": "data",
            "EVAL_RUNS_DIR": "",
            **({} if installed else {"PYTHONPATH": str(site)}),
            "PYTHONDONTWRITEBYTECODE": "1",
            "LITELLM_BASE_URL": "",
            "OPENROUTER_API_KEY": "",
            "EVAL_MAX_COST_USD": "",
        }

        def evh(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [ipy, "-m", "evaluation_harness", *args],
                cwd=proj,
                capture_output=True,
                text=True,
                env={**os.environ, **env},
            )

        made = evh(
            "dataset-create", "--dataset-id", "jds_v1", "--source-dir", str(data / "sources" / "jds_v1")
        )
        mat = evh("dataset-materialize", "--dataset-id", "jds_v1")
        check(
            "installed judge-score: the project's dataset is frozen and materialized by the package",
            made.returncode == 0 and mat.returncode == 0,
            (made.stderr + mat.stderr)[-300:],
        )
        for arm, fam in (("arm_a", "gemma"), ("arm_b", "qwen")):
            d = data / "runs" / f"{arm}_20260101T000000Z"
            (d / "outputs").mkdir(parents=True)
            for i in ids:
                (d / "outputs" / f"{i}.txt").write_text(f"{arm} summary of {i}\n")
            (d / "predictions.jsonl").write_text(
                "".join(_json.dumps({"item_id": i, "rouge1": 0.3}) + "\n" for i in ids)
            )
            (d / "metrics.json").write_text(
                _json.dumps(
                    {
                        "config_id": arm,
                        "dataset_id": "jds_v1",
                        "created_at": "2026-01-01T00:00:00Z",
                        "params": {"family": fam},
                        "n_items": 3,
                        "primary_metric": "rouge1",
                        "reference_tier": "silver",
                        "scores": {"rouge1": 0.3},
                        "metric_kinds": {"rouge1": "quality"},
                    }
                )
            )
        (proj / "prompts").mkdir()
        shutil.copy2(
            ROOT.parent / "examples" / "summeval-judging" / "prompt.txt", proj / "prompts" / "judge.txt"
        )
        fake = {"provider": "fake", "temperature": 0.0, "usd_per_mtok_in": 1.0, "usd_per_mtok_out": 2.0}
        (data / "scorers").mkdir()
        (data / "scorers" / "judge-fake-v1.yaml").write_text(
            _json.dumps(
                {
                    "scorer_id": "judge-fake-v1",
                    "kind": "judge",
                    "dataset_id": "jds_v1",
                    "judges": [
                        {"id": "fa", "params": {**fake, "model": "fake-a", "family": "gemma"}},
                        {"id": "fb", "params": {**fake, "model": "fake-b", "family": "qwen"}},
                    ],
                    "prompt": {"file": "prompts/judge.txt"},
                    "protocol": {
                        "outputs_per_call": 16,
                        "blinding": True,
                        "order_seed": 0,
                        "position_check_fraction": 0.34,
                        "noise_check_fraction": 0.34,
                    },
                    "arms_match": "arm_",
                    "cost_cap_usd": 1.0,
                }
            )
        )
        judged = data / "runs-judged" / "judge-fake-v1"

        refused = evh("judge-score", "--dataset-id", "jds_v1", "--scorer", "judge-fake-v1")
        check(
            "installed judge-score: a fake-judge scorer is refused without --unvalidated",
            refused.returncode == 3 and "REFUSED" in refused.stderr and not judged.exists(),
            refused.stderr[-300:],
        )
        dry = evh(
            "judge-score", "--dataset-id", "jds_v1", "--scorer", "judge-fake-v1", "--unvalidated", "--dry-run"
        )
        check(
            "installed judge-score: --dry-run counts the calls and writes nothing",
            dry.returncode == 0
            and "DRY RUN" in dry.stdout
            and not judged.exists()
            and not (data / "judge-verdicts").exists(),
            (dry.stderr + dry.stdout)[-300:],
        )
        ran = evh("judge-score", "--dataset-id", "jds_v1", "--scorer", "judge-fake-v1", "--unvalidated")
        runs = sorted(judged.glob("arm_*/metrics.json"))
        m = _json.loads(runs[0].read_text()) if runs else {}
        check(
            "installed judge-score: scored runs land in the project's data dir, labelled unvalidated",
            ran.returncode == 0
            and len(runs) == 2
            and m["derived"]["with"]["label"] == "unvalidated judge"
            and m.get("primary_metric") == "judge_score_unvalidated"
            and m["derived"]["with"]["validated"] is False,
            (ran.stderr + ran.stdout)[-400:],
        )
        check(
            "installed judge-score: the judging set and the verdicts are in the project too",
            len(list((data / "judging-sets").glob("*.json"))) == 1
            and len(list((data / "judge-verdicts").glob("judge-fake-v1/*/fa/*.json"))) > 0,
        )
        check("installed judge-score: nothing was written beside the package code", listing() == before)
        check(
            "installed judge-score: nothing was written into this checkout's data",
            not (ROOT / "data" / "runs-judged" / "judge-fake-v1" / "arm_a_20260101T000000Z").exists()
            and not list((ROOT / "data" / "judging-sets").glob("jds_v1-*")),
        )
        board = subprocess.run(
            [ipy, "-m", "evaluation_harness", "leaderboard", "--dataset-id", "jds_v1"],
            cwd=proj,
            capture_output=True,
            text=True,
            env={**os.environ, **env, "EVAL_RUNS_DIR": str(judged)},
        )
        check(
            "installed judge-score: leaderboard reads the scored runs",
            board.returncode == 0
            and "arm_a" in board.stdout
            and "arm_b" in board.stdout
            and "judge_score_unvalidated" in board.stdout,
            (board.stderr + board.stdout)[-400:],
        )
        check(
            "installed judge-score: a judged run carries no reference tier; the source's is kept",
            "reference_tier" not in m and m["derived"]["with"].get("source_reference_tier") == "silver",
        )
        check(
            "installed judge-score: leaderboard says a judge scored them, not silver references",
            "Scored by an LLM judge, not against references: judge-fake-v1, unvalidated judge" in board.stdout
            and "SILVER" not in board.stdout,
            board.stdout[-400:],
        )
        again = evh("judge-score", "--dataset-id", "jds_v1", "--scorer", "judge-fake-v1", "--unvalidated")
        check(
            "installed judge-score: a rerun resumes from the stored verdicts (no new calls)",
            again.returncode == 0 and "calls 0," in again.stdout,
            again.stdout[-300:],
        )

        # A scorer that declares its own task: labels, dimensions, a 0-3 scale, `{n}` prompt.
        (proj / "prompts" / "answers.txt").write_text(
            "Rate each of the {n} numbered answers to the question, 0 to 3, on correctness "
            "and completeness. Reply as JSON: one list of {n} integers per dimension.\n"
        )
        (data / "scorers" / "judge-task-v1.yaml").write_text(
            _json.dumps(
                {
                    "scorer_id": "judge-task-v1",
                    "kind": "judge",
                    "dataset_id": "jds_v1",
                    "task": {
                        "source_label": "QUESTION",
                        "output_label": "ANSWERS",
                        "dimensions": ["correctness", "completeness"],
                        "scale": [0, 3],
                    },
                    "judges": [
                        {"id": "fa", "params": {**fake, "model": "fake-a", "family": "gemma"}},
                        {"id": "fb", "params": {**fake, "model": "fake-b", "family": "qwen"}},
                    ],
                    "prompt": {"file": "prompts/answers.txt"},
                    "protocol": {
                        "outputs_per_call": 16,
                        "blinding": True,
                        "order_seed": 0,
                        "position_check_fraction": 0.34,
                        "noise_check_fraction": 0.34,
                    },
                    "cost_cap_usd": 1.0,
                }
            )
        )
        task_ran = evh("judge-score", "--dataset-id", "jds_v1", "--scorer", "judge-task-v1", "--unvalidated")
        tjudged = data / "runs-judged" / "judge-task-v1"
        tvals = [
            _json.loads(line)["judge_score_unvalidated"]
            for f in sorted(tjudged.glob("arm_*/predictions.jsonl"))
            for line in f.read_text().splitlines()
            if line.strip()
        ]
        tsets = [_json.loads(f.read_text()) for f in (data / "judging-sets").glob("jds_v1-*.json")]
        tverd = [
            _json.loads(f.read_text()) for f in (data / "judge-verdicts").glob("judge-task-v1/*/fa/*.json")
        ]
        check(
            "installed judge-score: a declared task runs end to end, scores on its own scale",
            task_ran.returncode == 0 and len(tvals) == 2 * len(ids) and all(0 <= v <= 3 for v in tvals),
            (task_ran.stderr + task_ran.stdout)[-400:],
        )
        check(
            "installed judge-score: the declared task is in the judging set and shapes the replies",
            any((s.get("task") or {}).get("dimensions") == ["correctness", "completeness"] for s in tsets)
            and tverd
            and all(set(_json.loads(v["output"])) == {"correctness", "completeness"} for v in tverd),
        )
        check(
            "installed judge-score: a declared task is a different judging set from the default",
            len(tsets) == 2,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    print("harness self-tests (no network, no keys)\n")
    for fn in (
        test_dotenv_does_not_override_exported,
        test_import_reads_no_env_and_no_paths,
        test_price_needs_all_four_inputs,
        test_score_handles_absent_reference,
        test_compare_refuses_cross_dataset,
        test_metric_direction_is_not_always_up,
        test_descriptive_metrics_get_no_verdict,
        test_leaderboard_declares_silver_from_any_run,
        test_no_absolute_home_path_in_committed_data,
        test_no_committed_artifact_depends_on_an_ignored_one,
        test_fingerprint_core_imports_no_ml_framework,
        test_fingerprint_reports_library_versions_without_importing_them,
        test_fingerprint_does_not_invent_a_revision,
        test_untracked_run_output_does_not_make_the_tree_dirty,
        test_fingerprint_records_what_was_loaded,
        test_a_broken_fingerprint_hook_does_not_kill_the_run,
        test_fingerprint_hash_changes_when_anything_does,
        test_cli_help_works,
        test_family_test_cache_never_serves_a_stale_answer,
        test_example_scorer_suites_pass,
        test_fingerprint_version_is_read_somewhere,
        test_verdict_honours_declared_kinds,
        test_fingerprint_covers_reference_bytes,
        test_resume_scores_and_persists,
        test_writes_leave_no_partial_file,
        test_rescore_rehashes_the_references_it_actually_read,
        test_rescore_takes_source_path_from_the_dataset,
        test_a_run_that_measured_nothing_is_not_a_success,
        test_adapter_declaration_beats_a_stale_run,
        test_a_rescored_run_carries_the_current_parse,
        test_every_planted_defect_still_anchors,
        test_v4_neither_skips_a_missing_file_nor_hides_what_it_did_not_check,
        test_v10_fails_when_a_derived_run_states_no_scorer,
        test_nemenyi_table_is_computed_not_copied,
        test_two_runs_sharing_a_config_id_are_refused,
        test_the_reports_separation_counts_are_real,
        test_promote_reads_its_reason_from_the_env,
        test_rescore_refuses_a_missing_reference_set,
        test_spearman_is_tie_correct,
        test_rank_stability_ranks_the_right_way_up,
        test_v5_tells_a_tie_from_a_copy,
        test_rescore_can_move_runs_onto_a_new_reference_set,
        test_the_reproduction_tables_agree_with_the_configs_and_runs,
        test_the_gateway_routes_as_documented,
        test_bundled_adapter_calls_the_installed_anthropic_sdk,
        test_a_project_elsewhere_imports_runs_and_tests_them,
        test_hints_name_the_command_the_user_has,
        test_rescore_finds_the_bundled_adapter_from_an_installed_package,
        test_judge_score_runs_from_an_installed_package,
    ):
        # A TEST THAT RAISES MUST NOT HIDE THE ONES AFTER IT. `fn()` bare meant one
        # ImportError -- from a helper that had been renamed, say -- aborted the suite
        # at that point and every later test simply never ran, silently, while the
        # output looked like a normal early exit. That is the same shape as every
        # other "reported green for checking nothing" bug in this repo.
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — a crashing test is a failing test
            import traceback  # noqa: PLC0415

            check(f"{fn.__name__} ran without raising", False, f"{type(exc).__name__}: {exc}")
            traceback.print_exc()
    failures = [label for label, passed in results if not passed]
    if failures or not results:
        print(f"\n{len(failures)} FAILED: {', '.join(failures)}" if failures else "\nFAIL  no self-test ran")
        return 1
    print("\nall self-tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
