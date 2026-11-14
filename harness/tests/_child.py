"""A test's child command, with its stacks dumped when it hangs.

Two source tests (test_hf_source, test_zenodo_openml) each saw one `dataset-create` hang past its 300 s timeout under
the full suite's load (2026-11-09, 2026-11-11), and 140 runs in a row did not repeat it. A hang is now a failure that
says where every thread of the child was: the child runs with faulthandler on, and on the timeout it is sent SIGABRT,
which makes it print each thread's stack before it dies.
"""

import os
import signal
import subprocess


def run(cmd: list, timeout: float = 300, **kw) -> subprocess.CompletedProcess:
    """subprocess.run(cmd, capture_output=True, text=True), but a child past `timeout` has its threads' stacks
    printed and the test fails with them (subprocess.TimeoutExpired, its stderr holding the stacks)."""
    env = dict(kw.pop("env", None) or os.environ, PYTHONFAULTHANDLER="1")
    p = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kw)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.send_signal(signal.SIGABRT)  # faulthandler: every thread's stack to stderr
        try:
            out, err = p.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            p.kill()
            out, err = p.communicate()
        print(
            f"  HUNG after {timeout:g} s: {' '.join(map(str, cmd))[:300]}\n  its stacks:\n{err[-12000:]}",
            flush=True,
        )
        raise subprocess.TimeoutExpired(cmd, timeout, output=out, stderr=err) from None
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)
