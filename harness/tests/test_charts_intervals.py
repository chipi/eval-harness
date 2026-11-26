"""The intervals chart on a stub leaderboard group (RFC-034 §2; the review of 2026-11-19): the margin is drawn from the
arm contenders are tested against, and only a significant difference is a filled dot (the leader is the hollow zero).

    python tests/test_charts_intervals.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation_harness import charts
from evaluation_harness._check import check, summary


def arm(label, leader=False, baseline=False, delta=None, ci=None, verdict="", ni=None):
    return {
        "arm": f"runs/d/{label}",
        "label": label,
        "leader": leader,
        "baseline": baseline,
        "contender": False,
        "vs_leader": {
            "delta": delta,
            "ci": ci,
            "verdict": verdict,
            "p": 0.01 if verdict.startswith("sig") else 0.4,
        },
        "noninferior": ni,
    }


def group(against: str) -> dict:
    ni = {"margin": 0.05, "against": against, "verdict": "non-inferior", "p": 0.01}
    return {
        "dataset": "d",
        "measure": "f1",
        "direction": "higher",
        "scored_against": "gold/d",
        "scorer": "",
        "arms": [
            arm("lead", leader=True),
            arm("base", baseline=True, delta=-0.1, ci=[-0.15, -0.05], verdict="significant: worse"),
            arm("close", delta=-0.12, ci=[-0.2, -0.04], verdict="not separated", ni=ni),
        ],
    }


def chart(against: str) -> dict:
    def stub(goal: str, dataset: str | None = None) -> dict:
        return group(against)

    charts._group = stub
    return charts.intervals("g")


def margin_at(svg: str) -> float | None:
    m = re.search(r"<title>the margin: ([^<]+)</title>", svg)
    return float(m.group(1).replace("−", "-")) if m else None


def filled(svg: str) -> dict[str, bool]:
    out = {}
    for paint, tip in re.findall(r'<circle [^>]*?(fill="[^"]+")[^>]*><title>([^<]+)</title>', svg):
        out[tip.split(":")[0]] = 'fill="none"' not in paint
    return out


c = chart("leader")
at = margin_at(c["svg"])
check(
    "tested against the leader: the margin line at minus the margin from 0, said so",
    at is not None and abs(at + 0.05) < 1e-9 and "from the leader" in c["caption"],
    (at, c["caption"][-200:]),
)
c = chart("baseline")
at = margin_at(c["svg"])
check(
    "tested against the promoted baseline: the margin line at the baseline's difference minus the margin, said so",
    at is not None
    and abs(at - (-0.1 - 0.05)) < 1e-9
    and "measured from the promoted baseline base" in c["caption"],
    (at, c["caption"][-260:]),
)
f = filled(c["svg"])
check(
    "only a significant difference is a filled dot: the leader (the zero) and a not-separated arm are hollow",
    f.get("base") is True and f.get("lead") is False and f.get("close") is False,
    f,
)

# The agreement chart (a scorer's controls): a judge pair with no τ (too few shared items) is an empty cell, never a
# 0, which would read as two judges that do not agree at all.
import json  # noqa: E402
import os  # noqa: E402
import tempfile  # noqa: E402

from evaluation_harness.model import scorers as model_scorers  # noqa: E402

os.environ.setdefault("EVAL_STORE", "files")
tmp = Path(tempfile.mkdtemp(prefix="evh-agree-", dir=str(Path.home() / ".cache" / "evh-tests")))
summary_path = tmp / "summary.json"
summary_path.write_text(
    json.dumps(
        {
            "controls": {"j1": {}, "j2": {}},
            "judge_agreement": {
                "j1~j2": {"n_items": 1, "arm_mean_spearman": None, "mean_item_tau": None},
                "j1~j3": {"n_items": 20, "arm_mean_spearman": 0.8, "mean_item_tau": 0.6},
            },
        }
    ),
    encoding="utf-8",
)
model_scorers.judging_sets_of = lambda scorer_id, data=None: ["s1"]
model_scorers.summary_file = lambda scorer_id, set_id, data=None: summary_path
ag = charts._judge_agreement("judge-v1")
titles = re.findall(r"<title>([^<]+)</title>", ag["svg"])
check(
    "agreement: a judge pair with no τ is an empty cell ('none'), a pair with one is drawn with its value",
    any(t.startswith("j1~j2") and t.endswith("none") for t in titles)
    and any("j1 and j3: τ per item 0.6" in t for t in titles)
    and not any("j1 and j2: τ per item" in t for t in titles),
    titles,
)
check(
    "agreement: the table's columns are the caption's words (reordered τ, re-asked τ, each other τ), not the code's",
    ag["columns"][1:3] == ["reordered τ", "re-asked τ"]
    and "each other τ" in ag["columns"]
    and all(w in ag["caption"] for w in ("reordered τ", "re-asked τ", "each other τ"))
    and not any("_tau" in c for c in ag["columns"]),
    ag["columns"],
)
import shutil  # noqa: E402

shutil.rmtree(tmp, ignore_errors=True)

sys.exit(summary())
