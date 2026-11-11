#!/usr/bin/env python3
"""Mutants for the filing replay (RFC-030 R5): does the faithfulness gate notice a change to the system?

    python <harness>/examples/replay-filing/mutants.py --system replay-filing/system --production <production's run>

Each mutant is a named edit of `filing.py`, applied to every commit that has the line it edits: its repository is a
clone of the system's with each commit rewritten, its code record (`data/models/toy_filing_m_<name>.yaml`, kind: code)
maps each version to the rewritten commit, and `evh faithfulness` replays it against production's arm. A mutant is killed when the replay
disagrees with production somewhere; one that survives is printed with the functions the replay never entered, which
is usually why (no decision in the history reaches the rule). Exit 1 when a mutant survives that coverage does not
explain, else 0.
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

#: (name, the line's text as it is, as the mutant has it, the function a survivor's coverage should name).
MUTANTS = [
    ("reopen-as-comment", 'if GH.state(REPO, n) == "closed":', "if False:", None),
    ("key-keeps-case", ".lower()", "", None),
    ("info-files", 'if signal.get("level") == "info":', "if False:", None),
    ("cron-waits-longer", "< 3", "< 5", "_cron_waits"),
]


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def mutate(system: Path, dest: Path, old: str, new: str) -> dict[str, str]:
    """A clone of `system` whose every commit has `old` replaced by `new` in filing.py: {original commit: mutant}."""
    shutil.rmtree(dest, ignore_errors=True)
    commits = git(system, "rev-list", "--reverse", "HEAD").split()
    dest.mkdir(parents=True)
    git(dest, "init", "-q", "-b", "main")
    git(dest, "config", "user.email", "replay-example@example.invalid")
    git(dest, "config", "user.name", "replay example")
    out = {}
    for c in commits:
        text = git(system, "show", f"{c}:filing.py") + "\n"
        (dest / "filing.py").write_text(text.replace(old, new))
        git(dest, "add", "filing.py")
        git(dest, "commit", "-q", "--allow-empty", "-m", f"mutant of {c[:12]}")
        out[c] = git(dest, "rev-parse", "HEAD")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--system", type=Path, required=True, help="the system's repository (make_history.py's OUT/system)"
    )
    ap.add_argument("--production", required=True, help="production's arm: the run of filing_production_v1")
    ap.add_argument(
        "--config", default="data/configs/filing_replay_v1.yaml", help="the replay config mutants copy"
    )
    ap.add_argument("--evh", default="evh", help="how to call the harness (default: evh)")
    args = ap.parse_args()
    import yaml  # noqa: PLC0415
    from evaluation_harness import _common, _store  # noqa: PLC0415 - the harness only where data is written

    root = Path.cwd().resolve()
    base = yaml.safe_load(_store.read_text(root / args.config))
    record = yaml.safe_load(_store.read_text(_common.DATA / "models" / f"{base['model_record']}.yaml"))
    survivors = []
    for name, old, new, explained_by in MUTANTS:
        repo = args.system.resolve().parent / "mutants" / name
        mapping = mutate(args.system.resolve(), repo, old, new)
        model_id = f"{record['model_id']}_m_{name.replace('-', '_')}"
        rec = {
            **record,
            "model_id": model_id,
            "repo": str(repo.relative_to(root)) if repo.is_relative_to(root) else str(repo),
        }
        rec["versions"] = [
            {"commit": mapping[git(args.system, "rev-parse", v["commit"])], "deployed": v["deployed"]}
            for v in record["versions"]
        ]
        _store.write_text(_common.DATA / "models" / f"{model_id}.yaml", yaml.safe_dump(rec, sort_keys=False))
        cfg = {
            **base,
            "config_id": f"{base['config_id']}_m_{name.replace('-', '_')}",
            "model_record": model_id,
        }
        cfg_path = repo.parent / f"{name}.yaml"
        cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False))
        cmd = [
            *shlex.split(args.evh),
            "faithfulness",
            "--config",
            str(cfg_path),
            "--production",
            args.production,
            "--json",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        try:
            got = (json.loads(r.stdout).get("result") or {}).get("values", {}).get("faithfulness") or {}
        except ValueError:
            print(f"{name}: evh faithfulness failed: {r.stderr[-400:]}")
            return 2
        dis = got.get("disagreements") or []
        never = [n for v in (got.get("coverage") or {}).values() for n in v.get("never") or []]
        if dis:
            print(f"{name}: killed ({len(dis)} decision(s) differ, the first {dis[0]['item_id']})")
            continue
        why = [n for n in never if explained_by and n.endswith(f":{explained_by}")]
        print(f"{name}: SURVIVED; never entered: {', '.join(never) or 'nothing'}")
        if not why:
            survivors.append(name)
    print(f"{len(MUTANTS) - len(survivors)} of {len(MUTANTS)} mutants killed or explained by coverage")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
