"""The Scorers page and a page per judge scorer (RFC-032 step 8, from step 7).

    scorers.html         every judge scorer: its mode, its judges, whether it is validated, the judged scores it
                         made and how many of them with another version of it
    scorers/<id>.html    one scorer: its judges and their models, its validation, the people's checks of its
                         judges, the judging sets and summaries of its passes, and the arms it judged

`evh scorer-list` and `evh scorer-show` answer the same (model/scorer_views, read through the adapter's data
directory: a deployment's copy of the data has no other). Counts only: a page never carries a judge's reply, a
verdict or an item's text, so a judge's outputs on a dataset marked `text: hidden` are on no page, and a deployment's
copy, which holds no verdicts of a hidden dataset and no people's checks, shows what it holds.
"""

from __future__ import annotations

import html


def e(s) -> str:
    """`s` escaped for HTML text and attributes."""
    return html.escape(str(s), quote=True)


def scorer_page(scorer_id: str) -> str:
    """The scorer's page, relative to the catalog root."""
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415

    return f"scorers/{cb.slug(scorer_id)}.html"


def entries(A) -> list[dict]:
    """The adapter's judge scorers, as `evh scorer-list` lists them ([] when it has none)."""
    fn = getattr(A, "scorers", None)
    return (fn() if callable(fn) else None) or []


def page_ids(A) -> set[str]:
    """The scorers that have a page of their own: those that could be read."""
    return {x["scorer"] for x in entries(A) if "judged_scores" in x}


def judges_text(s: dict) -> str:
    """The judges of a scorer as one cell: each judge and the model it is called as."""
    return (
        "<br>".join(f"<code>{e(j['judge'])}</code> {e(j['model'] or '')}".rstrip() for j in s["judges"])
        or "no judges"
    )


def version_cell(n: int, other: int) -> str:
    """How many judged scores were made, and how many of them with another version of the scorer."""
    return f'<span data-v="{n}">{n}</span>' + (
        f'<br><small class="muted">{other} with another version</small>' if other else ""
    )


def validated_cell(s: dict) -> str:
    """Whether the scorer is validated, as a table cell."""
    return "yes" if s.get("validated") else '<span class="muted">no</span>'


def render_scorers(A, by_ds: dict, out, nav: list) -> None:
    """Write scorers.html and a page per scorer."""
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415

    rows = []
    for s in entries(A):
        sid = s["scorer"]
        if "judged_scores" not in s:  # a record that does not read: named, not shown
            rows.append(
                [
                    f"<b>{e(sid)}</b>",
                    "—",
                    '<span class="muted">does not read</span>',
                    "—",
                    "—",
                    f'<small class="muted">{e(s.get("problem") or "")}</small>',
                ]
            )
            continue
        rows.append(
            [
                f'<a class="cell-link" href="{scorer_page(sid)}">{e(sid)}</a>'
                + (
                    f'<br><small class="muted">supersedes {scorer_link(s["supersedes"])}</small>'
                    if s.get("supersedes")
                    else ""
                ),
                e(s["mode"]),
                judges_text(s),
                validated_cell(s),
                version_cell(s["judged_scores"], s["other_version"]),
                f'<small class="muted">{e(s["problem"])}</small>' if s.get("problem") else "",
            ]
        )
    body = cb.hero(
        "scorers",
        "Scorers",
        "The judges that score arms' outputs, and what each one made. A scorer names its judges (two vendors at "
        "least), its protocol and the people's check it was validated by; one that has made judged scores is never "
        "changed: a new version is a new scorer (<code>supersedes</code>), since every judged score records the "
        "scorer it was made with.",
    )
    body += cb.block(
        "01",
        "judge scorers",
        cb.table(
            "scorers",
            ["scorer", "mode", "judges", "validated", "judged scores", "note"],
            rows,
            "filter scorers",
        )
        if rows
        else '<p class="muted">No judge scorers yet: <code>evh scorer-new &lt;id&gt; --set dataset_id=&lt;dataset&gt; '
        "--set judges.0.id=&lt;judge&gt; …</code>, then <code>evh judge-score</code> judges arms with it.</p>",
    )
    cb.write(
        out,
        "scorers.html",
        cb.page("Scorers", body, 0, "scorers", nav=nav, item=A.item_word, elsewhere=(("scorer-list", {}),)),
    )
    for s in entries(A):
        if "judged_scores" in s:
            render_scorer(A, s["scorer"], by_ds, out, nav)


def scorer_link(scorer_id: str, up: str = "") -> str:
    """A scorer's id, linked to its page when it has one."""
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415

    return cb.scorer_link(scorer_id, up, code=False)


def _validation(v: dict) -> str:
    block = v["validation"].get("block") or {}
    facts = [
        ("validated", "yes" if v["validation"]["validated"] else "no"),
        ("against", e(block.get("what") or "")),
        ("on", e(" · ".join(str(x) for x in (block.get("dataset_id"), block.get("metric")) if x))),
        ("how it differs from this use", e(block.get("differs_from_this_use") or "")),
    ]
    out = '<dl class="kv">' + "".join(f"<dt>{k}</dt><dd>{x}</dd>" for k, x in facts if x) + "</dl>"
    problems = v["validation"]["problems"]
    if problems:
        out += "<ul>" + "".join(f"<li>{e(p)}</li>" for p in problems) + "</ul>"
    return out


def _checks(v: dict) -> str:
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415

    if not v["checks"]:
        return (
            '<p class="muted">No check of the judges by people is kept in this data (a deployment\'s copy of the '
            "data does not carry them).</p>"
        )
    rows = [
        [
            f"<code>{e(c['source'])}</code>",
            e(c.get("citation") or "—"),
            f'<span data-v="{c.get("articles") or 0}">{c.get("articles") if c.get("articles") is not None else "—"}</span>',
            ", ".join(f"<code>{e(j['judge'])}</code>" for j in c["judges"]) or "—",
            f'<span data-v="{c["records"]}">{c["records"]}</span>',
            "yes"
            if c.get("current")
            else '<span class="muted">another version</span>'
            if c.get("scorer_sha256")
            else '<span class="muted">not recorded</span>',
        ]
        for c in v["checks"]
    ]
    return cb.table(
        "checks", ["source", "citation", "articles", "judges", "records", "of this version"], rows
    )


def _sets(A, v: dict, by_ds: dict) -> tuple[str, str]:
    """The judging sets table and the summaries table of the scorer."""
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415

    sets, sums = [], []
    for js in v["judging_sets"]:
        ds = js.get("dataset")
        sets.append(
            [
                f"<code>{e(js['set'])}</code>",
                (cb.dataset_link(ds, "../") if ds in by_ds else f"<code>{e(ds)}</code>") if ds else "—",
                f'<span data-v="{js["arms"]}">{js["arms"]}</span>',
                f'<span data-v="{js["items"]}">{js["items"]}</span>',
                f'<span data-v="{js["verdicts"]}">{js["verdicts"]}</span>',
                f'<span data-v="{js["judged_scores"]}">{js["judged_scores"]}</span>',
            ]
        )
        sm = js.get("summary")
        if sm:
            sums.append(
                [
                    f"<code>{e(js['set'])}</code>",
                    e(sm.get("label") or "—"),
                    "yes" if sm.get("validated") else "no",
                    "yes" if sm.get("partial") else "no",
                    f'<span data-v="{sm.get("items_scored") or 0}">{sm.get("items_scored") if sm.get("items_scored") is not None else "—"}</span>',
                    "this version" if sm.get("current") else '<span class="muted">another version</span>',
                ]
            )
    first = (
        cb.table(
            "judgingsets",
            ["judging set", "dataset", "arms", "items", "verdicts", "judged scores"],
            sets,
        )
        if sets
        else '<p class="muted">This scorer has judged no judging set yet: <code>evh judge-score</code>.</p>'
    )
    second = (
        cb.table(
            "summaries",
            ["judging set", "label", "validated", "partial", "items scored", "scored with"],
            sums,
        )
        if sums
        else '<p class="muted">No summary of a pass is kept.</p>'
    )
    return first, second


def _arms(A, v: dict, by_ds: dict) -> str:
    """The arms this scorer judged, each with how many of its judged scores were made with another version."""
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415

    made = {s["run"]: s for s in v["runs"]}
    rows = []
    for ds, x in sorted(by_ds.items()):
        for a in x["arms"]:
            if a.get("judge") != v["scorer"]:
                continue
            mine = [made[r["run_id"]] for r in a["run_list"] if r.get("run_id") in made]
            other = sum(1 for m in mine if not m["current"])
            rows.append(
                [
                    cb.arm_link(a["arm"], a["label"], "../"),
                    cb.dataset_link(ds, "../"),
                    f'<span data-v="{len(a["run_list"])}">{len(a["run_list"])}</span>'
                    + (f'<br><small class="muted">{other} with another version</small>' if other else ""),
                ]
            )
    return (
        cb.table("judgedarms", ["arm", "dataset", "judged scores"], rows, "filter arms")
        if rows
        else '<p class="muted">No arm in this catalog was judged by this scorer yet.</p>'
    )


def render_scorer(A, scorer_id: str, by_ds: dict, out, nav: list) -> None:
    """Write scorers/<id>.html."""
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415

    v = A.scorer(scorer_id)
    entry = next(x for x in entries(A) if x["scorer"] == scorer_id)
    ds = entry.get("dataset")
    facts = [
        ("mode", e(entry["mode"])),
        ("dataset", cb.dataset_link(ds, "../") if ds and ds in by_ds else e(ds or "")),
        ("supersedes", scorer_link(entry["supersedes"], "../") if entry.get("supersedes") else ""),
        ("judged scores", version_cell(v["judged_scores"], v["other_version"])),
        ("version", f"<code>{e(v['sha256'][:12])}</code>" if v.get("sha256") else ""),
        ("it does not read", e(v.get("problem") or "")),
    ]
    body = cb.hero(
        "scorers",
        e(scorer_id),
        f"A {e(entry['mode'])} judge scorer. <code>evh scorer-show {e(scorer_id)}</code> prints the same.",
        f'<dl class="kv">{"".join(f"<dt>{k}</dt><dd>{x}</dd>" for k, x in facts if x)}</dl>'
        '<p class="btns"><a class="btn" href="../scorers.html">Every scorer</a></p>',
    )
    judges = [
        [
            f"<code>{e(j['judge'])}</code>",
            e(j.get("model") or "—"),
            e(j.get("family") or "—"),
            f"<code>{e(j['system'])}</code>" if j.get("system") else "—",
            f"<code>{e(j['fingerprint'])}</code>" if j.get("fingerprint") else "—",
        ]
        for j in v["judges"]
    ]
    body += cb.block(
        "01",
        "judges",
        cb.table("judges", ["judge", "model", "vendor family", "system", "fingerprint"], judges)
        if judges
        else '<p class="muted">No judges.</p>',
    )
    body += cb.block("02", "validation", _validation(v))
    body += cb.block("03", "the people's checks", _checks(v))
    sets, sums = _sets(A, v, by_ds)
    body += cb.block("04", "judging sets", sets)
    body += cb.block("05", "summaries", sums)
    body += cb.block("06", "arms it judged", _arms(A, v, by_ds))
    cb.write(
        out,
        scorer_page(scorer_id),
        cb.page(scorer_id, body, 1, "scorers", nav=nav, item=A.item_word, elsewhere=(("scorer-list", {}),)),
    )
