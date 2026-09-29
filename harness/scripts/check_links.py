#!/usr/bin/env python3
"""Every relative markdown link and #anchor in the repo must resolve. $0.

    python scripts/check_links.py

Review found a broken anchor and four wrong command paths that had survived a
rename -- the kind of rot no reader reports and no test catches. Slugs follow
GitHub's rule: lowercase, drop punctuation, replace EACH space with a hyphen
(runs of spaces become runs of hyphens, which is why a heading with an em dash
produces a double hyphen). My first version of this collapsed them and produced
five false positives, so the rule is written down here rather than re-derived.
"""
import re, pathlib
root = pathlib.Path(__file__).resolve().parents[2]
def slugs(text):
    out=set()
    for line in text.split("\n"):
        m=re.match(r"^#{1,6}\s+(.*)",line)
        if m:
            t=m.group(1).strip().lower()
            t=re.sub(r"[^\w\s-]","",t); t=t.replace(" ","-")
            out.add(t)
    return out
bad=[]
for md in root.rglob("*.md"):
    if ".venv" in str(md): continue
    for m in re.finditer(r"\[[^\]]*\]\(([^)]*?)#([^)]+)\)", md.read_text()):
        tgt,anc=m.group(1),m.group(2)
        f = md if not tgt else (md.parent/tgt)
        if not f.exists(): continue
        if anc not in slugs(f.read_text()):
            bad.append(f"{md.relative_to(root)} -> {tgt or md.name}#{anc}")
for md in root.rglob("*.md"):
    if ".venv" in str(md): continue
    for m in re.finditer(r"\[[^\]]*\]\(([^)#]+?)(?:#[^)]*)?\)", md.read_text()):
        t = m.group(1)
        if t.startswith(("http", "mailto:")): continue
        if not (md.parent / t).exists():
            bad.append(f"{md.relative_to(root)} -> {t}  (missing file)")

if not list(root.rglob("*.md")):
    print("FAIL  no markdown found — this check is not looking at the repo")
    raise SystemExit(1)
print("\n".join(bad) if bad else
      f"all relative links and anchors resolve")
