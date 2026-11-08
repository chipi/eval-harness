#!/usr/bin/env python3
"""A setting's save on a running server (the data page): one at a time, and one `evh validate` a save, not two.

    python tests/test_settings_save.py

The architecture review (2026-11-06) measured `evh validate` at 25.8 s on this repository, run before and after
every save, with nothing serialising two saves on the server's threads: the second's "before" could be the first's
"after". Here `project_check` is stood in for (it counts its calls and how many overlap), two saves race on two
threads, and a delete races with a save: never two at once. Two saves in a row run the check three times (the first
save's "after" is the second's "before"); another process's commit to the database makes the next save check again.
"""

import os
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
proj = Path(tempfile.mkdtemp(prefix="evh-settings-save-"))
os.environ["EVAL_HOME"] = str(proj)
os.environ["EVAL_STORE"] = "sqlite"  # the data page is SQLite's (Configure needs it)
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR"):
    os.environ.pop(k, None)
from evaluation_harness import _data_page, _outputs, _settings_form, _store  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

_outputs.reset()
data = proj / "data"
data.mkdir()
calls = {"n": 0, "now": 0, "most": 0, "mixed": 0}
watch: list[Path] = []  # a path whose existence must not change while one check runs
lock = threading.Lock()


def stand_in() -> dict:
    with lock:
        calls["n"] += 1
        calls["now"] += 1
        calls["most"] = max(calls["most"], calls["now"])
    seen = [_store.exists(w) for w in watch]
    time.sleep(0.2)
    if [_store.exists(w) for w in watch] != seen:
        calls["mixed"] += 1
    with lock:
        calls["now"] -= 1
    return {}


_settings_form.project_check = stand_in
try:
    f1, f2 = data / "goals" / "a.yaml", data / "goals" / "b.yaml"
    errs: list[str] = []

    def save(f: Path, text: str) -> None:
        try:
            _settings_form.guarded_write(f"goals/{f.name}", f, text)
        except Exception as e:  # noqa: BLE001 - the check reports it
            errs.append(f"{type(e).__name__}: {e}")

    ts = [threading.Thread(target=save, args=(f, f"goal_id: {f.stem}\n")) for f in (f1, f2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    check(
        "two saves at once: never two checks at once, both saved",
        calls["most"] == 1
        and not errs
        and _store.read_text(f1) == "goal_id: a\n"
        and _store.read_text(f2) == "goal_id: b\n",
        (calls, errs),
    )
    check("two saves in a row: the check runs three times, not four", calls["n"] == 3, calls)

    calls.update(n=0)
    other = sqlite3.connect(str(data / _store.DB))
    other.execute("INSERT OR REPLACE INTO files VALUES ('goals/c.yaml', x'00', 'x', 0)")
    other.commit()
    other.close()
    save(f1, "goal_id: a\ntitle: changed\n")
    check(
        "another process wrote to the database: the next save checks the project before it again",
        calls["n"] == 2 and not errs,
        (calls, errs),
    )

    calls.update(n=0, most=0)
    run = data / "runs" / "arm_v1_x"
    _store.write_text(run / "metrics.json", "{}")
    watch.append(run)
    gone: list[str] = []

    def delete() -> None:
        try:
            _data_page.remove("runs/arm_v1_x")
        except Exception as e:  # noqa: BLE001
            gone.append(f"{type(e).__name__}: {e}")

    t1 = threading.Thread(target=save, args=(f2, "goal_id: b\ntitle: again\n"))
    t2 = threading.Thread(target=delete)
    t1.start()
    time.sleep(0.05)
    t2.start()
    t1.join()
    t2.join()
    check(
        "a delete waits for a save in progress (the save's checks see one project), and is done after it",
        not errs and not gone and not _store.exists(run) and calls["mixed"] == 0,
        (errs, gone, _store.exists(run), calls),
    )
finally:
    _store.close()
    import shutil

    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
