#!/usr/bin/env python3
"""A judge is a system with its own `key_file` (0.8.3): $0, offline.

    python tests/test_judge_key_file.py

A judge whose definition names `key_file` sends that file's key on its calls (a fake OpenAI-shaped server keeps the
bearer), its fingerprint is the same wherever its key is kept, and a key file that lacks the key is refused with nothing
falling through to the shell. `EVAL_JUDGE_<NAME>` still works, with one warning per process that names the `key_file`
way and 0.9.0; `evh judge-score --dry-run` says where each judge's key comes from and never shows a value.
"""

import contextlib
import http.server
import io
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

os.environ["EVAL_STORE"] = "files"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore, _runfix
import _runfix
import _runstore
import yaml
from evaluation_harness import _outputs, _providers, judging, ops
from evaluation_harness import judge_score as js
from evaluation_harness._check import check, summary
from evaluation_harness.ops import cli as ops_cli

HERE = Path(__file__).resolve().parents[1]
ARMS = ["arm0_v1", "arm1_v1"]
SEEN: list[str] = []
PRINTED: list[str] = []
KEY_FILE, KEY_ENV, KEY_SHELL, KEY_OTHER = (
    "sk-test-file-not-printed",
    "sk-test-judge-env-not-printed",
    "sk-test-shell-not-printed",
    "sk-test-other-not-printed",
)


class Fake(http.server.BaseHTTPRequestHandler):
    """An OpenAI-shaped server: keeps the bearer each call carried, answers a verdict."""

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers["Content-Length"]))
        SEEN.append(str(self.headers.get("Authorization", "")).removeprefix("Bearer "))
        data = json.dumps({
            "id": "x", "object": "chat.completion", "created": 0, "model": "fake",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "[1, 2]"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
        }).encode()  # fmt: skip
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a: object) -> None:
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=server.serve_forever, daemon=True).start()
ADDRESS = f"http://127.0.0.1:{server.server_address[1]}"

for k in [k for k in os.environ if k.startswith(("LITELLM_", "EVAL_JUDGE_"))] + ["EVAL_MAX_COST_USD"]:
    os.environ.pop(k, None)


def said_of(argv: list[str]) -> tuple[int, str]:
    out, err = io.StringIO(), io.StringIO()
    rc: object = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = ops_cli.main(ops.OPS["judge-score"], argv)
        except SystemExit as exc:
            rc = exc.code
    PRINTED.append(out.getvalue() + err.getvalue() + (rc if isinstance(rc, str) else ""))
    return (1 if isinstance(rc, str) else int(rc or 0)), PRINTED[-1]


def dry() -> tuple[int, str]:
    return said_of(["--dataset-id", "ds", "--scorer", "judge-kf-test-v1", "--unvalidated", "--dry-run"])


def judge_line(out: str, jid: str) -> str:
    return next((ln for ln in out.splitlines() if ln.startswith(f"  judge {jid}") and "key" in ln), "")


try:
    with tempfile.TemporaryDirectory() as tmp:
        td = Path(tmp)
        keyfile = td / "judge.env"
        keyfile.write_text(f"LITELLM_API_KEY={KEY_FILE}\nLITELLM_BASE_URL={ADDRESS}\n", encoding="utf-8")
        lacking = td / "lacking.env"
        lacking.write_text(f"LITELLM_BASE_URL={ADDRESS}\n", encoding="utf-8")

        # ── the call: the file's key, whatever the shell holds ──────────────────────────────────────
        params = {"provider": "litellm", "model": "m", "usd_per_mtok_in": 0, "usd_per_mtok_out": 0}
        os.environ.update(LITELLM_API_KEY=KEY_SHELL, LITELLM_BASE_URL="http://proxy.invalid")
        res = judging.call_judge("judge this", {**params, "key_file": str(keyfile)})
        check(
            "a judge with a key_file: its call carries that file's key, and the file's address",
            SEEN == [KEY_FILE] and res.output == "[1, 2]",
            (SEEN, res.output),
        )
        SEEN.clear()
        # the old way still reaches the same server with the shell's key: EVAL_JUDGE_<NAME> first
        os.environ.update(EVAL_JUDGE_LITELLM_API_KEY=KEY_ENV, LITELLM_BASE_URL=ADDRESS)
        judging.call_judge("judge this", params)
        check(
            "a judge with no key_file: EVAL_JUDGE_<NAME> is read first, as in 0.8.2",
            SEEN == [KEY_ENV],
            SEEN,
        )
        SEEN.clear()
        judging.call_judge("judge this", {**params, "key_file": str(keyfile)})
        check(
            "a judge with a key_file: EVAL_JUDGE_<NAME> is not used beside it",
            SEEN == [KEY_FILE],
            SEEN,
        )
        SEEN.clear()

        # ── K4 for judges: a key file without the key is refused, nothing falls through ─────────────
        for what in (
            {"EVAL_JUDGE_LITELLM_API_KEY": KEY_ENV, "LITELLM_API_KEY": KEY_SHELL},
            {"LITELLM_API_KEY": KEY_SHELL},
        ):
            for k in ("EVAL_JUDGE_LITELLM_API_KEY", "LITELLM_API_KEY"):
                os.environ.pop(k, None)
            os.environ.update(what)
            why = _providers.problems({**params, "key_file": str(lacking)}, "judge")
            check(
                f"a judge's key_file without the key ({' + '.join(what)} set): refused, naming the file and LITELLM_API_KEY",
                len(why) == 1 and str(lacking) in why[0] and "LITELLM_API_KEY" in why[0],
                why,
            )
            with contextlib.suppress(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                judging.call_judge("judge this", {**params, "key_file": str(lacking)})
            check("...and no call was made", not SEEN, SEEN)
        os.environ.pop("EVAL_JUDGE_LITELLM_API_KEY", None)

        # ── identity: where the key is kept is not what was measured ────────────────────────────────
        j: dict[str, Any] = {"id": "g", "params": {**params, "family": "x"}}
        fps = {
            js.judge_fingerprint({**j, "params": {**j["params"], **extra}})
            for extra in ({}, {"key_file": str(keyfile)}, {"key_file": "/elsewhere/other.env"})
        }
        check(
            "a judge's fingerprint is the same with the key in a key_file or in the environment",
            len(fps) == 1,
            fps,
        )
        check(
            "...and a key_file path is in no part of it",
            "judge.env" not in json.dumps(j) and len(next(iter(fps))) == 16,
            fps,
        )

        # ── the dry run says where each key comes from ──────────────────────────────────────────────
        with _runstore._InProject(td / "proj") as data:
            sc = yaml.safe_load(
                (HERE / "data" / "scorers" / "judge-summ-v1.yaml").read_text(encoding="utf-8")
            )
            sc.update(scorer_id="judge-kf-test-v1", dataset_id="ds", arms_match="_v1")
            sc.pop("supersedes", None)
            (data / "scorers").mkdir(parents=True)
            pf = data / "scorers" / "examples" / "summeval-judging" / "prompt.txt"
            pf.parent.mkdir(parents=True)
            pf.write_text(
                (HERE.parent / "examples" / "summeval-judging" / "prompt.txt").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (data / "datasets").mkdir()
            (data / "datasets" / "ds.json").write_text(
                json.dumps({"dataset_id": "ds", "items": [{"item_id": "itemA"}]}), encoding="utf-8"
            )
            (data / "materialized" / "ds").mkdir(parents=True)
            (data / "materialized" / "ds" / "itemA.txt").write_text(
                "An article about itemA.", encoding="utf-8"
            )
            for name in ARMS:
                d = data / "runs" / f"{name}_2026"
                _outputs.writer(d).add("itemA", f"summary by {name}")
                _runfix.put_run(
                    data,
                    {
                        "system_id": name,
                        "run_id": f"{name}_2026",
                        "dataset_id": "ds",
                        "created_at": "2026",
                        "primary_metric": "coverage",
                        "scores": {"coverage": 0.3},
                        "metric_kinds": {"coverage": "quality"},
                        "params": {"family": "x"},
                        "fingerprint": {"hash": "abc", "arm": {"config_id": name}},
                    },
                    [{"item_id": "itemA", "coverage": 0.3}],
                )

            def write_scorer(first_key_file: Path | None) -> None:
                s = json.loads(json.dumps(sc))
                if first_key_file:
                    s["judges"][0]["params"]["key_file"] = str(first_key_file)
                (data / "scorers" / "judge-kf-test-v1.yaml").write_text(yaml.safe_dump(s), encoding="utf-8")

            saved = (js.DATA, js.MATERIALIZED, js.SCORERS, js.SETS, js.VERDICTS)
            js.DATA, js.MATERIALIZED = data, data / "materialized"
            js.SCORERS, js.SETS, js.VERDICTS = (
                data / "scorers",
                data / "judging-sets",
                data / "judge-verdicts",
            )
            try:
                for k in ("EVAL_JUDGE_LITELLM_API_KEY", "LITELLM_API_KEY"):
                    os.environ.pop(k, None)
                os.environ.update(EVAL_JUDGE_LITELLM_API_KEY=KEY_ENV, LITELLM_BASE_URL=ADDRESS)
                write_scorer(keyfile)
                _providers._JUDGE_ENV_SAID.clear()  # the calls above already read EVAL_JUDGE_LITELLM_API_KEY
                rc, out = dry()
                gemma, qwen = judge_line(out, "gemma_l"), judge_line(out, "qwen_s")
                check("the dry run: exit 0 and an estimate", rc == 0 and "DRY RUN" in out, out[-600:])
                check(
                    "the dry run: a judge with a key_file says its key is the file's, by path",
                    f"key LITELLM_API_KEY (key_file {keyfile})" in gemma,
                    gemma,
                )
                check(
                    "the dry run: a judge on EVAL_JUDGE_<NAME> says so and that it is deprecated",
                    "key EVAL_JUDGE_LITELLM_API_KEY" in qwen and "deprecated" in qwen,
                    qwen,
                )
                warned = [ln for ln in out.splitlines() if "deprecated" in ln and "0.9.0" in ln]
                check(
                    "the deprecation warning is printed once, naming the key_file way and 0.9.0",
                    len(warned) == 1
                    and "key_file" in warned[0]
                    and "EVAL_JUDGE_LITELLM_API_KEY" in warned[0],
                    warned,
                )
                _rc, again = dry()
                check(
                    "...and not again in the same process",
                    "0.9.0" not in again and "deprecated" in judge_line(again, "qwen_s"),
                    again[:800],
                )

                os.environ.pop("EVAL_JUDGE_LITELLM_API_KEY")
                os.environ["LITELLM_API_KEY"] = KEY_SHELL
                rc, out = dry()
                check(
                    "the dry run: a judge on the shell's LITELLM_API_KEY says shell, and no warning",
                    "key LITELLM_API_KEY (shell)" in judge_line(out, "qwen_s") and "0.9.0" not in out,
                    judge_line(out, "qwen_s"),
                )

                write_scorer(lacking)
                rc, out = dry()
                gemma = judge_line(out, "gemma_l")
                missing = [ln for ln in out.splitlines() if "MISSING" in ln]
                check(
                    "the dry run: a key_file without the key is MISSING, names the file and variable; the shell's key is not used",
                    len(missing) == 1
                    and str(lacking) in missing[0]
                    and "LITELLM_API_KEY" in missing[0]
                    and "key_file" in gemma
                    and "not in" in gemma,
                    (gemma, missing),
                )
                rc, out = said_of(["--dataset-id", "ds", "--scorer", "judge-kf-test-v1", "--unvalidated"])
                check(
                    "judge-score on it is refused (not-configured) before any call",
                    rc != 0 and "not-configured" in out and not SEEN,
                    (rc, out[-400:], SEEN),
                )
                check(
                    "no key's value in anything printed",
                    not any(k in "\n".join(PRINTED) for k in (KEY_FILE, KEY_ENV, KEY_SHELL, KEY_OTHER)),
                    "",
                )
            finally:
                js.DATA, js.MATERIALIZED, js.SCORERS, js.SETS, js.VERDICTS = saved
finally:
    server.shutdown()
sys.exit(summary())
