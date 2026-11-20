#!/usr/bin/env python3
"""The committed judge-validation records as runs of the rated datasets, for $0 (RFC-038 section 3.6).

    python tools/reproject_judge_validation.py            # from harness/: the eight recorded runs
    python tools/reproject_judge_validation.py --dry-run  # what it would run

It can be run again: a capture and a system that exist with the same content are "kept" (not made again) and the run is
made anew; one that exists with other content is refused, naming it, and nothing is run for it. EVAL_HOME names the
project (default: this checkout's harness/); `--scorers` and `--sources` narrow what is read.

`validate_judge_goyal.py` and `validate_judge_zhang.py` stored each judge's replies under
`data/judge-validation/<scorer>/<source>/<judge>/`. This reads them as a capture of verdicts in the core adapter's
output form (`scripts/judge_validation.py`, in the dataset's item order), makes a recorded system of it and runs it over
the rated dataset the example's source builds: a run scored as a live one is, with the people's own agreement beside the
judge's, and nothing called. Run it in this checkout after the datasets exist (the RUNBOOK's commands):

    evh dataset-create --dataset-id goyal2022_cnn_v1 --source ../examples/judge-validation-goyal/source.py:Source \\
        --query '{"answer": "ratings"}'     (and zhang2023_cnndm_v1 with the Zhang source), then materialize, then
    evh reference-promote --dataset-id ... --labels answers --tier gold --reason "..." --by ...

The old reports and records stay as the research report's evidence; these runs are what the command reads.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
os.environ.setdefault("EVAL_HOME", str(HARNESS))
#: The project the runs are made in: this checkout's harness/ unless EVAL_HOME names another (a test's scratch one).
PROJECT = Path(os.environ["EVAL_HOME"]).resolve()

from evaluation_harness import _store  # noqa: E402

#: How a capture names this file: from the checkout's harness/, else where it is.
IMPORTER = (
    "tools/reproject_judge_validation.py" if HARNESS.resolve() == PROJECT else f"{Path(__file__).resolve()}"
)
SOURCES = {"goyal": ("goyal2022-cnn", "goyal2022_cnn_v1"), "zhang": ("zhang2023-cnndm", "zhang2023_cnndm_v1")}
SCORERS = ("judge-summ-v1", "judge-summ-v2")
SYSTEMS = ("gpt3", "brio", "t0")
DIMS = ("coherence", "consistency", "fluency", "relevance")


class Importer:
    """A source's committed records for one judge as records of verdicts: `{id: the item's id, body: the verdict}`."""

    def __init__(self, options: dict) -> None:
        self.options = options

    def records(self, query: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """Query: scorer, judge, source (`goyal` or `zhang`)."""
        root = (
            PROJECT
            / "data"
            / "judge-validation"
            / query["scorer"]
            / SOURCES[query["source"]][0]
            / query["judge"]
        )
        files = sorted(_store.glob(root, "*.json"))
        if not files:
            raise ValueError(f"no records under {root}")
        if query["source"] == "goyal":
            for f in files:
                r = json.loads(_store.read_text(f))
                reply = json.loads(re.search(r"\{.*\}", r["output"], re.S).group(0))  # type: ignore[union-attr]
                pos = {n: i for i, n in enumerate(r["order"])}
                scores = {d: [float(reply[d][pos[n]]) for n in SYSTEMS] for d in DIMS}
                yield {"id": r["article_id"], "body": {"scores": scores, "blocks": 1, "parsed": 1}}
            return
        by_article: dict[str, list[dict[str, Any]]] = {}
        for f in files:
            r = json.loads(_store.read_text(f))
            by_article.setdefault(r["article_id"], []).append(r)
        for aid, recs in by_article.items():
            names = sorted(n for r in recs for n in r["order"])
            got: dict[str, dict[str, float]] = {d: {} for d in DIMS}
            parsed = 0
            for r in recs:
                if r["dims"] is None:
                    continue
                parsed += 1
                for d in DIMS:
                    for n, v in zip(r["order"], r["dims"][d], strict=True):
                        got[d][n] = float(v)
            verdict = {
                "scores": {d: [got[d][n] for n in names] for d in DIMS} if parsed == len(recs) else None
            }
            yield {"id": aid, "body": {**verdict, "blocks": len(recs), "parsed": parsed}}


def capture_id(source: str, scorer: str, judge: str) -> str:
    """The capture's id: lowercase letters, digits and underscores."""
    return re.sub(r"[^a-z0-9]+", "_", f"{source}_{scorer}_{judge}".lower())


def system_id(source: str, scorer: str, judge: str) -> str:
    """The recorded system's id: the judge's validation system, and the source it was recorded on."""
    return f"{scorer}__{judge}__validation_{source}"


def capture_kept(cap: str, query: dict[str, Any]) -> bool | None:
    """True when the capture exists with these records (kept), False when it does not exist; None when it exists with
    other records."""
    from evaluation_harness.dataset_from_capture import load_capture  # noqa: PLC0415

    if not _store.is_file(PROJECT / "data" / "captures" / cap / "capture.json"):
        return False
    _doc, have = load_capture(cap)
    want = {r["id"]: r["body"] for r in Importer({}).records(query)}
    return True if {r["id"]: r["body"] for r in have} == want else None


def system_kept(sid: str, spec: dict[str, Any]) -> bool | None:
    """True when the system exists with this content (kept), False when it does not exist; None when it differs."""
    import yaml  # noqa: PLC0415

    f = PROJECT / "data" / "systems" / f"{sid}.yaml"
    if not _store.is_file(f):
        return False
    return True if yaml.safe_load(_store.read_text(f)) == spec else None


def evh(*args: str) -> subprocess.CompletedProcess[str]:
    """`evh <args>` in the project."""
    return subprocess.run(  # nosec B603 - this interpreter and the harness's own CLI
        [sys.executable, str(HARNESS / "scripts" / "cli.py"), *args],
        cwd=PROJECT, capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False,
    )  # fmt: skip


def main() -> int:
    """Capture, record and run each of the eight sets of records; 1 when one step fails."""
    import yaml  # noqa: PLC0415

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--scorers", nargs="+", default=list(SCORERS), help="the scorers to read (default: both)")
    ap.add_argument(
        "--sources", nargs="+", choices=list(SOURCES), default=list(SOURCES), help="default: both"
    )
    args = ap.parse_args()
    for scorer in args.scorers:
        sc = yaml.safe_load(_store.read_text(PROJECT / "data" / "scorers" / f"{scorer}.yaml"))
        for j in sc["judges"]:
            for source in args.sources:
                _folder, dataset = SOURCES[source]
                cap, sid = capture_id(source, scorer, j["id"]), system_id(source, scorer, j["id"])
                steps = [
                    ["capture", "--importer", f"{IMPORTER}:Importer", "--capture", cap,
                     "--query", json.dumps({"scorer": scorer, "judge": j["id"], "source": source})],
                    ["run", "--system", sid, "--dataset", dataset],
                ]  # fmt: skip
                print(f"{scorer} {j['id']} {source}: capture {cap}, system {sid}, run on {dataset}")
                if args.dry_run:
                    continue
                spec: dict[str, Any] = {
                    "system_id": sid,
                    "adapter": "scripts/judge_validation.py",
                    "params": {
                        "provider": "recorded",
                        "capture": cap,
                        "scorer": scorer,
                        "judge": j["id"],
                        "mode": sc.get("mode") or "grade",
                        "task": sc.get("task") or {},
                        "recorded_from": f"data/judge-validation/{scorer}/{_folder}/{j['id']}",
                    },
                }
                if not spec["params"]["task"]:
                    del spec["params"]["task"]
                query = {"scorer": scorer, "judge": j["id"], "source": source}
                cap_state, sys_state = capture_kept(cap, query), system_kept(sid, spec)
                if cap_state is None or sys_state is None:
                    which = f"capture {cap}" if cap_state is None else f"system {sid}"
                    print(
                        f"  REFUSED: {which} exists and differs from what the records and the scorer give; nothing is run"
                    )
                    return 1
                if cap_state:
                    print(f"  capture: kept {cap}")
                else:
                    r = evh(*steps[0])
                    if r.returncode:
                        print(r.stdout + r.stderr)
                        return 1
                    print(
                        f"  capture: {next((ln for ln in r.stdout.splitlines() if ln.strip()), '').strip()[:200]}"
                    )
                if sys_state:
                    print(f"  system: kept {sid}")
                else:
                    _store.write_text(
                        PROJECT / "data" / "systems" / f"{sid}.yaml",
                        "# A judge's committed validation records, read as a recorded arm over a rated dataset\n"
                        "# (tools/reproject_judge_validation.py): nothing is called.\n"
                        + yaml.safe_dump(spec, sort_keys=False),
                    )
                    print(f"  system: wrote {sid}")
                r = evh(*steps[1])
                if r.returncode:
                    print(r.stdout + r.stderr)
                    return 1
                last = [ln for ln in r.stdout.splitlines() if ln.strip()][-1] if r.stdout.strip() else ""
                print(f"  run: {last.strip()[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
