"""Print one `run:` step of a workflow as a bash script, its `env:` exported and every `${{ }}` supplied.

    workflow_step.py WORKFLOW.yml JOB "STEP NAME" [--sub inputs.sha=abc ...]

The way a runner would run it, so a step's guard can be proven locally as a pass case and a fail case
(infra/deploy/test_dispatch.sh). An expression with no --sub is refused (exit 4) rather than run empty.
"""

import re
import shlex
import sys
from pathlib import Path

import yaml

EXPR = re.compile(r"\$\{\{\s*(.*?)\s*\}\}")


def main(argv: list) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # bash reads this as the script: UTF-8, whatever the locale
    path, job, name, *rest = argv
    subs = dict(a.split("=", 1) for a in rest if "=" in a)
    steps = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["jobs"][job]["steps"]
    step = next(s for s in steps if s.get("name") == name)

    def sub(text: str) -> str:
        def one(m: re.Match) -> str:
            if m.group(1) not in subs:
                print(f"workflow_step.py: no --sub for ${{{{ {m.group(1)} }}}}", file=sys.stderr)
                raise SystemExit(4)
            return subs[m.group(1)]

        return EXPR.sub(one, str(text))

    for key, val in (step.get("env") or {}).items():
        print(f"export {key}={shlex.quote(sub(val))}")
    print(sub(step["run"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
