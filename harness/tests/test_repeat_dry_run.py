#!/usr/bin/env python3
"""`evh run --purpose repeat --of RUN --dry-run` says where the repeat would be read, and what differs (0.8.1 beta).

    EVAL_STORE=files python tests/test_repeat_dry_run.py        (and EVAL_STORE=sqlite)

The real run said it ("repeat of RUN: not the same measurement (...), so this run is read under `repeats`") and the dry
run, where --help sends a user first, said nothing. Now the dry run prints the same line, from the same function; the line
names the parts that differ with their value then and now (an adapter's sha256, a setting, the items), not the list of all
four; a dry run on a dataset that is not materialized refuses as the run does, before pricing it at 0 tokens; and
`--items` (a subset: other data than the whole dataset) says in --help and in the line whether it can join RUN's arm.
"""

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
proj = Path(tempfile.mkdtemp(prefix="evh-repeat-dry-"))
os.environ["EVAL_HOME"] = str(proj)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVAL_MAX_COST_USD"):
    os.environ.pop(k, None)
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _format, _store  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.model import runs as R  # noqa: E402

KIT = HARNESS / "tutorial"
env = dict(os.environ, EVAL_BUILD_REF="test-repeat-dry", EVAL_MAX_RETRIES="0", EVH_ACTOR="person:test")
DS = "tickets_v1"
RAW = "tickets_raw"

ADAPTER = """
from types import SimpleNamespace

def call_system(text, params):
    return SimpleNamespace(output=text[: int(params.get("n", 40))], tokens_in=10, tokens_out=5, cost_usd=None,
                           latency_ms=None, extra={}, meta={})

def score(output, reference):
    return {"words": float(len(output.split()))}

PRIMARY_METRIC = "words"
"""


def evh(*args):
    _store.close()
    return _cli.run(proj, env, *args)


def out(r):
    return r.stdout + r.stderr


def system(name, **params):
    body = "".join(f"  {k}: {json.dumps(v)}\n" for k, v in params.items())
    _runstore.write_text(
        proj, f"systems/{name}.yaml", f"system_id: {name}\nadapter: a.py\nparams:\n  provider: echo\n{body}"
    )


def run_ids(sid, ds=DS):
    _store.close()
    return sorted(R.run_of(sd).name for sd, _rec in R.scored(ds, system_id=sid, label_is=None))


def says(r):
    return next((ln for ln in out(r).splitlines() if ln.strip().startswith("repeat of ")), "")


try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (proj / "data" / "systems").mkdir(parents=True)
        (proj / "data" / "goals").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    (proj / "a.py").write_text(ADAPTER, encoding="utf-8")
    _runstore.write_text(proj, "validate.json", json.dumps({"committed": ["runs", "repeats"]}))
    _runstore.write_text(
        proj,
        "goals/tickets_summary.yaml",
        (KIT / "goals" / "tickets_summary.yaml").read_text(encoding="utf-8").replace("overlap_f1", "words"),
    )
    r = evh("dataset-create", "--dataset-id", DS, "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", DS)
    check("setup: a materialized dataset", r.returncode == 0, out(r)[-300:])
    r = evh("dataset-create", "--dataset-id", RAW, "--source-dir", "tutorial/tickets")
    check("setup: a dataset that is not materialized", r.returncode == 0, out(r)[-300:])

    system("fleet_v1", n=30)
    r = evh("run", "--system", "fleet_v1", "--dataset", DS)
    (x0,) = run_ids("fleet_v1")
    check("setup: the run to repeat", r.returncode == 0, out(r)[-300:])
    base = ("run", "--system", "fleet_v1", "--dataset", DS, "--purpose", "repeat", "--of", x0)

    # A: the dry run says where the repeat is read, in the real run's words
    r = evh(*base, "--dry-run")
    dry = says(r)
    check(
        "A: a dry run of a repeat that is the same measurement says it joins RUN's arm, calling nothing",
        r.returncode == 0
        and f"repeat of {x0}: the same measurement" in dry
        and "joins its arm" in dry
        and "DRY RUN" in r.stdout
        and run_ids("fleet_v1") == [x0],
        (out(r)[-600:], run_ids("fleet_v1")),
    )
    r = evh(*base)
    real = says(r)
    check(
        "A: the real run says the same line the dry run did", r.returncode == 0 and real == dry, (real, dry)
    )

    system("fleet_v1", n=20)
    r = evh(*base, "--dry-run")
    dry = says(r)
    check(
        "A: a dry run of a repeat that is not says it is read under `repeats`, and why",
        r.returncode == 0 and "not the same measurement" in dry and "read under `repeats`" in dry,
        out(r)[-600:],
    )
    r = evh(*base)
    check("A: the real run says the same line (one source)", says(r) == dry, (says(r), dry))

    # B: what differs is named, with its value then and now; what does not differ is not listed
    check(
        "B: a changed setting is named with its value then and now; data, deployment and adapter are not named",
        "settings" in dry
        and "30 then" in dry
        and "20 now" in dry
        and "data" not in dry.replace("deployment", "")
        and "adapter" not in dry
        and "(data, deployment, settings, adapter)" not in dry,
        dry,
    )
    system("fleet_v1", n=30)
    (proj / "a.py").write_text(
        ADAPTER.replace('"words": float(len(output.split()))', '"words": float(len(output))'),
        encoding="utf-8",
    )
    old_sha = (
        ((R.run(x0) or {}).get("fingerprint") or {})
        .get("instrument", {})
        .get("adapter", {})
        .get("sha256", "")
    )
    r = evh(*base, "--dry-run")
    dry = says(r)
    check(
        "B: a changed adapter is named with its sha256 then and now, abbreviated",
        "not the same measurement" in dry
        and f"adapter sha256 {old_sha[:8]}… then" in dry
        and re.search(r"then, [0-9a-f]{8}… now", dry) is not None
        and "settings" not in dry,
        (dry, old_sha[:8]),
    )
    (proj / "a.py").write_text(ADAPTER, encoding="utf-8")

    # D: a subset is other data; it joins RUN's arm only if RUN ran exactly these items
    items = proj / "three.txt"
    ds_items = sorted(p.stem for p in (proj / "tutorial" / "tickets").glob("*.txt"))[:2]
    items.write_text("\n".join(ds_items) + "\n", encoding="utf-8")
    r = evh(*base, "--items", str(items), "--dry-run")
    dry = says(r)
    check(
        "D: a subset repeat of a whole-dataset run is read under `repeats`: the data differs, and the line says why",
        r.returncode == 0
        and "not the same measurement" in dry
        and "data.n_items" in dry
        and "--items" in dry
        and "same items" in dry,
        out(r)[-700:],
    )
    system("subset_v1", n=30)
    r = evh("run", "--system", "subset_v1", "--dataset", DS, "--items", str(items))
    (s0,) = run_ids("subset_v1")
    sub = (
        "run",
        "--system",
        "subset_v1",
        "--dataset",
        DS,
        "--purpose",
        "repeat",
        "--of",
        s0,
        "--items",
        str(items),
    )
    r = evh(*sub, "--dry-run")
    dry = says(r)
    check(
        "D: a subset repeat of a run of exactly these items joins its arm, and the line says the items are the same",
        r.returncode == 0
        and "the same measurement" in dry
        and "joins its arm" in dry
        and "same items" in dry,
        dry or out(r)[-500:],
    )
    r = evh("run", "--system", "subset_v1", "--dataset", DS, "--purpose", "repeat", "--of", s0, "--dry-run")
    dry = says(r)
    check(
        "D: a whole-dataset repeat of a subset run is read under `repeats`, with the item counts then and now",
        "not the same measurement" in dry and "data.n_items 2 then" in dry and "--items" not in dry,
        dry or out(r)[-500:],
    )
    r = evh("run", "--help")
    help_text = r.stdout
    help_items = " ".join(
        re.search(r"\n  --items FILE(.*?)(?=\n  --|\Z)", r.stdout, re.S).group(1).split()  # type: ignore[union-attr]
        if re.search(r"\n  --items FILE", r.stdout)
        else ""
    )
    check(
        "D: run --help for --items says a subset is other data and joins only a run of the same items",
        "other data" in help_items and "exactly these items" in help_items and "`repeats`" in help_items,
        help_items or r.stdout[-400:],
    )

    # help and price text a beta project asked for
    dataset_help = " ".join(
        re.search(r"\n  --dataset DATASET(.*?)(?=\n  --|\Z)", help_text, re.S).group(1).split()  # type: ignore[union-attr]
        if re.search(r"\n  --dataset DATASET", help_text)
        else ""
    )
    check(
        "--dataset in `evh run --help` names the command that lists datasets",
        "evh dataset-list" in dataset_help,
        dataset_help or help_text[-300:],
    )
    r = evh("run", "--system", "fleet_v1", "--dataset", DS, "--dry-run")
    price = " ".join(r.stdout.split("No price in the system", 1)[-1].split("\n\n")[0].split())
    check(
        "the dry run's no-price note says where the price goes (the system's params) and that 0 is a valid price",
        r.returncode == 0 and "params" in price and "system" in price and "0 is a valid price" in price,
        price or out(r)[-400:],
    )

    # C: a dataset that is not materialized refuses in the dry run as in the run
    system("raw_v1", n=30)
    r = evh("run", "--system", "raw_v1", "--dataset", RAW, "--dry-run")
    real = evh("run", "--system", "raw_v1", "--dataset", RAW)
    want = f"evh dataset-materialize --dataset-id {RAW}"
    check(
        "C: a dry run on a dataset that is not materialized refuses (not-materialized) naming the command, with no "
        "0-token price",
        r.returncode != 0
        and "not-materialized" in out(r)
        and want in out(r)
        and "input" not in r.stdout
        and "not-materialized" in out(real)
        and want in out(real),
        (out(r)[-500:], out(real)[-300:]),
    )
finally:
    _store.close()
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
