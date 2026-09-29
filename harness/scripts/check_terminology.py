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

# The repo root, derived from THIS FILE. It was hardcoded to one laptop's absolute
# path, so everywhere else `rglob` matched nothing, `bad` stayed empty and the check
# exited 0 having read no files at all. It was reported as green in CI and described
# in a commit message as having "earned itself twice". It had checked nothing.
root = pathlib.Path(__file__).resolve().parents[2]

files = [f for f in root.rglob("*.md")
         if ".venv" not in str(f) and "/data/" not in str(f)]
if not files:
    # A check that cannot find its inputs must FAIL, not pass. This is the assertion
    # that would have caught the hardcoded path immediately.
    print(f"FAIL  no markdown found under {root} — this check is not looking at the repo")
    sys.exit(1)

# WHAT THIS CHECK ACTUALLY COVERS, counted rather than implied. It used to report
# "every experiment-column cell in 40 file(s)", which is how many markdown files it
# READ. It only asserts on tables whose header row is `| experiment |`, and exactly 2
# files have one -- so the message overstated coverage twentyfold, on a check whose
# whole history is having reported green for reading nothing. Reading is not checking.
bad = []
with_table = []
cells = 0
for f in files:
    lines = f.read_text().split("\n"); in_exp = False; seen_here = False
    for i, line in enumerate(lines, 1):
        if re.match(r"^\| *experiment *\|", line, re.I): in_exp = True; seen_here = True; continue
        if in_exp:
            if not line.startswith("|"): in_exp = False; continue
            if re.match(r"^\|[-: |]+\|$", line): continue
            cell = re.match(r"^\| *\*{0,2}([^|*]+?)\*{0,2} *\|", line)
            if cell:
                v = cell.group(1).strip()
                if v in ("all", "", "—"):
                    continue
                cells += 1
                if not v.startswith(("Summarisation ·","Classification ·",
                                     "Extraction ·","Retrieval ·")):
                    bad.append("%s:%d  %s" % (f.relative_to(root), i, v))
    if seen_here:
        with_table.append(f.relative_to(root))

if bad:
    print("FAIL  %d non-canonical experiment label(s):" % len(bad))
    print("\n".join("  " + b for b in bad))
    sys.exit(1)
if not cells:
    # Same hole as the hardcoded path, one level in: reading 40 files and asserting on
    # none of them is not a pass.
    print("FAIL  %d markdown file(s) read, but NOT ONE experiment-column cell was "
          "checked — this check is asserting nothing" % len(files))
    sys.exit(1)
print("%d experiment-column cell(s) in %d of %d markdown file(s) use the canonical "
      "Task · Dataset label" % (cells, len(with_table), len(files)))
print("  files with an experiment column: " + ", ".join(str(x) for x in with_table))
sys.exit(0)
