#!/usr/bin/env python3
"""Model records (RFC-020): loading, the weights facts the arms page reads, and what V18 catches.

python tests/test_models.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yaml
from evaluation_harness import _models
from evaluation_harness._check import check, summary


def write(base: Path, name: str, doc: dict) -> None:
    (base / "models").mkdir(exist_ok=True)
    (base / "models" / f"{name}.yaml").write_text(yaml.safe_dump(doc))


with tempfile.TemporaryDirectory() as td:
    data = Path(td)
    check("no records: no facts, no problems", _models.facts(data) == {} and _models.problems(data) == [])
    write(
        data,
        "gemma4-12b",
        {
            "model_id": "gemma4-12b",
            "kind": "llm",
            "aliases": ["gemma4:12b", "eval-gemma-12b"],
            "weights": "open",
            "licence": "Apache-2.0",
        },
    )
    write(data, "span", {"model_id": "span", "kind": "ml", "aliases": ["org/span"]})
    facts = _models.facts(data)
    check(
        "facts: every alias of a record with weights", set(facts) == {"gemma4:12b", "eval-gemma-12b"}, facts
    )
    check("facts: weights and licence", facts["gemma4:12b"] == {"weights": "open", "licence": "Apache-2.0"})
    check("by_alias finds the record", _models.by_alias(data)["org/span"]["model_id"] == "span")
    check("find by id", (_models.find(data, "gemma4-12b") or {}).get("kind") == "llm")
    check("a clean set has no problems", _models.problems(data) == [], _models.problems(data))
    write(
        data,
        "set",
        {
            "model_id": "set",
            "kind": "llm",
            "aliases": ["set:1b"],
            "settings": {"reasoning_effort": "none", "max_tokens": 1024},
        },
    )
    got = _models.resolve({"config_id": "a", "model_record": "set", "params": {"max_tokens": 2048}}, data)
    check(
        "resolve: the record's settings under the config's params, the config wins, model from the alias",
        got["params"] == {"reasoning_effort": "none", "max_tokens": 2048, "model": "set:1b"},
        got,
    )
    check(
        "resolve: a config naming no record is unchanged",
        _models.resolve({"params": {"x": 1}}, data) == {"params": {"x": 1}},
    )
    try:
        _models.resolve({"model_record": "nope"}, data)
        raised = False
    except ValueError:
        raised = True
    check("resolve: a record that does not exist is refused", raised)
    write(data, "other", {"model_id": "not-other", "kind": "llm", "aliases": ["gemma4:12b"]})
    probs = " | ".join(_models.problems(data))
    check("a file not named by its id is a problem", "is not the file's name" in probs, probs)
    check("an alias two records claim is a problem", "claimed by" in probs, probs)

sys.exit(summary())
