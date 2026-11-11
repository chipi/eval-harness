#!/usr/bin/env python3
"""Make the replay example's history (RFC-030): a system with three commits, production running them, all frozen.

    cd <your project>
    python <harness>/examples/replay-filing/make_history.py --out replay-filing

Everything is synthetic and made here, so the example runs anywhere at $0:

  OUT/system/            the filing system's git repository: three commits, system/v1..v3 of this folder
  OUT/frozen/            what a freezer keeps of production: decisions.jsonl (each signal, when its decision started
                         and when it was stamped, the issue it created) and issues.jsonl (each issue's timeline)
  OUT/rows.jsonl         one row per decision for `evh capture --importer jsonl`: the signal as the body, the times
                         and production's action (joined from the timelines by production_actions.py, R4)
  OUT/gold/              the actions that should have been taken, for a reference set

and, in the project's data: the code record `toy_filing` (data/models/, `kind: code`: the commits and when each ran
in production), the field set `filing`, the goal, and three configs: production's recorded arm, the replay, and a
candidate (every decision at the third commit).
It prints the commands that follow.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import production_actions  # noqa: E402

UTC = dt.timezone.utc
DAYS = [
    dt.datetime(2026, 10, 2, tzinfo=UTC),
    dt.datetime(2026, 10, 3, tzinfo=UTC),
    dt.datetime(2026, 10, 4, tzinfo=UTC),
]
#: (day, minutes after 09:00, signal); one day per version of the system.
SIGNALS: list[tuple[int, int, dict[str, Any]]] = [
    (0, 0, {"name": "Disk 91% on db2", "level": "warn", "source": "host"}),
    (0, 40, {"name": "API 500s on checkout", "level": "error", "source": "app"}),
    (0, 80, {"name": "Disk 91% on db2", "level": "warn", "source": "host"}),
    (0, 120, {"name": "Queue lag high", "level": "warn", "source": "app"}),
    (0, 160, {"name": "disk 97% on DB3", "level": "warn", "source": "host"}),
    (0, 240, {"name": "API 500s on checkout", "level": "error", "source": "app"}),
    (0, 280, {"name": "Cache misses rising", "level": "info", "source": "app"}),
    (0, 320, {"name": "Queue lag high", "level": "warn", "source": "app"}),
    (1, 0, {"name": "Disk 88% on db4", "level": "warn", "source": "host"}),
    (1, 40, {"name": "disk 99% on db2", "level": "warn", "source": "host"}),
    (1, 80, {"name": "Queue lag high", "level": "warn", "source": "app"}),
    (1, 120, {"name": "Cert expires in 9 days", "level": "warn", "source": "host"}),
    (1, 240, {"name": "Cert expires in 3 days", "level": "warn", "source": "host"}),
    (1, 280, {"name": "Queue lag high", "level": "warn", "source": "app"}),
    (2, 0, {"name": "Cache misses rising", "level": "info", "source": "app"}),
    (2, 40, {"name": "API 500s on checkout", "level": "error", "source": "app"}),
    (2, 80, {"name": "Queue lag high", "level": "warn", "source": "app"}),
    (2, 120, {"name": "Backup job failed", "level": "warn", "source": "app"}),
    (2, 160, {"name": "Disk 95% on db9", "level": "warn", "source": "host"}),
    (2, 200, {"name": "API 500s on checkout", "level": "error", "source": "app"}),
]
#: A person closes an issue (by its title) between decisions: (day, minutes after 09:00, title).
CLOSES = [
    (0, 200, "API 500s on checkout"),
    (1, 200, "Cert expires in 9 days"),
    (2, 180, "API 500s on checkout"),
]
#: Where the reference set says production was wrong: the info alert on day 1 should have filed nothing.
GOLD_FIXES = {"d07": "none"}


def iso(t: dt.datetime) -> str:
    return t.isoformat(timespec="milliseconds")


class Tracker:
    """Production's issue tracker: every write lands in an issue's timeline at the tracker's clock."""

    def __init__(self) -> None:
        self.issues: dict[int, dict[str, Any]] = {}
        self.next = 101
        self.clock = DAYS[0]

    def tick(self) -> str:
        self.clock += dt.timedelta(milliseconds=100)
        return iso(self.clock)

    def state(self, repo: str, n: int) -> str:
        state = "open"
        for e in self.issues[int(n)]["events"]:
            if e["type"] == "closed":
                state = "closed"
            elif e["type"] == "reopened":
                state = "open"
        return state

    def create(self, repo: str, title: str) -> int:
        n, self.next = self.next, self.next + 1
        at = self.tick()
        self.issues[n] = {
            "number": n,
            "title": title,
            "created_at": at,
            "events": [{"type": "created", "at": at, "by": "fleet"}],
        }
        return n

    def comment(self, repo: str, n: int, text: str) -> None:
        self.issues[int(n)]["events"].append(
            {"type": "comment", "at": self.tick(), "by": "fleet", "text": text}
        )

    def reopen(self, repo: str, n: int) -> None:
        self.issues[int(n)]["events"].append({"type": "reopened", "at": self.tick(), "by": "fleet"})

    def close(self, title: str, at: dt.datetime) -> None:
        for i in self.issues.values():
            if i["title"] == title and self.state("", i["number"]) == "open":
                i["events"].append({"type": "closed", "at": iso(at), "by": "person"})
                return


def git(cwd: Path, *args: str) -> str:
    env = dict(os.environ, GIT_AUTHOR_DATE="2026-10-01T00:00:00Z", GIT_COMMITTER_DATE="2026-10-01T00:00:00Z")
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env, check=True)
    return r.stdout.strip()


def make_repo(out: Path) -> list[str]:
    """The system's repository: one commit per version folder. Returns the commits, oldest first."""
    repo = out / "system"
    shutil.rmtree(repo, ignore_errors=True)
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "replay-example@example.invalid")
    git(repo, "config", "user.name", "replay example")
    commits = []
    for v in ("v1", "v2", "v3"):
        shutil.copy(HERE / "system" / v / "filing.py", repo / "filing.py")
        git(repo, "add", "filing.py")
        git(repo, "commit", "-q", "-m", f"filing {v}")
        commits.append(git(repo, "rev-parse", "HEAD"))
    return commits


def load_version(v: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"filing_{v}", HERE / "system" / v / "filing.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def run_production(out: Path) -> tuple[list[dict], list[dict]]:
    """Production: each day's version files that day's signals against the tracker, people close issues between."""
    tracker = Tracker()
    ledger = out / ".production-ledger.json"
    ledger.unlink(missing_ok=True)
    versions = [load_version(v) for v in ("v1", "v2", "v3")]
    for mod in versions:
        mod.GH, mod.LEDGER = tracker, str(ledger)
    events = sorted(
        [(DAYS[d] + dt.timedelta(hours=9, minutes=m), 0, s) for d, m, s in SIGNALS]
        + [(DAYS[d] + dt.timedelta(hours=9, minutes=m), 1, t) for d, m, t in CLOSES],
        key=lambda x: (x[0], x[1]),
    )
    decisions = []
    for at, kind, what in events:
        if kind == 1:
            tracker.close(what, at)
            continue
        tracker.clock = at
        before = set(tracker.issues)
        day = next(i for i in range(3) if DAYS[i] <= at < DAYS[i] + dt.timedelta(days=1))
        versions[day].file(dict(what))
        made = sorted(set(tracker.issues) - before)
        n = len(decisions) + 1
        decisions.append(
            {
                "id": f"d{n:02d}",
                "started": iso(at),
                "ts": iso(at + dt.timedelta(milliseconds=800)),  # stamped after its writes
                "signal": what,
                **({"production_issue": made[0]} if made else {}),
            }
        )
    ledger.unlink(missing_ok=True)
    return decisions, list(tracker.issues.values())


def write_data(rel: str, text: str) -> None:
    """A file into the project's data, in its store (files or SQLite)."""
    from evaluation_harness import _common, _store  # noqa: PLC0415 - the harness only where data is written

    _store.write_text(_common.DATA / rel, text)
    print(f"  wrote data/{rel}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--out", type=Path, default=Path("replay-filing"), help="the folder to make (relative to here)"
    )
    args = ap.parse_args()
    root = Path.cwd().resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    def rel(p: Path) -> str:
        try:
            return str(p.relative_to(root))
        except ValueError:
            return str(p)

    commits = make_repo(out)
    decisions, issues = run_production(out)
    actions, stray = production_actions.actions(decisions, issues)
    (out / "frozen").mkdir(exist_ok=True)
    (out / "frozen" / "decisions.jsonl").write_text(
        "".join(json.dumps(d, sort_keys=True) + "\n" for d in decisions)
    )
    (out / "frozen" / "issues.jsonl").write_text(
        "".join(json.dumps(i, sort_keys=True) + "\n" for i in issues)
    )
    rows = [
        {
            "id": d["id"],
            "body": json.dumps(d["signal"], sort_keys=True),
            "created_at": d["ts"],
            "ts": d["ts"],
            "started": d["started"],
            **({"production_issue": d["production_issue"]} if "production_issue" in d else {}),
            "action": actions[d["id"]],
        }
        for d in decisions
    ]
    (out / "rows.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    gold = out / "gold"
    shutil.rmtree(gold, ignore_errors=True)
    gold.mkdir()
    for d in decisions:
        (gold / f"{d['id']}.txt").write_text(GOLD_FIXES.get(d["id"], actions[d["id"]]) + "\n")
    print(
        f"made {out}: {len(commits)} commits, {len(decisions)} decisions, {len(issues)} issues, {len(stray)} stray write(s)"
    )

    versions = "".join(
        f"  - commit: {c}\n"
        f"    deployed: [{{from: '{DAYS[i].isoformat()}'"
        + (f", to: '{DAYS[i + 1].isoformat()}'" if i + 1 < len(commits) else "")
        + f"}}]\n    note: filing v{i + 1}\n"
        for i, c in enumerate(commits)
    )
    write_data(
        "models/toy_filing.yaml",
        "model_id: toy_filing\nkind: code\n"
        f"repo: {rel(out / 'system')}\nnotes: the replay example's synthetic filing system (RFC-030)\n"
        f"versions:\n{versions}",
    )
    write_data(
        "fields/filing.yaml",
        "fieldset_id: filing\ndescription: a filing decision's times and the issue production created\nfields:\n"
        "  - {name: ts, type: datetime, label: Stamped, description: 'when the decision was stamped, after its writes'}\n"
        "  - {name: started, type: datetime, label: Started, description: 'when the decision started and read the tracker'}\n"
        "  - {name: production_issue, type: integer, label: Issue created, description: the issue production created}\n",
    )
    adapter = rel(HERE / "replay_filing.py")
    replay = (
        "dataset_id: filing_history_v1\ngoal: filing\nadapter: {adapter}\nmodel_record: toy_filing\n"
        "replay: {{order: [ts], time_field: started, support: [replay_world.py]{commit}}}\n"
        "params:\n  world: {world}\n"
    )
    world = rel(out / "frozen")
    write_data(
        "configs/filing_replay_v1.yaml",
        "config_id: filing_replay_v1\n" + replay.format(adapter=adapter, commit="", world=world),
    )
    write_data(
        "configs/filing_candidate_v3.yaml",
        "config_id: filing_candidate_v3\n"
        + replay.format(adapter=adapter, commit=f", commit: {commits[-1]}", world=world),
    )
    write_data(
        "configs/filing_production_v1.yaml",
        "config_id: filing_production_v1\ndataset_id: filing_history_v1\ngoal: filing\n"
        f"adapter: {adapter}\nparams:\n  provider: recorded\n  capture: filing_prod\n  field: action\n",
    )
    write_data(
        "goals/filing.yaml",
        "goal_id: filing\ntitle: Filing decisions\nstatement: Does a change to the filing stage take better actions?\n"
        "decision: whether to deploy a filing change\nsuccess_criteria: {primary: {measure: exact, direction: higher}}\n"
        "datasets:\n  - {dataset_id: filing_history_v1, role: validation}\n",
    )
    print(
        "\nnext:\n"
        f'  evh capture --importer jsonl --query \'{{"path": "{rel(out / "rows.jsonl")}"}}\' --capture filing_prod\n'
        "  evh dataset-from-capture filing_prod --dataset-id filing_history_v1 --fieldset filing "
        "--field ts --field started --field production_issue\n"
        "  evh dataset-materialize --dataset-id filing_history_v1\n"
        "  evh run --config data/configs/filing_production_v1.yaml\n"
        "  evh faithfulness --config data/configs/filing_replay_v1.yaml --production <that run>\n"
        f"  evh label-import {rel(gold)} --dataset-id filing_history_v1 --set gold --by person:you\n"
        "  evh reference-promote --dataset-id filing_history_v1 --labels gold --tier gold --reason '...' --by person:you\n"
        "  evh run --config data/configs/filing_replay_v1.yaml\n"
        "  evh run --config data/configs/filing_candidate_v3.yaml\n"
        f"  python {rel(HERE / 'mutants.py')} --system {rel(out / 'system')} --production <that run>"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
