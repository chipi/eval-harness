"""The release notes page: harness/CHANGELOG.md, rendered.

The changelog is the one record of what each release shipped. The GitHub Release for a tag
takes its notes from the same section (harness-release.yml), the docs site shows the file
itself, and this page shows it on the harness site, so the three cannot disagree.

Only the Markdown the changelog uses is rendered: `##`/`###` headings, `- ` bullets (wrapped
lines continue them), paragraphs, **bold**, `code` and [links](url). Anything else stays as
text, so a new construct shows up plainly instead of silently breaking the page.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "harness" / "CHANGELOG.md"
_RELEASE = re.compile(r"^##\s+(\d+\.\d+\.\d+)(?:\s+—\s+(\d{4}-\d{2}-\d{2}|unreleased))?\s*$")


def _inline(H, text: str, blob: str) -> str:
    out = H.e(text)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", out)

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
            raise SystemExit(f"harness/CHANGELOG.md: {line!r} is not '## X.Y.Z', '## X.Y.Z — unreleased' or '## X.Y.Z — YYYY-MM-DD'")
        if m:
            cur = {"version": m.group(1), "date": None if m.group(2) in (None, "unreleased") else m.group(2), "blocks": []}
            out.append(cur)
            para, item = [], None
            continue
        if cur is None:
            continue
        if line.startswith("### "):
            cur["blocks"].append(("h3", line[4:].strip()))
            para, item = [], None
        elif line.startswith("- "):
            item = [line[2:].strip()]
            cur["blocks"].append(("li", item))
            para = []
        elif not line.strip():
            item, para = None, []
        elif item is not None and raw.startswith("  "):
            item.append(line.strip())
        else:
            if not para:
                para = [line.strip()]
                cur["blocks"].append(("p", para))
            else:
                para.append(line.strip())
    return out


def release_html(H, rel: dict, blob: str, repo: str) -> str:
    parts, in_list = [], False
    for kind, val in rel["blocks"]:
        if kind == "li":
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_inline(H, ' '.join(val), blob)}</li>")
            continue
        if in_list:
            parts.append("</ul>")
            in_list = False
        if kind == "h3":
            parts.append(f"<h3>{H.e(val)}</h3>")
        else:
            parts.append(f"<p>{_inline(H, ' '.join(val), blob)}</p>")
    if in_list:
        parts.append("</ul>")
    v = rel["version"]
    date = rel["date"] or "unreleased"
    tag = (f'<p class="note"><a href="{repo}/releases/tag/v{v}">GitHub Release v{v} ↗</a></p>'
           if rel["date"] else "")
    return (f'<article class="release" id="v{v}" style="margin-bottom:72px"><div class="eyebrow"><span class="num">release</span>{H.e(date)}</div><h2>v{v}</h2>'
            f'<div class="prose">{"".join(parts)}</div>{tag}</article>')


def releases_page(H) -> str:
    rels = releases(CHANGELOG.read_text(encoding="utf-8"))
    if not rels:
        raise SystemExit("harness/CHANGELOG.md has no '## X.Y.Z — date' section")
    toc = "".join(f'<a href="#v{r["version"]}"><span>v{r["version"]}</span>{H.e(r["date"] or "unreleased")}</a>'
                  for r in rels)
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
    return H.page("Release notes — eval-harness",
                  "What each release of the harness shipped: new capabilities, changes that can move "
                  "a result, and how to upgrade.", body, here="releases")
