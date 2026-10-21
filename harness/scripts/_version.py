"""The harness's own version.

A run records it in `fingerprint.instrument.harness.version`, beside a content hash of the
harness code, because the git commit a run records is the commit of the PROJECT it ran in.
For a project that installs the harness as a dependency, that commit says nothing about
which harness produced the number. Bump it on every change that can move a result.
"""

__version__ = "0.4.0"
