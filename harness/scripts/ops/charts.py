"""The evidence charts as one operation (RFC-034): `evh chart KIND`, `GET /api/v1/charts/{kind}`, an MCP tool. Its
answer is what the chart draws (`rows` under `columns`), its title and caption, and the drawing (`svg`); the command
prints the table and the caption, and writes the drawing to `--svg FILE` when asked."""

from __future__ import annotations

from typing import Any

from evaluation_harness.ops.registry import Op

_C = "evaluation_harness.ops.charts"

OPS = (
    Op("chart", "read", "an evidence chart (RFC-034): gain-cost, intervals, study-progress, rank-stability, latency, agreement, items or trend; what it draws as a table, its caption, and the drawing as SVG",
       "GET", "/charts/{kind}", f"{_C}:chart", f"{_C}:say_chart",
       inputs={
           "goal": {"type": "string", "description": "the goal (gain-cost, intervals, study-progress, latency, items, trend)"},
           "round": {"type": "string", "description": "a round of the goal (gain-cost)"},
           "study": {"type": "string", "description": "a study of the goal (gain-cost, study-progress)"},
           "dataset": {"type": "string", "description": "the dataset (rank-stability, agreement; for a goal's charts, one of its datasets)"},
           "scorer": {"type": "string", "description": "a judge scorer (agreement: its judges' controls)"},
           "model": {"type": "string", "description": "a code record (trend: its faithfulness per deployed period)"},
           "metric": {"type": "string", "description": "the measure (rank-stability; default: the runs' primary)"},
           "svg": {"type": "string", "x-file": "no", "x-metavar": "FILE", "description": "write the drawing to FILE (the command line only)"},
       }, tool_hidden=("svg",), public_hidden=("svg",)),
)  # fmt: skip


def chart(
    kind: str,
    goal: str | None = None,
    round: str | None = None,
    study: str | None = None,
    dataset: str | None = None,
    scorer: str | None = None,
    model: str | None = None,
    metric: str | None = None,
    svg: str | None = None,
) -> dict[str, Any]:
    """The chart, and its drawing written to `svg` when named."""
    from evaluation_harness import charts  # noqa: PLC0415

    out = charts.chart(
        kind, goal=goal, round=round, study=study, dataset=dataset, scorer=scorer, model=model, metric=metric
    )
    if svg:
        from pathlib import Path  # noqa: PLC0415

        from evaluation_harness import _store  # noqa: PLC0415

        _store.write_text(Path(svg), _standalone(out["svg"]))
        out = out | {"written": svg}
    return out


def _standalone(html: str) -> str:
    """The drawing as an SVG file: the first <svg> of the chart's figure, with its namespace and the colours its marks
    name as CSS variables given values (a file has no page to inherit them from)."""
    import re  # noqa: PLC0415

    m = re.search(r"<svg\b.*?</svg>", html, re.S)
    body = m.group(0) if m else "<svg></svg>"
    style = (
        "<style>svg{--ink:#0b0b0b;--ink-2:#4a4945;--muted:#66645e;--axis:#c3c2b7;--local:#d95926;--surface:#fff;"
        "--s1:#2a78d6;--s2:#e8551a;--s3:#179669;--s4:#b47a00;--s5:#e15187;--s6:#008300;--s7:#6250d6;--s8:#e34948;"
        "background:#fff;font-family:ui-monospace,monospace}text{font-size:12.5px;fill:var(--ink-2)}"
        ".t-ink{fill:var(--ink)}.t-muted{fill:var(--muted)}</style>"
    )
    return body.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1).replace(">", ">" + style, 1)


def say_chart(r: dict[str, Any]) -> str:
    """The chart as text: its title, its table, its caption, and where the drawing went."""
    cols = r["columns"]

    def cell(v: Any) -> str:
        if v is None:
            return "—"
        if isinstance(v, float):
            return f"{v:.4g}"
        if isinstance(v, dict):
            return ", ".join(f"{k}={x}" for k, x in v.items()) or "—"
        return str(v)

    rows = [cols] + [[cell(x.get(c)) for c in cols] for x in r["rows"]]
    w = [max(len(row[i]) for row in rows) for i in range(len(cols))]
    table = ["  " + "  ".join(c.ljust(w[i]) for i, c in enumerate(row)).rstrip() for row in rows]
    out = [r["title"], *table, "", r["caption"]]
    if r.get("written"):
        out.append(f"the drawing: {r['written']}")
    return "\n".join(out)
