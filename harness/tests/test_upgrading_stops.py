#!/usr/bin/env python3
"""Every change a release's CHANGELOG says can stop a run has a line in UPGRADING's section for that release.

    python tests/test_upgrading_stops.py                # the check
    python tests/test_upgrading_stops.py --candidates   # older bullets that look like one (a report, never a failure)

A CHANGELOG bullet is marked by the phrase `can stop a run that worked`; UPGRADING's "From X to Y" section for that
release names each with a bullet whose bold lead carries the same phrase, so a reader who pins the release finds it where
they look for what to do. The count is what is checked, not the pairing: a section with fewer such leads than the release
has marked bullets fails, naming the bullets.

0.8.2 was released before the marker: STOPS_BEFORE_MARKER names its two bullets by their lead (0.8.2's notes are
published and are not rewritten). Older releases are not held to it; `--candidates` lists the bullets of theirs whose words
(refuses, stops the run, ...) say they might be one, for someone to decide.
"""

import re
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

MARKER = "can stop a run that worked"
#: release -> the start of each CHANGELOG bullet (after "- **") that stopped a run before the marker existed.
STOPS_BEFORE_MARKER = {
    "0.8.2": (
        "Changed, a round with a budget refuses an arm with no price",
        "Fixed, a provider's 401",
    ),
}
LOOKS_LIKE = re.compile(r"refus|stops? the run|stops? a run|now fails|now stops", re.I)


def changelog_sections(text: str) -> dict[str, list[str]]:
    """Version -> its bullets (a bullet and its continuation lines joined)."""
    out: dict[str, list[str]] = {}
    ver = None
    for line in text.splitlines():
        m = re.match(r"^## (\d+\.\d+\.\d+)\b", line)
        if m:
            ver, out[ver] = m.group(1), []
        elif ver and line.startswith("- "):
            out[ver].append(line)
        elif ver and out[ver] and line.startswith("  ") and line.strip():
            out[ver][-1] += " " + line.strip()
    return out


def upgrading_sections(text: str) -> dict[str, str]:
    """The release a section upgrades to -> its text."""
    parts = re.split(r"^## (?=From \S+ to \S+$)", text, flags=re.M)[1:]
    out = {}
    for p in parts:
        head, _, body = p.partition("\n")
        out[head.rsplit(" to ", 1)[1]] = body.split("\n## ", 1)[0]
    return out


def marked(version: str, bullets: list[str]) -> list[str]:
    leads = STOPS_BEFORE_MARKER.get(version, ())
    return [b for b in bullets if MARKER in b or any(b.startswith("- **" + lead) for lead in leads)]


def stop_leads(section: str) -> list[str]:
    return re.findall(r"^- \*\*[^\n]*?" + re.escape(MARKER) + r"[^\n]*?\*\*", section, flags=re.M)


def uncovered(change: dict[str, list[str]], upg: dict[str, str], versions=None) -> dict[str, list[str]]:
    """Per release, the marked bullets (their first 70 characters) its UPGRADING section has no lead for."""
    missing = {}
    for ver, bullets in change.items():
        if versions and ver not in versions:
            continue
        want = marked(ver, bullets)
        have = stop_leads(upg.get(ver, ""))
        if len(have) < len(want):
            missing[ver] = [b[:70] for b in want][len(have) :] if have else [b[:70] for b in want]
    return missing


def main() -> int:
    change = changelog_sections((HARNESS / "CHANGELOG.md").read_text(encoding="utf-8"))
    upg = upgrading_sections((HARNESS / "docs" / "UPGRADING.md").read_text(encoding="utf-8"))
    if "--candidates" in sys.argv:
        for ver, bullets in change.items():
            if MARKER in " ".join(bullets) or ver in STOPS_BEFORE_MARKER:
                continue
            for b in bullets:
                if LOOKS_LIKE.search(b):
                    print(f"{ver}: {b[:150]}")
        return 0

    # The checker itself, on text it can be wrong about.
    sample_c = {"9.9.9": [f"- **Changed, x** it {MARKER}.", "- **New, y** nothing"]}
    check(
        "a marked bullet with no UPGRADING section is found",
        uncovered(sample_c, {}) == {"9.9.9": [sample_c["9.9.9"][0][:70]]},
    )
    check(
        "a marked bullet with a lead in its section is covered",
        not uncovered(sample_c, {"9.9.9": f"- **A thing {MARKER}:** do z.\n"}),
    )
    check(
        "a lead in another release's section does not cover it",
        bool(uncovered(sample_c, {"9.9.8": f"- **A thing {MARKER}:** z\n"})),
    )
    check("an unmarked release needs nothing", not uncovered({"9.9.9": ["- **New, y** nothing"]}, {}))

    versions = [v for v in change if v in STOPS_BEFORE_MARKER or any(MARKER in b for b in change[v])]
    check(
        "0.8.2's two bullets are found by their lead",
        len(marked("0.8.2", change["0.8.2"])) == 2,
        marked("0.8.2", change["0.8.2"]),
    )
    gaps = uncovered(change, upg, versions)
    for ver in versions:
        check(f"{ver}: UPGRADING names each change that can stop a run", ver not in gaps, gaps.get(ver))
    return summary("test_upgrading_stops")


sys.exit(main())
