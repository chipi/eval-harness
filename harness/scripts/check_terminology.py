#!/usr/bin/env python3
"""Every "experiment" table cell must use the canonical `Task · Dataset` label. $0.

    python scripts/check_terminology.py

WHY THIS IS A CHECK AND NOT A CONVENTION. The five experiments were referred to by
task name in some tables ("summarisation") and by dataset name in others ("AG News",
"SciFact"), in the same column, across 65 rows. Two of them share the classification
task, so a dataset-only label is ambiguous and a task-only label is wrong -- and
nothing catches the drift by eye once a document is 500 lines long.

The canonical labels are defined in docs/REFERENCE.md#terminology. This fails if a
cell in any experiment-keyed table does not use one.
"""
import pathlib, re, sys
root = pathlib.Path("/Users/claude/projects/eval-harness")
bad = []
for f in root.rglob("*.md"):
    if ".venv" in str(f) or "/data/" in str(f): continue
    lines = f.read_text().split("\n"); in_exp = False
    for i, line in enumerate(lines, 1):
        if re.match(r"^\| *experiment *\|", line, re.I): in_exp = True; continue
        if in_exp:
            if not line.startswith("|"): in_exp = False; continue
            if re.match(r"^\|[-: |]+\|$", line): continue
            cell = re.match(r"^\| *\*{0,2}([^|*]+?)\*{0,2} *\|", line)
            if cell:
                v = cell.group(1).strip()
                ok = v.startswith(("Summarisation ·","Classification ·","Extraction ·","Retrieval ·"))
                if not ok and v not in ("all","","—"):
                    bad.append("%s:%d  %s" % (f.relative_to(root), i, v))
print("\n".join(bad) if bad else "every experiment-column cell uses the canonical Task · Dataset label")
sys.exit(1 if bad else 0)
