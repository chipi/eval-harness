#!/usr/bin/env python3
"""Every part of data/ the catalog adapter reads is copied by the deployment's render.sh.

    python tests/test_render_data.py

0.4.2 added data/models.yaml (the arms page's weights) and render.sh never copied it, so the
deployed arms page called every model's weights unknown for two releases. This reads the names
`catalog_adapter.py` opens under its data_dir and checks each against the lists render.sh copies.
Item text (`materialized`) is left out on purpose; runs directories are copied as `runs*`.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness._check import check, summary  # noqa: E402

LEFT_OUT = {"materialized"}  # item text: never deployed

render = ROOT / "infra" / "deploy" / "render.sh"
if not render.is_file():  # an installed package has no infra/: nothing to check
    print("  --   render.sh not here (not a checkout)")
    sys.exit(0)
adapter = (ROOT / "harness" / "scripts" / "catalog_adapter.py").read_text(encoding="utf-8")
read = set(re.findall(r'data_dir / "([A-Za-z0-9_.-]+)"', adapter))
sh = render.read_text(encoding="utf-8")
copied = set()
for group in re.findall(r"harness/data/\{([^}]*)\}", sh):
    copied |= set(group.split(","))
copied |= set(re.findall(r"harness/data/([A-Za-z0-9_-]+\.(?:yaml|json))\b", sh))
runs_glob = "harness/data/runs*" in sh
for name in sorted(read - LEFT_OUT):
    ok = name in copied or (runs_glob and name.startswith("runs"))
    check(f"render.sh copies data/{name}, which the catalog adapter reads", ok, f"copied: {sorted(copied)}")
sys.exit(summary())
