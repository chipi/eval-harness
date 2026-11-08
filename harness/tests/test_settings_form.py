#!/usr/bin/env python3
"""A setting as a form (UXS-004 §04): the save that keeps the file, over every setting this repository has.

  python tests/test_settings_form.py

- Every setting under data/ opens: its values pass its schema's check, and written back unchanged it is the same
  file, byte for byte.
- In each, one value changed (the first of each kind of value: text, number, yes/no): the file parses to exactly
  that change, every comment line is kept, and at most a handful of lines move.
- The patch keeps every line an edit does not touch, even where ruamel.yaml would write it differently (a long
  flow list, text pyyaml wrapped at 80 columns).
- set_values: a dotted key sets a nested field, makes the next item of a list, and unsets one.
"""

from __future__ import annotations

import difflib
import json
import os
import sys
from pathlib import Path

import yaml

os.environ["EVAL_STORE"] = "files"  # reads this repository's committed settings, which are files

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness import _common, _data_page, _store  # noqa: E402
from evaluation_harness import _settings_form as F  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402


def settings() -> list[str]:
    out = []
    for folder in _data_page.SETTINGS:
        d = _common.DATA / folder
        if _store.is_dir(d):
            out += [f"{folder}/{p.name}" for p in sorted(_store.glob(d, "*.yaml"))]
    if _store.is_file(_common.DATA / _data_page.POLICY):
        out.append(_data_page.POLICY)
    return out


def comments(text: str) -> list[str]:
    return sorted(ln.strip() for ln in text.splitlines() if ln.strip().startswith("#"))


def tweak(v: object) -> object:
    if isinstance(v, bool):
        return not v
    if isinstance(v, (int, float)):
        return v + 1
    if isinstance(v, str):
        return v + " edited"
    return None


def main() -> int:
    paths = settings()
    check("the repository has settings to open", len(paths) > 20, len(paths))
    unchecked, unequal, wrong, lost, wide = [], [], [], [], []
    edits = 0
    for norm in paths:
        before = _store.read_text(_common.DATA / norm)
        values = F.values_of(norm)
        if F.problems(norm, values):
            unchecked.append(norm)
        if F.text_for(norm, values, before) != before:
            unequal.append(norm)
        seen: set[type] = set()
        for key, val in F.flat(values):
            nv = tweak(val)
            if not key or nv is None or type(val) in seen:
                continue
            seen.add(type(val))
            changed = F.set_values(values, [(key, nv)], [])
            after = F.text_for(norm, changed, before)
            parsed = json.loads(after) if norm.endswith(".json") else yaml.safe_load(after)
            edits += 1
            if F.plain(parsed) != changed:
                wrong.append(f"{norm} {key}")
            elif not norm.endswith(".json") and comments(after) != comments(before):
                lost.append(f"{norm} {key}")
            else:
                moved = [ln for ln in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
                         if ln[:1] in "+-" and ln[:3] not in ("+++", "---")]  # fmt: skip
                if len(moved) > 8 and not norm.endswith(".json"):
                    wide.append(f"{norm} {key}: {len(moved)} lines")
    check(f"all {len(paths)} settings pass their schema's check as they are", not unchecked, unchecked[:5])
    check(
        f"all {len(paths)} settings, written back unchanged, are the same files byte for byte",
        not unequal,
        unequal[:5],
    )
    check(f"{edits} one-value edits parse to exactly the change", edits > 100 and not wrong, wrong[:5])
    check("every edit keeps every comment line", not lost, lost[:5])
    check("an edit moves at most a handful of lines (a YAML file)", not wide, wide[:5])

    ours = "a: 1   # one\nlist: [x,\n  y]\nb: two\n"
    base = "a: 1   # one\nlist: [x, y]\nb: two\n"
    check("patch: no edit gives the file back as it is", F.patch(ours, base, base) == ours)
    check("patch: an edit away from a reflowed list keeps the list as it was",
          F.patch(ours, base, base.replace("b: two", "b: three")) == ours.replace("b: two", "b: three"))  # fmt: skip
    check("patch: an edit inside the reflowed list takes it as ruamel writes it",
          F.patch(ours, base, base.replace("[x, y]", "[x, z]")) == "a: 1   # one\nlist: [x, z]\nb: two\n")  # fmt: skip

    # Edits that only add or only remove: a key, a list item, a group. Each changes the file by exactly that.
    src = "# a config\nconfig_id: a_v1   # its id\ndataset_id: d\nparams:\n  provider: echo\n  sentences: 1\n"
    for what, change, want in (
        ("a key added alone", lambda d: d.update(goal="g"), src + "goal: g\n"),
        ("a key added inside a group", lambda d: d["params"].update(noise=0.5), src + "  noise: 0.5\n"),
        ("a key removed alone", lambda d: d.pop("dataset_id"), src.replace("dataset_id: d\n", "")),
        (
            "a group added",
            lambda d: d.update(hypothesis={"against": "b"}),
            src + "hypothesis:\n  against: b\n",
        ),
    ):
        values = yaml.safe_load(src)
        change(values)
        got = F.text_for("configs/a.yaml", values, src)
        check(f"text_for: {what} changes the file by exactly that, comments kept", got == want, got)
    goal = "goal_id: g\ndatasets:\n  - dataset_id: a   # the first\n"
    values = yaml.safe_load(goal)
    values["datasets"].append({"dataset_id": "b"})
    got = F.text_for("goals/g.yaml", values, goal)
    check("text_for: a list item added alone", got == goal + "  - dataset_id: b\n", got)

    # A validate that does not reach its verdict decides nothing: the save is refused and the file left as it was
    # (advisor review, 2026-11-06: a crashed validate let every save through). subprocess.run is faked; the file is
    # a temporary one outside any project.
    import subprocess  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    real_run = subprocess.run
    tmp = Path(tempfile.mkdtemp(prefix="evh-guard-"))
    target = tmp / "g.yaml"

    def fake(*answers):
        seq = iter(answers)

        def run(*_a, **_k):
            x = next(seq, "")  # any further run: crashed too
            if x == "timeout":
                raise subprocess.TimeoutExpired("validate", 1)
            return subprocess.CompletedProcess(
                [], 0 if "PASSED" in x else 1, stdout=x, stderr="Traceback: KeyError"
            )

        return run

    outcomes = []
    for answers, start in (
        (("",), None),  # crashed before the write: nothing written
        (("timeout",), None),  # hung before the write
        (("\nVALIDATION PASSED", ""), "kept: 1\n"),  # crashed after the write: put back
    ):
        if start is None:
            target.unlink(missing_ok=True)
        else:
            target.write_text(start)
        subprocess.run = fake(*answers)
        try:
            F.guarded_write("goals/g.yaml", target, "changed: 2\n")
            kind = None
        except _data_page.Refused as exc:
            kind = exc.kind
        except Exception as exc:  # noqa: BLE001 - recorded: anything but a refusal is the failure
            kind = type(exc).__name__
        finally:
            subprocess.run = real_run
        outcomes.append((kind, target.read_text() if target.exists() else None, start))
    check("a validate that crashes or hangs refuses the save (kind failed); the file stays as it was",
          all(k == "failed" and now == was for k, now, was in outcomes), outcomes)  # fmt: skip

    v = {"params": {"a": 1}, "datasets": [{"dataset_id": "x"}]}
    out = F.set_values(
        v, [("params.b", True), ("datasets.1.dataset_id", "y"), ("context.usage", "u")], ["params.a"]
    )
    check("set_values: nested, the next list item, a missing group; unset",
          out == {"params": {"b": True}, "datasets": [{"dataset_id": "x"}, {"dataset_id": "y"}], "context": {"usage": "u"}}
          and v == {"params": {"a": 1}, "datasets": [{"dataset_id": "x"}]}, out)  # fmt: skip
    try:
        F.set_values(v, [("datasets.5.role", "test")], [])
        refused = False
    except _data_page.Refused:
        refused = True
    check("set_values: an item past the end of a list is refused", refused)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
