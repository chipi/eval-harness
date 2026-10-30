#!/usr/bin/env python3
"""Every part of data/ the catalog adapter reads is copied by the deployment's data copy.

    python tests/test_render_data.py

0.4.2 added data/models.yaml (the arms page's weights) and render.sh never copied it, so the
deployed arms page called every model's weights unknown for two releases. This reads the names
`catalog_adapter.py` opens under its data_dir and checks each against what _release.py copies
(COPIED_DIRS, COPIED_FILES, every runs*), and that render.sh copies the data through it.
Item text (`materialized`) is left out on purpose.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness._release import COPIED_DIRS, COPIED_FILES  # noqa: E402

LEFT_OUT = {"materialized"}  # item text: never deployed

render = ROOT / "infra" / "deploy" / "render.sh"
if not render.is_file():  # an installed package has no infra/: nothing to check
    print("  --   render.sh not here (not a checkout)")
    sys.exit(0)
adapter = (ROOT / "harness" / "scripts" / "catalog_adapter.py").read_text(encoding="utf-8")
read = set(re.findall(r'data_dir / "([A-Za-z0-9_.-]+)"', adapter))
copied = set(COPIED_DIRS) | set(COPIED_FILES)
sh = render.read_text(encoding="utf-8")
check(
    "render.sh copies the data through _release.py copy-data",
    bool(re.search(r"_release\.py\"? copy-data \"\$ROOT/harness/data\"", sh)),
)
check(
    "render.sh copies no data directory itself", "harness/data/{" not in sh and "harness/data/runs*" not in sh
)
for name in sorted(read - LEFT_OUT):
    ok = name in copied or name.startswith("runs")
    check(f"the release copies data/{name}, which the catalog adapter reads", ok, f"copied: {sorted(copied)}")
check("the release never copies materialized items", not (copied & LEFT_OUT))
sys.exit(summary())
