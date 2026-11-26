#!/usr/bin/env python3
"""Every parquet read in the harness and its examples runs on the calling thread, with neither of pyarrow's pools.

    python tests/test_parquet_reads.py

`use_threads=False` keeps pyarrow's CPU pool out; `pre_buffer=False` keeps its I/O pool out. With pre-buffering on,
a read from a Python file object (io.BytesIO) leaves a background read holding a Python buffer: when the process
exits first (`evh source-preview --rows 2` stops early), that thread takes the GIL during finalization and the process
aborts in pyarrow 26 (SIGABRT; the store matrix, 2026-11-26: core dump of `source-preview`, an arrow ThreadPool
thread in ReadRangeCache -> PyBuffer::~PyBuffer -> PyGILState_Ensure -> pthread_exit -> std::terminate).
"""

import ast
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
ROOT = HARNESS.parent
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

READERS = ("read_table", "ParquetFile", "ParquetDataset", "iter_batches")
found = []
for base in (HARNESS / "scripts", ROOT / "examples"):
    for f in sorted(base.rglob("*.py")):
        if ".venv" in f.parts or "node_modules" in f.parts:
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"), str(f))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name not in READERS:
                continue
            kw = {k.arg: k.value for k in node.keywords}
            off = all(
                isinstance(v := kw.get(k), ast.Constant) and v.value is False
                for k in ("use_threads", "pre_buffer")
            )
            found.append((f"{f.relative_to(ROOT)}:{node.lineno} {name}", off))

check(
    "the scan finds the harness's parquet reads (sources/huggingface.py, sources/_tables.py)",
    len(found) >= 3,
    found,
)
for where, off in found:
    check(f"{where}: use_threads=False and pre_buffer=False", off)
sys.exit(summary())
