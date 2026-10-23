"""`python -m evaluation_harness <command>`, the same as the `evh` command."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cli import main

raise SystemExit(main())
