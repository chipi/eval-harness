#!/usr/bin/env python3
"""Every relative markdown link and #anchor in the repo must resolve. $0.

    python tools/check_links.py

Review found a broken anchor and four wrong command paths that had survived a
rename -- the kind of rot no reader reports and no test catches. Slugs follow
GitHub's rule: lowercase, drop punctuation, replace EACH space with a hyphen
(runs of spaces become runs of hyphens, which is why a heading with an em dash
produces a double hyphen). My first version of this collapsed them and produced
five false positives, so the rule is written down here rather than re-derived.
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # the evaluation_harness package
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from evaluation_harness import _store
from evaluation_harness._common import no_options

no_options(__doc__)  # --help prints this; anything else is refused
root = pathlib.Path(__file__).resolve().parents[2]


def slugs(text):
    """All markdown heading slugs in the text (GitHub's rules: lowercase, spaces->hyphens)."""
    out = set()
    for line in text.split("\n"):
        m = re.match(r"^#{1,6}\s+(.*)", line)
        if m:
            t = m.group(1).strip().lower()
            t = re.sub(r"[^\w\s-]", "", t)
            t = t.replace(" ", "-")
            out.add(t)
    return out


bad = []
for md in _store.rglob(root, "*.md"):
    if ".venv" in str(md):
        continue
    for m in re.finditer(r"\[[^\]]*\]\(([^)]*?)#([^)]+)\)", _store.read_text(md)):
        tgt, anc = m.group(1), m.group(2)
        f = md if not tgt else (md.parent / tgt)
        if not _store.exists(f):
            continue
        if anc not in slugs(_store.read_text(f)):
            bad.append(f"{md.relative_to(root)} -> {tgt or md.name}#{anc}")
# REFERENCE-STYLE LINKS. `[text][ref]` with `[ref]: ./path` at the bottom was invisible
# to both loops above -- they only match the inline `[text](path)` form -- so a
# reference-style link to a missing file passed. Found by external review.
for md in _store.rglob(root, "*.md"):
    if ".venv" in str(md):
        continue
    for m in re.finditer(r"^\[[^\]]+\]:\s*(\S+)\s*$", _store.read_text(md), re.M):
        t = m.group(1).split("#")[0]
        if not t or t.startswith(("http", "mailto:")):
            continue
        if not _store.exists(md.parent / t):
            bad.append(f"{md.relative_to(root)} -> {t}  (missing file, reference-style)")

for md in _store.rglob(root, "*.md"):
    if ".venv" in str(md):
        continue
    for m in re.finditer(r"\[[^\]]*\]\(([^)#]+?)(?:#[^)]*)?\)", _store.read_text(md)):
        t = m.group(1)
        if t.startswith(("http", "mailto:")):
            continue
        if not _store.exists(md.parent / t):
            bad.append(f"{md.relative_to(root)} -> {t}  (missing file)")

if not list(_store.rglob(root, "*.md")):
    print("FAIL  no markdown found — this check is not looking at the repo")
    raise SystemExit(1)
# EXIT NON-ZERO WHEN SOMETHING IS BROKEN. This printed the bad links and exited 0,
# so `make ci` stayed green through every broken link it found. A checker that cannot
# fail is not a check -- the same hole `check_terminology.py` had in round 1, which was
# fixed there and nowhere else. The lesson was the instance; the bug was the class.
if bad:
    print(f"FAIL  {len(bad)} broken link(s) or anchor(s):")
    print("\n".join(f"  {b}" for b in bad))
    raise SystemExit(1)
print("all relative links and anchors resolve")
