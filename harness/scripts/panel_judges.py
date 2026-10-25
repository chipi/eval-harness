"""Judge protocol + two implementations, for the judge panel (`evh judge`).

A judge takes a (run_id, item, dimensions) and returns a per-dimension
score on a 1-5 scale plus a USD cost. Two implementations ship:

- FakeJudge:   deterministic, no API, $0. Only with `--use-fake-judge`.
- HostedJudge: the model a judge spec names, called through `_providers` as every arm and
               judge-score judge is: `provider`, `model` and the prices in the panel's config,
               keys read as EVAL_JUDGE_<NAME> first, then <NAME>.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import hashlib
import json
from dataclasses import dataclass, field
from typing import Protocol

from evaluation_harness import _providers


@dataclass
class ItemScore:
    """One judge's verdict on one item."""

    run_id: str
    item_id: str
    per_dimension: dict[str, int] = field(default_factory=dict)  # dim → 1-5
    total_cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)


class Judge(Protocol):
    """A judge scores items along configured dimensions."""

    name: str

    def score(
        self,
        *,
        run_id: str,
        item_id: str,
        item_content: str,
        dimensions: list[str],
    ) -> ItemScore:
        """Return a verdict on one item."""
        ...


# ---------------------------------------------------------------------------


class FakeJudge:
    """Deterministic judge — no API. Returns a hashed score per (item, dim).

    Use for the demo and for unit tests of the harness's promotion /
    aggregation paths. Real judging happens via LLMJudge.
    """

    def __init__(self, name: str = "fake-judge"):
        self.name = name

    def score(
        self,
        *,
        run_id: str,
        item_id: str,
        item_content: str,
        dimensions: list[str],
    ) -> ItemScore:
        """Return a hashed deterministic verdict (1-5 per dimension)."""
        per_dim: dict[str, int] = {}
        for dim in dimensions:
            # Deterministic 1-5 from a hash of (run_id, item_id, dim).
            # Bias slightly toward 3-4 to look like real ratings.
            key = f"{run_id}|{item_id}|{dim}".encode()
            digest = hashlib.sha256(key).digest()
            per_dim[dim] = 2 + (digest[0] % 4)  # → 2, 3, 4, or 5
        return ItemScore(
            run_id=run_id,
            item_id=item_id,
            per_dimension=per_dim,
            total_cost_usd=0.0,
        )


# ---------------------------------------------------------------------------


class HostedJudge:
    """A hosted model scoring each item on the requested dimensions, 1-5, with one line of
    rationale (logged by nobody; the score is the answer, the rationale is for spot checks)."""

    INSTRUCTIONS = (
        "You are an evaluation judge. Score the candidate output on each "
        "requested dimension using a 1-5 scale (1 = poor, 5 = excellent). "
        'Return STRICT JSON only: {"scores": {"<dim>": <int>, ...}, '
        '"rationale": "<one sentence>"}. No prose outside the JSON.'
    )

    def __init__(self, spec: dict):
        self.name = spec["id"]
        self.params = {k: v for k, v in spec.items() if k != "id"}

    def score(
        self,
        *,
        run_id: str,
        item_id: str,
        item_content: str,
        dimensions: list[str],
    ) -> ItemScore:
        """Ask the model, and return its per-dimension 1-5 score and what the call cost."""
        prompt = (
            f"{self.INSTRUCTIONS}\n\nDimensions to score: {', '.join(dimensions)}\n\n"
            f"Candidate output:\n---\n{item_content}\n---"
        )
        try:
            c = _providers.complete(prompt, self.params, role="judge", max_tokens=512)
        except Exception as exc:  # noqa: BLE001 — any provider error is this item's error, recorded
            return ItemScore(run_id=run_id, item_id=item_id, errors=[f"api: {type(exc).__name__}: {exc}"])
        per_dim, error = self._parse(c.text, dimensions)
        return ItemScore(
            run_id=run_id,
            item_id=item_id,
            per_dimension=per_dim,
            # Unpriced is not free: the spec's prices are required, so None means no tokens came back.
            total_cost_usd=c.cost_usd if c.cost_usd is not None else 0.0,
            errors=[error]
            if error
            else ([] if c.cost_usd is not None else ["cost: the reply carried no token counts"]),
        )

    @staticmethod
    def _parse(text: str, dimensions: list[str]) -> tuple[dict[str, int], str | None]:
        t = text.strip()
        if t.startswith("```"):
            t = t.strip("`").removeprefix("json").strip()
        try:
            scores = (json.loads(t) or {}).get("scores") or {}
            per_dim = {d: int(scores[d]) for d in dimensions if d in scores}
        except (json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
            return {}, f"parse: {type(exc).__name__}: {exc}"
        return (per_dim, None) if per_dim else ({}, "parse: no scores in response")


#: What a judge spec in the panel's config must give: the same fields as a judge-score judge.
SPEC_REQUIRED = ("id", "provider", "model", "usd_per_mtok_in", "usd_per_mtok_out")


def build_judge(spec: dict | None, *, use_fake: bool = False) -> Judge | None:
    """The judge a panel config's `primary_judge` / `cross_judge` spec names, or None for none.

    `use_fake` gives a FakeJudge under the spec's id, and is the only way to get one: a hosted
    judge whose key is missing stops here, before any call, naming what to set.
    """
    if spec is None:
        return None
    if not isinstance(spec, dict) or any(spec.get(k) in (None, "") for k in SPEC_REQUIRED):
        raise SystemExit(
            f"a panel judge is a mapping with {', '.join(SPEC_REQUIRED)} "
            "(and optionally temperature, max_tokens, base_url, api_key_env); got " + repr(spec)
        )
    if use_fake:
        return FakeJudge(name=spec["id"])
    found = _providers.problems({k: v for k, v in spec.items() if k != "id"}, "judge")
    if found:
        raise SystemExit(
            f"judge {spec['id']}: " + "; ".join(found) + ". Nothing was called; `evh env-check` shows "
            "what each role reads, and --use-fake-judge runs the panel offline."
        )
    return HostedJudge(spec)
