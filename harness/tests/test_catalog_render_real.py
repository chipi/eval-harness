#!/usr/bin/env python3
"""The catalog of this repository's own runs, rendered one page at a time, is its export (RFC-040).

    python tests/test_catalog_render_real.py

tests/test_catalog_render.py checks the two drivers on a tutorial project in either store; this file checks them where
the pages are many and varied: 7 goals, 673 arms, the redirects of renamed arms, a dataset's item pages, the scorers'
and models' pages. Every page is rendered on its own from a fresh model, in a shuffled order (no page may lean on one
rendered before it), and must be the exported file byte for byte; every exported file's group is the one its path
names. $0 and offline: it reads the committed runs.
"""

import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness import _common  # noqa: E402
from evaluation_harness import catalog_build as cb  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.catalog_adapter import load_catalog_adapter  # noqa: E402

BUILT = "2026-11-23 12:00 UTC"
_common.use_p_cache()  # as `evh` and the server do: the p-values drawn once

out = Path(tempfile.mkdtemp(prefix="evh-render-real-")) / "catalog"
try:
    t = time.monotonic()
    site = cb.prepare(load_catalog_adapter(None), built=BUILT)
    wrote = site.export(out)
    export_s = time.monotonic() - t
    exported = {
        p.relative_to(out).as_posix(): p.read_text(encoding="utf-8")
        for p in out.rglob("*")
        if p.is_file() and p.relative_to(out).parts[0] != "assets"
    }
    check(
        f"the export wrote {len(exported)} pages, every one through a group ({export_s:.0f} s)",
        set(exported) == set(wrote) and len(exported) > 1000,
        (len(exported), len(wrote)),
    )
    check(
        "the redirects, a dataset's item pages, the models' and the scorers' pages are among them",
        any(wrote[p] == "redirects" for p in wrote)
        and any("~items-" in p for p in wrote)
        and any(p.startswith("models/") for p in wrote)
        and any(p.startswith("scorers/") for p in wrote),
        sorted({g.partition(":")[0] for g in wrote.values()}),
    )

    fresh = cb.prepare(load_catalog_adapter(None), built=BUILT)
    misowned = sorted((p, g, fresh.owner(p)) for p, g in wrote.items() if fresh.owner(p) != g)
    check("every exported page's group is the one its path names", not misowned, misowned[:5])

    order = sorted(exported)
    random.Random(40).shuffle(order)
    t = time.monotonic()
    differ = [p for p in order if fresh.page(p) != exported[p]]
    served_s = time.monotonic() - t
    check(
        f"every page rendered on its own, in a shuffled order, is the exported file ({served_s:.0f} s)",
        not differ,
        differ[:5],
    )
    check("an arm that is not there is no page", fresh.page("a/no-such-arm.html") is None)
finally:
    shutil.rmtree(out.parent, ignore_errors=True)
sys.exit(summary())
