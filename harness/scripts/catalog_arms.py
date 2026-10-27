"""The arms page: every arm, and every config across the datasets it ran on.

    arms.html   the table of every arm (grouped by dataset, config, model, provider or what it is
                scored against; a derived arm under the arm it came from), the configs, what changed
                in the period, and each goal's arms on its trade-off charts

`evh arms` prints the same rows (`arm_rows`, `config_rows`). The period parts are the shared ones
(catalog_periods.py, catalog_assets/period.js); the grouping, facets and comparison are
catalog_assets/arms.js.
"""

from __future__ import annotations

import html

#: Providers that bill per call over the network. An arm is hosted when it runs through one of
#: these or its config prices tokens; every other provider runs on the machine that ran the arm.
HOSTED_PROVIDERS = ("litellm", "openai", "anthropic", "openrouter", "together", "groq", "mistral", "gemini")

#: How a table of arms can be grouped: (key, the chip's name).
GROUPS = (
    ("", "no grouping"),
    ("dataset", "dataset"),
    ("config", "config"),
    ("model", "model"),
    ("provider", "provider"),
    ("scored", "scored against"),
)


def e(s) -> str:
    return html.escape(str(s), quote=True)


def _base(arm: str) -> str:
    """The runs directory an arm's id starts with (runs, runs-silver, runs-judged/<scorer>, ...)."""
    parts = arm.split("/")
    return "/".join(parts[:-2])


def arm_rows(A, by_ds: dict) -> list[dict]:
    """One row per arm, in the page's order (a derived arm right after the arm it came from):
    {"arm", "label", "dataset", "config", "model", "provider", "family", "tier", "local",
    "scored", "source", "derived", "roles", "goal", "measure", "value", "lower", "repeats",
    "cost", "latency", "first", "last"}."""
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415

    cfg = getattr(A, "arm_config", None)
    roles: dict = {}
    measure_of: dict = {}
    for r in cb.glance(A, by_ds):
        g, dec = r["goal"], r["dec"]
        for arm, word in (
            (r["baseline"], "baseline"),
            (r["leader"], "leader"),
            (r["recommended"], "recommended"),
        ):
            if arm:
                roles.setdefault(arm, []).append(word)
        for arm, rnd in (r.get("retired") or {}).items():
            roles.setdefault(arm, []).append(f"retired in {rnd}")
        if dec:
            for arm in dec["rows"]:
                measure_of.setdefault(arm, (g, r["measure"], r["lower"]))
                if arm not in dec["eligible"] and arm not in (r.get("retired") or {}):
                    roles.setdefault(arm, []).append("not eligible")
    out = []
    for ds, v in sorted(by_ds.items()):
        tiers = {x["id"]: x["tier"] for x in v["refs"]}
        arms = sorted(
            v["arms"], key=lambda a: (a["arm"].rsplit("/", 1)[-1], _base(a["arm"]) != "runs", a["arm"])
        )
        ids = {a["arm"] for a in arms}
        for a in arms:
            c = cfg(a["arm"]) if callable(cfg) else {}
            p = (c or {}).get("params") or {}
            cid = (c or {}).get("config_id") or a["arm"].rsplit("/", 1)[-1]
            source = f"runs/{ds}/{cid}"
            derived = next((r.get("derived") for r in a["run_list"] if r.get("derived")), "")
            g, m, lower = measure_of.get(a["arm"], (None, a["metric"], a["lower"]))
            value = (a["means"].get(m) or (None,))[0] if m else None
            dated = [r.get("created_at") or "" for r in a["run_list"] if r.get("created_at")]
            out.append(
                {
                    "arm": a["arm"],
                    "label": a["label"],
                    "dataset": ds,
                    "config": cid,
                    "model": p.get("model") or "",
                    "provider": p.get("provider") or "",
                    "family": p.get("family") or "",
                    "tier": p.get("price_tier") or "",
                    "local": not (
                        (p.get("provider") or "") in HOSTED_PROVIDERS or p.get("usd_per_mtok_in") is not None
                    ),
                    "scored": "judge" if a["judge"] else (tiers.get(a["reference"]) or "none"),
                    "source": source if source != a["arm"] and source in ids else "",
                    "derived": derived if source != a["arm"] else "",
                    "roles": roles.get(a["arm"], []),
                    "goal": g,
                    "measure": m,
                    "value": value,
                    "lower": lower,
                    "repeats": a["runs"],
                    "cost": (a["means"].get("cost_usd") or (None,))[0],
                    "latency": (a["means"].get("latency_ms") or (None,))[0],
                    "first": min(dated, default="")[:10],
                    "last": max(dated, default="")[:10],
                }
            )
    return out


def config_rows(A, by_ds: dict, rows: list[dict], spend: list[dict]) -> list[dict]:
    """One row per config across every dataset it ran on: {"config", "model", "provider",
    "family", "datasets", "arms", "usd", "ranks": [(goal, dataset, rank, of)]}. A rank is the
    config's best arm on the goal's deciding measure among the arms the goal's decision weighs."""
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415

    by_cfg: dict = {}
    for r in rows:
        by_cfg.setdefault(r["config"], []).append(r)
    arm_cfg = {r["arm"]: r["config"] for r in rows}
    usd: dict = {}
    for x in spend:
        if x.get("kind") == "arm" and isinstance(x.get("usd"), (int, float)) and x.get("arm") in arm_cfg:
            usd[arm_cfg[x["arm"]]] = usd.get(arm_cfg[x["arm"]], 0.0) + float(x["usd"])
    ranks: dict = {}
    for gr in cb.glance(A, by_ds):
        dec = gr["dec"]
        if not dec:
            continue
        vals = {a: (dec["rows"][a]["quality"]["value"]) for a in dec["rows"]}
        ordered = sorted(
            (a for a in vals if vals[a] is not None), key=lambda a: vals[a], reverse=not gr["lower"]
        )
        best: dict = {}
        for i, a in enumerate(ordered, 1):
            best.setdefault(arm_cfg.get(a, a.rsplit("/", 1)[-1]), i)
        for cid, i in best.items():
            ranks.setdefault(cid, []).append((gr["goal"], gr["dataset"], i, len(ordered)))
    out = []
    for cid, rs in sorted(by_cfg.items()):
        out.append(
            {
                "config": cid,
                "model": rs[0]["model"],
                "provider": rs[0]["provider"],
                "family": rs[0]["family"],
                "tier": rs[0]["tier"],
                "local": rs[0]["local"],
                "datasets": sorted({r["dataset"] for r in rs}),
                "arms": len(rs),
                "usd": usd.get(cid),
                "ranks": ranks.get(cid, []),
            }
        )
    return out


def render_arms(A, by_ds: dict, out, nav: list) -> None:
    """Write arms.html."""
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415
    from evaluation_harness import catalog_periods as cp  # noqa: PLC0415

    w, idx = cb.window(A, by_ds), cp.arm_index(by_ds)
    rows = arm_rows(A, by_ds)
    by_arm = {a["arm"]: a for v in by_ds.values() for a in v["arms"]}
    period_rows, trs = {}, []
    for r in rows:
        a = by_arm[r["arm"]]
        period_rows[r["arm"]] = {
            "runs": cp.runs_of([a], idx),
            "usd": cp.spend_of(
                w["spend"], lambda x, arm=r["arm"]: x.get("kind") == "arm" and x.get("arm") == arm
            ),
        }
        src = by_arm.get(r["source"]) if r["source"] else None
        moved = ""
        if src and r["measure"] and r["value"] is not None:
            before = (src["means"].get(r["measure"]) or (None,))[0]
            if before is not None:
                moved = f'<br><small class="muted">{e(r["derived"] or "derived")} from the arm above: {r["value"] - before:+.3f}</small>'
        latency = f"{r['latency']:.0f} ms" if r["latency"] else "—"
        badges = "".join(f'<span class="role">{e(x)}</span>' for x in dict.fromkeys(r["roles"]))
        attrs = {
            "dataset": r["dataset"],
            "config": r["config"],
            "model": r["model"] or "—",
            "provider": r["provider"] or "—",
            "scored": r["scored"],
            "where": "local" if r["local"] else "hosted",
            "tier": r["tier"] or "—",
        }
        trs.append(
            {
                "key": r["arm"],
                "made": r["first"],
                "cls": "fromarm" if r["source"] else "",
                "data": attrs,
                "cells": [
                    f'<input type="checkbox" class="pick" aria-label="pick {e(r["label"])}" data-arm="{e(r["arm"])}" data-ds="{e(r["dataset"])}">',
                    cb.arm_link(r["arm"], r["label"]) + moved,
                    cb.dataset_link(r["dataset"]),
                    (f"<code>{e(r['model'])}</code>" if r["model"] else "—")
                    + f'<br><small class="muted">{e(r["provider"] or "—")}{" · local" if r["local"] else ""}</small>',
                    e(r["scored"]),
                    badges or "—",
                    (
                        cb.metric_link(r["measure"])
                        + f' <span data-v="{r["value"]}">{cb.fmt(r["value"])}</span>'
                    )
                    if r["measure"] and r["value"] is not None
                    else "—",
                    f'<span data-v="{r["repeats"]}">{r["repeats"]}</span>',
                    f'<span data-v="{r["cost"] if r["cost"] is not None else ""}">{cb.fmt_amount(r["cost"], "usd") if r["cost"] else "—"}</span>',
                    f'<span data-v="{r["latency"] if r["latency"] is not None else ""}">{latency}</span>',
                    f'<span data-v="{e(r["last"])}">{e(r["last"]) or "—"}</span>',
                    f'<span data-flow="runs" data-line>{len(period_rows[r["arm"]]["runs"])}</span>',
                    '<span data-flow="usd">—</span>',
                ],
            }
        )
    cfgs = config_rows(A, by_ds, rows, w["spend"])
    crs = []
    for c in cfgs:
        mine = [by_arm[r["arm"]] for r in rows if r["config"] == c["config"]]
        key = f"c:{c['config']}"
        period_rows[key] = {
            "runs": cp.runs_of(mine, idx),
            "usd": cp.spend_of(
                w["spend"],
                lambda x, ids={a["arm"] for a in mine}: x.get("kind") == "arm" and x.get("arm") in ids,
            ),
        }
        crs.append(
            {
                "key": key,
                "made": min((r[0] for r in period_rows[key]["runs"]), default=""),
                "cells": [
                    f"<code>{e(c['config'])}</code>",
                    (f"<code>{e(c['model'])}</code>" if c["model"] else "—")
                    + f'<br><small class="muted">{e(c["provider"] or "—")}{" · local" if c["local"] else ""}</small>',
                    "<br>".join(cb.dataset_link(d) for d in c["datasets"]),
                    f'<span data-v="{c["arms"]}">{c["arms"]}</span>',
                    f'<span data-v="{c["usd"] or 0}">{cb.fmt_amount(c["usd"], "usd") if c["usd"] else "—"}</span>',
                    "<br>".join(
                        f'{cb.goal_link(g)} <span class="nowrap">#{i} of {n}</span>'
                        for g, _ds, i, n in c["ranks"]
                    )
                    or "—",
                    f'<span data-flow="runs" data-line>{len(period_rows[key]["runs"])}</span>',
                    '<span data-flow="usd">—</span>',
                ],
            }
        )
    # What changed for arms in the period: first runs, re-measurements, baselines, retirements.
    feed = []
    for r in rows:
        if r["first"]:
            feed.append(
                [
                    r["first"],
                    r["arm"],
                    "derived: " + (r["derived"] or "derived") if r["source"] else "first run",
                ]
            )
    for v in by_ds.values():
        for bl in v.get("baselines") or []:
            if bl.get("promoted_at") and bl.get("arm"):
                feed.append([bl["promoted_at"][:10], bl["arm"], "promoted as the baseline"])
    fn = getattr(A, "rounds", None)
    for rnd in fn() if callable(fn) else []:
        for x in rnd.get("retired") or []:
            day = (rnd.get("closed_at") or rnd.get("opened_at") or "")[:10]
            match = [
                r["arm"]
                for r in rows
                if r["config"] == x.get("config_id") and r["dataset"] == rnd.get("dataset_id")
            ]
            for arm in match[:1]:
                feed.append([day, arm, f"retired in {rnd['round_id']}: {x.get('reason', '')}"])
    feed.sort(key=lambda x: x[0], reverse=True)
    labels = {r["arm"]: r["label"] for r in rows}
    cb.write_period_rows(out, "arms", period_rows)

    # Each goal's arms on its trade-off charts, one goal at a time (the select picks).
    charts, options = [], []
    for gr in cb.glance(A, by_ds):
        if not gr["dec"]:
            continue
        svg = cb.tradeoff_charts(gr["dec"], labels, gr["measure"])
        if svg:
            k = cb.slug(f"{gr['goal']['goal_id']}-{gr['dataset']}")
            options.append(
                f'<option value="{k}">{e(gr["goal"].get("title") or gr["goal"]["goal_id"])} · {e(gr["dataset"])}</option>'
            )
            charts.append(f'<div data-tradeoff="{k}"{"" if not charts else " hidden"}>{svg}</div>')

    group_chips = "".join(
        f'<button type="button" class="chip" data-group-by="{k}" aria-pressed="{str(not k).lower()}">{e(n)}</button>'
        for k, n in GROUPS
    )
    facet_chips = "".join(
        f'<button type="button" class="chip" data-facet="{f}" data-value="{v}" aria-pressed="false">{e(n)}</button>'
        for f, v, n in (("where", "local", "local"), ("where", "hosted", "hosted"))
    ) + "".join(
        f'<button type="button" class="chip" data-facet="tier" data-value="{e(t)}" aria-pressed="false">{e(t)}</button>'
        for t in sorted({r["tier"] for r in rows if r["tier"]})
    )
    n_cfg = len(cfgs)
    body = cb.hero(
        "arms",
        "Arms and configs",
        f"{len(rows)} arms from {n_cfg} configs on {len(by_ds)} datasets. An arm is one config on one dataset "
        "scored one way; a rescored or judged arm sits under the arm it came from, with how its number "
        "moved. Pick arms on one dataset to open them in the inspector.",
        cp.bar(w["first"], w["until"]),
    )
    body += cb.block(
        "01",
        "every arm",
        '<div class="arm-tools">'
        f'<p class="row-chips group-chips" role="group" aria-label="group by"><span class="muted small">group by</span>{group_chips}</p>'
        f'<p class="row-chips facet-chips" role="group" aria-label="only"><span class="muted small">only</span>{facet_chips}</p>'
        "</div>"
        + cp.row_chips("arms", "arms")
        + '<p class="compare-bar" hidden><span data-picked>0 picked</span> <a class="btn small" data-compare href="#">open in the inspector</a> <button type="button" class="btn small" data-unpick>clear</button> <small class="muted" data-why></small></p>'
        + cb.table(
            "arms",
            [
                "",
                "arm",
                "dataset",
                "model · provider",
                "scored against",
                "role",
                "deciding measure",
                "repeats",
                "cost / item",
                "latency",
                "last run",
                "runs in period",
                "spend in period",
            ],
            trs,
            "filter arms (name, model, provider…)",
            period=True,
        ),
        "every",
    )
    body += cb.block(
        "02",
        "configs",
        '<p class="small muted">One row per config, across every dataset it ran on: where it ranks on each '
        "goal is its best arm among the arms the goal's decision weighs.</p>"
        + cp.row_chips("configs", "configs")
        + cb.table(
            "configs",
            [
                "config",
                "model · provider",
                "datasets",
                "arms",
                "spend",
                "rank on each goal",
                "runs in period",
                "spend in period",
            ],
            crs,
            "filter configs",
            period=True,
        ),
        "configs",
    )
    if feed:
        body += cb.block(
            "03",
            "what changed in the period",
            '<p class="muted pempty" data-feed-empty="armfeed" hidden>Nothing changed for an arm in this period.</p>'
            + cb.table(
                "armfeed",
                ["when", "arm", "what"],
                [
                    {
                        "made": d,
                        "cells": [
                            f'<span data-v="{e(d)}">{e(d)}</span>',
                            cb.arm_link(a, labels.get(a, a)),
                            e(w_),
                        ],
                    }
                    for d, a, w_ in feed
                ],
            ).replace('class="data sortable"', 'class="data sortable" data-period-feed', 1),
        )
    if charts:
        body += cb.block(
            "04",
            "cost and quality, by goal",
            f'<p><select id="tradeoff-goal" class="chip more" aria-label="goal">{"".join(options)}</select></p>'
            + "".join(charts),
        )
    cb.write(
        out,
        "arms.html",
        cb.page(
            "Arms",
            body,
            0,
            "arms",
            (*cb.PERIOD_SCRIPTS("arms"), "assets/arms.js"),
            nav=nav,
            item=A.item_word,
        ),
    )
