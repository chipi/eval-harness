"""A reader made to work a fact out itself, for test_reader_agreement.py to catch (RFC-041, PLAN 0.8.1 R3).

Each stub is what a reader looked like before the fact had one source: the catalog's `direction` answering from the name
table (the podcast project's `wer`), `runs_of_arm` keeping the runs of another reference (the averaging of silver with gold).
`apply(name)` patches the running process; `_reader_proc.py` applies one before a reader runs. A check that passes with
a stub applied checks nothing about that fact.
"""

from __future__ import annotations

from collections.abc import Callable


def catalog_direction_by_name() -> None:
    """The catalog's adapter says which way is better from the metric's name only: no goal, no declared direction, no
    declared kind (the answer `_common` gave every reader before `_runs.direction`)."""
    from evaluation_harness import _common, catalog_adapter  # noqa: PLC0415

    def direction(self: object, metric: str, dataset: str | None = None) -> str:
        if _common.lower_is_better(metric):
            return "lower"
        return "neutral" if _common.is_descriptive(metric) else "higher"

    catalog_adapter.HarnessAdapter.direction = direction  # type: ignore[method-assign]


def runs_keep_other_references() -> None:
    """An arm's runs are all the runs of its system, whichever reference each was scored against: the arm of a run before
    its dataset had a reference is averaged with the runs after (`model.runs.runs_of_arm` left them out)."""
    from evaluation_harness.model import runs  # noqa: PLC0415

    runs.runs_of_arm = lambda found: (list(found), [])  # type: ignore[assignment]


STUBS: dict[str, Callable[[], None]] = {
    "catalog-direction-by-name": catalog_direction_by_name,
    "runs-keep-other-references": runs_keep_other_references,
}


def apply(name: str) -> None:
    STUBS[name]()
