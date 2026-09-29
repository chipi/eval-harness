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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EV = ROOT / "docs" / "evidence" / "model_facts.json"

ok: list = []
def check(label, cond, detail=""):
    ok.append(cond)
    print(f"  {'ok  ' if cond else 'FAIL'} {label}{('   ' + detail) if detail and not cond else ''}")

if not EV.is_file():
    print(f"FAIL  no evidence capture at {EV}")
    sys.exit(1)
facts = json.loads(EV.read_text())["models"]

#: (model id, what the reports claim). Licences are what docs/REFERENCE.md tabulates.
CLAIMED_LICENCE = {
    "facebook/bart-large-cnn": "mit",
    "facebook/bart-large-mnli": "mit",
    "BAAI/bge-small-en-v1.5": "mit",
    "intfloat/e5-base-v2": "mit",
    "sentence-transformers/all-MiniLM-L6-v2": "apache-2.0",
    "sentence-transformers/all-mpnet-base-v2": "apache-2.0",
    "urchade/gliner_medium-v2.1": "apache-2.0",
    "guishe/span-marker-generic-ner-v1-fewnerd-fine-super": "cc-by-sa-4.0",
    "mistralai/Mistral-Large-3": "apache-2.0",
    "zai-org/GLM-4.5-Air": "mit",
    "zai-org/GLM-4.6": "mit",
}
for mid, lic in CLAIMED_LICENCE.items():
    got = (facts.get(mid) or {}).get("license")
    check(f"licence {mid}", got == lic, f"reports say {lic}, evidence says {got}")

#: The size figures the synthesis quotes, in GB of weights as stored (dtype-aware).
def on_disk_gb(mid):
    p = (facts.get(mid) or {}).get("params_by_dtype") or {}
    w = {"F32": 4, "BF16": 2, "F16": 2, "F8_E4M3": 1, "I8": 1, "I64": 8, "I32": 4}
    return sum(v * w.get(k, 2) for k, v in p.items()) / 1e9

CLAIMED_GB = {
    "google/gemma-4-26b-a4b-it": 52, "google/gemma-4-31b-it": 63,
    "google/gemma-3-27b-it": 55, "mistralai/Mistral-Small-3.2-24B-Instruct-2506": 48,
    "meta-llama/Llama-3.3-70B-Instruct": 141, "zai-org/GLM-4.5-Air": 221,
    "zai-org/GLM-4.6": 714, "deepseek-ai/DeepSeek-V4.1-Flash": 765,
}
for mid, gb in CLAIMED_GB.items():
    got = on_disk_gb(mid)
    check(f"size {mid} ~{gb} GB", abs(got - gb) <= max(2, gb * 0.03),
          f"reports say ~{gb} GB, evidence gives {got:.0f} GB")

# THE ONE THE REVIEW DISPUTED: both numbers are right about different things.
ds = facts.get("deepseek-ai/DeepSeek-V4.1-Flash") or {}
check("DeepSeek-V4.1-Flash total params are 763B, not 552B",
      abs((ds.get("params_total") or 0) / 1e9 - 763) < 1,
      f"evidence: {ds.get('params_total')}")
check("...and the reports say BOTH 552B backbone and ~765 GB checkpoint",
      all(t in (ROOT / "research" / "REPORT_SYNTHESIS.md").read_text()
          for t in ("552B", "765 GB")))

# The tier split the synthesis states.
syn = (ROOT / "research" / "REPORT_SYNTHESIS.md").read_text()
check("the synthesis states 14 open-weight arms", "14 of the 24" in syn)
check("mistral_l is tabulated as open in REFERENCE.md",
      re.search(r"\| `mistral_l` \|[^|]*\|[^|]*\| \*\*open\*\*", (ROOT / "docs" / "REFERENCE.md").read_text()) is not None)

print(f"\n{sum(ok)}/{len(ok)} model facts match the {EV.parent.name}/ capture")
sys.exit(0 if all(ok) else 1)
