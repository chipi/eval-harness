"""evaluation-harness: frozen datasets, run fingerprints, paired significance tests.

Installed, this directory is the `evaluation_harness` package and `evh <command>` runs
its scripts (see cli.py). In a checkout the same files run directly through the Makefile.
The scripts import each other as top-level modules (`from _common import ...`), the way
they run from a checkout. So that `import evaluation_harness.catalog_adapter` (INTEGRATION.md)
or `evaluation_harness.judging` resolves those imports, this directory goes on sys.path, at
the END: a project's own `adapter.py` or `stats.py` still wins over the harness's. Without
it, `evaluation_harness.judging` did not import at all, and a module that tried
`from ._common` first loaded `_common` a second time beside the top-level one.
"""

import sys as _sys
from pathlib import Path as _Path

if str(_Path(__file__).resolve().parent) not in _sys.path:
    _sys.path.append(str(_Path(__file__).resolve().parent))

from _version import __version__  # noqa: F401
