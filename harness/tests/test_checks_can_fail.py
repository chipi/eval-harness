#!/usr/bin/env python3
"""The checks can fail: every checker goes red, by name, on the defects it exists to catch.

    make guard-check

Twice a checker was found passing everything it was pointed at, so each kind of claim has a
planted defect here. All of a checker's defects are planted at once, in one private copy of
the repository, and the checker runs once: its output must name every defect, so one plant
cannot hide another. The real tree is never written to.

CI runs this only when a checker or the code it reads changes (.github/workflows/guards.yml);
`make ci` does not, because the checkers' code is what this proves, not the reports.
"""

from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
REPO = HARNESS.parent
sys.path.insert(0, str(HARNESS))  # the evaluation_harness package
from evaluation_harness._check import check, summary  # noqa: E402

#: (checker, the defect, file, anchor, what it becomes, what the checker's output must say)
#: An anchor that no longer matches exactly once is a failure, not a skip.
PLANTS = [
    # A TABLE ROW: prose has its own family below.
    (
        "tools/check_report_claims.py",
        "a wrong number in a leaderboard row",
        "research/REPORT_NER.md",
        "| **span_marker** | 0.7674 | 0.8370 |",
        "| **span_marker** | 0.9999 | 0.8370 |",
        "span_marker shows 0.9999",
    ),
    (
        "tools/check_report_claims.py",
        "a wrong COST in a table cell",
        "research/REPORT_RETRIEVAL.md",
        "| 0.7364 | 1.2 s | $0.1421 |",
        "| 0.7364 | 1.2 s | $0.5000 |",
        "glm_s shows $0.5000",
    ),
    # A NEAR miss (1.7%): the band between "equals the bill" and "2% off" used to be silent.
    (
        "tools/check_report_claims.py",
        "a cost cell 1.7% off the bill",
        "research/REPORT_RETRIEVAL.md",
        "| 0.7325 | 1.2 s | $0.4576 |",
        "| 0.7325 | 1.2 s | $0.4654 |",
        "glm_m shows $0.4654",
    ),
    (
        "tools/check_report_claims.py",
        "a wrong number in a CODE BLOCK",
        "research/REPORT_CLASSIFICATION.md",
        "bert_mini ◆          0.9450",
        "bert_mini ◆          0.9999",
        "bert_mini shows 0.9999",
    ),
    (
        "tools/check_report_claims.py",
        "a wrong CHEAPNESS RATIO",
        "research/REPORT_SYNTHESIS.md",
        "| $0.012 | **115× cheaper** |",
        "| $0.012 | **250× cheaper** |",
        "the report says 250×",
    ),
    (
        "tools/check_report_claims.py",
        "a wrong TIE GROUP size",
        "research/REPORT_SYNTHESIS.md",
        "| Summarisation · CNN/DM | 15 arms (13 paid)",
        "| Summarisation · CNN/DM | 14 arms (12 paid)",
        "the row says 14 (12 paid)",
    ),
    (
        "tools/check_report_claims.py",
        "a wrong PARETO count",
        "research/REPORT_SUMMARIZATION.md",
        "| **8 of 24** | three arms' quality",
        "| **5 of 24** | three arms' quality",
        "the report says 5 of 24",
    ),
    (
        "tools/check_report_claims.py",
        "a wrong figure in PROSE",
        "research/REPORT_NER.md",
        "`span_marker` scored **0.7674**",
        "`span_marker` scored **0.9999**",
        "span_marker reads 0.9999",
    ),
    (
        "tools/check_report_claims.py",
        "a wrong CROSS-MACHINE ratio",
        "research/REPORT_SUMMARIZATION.md",
        "ran `bart_l` itself 1.7× faster",
        "ran `bart_l` itself 2.7× faster",
        "FAIL cross-machine: REPORT_SUMMARIZATION.md says the Linux box ran bart_l",
    ),
    # On a WRAPPED continuation line on purpose: the check once scoped to the citing line.
    (
        "tools/check_report_claims.py",
        "a wrong RE-TIMED LATENCY in prose",
        "research/REPORT_SUMMARIZATION.md",
        "and `bart_s` (460 MB, 0.3276) **3.4 s**",
        "and `bart_s` (460 MB, 0.3276) **1.1 s**",
        "FAIL re-timed latency: REPORT_SUMMARIZATION.md states 3.4 s for cnn_bart_s_n200_v1",
    ),
    (
        "tools/check_report_claims.py",
        "a falsified CONVERSION-PR result",
        "docs/evidence/conversion_pr_check.json",
        (
            '"recorded_run": "ag_bert_base_ta_n200_v1_20260930T094555Z",\n      "loaded_dtype": null,\n'
            '      "byte_identical": 200,'
        ),
        (
            '"recorded_run": "ag_bert_base_ta_n200_v1_20260930T094555Z",\n      "loaded_dtype": null,\n'
            '      "byte_identical": 150,'
        ),
        "ag_bert_base_ta_n200_v1: 150/200",
    ),
    (
        "tools/check_model_facts.py",
        "a licence the evidence contradicts",
        "docs/REFERENCE.md",
        "[`facebook/bart-large-cnn`](https://huggingface.co/facebook/bart-large-cnn) | MIT |",
        "[`facebook/bart-large-cnn`](https://huggingface.co/facebook/bart-large-cnn) | GPL-3.0 |",
        "REFERENCE.md says GPL-3.0",
    ),
    (
        "tools/check_model_facts.py",
        "an OPEN-WEIGHT count the licence table contradicts",
        "research/REPORT_SYNTHESIS.md",
        "**14 of the 24** — DeepSeek",
        "**13 of the 24** — DeepSeek",
        "the synthesis says 13 (open)",
    ),
    (
        "tools/check_links.py",
        "a link to a file that does not exist",
        "research/internal/KNOWN_ISSUES.md",
        "# Known issues — read before reviewing",
        "# Known issues — read before reviewing\n\n[x](./_no_such_file_.md)",
        "_no_such_file_.md",
    ),
    (
        "tools/check_terminology.py",
        "a non-canonical experiment label",
        "docs/REFERENCE.md",
        "| Retrieval · SciFact |",
        "| Retrieval on SciFact |",
        "Retrieval on SciFact",
    ),
    # V10 guards CODE: each plant changes a constant code_digest covers, in the NER parser, the
    # extraction scorer and the retrieval parser. Their messages are checked below.
    (
        "scripts/validate_tree.py",
        "a NER PARSER change the rescored runs predate",
        "examples/ner-few-nerd/adapter.py",
        '_BARE_KEY = re.compile(r"([{,]\\s*)',
        '_BARE_KEY = re.compile(r"(?:ZZ)?([{,]\\s*)',
        None,
    ),
    (
        "scripts/validate_tree.py",
        "a SCORER CHANGE the rescored runs predate",
        "examples/_shared/extraction.py",
        '_ARTICLES = ("the ", "a ", "an ")',
        '_ARTICLES = ("z ", "the ", "a ", "an ")',
        None,
    ),
    (
        "scripts/validate_tree.py",
        "a PARSER CHANGE the reparsed runs predate",
        "examples/_shared/retrieval.py",
        '_ID_TOKEN = re.compile(r"^[\\w.\\-]+$")',
        '_ID_TOKEN = re.compile(r"^[Z\\w.\\-]+$")',
        "FAIL V10 runs: scorer_sha256 match the code (19 run(s))",
    ),
]


def shadow_tree() -> Path:
    """A private copy of the repository. Code, reports and docs are copied; harness/data is
    links to the real one, except the committed runs directories (validate.json), which are
    hard-linked because V9 lists them through git and a test writes into them: replace() a
    file there, never write it in place."""
    shadow = Path(tempfile.mkdtemp(prefix="checks-can-fail-"))
    atexit.register(shutil.rmtree, shadow, True)
    shutil.copytree(
        REPO,
        shadow,
        dirs_exist_ok=True,
        symlinks=True,
        ignore=shutil.ignore_patterns(".git", ".venv", "build", "__pycache__", "data"),
    )
    data = shadow / "harness" / "data"
    data.mkdir()
    policy = json.loads((HARNESS / "data" / "validate.json").read_text(encoding="utf-8"))
    committed = {d.split("/")[0] for d in policy.get("committed") or []}

    def link_or_copy(s, d):
        try:
            os.link(s, d)
        except OSError:  # another filesystem
            shutil.copy2(s, d)

    for child in (HARNESS / "data").iterdir():
        if child.name in committed:
            shutil.copytree(child, data / child.name, symlinks=True, copy_function=link_or_copy)
        else:
            (data / child.name).symlink_to(child)
    return shadow


def replace(f: Path, text: str) -> None:
    """Write a hard-linked file as a NEW file, so the real one is untouched."""
    f.unlink()
    f.write_text(text, encoding="utf-8")


def run_in(shadow: Path, script: str) -> str:
    """Run a checker in the shadow; V7 and V9 read the real git index, read only."""
    gitdir = subprocess.run(
        ["git", "rev-parse", "--absolute-git-dir"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    env = {**os.environ, "GIT_DIR": gitdir, "GIT_WORK_TREE": str(shadow), "GIT_OPTIONAL_LOCKS": "0"}
    r = subprocess.run(
        [sys.executable, str(shadow / "harness" / script)],
        cwd=shadow / "harness",
        capture_output=True,
        text=True,
        env=env,
    )
    out = (r.stdout or "") + (r.stderr or "")
    check(f"{script} exits non-zero", r.returncode != 0, f"exit {r.returncode}")
    # Exiting 1 on a traceback is how an earlier version of this test passed proving nothing.
    check(f"{script} fails by failing, not by crashing", "Traceback" not in out, out[-300:])
    return out


def plant_runs_linux(shadow: Path) -> None:
    """The defects V8 and V9 exist for. runs-linux was outside V8's list once, and V9 read
    presence while a truncated predictions.jsonl left `make ci` green. The emptied and
    truncated runs are ones no planted claim above depends on."""
    linux = shadow / "harness" / "data" / "runs-linux"
    src = sorted(linux.glob("cnn_bart_s_*/"))[0]
    shutil.copytree(src, linux / (src.name + "b"))
    replace(sorted(linux.glob("ag_bert_base_fy_*/"))[0] / "predictions.jsonl", "")
    partial = sorted(linux.glob("cnn_bart_m_*/"))[0] / "predictions.jsonl"
    replace(partial, "".join(partial.read_text(encoding="utf-8").splitlines(keepends=True)[:-3]))


def plant_runs_pair(shadow: Path) -> str:
    """The defects V1-V3 exist for, in a derived directory. Planted after the claims check has
    run: that check reads this run, and a run with no scores crashes it."""
    run = sorted((shadow / "harness" / "data" / "runs-pair").glob("*/metrics.json"))[0]
    m = json.loads(run.read_text(encoding="utf-8"))
    m["dataset_id"] = "no_such_dataset"
    m["build"] = {**(m.get("build") or {}), "ref": "unknown"}
    m.pop("scores", None)
    replace(run, json.dumps(m))
    return f"runs-pair/{run.parent.name}"


def main() -> int:
    print("the checks can fail (one run per checker, every defect named)\n")
    shadow = shadow_tree()
    for _script, what, rel, old, new, _says in PLANTS:
        f = shadow / rel
        text = f.read_text(encoding="utf-8")
        if check(
            f"the plant still anchors: {what} ({rel})",
            text.count(old) == 1,
            f"{text.count(old)} matches for {old[:60]!r} — update the anchor",
        ):
            f.write_text(text.replace(old, new), encoding="utf-8")
    plant_runs_linux(shadow)

    # validate_tree last: plant_runs_pair is for it alone.
    for script in dict.fromkeys(p[0] for p in PLANTS):
        pair = plant_runs_pair(shadow) if script == "scripts/validate_tree.py" else ""
        out = run_in(shadow, script)
        for s, what, _rel, _old, _new, says in PLANTS:
            if s == script and says:
                check(f"{script} names {what}", says in out, out[-400:])
        if script == "tools/check_report_claims.py":
            check("...and refuses a duplicated runs-linux arm", "FAIL runs-linux names each arm once" in out)
        if script == "scripts/validate_tree.py":
            check("validate: V1 checks the schema of a run in runs-pair", "FAIL V1" in out)
            check("validate: V2 names the dangling dataset in runs-pair", "FAIL V2" in out and pair in out)
            check(
                "validate: V3 names the run in runs-pair with no build ref", "FAIL V3" in out and pair in out
            )
            check("validate: V8 refuses a duplicate config_id in runs-linux", "FAIL V8" in out)
            check("validate: V9 refuses an empty predictions.jsonl", "is empty" in out)
            check("validate: V9 refuses fewer rows than n_items", "prediction rows" in out)
            # The NER parser and the extraction scorer plants land on the same 28 runs: all
            # three digests mismatching on every one of them is both plants caught.
            m = re.search(
                r"V10 runs: normalizer_sha256, parser_sha256, scorer_sha256 match the code "
                r"\((\d+) run\(s\)\) — (\d+) mismatch",
                out,
            )
            check(
                "validate: V10 names the NER parser and the extraction scorer changes",
                m is not None and int(m.group(2)) == 3 * int(m.group(1)),
                m and m.group(0),
            )

    # A git that cannot list what is committed lists nothing, and nothing listed once read as
    # nothing missing. A committed directory behind a link leaving the repository does it.
    repeats = shadow / "harness" / "data" / "runs-repeats"
    shutil.rmtree(repeats)
    repeats.symlink_to(HARNESS / "data" / "runs-repeats")
    out = run_in(shadow, "scripts/validate_tree.py")
    check("validate: V9 fails when git cannot list the committed runs", "git ls-files failed" in out)

    # The no-input path: the original check_terminology bug.
    with tempfile.TemporaryDirectory() as td:
        fake = Path(td) / "repo" / "harness"
        (fake / "data" / "runs").mkdir(parents=True)
        shutil.copytree(HARNESS / "scripts", fake / "scripts")
        shutil.copytree(HARNESS / "tools", fake / "tools")
        r = subprocess.run(
            [sys.executable, str(fake / "tools" / "check_terminology.py")],
            cwd=fake,
            capture_output=True,
            text=True,
        )
        check("check_terminology with no markdown exits non-zero", r.returncode != 0, f"exit {r.returncode}")
    return summary("guard checks")


if __name__ == "__main__":
    raise SystemExit(main())
