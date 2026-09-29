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
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
#: The harness root. HERE is scripts/, which is what the sys.path inserts below want — but
#: a data check written against HERE scans scripts/data/, which does not exist, so it finds
#: nothing and passes for the wrong reason. That is exactly how the first version of
#: test_no_absolute_home_path_in_committed_data shipped green while checking nothing.
ROOT = HERE.parent
ROOT = HERE.parent
PY = sys.executable
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {label}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(label)


def run(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run a harness script. `env` adds to the inherited environment, it does not
    replace it -- a test that needs EVAL_RUNS_DIR still needs PATH and HOME."""
    import os  # noqa: PLC0415

    e = {**os.environ, **(env or {})}
    return subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True, env=e)


def test_dotenv_does_not_override_exported() -> None:
    """An exported var must win, so a one-off override needs no file edit."""
    import os

    sys.path.insert(0, str(HERE))
    from _common import load_dotenv

    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as fh:
        fh.write("EVAL_SELFTEST_A=from_file\nEVAL_SELFTEST_B=from_file\n")
        path = Path(fh.name)
    os.environ["EVAL_SELFTEST_A"] = "from_shell"
    os.environ.pop("EVAL_SELFTEST_B", None)
    load_dotenv(path)
    check("dotenv: exported var wins", os.environ["EVAL_SELFTEST_A"] == "from_shell")
    check("dotenv: missing var is filled", os.environ.get("EVAL_SELFTEST_B") == "from_file")
    path.unlink()


def test_price_needs_all_four_inputs() -> None:
    sys.path.insert(0, str(HERE))
    from adapter import _price

    check("price: None when unpriced", _price({}, 1000, 1000) is None)
    check("price: None when tokens missing",
          _price({"usd_per_mtok_in": 3, "usd_per_mtok_out": 15}, None, 10) is None)
    got = _price({"usd_per_mtok_in": 3.0, "usd_per_mtok_out": 15.0}, 1_000_000, 1_000_000)
    check("price: 1M in + 1M out = in+out rate", got == 18.0, f"got {got}")


def test_score_handles_absent_reference() -> None:
    sys.path.insert(0, str(HERE))
    from adapter import score

    check("score: no reference -> no quality metric", "overlap_f1" not in score("a b c", None))
    check("score: identical output scores 1.0", score("a b c", "a b c")["overlap_f1"] == 1.0)
    check("score: disjoint output scores 0.0", score("a b", "c d")["overlap_f1"] == 0.0)


def test_compare_refuses_cross_dataset() -> None:
    r = run("scripts/compare_runs.py", "--baseline", "nope_a", "--candidate", "nope_b")
    check("compare: unknown run is an error", r.returncode != 0)


def test_cli_help_works() -> None:
    for script in ("dataset_create", "materialize", "experiment_run", "compare_runs",
                   "promote_baseline", "validate_tree", "list_runs", "reference_create",
                   "leaderboard", "sweep", "env_check", "holdout_significance",
                   "pair_test", "family_test", "classification_report", "bootstrap_test",
                   "rank_stability", "extraction_report", "retrieval_report", "rescore",
                   "check_terminology", "check_report_claims", "check_links",
                   "check_model_facts"):
        r = run(f"scripts/{script}.py", "--help")
        check(f"{script}.py --help", r.returncode == 0, r.stderr.strip()[:80])


def test_metric_direction_is_not_always_up() -> None:
    """Cost and latency improve by going DOWN.

    compare_runs.py judged every metric with `"better" if d > 0 else "worse"`, so a run
    that got faster or cheaper was reported as worse — while leaderboard.py, in the same
    harness, already knew these keys were lower-is-better. Two scripts disagreeing about
    what a number means is worse than either being wrong alone: whichever you read last
    is the one you believe.
    """
    sys.path.insert(0, str(HERE / "scripts"))
    from _common import verdict_for

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
    sys.path.insert(0, str(HERE / "scripts"))
    from _common import verdict_for

    check("descriptive: more words is 'changed'", verdict_for("output_words", 12) == "changed")
    check("descriptive: fewer words is 'changed'", verdict_for("output_words", -12) == "changed")


def test_leaderboard_declares_silver_from_any_run() -> None:
    """The SILVER caveat must survive a config whose FIRST run predates the reference.

    leaderboard.py read `runs[0].get("reference_tier")`. A config with an early unscored
    run therefore printed a silver-derived quality score with no disclaimer — a
    model-generated number shown as if it were ground truth, which is the single thing
    this table must never do.
    """
    rows = [
        {"reference_tier": None},
        {"reference_tier": "silver"},
    ]
    tiers = {r.get("reference_tier") for r in rows if r.get("reference_tier")}
    check("leaderboard: silver seen behind an unscored first run", "silver" in tiers)
    check(
        "leaderboard: no tier at all stays unlabelled",
        {r.get("reference_tier") for r in [{"reference_tier": None}] if r.get("reference_tier")}
        == set(),
    )


def test_no_absolute_home_path_in_committed_data() -> None:
    """A dataset describes a SELECTION, not the machine that built it.

    dataset_create.py wrote `args.source_dir.as_posix()` — the resolved, absolute path — so
    every dataset in this repo carried "/Users/<name>/projects/..." into git. That leaks
    whoever ran it, and makes a file that is meant to travel between machines describe one.
    Only `created_at` and `source_dir` differ after the fix; every source_sha256 is
    unchanged, which is what actually freezes a dataset.
    """
    import re

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
            cwd=ROOT, capture_output=True, text=True, timeout=30, check=True,
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
    import subprocess

    baselines = sorted((ROOT / "data" / "baselines").glob("*.json"))
    check("consistency: a baseline ships", bool(baselines), "none found")
    for b in baselines:
        promoted_from = json.loads(b.read_text()).get("promoted_from")
        if not promoted_from:
            continue
        run_dir = ROOT / "data" / "runs" / promoted_from
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(run_dir / "metrics.json")],
            cwd=ROOT, capture_output=True,
        ).returncode == 0
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
        ["git", "ls-files", "data/references"], cwd=ROOT, capture_output=True, text=True,
    ).stdout.split()
    tracked_ref_ids = {pathlib.Path(f).parent.name for f in tracked_refs}
    needs_fetch = set()
    for mj in sorted((ROOT / "data" / "runs").glob("*/metrics.json")):
        rid = ((json.loads(mj.read_text()).get("fingerprint") or {}).get("data")
               or {}).get("reference_id")
        if rid and pathlib.Path(rid).name not in tracked_ref_ids:
            needs_fetch.add(pathlib.Path(rid).name)
    print(f"  --   consistency: {len(needs_fetch)} reference set(s) are ignored by "
          f"design and must be re-fetched before rescore: "
          f"{', '.join(sorted(needs_fetch)) or 'none'}")


def test_fingerprint_core_imports_no_ml_framework() -> None:
    """The core must stay usable by someone who never installs an ML framework.

    The whole reason the model half is a hook rather than an inspection: an LLM-only eval,
    or a regex baseline, should not pull in torch. This asserts the module text itself
    never imports one — a runtime check would pass simply because the framework is absent.
    """
    import ast

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
    sys.path.insert(0, str(HERE))
    from _fingerprint import _installed_versions

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
    sys.path.insert(0, str(HERE))
    from _fingerprint import _model_identity

    no_rev = _model_identity(lambda _p: {"id": "some-local-blob"}, {})
    check("fingerprint: absent revision stays None", no_rev["revision"] is None)
    check("fingerprint: absent revision is labelled", no_rev["revision_source"] == "unavailable")
    none_hook = _model_identity(None, {})
    check("fingerprint: no hook -> identity_declared False",
          none_hook == {"identity_declared": False})


def test_a_broken_fingerprint_hook_does_not_kill_the_run() -> None:
    """Fingerprinting describes a run; it is not a precondition for one."""
    sys.path.insert(0, str(HERE))
    from _fingerprint import _model_identity

    def boom(_params):
        raise RuntimeError("no model here")

    got = _model_identity(boom, {})
    check("fingerprint: broken hook is caught", got["identity_declared"] is False)

    # ── retries ──────────────────────────────────────────────────────────────
    # Guarded here because the absence of these was invisible: EVAL_MAX_RETRIES was
    # honoured by one adapter and not by the one doing the work, and two sweeps each
    # lost a whole arm to one upstream 429 before anybody noticed.
    from _retry import call_with_retries, is_transient  # noqa: PLC0415

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

    check("retry: adapter marker honoured",
          is_transient(RuntimeError("model is warming up"), extra=("model is warming up",)))
    check("retry: unknown error is not transient", not is_transient(ValueError("banana")))
    check("fingerprint: broken hook records why", "no model here" in got.get("error", ""))


def test_fingerprint_hash_changes_when_anything_does() -> None:
    """The hash is the one-glance answer to "did anything else move?"."""
    sys.path.insert(0, str(HERE))
    from _fingerprint import build_fingerprint, differing_paths

    ds = {"dataset_id": "d1", "items": [{"item_id": "i1", "source_sha256": "aaa"}]}
    kw = dict(root=HERE.parent, dataset=ds, reference_id=None, reference_tier=None,
              config_id="c1", adapter_id="scripts/adapter.py",
              adapter_path=HERE / "adapter.py", model_hook=None)
    base = build_fingerprint(params={"sentences": 1}, **kw)
    same = build_fingerprint(params={"sentences": 1}, **kw)
    moved = build_fingerprint(params={"sentences": 2}, **kw)
    check("fingerprint: stable across identical inputs", base["hash"] == same["hash"])
    check("fingerprint: changes when a param moves", base["hash"] != moved["hash"])
    check("fingerprint: names the field that moved",
          differing_paths(base, moved) == ["arm.params.sentences"],
          f"got {differing_paths(base, moved)}")
    # Different DATA must move it too — dataset_id is a name, the item hashes are identity.
    other = build_fingerprint(params={"sentences": 1},
                              **{**kw, "dataset": {"dataset_id": "d1",
                                                   "items": [{"item_id": "i1",
                                                              "source_sha256": "bbb"}]}})
    check("fingerprint: same dataset_id, different bytes -> different hash",
          base["hash"] != other["hash"])


def test_example_scorer_suites_pass() -> None:
    """RUN the example scorer suites, do not just --help them.

    They were briefly in the CLI --help list, which proved nothing: neither uses argparse,
    so both exited 0 by ignoring the flag. A test that passes for a reason unrelated to
    what it checks is worse than no test, because it reports green.

    Skipped rather than failed when the example venv is absent -- these import torch-free
    scorer modules, but the runner has to be a Python that can see them, and the harness's
    own interpreter may not be.
    """
    for script, subject in (("test_extraction_scorer.py", "set scorer"),
                            ("test_ner_parser.py", "NER JSON parser"),
                            ("test_retrieval_scorer.py", "ranked-list scorer"),
                            ("test_code_hashes.py", "scoring-code hashes"),
                            ("check_report_claims.py", "report claims vs committed runs"),
                            ("check_links.py", "markdown links and anchors"),
                            ("check_model_facts.py", "model facts vs the evidence capture")):
        path = HERE / script
        if not path.is_file():
            continue
        r = run(f"scripts/{script}")
        if r.returncode != 0 and "ModuleNotFoundError" in (r.stderr or ""):
            print(f"  --   {subject}: skipped (example deps not on this interpreter)")
            continue
        check(f"{subject}: all assertions pass", r.returncode == 0,
              (r.stdout or r.stderr or "").strip()[-160:])


def test_fingerprint_version_is_read_somewhere() -> None:
    """A version field nothing reads is decoration.

    v2 added `data.references_sha256`, so a v1 and a v2 hash are not comparable even
    when everything v1 covers is identical. `compare_runs` must say so rather than
    reporting a bare hash mismatch and sending a reader hunting for a change that is
    not there.
    """
    src = (HERE / "compare_runs.py").read_text()
    check("compare_runs notices a fingerprint version mismatch",
          'fa.get("version") != fb.get("version")' in src)
    from _fingerprint import build_fingerprint  # noqa: PLC0415
    fp = build_fingerprint(root=HERE.parent, dataset={"dataset_id": "d", "items": []},
                           reference_id=None, reference_tier=None, config_id="c",
                           params={}, adapter_id="a", adapter_path=None)
    check("new fingerprints are version 2", fp.get("version") == 2, str(fp.get("version")))


def test_verdict_honours_declared_kinds() -> None:
    """An adapter's own metric must not be judged better/worse by the sign of a delta.

    `verdict_for` consulted only the built-in table, which knows the bundled adapter's
    metrics and nothing else -- so every EXAMPLE metric got a better/worse verdict from
    its sign. `llm_named_unknown` counts hallucinated document ids, and more of them
    was reported as an improvement.
    """
    sys.path.insert(0, str(HERE))
    from _common import verdict_for  # noqa: PLC0415

    check("verdict: unknown metric, no kinds -> judged by sign (the old behaviour)",
          verdict_for("llm_named_unknown", +1.0) == "better")
    check("verdict: declared descriptive -> 'changed', not 'better'",
          verdict_for("llm_named_unknown", +1.0,
                      kinds={"llm_named_unknown": "descriptive"}) == "changed")
    check("verdict: declared quality still gets a direction",
          verdict_for("ndcg_10", +1.0, kinds={"ndcg_10": "quality"}) == "better")
    check("verdict: a declaration cannot flip cost's direction",
          verdict_for("cost_usd", +1.0, kinds={"cost_usd": "cost"}) == "worse")


def test_fingerprint_covers_reference_bytes() -> None:
    """Editing a reference must change the fingerprint. It did not, for five examples.

    `reference_id` is a NAME. The data block hashed the source items but identified the
    references only by name, so a changed gold file produced different scores under an
    identical hash -- and `compare_runs` reported "reference identical" while comparing
    two different measurements.
    """
    import shutil, tempfile  # noqa: PLC0415
    sys.path.insert(0, str(HERE))
    from _fingerprint import build_fingerprint  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        refs = root / "data" / "references" / "gold" / "t1"
        refs.mkdir(parents=True)
        (refs / "i1.txt").write_text("alpha", encoding="utf-8")
        ds = {"dataset_id": "t1", "items": [{"item_id": "i1", "source_sha256": "aa"}]}
        kw = dict(root=root, dataset=ds, reference_id="gold/t1", reference_tier="gold",
                  config_id="c", params={}, adapter_id="a", adapter_path=None)
        before = build_fingerprint(**kw)
        (refs / "i1.txt").write_text("beta", encoding="utf-8")
        after = build_fingerprint(**kw)
        check("fingerprint: editing a reference changes the hash",
              before["hash"] != after["hash"])
        check("fingerprint: references_sha256 is what moved",
              before["data"]["references_sha256"] != after["data"]["references_sha256"])
        check("fingerprint: no references -> None, not a hash of nothing",
              build_fingerprint(**{**kw, "reference_id": None})
              ["data"]["references_sha256"] is None)


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
        check("resume: outputs are written DURING the pass, not after it",
              t_out[-1] <= mj.stat().st_mtime and t_out[0] <= t_out[-1],
              f"last output {t_out[-1]:.3f}, metrics {mj.stat().st_mtime:.3f}")

    # Simulate a crash: drop all but one output, as if the pass died at item 2.
    for f in outs[1:]:
        f.unlink()
    r2 = run("scripts/experiment_run.py", "--config", "data/configs/arm_b.yaml",
             "--resume", src, env=env)
    check("resume: the resumed pass exits 0", r2.returncode == 0,
          (r2.stderr or "")[-160:])
    newest = max((p for p in runs.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
    rows = [l for l in (newest / "predictions.jsonl").read_text().splitlines() if l.strip()]
    check("resume: every item is SCORED, not skipped", len(rows) == len(outs),
          f"{len(rows)} rows for {len(outs)} items")
    check("resume: replayed items are flagged",
          any('"resumed": 1' in l or '"resumed":1' in l for l in rows))

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
    replayed = [_json.loads(l) for l in rows
                if _json.loads(l).get("resumed") == 1.0]
    check("resume: at least one item was actually replayed", bool(replayed),
          f"{len(replayed)} replayed of {len(rows)}")
    if replayed:
        r = replayed[0]
        o = src_rows.get(r["item_id"], {})
        # Only assert on fields the original row actually had; the demo arm is free and
        # local, so cost and tokens may legitimately be absent from BOTH.
        carried = [k for k in ("cost_usd", "latency_ms", "tokens_in", "tokens_out")
                   if o.get(k) is not None]
        check("resume: a replayed item keeps the measurements from its original pass",
              all(r.get(k) == o.get(k) for k in carried) if carried else True,
              f"carried={carried} orig={[o.get(k) for k in carried]} "
              f"now={[r.get(k) for k in carried]}")
        if o.get("_meta"):
            check("resume: and keeps its _meta",
                  isinstance(r.get("_meta"), dict)
                  and all(r["_meta"].get(k) == v for k, v in o["_meta"].items()),
                  f"orig keys {sorted(o['_meta'])} now {sorted((r.get('_meta') or {}))}")

    # RESUMING FROM ANOTHER ARM MUST BE REFUSED. `--resume` took a run id and read its
    # outputs; nothing compared the arms, so one mistyped id replayed a different
    # model's answers and recorded them under this one, with a valid fingerprint.
    other = run("scripts/experiment_run.py", "--config", "data/configs/arm_a.yaml",
                "--resume", src, env=env)
    msg = (other.stderr or "") + (other.stdout or "")
    check("resume: another arm's outputs are refused",
          other.returncode != 0 and "another arm" in msg.lower(), msg[-200:])
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

    sys.path.insert(0, str(HERE))
    from _common import write_text_atomic  # noqa: PLC0415

    with _tf.TemporaryDirectory() as td:
        target = pathlib.Path(td) / "out.txt"
        target.write_text("the original, complete content")

        # WINDOW 1: death DURING the write. A lone surrogate cannot be encoded to
        # utf-8, so the write raises partway -- the same shape as running out of disk.
        try:
            write_text_atomic(target, "good start \ud800 bad")
        except Exception:  # noqa: BLE001 — what survives is the point, not what raised
            pass
        check("atomic write: a write that dies partway leaves the original intact",
              target.read_text() == "the original, complete content",
              f"file now: {target.read_text()[:60]!r}")

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
        check("atomic write: a death before the rename leaves the original intact",
              target.read_text() == "the original, complete content",
              f"file now: {target.read_text()[:60]!r}")

        leftovers = [f.name for f in pathlib.Path(td).iterdir() if f.name != "out.txt"]
        check("atomic write: and leaves no temp file behind", not leftovers,
              str(leftovers))

        write_text_atomic(target, "the new content")
        check("atomic write: a successful write still replaces the file",
              target.read_text() == "the new content", target.read_text()[:60])

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
        check("atomic write: and the plain write_text it replaces DOES lose the file",
              naive.read_text() != "the original, complete content",
              f"write_text somehow preserved it: {naive.read_text()[:40]!r}")


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
    j["fingerprint"]["data"]["references_sha256"] = "0" * 64      # cannot match
    (dst / "metrics.json").write_text(_json.dumps(j))

    env = {"EVAL_RUNS_DIR": str(runs.relative_to(HERE.parent))}
    out = runs / "out"
    r = run("scripts/rescore.py", "--dataset-id", str(j.get("dataset_id")),
            "--out", str(out.relative_to(HERE.parent)), env=env)
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
        check("rescore: references_sha256 is recomputed, not copied",
              data.get("references_sha256") not in (None, "0" * 64),
              f"got {str(data.get('references_sha256'))[:24]}")
        check("rescore: and a changed gold set is flagged, not silently overwritten",
              data.get("references_changed_since_measurement") is True
              and data.get("references_sha256_at_measurement") == "0" * 64,
              f"keys present: {sorted(k for k in data if 'reference' in k)}")
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
        print("  --   rescore/source_path: skipped (corpus not fetched on this machine)")
        return

    tmp = HERE.parent / "data" / "runs-selftest-srcpath"
    shutil.rmtree(tmp, ignore_errors=True)
    dst = tmp / src.name
    dst.mkdir(parents=True)
    for n in ("metrics.json", "predictions.jsonl"):
        shutil.copy2(src / n, dst / n)
    shutil.copytree(src / "outputs", dst / "outputs")

    env = {"EVAL_RUNS_DIR": str(tmp.relative_to(HERE.parent))}
    base = run("scripts/rescore.py", "--dataset-id", "cnn_dailymail_200",
               "--out", str((tmp / "out-base").relative_to(HERE.parent)), env=env)
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
            lines = [l for l in err.splitlines() if l.strip()]
            detail = next((l for l in lines if l.startswith(("ERROR", "Traceback"))
                           or "Error" in l), lines[-1] if lines else "no output")
            check("rescore: a committed run can be rescored at all", False, detail[:200])
        shutil.rmtree(tmp, ignore_errors=True)
        return

    # Swap two items' source_path. The files still exist; each item now points at the
    # other's text, so any scorer that reads the source must produce different numbers.
    ds = _json.loads(ds_file.read_text())
    items = [i for i in ds.get("items", []) if i.get("source_path")]
    original = ds_file.read_text()
    try:
        items[0]["source_path"], items[1]["source_path"] = (
            items[1]["source_path"], items[0]["source_path"])
        ds_file.write_text(_json.dumps(ds))
        swapped = run("scripts/rescore.py", "--dataset-id", "cnn_dailymail_200",
                      "--out", str((tmp / "out-swap").relative_to(HERE.parent)), env=env)
    finally:
        ds_file.write_text(original)

    def scores(where):
        f = where / src.name / "metrics.json"
        return _json.loads(f.read_text())["scores"] if f.is_file() else None

    a, b = scores(tmp / "out-base"), scores(tmp / "out-swap")
    if a is None or b is None:
        print("  --   rescore/source_path: skipped (rescore produced no metrics)")
    else:
        check("rescore: the dataset's source_path is what selects the source text",
              a != b, "swapping two items' source_path changed nothing — the dataset's "
                      "source_path is being ignored")
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
    if r2.returncode != 0:
        why = ((r2.stdout or "") + (r2.stderr or "")).strip().splitlines()
        print(f"  --   cost cap: skipped (the demo arm cannot run here: "
              f"{why[-1][:70] if why else 'no output'})")
        shutil.rmtree(runs, ignore_errors=True)
        return
    check("cost cap: an uncapped run of the same arm still exits 0", True)
    shutil.rmtree(runs, ignore_errors=True)

    r = run("scripts/experiment_run.py", "--config", "data/configs/arm_b.yaml",
            env={**env, "EVAL_MAX_COST_USD": "0"})
    out = (r.stdout or "") + (r.stderr or "")
    check("cost cap: a run that scored NO items exits non-zero",
          r.returncode != 0, f"exit {r.returncode}")
    check("cost cap: and says nothing was measured",
          "scored NO items" in out or "Nothing was measured" in out, out[-160:])

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
    m.setdefault("metric_kinds", {})["llm_named_unknown"] = "quality"   # the stale state
    (dst / "metrics.json").write_text(_json.dumps(m))

    env = {"EVAL_RUNS_DIR": str(runs.relative_to(HERE.parent))}
    r = run("scripts/leaderboard.py", "--dataset-id", str(m.get("dataset_id")), env=env)
    # The COLUMN header, not the "ranked by: ndcg_10" caption above it -- both contain
    # the metric name, and matching the caption made this fail for the wrong reason.
    header = next((ln for ln in (r.stdout or "").splitlines()
                   if "ndcg_10" in ln and ln.split()[:1] == ["arm"]), "")
    cols = header.split()
    ok = ("llm_named_unknown" in cols and "recall_100" in cols
          and cols.index("llm_named_unknown") > cols.index("recall_100"))
    check("metric kinds: the adapter's 'descriptive' overrides a run's stale 'quality'",
          ok, f"columns: {cols[:14]}")
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

    reparsed = HERE.parent / "data" / "runs-reparsed"
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
        r = run("scripts/family_test.py", "--dataset-id", "scifact_200",
                "--a", "sf_glm_s_n200_v1", "--against", "_n200_v1",
                "--metric", "ndcg_10", env={"EVAL_RUNS_DIR": str(scope)})

    m = _re.search(r"separated from (\d+) of (\d+) opponents", r.stdout or "")
    if not m:
        check("separation counts: family_test produced a verdict", False,
              ((r.stderr or "") + (r.stdout or ""))[-160:])
        return
    sep, fam = int(m.group(1)), int(m.group(2))
    report = (HERE.parents[1] / "research" / "REPORT_RETRIEVAL.md").read_text()
    check(f"REPORT_RETRIEVAL states the {sep} of {fam} that family_test computes",
          f"**{sep} of {fam}**" in report,
          f"the tool says {sep} of {fam}; the report does not state that")
    check(f"...and the tie group it implies, {fam - sep} of {fam}",
          f"**{fam - sep} of {fam}**" in report,
          f"tie group should read {fam - sep} of {fam}")


def test_the_checks_can_actually_fail() -> None:
    """Every `make ci` checker must EXIT NON-ZERO on the thing it exists to catch.

    Round 1 found `check_terminology.py` reporting green while reading zero files. I
    fixed that one file and never asked whether its siblings had the same hole. Round 2
    found two more, and they had been green through real breakage the whole time:

      check_links.py            printed the broken link and exited 0
      check_report_claims.py    printed "0/0 claims verified" and exited 0 with no runs

    So the round-1 lesson was learned as an instance when it was a class. This test is
    the class: each checker is pointed at a tree that must make it fail, and the
    assertion is on the EXIT CODE, because that is the only part `make` reads.

    Each checker resolves its own root from `__file__`, so copying `scripts/` into a
    throwaway tree is enough to aim it somewhere harmless.
    """
    import shutil  # noqa: PLC0415
    import tempfile as _tf  # noqa: PLC0415

    with _tf.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        fake = tmp / "repo" / "harness"
        (fake / "data" / "runs").mkdir(parents=True)
        (fake / "data" / "runs-rescored").mkdir(parents=True)
        shutil.copytree(HERE, fake / "scripts")

        def run_there(script: str) -> subprocess.CompletedProcess:
            return subprocess.run([PY, str(fake / "scripts" / script)],
                                  cwd=fake, capture_output=True, text=True)

        # check_report_claims: no runs at all. Every claim skips.
        r = run_there("check_report_claims.py")
        check("checks can fail: check_report_claims with no runs exits non-zero",
              r.returncode != 0, f"exit {r.returncode}: {(r.stdout or '')[-120:]}")

        # check_links: one markdown file with a link to nothing.
        (tmp / "repo" / "BROKEN.md").write_text("[x](./does_not_exist_xyz.md)\n")
        r = run_there("check_links.py")
        check("checks can fail: check_links with a broken link exits non-zero",
              r.returncode != 0, f"exit {r.returncode}: {(r.stdout or '')[-120:]}")

        # check_terminology: the round-1 hole, re-asserted here so it cannot regress.
        (tmp / "repo" / "BROKEN.md").unlink()
        r = run_there("check_terminology.py")
        check("checks can fail: check_terminology with no markdown exits non-zero",
              r.returncode != 0, f"exit {r.returncode}: {(r.stdout or '')[-120:]}")


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
    r = run("scripts/promote_baseline.py", "--reason-from-env", "--run", "nope",
            env={"EVAL_PROMOTE_REASON": ""})
    out = (r.stderr or "") + (r.stdout or "")
    check("promote: an empty EVAL_PROMOTE_REASON is refused, not crashed",
          r.returncode != 0 and "NameError" not in out, out[-160:])
    # NOT just `"reason" in out`: the NameError traceback echoes the offending source
    # line, which contains the word "reason", so that assertion passed against the
    # broken code. It has to be the ERROR MESSAGE, and no traceback.
    check("promote: and it says a reason is required",
          "a reason is required" in out and "Traceback" not in out, out[-160:])

    r = run("scripts/promote_baseline.py", "--reason-from-env", "--run",
            "_no_such_run_selftest_", env={"EVAL_PROMOTE_REASON": "a reason"})
    out = (r.stderr or "") + (r.stdout or "")
    check("promote: with the env reason set it gets PAST the env read to the run lookup",
          "NameError" not in out and "no run" in out.lower(), out[-160:])


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
    r = run("scripts/rescore.py", "--dataset-id", str(m.get("dataset_id")),
            "--out", str(runs / "out"), env=env)
    check("rescore: a declared-but-absent reference set is refused, not scored",
          r.returncode != 0, f"exit {r.returncode}")
    check("rescore: and it says the references are what is missing",
          "reference" in ((r.stderr or "") + (r.stdout or "")).lower(),
          ((r.stderr or "") + (r.stdout or ""))[-160:])
    check("rescore: it writes no partial rescored run",
          not (runs / "out" / src.name / "metrics.json").is_file())
    shutil.rmtree(runs, ignore_errors=True)


def test_spearman_is_tie_correct() -> None:
    """rho must equal the textbook shortcut WITHOUT ties, and differ WITH them.

    Both directions, because widening a formula until it stops disagreeing is how a
    correct-looking wrong answer gets in. The shortcut
    `1 - 6*sum(d^2)/(n(n^2-1))` is an algebraic identity for Pearson-on-ranks that holds
    only when every rank is distinct; the repo shipped it against tied data for four
    examples, where it did not approximate rho but computed a different quantity.
    """
    sys.path.insert(0, str(HERE))
    from rank_stability import ranks_on, spearman  # noqa: PLC0415

    def shortcut(x, y):
        n = len(x)
        return 1 - 6 * sum((x[i] - y[i]) ** 2 for i in range(n)) / (n * (n * n - 1))

    a = [1, 2, 3, 4, 5]
    b = [2, 1, 4, 3, 5]
    check("spearman: no ties -> agrees with the textbook shortcut",
          abs(spearman(a, b) - shortcut(a, b)) < 1e-12,
          f"{spearman(a, b)} vs {shortcut(a, b)}")
    check("spearman: identical orderings -> 1.0", abs(spearman(a, a) - 1.0) < 1e-12)
    check("spearman: reversed -> -1.0",
          abs(spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) + 1.0) < 1e-12)

    # Midranks: three arms tied for first share rank 2.0, the fourth gets 4.0.
    M = {"a": {"i": 1.0}, "b": {"i": 1.0}, "c": {"i": 1.0}, "d": {"i": 0.0}}
    r = ranks_on(M, ["a", "b", "c", "d"], ["i"])
    check("ranks_on: tied arms share the average rank, not the alphabet",
          r["a"] == r["b"] == r["c"] == 2.0 and r["d"] == 4.0, str(r))

    tied = [2.0, 2.0, 2.0, 4.0]
    check("spearman: a half where EVERY arm ties -> NaN, not 0.0",
          spearman([1.0, 1.0, 1.0, 1.0], tied) != spearman([1.0, 1.0, 1.0, 1.0], tied))
    check("spearman: with ties it DIFFERS from the shortcut",
          abs(spearman(tied, [1.0, 2.0, 3.0, 4.0])
              - shortcut(tied, [1.0, 2.0, 3.0, 4.0])) > 1e-9)


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
    import os
    import shutil

    scores = {"correct": 0.86, "parsed": 1.0}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        def make(name: str, model: str, correct_items: list) -> None:
            d = root / name
            d.mkdir()
            (d / "metrics.json").write_text(json.dumps({
                "config_id": name, "dataset_id": "ds_v1", "scores": scores,
                "params": {"model": model}, "build": {"ref": "test"},
            }))
            (d / "predictions.jsonl").write_text("\n".join(
                json.dumps({"item_id": f"i{i}", "correct": float(c)})
                for i, c in enumerate(correct_items)))

        # Same mean (2 of 4), DIFFERENT items right. Two measurements.
        make("arm_a", "model-a", [1, 1, 0, 0])
        make("arm_b", "model-b", [0, 0, 1, 1])
        env = {**os.environ, "EVAL_RUNS_DIR": str(root)}
        r = subprocess.run([PY, "scripts/validate_tree.py"], cwd=ROOT, env=env,
                           capture_output=True, text=True)
        check("V5: same mean, different items -> not flagged",
              "V5 no two configs" not in r.stdout or "FAIL V5" not in r.stdout,
              r.stdout[-200:])

        # A real copy: same mean AND the same items right, under different params.
        shutil.rmtree(root / "arm_b")
        make("arm_b", "model-b", [1, 1, 0, 0])
        r = subprocess.run([PY, "scripts/validate_tree.py"], cwd=ROOT, env=env,
                           capture_output=True, text=True)
        check("V5: same mean, same items, different params -> flagged",
              "FAIL V5" in r.stdout, r.stdout[-200:])


def main() -> int:
    print("harness self-tests (no network, no keys)\n")
    for fn in (
        test_dotenv_does_not_override_exported,
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
        test_a_broken_fingerprint_hook_does_not_kill_the_run,
        test_fingerprint_hash_changes_when_anything_does,
        test_cli_help_works,
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
        test_the_reports_separation_counts_are_real,
        test_the_checks_can_actually_fail,
        test_promote_reads_its_reason_from_the_env,
        test_rescore_refuses_a_missing_reference_set,
        test_spearman_is_tie_correct,
        test_v5_tells_a_tie_from_a_copy,
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

            check(f"{fn.__name__} ran without raising", False,
                  f"{type(exc).__name__}: {exc}")
            traceback.print_exc()
    if failures:
        print(f"\n{len(failures)} FAILED: {', '.join(failures)}")
        return 1
    print("\nall self-tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
