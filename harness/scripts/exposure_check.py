#!/usr/bin/env python3
"""Search the project's public repos for a held-out side's item ids (RFC-031 H1): a leak the register lacks.

    evh exposure-check --dataset-id triage_v1_test [--out new-reads.tsv]

config.yaml names what to search:

    exposure:
      public_repos: [../flotilla, ../agentic-ai-homelab]   # local git checkouts (a clone of each public repo)
      ids: [alert_id, short_id]                             # item fields that hold the item's own natural ids
      ids_hook: exposure_ids.py:forms                       # optional: forms(item) -> more strings to search

Each item's `item_id`, its natural ids and the hook's forms are searched in every commit of every branch (patches and
messages, `git log --all -G` and `--grep`). A hit counts only in a commit made after the item's time (the split's time
key: a commit can name an item before it was held out). A hit whose item is not in the register is a leak not yet
recorded: the count is printed, and `--out` writes them as a TSV for `evh exposure-add --from` (ids are not printed:
the terminal may be read by anyone). Exit 6 when there is one.

What it cannot catch, said every time: a paraphrase, a title, a range or list written without the ids' prefix
("-F, -J" for "ALERT-F, ALERT-J"), a private repo or a transcript. The ids hook can add list forms a project uses.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import re
import subprocess  # nosec B404 - git, on the project's own checkouts
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from evaluation_harness import _exposure, _jsonout, _seal, _store
from evaluation_harness._common import die, evh_prog, load_dataset, load_module
from evaluation_harness._importers import parse_time

MISSES = "not caught: a paraphrase, a title, a range or list written without the ids' prefix, a private repo, a transcript"


def settings() -> dict[str, Any]:
    """config.yaml's `exposure:` section."""
    import yaml  # noqa: PLC0415
    from evaluation_harness import _common  # noqa: PLC0415

    cfg = _common.ROOT / "config.yaml"
    doc = yaml.safe_load(_store.read_text(cfg, encoding="utf-8")) if _store.is_file(cfg) else {}
    out = (doc or {}).get("exposure") or {}
    if not isinstance(out, dict):
        die("config.yaml: exposure must be a mapping (public_repos, ids, ids_hook)", "invalid-file")
    return out


def _hook(spec: str | None):
    if not spec:
        return None
    from evaluation_harness import _common  # noqa: PLC0415

    path, _, fn = spec.rpartition(":")
    if not path or not fn:
        die(f"exposure.ids_hook {spec!r}: path/to/file.py:function", "invalid-file")
    mod = load_module((_common.ROOT / path).resolve(), "evh_exposure_ids_hook")
    return getattr(mod, fn)


def _commits(repo: Path, needle: str) -> list[datetime]:
    """When each commit that adds or removes `needle`, or names it in its message, was made (every branch)."""
    out: list[datetime] = []
    pattern = re.escape(needle)
    for args in (["-G", pattern], ["--grep", pattern]):
        r = subprocess.run(  # nosec B603 B607 - git, fixed arguments, the project's own checkout
            ["git", "-C", str(repo), "log", "--all", "--format=%cI", *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            die(f"{repo}: git log failed: {(r.stderr or '').strip()[:200]}", "failed")
        out += [t for t in (parse_time(x.strip()) for x in r.stdout.splitlines() if x.strip()) if t]
    return out


def main() -> int:
    """Search, count, write the new reads."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True, help="the held-out side")
    ap.add_argument(
        "--out", type=Path, help="write the leaks not in the register as a TSV for exposure-add --from"
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("exposure-check", args.json, live=sys.stderr):
        if not _exposure.applies(args.dataset_id):
            die(f"{args.dataset_id} is not a held-out side (no seal)", "not-allowed")
        conf = settings()
        repos = [Path(str(r)).expanduser() for r in conf.get("public_repos") or []]
        if not repos:
            die("config.yaml names no exposure.public_repos to search (local git checkouts)", "not-found")
        from evaluation_harness import _common  # noqa: PLC0415

        repos = [r if r.is_absolute() else (_common.ROOT / r).resolve() for r in repos]
        bad = [str(r) for r in repos if not (r / ".git").exists() and not (r / "HEAD").is_file()]
        if bad:
            die(f"not a git checkout: {', '.join(bad)}", "not-found")
        fields = [str(f) for f in conf.get("ids") or []]
        forms = _hook(conf.get("ids_hook"))
        doc = load_dataset(args.dataset_id)
        key = (
            ((doc.get("split") or {}).get("key"))
            if (doc.get("split") or {}).get("split_by") == "time"
            else None
        )
        registered = _exposure.exposed(args.dataset_id)
        leaks: list[dict[str, str]] = []
        hits = 0
        for it in doc["items"]:
            f = it.get("fields") or {}
            needles = {str(it["item_id"])} | {str(f[k]) for k in fields if f.get(k) not in (None, "")}
            if forms is not None:
                needles |= {str(x) for x in (forms(it) or []) if str(x).strip()}
            since = parse_time(f.get(key)) if key else None
            found = [
                (repo, t)
                for repo in repos
                for n in sorted(needles)
                for t in _commits(repo, n)
                if since is None or t > since
            ]
            if not found:
                continue
            hits += 1
            if str(it["item_id"]) not in registered:
                first = min(t for _r, t in found)
                leaks.append(
                    {
                        "item_id": str(it["item_id"]),
                        "what": "named in a public repo ("
                        + ", ".join(sorted({r.name for r, _t in found}))
                        + ")",
                        "by": "",
                        "at": first.isoformat(),
                    }
                )
        if args.out and leaks:
            lines = ["item_id\twhat\tby\tat"] + [
                f"{x['item_id']}\t{x['what']}\t{x['by']}\t{x['at']}" for x in leaks
            ]
            _store.write_text(args.out, "\n".join(lines) + "\n", encoding="utf-8")
        print(
            f"{args.dataset_id}: {hits} of {len(doc['items'])} held-out item(s) named in {len(repos)} public repo(s) "
            f"after their time; {len(leaks)} not in the register"
            + (
                f" (written to {args.out}: evh exposure-add --dataset-id {args.dataset_id} --from {args.out})"
                if args.out and leaks
                else ""
            )
        )
        print(f"  {MISSES}")
        sealed_at = _seal.record_of(args.dataset_id).get("sealed", {}).get("at")
        _jsonout.values(
            {"dataset_id": args.dataset_id, "named": hits, "new": len(leaks), "sealed_at": sealed_at}
        )
        return 6 if leaks else 0


if __name__ == "__main__":
    raise SystemExit(main())
