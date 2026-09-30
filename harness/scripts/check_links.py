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
import re, pathlib, sys

if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
    # It used to fall through and run the whole check, so `--help`
    # returned 0 only when every assertion happened to pass -- the trap
    # validate_tree and check_model_facts already learned.
    print(__doc__)
    raise SystemExit(0)
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
# REFERENCE-STYLE LINKS. `[text][ref]` with `[ref]: ./path` at the bottom was invisible
# to both loops above -- they only match the inline `[text](path)` form -- so a
# reference-style link to a missing file passed. Found by external review.
for md in root.rglob("*.md"):
    if ".venv" in str(md): continue
    for m in re.finditer(r"^\[[^\]]+\]:\s*(\S+)\s*$", md.read_text(), re.M):
        t = m.group(1).split("#")[0]
        if not t or t.startswith(("http", "mailto:")): continue
        if not (md.parent / t).exists():
            bad.append(f"{md.relative_to(root)} -> {t}  (missing file, reference-style)")

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
# EXIT NON-ZERO WHEN SOMETHING IS BROKEN. This printed the bad links and exited 0,
# so `make ci` stayed green through every broken link it found. A checker that cannot
# fail is not a check -- the same hole `check_terminology.py` had in round 1, which was
# fixed there and nowhere else. The lesson was the instance; the bug was the class.
if bad:
    print(f"FAIL  {len(bad)} broken link(s) or anchor(s):")
    print("\n".join(f"  {b}" for b in bad))
    raise SystemExit(1)
print("all relative links and anchors resolve")
