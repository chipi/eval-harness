"""Readers that run in a process of their own, for test_reader_agreement.py, with an optional stub applied first.

    python tests/_reader_proc.py build NAME DIR                  one of the test's projects (_agree_projects.py), built in DIR
    python tests/_reader_proc.py mcp OUT.json [--stub NAME]      the MCP server's read operations, in this process
    python tests/_reader_proc.py evh [--stub NAME] -- <evh args>  `evh <args>` in this process (the catalog build, a server)

`mcp` answers what `facts_dump.collect` asks through `mcp_server.run_op`, the function every MCP tool call runs (a public
call for `public=True`), and writes the facts it found. The project is the environment's (EVAL_HOME, EVAL_STORE). `evh`
is the command with a stub applied before it runs: a stub (`_reader_stubs.py`) is a reader made to work a fact out
itself, which the check must then catch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HARNESS / "tools"))
import _reader_stubs  # noqa: E402
import facts_dump as FD  # noqa: E402


def mcp(out: Path) -> int:
    from evaluation_harness import mcp_server  # noqa: PLC0415
    from evaluation_harness.ops import OPS  # noqa: PLC0415

    def read(op: str, public: bool = False, **params: Any) -> dict[str, Any]:
        spec = OPS.get(op)
        if spec is None or spec.kind != "read":
            raise FD.Unavailable(f"{op}: not a read operation of the MCP server")
        if public and spec.public_dropped:
            raise FD.Unavailable(f"{op}: not offered by a public MCP server")
        try:
            return dict(mcp_server.run_op(spec, params, public)["result"])
        except Exception as exc:  # noqa: BLE001 - a refusal is an answer the check records, whatever its type
            raise FD.Unavailable(f"{op}: {type(exc).__name__}: {str(exc)[:160]}") from None

    c = FD.collect(read, jobs=1)
    out.write_text(
        json.dumps(
            {
                "facts": {r: [[k, list(key), v] for (k, key), v in d.items()] for r, d in c.facts.items()},
                "why": c.why,
            }
        )
    )
    return 0


def main(argv: list[str]) -> int:
    stub = None
    if "--stub" in argv:
        i = argv.index("--stub")
        stub = argv[i + 1]
        argv = argv[:i] + argv[i + 2 :]
    if stub:
        _reader_stubs.apply(stub)
    if argv and argv[0] == "build":
        import _agree_projects  # noqa: PLC0415

        print(json.dumps(_agree_projects.build(argv[1], Path(argv[2])), default=str))
        return 0
    if argv and argv[0] == "mcp":
        return mcp(Path(argv[1]))
    if argv and argv[0] == "evh":
        from evaluation_harness import cli  # noqa: PLC0415

        return int(cli.main([a for a in argv[1:] if a != "--"]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
