#!/usr/bin/env python3
"""A system names the file its provider key comes from (`key_file`, 0.8.2): $0, offline.

    python tests/test_key_file.py

A throwaway project with systems on a fake OpenAI-shaped server that keeps each call's Authorization header: each system's
request carries the key of its own file; the order is key_file, then the shell, then .env; a missing, unreadable or
mistyped key_file is refused before any call, naming the file and the system; a key file inside a git checkout and not
ignored is warned about; the dry run and env-check say where each key comes from; the file's path is outside every
identity hash; and no key's value is in anything the harness printed or wrote. Keys here are fake, low-entropy strings.
"""

from __future__ import annotations

import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parents[1]
KIT = HARNESS / "tutorial"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore, _cli
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _fingerprint, _providers  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

SEEN: list[str] = []

KEY_A, KEY_B = "sk-test-a-not-printed", "sk-test-b-not-printed"
KEY_SHELL, KEY_DOTENV = "sk-test-shell-not-printed", "sk-test-dotenv-not-printed"
KEY_PROXY = "sk-test-proxy-not-printed"
ALL_KEYS = (KEY_A, KEY_B, KEY_SHELL, KEY_DOTENV, KEY_PROXY)


class Fake(http.server.BaseHTTPRequestHandler):
    """An OpenAI-shaped server: keeps the bearer each call carried, answers one line."""

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers["Content-Length"]))
        SEEN.append(str(self.headers.get("Authorization", "")).removeprefix("Bearer "))
        data = json.dumps({
            "id": "x", "object": "chat.completion", "created": 0, "model": "fake",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "a summary"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
        }).encode()  # fmt: skip
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a: Any) -> None:
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{server.server_address[1]}/v1"

proj = Path(tempfile.mkdtemp(prefix="evh-keyfile-"))
outside = Path(tempfile.mkdtemp(prefix="evh-keyfile-out-"))
env = dict(
    os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), HOME=str(outside), OPENAI_API_KEY=KEY_SHELL
)
for k in (
    "EVAL_DATA_DIR",
    "EVAL_GOALS_DIR",
    "EVAL_MAX_COST_USD",
    "EVAL_JUDGE_OPENAI_API_KEY",
    "OPENAI_BASE_URL",
):
    env.pop(k, None)
os.environ.setdefault("EVAL_STORE", "files")
env["EVAL_STORE"] = os.environ["EVAL_STORE"]
printed: list[str] = []  # everything the commands said


def evh(*args: str, with_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    r = _cli.run(proj, with_env or env, *args)
    printed.append(r.stdout + r.stderr)
    return r


def smoke(system: str, **kw: Any) -> tuple[subprocess.CompletedProcess, list[str]]:
    """arm-smoke one item of `system`: the process and the bearers the fake saw."""
    SEEN.clear()
    r = evh("arm-smoke", "--system", system, "--dataset", "tk_v1", "--items", "1", **kw)
    return r, list(SEEN)


def system(sid: str, key_file: Any = None, adapter: str | None = None) -> None:
    kf = "" if key_file is None else f"  key_file: {json.dumps(key_file)}\n"
    ad = "" if adapter is None else f"adapter: {adapter}\n"
    _runstore.write_text(
        proj,
        f"systems/{sid}.yaml",
        f"system_id: {sid}\n{ad}params:\n  provider: openai\n  model: fake\n  base_url: {BASE}\n{kf}"
        "  usd_per_mtok_in: 0\n  usd_per_mtok_out: 0\n",
    )


def carried(seen: list[str], key: str) -> bool:
    """Every call of the smoke (it calls an item twice, to see whether the output repeats) carried this key."""
    return bool(seen) and set(seen) == {key}


def said(r: subprocess.CompletedProcess) -> str:
    return r.stdout + r.stderr


try:
    r = evh("init", "--store", env["EVAL_STORE"], "--tutorial")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    for step in (
        ("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets"),
        ("dataset-materialize", "--dataset-id", "tk_v1"),
        ("label-import", "--sheet", str(KIT / "gold"), "--dataset-id", "tk_v1", "--set", "g", "--by", "t"),
        ("reference-promote", "--dataset-id", "tk_v1", "--labels", "g", "--tier", "gold", "--reason",
         "the kit's summaries, for the test", "--by", "t"),
    ):  # fmt: skip
        r = r if r.returncode else evh(*step)
    check("setup: a dataset with its reference", r.returncode == 0, r.stderr[-300:])

    (proj / ".env").write_text(f"OPENAI_API_KEY={KEY_DOTENV}\n", encoding="utf-8")
    (proj / "keys").mkdir()
    (proj / "keys" / "a.env").write_text(f"# a's key\nOPENAI_API_KEY={KEY_A}\n", encoding="utf-8")
    (outside / "b.env").write_text(f'OPENAI_API_KEY="{KEY_B}"\n', encoding="utf-8")
    (proj / "keys" / "other.env").write_text("SOMETHING_ELSE=1\n", encoding="utf-8")
    system("sys_a", "keys/a.env")
    system("sys_b", "~/b.env")
    system("sys_plain")
    system("sys_nokey", "keys/other.env")

    # ── each system's request carries its own file's key ─────────────────────
    r, seen = smoke("sys_a")
    check("a relative key_file: the request carries that file's key, not the shell's or .env's",
          r.returncode == 0 and carried(seen, KEY_A), (said(r)[-300:], seen))  # fmt: skip
    r, seen = smoke("sys_b")
    check("a key_file under ~ (HOME expanded), outside the project: its own key",
          r.returncode == 0 and carried(seen, KEY_B), (said(r)[-300:], seen))  # fmt: skip
    absolute = str(outside / "b.env")
    system("sys_abs", absolute)
    r, seen = smoke("sys_abs")
    check(
        "an absolute key_file path works the same",
        r.returncode == 0 and carried(seen, KEY_B),
        (said(r)[-300:], seen),
    )

    # ── the order: key_file, shell, .env ─────────────────────────────────────
    r, seen = smoke("sys_plain")
    check(
        "no key_file: the shell's key wins over .env's, as before",
        carried(seen, KEY_SHELL),
        (said(r)[-300:], seen),
    )
    no_shell = {k: v for k, v in env.items() if k != "OPENAI_API_KEY"}
    SEEN.clear()
    r = evh("arm-smoke", "--system", "sys_plain", "--dataset", "tk_v1", "--items", "1", with_env=no_shell)
    check(
        "no key_file, nothing exported: .env's key",
        carried(list(SEEN), KEY_DOTENV),
        (said(r)[-300:], list(SEEN)),
    )
    r, seen = smoke("sys_nokey")
    check("a key_file without the variable: the shell's key is used (key_file, then shell)",
          carried(seen, KEY_SHELL), (said(r)[-300:], seen))  # fmt: skip
    SEEN.clear()
    r = evh("arm-smoke", "--system", "sys_a", "--dataset", "tk_v1", "--items", "1", with_env=no_shell)
    check("key_file also beats .env", carried(list(SEEN), KEY_A), (said(r)[-300:], list(SEEN)))

    # ── refusals: before any call, naming the file and the system ────────────
    system("sys_missing", "keys/nope.env")
    system("sys_dir", "keys")
    system("sys_typed", 5)
    for sid, named in (("sys_missing", "keys/nope.env"), ("sys_dir", "keys"), ("sys_typed", "key_file")):
        for cmd in (("arm-smoke", "--items", "1"), ("run",), ("run", "--dry-run")):
            SEEN.clear()
            r = evh(cmd[0], "--system", sid, "--dataset", "tk_v1", *cmd[1:])
            out = said(r)
            check(
                f"{sid}: `{' '.join(cmd)}` is refused (not-configured) naming the file and the system, no call made",
                r.returncode != 0
                and "ERROR (not-configured)" in out
                and named in out
                and sid in out
                and not SEEN,
                (out[-400:], SEEN),
            )

    # ── the warning: a key file in the project, in a git checkout, not ignored ──
    git = subprocess.run(["git", "init", "-q", str(proj)], capture_output=True, text=True, encoding="utf-8")
    r, _ = smoke("sys_a")
    check("a key file inside the project and not gitignored: a WARNING that a key file must not be committed",
          "WARNING" in said(r) and "must not be committed" in said(r) and "keys/a.env" in said(r),
          (git.returncode, said(r)[-400:]))  # fmt: skip
    r, _ = smoke("sys_b")
    check(
        "a key file outside the project: no warning", "must not be committed" not in said(r), said(r)[-300:]
    )
    with (proj / ".gitignore").open("a", encoding="utf-8") as ignore:
        ignore.write("\nkeys/\n")
    r, seen = smoke("sys_a")
    check("the same file once ignored: no warning, and the call still carries its key",
          "must not be committed" not in said(r) and carried(seen, KEY_A), (said(r)[-300:], seen))  # fmt: skip

    # ── the dry run says where each key comes from ───────────────────────────
    for sid, where in (
        ("sys_a", "key_file keys/a.env"),
        ("sys_b", "key_file ~/b.env"),
        ("sys_plain", "shell"),
    ):
        SEEN.clear()
        r = evh("run", "--system", sid, "--dataset", "tk_v1", "--dry-run")
        check(f"the dry run of {sid} says its key comes from: {where}",
              r.returncode == 0 and "OPENAI_API_KEY" in r.stdout and where in r.stdout and not SEEN,
              (r.stdout[:600], r.stderr[-200:]))  # fmt: skip

    # ── env-check: per system and key, which file; never the value ───────────
    r = evh("env-check")
    out = r.stdout
    check("env-check: each system's key and where it came from (key_file, shell)",
          all(s in out for s in ("sys_a", "sys_b", "key_file keys/a.env", "key_file ~/b.env")),
          out[-1800:])  # fmt: skip
    files_line = next((ln for ln in out.splitlines() if ln.startswith("files read")), "")
    check("env-check: the `files read` line lists the key files and .env",
          "keys/a.env" in files_line and "~/b.env" in files_line and ".env" in files_line, files_line)  # fmt: skip
    check("env-check: a system whose key_file lacks the variable is told so",
          "sys_nokey" in out and "keys/other.env" in out and "not in the file" in out, out[-1800:])  # fmt: skip
    check("env-check: a missing key file is reported, not skipped",
          "sys_missing" in out and "keys/nope.env" in out and "cannot be read" in out, out[-1800:])  # fmt: skip

    # ── a LiteLLM system: the file also names its base URL ───────────────────
    (proj / "keys" / "proxy.env").write_text(
        f"LITELLM_API_KEY={KEY_PROXY}\nLITELLM_BASE_URL={BASE.removesuffix('/v1')}\n", encoding="utf-8"
    )
    _runstore.write_text(
        proj,
        "systems/sys_proxy.yaml",
        "system_id: sys_proxy\nparams:\n  provider: litellm\n  model: fake\n  key_file: keys/proxy.env\n"
        "  usd_per_mtok_in: 0\n  usd_per_mtok_out: 0\n",
    )
    r, seen = smoke("sys_proxy")
    check("provider litellm: the key and the base URL are both read from the key_file",
          r.returncode == 0 and carried(seen, KEY_PROXY), (said(r)[-300:], seen))  # fmt: skip

    # ── the address's source is said as the key's is ─────────────────────────
    (proj / "keys" / "keyonly.env").write_text(f"LITELLM_API_KEY={KEY_PROXY}\n", encoding="utf-8")
    for sid, kf, provider in (
        ("sys_keyonly", "keys/keyonly.env", "litellm"),
        ("sys_or", "keys/a.env", "openrouter"),
    ):
        _runstore.write_text(
            proj,
            f"systems/{sid}.yaml",
            f"system_id: {sid}\nparams:\n  provider: {provider}\n  model: fake\n  key_file: {kf}\n"
            "  usd_per_mtok_in: 0\n  usd_per_mtok_out: 0\n",
        )
    shell_base = {**env, "LITELLM_BASE_URL": BASE.removesuffix("/v1")}
    for sid, where, with_env in (
        ("sys_a", "base_url: system's base_url param", None),
        ("sys_proxy", "LITELLM_BASE_URL: key_file keys/proxy.env", None),
        ("sys_keyonly", "LITELLM_BASE_URL: shell; key_file keys/keyonly.env does not hold it", shell_base),
        ("sys_keyonly", "LITELLM_BASE_URL: not set; key_file keys/keyonly.env does not hold it", None),
        ("sys_or", "default", None),
    ):
        r = evh("run", "--system", sid, "--dataset", "tk_v1", "--dry-run", with_env=with_env)
        line = next((ln for ln in r.stdout.splitlines() if ln.startswith("  key ")), "")
        check(
            f"the dry run of {sid} says where its address comes from: {where}",
            where in line,
            (line, r.stderr[-200:]),
        )
    out = evh("env-check", with_env=shell_base).stdout
    row = next(
        (ln for ln in out.splitlines() if ln.startswith("  sys_keyonly") and "LITELLM_BASE_URL" in ln), ""
    )
    check("env-check: the address of a system whose key is in a key_file says it is not",
          "shell" in row and "keys/keyonly.env does not hold it" in row, row)  # fmt: skip
    row = next((ln for ln in out.splitlines() if ln.startswith("  sys_a ") and "base_url" in ln), "")
    check(
        "env-check: a system's own base_url param is the address's source",
        "system's base_url param" in row,
        row,
    )

    # ── a project adapter that calls the bundled providers gets the same ─────
    (proj / "mine_adapter.py").write_text(
        "from evaluation_harness import _providers\n"
        "from evaluation_harness.adapter import Result, score  # noqa: F401\n\n"
        "def call_system(text, params):\n"
        "    c = _providers.complete(text, params, role='arm', max_tokens=50)\n"
        "    return Result(output=c.text, cost_usd=0.0)\n",
        encoding="utf-8",
    )
    system("sys_project", "keys/a.env", adapter="mine_adapter.py")
    r, seen = smoke("sys_project")
    check("a project adapter calling _providers.complete with the system's params: the key_file applies",
          r.returncode == 0 and carried(seen, KEY_A), (said(r)[-400:], seen))  # fmt: skip
    files_line = next((ln for ln in evh("env-check").stdout.splitlines() if ln.startswith("files read")), "")
    check("env-check: a key file two systems name is listed once in `files read`",
          files_line.count("keys/a.env") == 1, files_line)  # fmt: skip

    # ── identity: the file's path is outside every hash ──────────────────────
    with tempfile.TemporaryDirectory() as td:
        kw: dict[str, Any] = {
            "root": Path(td),
            "dataset": {"dataset_id": "d", "items": []},
            "reference_id": None,
            "reference_tier": None,
            "system_id": "c",
            "adapter_id": "bundled",
            "adapter_path": None,
        }
        base_p = {"provider": "openai", "model": "m"}
        h = [
            _fingerprint.build_fingerprint(params={**base_p, **extra_p}, **kw)
            for extra_p in ({}, {"key_file": "keys/a.env"}, {"key_file": "/elsewhere/b.env"})
        ]
        check("two systems differing only in key_file have the same fingerprint hash",
              h[0]["hash"] == h[1]["hash"] == h[2]["hash"], [x["hash"] for x in h])  # fmt: skip
        check("the file's path is in no part of the fingerprint", "keys/a.env" not in json.dumps(h[1]), "")
    check("identity_params leaves key_file out, as api_key_env",
          _providers.identity_params({"model": "m", "key_file": "k", "api_key_env": "K"}) == {"model": "m"}, "")  # fmt: skip
    check("a page's params do not show the path (a home directory's name)",
          "key_file" not in _providers.shown_params({"model": "m", "key_file": "/home/x/k.env"}), "")  # fmt: skip

    # ── no key's value anywhere: not said, not written ───────────────────────
    spoken = "\n".join(printed)
    leaks = [k for k in ALL_KEYS if k in spoken]
    check("no key value in anything a command printed", not leaks, len(leaks))
    key_files = {
        proj / ".env",
        proj / "keys" / "a.env",
        proj / "keys" / "proxy.env",
        proj / "keys" / "keyonly.env",
        outside / "b.env",
    }
    wrote = []
    for root, _dirs, names in os.walk(proj):
        for n in names:
            f = Path(root) / n
            if f in key_files or ".git" in f.relative_to(proj).parts:
                continue
            blob = f.read_bytes()
            wrote += [(str(f.relative_to(proj)), k) for k in ALL_KEYS if k.encode() in blob]
    check("no key value in any file the harness wrote (the store, run records, caches)", not wrote, wrote[:5])
finally:
    server.shutdown()
    shutil.rmtree(proj, ignore_errors=True)
    shutil.rmtree(outside, ignore_errors=True)
sys.exit(summary())
