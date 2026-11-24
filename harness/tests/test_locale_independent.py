#!/usr/bin/env python3
"""The harness does not depend on the locale's encoding. $0, offline.

  EVAL_STORE=files python tests/test_locale_independent.py        (and EVAL_STORE=sqlite)

Run under a console that cannot encode "—", "×" or "→" (LC_ALL=C, no UTF-8 mode, no locale coercion: what a
Windows console or an ISO-8859 box is for these purposes), `evh validate` ended in a UnicodeEncodeError traceback,
`tools/store_matrix.py` crashed printing its own summary line, and a file read without an encoding was read as
ASCII. Now a character the console cannot encode is printed as its backslash escape, a console that is UTF-8 is
left alone, and every text file the harness reads or writes is UTF-8 whatever the locale says.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HERE))
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness._check import check, store_under_test, summary  # noqa: E402

TEXT = "café — × → done\n"
ESCAPED = "\\u2014"  # what the console that cannot encode "—" is shown

proj = Path(tempfile.mkdtemp(prefix="evh-locale-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-locale", EVAL_MAX_RETRIES="0")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "PYTHONIOENCODING", "LC_CTYPE", "LANGUAGE"):
    env.pop(k, None)
env.update(LC_ALL="C", LANG="C", PYTHONCOERCECLOCALE="0", PYTHONUTF8="0")


def evh(*args):
    return _cli.run(proj, env, *args)


def child(argv, **kw):
    return subprocess.run(
        argv,
        cwd=proj,
        env=kw.pop("env", env),
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=300,
        **kw,
    )


def clean(r):
    """The command ended without a traceback, whatever it printed."""
    both = r.stdout + r.stderr
    return r.returncode == 0 and "Traceback" not in both and "UnicodeEncodeError" not in both


try:
    probe = child(
        [sys.executable, "-c", "import sys; print(sys.stdout.encoding, sys.getfilesystemencoding())"],
        text=True,
        encoding="utf-8",
    )
    check(
        "the environment under test is not UTF-8 (else this test proves nothing)",
        probe.stdout.split()[0].lower().replace("-", "") != "utf8",
        probe.stdout + probe.stderr,
    )

    r = evh("init", "--store", store_under_test())
    check("init under a non-UTF-8 locale", clean(r), r.stdout[-300:] + r.stderr[-600:])

    r = evh("validate")
    check(
        "evh validate prints its em dashes without a traceback", clean(r), r.stdout[-300:] + r.stderr[-800:]
    )
    check(
        "an unencodable character is printed as its escape, not dropped", ESCAPED in r.stdout, r.stdout[:400]
    )
    check("validate still says it passed", "VALIDATION PASSED" in r.stdout, r.stdout[-300:])

    r = evh("--help")
    check("evh --help works", clean(r) and "usage: evh" in r.stdout, r.stderr[-300:])

    (proj / "src").mkdir()
    (proj / "src" / "a.txt").write_text(TEXT, encoding="utf-8")
    (proj / "src" / "b.txt").write_text("second é\n", encoding="utf-8")
    r = evh("dataset-create", "--dataset-id", "d_v1", "--source-dir", "src")
    check("a dataset of non-ASCII text is created", clean(r), r.stdout[-300:] + r.stderr[-600:])
    r = evh("dataset-materialize", "--dataset-id", "d_v1")
    check(
        "and materialized, its hashes verified",
        clean(r) and "all hashes verified" in r.stdout,
        r.stdout[-300:] + r.stderr[-600:],
    )
    got = _runstore.read_bytes(proj, "materialized/d_v1/a.txt")
    check("the text read back is the text written, byte for byte", got == TEXT.encode("utf-8"), got)

    log = proj / "matrix-logs"
    r = child(
        [
            sys.executable,
            str(HARNESS / "tools" / "store_matrix.py"),
            "--only",
            "no_such_test_*.py",
            "--store",
            "files",
            "--log",
            str(log),
        ],
        text=True,
        encoding="utf-8",
    )
    check(
        "store_matrix prints its summary line (with its ×) without a traceback",
        clean(r),
        r.stdout[-300:] + r.stderr[-800:],
    )
    check(
        "and says so in its own words",
        "STORE MATRIX: PASS" in r.stdout and "0 test files" in r.stdout,
        r.stdout[-300:],
    )

    script = proj / "probe.py"
    script.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(HARNESS)!r})\n"
        "from evaluation_harness._console import degrade_unencodable\n"
        "if sys.argv[1:] == ['degrade']:\n"
        "    degrade_unencodable()\n"
        "print('a \\u00d7 b \\u2014 c')\n"
        "print('d \\u2192 e', file=sys.stderr)\n",
        encoding="utf-8",
    )
    plain = child([sys.executable, str(script)])
    check(
        "without the helper, the same print is the crash this guards against",
        plain.returncode != 0 and b"UnicodeEncodeError" in plain.stderr,
        plain.stderr[-300:],
    )
    r = child([sys.executable, str(script), "degrade"])
    check(
        "with it, stdout and stderr degrade to escapes and exit 0",
        r.returncode == 0 and r.stdout == b"a \\xd7 b \\u2014 c\n" and r.stderr == b"d \\u2192 e\n",
        (r.stdout, r.stderr),
    )
    r = child([sys.executable, str(script), "degrade"], env=dict(env, PYTHONIOENCODING="utf-8"))
    check(
        "a UTF-8 console is not touched: the characters themselves",
        r.returncode == 0 and r.stdout == "a × b — c\n".encode(),
        r.stdout,
    )

    import io

    from evaluation_harness._console import degrade_unencodable, dump_json

    saved = sys.stdout
    sys.stdout = io.StringIO()
    try:
        degrade_unencodable()
        ok = True
    except Exception:  # noqa: BLE001 - the check reports it
        ok = False
    finally:
        sys.stdout = saved
    check("a stream that cannot be reconfigured is left as it is", ok)

    doc = {"text": "a \u00d7 b \u2014 c"}
    for enc, want in (
        ("ascii", '{"text": "a \\u00d7 b \\u2014 c"}'),
        ("utf-8", json.dumps(doc, ensure_ascii=False)),
    ):
        sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding=enc)
        try:
            dumped = dump_json(doc)
        finally:
            sys.stdout = saved
        check(
            f"--json to a {enc} console is valid JSON, escaped only where it must be",
            dumped == want and json.loads(dumped) == doc,
            dumped,
        )
    r = evh("validate", "--json")
    ok = r.returncode == 0 and "Traceback" not in r.stderr
    check(
        "evh validate --json is parseable under the non-UTF-8 locale",
        ok and json.loads(r.stdout)["command"] == "validate",
        r.stdout[:200] + r.stderr[-300:],
    )

    # A harness process that parses another's answer: the parent's console encoding does not reach the child's pipe.
    from evaluation_harness import _cmdline, _spend

    echo = proj / "echo.py"
    echo.write_text("print('x\\u00e9 \\u2014 \\u00d7')\n", encoding="utf-8")
    (proj / "fakecli").mkdir()
    (proj / "fakecli" / "cli.py").write_text(echo.read_text(encoding="utf-8"), encoding="utf-8")
    want = "x\u00e9 \u2014 \u00d7"
    saved_env = os.environ.get("PYTHONIOENCODING")
    os.environ["PYTHONIOENCODING"] = "cp1252:replace"
    saved_here = _cmdline.HERE
    try:
        done, _paid = _spend.run_child(
            [sys.executable, str(echo)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            stdin=subprocess.DEVNULL,
        )
        check(
            "run_child reads an \u00e9 \u2014 \u00d7 exactly from a child, the parent's console being cp1252",
            done.stdout.strip() == want,
            done.stdout,
        )
        _cmdline.HERE = proj / "fakecli"
        code, out, err = _cmdline._run(proj, [], 60, None)
        check(
            "_cmdline reads the same exactly, the parent's console being cp1252",
            code == 0 and out.strip() == want,
            (code, out, err),
        )
    finally:
        _cmdline.HERE = saved_here
        if saved_env is None:
            os.environ.pop("PYTHONIOENCODING", None)
        else:
            os.environ["PYTHONIOENCODING"] = saved_env
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
