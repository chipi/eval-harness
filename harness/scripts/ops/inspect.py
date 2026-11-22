"""The inspector's per-item reads as operations (RFC-032 step 9): what the inspect command answered besides the comparison
(`comparison-show`): one item of the arms compared (`comparison-item`), two per-item scores crossed (`comparison-crosstab`),
every item's outputs (`comparison-items`) and a dataset's sheet (`sheet-show`). The sheet as a CSV to fill in is the command
`sheet-export`, which writes a file.

Each answer is what `--json` always gave, the printed lines and tables in order and the command's named values; the command
line prints them as it always printed them."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from evaluation_harness.ops import legacy
from evaluation_harness.ops.registry import Op

_I = "evaluation_harness.ops.inspect"
_RUNS = {
    "type": "string",
    "description": "the arms: arm ids, or system ids (looked up under label), comma-separated",
}
_LABEL = {
    "type": "string",
    "description": 'the label system ids are looked up under: "", silver, repeats, "rescored cd35dc1f", judged/<scorer> (default: the plain arm); `evh runs-list` shows what is there',
}
_WHERE = {
    "type": "array",
    "items": {"type": "string"},
    "description": "FIELD:VALUE or FIELD:LO..HI, keep only matching items",
}
_BASELINE = {"type": "string", "description": "the arm the others are compared to (default: the first)"}

OPS = (
    Op("comparison-item", "read", "one item of the arms compared: each arm's output beside the reference, the item itself, its fields and its labels",
       "GET", "/compare/item", f"{_I}:comparison_item", f"{_I}:say_blocks", output=legacy.BLOCKS, printer=f"{_I}:print_comparison_item",
       inputs={
           "runs": _RUNS,
           "item": {"type": "string", "description": "the item's id"},
           "baseline": _BASELINE,
           "label": _LABEL,
       }, required=("runs", "item"),
       public_dropped="an item's text and each arm's output are not served publicly"),
    Op("comparison-crosstab", "read", "two per-item scores of the arms crossed: per group, a table of item counts, A's values down, B's across, and the items off the diagonal",
       "GET", "/compare/crosstab", f"{_I}:comparison_crosstab", f"{_I}:say_blocks", output=legacy.BLOCKS, printer=f"{_I}:print_comparison_crosstab",
       inputs={
           "runs": _RUNS,
           "crosstab": {"type": "string", "description": "A,B: two per-item scores of the arms (numbers or true/false)"},
           "group": {"type": "string", "description": "group by this field of the run's prediction rows (a dotted path, e.g. _meta.gates); default: one group"},
           "group_match": {"type": "string", "description": "with group: the group is the first (...) of the regex found in the field's text, else the whole match; no match: none"},
           "label": _LABEL,
           "where": _WHERE,
           "max_ids": {"type": "integer", "description": "item ids listed per cell (default 8; -1 for all)"},
       }, required=("runs", "crosstab"), public_hidden=("group", "group_match")),
    Op("comparison-items", "read", "every item of the arms compared: each run's whole output and scores beside the reference and the labels; with disagree, only the items the runs decided differently from the first",
       "GET", "/compare/items", f"{_I}:comparison_items", f"{_I}:say_blocks", output=legacy.BLOCKS, printer=f"{_I}:print_comparison_items",
       inputs={
           "runs": _RUNS,
           "disagree": {"type": "boolean", "description": "only the items the runs decided differently from the first"},
           "baseline": {"type": "string", "description": "the arm the others are compared to: it goes first"},
           "label": _LABEL,
           "metric": {"type": "string", "description": "the measure (default: the arms' primary metric)"},
           "where": _WHERE,
           "max_chars": {"type": "integer", "description": "characters of each output the command prints (default 300, 0 = all); the answer keeps them whole"},
       }, required=("runs",), public_dropped="it shows recorded texts: the outputs, the references and the labels"),
    Op("sheet-show", "read", "a dataset's sheet: its items down, a column per run (the first is production's): what it wrote, its scores, the labels, the winner, the signals, and a footer per run",
       "GET", "/datasets/{dataset}/sheet", f"{_I}:sheet_show", f"{_I}:say_blocks", output=legacy.BLOCKS, printer=f"{_I}:print_sheet_show",
       inputs={
           "runs": _RUNS,
           "metric": {"type": "string", "description": "the measure, or SCORER/METRIC (default: the arms' primary metric)"},
           "label": _LABEL,
           "where": _WHERE,
           "by": {"type": "string", "description": "also count the shown rows by this field"},
           "disagree": {"type": "boolean", "description": "only the items where a run decided differently from the first"},
           "split": {"type": "boolean", "description": "only the items the candidates (the runs after the first) decided differently among themselves"},
           "wrong_against": {"type": "string", "description": "only the items where the first run's decision is not this label set's (SET or DATASET/SET)"},
           "new_vs": {"type": "string", "description": "only the items with a field value this dataset has never had"},
           "unlabelled": {"type": "boolean", "description": "only the items no label set labels yet"},
           "judge_disagrees": {"type": "boolean", "description": "only the items where a judge on a validation disagrees with the people's ratings (its term of the validation figure is under chance)"},
           "scores_only": {"type": "boolean", "description": "leave the runs' outputs out, keep their scores"},
       }, required=("runs",), public_dropped="the sheet shows the items' outputs and labels"),
)  # fmt: skip


def _adapter() -> Any:
    """The adapter the views read, set for the helpers of the inspector (catalog_serve) too."""
    from evaluation_harness import catalog_serve as cs  # noqa: PLC0415
    from evaluation_harness.ops.views import _adapter as shared  # noqa: PLC0415

    A = shared()
    if cs.A is not A:
        cs.set_adapter(A)
    return A


def _split(runs: str) -> list[str]:
    return [t.strip() for t in runs.split(",") if t.strip()]


def _comparison_item_body(runs: str, item: str, baseline: str | None = None, label: str = "") -> None:
    from evaluation_harness import catalog_views  # noqa: PLC0415

    catalog_views.item_view(
        _adapter(), SimpleNamespace(runs=runs, item=item, baseline=baseline, label=label or "")
    )


def _comparison_crosstab_body(
    runs: str,
    crosstab: str,
    group: str | None = None,
    group_match: str | None = None,
    label: str = "",
    where: list[str] | None = None,
    max_ids: int = 8,
) -> None:
    from evaluation_harness import _visibility, catalog_views  # noqa: PLC0415
    from evaluation_harness._common import die  # noqa: PLC0415

    if _visibility.public_env() and group:
        # A recorded field can hold text; the counts of two scores are numbers and ids.
        die("group shows recorded texts: not served publicly", "not-public")
    if group_match and not group:
        die("group_match: with group FIELD", "bad-argument")
    catalog_views._crosstab(
        _adapter(),
        SimpleNamespace(
            runs=runs,
            crosstab=crosstab,
            group=group,
            group_match=group_match,
            label=label or "",
            where=list(where or []),
            max_ids=max_ids,
        ),
    )


def _comparison_items_body(
    runs: str,
    disagree: bool = False,
    baseline: str | None = None,
    label: str = "",
    metric: str | None = None,
    where: list[str] | None = None,
    max_chars: int = 300,
) -> None:
    from evaluation_harness import _visibility, catalog_views  # noqa: PLC0415
    from evaluation_harness._common import die  # noqa: PLC0415

    if _visibility.public_env():
        die("items shows recorded texts: not served publicly", "not-public")
    catalog_views._items_out(
        _adapter(),
        SimpleNamespace(
            runs=runs,
            disagree=disagree,
            baseline=baseline,
            label=label or "",
            metric=metric,
            where=list(where or []),
            max_chars=max_chars,
        ),
    )


def _sheet_show_body(dataset: str, runs: str, **given: Any) -> int:
    from evaluation_harness import catalog_views  # noqa: PLC0415

    args = SimpleNamespace(
        dataset_id=dataset,
        runs=runs,
        metric=given.get("metric"),
        label=given.get("label") or "",
        where=list(given.get("where") or []),
        by=given.get("by"),
        disagree=bool(given.get("disagree")),
        split=bool(given.get("split")),
        wrong_against=given.get("wrong_against"),
        new_vs=given.get("new_vs"),
        unlabelled=bool(given.get("unlabelled")),
        judge_disagrees=bool(given.get("judge_disagrees")),
        scores_only=bool(given.get("scores_only")),
    )
    return catalog_views.sheet_view(_adapter(), args)


comparison_item, print_comparison_item = legacy.pair(_comparison_item_body)
comparison_crosstab, print_comparison_crosstab = legacy.pair(_comparison_crosstab_body)
comparison_items, print_comparison_items = legacy.pair(_comparison_items_body)
sheet_show, print_sheet_show = legacy.pair(_sheet_show_body)
say_blocks = legacy.say_blocks
