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

sys.exit(summary())
