"""evaluation-harness: frozen datasets, run fingerprints, paired significance tests.

Installed, this directory is the `evaluation_harness` package and `evh <command>` runs
its scripts (see cli.py). In a checkout the same files run directly through the Makefile.
The scripts import each other as top-level modules, so use them through the CLI rather
than importing this package's modules one by one.
"""

from ._version import __version__  # noqa: F401
