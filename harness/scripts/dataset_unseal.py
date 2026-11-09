#!/usr/bin/env python3
"""Open a sealed side of a split to one candidate, named in advance (the fleet's feedback 29).

    evh dataset-unseal triage_v1_test --config candidate_test_v1 --reason "the tuned filter, frozen on validation"

The config must run on the sealed dataset and carry a hypothesis (ADR-0025) committed before now: the candidate and
what it is compared with are named before anything is read from the held-out side. The unseal opens the dataset to
that config and to the config its hypothesis is against, and records the look: when, why, the hypothesis and the
commit that named it. Every other config is still refused. Each unseal is one look at the held-out side.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
from pathlib import Path

import yaml
from evaluation_harness import _hypothesis, _seal, _store
from evaluation_harness._common import DATASETS, dataset_id_ok, die, evh_prog, load_dataset, now, write_json


def _head(config_path: Path) -> dict:
    """The commit the working tree is at, as a run's build names it (the hypothesis must be in its history)."""
    from evaluation_harness._fingerprint import _git  # noqa: PLC0415

    ref = _git(Path(config_path).resolve().parent, "rev-parse", "HEAD")
    return {"source": "git", "ref": ref} if ref else {}


def main() -> int:
    """Open a sealed dataset to a candidate config."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("dataset_id", help="the sealed dataset (a split's test side)")
    ap.add_argument("--config", required=True, help="the candidate's config_id: it runs on this dataset")
    ap.add_argument("--reason", required=True, help="why this candidate, and why now: a sentence")
    args = ap.parse_args()

    ds_id = dataset_id_ok(args.dataset_id)
    doc = load_dataset(ds_id)
    if not doc.get("sealed"):
        die(f"{ds_id} is not sealed (dataset-split --seal seals a test side)", "not-allowed")
    if len(args.reason.split()) < 3:
        die("--reason is a sentence: why this candidate, and why now?", "bad-argument")
    ids = _hypothesis.config_ids()
    path = ids.get(args.config)
    if path is None:
        die(f"--config {args.config}: no arm config with that config_id", "not-found")
    cfg = yaml.safe_load(_store.read_text(path, encoding="utf-8")) or {}
    if cfg.get("dataset_id") != ds_id:
        die(f"{args.config} runs on {cfg.get('dataset_id')}, not on {ds_id}", "mismatch")
    hyp = _hypothesis.of(cfg)
    if not hyp:
        die(
            f"{args.config} names no hypothesis: write one in its config (against, measure, direction, statement; "
            "ADR-0025) and commit it, so the comparison is named before the held-out side is read",
            "not-allowed",
        )
    bad = _hypothesis.problems(cfg, path, ids)
    if bad:
        die(f"{args.config}: " + "; ".join(bad), "invalid-file")
    # The project's database keeps its configs out of git (RFC-025): no commit can speak for one, so the unseal
    # itself, timestamped before any run it allows, is the naming in advance, and the look says so.
    if _store.sqlite() and _store.rel(path) is not None:
        named = {"named": None, "commit": None, "why": "the config is in the project's database, not in git"}
    else:
        named = _hypothesis.named_before(path, hyp, _head(path), now())
        if named.get("named") is not True:
            die(
                f"{args.config}'s hypothesis is not committed: {named.get('why')}. Commit the config first.",
                "not-allowed",
            )
    opened = sorted({args.config, str(hyp["against"])} - _seal.opened_for(doc))
    look = {
        "config_id": args.config,
        "at": now(),
        "reason": args.reason,
        "hypothesis": hyp,
        "commit": named.get("commit") or "not determinable",
    }
    doc["unsealed"] = [*(doc.get("unsealed") or []), look]
    write_json(DATASETS / f"{ds_id}.json", doc)
    n = len(doc["unsealed"])
    print(
        f"data/datasets/{ds_id}.json  unsealed for {args.config} against {hyp['against']} "
        + (
            f"(look {n} at this held-out side; hypothesis committed {str(named.get('commit'))[:8]})"
            if named.get("commit")
            else f"(look {n} at this held-out side; {named.get('why')}: this unseal names it in advance)"
        )
    )
    if opened:
        print(f"  now open to: {', '.join(sorted(_seal.opened_for(doc) | set(opened)))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
