"""A process that runs `evh <args>` for a test, one request after another, so the package is imported once (`_cli.Session`).

Requests are JSON lines on stdin, `{"argv": [...], "public": true | false | null}`; each is answered by a JSON line on a
channel of its own, `{"rc": n, "out": "...", "err": "..."}`. A command's own printing is captured: it goes to a
buffer, never to the channel.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))


ENCODING = sys.stdout.encoding or "utf-8"


def capture() -> io.TextIOWrapper:
    """A stream as the console is: the console's encoding, so a character it cannot hold is what `degrade_unencodable` makes of it."""
    return io.TextIOWrapper(io.BytesIO(), encoding=ENCODING, write_through=True)


def text(stream: io.TextIOWrapper) -> str:
    stream.flush()
    return stream.buffer.getvalue().decode(ENCODING, errors="replace")  # type: ignore[attr-defined]


def main() -> int:
    channel = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(os.open(os.devnull, os.O_WRONLY), 1)
    from evaluation_harness import cli  # noqa: PLC0415

    started_as = os.environ.get("EVH_PUBLIC")
    requests, sys.stdin = sys.stdin, io.StringIO("")
    for line in requests:
        req = json.loads(line)
        public = started_as if req["public"] is None else "1" if req["public"] else None
        if public is None:
            os.environ.pop("EVH_PUBLIC", None)
        else:
            os.environ["EVH_PUBLIC"] = public
        out, err = capture(), capture()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(list(req["argv"]))
        channel.write(json.dumps({"rc": rc, "out": text(out), "err": text(err)}) + "\n")
        channel.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
