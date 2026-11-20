#!/usr/bin/env python3
"""The committed judge-validation records as runs of the rated datasets, for $0 (RFC-038 section 3.6).

    python tools/reproject_judge_validation.py            # from harness/: the eight recorded runs
    python tools/reproject_judge_validation.py --dry-run  # what it would run

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

from evaluation_harness import _store  # noqa: E402

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
            HARNESS
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


def evh(*args: str) -> subprocess.CompletedProcess[str]:
    """`evh <args>` in this checkout."""
    return subprocess.run(  # nosec B603 - this interpreter and the harness's own CLI
        [sys.executable, str(HARNESS / "scripts" / "cli.py"), *args],
        cwd=HARNESS, capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False,
    )  # fmt: skip


def main() -> int:
    """Capture, record and run each of the eight sets of records; 1 when one step fails."""
    import yaml  # noqa: PLC0415

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    for scorer in SCORERS:
        sc = yaml.safe_load(_store.read_text(HARNESS / "data" / "scorers" / f"{scorer}.yaml"))
        for j in sc["judges"]:
            for source, (_folder, dataset) in SOURCES.items():
                cap, sid = capture_id(source, scorer, j["id"]), system_id(source, scorer, j["id"])
                steps = [
                    ["capture", "--importer", "tools/reproject_judge_validation.py:Importer", "--capture", cap,
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
                for n, step in enumerate(steps):
                    if n == 1:
                        _store.write_text(
                            HARNESS / "data" / "systems" / f"{sid}.yaml",
                            "# A judge's committed validation records, read as a recorded arm over a rated dataset\n"
                            "# (tools/reproject_judge_validation.py): nothing is called.\n"
                            + yaml.safe_dump(spec, sort_keys=False),
                        )
                    r = evh(*step)
                    if r.returncode:
                        print(r.stdout + r.stderr)
                        return 1
                    last = [ln for ln in r.stdout.splitlines() if ln.strip()][-1] if r.stdout.strip() else ""
                    print(f"  {step[0]}: {last.strip()[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
