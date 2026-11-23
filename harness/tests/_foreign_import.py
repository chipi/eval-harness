"""`evh import-run`, many times in one process: the same operation body the command runs (`ops.registry.OPS`), without
a process start for each. `python tests/_foreign_import.py spec.json` in the project's environment (EVAL_HOME, EVAL_STORE);
spec.json is a list of the command's inputs. Used by `_foreign.py`, which makes a few of its runs with the command itself."""

import contextlib
import functools
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import _fingerprint
from evaluation_harness.ops.registry import OPS

# The hash of the harness code is the same for every call of this process, and takes 0.4 s to work out each time.
_fingerprint.harness_code_sha256 = functools.cache(_fingerprint.harness_code_sha256)

for spec in json.loads(Path(sys.argv[1]).read_text()):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        code = OPS["import-run"].body(**spec)
    if code:
        sys.exit(f"import-run {spec.get('run_id')}: exit {code}: {out.getvalue()[-300:]}")
