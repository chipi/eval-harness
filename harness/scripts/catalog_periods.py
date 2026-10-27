"""The home page's periods and its tiles' trends, measured from today.

The catalog is static and built only when it is deployed, so a period like "current week" cannot
be fixed at build time: the page carries the numbers per day (`home_data`) and the browser works
the period out from the viewer's date (catalog_assets/overview.js, `HOME`). `evh overview
--period` computes the same here, from the machine's date; the browser test checks they agree.

A flow tile (measured runs, billed, tokens) shows the period's total and its change against the
period before it of the same kind; a stock tile (goals, datasets, ...) shows the total so far and
how many are new in the period. Something with no date is in the total and never new.
"""

from __future__ import annotations

from datetime import date, timedelta

#: (key, its name, what a trend is against), in the order the picker shows them.
PERIODS = (
    ("7d", "last 7 days", "the 7 days before"),
    ("14d", "last 14 days", "the 14 days before"),
    ("30d", "last 30 days", "the 30 days before"),
    ("90d", "last 90 days", "the 90 days before"),
    ("week", "this week", "the same days last week"),
    ("lastweek", "last week", "the week before"),
    ("month", "this month", "the same days last month"),
    ("lastmonth", "last month", "the month before"),
    ("year", "this year", "the same days last year"),
    ("all", "all time", ""),
)
#: The period the page and `evh overview` open on.
DEFAULT = "14d"


def chip(label: str) -> str:
    """A period's name on its chip: "last 14 days" is "14 days" there."""
    return label[5:] if label.startswith("last ") and label[5:6].isdigit() else label


#: The tiles, in order and by subject: (what, page, "stock" | "flow", group). The page colours a
#: tile by its group (catalog.css), so the colour says what a tile is about, nothing more.
TILES = (
    ("goals", "goals.html", "stock", "goals"),
    ("datasets", "datasets.html", "stock", "data"),
    ("references", "references.html", "stock", "data"),
    ("configs", "datasets.html", "stock", "experiments"),
    ("arms", "datasets.html", "stock", "experiments"),
    ("metrics", "metrics.html", "stock", "experiments"),
    ("measured runs", "#activity", "flow", "work"),
    ("billed", "#spend", "flow", "work"),
    ("tokens", "#spend", "flow", "work"),
)


def _month_start(d: date, back: int = 0) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 - back, 12)
    return date(y, m + 1, 1)


def _month_end(d: date) -> date:
    return _month_start(d, -1) - timedelta(days=1)


def _same_day(first: date, day: int) -> date:
    """Day `day` of first's month, or the month's last day when it is shorter."""
    return min(first.replace(day=1) + timedelta(days=day - 1), _month_end(first))


def bounds(key: str, today: date, first: str = "") -> dict:
    """{"since", "until", "prev"}: ISO days, inclusive; prev is (since, until) or None."""
    iso = date.isoformat
    if key.endswith("d") and key[:-1].isdigit():
        n = int(key[:-1])
        s = today - timedelta(days=n - 1)
        return {
            "since": iso(s),
            "until": iso(today),
            "prev": (iso(s - timedelta(days=n)), iso(s - timedelta(days=1))),
        }
    if key == "week":
        s = today - timedelta(days=today.weekday())
        return {
            "since": iso(s),
            "until": iso(today),
            "prev": (iso(s - timedelta(days=7)), iso(today - timedelta(days=7))),
        }
    if key == "lastweek":
        s = today - timedelta(days=today.weekday() + 7)
        return {
            "since": iso(s),
            "until": iso(s + timedelta(days=6)),
            "prev": (iso(s - timedelta(days=7)), iso(s - timedelta(days=1))),
        }
    if key == "month":
        s, p = _month_start(today), _month_start(today, 1)
        return {"since": iso(s), "until": iso(today), "prev": (iso(p), iso(_same_day(p, today.day)))}
    if key == "lastmonth":
        s, p = _month_start(today, 1), _month_start(today, 2)
        return {"since": iso(s), "until": iso(_month_end(s)), "prev": (iso(p), iso(_month_end(p)))}
    if key == "year":
        s = date(today.year, 1, 1)
        last = date(today.year - 1, today.month, 28 if (today.month, today.day) == (2, 29) else today.day)
        return {"since": iso(s), "until": iso(today), "prev": (iso(date(today.year - 1, 1, 1)), iso(last))}
    if key == "all":
        return {"since": first[:10] or iso(today), "until": iso(today), "prev": None}
    raise ValueError(f"unknown period {key!r}: one of {', '.join(k for k, *_ in PERIODS)}")


def home_data(A, by_ds: dict, spend: list[dict], goals: list[dict], rounds: list[dict]) -> dict:
    """What the home page's tiles, charts and switch are drawn from, per day and in JSON:
    {"runs": {day: {dataset: measured runs}}, "spend": {day: {kind: [usd, tokens]}},
    "kinds": [...], "datasets": [...], "dates": {stock tile: [the day each one is new]},
    "first": the first day anything happened}."""
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415

    runs: dict = {}
    for ds, per in cb.activity_counts(by_ds, "").items():
        for day, n in per.items():
            runs.setdefault(day, {})[ds] = n
    out_spend: dict = {}
    for i, unit in enumerate(cb.SPEND_UNITS):
        for kind, per in cb.spend_by_day(spend, "", unit).items():
            for day, v in per.items():
                out_spend.setdefault(day, {}).setdefault(kind, [None, None])[i] = round(v, 6)

    def day(s) -> str:
        return (s or "")[:10]

    arm_first = {
        a["arm"]: min((day(r.get("created_at")) for r in a["run_list"] if r.get("created_at")), default="")
        for v in by_ds.values()
        for a in v["arms"]
    }

    def earliest(xs) -> str:
        return min((x for x in xs if x), default="")

    made = getattr(A, "dataset_created", None)
    ds_dates = {
        ds: day(made(ds) if callable(made) else "") or earliest(arm_first[a["arm"]] for a in v["arms"])
        for ds, v in by_ds.items()
    }
    configs: dict = {}
    for v in by_ds.values():
        for a in v["arms"]:
            k = tuple(a["arm"].rsplit("/", 2)[-2:])
            configs[k] = earliest([configs.get(k, ""), arm_first[a["arm"]]])
    # Every metric the metrics page lists (a goal can decide on one no arm records yet: undated).
    metrics: dict = dict.fromkeys(cb.metric_index(A, by_ds), "")
    for v in by_ds.values():
        for a in v["arms"]:
            for m in a["means"]:
                metrics[m] = earliest([metrics.get(m, ""), arm_first[a["arm"]]])
    goal_dates = []
    for g in goals:
        opened = [day(r.get("opened_at")) for r in rounds if r.get("goal") == g.get("goal_id")]
        on = [
            ds_dates.get(d.get("dataset_id", ""), "") for d in g.get("datasets") or [] if isinstance(d, dict)
        ]
        goal_dates.append(earliest(opened + on))
    stamps = [*runs, *out_spend] + [x for x in ds_dates.values() if x]
    return {
        "first": min(stamps, default=""),
        "datasets": sorted(by_ds),
        "kinds": [name for _, name in cb.SPEND_KINDS],
        "runs": runs,
        "spend": out_spend,
        "dates": {
            "goals": goal_dates,
            "datasets": list(ds_dates.values()),
            "configs": list(configs.values()),
            "arms": list(arm_first.values()),
            "references": [day(r.get("created_at")) for v in by_ds.values() for r in v["refs"]],
            "metrics": list(metrics.values()),
        },
    }


def _within(day: str, span) -> bool:
    return bool(day) and span[0] <= day <= span[1]


def _flow(data: dict, what: str, span) -> float:
    if what == "measured runs":
        return sum(sum(per.values()) for d, per in data["runs"].items() if _within(d, span))
    i = 0 if what == "billed" else 1
    return sum(x[i] or 0 for d, per in data["spend"].items() if _within(d, span) for x in per.values())


def trend(now: float, before: float | None) -> dict:
    """{"pct": change in percent or None, "text": how the trend reads}."""
    if before is None:
        return {"pct": None, "text": ""}
    if not before:
        return {
            "pct": None,
            "text": "new: nothing in the previous period" if now else "none in either period",
        }
    pct = (now - before) / before * 100
    arrow = "▲" if pct > 0 else "▼" if pct < 0 else "="
    return {"pct": pct, "text": f"{arrow} {abs(pct):.0f}%"}


def tiles(data: dict, key: str, today: date) -> list[dict]:
    """Each tile for a period: {"what", "href", "kind", "value", "new" (stock), "prev" and
    "trend" (flow), "spark" (flow: the value per day of the period)}."""
    b = bounds(key, today, data["first"])
    span = (b["since"], b["until"])
    days = []
    d = date.fromisoformat(span[0])
    while d.isoformat() <= span[1]:
        days.append(d.isoformat())
        d += timedelta(days=1)
    out = []
    for what, href, kind, group in TILES:
        t = {"what": what, "href": href, "kind": kind, "group": group}
        if kind == "stock":
            dates = data["dates"][what]
            t["value"] = len(dates)
            t["new"] = sum(1 for x in dates if _within(x, span))
        else:
            t["value"] = _flow(data, what, span)
            t["prev"] = _flow(data, what, b["prev"]) if b["prev"] else None
            t["trend"] = trend(t["value"], t["prev"])
            t["spark"] = [_flow(data, what, (x, x)) for x in days]
        out.append(t)
    return out


# -- the period on the other pages: one bar, a row's dates, its runs and spend ------------------


def bar(first: str, until: str) -> str:
    """The period chips and the line under them (catalog_assets/period.js fills both). Without
    the script the chips stay hidden and the line says the page shows all time."""
    import html  # noqa: PLC0415

    e = html.escape
    return (
        '<div class="period-switch"><div class="chips" id="period" role="group" aria-label="period" hidden>'
        + "".join(
            f'<button type="button" class="chip" data-period="{k}" aria-pressed="false" title="{e(label)}">'
            f"{e(chip(label))}</button>"
            for k, label, _ in PERIODS
        )
        + '</div><p class="period-note" id="period-span">'
        + (f"all time, {e(first)} to {e(until)}" if first else "")
        + "</p></div>"
    )


def row_chips(table_id: str, noun: str) -> str:
    """All / new in the period / active in the period, over a table of dated rows."""
    return (
        f'<p class="row-chips" data-for="{table_id}" role="group" aria-label="which {noun}">'
        f'<button type="button" class="chip" data-rows="all" aria-pressed="true">all {noun}</button>'
        '<button type="button" class="chip" data-rows="new" aria-pressed="false">new in period <b>0</b></button>'
        '<button type="button" class="chip" data-rows="active" aria-pressed="false">active in period <b>0</b></button>'
        "</p>"
    )


def arm_index(by_ds: dict) -> dict:
    """Every arm's number, the same on every page (rows name arms by it to count them)."""
    return {a: i for i, a in enumerate(sorted(a["arm"] for v in by_ds.values() for a in v["arms"]))}


def runs_of(arms: list[dict], idx: dict) -> list[list]:
    """[[day, arm number]] for every measured run of these arms (repeats one by one)."""
    return sorted(
        [(r.get("created_at") or "")[:10], idx[a["arm"]]]
        for a in arms
        for r in a["run_list"]
        if r.get("created_at") and not r.get("derived")
    )


def spend_of(spend: list[dict], keep) -> list[list]:
    """[[day, usd]] for the spend events `keep(event)` accepts."""
    return sorted(
        [(x.get("at") or "")[:10], round(float(x["usd"]), 6)]
        for x in spend
        if x.get("at") and isinstance(x.get("usd"), (int, float)) and keep(x)
    )


def first_dates(A, by_ds: dict) -> dict:
    """When each dataset and arm is new: {"datasets": {ds: day}, "arms": {arm: day}} (a
    dataset's `created_at`, else its first run; an arm's first run)."""
    arm_first = {
        a["arm"]: min(
            ((r.get("created_at") or "")[:10] for r in a["run_list"] if r.get("created_at")), default=""
        )
        for v in by_ds.values()
        for a in v["arms"]
    }
    made = getattr(A, "dataset_created", None)
    ds = {
        d: ((made(d) if callable(made) else "") or "")[:10]
        or min((arm_first[a["arm"]] for a in v["arms"] if arm_first[a["arm"]]), default="")
        for d, v in by_ds.items()
    }
    return {"datasets": ds, "arms": arm_first}


def in_period(rows: dict, key: str, today: date, first: str = "") -> dict:
    """{row: {"runs", "arms", "usd", and each "<x>_prev" or None}} for a period: what the page's
    in-period columns show (`evh <page> --period`)."""
    b = bounds(key, today, first)
    span, prev = (b["since"], b["until"]), b["prev"]

    def one(r, s):
        rs = [x for x in r.get("runs", []) if _within(x[0], s)]
        return len(rs), len({x[1] for x in rs}), sum(x[1] for x in r.get("usd", []) if _within(x[0], s))

    out = {}
    for k, r in rows.items():
        n, a, u = one(r, span)
        p = one(r, prev) if prev else (None, None, None)
        out[k] = {"runs": n, "arms": a, "usd": u, "runs_prev": p[0], "arms_prev": p[1], "usd_prev": p[2]}
    return out
