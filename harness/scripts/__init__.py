"""evaluation-harness: frozen datasets, run fingerprints, paired significance tests.

Installed, this directory is the `evaluation_harness` package and `evh <command>` runs
its scripts (see cli.py). In a checkout the same files run directly through the Makefile.
The modules import each other as this package (`from evaluation_harness._common import ...`),
never as bare top-level names: a project's own `stats.py` or `adapter.py` cannot replace the
harness's, and the harness's cannot replace a project's. Run as files from a checkout
(`python scripts/x.py`), each puts the package's parent on sys.path itself; in a checkout
that is harness/, where `evaluation_harness` is a link to scripts/.
"""

from evaluation_harness._version import __version__  # noqa: F401
