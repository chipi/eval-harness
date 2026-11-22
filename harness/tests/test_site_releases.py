#!/usr/bin/env python3
"""The site's release notes page (site/releases.py): the changelog's Markdown, rendered.

    python tests/test_site_releases.py

Nested bullets keep their nesting, bold may hold code and italics, italics render, and code is never read as emphasis.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "site"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import releases as R  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402


class H:
    @staticmethod
    def e(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


TEXT = """# Changelog

## 9.9.0 — unreleased

### Changed

- **`evh experiment-run` is `evh run`, and an *experiment* is an *eval***: words.
- **Labels**:
  - **`evh label-sheet`** writes a sheet,
    wrapped onto a second line.
  - **The same rules:**
    - Arms on different `dataset_id`s are refused.
    - A `*` in `data/runs-judged/*` is code.
- The last one, and *vetted* is italic.
"""

rel = R.releases(TEXT)[0]
html = R.release_html(H, rel, "https://x/blob/main", "https://x")
check(
    "bold that holds code and italics renders, with no * left",
    "<b><code>evh experiment-run</code> is <code>evh run</code>, and an <em>experiment</em> is an <em>eval</em></b>"
    in html
    and "**" not in html,
    html[:400],
)
check(
    "a nested bullet is a nested list, two levels deep, its wrapped line continuing it",
    "<li><b>Labels</b>:<ul><li><b><code>evh label-sheet</code></b> writes a sheet, wrapped onto a second line."
    in html
    and "<ul><li>Arms on different <code>dataset_id</code>s are refused.</li><li>" in html
    and html.count("<ul>") == html.count("</ul>") == 3
    and " - " not in html,
    html,
)
check(
    "code is never emphasis; italics outside code render",
    "<code>data/runs-judged/*</code> is code" in html and "<em>vetted</em> is italic" in html,
    html[-300:],
)
real = R.releases((ROOT / "harness" / "CHANGELOG.md").read_text(encoding="utf-8"))
pages = [R.release_html(H, r, "https://x/blob/main", "https://x") for r in real]
check(
    "the real changelog: no bullet flattened into ' - ', no ** left, every list closed",
    all("**" not in p and p.count("<ul>") == p.count("</ul>") for p in pages)
    and not any("</code> - <" in p or ". - " in p for p in pages),
    next((p[:300] for p in pages if "**" in p or ". - " in p), ""),
)


# A release's section is short and links to its full notes (docs/releases/<version>.md): the size is checked, the link
# resolves both ways. Releases before 0.8.0 are exempt (their sections are long, and stay).
import tempfile  # noqa: E402

LINK = "https://github.com/chipi/eval-harness/blob/main/docs/releases/9.9.0.md"
short = f"# Changelog\n\n## 9.9.0 — 2030-01-01\n\nOne paragraph.\n\nFull notes: [9.9.0]({LINK}).\n"
long_ = "# Changelog\n\n## 9.9.0 — 2030-01-01\n\n" + "A very long line of notes. " * 400 + "\n"
legacy = "# Changelog\n\n## 0.7.0 — 2026-11-04\n\n" + "A very long line of notes. " * 400 + "\n"
with tempfile.TemporaryDirectory() as d:
    notes = Path(d)
    check(
        "a section over the limit is a problem",
        bool(R.check_sections(long_, notes)),
        str(R.check_sections(long_, notes)),
    )
    check(
        "a long section before 0.8.0 is not",
        R.check_sections(legacy, notes) == [],
        str(R.check_sections(legacy, notes)),
    )
    check("a link to a notes page that does not exist is a problem", bool(R.check_sections(short, notes)))
    (notes / "9.9.0.md").write_text("# 9.9.0\n", encoding="utf-8")
    check(
        "a short section linking to an existing notes page is fine",
        R.check_sections(short, notes) == [],
        str(R.check_sections(short, notes)),
    )
    bare = short.replace(f"Full notes: [9.9.0]({LINK}).\n", "")
    check(
        "a notes page the section does not link to is a problem",
        bool(R.check_sections(bare, notes)),
        str(R.check_sections(bare, notes)),
    )
check(
    "the real changelog: every section from 0.8.0 is short and its notes link resolves",
    R.check_sections((ROOT / "harness" / "CHANGELOG.md").read_text(encoding="utf-8")) == [],
    str(R.check_sections((ROOT / "harness" / "CHANGELOG.md").read_text(encoding="utf-8"))),
)

sys.exit(summary())
