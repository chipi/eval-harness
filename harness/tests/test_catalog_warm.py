#!/usr/bin/env python3
"""The server renders its slowest pages ahead after a change (RFC-040, step 6) without making a reader wait for them.

  python tests/test_catalog_warm.py

- a page asked for while the pages are being rendered ahead waits for at most the one render under way, not for the
  rest of them: rendering ahead starts no page while a request waits. The renders keep the interpreter busy, as real
  ones do, and three other threads want it too: the renders' lock alone let rendering ahead take it back first;
- rendering ahead still renders every page it was going to once nobody is waiting.
"""

import sys
import threading
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness import catalog_build as cb  # noqa: E402
from evaluation_harness import catalog_serve as cs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

SLOW_S = 0.25  # a goal page's render here (0.38-1.25 s on this repository)
GOALS = [f"goal{k}" for k in range(12)]


class Site:
    """A model whose goal pages are slow and whose arm page is not; it renders under the build's lock, as a real one."""

    def __init__(self) -> None:
        self.goals = GOALS
        self.rendered: list[str] = []
        self.starts: list[float] = []
        self.started = threading.Event()

    def page(self, path: str) -> str:
        with cb._RENDER_LOCK:
            if path.startswith("a/"):
                return "arm"
            self.starts.append(time.monotonic())
            self.started.set()
            end = time.monotonic() + SLOW_S
            while time.monotonic() < end:  # busy, holding the interpreter as a real render does
                pass
            self.rendered.append(path)
            return path


def busy(until: float) -> None:
    """Another thread wanting the interpreter, as the API's threads and a loaded machine do."""
    while time.monotonic() < until:
        pass


site = Site()
cs.current_site = lambda: site
cs.WARM_QUIET_S = 0.05
threading.Thread(target=cs._pages_warmer, daemon=True).start()
cs._WARM.set()
check("the pages began to be rendered ahead", site.started.wait(10))

load_until = time.monotonic() + 3
for _ in range(3):
    threading.Thread(target=busy, args=(load_until,), daemon=True).start()
time.sleep(SLOW_S / 2)  # inside a render
overtaken = []
for _ in range(6):
    t0 = time.monotonic()
    _, got = cs.site_page("a/one.html")
    t1 = time.monotonic()
    overtaken.append(sum(1 for s in site.starts if t0 < s < t1))
    time.sleep(SLOW_S / 3)
check(
    "a page asked for during the rendering ahead waits for the render under way only: none starts while it waits",
    got == "arm" and not any(overtaken),
    overtaken,
)

want = 2 + len(GOALS)
deadline = time.monotonic() + want * SLOW_S + 10
while len(site.rendered) < want and time.monotonic() < deadline:
    time.sleep(0.05)
check(
    "every page is still rendered ahead once nobody waits",
    len(set(site.rendered)) == want and site.rendered[:2] == ["index.html", "goals.html"],
    len(site.rendered),
)

sys.exit(summary("catalog warm"))
