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
    """A resumed run must SCORE its replayed items, and a crash must leave outputs.

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
        test_adapter_declaration_beats_a_stale_run,
        test_the_checks_can_actually_fail,
        test_promote_reads_its_reason_from_the_env,
        test_rescore_refuses_a_missing_reference_set,
        test_spearman_is_tie_correct,
        test_v5_tells_a_tie_from_a_copy,
    ):
        fn()
    if failures:
        print(f"\n{len(failures)} FAILED: {', '.join(failures)}")
        return 1
    print("\nall self-tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
