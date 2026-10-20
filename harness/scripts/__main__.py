"""`python -m eval_harness <command>`, the same as the `eval-harness` command."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cli import main  # noqa: E402

raise SystemExit(main())
