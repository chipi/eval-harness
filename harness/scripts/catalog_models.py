"""The Models page and a page per model (RFC-020, UXS-001).

    models.html          every model record: its build, where it runs, the settings chosen, whether it
                         was vetted, the arms and goals that use it, and what changed in the period
    models/<id>.html     one record: builds, the onboarding report, the settings history, its arms

`evh models` prints the same rows (`model_rows`). The records are data/models/<id>.yaml (_models.py); the
adapter's `models()` says which arms use each. The grouping and facets are catalog_assets/group.js, the
period parts the shared ones (catalog_periods.py, catalog_assets/period.js).
"""

from __future__ import annotations

import html
from datetime import date, timedelta

#: A build last checked longer ago than this is shown muted: it may no longer be what runs there.
STALE_DAYS = 30

#: The onboarding status a record's chip and `evh models --status` name, by the status it records.
STATUS = {"pass": "vetted", "check": "check"}
STATUS_WORDS = {"vetted": "vetted", "check": "to check", "none": "not onboarded"}
#: How an arm that uses a record says whether it was smoked (`evh arm-smoke`): pass, check or none.
SMOKE_WORDS = {"pass": "smoked", "check": "smoke: check", "none": "not smoked"}
SMOKE_BADGE = {k: f'<span class="role">{v}</span>' for k, v in SMOKE_WORDS.items()}


def e(s) -> str:
    """`s` escaped for HTML text and attributes."""
    return html.escape(str(s), quote=True)


def model_page(model_id: str) -> str:
    """The model's page, relative to the catalog root."""
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415

    return f"models/{cb.slug(model_id)}.html"


def model_link(model_id: str, label: str = "", up: str = "") -> str:
    """A model record's name, linked to its page."""
    return f'<a class="cell-link" href="{up}{model_page(model_id)}">{e(label or model_id)}</a>'


def entries(A) -> list[dict]:
    """The adapter's model records with their arms ([] when it has none)."""
    fn = getattr(A, "models", None)
    return (fn() if callable(fn) else None) or []


def arm_records(A) -> dict[str, dict]:
    """{arm id: the model record it uses}."""
    return {arm: x["record"] for x in entries(A) for arm in x["arms"]}


def smoke_of(rec: dict, config_id: str) -> str:
    """The latest arm smoke of a config that names the record: pass, check or none."""
    status = ((rec.get("smokes") or {}).get(config_id) or {}).get("status")
    return str(status) if status in ("pass", "check") else "none"


def status_of(rec: dict) -> str:
    """vetted (onboarding passed), check (it flagged something) or none."""
    return STATUS.get((rec.get("onboarding") or {}).get("status", ""), "none")


def hosting(rec: dict) -> str:
    """self-hosted when a build runs on a machine (it names a server, a device or just a place) and none
    has a provider id; hosted when a build has a provider id; "" for a record with no builds."""
    builds = rec.get("builds") or []
    if any(b.get("provider_id") for b in builds):
        return "hosted"
    return "self-hosted" if any(b.get("server") or b.get("device") or b.get("where") for b in builds) else ""


def identity(b: dict) -> str:
    return b.get("digest") or b.get("revision") or b.get("file_hash") or ""


def short(s: str, n: int = 12) -> str:
    return s.removeprefix("sha256:")[:n]


def build_text(b: dict) -> str:
    """A build as one short token: its tag or provider id, then the first characters of its digest,
    revision or hash."""
    return "@".join(x for x in (b.get("tag") or b.get("provider_id") or "", short(identity(b))) if x) or "—"


def build_diffs(rec: dict) -> list[str]:
    """Per build, "" when it is the record's build for its tag (the first one listed) or matches it, else
    what differs: the same tag on two machines with different digests, revisions or hashes."""
    first: dict = {}
    out = []
    for b in rec.get("builds") or []:
        ref = first.setdefault(b.get("tag") or b.get("provider_id") or "", b)
        mine, theirs = identity(b), identity(ref)
        out.append(
            f"{short(mine)} against {short(theirs)} on {ref.get('where')}"
            if mine and theirs and mine != theirs
            else ""
        )
    return out


def settings_line(rec: dict) -> str:
    """The chosen settings in a line: "reasoning off · 1024 tokens · 30 s" for an LLM, "cpu · fp32 · batch 1"
    for an ML model; "defaults" when none is chosen."""
    s = dict(rec.get("settings") or {})
    parts = []
    if rec.get("kind") == "llm":
        eff = s.pop("reasoning_effort", None)
        if eff is not None:
            parts.append("reasoning off" if str(eff) == "none" else f"reasoning {eff}")
        for key, tpl in (("max_tokens", "{} tokens"), ("call_timeout_s", "{} s")):
            if (v := s.pop(key, None)) is not None:
                parts.append(tpl.format(v))
    else:
        for key, tpl in (("device", "{}"), ("precision", "{}"), ("batch_size", "batch {}")):
            if (v := s.pop(key, None)) is not None:
                parts.append(tpl.format(v))
    parts += [f"{k} {v}" for k, v in s.items()]
    return " · ".join(parts) or "defaults"


def day(s) -> str:
    return str(s or "")[:10]


def first_day(rec: dict, arm_days: list[str]) -> str:
    """The day a record is new from: its earliest onboarding, history or build check, else its first arm's
    first run; "" when none is dated."""
    days = [
        day(x)
        for x in [
            (rec.get("onboarding") or {}).get("at"),
            *(h.get("at") for h in rec.get("history") or []),
            *(b.get("checked_at") for b in rec.get("builds") or []),
        ]
        if x
    ]
    return min(days or [d for d in arm_days if d], default="")


def stale(b: dict, today: date | None = None) -> bool:
    d = day(b.get("checked_at"))
    try:
        return date.fromisoformat(d) < (today or date.today()) - timedelta(days=STALE_DAYS)
    except ValueError:
        return False


def model_rows(A, by_ds: dict, arms_rows: list[dict] | None = None) -> list[dict]:
    """One row per model record: {"id", "name", "kind", "hosting", "weights", "licence", "status",
    "onboarded", "flags", "build", "builds", "differs", "settings", "arms" (the arm rows of
    catalog_arms.arm_rows), "goals", "best" ([(goal, dataset, rank, of)]), "record"}. `best` is the
    record's best arm's place on each goal's deciding measure among the arms the goal's decision weighs."""
    from evaluation_harness import catalog_arms as ca  # noqa: PLC0415

    found = entries(A)
    if not found:
        return []
    arm_rows = {r["arm"]: r for r in (arms_rows if arms_rows is not None else ca.arm_rows(A, by_ds))}
    ranks: dict = {}
    for c in ca.config_rows(A, by_ds, list(arm_rows.values()), []):
        ranks[c["config"]] = c["ranks"]
    out = []
    for x in found:
        rec = x["record"]
        arms = [arm_rows[a] for a in x["arms"] if a in arm_rows]
        best: dict = {}
        for cid in {r["config"] for r in arms}:
            for g, ds, i, n in ranks.get(cid, []):
                k = (g["goal_id"], ds)
                if k not in best or i < best[k][2]:
                    best[k] = (g, ds, i, n)
        goals: dict = {}
        for r in arms:
            if r["goal"]:
                goals.setdefault(r["goal"]["goal_id"], r["goal"])
        for g, *_ in best.values():
            goals.setdefault(g["goal_id"], g)
        onb = rec.get("onboarding") or {}
        diffs = build_diffs(rec)
        builds = rec.get("builds") or []
        out.append(
            {
                "id": rec["model_id"],
                "name": rec.get("name") or rec["model_id"],
                "kind": rec.get("kind") or "",
                "hosting": hosting(rec),
                "weights": rec.get("weights") or "",
                "licence": rec.get("licence") or "",
                "status": status_of(rec),
                "onboarded": day(onb.get("at")),
                "flags": list(onb.get("flags") or []),
                "build": list(dict.fromkeys(build_text(b) for b in builds)),
                "builds": builds,
                "diffs": diffs,
                "differs": any(diffs),
                "settings": settings_line(rec),
                "arms": arms,
                "goals": list(goals.values()),
                "best": sorted(best.values(), key=lambda t: (t[0]["goal_id"], t[1])),
                "record": rec,
            }
        )
    return out


def changes(rows: list[dict]) -> list[tuple]:
    """What changed for the models, newest first: (day, model id, what). Onboarding, then each entry of
    a record's history (what, from, to)."""
    out = []
    for r in rows:
        rec = r["record"]
        onb = rec.get("onboarding") or {}
        if onb.get("at"):
            where = f" on {onb['where']}" if onb.get("where") else ""
            out.append((day(onb["at"]), r["id"], f"onboarded{where}: {STATUS_WORDS[r['status']]}"))
        for h in rec.get("history") or []:
            moved = f" {h.get('from', '—')} → {h.get('to', '—')}" if "from" in h or "to" in h else ""
            out.append(
                (
                    day(h.get("at")),
                    r["id"],
                    f"{h.get('what')}{moved}" + (f" ({h['why']})" if h.get("why") else ""),
                )
            )
    return sorted(out, key=lambda t: t[0], reverse=True)


def onboarding_cell(r: dict) -> str:
    if r["status"] == "none":
        return '<span class="muted">not onboarded</span>'
    word = "pass" if r["status"] == "vetted" else "check"
    title = f' title="{e("; ".join(r["flags"]))}"' if r["flags"] else ""
    return f'<span{title}>{word}</span><br><small class="muted">{e(r["onboarded"])}</small>'


def best_cell(r: dict) -> str:
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415

    return (
        "<br>".join(
            f'{cb.goal_link(g)} <span class="nowrap">#{i} of {n}</span>' for g, _ds, i, n in r["best"]
        )
        or "—"
    )


def render_models(A, by_ds: dict, out, nav: list, arms_rows: list[dict] | None = None) -> None:
    """Write models.html and a page per model."""
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415
    from evaluation_harness import catalog_periods as cp  # noqa: PLC0415

    w = cb.window(A, by_ds)
    rows = model_rows(A, by_ds, arms_rows)
    today = date.today()
    trs = []
    for r in rows:
        where = "<br>".join(
            f'<span class="muted">{e(b["where"])}</span>' if stale(b, today) else e(b["where"])
            for b in r["builds"]
        )
        trs.append(
            {
                "key": r["id"],
                "data": {
                    "kind": r["kind"],
                    "where": r["hosting"] or "unknown",
                    "weights": r["weights"] or "unknown",
                    "status": r["status"],
                    "differs": "yes" if r["differs"] else "no",
                },
                "cells": [
                    model_link(r["id"], r["name"]) + f'<br><small class="muted">{e(r["kind"])}</small>',
                    ("<br>".join(f"<code>{e(b)}</code>" for b in r["build"]) or "—")
                    + (
                        ' <span class="role" title="a machine\'s build is not the record\'s">differs</span>'
                        if r["differs"]
                        else ""
                    ),
                    where or "—",
                    e(r["settings"]),
                    onboarding_cell(r),
                    f'<a href="arms.html?q={e(r["id"])}"><span data-v="{len(r["arms"])}">{len(r["arms"])}</span></a>'
                    if r["arms"]
                    else '<span data-v="0">0</span>',
                    "<br>".join(cb.goal_link(g) for g in r["goals"]) or "—",
                    best_cell(r),
                ],
            }
        )
    facets = [("kind", v, v) for v in ("llm", "ml", "baseline") if any(r["kind"] == v for r in rows)]
    facets += [("where", v, v) for v in ("self-hosted", "hosted") if any(r["hosting"] == v for r in rows)]
    facets += [
        ("weights", v, n)
        for v, n in (("open", "open weights"), ("proprietary", "proprietary"))
        if any(r["weights"] == v for r in rows)
    ]
    facets += [
        ("status", v, STATUS_WORDS[v])
        for v in ("vetted", "check", "none")
        if any(r["status"] == v for r in rows)
    ]
    if any(r["differs"] for r in rows):
        facets.append(("differs", "yes", "builds differ"))
    chips = "".join(
        f'<button type="button" class="chip" data-facet="{f}" data-value="{e(v)}" aria-pressed="false">{e(n)}</button>'
        for f, v, n in facets
    )
    n_vetted = sum(r["status"] == "vetted" for r in rows)
    n_check = sum(r["status"] == "check" for r in rows)
    body = cb.hero(
        "models",
        "Models",
        f"{len(rows)} models: {n_vetted} vetted, {n_check} to check, {len(rows) - n_vetted - n_check} not onboarded yet. "
        "A model is onboarded once (its build on every machine, what it can do, the settings chosen for it, a smoke "
        "behind them) and used by any experiment's arms.",
        cp.bar(w["first"], w["until"]),
    )
    if rows:
        body += cb.block(
            "01",
            "every model",
            f'<p class="row-chips facet-chips" data-for="models" role="group" aria-label="only"><span class="muted small">only</span>{chips}</p>'
            + cb.table(
                "models",
                ["model", "build", "where", "settings", "onboarding", "arms", "goals", "best result"],
                trs,
                "filter models (name, machine, goal…)",
                noun="model",
            ),
            "every",
        )
    else:
        body += cb.block(
            "01",
            "every model",
            '<p class="muted">No model record yet: <code>data/models/&lt;model_id&gt;.yaml</code>, then '
            "<code>evh model-onboard</code>.</p>",
            "every",
        )
    feed = changes(rows)
    body += cb.block(
        "02",
        "what changed in the period",
        '<p class="muted pempty" data-feed-empty="modelfeed" hidden>Nothing changed for a model in this period.</p>'
        + cb.table(
            "modelfeed",
            ["when", "model", "what"],
            [
                {
                    "made": d,
                    "cells": [f'<span data-v="{e(d)}">{e(d)}</span>', model_link(mid), e(what)],
                }
                for d, mid, what in feed
                if d
            ],
        ).replace('class="data sortable"', 'class="data sortable" data-period-feed', 1)
        if any(d for d, *_ in feed)
        else '<p class="muted">No onboarding or settings change is recorded yet.</p>',
    )
    cb.write(
        out,
        "models.html",
        cb.page(
            "Models",
            body,
            0,
            "models",
            (*cb.PERIOD_SCRIPTS(), "assets/group.js"),
            nav=nav,
            item=A.item_word,
            elsewhere=(("models", {}),),
        ),
    )
    for r in rows:
        render_model(A, r, out, nav)


def smoke_text(s: dict) -> str:
    """An arm smoke or onboarding as "pass 2026-10-31" (flags on hover), or "none"."""
    if not s:
        return '<span class="muted">none</span>'
    title = f' title="{e("; ".join(s.get("flags") or []))}"' if s.get("flags") else ""
    return f'<span{title}>{e(s.get("status", "?"))}</span> <small class="muted">{e(day(s.get("at")))}</small>'


def kv(d: dict) -> str:
    """A mapping on one line: "s 8.98 · tokens out 146", a nested mapping in brackets."""
    return " · ".join(
        f"{k.replace('_', ' ')} {f'({kv(v)})' if isinstance(v, dict) else v}" for k, v in d.items()
    )


def render_model(A, r: dict, out, nav: list) -> None:
    """Write one model's page."""
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415

    rec = r["record"]
    onb = rec.get("onboarding") or {}
    why = rec.get("settings_why") or {}
    settings = "<br>".join(
        f"<code>{e(k)}</code> {e(v)}" + (f' <small class="muted">{e(why[k])}</small>' if why.get(k) else "")
        for k, v in (rec.get("settings") or {}).items()
    )
    facts = [
        ("weights", e(r["weights"]) if r["weights"] else ""),
        ("licence", e(r["licence"])),
        ("aliases", " ".join(f"<code>{e(a)}</code>" for a in rec.get("aliases") or [])),
        ("settings", settings or "defaults"),
        (
            "onboarding",
            smoke_text(onb) + (f" on {e(onb['where'])}" if onb.get("where") else "")
            if onb
            else "not onboarded: <code>evh model-onboard</code>",
        ),
    ]
    dl = "".join(f"<dt>{k}</dt><dd>{x}</dd>" for k, x in facts if x)
    body = cb.hero(
        "model",
        e(r["name"]) + f' <span class="tag-base">{e(r["kind"])}</span>',
        "A model record: onboarded once for the project and used by any experiment's arms.",
        f'<dl class="kv">{dl}</dl><p class="btns"><a class="btn" href="../models.html">Every model</a></p>',
    )
    if r["builds"]:
        brs = []
        for b, diff in zip(r["builds"], r["diffs"], strict=True):
            run = " ".join(
                x
                for x in (
                    e(b.get("server") or b.get("device") or "—"),
                    f'<small class="muted">{e(kv(b["server_settings"]))}</small>'
                    if b.get("server_settings")
                    else "",
                )
                if x
            )
            ident = "<br>".join(
                f"<code>{e(b[k])}</code>"
                for k in ("tag", "provider_id", "digest", "revision", "file_hash", "quantization")
                if b.get(k)
            )
            brs.append(
                [
                    e(b["where"]),
                    run,
                    ident or "—",
                    f"differs: {e(diff)}" if diff else "yes",
                    f'<span data-v="{e(day(b.get("checked_at")))}"'
                    + (' class="muted"' if stale(b) else "")
                    + f">{e(day(b.get('checked_at'))) or '—'}</span>",
                ]
            )
        builds = cb.table(
            "builds", ["where", "server or device", "build", "matches the record", "checked"], brs
        )
    else:
        builds = '<p class="muted">No build is recorded for this model.</p>'
    body += cb.block("01", "builds", builds)
    if onb:
        rep = onb.get("report") or {}
        flags = list(onb.get("flags") or [])
        used: set = set()
        probes = []
        for k, v in rep.items():
            mine = [f for f in flags if k.replace("_", " ") in f.lower() or k in f.lower()]
            used.update(mine)
            text = kv(v) if isinstance(v, dict) else str(v)
            probes.append(
                [
                    e(k.replace("_", " ")),
                    f"<code>{e(text)}</code>" if k != "smoke" else f"<pre>{e(text)}</pre>",
                    e("; ".join(mine)) or "—",
                ]
            )
        rest = [f for f in flags if f not in used]
        inner = (
            f'<p class="small">{smoke_text(onb)}'
            + (f" on {e(onb['where'])}" if onb.get("where") else "")
            + "</p>"
            + (cb.table("probes", ["probe", "measurement", "flag"], probes) if probes else "")
            + (f'<p class="small">Other flags: {e("; ".join(rest))}</p>' if rest else "")
            + (
                f'<p class="small muted">What it can do: {e(kv(rec["capabilities"]))}</p>'
                if rec.get("capabilities")
                else ""
            )
        )
    else:
        inner = f'<p class="muted">Not onboarded yet: <code>evh model-onboard {e(r["id"])}</code>.</p>'
    body += cb.block("02", "onboarding", inner)
    hist = [
        [
            f'<span data-v="{e(day(h.get("at")))}">{e(day(h.get("at")))}</span>',
            e(
                f"{h.get('what')}: {h.get('from', '—')} → {h.get('to', '—')}"
                if "from" in h or "to" in h
                else h.get("what")
            ),
            e(h.get("why") or "—"),
        ]
        for h in sorted(rec.get("history") or [], key=lambda h: str(h.get("at")), reverse=True)
    ]
    body += cb.block(
        "03",
        "settings history",
        cb.table("history", ["when", "what changed", "why"], hist)
        if hist
        else '<p class="muted">No change of settings or build is recorded.</p>',
    )
    cfg_fn = getattr(A, "arm_config", None)
    ars = []
    for a in r["arms"]:
        params = ((cfg_fn(a["arm"]) if callable(cfg_fn) else {}) or {}).get("params") or {}
        over = [
            f"{k} {params[k]}"
            for k, v in (rec.get("settings") or {}).items()
            if k in params and params[k] != v
        ]
        sm = (rec.get("smokes") or {}).get(a["config"])
        ars.append(
            [
                cb.arm_link(a["arm"], a["label"], "../")
                + f'<br><small class="muted">{e(a["dataset"])}</small>',
                cb.goal_link(a["goal"], "../") if a["goal"] else "—",
                e(", ".join(over)) or "—",
                smoke_text(sm or {}),
                (cb.metric_link(a["measure"], "../") + f" {cb.fmt(a['value'])}")
                if a["measure"] and a["value"] is not None
                else "—",
            ]
        )
    body += cb.block(
        "04",
        "arms",
        cb.table("modelarms", ["arm", "goal", "settings it overrides", "arm smoke", "result"], ars)
        if ars
        else '<p class="muted">No arm uses this model yet: name it with <code>model_record</code> in a config.</p>',
    )
    cb.write(
        out,
        model_page(r["id"]),
        cb.page(
            r["name"],
            body,
            1,
            "models",
            nav=nav,
            item=A.item_word,
            elsewhere=(("models", {"model": r["id"]}),),
        ),
    )
