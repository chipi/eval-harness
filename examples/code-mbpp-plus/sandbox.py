"""Run model-written Python where it cannot reach the network or write outside a scratch dir.

Every other experiment here reads a model's output; this one EXECUTES it. A model asked to
"write a function" can write one that deletes files, opens sockets or forks forever -- not
out of malice, but because that is what code does when it is wrong. So the rule this module
exists to enforce is the experiment's one refusal:

    NEVER EXECUTE OUTSIDE THE SANDBOX.

There is no flag to turn it off. If neither backend below is available, or the self-probe
(`probe()`, run at warm-up) finds the sandbox leaking, the run stops before any model is
called and nothing is spent.

BACKENDS
  linux   `unshare --user --map-root-user --net --mount --pid --fork`: a fresh user, network,
          mount and pid namespace per execution. Inside it, the whole filesystem is
          bind-mounted read-only, a 64 MB tmpfs is the only writable place, and the code runs
          chrooted there. No network interface but loopback (down). Killing the namespace's
          first process kills everything the code spawned.
  macos   `sandbox-exec` with a profile that denies network, process forking, and every
          file write outside a fresh temporary directory.

ON TOP OF EITHER
  * a fresh process per execution (one for the base tests, one for the plus tests), so one
    item's leftovers cannot reach the next;
  * resource limits: CPU seconds, address space, file size, open files;
  * a wall-clock timeout, after which the whole process group is killed; a timeout is
    reported as `timeout`, not as `fail` (a slow CPU must not read as wrong code);
  * a clean environment: no API keys, no HOME, no PYTHONPATH; `python -I`.

The verdict comes back on stdout behind a random per-execution marker, so code that prints
cannot forge a pass, and code that exits early (sys.exit, os._exit) simply never reports one.
"""

from __future__ import annotations

import json
import os
import platform
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# The runner that executes inside the sandbox. Kept here, as a string, so its exact bytes are
# part of the adapter's code hash.
RUNNER = r'''
import json, sys, traceback
job = json.load(open(sys.argv[1]))
mark = job["marker"]
def report(status, detail=""):
    sys.__stdout__.write("\n" + mark + json.dumps({"status": status, "detail": detail[-400:]}) + "\n")
    sys.__stdout__.flush()
ns = {"__name__": "solution"}
try:
    exec(compile(job["code"], "solution.py", "exec"), ns)
except BaseException:
    report("error", traceback.format_exc()); raise SystemExit(0)
try:
    for line in job.get("imports") or []:
        exec(line, ns)
    exec(compile(job["test"], "test.py", "exec"), ns)
except AssertionError:
    report("fail", traceback.format_exc()); raise SystemExit(0)
except BaseException:
    report("error", traceback.format_exc()); raise SystemExit(0)
report("pass")
'''

# Inside the Linux namespaces: bind / read-only, a tmpfs as the only writable place, chroot.
_LINUX_SETUP = r'''
set -e
R=$(mktemp -d /tmp/mbpp-sbx.XXXXXX)
mount --rbind / "$R"
awk -v r="$R" '$5==r || index($5, r"/")==1 {print $5}' /proc/self/mountinfo |
  while read -r m; do mount -o remount,bind,ro "$m" 2>/dev/null || true; done
mount -t tmpfs -o size=64m,mode=1777 tmpfs "$R/tmp"
cp "$1" "$R/tmp/runner.py"; cp "$2" "$R/tmp/job.json"
shift 2
cd /
exec chroot "$R" /bin/sh -c 'cd /tmp && exec "$@" /tmp/runner.py /tmp/job.json' sh "$@"
'''

_MAC_PROFILE = """(version 1)
(allow default)
(deny network*)
(deny process-fork)
(deny file-write*)
(allow file-write* (subpath "{work}") (literal "/dev/null") (literal "/dev/dtracehelper"))
"""

LIMITS = {"cpu_s": None, "address_space_mb": 4096, "file_size_mb": 16, "open_files": 64}


def backend() -> Optional[str]:
    """Which sandbox this machine can provide, or None (and then nothing will execute)."""
    system = platform.system()
    if system == "Linux" and shutil.which("unshare"):
        try:
            ok = subprocess.run(["unshare", "--user", "--map-root-user", "--net", "--mount",
                                 "--pid", "--fork", "true"], capture_output=True, timeout=20)
            if ok.returncode == 0:
                return "linux-namespaces"
        except (OSError, subprocess.SubprocessError):
            pass
    if system == "Darwin" and shutil.which("sandbox-exec"):
        return "macos-sandbox-exec"
    return None


def _limits(cpu_s: int):
    def apply() -> None:
        import resource  # noqa: PLC0415 -- POSIX only, and only in the child

        os.setsid()
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (LIMITS["file_size_mb"] << 20,) * 2)
        resource.setrlimit(resource.RLIMIT_NOFILE, (LIMITS["open_files"],) * 2)
        if platform.system() == "Linux":  # macOS does not enforce RLIMIT_AS
            resource.setrlimit(resource.RLIMIT_AS, (LIMITS["address_space_mb"] << 20,) * 2)
    return apply


def execute(code: str, test: str, imports: Optional[List[str]] = None, *,
            timeout_s: float = 10.0, python: Optional[str] = None) -> Dict[str, Any]:
    """Run `code`, then `test` against it, in the sandbox. Returns
    {"status": pass|fail|error|timeout|crash, "detail": str, "seconds": float}."""
    kind = backend()
    if kind is None:
        raise SystemExit(
            "REFUSED: no sandbox on this machine (needs Linux user namespaces via `unshare`, "
            "or macOS `sandbox-exec`). This experiment executes model-written code and will "
            "not do it unconfined. Nothing was run.")
    py = python or sys.executable
    marker = "@@MBPP-" + secrets.token_hex(16) + "@@"
    with tempfile.TemporaryDirectory(prefix="mbpp-job-") as work:
        work = os.path.realpath(work)
        Path(work, "runner.py").write_text(RUNNER, encoding="utf-8")
        Path(work, "job.json").write_text(json.dumps(
            {"code": code, "test": test, "imports": imports or [], "marker": marker}),
            encoding="utf-8")
        if kind == "linux-namespaces":
            cmd = ["unshare", "--user", "--map-root-user", "--net", "--mount", "--pid", "--fork",
                   "--propagation", "private", "/bin/sh", "-c", _LINUX_SETUP, "sh",
                   f"{work}/runner.py", f"{work}/job.json", py, "-I"]
            cwd = "/"
        else:
            cmd = ["sandbox-exec", "-p", _MAC_PROFILE.format(work=work), py, "-I",
                   f"{work}/runner.py", f"{work}/job.json"]
            cwd = work
        env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "TMPDIR": "/tmp" if kind.startswith("linux") else work,
               "PYTHONHASHSEED": "0", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
        started = time.perf_counter()
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                preexec_fn=_limits(int(timeout_s) + 2))
        try:
            out, err = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.communicate()
            return {"status": "timeout", "detail": f"over {timeout_s:g}s wall clock",
                    "seconds": round(time.perf_counter() - started, 3)}
        seconds = round(time.perf_counter() - started, 3)
    text = out.decode("utf-8", "replace")
    for line in reversed(text.splitlines()):
        if line.startswith(marker):
            try:
                verdict = json.loads(line[len(marker):])
                verdict["seconds"] = seconds
                return verdict
            except json.JSONDecodeError:
                break
    # No verdict: the process died (memory, CPU limit, os._exit, a signal) or exited early.
    tail = err.decode("utf-8", "replace")[-400:]
    return {"status": "crash", "detail": f"exit {proc.returncode}: {tail}", "seconds": seconds}


# ── the self-probe: prove the sandbox holds before trusting it with model output ──────────
_PROBES = {
    "network": ("import socket\ndef f():\n    socket.create_connection(('1.1.1.1', 53), 3)\n",
                "f()"),
    "write_home": ("import os\ndef f(p):\n    open(p, 'w').write('x')\n", "f({path!r})"),
    "fork": ("import subprocess\ndef f():\n    subprocess.run(['/bin/true'], check=True)\n", "f()"),
    "runs_code": ("def add(a, b):\n    return a + b\n", "assert add(2, 3) == 5"),
    "catches_wrong_code": ("def add(a, b):\n    return a - b\n", "assert add(2, 3) == 5"),
    "timeout": ("def spin():\n    while True:\n        pass\n", "spin()"),
}


def probe(python: Optional[str] = None, sentinel_dir: Optional[Path] = None) -> Dict[str, str]:
    """Run code that SHOULD be stopped, and code that should run, and check each outcome.

    Raises SystemExit naming the leak if anything escapes. Returns the outcome per probe for
    the run's fingerprint. `sentinel_dir` is a real directory outside the sandbox's scratch
    space that the write probe tries to write into.
    """
    sentinel_dir = Path(sentinel_dir or Path.home())
    sentinel = sentinel_dir / f".mbpp-sandbox-probe-{secrets.token_hex(6)}"
    got: Dict[str, str] = {}
    for name, (code, test) in _PROBES.items():
        r = execute(code, test.format(path=str(sentinel)), python=python,
                    timeout_s=3.0 if name == "timeout" else 20.0)
        got[name] = r["status"]
    leaked = sentinel.exists()
    if leaked:
        sentinel.unlink()
    # Forking: macOS denies it outright; on Linux a child is allowed but lives and dies inside
    # the same pid, network and mount namespaces, so it can do nothing its parent cannot.
    fork_ok = {"error", "crash"} if backend() == "macos-sandbox-exec" else {"pass", "error", "crash"}
    want = {"network": {"error"}, "write_home": {"error"}, "fork": fork_ok,
            "runs_code": {"pass"}, "catches_wrong_code": {"fail"}, "timeout": {"timeout"}}
    bad = [f"{k}: got {got[k]}, expected {'/'.join(sorted(want[k]))}" for k in want if got[k] not in want[k]]
    if leaked:
        bad.append(f"write_home: a file appeared at {sentinel}")
    if bad:
        raise SystemExit("REFUSED: the sandbox self-probe failed, so no model-written code will "
                         "run on this machine:\n  " + "\n  ".join(bad))
    return got


if __name__ == "__main__":
    print(f"backend: {backend()}")
    print(json.dumps(probe(sentinel_dir=Path(__file__).resolve().parent), indent=1))
