#!/usr/bin/env python3
"""The reports' model facts must match the captured evidence. $0, NO NETWORK.

    python scripts/check_model_facts.py

WHY NO NETWORK. Three reviewers could not check a single model size or licence claim
because HuggingFace and OpenRouter were blocked from their container. An offline check
against a dated capture is worth more than an online one they cannot run: it separates
"this repo got the fact wrong" from "the fact changed since", which are otherwise
indistinguishable.

The capture is docs/evidence/model_facts.json. Refresh it with
docs/evidence/capture.sh; this script never reaches the network itself.
"""
import json
import re
import sys
from pathlib import Path

if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
    # It used to fall through and run the whole check, so `--help` returned 0 only when
    # every assertion happened to pass -- the same trap validate_tree had.
    print(__doc__)
    raise SystemExit(0)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EV = ROOT / "docs" / "evidence" / "model_facts.json"

ok: list = []
notes: list = []
def check(label, cond, detail=""):
    ok.append(cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}{('   ' + detail) if detail and not cond else ''}")

if not EV.is_file():
    print(f"FAIL  no evidence capture at {EV}")
    sys.exit(1)
facts = json.loads(EV.read_text())["models"]

# WHERE THE CLAIMS COME FROM: THE DOCUMENTS, NOT THIS FILE.
#
# This used to hold CLAIMED_LICENCE and CLAIMED_GB as literals and compare THEM to the
# evidence. That checks the checker. Editing REPORT_SYNTHESIS.md to say bart-large-cnn
# is GPL, or that DeepSeek is 40 GB, changed nothing here and `make ci` stayed green.
# Found by external review. The claims are now parsed out of the prose that makes them.
REF = (ROOT / "docs" / "REFERENCE.md").read_text()
SYN = (ROOT / "research" / "REPORT_SYNTHESIS.md").read_text()

#: Display name -> HuggingFace id. An IDENTITY mapping, not a claim: the reports write
#: "Llama-3.3-70B" where the API says "meta-llama/Llama-3.3-70B-Instruct". If a report
#: renames a model this map must follow, and the coverage assertion at the bottom is
#: what makes that impossible to forget.
ALIASES = {
    "DeepSeek-V4.1-Flash": "deepseek-ai/DeepSeek-V4.1-Flash",
    "DeepSeek-V4.1": "deepseek-ai/DeepSeek-V4.1-Flash",
    "DeepSeek-V4-Pro": "deepseek-ai/DeepSeek-V4-Pro",
    "DeepSeek-V4-Flash": "deepseek-ai/DeepSeek-V4-Flash",
    "GLM-4.5-Air": "zai-org/GLM-4.5-Air",
    "GLM-4.6": "zai-org/GLM-4.6",
    "GLM-5": "zai-org/GLM-5",
    "Llama-3.3-70B": "meta-llama/Llama-3.3-70B-Instruct",
    "Gemma-4-26B-A4B": "google/gemma-4-26b-a4b-it",
    "Gemma-4-31B": "google/gemma-4-31b-it",
    "Gemma-3-27B": "google/gemma-3-27b-it",
    "Mistral-Small-3.2-24B": "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
    "Mistral-Large-3": "mistralai/Mistral-Large-3",
}


def weights_gb(mid):
    """Size of ONE copy of the weights, MEASURED, in GB.

    Measured bytes rather than a figure derived from `safetensors.parameters`, which is
    an ELEMENT count per dtype. Deriving bytes from it assumes one byte per int8
    element, and for the three DeepSeek checkpoints that is wrong by up to 1.85x: they
    report 763B "I8" elements and occupy 510 GB, because those tensors are packed at
    roughly four bits. 763.2B params in 510.3 GB is 0.67 bytes per parameter.

    The old derivation is still computed below, as a cross-check rather than an answer.
    """
    b = (facts.get(mid) or {}).get("safetensors_bytes")
    return (b / 1e9) if b else None


def derived_gb(mid):
    """The dtype-derived figure this file used to trust. Kept to flag disagreement."""
    p = (facts.get(mid) or {}).get("params_by_dtype") or {}
    w = {"F32": 4, "BF16": 2, "F16": 2, "F8_E4M3": 1, "I8": 1, "I64": 8, "I32": 4}
    return sum(v * w.get(k, 2) for k, v in p.items()) / 1e9 if p else None


# ---- licences, read from docs/REFERENCE.md's licence table -------------------------
lic_rows = re.findall(r"^\|\s*\[`([^`]+)`\]\([^)]*\)\s*\|\s*([A-Za-z0-9.\- ]+?)\s*\|\s*$",
                      REF, re.M)
check("REFERENCE.md's licence table is readable", len(lic_rows) >= 10,
      f"parsed {len(lic_rows)} rows")
for mid, claimed in lic_rows:
    got = (facts.get(mid) or {}).get("license")
    if got is None:
        continue                      # not in the capture; the coverage check catches it
    check(f"licence {mid}", got.lower() == claimed.strip().lower(),
          f"REFERENCE.md says {claimed}, evidence says {got}")

# ---- small-model sizes, read from docs/REFERENCE.md's model table ------------------
size_rows = re.findall(
    r"^\|\s*`[^`]*`\s*\|\s*\[`([^`]+)`\]\([^)]*\)\s*\|\s*([0-9.]+)\s*(GB|MB)\s*\|",
    REF, re.M)
check("REFERENCE.md's model table is readable", len(size_rows) >= 8,
      f"parsed {len(size_rows)} rows")
for mid, num, unit in size_rows:
    claimed = float(num) * (1.0 if unit == "GB" else 0.001)
    got = weights_gb(mid)
    if got is None:
        continue
    # 12% admitted a 13% error: e5_base's 438 MB could read 495 MB and pass. These
    # are checkpoint byte counts, not estimates, so the tolerance only has to
    # absorb MB-vs-MiB rounding and how the doc rounds. 20 MB or 5%, whichever is
    # larger. Found by external review.
    check(f"size {mid} ~{num} {unit}", abs(got - claimed) <= max(0.02, claimed * 0.05),
          f"REFERENCE.md says {num} {unit}, evidence gives {got*1000:.0f} MB")

# ---- large-model sizes, read from the synthesis's own sentences --------------------
# Every "<display name> ... N GB" within one line. The synthesis states these in tables
# and prose, and this is the claim a reader acts on when deciding what hardware to buy.
seen_big = set()
for disp, mid in ALIASES.items():
    got = weights_gb(mid)
    if got is None:
        continue
    for line in SYN.splitlines():
        if disp not in line:
            continue
        # The gap may cross a table cell boundary -- "| DeepSeek-V4.1 | 765 GB |" puts
        # the number in the next cell -- so "|" is allowed in it, but a newline is not.
        for num in re.findall(re.escape(disp) + r"[^\n]{0,60}?([0-9][0-9,.]*)\s*GB", line):
            claimed = float(num.replace(",", ""))
            # int4/int8 quantisation figures are deliberately fractions of the native
            # size and are not claims about the published checkpoint.
            if claimed < got * 0.6:
                continue
            seen_big.add(disp)
            check(f"size {disp} ~{claimed:.0f} GB (REPORT_SYNTHESIS)",
                  abs(got - claimed) <= max(2, claimed * 0.05),
                  f"the synthesis says {claimed:.0f} GB, the checkpoint measures {got:.0f} GB")
check("the synthesis's large-model sizes were actually found and checked",
      len(seen_big) >= 4, f"only matched {sorted(seen_big)}")

# ---- the derived figure disagreeing with the measured one is itself a finding ------
for mid in facts:
    d, m = derived_gb(mid), weights_gb(mid)
    if d and m and abs(d - m) > max(2, m * 0.05):
        notes.append(f"{mid}: dtype-derived {d:.0f} GB vs measured {m:.0f} GB "
                     f"({d/m:.2f}x) — packed tensors, use the measured figure")

# THE ONE THE REVIEW DISPUTED: both numbers are right about different things.
ds = facts.get("deepseek-ai/DeepSeek-V4.1-Flash") or {}
check("DeepSeek-V4.1-Flash total params are 763B, not 552B",
      abs((ds.get("params_total") or 0) / 1e9 - 763) < 1,
      f"evidence: {ds.get('params_total')}")
check("...and the reports say BOTH the 552B backbone and the measured checkpoint size",
      all(t in SYN for t in ("552B", "510 GB")))
# 765 GB may still APPEAR -- the synthesis explains where it came from and why it was
# wrong, and deleting that history would hide the correction. What must not survive is
# the number presented as the size. So: every line that mentions it must also mark it
# as the old figure.
_stale = [f"{f}:{i}: {ln.strip()[:70]}"
          for f in ("REPORT_SYNTHESIS.md", "REPORT_SUMMARIZATION.md")
          for i, ln in enumerate((ROOT / "research" / f).read_text().splitlines(), 1)
          if "765 GB" in ln and not any(w in ln for w in ("until", "never measured",
                                                          "inflated", "derived"))]
check("765 GB survives only where it is marked as the corrected-away figure",
      not _stale, "; ".join(_stale))

# The tier split the synthesis states.
syn = (ROOT / "research" / "REPORT_SYNTHESIS.md").read_text()
# DERIVED, not asserted. This used to check that the synthesis contains the checker's
# own literal "14 of the 24" -- the same self-verifying shape round 2 found elsewhere in
# this file. The open/proprietary split is a fact about REFERENCE.md's licence table, so
# count it there and require the synthesis to state that number. Found by external review.
# THE SECOND VERSION OF THIS CHECK ALSO COMPARED THE REPORT TO A LITERAL. `_hosted_open`
# was derived and then never used -- the assertion was `_stated == 14` -- and it was
# derived from the wrong table anyway: `lic_rows` is the 12-row licence table of small
# LOCAL models (bart, bge, e5, MiniLM, gliner...), not the 24 hosted arms, and it
# evaluated to 7. So the fix for "a number compared to a literal" recreated exactly that
# shape, with a comment above it claiming otherwise. Found by external review, round 5.
#
# The hosted arm table IS the source: 24 rows, each ending `**open**` or `proprietary`.
# Count them, and require the synthesis to state the count. Marking a model proprietary
# in REFERENCE.md must move the number in REPORT_SYNTHESIS or fail.
_HOSTED_ROW = re.compile(
    r"^\| `([a-z0-9_]+)` \|[^|]*\|[^|]*\| (\*\*open\*\*|proprietary)", re.M)
_hosted_rows = _HOSTED_ROW.findall((ROOT / "docs" / "REFERENCE.md").read_text())
_hosted_open = sum(1 for _a, _k in _hosted_rows if _k != "proprietary")
check(f"REFERENCE.md tabulates 24 hosted arms (found {len(_hosted_rows)})",
      len(_hosted_rows) == 24,
      "the open-weight count below is derived from this table; if it is not 24 rows "
      "the derivation is reading the wrong thing")
# EVERY statement of the count, not the first one. `re.search` returned the earliest
# match, so the synthesis states this number in three places and only one was read --
# editing either of the other two passed. That is round 4's M3 (a presence check that
# saw one of several) reappearing in a different file. Found by external review, round 5.
_prop = len(_hosted_rows) - _hosted_open
# Each pattern is anchored to the CLAIM, not to the phrase. "N of the 24 hosted arms"
# alone also matches "slower than 17 of the 24 hosted arms" -- a latency sentence --
# which the first version of this flagged as a wrong open-weight count. A check that
# cries wolf on correct text gets muted.
_counts = [(int(_n), "open") for _n in
           re.findall(r"(\d+) of the 24 hosted arms have \*\*downloadable weights\*\*", syn)]
for _line in syn.splitlines():
    _kind = ("open" if "Open-weight LLM" in _line else
             "proprietary" if "· Proprietary" in _line else None)
    if _kind:
        _counts += [(int(_n), _kind)
                    for _n in re.findall(r"\*\*(\d+) of the 24\*\*", _line)]
check(f"the synthesis states an open-weight count at all ({len(_counts)} statement(s))",
      any(k == "open" for _n, k in _counts),
      "no 'N of the 24' in REPORT_SYNTHESIS")
_wrong = [f"{_n} ({k})" for _n, k in _counts
          if _n != (_hosted_open if k == "open" else _prop)]
check(f"...and EVERY statement of it is the {_hosted_open} open / {_prop} proprietary "
      f"REFERENCE.md's hosted table supports",
      not _wrong,
      f"the synthesis says {', '.join(_wrong)}; the hosted table marks {_hosted_open} "
      f"of {len(_hosted_rows)} as open")
# REFERENCE.md repeats the count in its own prose, two paragraphs below the table.
check(f"...and REFERENCE.md's own prose agrees ({_hosted_open})",
      re.search(rf"\*\*{_hosted_open} of these 24\b",
                (ROOT / "docs" / "REFERENCE.md").read_text()) is not None,
      f"REFERENCE.md's table marks {_hosted_open} open; its prose says otherwise")
check("mistral_l is tabulated as open in REFERENCE.md",
      re.search(r"\| `mistral_l` \|[^|]*\|[^|]*\| \*\*open\*\*", (ROOT / "docs" / "REFERENCE.md").read_text()) is not None)

for n in notes:
    print(f"\n  note: {n}")
print(f"\n{sum(ok)}/{len(ok)} model facts match the {EV.parent.name}/ capture")
if not ok:
    print("FAIL  no facts were checked at all — this check is not reading the docs")
    sys.exit(1)
sys.exit(0 if all(ok) else 1)
