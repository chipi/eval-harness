#!/usr/bin/env python3
"""Whether a call is a public server's is one function (RFC-041 F4): `_visibility.public()`.

    EVAL_STORE=files python tests/test_public_gate.py

- it is true with public hosts (`catalog-serve --public`), inside `public_call(True)` (an MCP call made for a public
  server) and under EVH_PUBLIC; the comparison and the inspector's item route read the same function, so a call that is
  public by one rule is public by all;
- an in-process public call (public_env true, no hosts) is refused an item's text by `catalog_serve.item` itself, not
  only by the registry's `public_dropped` list: no source text, no labels, no judge reasons, the outputs withheld;
- `hidden` fails closed on a public server: a dataset whose file is missing or unparseable shows no text there, and
  still none is hidden on a person's own machine.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
tmp = Path(tempfile.mkdtemp(prefix="evh-public-gate-"))
os.environ["EVAL_HOME"] = str(tmp)
os.environ.pop("EVH_PUBLIC", None)
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/
import _catalog_fixture as fx  # noqa: E402
from evaluation_harness import _store, _visibility  # noqa: E402
from evaluation_harness import catalog_serve as cs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.catalog_adapter import HarnessAdapter  # noqa: E402
from evaluation_harness.model import compare  # noqa: E402

SECRET = "Hiddenmarkerword"


def has_text(doc: object) -> bool:
    return SECRET in json.dumps(doc)


try:
    # ── the one function ──────────────────────────────────────────────────────────────────────────────────────────
    saved = dict(cs.LIMITS)
    check("local: not public", _visibility.public() is False)
    with _visibility.public_call(True):
        check("inside public_call(True): public, with no hosts", _visibility.public() is True)
    check("... and not after it", _visibility.public() is False)
    cs.LIMITS["hosts"] = ("example.org",)
    check("with public hosts: public, outside any public_call", _visibility.public() is True)
    cs.LIMITS.clear()
    cs.LIMITS.update(saved)
    os.environ["EVH_PUBLIC"] = "1"
    check("under EVH_PUBLIC: public", _visibility.public() is True)
    del os.environ["EVH_PUBLIC"]
    check(
        "the comparison keeps no copy of the rule",
        not hasattr(compare, "public") and "def public(" not in Path(compare.__file__).read_text(),
    )

    # ── an in-process public call is refused an item's text by the inspector's own route ─────────────────────────
    data = tmp / "data"
    _store.mkdir(data / "datasets", parents=True, exist_ok=True)

    def record(name: str, text: str | None = None) -> None:
        _store.write_text(
            data / "datasets" / f"{name}.json", text or json.dumps({"dataset_id": name, "items": []})
        )
        _visibility._CACHE.clear()

    record("ds1")
    rows = [{"item_id": "i00", "acc": 0.5}]
    fx.put(
        data,
        "a_1",
        {"run_id": "a_1", "dataset_id": "ds1", "system_id": "arm_a", "primary_metric": "acc",
         "metric_kinds": {"acc": "quality"}, "fingerprint": {"data": {"reference_id": "gold/ds1"}}},
        "\n".join(json.dumps(x) for x in rows) + "\n",
        outputs={"i00": f"{SECRET} an output"},
    )  # fmt: skip
    from evaluation_harness import _common

    _common.ROOT = tmp
    cs.ROOT = tmp
    A = HarnessAdapter(data)
    cs.set_adapter(A)
    arm = sorted(A.arms())[0]
    ask = {"arms": [arm], "item": ["i00"]}

    local = cs.item(ask)
    check(
        "control: a person's own inspector shows the output and the item's source",
        has_text(local["views"][arm]) and "source" in local,
        local,
    )
    cs.LIMITS["publish"] = ("outputs", "references")  # a deployment that publishes its outputs
    with _visibility.public_call(True):
        got = cs.item(ask)
    cs.LIMITS.clear()
    cs.LIMITS.update(saved)
    check(
        "an in-process public call, no hosts: the item route gives no source, labels or judge reasons",
        not ({"source", "labels", "verdicts"} & set(got)),
        sorted(got),
    )
    record("ds1", json.dumps({"dataset_id": "ds1", "text": "hidden", "items": []}))
    cs.LIMITS["publish"] = ("outputs", "references")
    with _visibility.public_call(True):
        got = cs.item(ask)
    cs.LIMITS.clear()
    cs.LIMITS.update(saved)
    check(
        "... and, the dataset being `text: hidden`, none of its text, though the deployment publishes outputs",
        not has_text(got),
        got,
    )
    record("ds1")
    with _visibility.public_call(True):
        got = cs.item(ask)
    check(
        "... and with nothing published the outputs are withheld, as for a server with hosts",
        got["views"][arm].get("kind") == "none" and not has_text(got),
        got,
    )
    with _visibility.public_call(True):
        sheet = cs.sheet({"dataset": ["ds1"]})
        csv_status = cs.sheet_csv("dataset=ds1")[0]
    check(
        "the sheet and its download are refused to the same call",
        "not served publicly" in sheet.get("error", "") and csv_status == 403,
        (sheet, csv_status),
    )

    # ── `hidden` fails closed ─────────────────────────────────────────────────────────────────────────────────────
    d = data / "datasets"
    record("broken", "{not json")
    record("open")
    record("shut", json.dumps({"dataset_id": "shut", "text": "hidden", "items": []}))
    local_answers = [_visibility.hidden(x, d) for x in ("ghost", "broken", "open", "shut")]
    with _visibility.public_call(True):
        public_answers = [_visibility.hidden(x, d) for x in ("ghost", "broken", "open", "shut")]
    check(
        "locally a dataset that is missing or unparseable is not hidden (nothing is claimed of it)",
        local_answers == [False, False, False, True],
        local_answers,
    )
    check(
        "on a public server one that is missing or unparseable is hidden, one that says it is open is not",
        public_answers == [True, True, False, True],
        public_answers,
    )
    check(
        "text_shown(public=True) holds the text of an unreadable dataset back",
        _visibility.text_shown("ghost", public=True) is False
        and _visibility.text_shown("ghost", public=False) is True
        and _visibility.text_shown(None, public=True) is True,
        None,
    )
finally:
    shutil.rmtree(tmp, ignore_errors=True)

sys.exit(summary())
