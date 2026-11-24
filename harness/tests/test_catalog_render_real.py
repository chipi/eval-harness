#!/usr/bin/env python3
"""The catalog of this repository's own runs, rendered one page at a time, is its export (RFC-040).

    python tests/test_catalog_render_real.py

tests/test_catalog_render.py checks the two drivers on a tutorial project in either store; this file checks them where
the pages are many and varied: 7 goals, 673 arms, the redirects of renamed arms, a dataset's item pages, the scorers'
and models' pages. Every page is rendered on its own from a fresh model, in a shuffled order (no page may lean on one
rendered before it), and must be the exported file byte for byte; every exported file's group is the one its path
names. RFC-040 test 2, here where the p's are many: that holds with the p-value cache on and full (the export's), off
(every p drawn), and on and empty (every p drawn and written); and a sample of pages fetched over HTTP from a real
`evh catalog-serve` process, with the cache off and with it on, are the export's, but for the footer's time (another
process's clock). $0 and offline: it reads the committed runs.
"""

import os
import random
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/
import _render_proj  # noqa: E402
import _serve  # noqa: E402
from evaluation_harness import _common, _models  # noqa: E402
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
    reads: Counter = Counter()
    read = _models._read

    def counted(f: Path):
        reads[Path(f).as_posix()] += 1
        return read(f)

    _models._read = counted
    t = time.monotonic()
    try:
        differ = [p for p in order if fresh.page(p) != exported[p]]
    finally:
        _models._read = read
    served_s = time.monotonic() - t
    check(
        f"every page rendered on its own, in a shuffled order, is the exported file ({served_s:.0f} s)",
        not differ,
        differ[:5],
    )
    again = sorted(f for f, n in reads.items() if n > 1)
    check(
        "a model's record is read once per model of the data, not once per page that shows it (a goal's deploy sheet)",
        bool(reads) and not again,
        (len(reads), again[:3], max(reads.values(), default=0)),
    )
    check("an arm that is not there is no page", fresh.page("a/no-such-arm.html") is None)
    recorded = sorted(p for p, html in exported.items() if 'class="badge recorded"' in html)
    check(
        "the recorded arms' badges are in the export, so the passes here compare them",
        len(recorded) > 1,
        len(recorded),
    )

    # ── the p-value cache changes no byte (RFC-040 test 2) ──────────────────────────────────────────────────────────
    cache_file = os.environ["EVH_P_CACHE"]  # the export's: full
    scratch = Path(tempfile.mkdtemp(prefix="evh-render-p-"))
    try:
        for what, path in (
            ("off (every p drawn)", ""),
            ("on and empty (every p drawn and written)", str(scratch / "p.jsonl")),
        ):
            _render_proj.p_cache(path)
            t = time.monotonic()
            drawn = cb.prepare(load_catalog_adapter(None), built=BUILT)
            differ = [p for p in order if drawn.page(p) != exported[p]]
            check(
                f"every page rendered on its own with the p-value cache {what} is the export made with it full ({time.monotonic() - t:.0f} s)",
                not differ,
                differ[:5],
            )
        stored = (
            len((scratch / "p.jsonl").read_text(encoding="utf-8").splitlines())
            if (scratch / "p.jsonl").is_file()
            else 0
        )
        check(
            "the empty cache was filled by that pass: the p's compared were drawn, not stored",
            stored > 100,
            stored,
        )
    finally:
        _render_proj.p_cache(cache_file)
        shutil.rmtree(scratch, ignore_errors=True)

    # ── a sample over HTTP, from a real server, the cache off and on ────────────────────────────────────────────────
    kinds = {}
    for p, g in wrote.items():
        kinds.setdefault(g.partition(":")[0], []).append(p)
    sample = sorted(
        {
            "index.html",
            *recorded[:3],
            *(q for ps in kinds.values() for q in random.Random(3).sample(sorted(ps), min(2, len(ps)))),
        }
        | set(random.Random(4).sample(order, 40))
    )
    scratch = Path(tempfile.mkdtemp(prefix="evh-render-http-"))
    try:
        for what, path in (
            ("off", ""),
            ("on and empty", str(scratch / "p.jsonl")),
            ("on and full", cache_file),
        ):
            proc, port, lines = _serve.start(HARNESS, {**os.environ, "EVH_P_CACHE": path})
            try:
                prefix = next(
                    (
                        m.group(1)
                        for ln in lines
                        if (m := re.search(r"catalog: http://127\.0\.0\.1:\d+(\S*)", ln))
                    ),
                    "/",
                )
                got: dict[str, tuple] = {}
                t = time.monotonic()
                for p in sample:
                    req = urllib.request.Request(
                        f"http://127.0.0.1:{port}{prefix}{p}", headers={"Host": f"127.0.0.1:{port}"}
                    )
                    try:
                        with urllib.request.urlopen(req, timeout=300) as r:  # noqa: S310 - the test's own server  # nosec B310
                            got[p] = (r.status, r.read().decode("utf-8"))
                    except urllib.error.HTTPError as exc:
                        got[p] = (exc.code, "")
                differ = [
                    p
                    for p in sample
                    if got[p][0] != 200
                    or _render_proj.mask_built(got[p][1]) != _render_proj.mask_built(exported[p])
                ]
                check(
                    f"{len(sample)} pages over HTTP from a real server, the p-value cache {what}, are the export's ({time.monotonic() - t:.0f} s)",
                    not differ,
                    [(p, got[p][0]) for p in differ[:5]],
                )
            finally:
                _serve.stop(proc)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
finally:
    shutil.rmtree(out.parent, ignore_errors=True)
sys.exit(summary())
