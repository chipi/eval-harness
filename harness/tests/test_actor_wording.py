"""Who acted, in words, wherever a record's actor is shown (RFC-027; the fleet's G6, 2026-11-18).

`evh migrate` gives every record made before 0.8.0 the actor `{"type": "unknown", "name": "before 0.8.0", "from":
"migration"}`: runs, baselines, references, label sets, rounds, dataset and model records. Shown as a name, it read
"promoted 2026-10-31 by before 0.8.0". Each text a command prints and each catalog page that shows an actor goes
through `_actor.said`, so a migrated record names nobody and a named one names its person.

    python tests/test_actor_wording.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation_harness._actor import said
from evaluation_harness._check import check, summary
from evaluation_harness.baselines_migrate import BEFORE

ANA = {"type": "person", "name": "ana", "from": "flag"}
BOT = {"type": "agent", "name": "triage-bot", "for": "ana", "from": "environment"}
NOBODY = "nobody recorded (before 0.8.0)"

check(
    "said: a migrated record names nobody; a person by name; an agent with whom it acted for; none or nameless '?'",
    said(BEFORE) == NOBODY
    and said(ANA) == "ana"
    and said(BOT) == "triage-bot for ana"
    and said(None) == "?"
    and said({"type": "person"}) == "?",
    [said(BEFORE), said(ANA), said(BOT), said(None), said({"type": "person"})],
)


def shown(name: str, text: str) -> None:
    check(
        f"{name}: a migrated record's actor is shown as nobody recorded, never as the name 'before 0.8.0'",
        NOBODY in text and "by before 0.8.0" not in text and "'name': 'before 0.8.0'" not in text,
        text[-500:],
    )


from evaluation_harness.ops.datasets import say_label_set  # noqa: E402

shown(
    "label-set-show",
    say_label_set(
        {"set": "g", "items": 3, "folder": "data/labels/d/g", "references": [], "record": {"actor": BEFORE}}
    ),
)

from evaluation_harness.ops.records import say_baselines, say_looks  # noqa: E402

shown(
    "baselines",
    say_baselines(
        {
            "baselines": [
                {
                    "goal": "g",
                    "dataset": "d",
                    "current": 1,
                    "promoted_from": "r1",
                    "promoted_at": "2026-10-31T13:19:25Z",
                    "actor": BEFORE,
                    "reason": "",
                    "history": [],
                }
            ]
        }
    ),
)
shown(
    "looks",
    say_looks(
        {
            "sets": [
                {
                    "dataset_id": "d",
                    "limit": 3,
                    "next": 2,
                    "next_level": 0.025,
                    "prior_use": 0,
                    "looks": [{"key": "k", "number": 1, "level": 0.05, "what": "unseal", "actor": BEFORE}],
                }
            ]
        }
    ),
)

from evaluation_harness.ops.prompts import say_prompt  # noqa: E402

shown(
    "prompt-show",
    say_prompt(
        {"versions": [{"n": 1, "id": "p@abc", "created_at": "2026-10-01", "actor": BEFORE, "runs": []}]}
    ),
)

from evaluation_harness import catalog_build  # noqa: E402

shown(
    "the catalog's baseline facts",
    catalog_build._baseline_facts(None, {"version": 1, "actor": BEFORE, "migrated": True}),  # type: ignore[arg-type]
)
check(
    "the catalog's baseline facts: a named actor is shown by name",
    "promoted by ana" in catalog_build._baseline_facts(None, {"version": 2, "actor": ANA}),  # type: ignore[arg-type]
)

sys.exit(summary())
