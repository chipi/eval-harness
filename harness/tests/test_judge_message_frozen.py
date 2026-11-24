"""A judge's message with no reasons asked is the one it was validated with, byte for byte (RFC-034 §5, §7; the review
of 2026-11-19: the test compared the message with and without reasons, never with what was sent).

Every committed verdict stores the sha256 of the message its judge was sent (`prompt_sha256`). For this repository's
committed judging sets (grade and pick, made before reasons existed, so `explain` absent), the message today's
`message_for` builds from the committed set, its scorer's prompt, the materialized articles and the arms' stored
outputs hashes to what was sent, on a sample of verdicts of each pass. A change to the message a validated judge
reads (a word, a space, the reason's request leaking in) fails here.

    python tests/test_judge_message_frozen.py   (needs data/materialized/cnn_dailymail_200: CI runs it after
    `examples/reproduce.py data summarization`, in rerun.yml)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation_harness import judge_score as js
from evaluation_harness._check import check, summary
from evaluation_harness.model import runs as model_runs

DATA = Path(__file__).resolve().parents[1] / "data"
SAMPLE = 3  # verdicts per pass and judging set

for scorer_id in ("judge-summ-v1", "judge-summ-pick-v1"):
    sc = js.load_scorer(DATA / "scorers" / f"{scorer_id}.yaml", DATA)
    base = js.prompt_text(sc)
    for set_dir in sorted((DATA / "judge-verdicts" / scorer_id).iterdir()):
        man = json.loads((DATA / "judging-sets" / f"{set_dir.name}.json").read_text(encoding="utf-8"))
        items = {it["item_id"]: it for it in man["items"]}
        ds = man["dataset_id"]
        mat = DATA / "materialized" / ds
        verdicts = sorted(set_dir.glob("*/*.json"))
        sample = []
        for p in ("primary", "position", "noise"):
            sample += [v for v in verdicts if f".{p}.b" in v.name][:SAMPLE]
        need = {json.loads(v.read_text(encoding="utf-8"))["item_id"] for v in sample}
        articles = {i: (mat / f"{i}.txt").read_text(encoding="utf-8", errors="replace") for i in need}
        arms = [{"run": a["run"], "dir": str(model_runs.run_dir(a["run"], data=DATA))} for a in man["arms"]]
        outputs = {
            a["config_id"]: js.read_outputs(arm, sorted(need))
            for a, arm in zip(man["arms"], arms, strict=True)
        }
        bad = []
        for v in sample:
            rec = json.loads(v.read_text(encoding="utf-8"))
            msg = js.message_for(
                man, base, articles, outputs, items[rec["item_id"]], rec["pass"], rec["block"]
            )
            if js._sha(msg) != rec["prompt_sha256"]:
                bad.append(v.name)
        check(
            f"{scorer_id} on {set_dir.name}: today's message for {len(sample)} committed verdict(s) (each pass) "
            "hashes to what the judge was sent",
            "explain" not in man and len(sample) >= 3 and not bad,
            bad[:3],
        )

sys.exit(summary())
