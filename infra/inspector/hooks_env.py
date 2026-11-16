"""Which observability this run reports to, prod or dev, for both servers' hooks (hooks.py, mcp/hooks.py).

    EVALS_ENV=prod   the box (compose.yml), the default: settings from /srv/evals/observability.env
    EVALS_ENV=dev    a workstation (make serve-dev / mcp-dev): settings from ~/.config/evals/observability-dev.env

The contract is homelab's (agentic-ai-homelab docs/recipes/o11y-dev.md): a dev run reports to dev targets, every error,
span and log line saying environment=dev and worktree=<the git branch>, so the agent on that branch reads its own
(the o11y-dev skill) and the triage fleet, which files issues from prod, never sees it. A run that would cross is
refused: a prod GlitchTip project in dev, the dev project in prod. Errors go to GlitchTip `evals-dev` (one project, the
service a tag), traces to VictoriaTraces as in prod, and log lines, in dev only, straight to VictoriaLogs (in prod the
box's collector reads the containers' stdout).

The settings files are KEY=VALUE lines, outside the repository (EVALS_OBS_ENV names another). In dev the GlitchTip DSN
may stay in the file homelab handed it in: SENTRY_DSN_FILE names it. Every send is best effort: a part that cannot
start is off, said once on stdout, and the server answers as before.

Deployed beside hooks.py and mcp_hooks.py (render.sh); in the repository, infra/inspector/.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODES = ("prod", "dev")
SETTINGS = {"prod": "/srv/evals/observability.env", "dev": "~/.config/evals/observability-dev.env"}
#: GlitchTip projects (org homelab) by id: a DSN ends in its project's id. The dev project only in dev, never in prod.
PROD_PROJECTS = {"36": "evals-web", "37": "evals-inspector", "38": "evals-mcp"}
DEV_PROJECTS = {"40": "evals-dev"}


def mode() -> str:
    """prod or dev, from EVALS_ENV (unset: prod); anything else is said and reads as off."""
    m = (os.environ.get("EVALS_ENV") or "prod").strip().lower()
    return m if m in MODES else "off"


def _read(f: Path) -> dict:
    out: dict = {}
    if f.is_file():
        for line in f.read_text().splitlines():
            k, sep, v = line.strip().partition("=")
            if sep and k and not k.startswith("#"):
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def settings(m: str, keys: tuple[str, ...]) -> dict:
    """The mode's settings file (or EVALS_OBS_ENV), the environment's `keys` over it; a DSN by SENTRY_DSN_FILE when
    the file names one and gives none itself."""
    out = _read(Path(os.environ.get("EVALS_OBS_ENV") or SETTINGS.get(m, "")).expanduser())
    out.update({k: v for k, v in os.environ.items() if k in keys})
    if not out.get("SENTRY_DSN") and out.get("SENTRY_DSN_FILE"):
        out["SENTRY_DSN"] = _read(Path(out["SENTRY_DSN_FILE"]).expanduser()).get("SENTRY_DSN", "")
    return out


def dsn_refused(dsn: str, m: str) -> str:
    """Why this DSN may not be used in this mode ('' when it may): dev reports to a dev project only, prod never to
    one (o11y-dev.md: a dev run in a prod project, or a prod run labelled dev, breaks both reviews)."""
    project = dsn.rstrip("/").rsplit("/", 1)[-1]
    if m == "dev" and project not in DEV_PROJECTS:
        name = PROD_PROJECTS.get(project, f"project {project}")
        return f"GlitchTip {name} is not a dev project: a dev run reports to evals-dev (40) only"
    if m == "prod" and project in DEV_PROJECTS:
        return f"GlitchTip {DEV_PROJECTS[project]} is the dev project: prod never reports to it"
    return ""


def release(release_file: Path, m: str) -> str:
    """sha-<7> of the release (render.sh writes the sha to RELEASE); in dev, with no such file, dev-<7> of this checkout's
    commit, so GlitchTip and the traces name the code a dev error came from."""
    sha = release_file.read_text().strip() if release_file.is_file() else ""
    if sha:
        return f"sha-{sha[:7]}"
    if m == "dev":
        r = subprocess.run(
            ["git", "-C", str(HERE), "rev-parse", "--short=7", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode == 0 and r.stdout.strip():
            return f"dev-{r.stdout.strip()}"
    return "unknown"


def worktree() -> str:
    """The git branch this code is on (EVALS_WORKTREE when set): the label o11y-dev filters a branch's signals by."""
    if os.environ.get("EVALS_WORKTREE"):
        return os.environ["EVALS_WORKTREE"]
    try:
        r = subprocess.run(
            ["git", "-C", str(HERE), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "unknown"


class LogPush:
    """Log lines to VictoriaLogs' jsonline endpoint, in dev: a bounded queue, one thread sending a batch every two
    seconds, so a slow or absent VictoriaLogs never delays an answer or grows memory (a line that does not fit is
    dropped and counted). The stream is service, environment and worktree. A line stays queued until it is sent, and
    what is queued when the process ends is sent then: a run that exits within the two seconds lost its last lines."""

    FIELDS = ("service", "environment", "worktree")

    def __init__(self, url: str, labels: dict) -> None:
        import atexit  # noqa: PLC0415

        sep = "&" if "?" in url else "?"
        self.url = f"{url}{sep}_stream_fields={','.join(self.FIELDS)}"
        self.labels = labels
        self.lines: queue.Queue = queue.Queue(maxsize=1024)
        self.sent, self.failed, self.dropped = 0, 0, 0
        self._sending = threading.Lock()
        threading.Thread(target=self._run, name="evals-logpush", daemon=True).start()
        atexit.register(self.flush)

    def log(self, msg: str, level: str = "info", **fields) -> None:
        """One line: its text, its level and fields (never an argument's value: the callers pass names and counts)."""
        line = {"_msg": msg, "_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "level": level}
        line.update({k: v for k, v in fields.items() if v is not None})
        line.update(self.labels)
        try:
            self.lines.put_nowait(line)
        except queue.Full:
            self.dropped += 1

    def _run(self) -> None:
        while True:
            time.sleep(2)
            self.flush()

    def flush(self) -> None:
        """Send every queued line, in batches of up to 500 (the worker every two seconds, and once at exit)."""
        with self._sending:
            while True:
                batch = []
                while len(batch) < 500:
                    try:
                        batch.append(self.lines.get_nowait())
                    except queue.Empty:
                        break
                if not batch:
                    return
                body = "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in batch).encode()
                # Without this content type VictoriaLogs answers 200 and drops the lines (agent-access.md, section 3).
                req = urllib.request.Request(  # noqa: S310 -- the operator's own URL, from the settings file
                    self.url, data=body, headers={"Content-Type": "application/stream+json"}
                )
                try:
                    with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310  # nosec B310 -- the operator's own endpoint
                        r.read()
                    self.sent += len(batch)
                except Exception:  # noqa: BLE001 -- best effort: a lost batch is counted, the server goes on
                    self.failed += len(batch)
