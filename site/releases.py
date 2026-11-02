"""The release notes page: harness/CHANGELOG.md, rendered.

The changelog is the one record of what each release shipped. The GitHub Release for a tag
takes its notes from the same section (harness-release.yml), the docs site shows the file
itself, and this page shows it on the harness site, so the three cannot disagree.

Only the Markdown the changelog uses is rendered: `##`/`###` headings, `- ` bullets nested by
their indent (two spaces a level; wrapped lines continue them), paragraphs, **bold** (which may
hold `code` and *italics*), *italics*, `code` and [links](url). Anything else stays as text, so
a new construct shows up plainly instead of silently breaking the page.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "harness" / "CHANGELOG.md"
_RELEASE = re.compile(r"^##\s+(\d+\.\d+\.\d+)(?:\s+—\s+(\d{4}-\d{2}-\d{2}|unreleased))?\s*$")


def _inline(H, text: str, blob: str) -> str:
    out = H.e(text)
    # Code first, set aside so a `*` inside it is never emphasis.
    codes: list[str] = []

    def keep(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    out = re.sub(r"`([^`]+)`", keep, out)
    out = re.sub(r"\*\*((?:[^*]|\*[^*]+\*)+)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<![\w*])\*([^*\s](?:[^*]*[^*\s])?)\*(?![\w*])", r"<em>\1</em>", out)
    out = re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{codes[int(m.group(1))]}</code>", out)

    def link(m):
        label, url = m.group(1), m.group(2)
        if not re.match(r"https?://", url):
            # Relative links in the changelog are relative to harness/; point them at GitHub.
            url = f"{blob}/harness/{url}" if not url.startswith("../") else f"{blob}/{url[3:]}"
        return f'<a href="{url}">{label}</a>'

    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, out)


def releases(text: str) -> list:
    """[{version, date, blocks: [(kind, text)]}] from the changelog, newest first."""
    out, cur, para, item = [], None, [], None
    for raw in text.splitlines():
        line = raw.rstrip()
        m = _RELEASE.match(line)
        if line.startswith("## ") and not m:
            # A release written another way ('-' for the em dash, 'v0.3.0') would otherwise be
            # read into the release above it.
            raise SystemExit(
                f"harness/CHANGELOG.md: {line!r} is not '## X.Y.Z', '## X.Y.Z — unreleased' or '## X.Y.Z — YYYY-MM-DD'"
            )
        if m:
            cur = {
                "version": m.group(1),
                "date": None if m.group(2) in (None, "unreleased") else m.group(2),
                "blocks": [],
            }
            out.append(cur)
            para, item = [], None
            continue
        if cur is None:
            continue
        if line.startswith("### "):
            cur["blocks"].append(("h3", line[4:].strip()))
            para, item = [], None
        elif (
            line.lstrip().startswith("- ")
            and (len(line) - len(line.lstrip())) % 2 == 0
            and (not line.startswith(" ") or (cur["blocks"] and cur["blocks"][-1][0] == "li"))
        ):
            # A bullet's depth is its indent, two spaces a level (a nested list inside a bullet).
            item = [line.lstrip()[2:].strip()]
            cur["blocks"].append(("li", item, (len(line) - len(line.lstrip())) // 2))
            para = []
        elif not line.strip():
            item, para = None, []
        elif raw.startswith("  ") and cur["blocks"] and cur["blocks"][-1][0] == "li":
            # A wrapped line, or an indented paragraph inside the bullet after a blank line: the bullet's text.
            item = cur["blocks"][-1][1]
            item.append(line.strip())
        else:
            if not para:
                para = [line.strip()]
                cur["blocks"].append(("p", para))
            else:
                para.append(line.strip())
    # Two releases merged into one (a heading lost when the next section was written above it)
    # show as a release whose section headings repeat: 0.4.3 carried 0.4.2's whole section.
    for r in out:
        heads = [b[1] for b in r["blocks"] if b[0] == "h3"]
        dup = sorted({h for h in heads if heads.count(h) > 1})
        if dup:
            raise SystemExit(
                f"harness/CHANGELOG.md: {r['version']} has {', '.join(repr(h) for h in dup)} more than once: "
                "is a release heading missing below it?"
            )
    return out


def release_html(H, rel: dict, blob: str, repo: str) -> str:
    parts: list[str] = []
    depth = 0  # how many lists are open; an item at depth d sits in the d+1-th
    for kind, val, *rest in rel["blocks"]:
        if kind == "li":
            d = min(rest[0], depth)  # a level deeper at most: a stray indent is not two new lists
            if depth == 0 or d + 1 > depth:
                parts.append("<ul><li>")
            else:
                parts.append("</li></ul>" * (depth - d - 1) + "</li><li>")
            depth = d + 1
            parts.append(_inline(H, " ".join(val), blob))
            continue
        if depth:
            parts.append("</li></ul>" * depth)
            depth = 0
        if kind == "h3":
            parts.append(f"<h3>{H.e(val)}</h3>")
        else:
            parts.append(f"<p>{_inline(H, ' '.join(val), blob)}</p>")
    if depth:
        parts.append("</li></ul>" * depth)
    v = rel["version"]
    date = rel["date"] or "unreleased"
    tag = (
        f'<p class="note"><a href="{repo}/releases/tag/v{v}">GitHub Release v{v} ↗</a></p>'
        if rel["date"]
        else ""
    )
    return (
        f'<article class="release" id="v{v}" style="margin-bottom:72px"><div class="eyebrow"><span class="num">release</span>{H.e(date)}</div><h2>v{v}</h2>'
        f'<div class="prose">{"".join(parts)}</div>{tag}</article>'
    )


def releases_page(H) -> str:
    rels = releases(CHANGELOG.read_text(encoding="utf-8"))
    if not rels:
        raise SystemExit("harness/CHANGELOG.md has no '## X.Y.Z — date' section")
    toc = "".join(
        f'<a href="#v{r["version"]}"><span>v{r["version"]}</span>{H.e(r["date"] or "unreleased")}</a>'
        for r in rels
    )
    body = f"""
<section class="hero"><div class="wrap">
  <div class="kicker"><b>Release notes</b> · the harness, version by version</div>
  <h1>What each release <em>shipped.</em></h1>
  <p class="dek">The harness is installed by pinning a release tag. Each release below is its changelog section, the same text its GitHub Release carries. A change that can move a result is listed under Changed, in words a project pinning the harness can act on.</p>
  <nav class="toc">{toc}</nav>
  <div class="btns"><a class="btn primary" href="{H.REPO}/releases">GitHub Releases ↗</a><a class="btn" href="docs/harness/RELEASING/">How releases are cut</a><a class="btn" href="docs/harness/UPGRADING/">Upgrading</a></div>
</div></section>
<section class="block"><div class="wrap releases">{"".join(release_html(H, r, H.BLOB, H.REPO) for r in rels)}</div></section>
{H.author("releases")}"""
    return H.page(
        "Release notes — eval-harness",
        "What each release of the harness shipped: new capabilities, changes that can move "
        "a result, and how to upgrade.",
        body,
        here="releases",
    )
