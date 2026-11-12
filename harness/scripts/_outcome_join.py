"""An item's outcome from another capture (RFC-031 L1, X3): what an outside system recorded later about a decision.

    evh label-from-capture --dataset-id triage_v1 --capture decisions --map outcomes.yaml --set s \\
        --outcomes issues_2026_11 --join fingerprint=fingerprint --within -1m,+15m \\
        [--identity first_seen=first_seen] [--gone-if-missing]

The decision's own capture holds what the system did; its outcome lives on another object (the issue it filed, the
errors that followed), read once into a capture of its own, so what was read is kept, hashed and dated. Each item's
record is joined to the other capture's records whose RECORD_FIELD equals the item record's ITEM_FIELD (fields read
by dotted path) and, with `--within`, whose time falls in that window after the item's: the fleet's issue, created
between a minute before and 15 minutes after the decision. The rules then see `<capture>.<field>` for the first
match's outcome and fields, `<capture>.count` (how many matched) and `<capture>.created_at`, beside the item's own.

X3, gone from the source, or its id reused: with `--gone-if-missing`, an item whose key no record of the other capture
carries at all is "gone" (the outside object was deleted), and with `--identity ITEM_FIELD=RECORD_FIELD` a match whose
identity field differs from the item's (a GlitchTip short id reused after a project was deleted) is gone too, never
another item's outcome. A gone item is its own class: never "no outcome", never a negative label.

Several outside systems (the fleet's beta: GitHub's close reason and GlitchTip's recurrence): `--outcomes` again, each
followed by its own options up to the next one; the rules read each under its own name.

    ... --outcomes issues --outcomes-as gh --join fp=fp --within -1m,+15m \\
        --outcomes glitchtip --outcomes-as gt --join short_id=short_id --identity first_seen=first_seen --gone-if-missing
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from evaluation_harness._common import die
from evaluation_harness._importers import parse_time

_SPAN = re.compile(r"^([+-]?\d+(?:\.\d+)?)([smhd])$")
_UNIT = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def _dig(d: Any, dotted: str) -> Any:
    for part in dotted.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(part)
    return d


def _pair(text: str | None, flag: str) -> tuple[str, str] | None:
    if not text:
        return None
    a, sep, b = text.partition("=")
    if not sep or not a.strip() or not b.strip():
        die(f"{flag} {text!r}: ITEM_FIELD=RECORD_FIELD", "bad-argument")
    return a.strip(), b.strip()


def _span(text: str) -> timedelta:
    m = _SPAN.match(text.strip())
    if not m:
        die(f"--within {text!r}: a span like -1m, +15m, 2h, 14d", "bad-argument")
    return timedelta(**{_UNIT[m.group(2)]: float(m.group(1))})


def _value(rec: dict, field: str) -> Any:
    """A record's field: its fields, else its outcome, else the record itself (id, created_at)."""
    for where in (rec.get("fields"), rec.get("outcome"), rec):
        v = _dig(where or {}, field)
        if v is not None:
            return v
    return None


class Join:
    """The other capture, indexed by its join field."""

    def __init__(
        self,
        capture: str,
        join: str | None,
        within: str | None = None,
        identity: str | None = None,
        gone_if_missing: bool = False,
        name: str | None = None,
    ) -> None:
        from evaluation_harness.dataset_from_capture import load_capture  # noqa: PLC0415

        pair = _pair(join, "--join")
        if pair is None:
            die(
                "--outcomes needs --join ITEM_FIELD=RECORD_FIELD (what ties a decision to the other record)",
                "bad-argument",
            )
        self.capture = capture
        # The prefix the rules read: a later capture of the same source keeps the rules' names (`--outcomes-as`).
        self.name = name or capture
        self.within_text = within
        self.item_field, self.record_field = pair
        self.identity = _pair(identity, "--identity")
        self.gone_if_missing = gone_if_missing
        self.window: tuple[timedelta, timedelta] | None = None
        if within:
            lo, sep, hi = within.partition(",")
            if not sep:
                die(f"--within {within!r}: two spans, -1m,+15m", "bad-argument")
            self.window = (_span(lo), _span(hi))
            if self.window[0] > self.window[1]:
                die(f"--within {within!r}: the first span is after the second", "bad-argument")
        self.doc, recs = load_capture(capture)
        self.by_key: dict[str, list[dict]] = {}
        for r in recs:
            k = _value(r, self.record_field)
            if k not in (None, ""):
                self.by_key.setdefault(str(k), []).append(r)
        for rs in self.by_key.values():
            rs.sort(key=lambda r: (str(r.get("created_at") or ""), str(r.get("id"))))

    def source(self) -> dict[str, Any]:
        """What the label set records about the other capture (its provenance)."""
        import hashlib  # noqa: PLC0415

        from evaluation_harness import _store  # noqa: PLC0415
        from evaluation_harness._common import CAPTURES  # noqa: PLC0415

        return {
            "capture": self.capture,
            "capture_sha256": hashlib.sha256(
                _store.read_bytes(CAPTURES / self.capture / "capture.json")
            ).hexdigest(),
            "captured_at": self.doc.get("captured_at"),
            "join": f"{self.item_field}={self.record_field}",
            "within": self.within_text,
            "as": self.name,
            "identity": "=".join(self.identity) if self.identity else None,
            "gone_if_missing": self.gone_if_missing,
        }

    def outcome(self, rec: dict) -> tuple[dict[str, Any], bool]:
        """(the fields the rules see from the other capture, whether the outside object is gone or its id reused)."""
        key = _value(rec, self.item_field)
        if key in (None, ""):
            return {f"{self.name}.count": 0}, False
        found = list(self.by_key.get(str(key), []))
        if not found:
            return {f"{self.name}.count": 0}, self.gone_if_missing
        if self.identity:
            mine = _value(rec, self.identity[0])
            if mine is not None and all(str(_value(r, self.identity[1])) != str(mine) for r in found):
                return {f"{self.name}.count": 0}, True
            found = [r for r in found if mine is None or str(_value(r, self.identity[1])) == str(mine)]
        if self.window:
            t = parse_time(rec.get("created_at"))
            lo, hi = self.window
            found = [
                r
                for r in found
                if t is not None
                and (u := parse_time(r.get("created_at"))) is not None
                and t + lo <= u <= t + hi
            ]
        out: dict[str, Any] = {f"{self.name}.count": len(found)}
        if found:
            first = found[0]
            for where in (first.get("fields"), first.get("outcome")):
                if isinstance(where, dict):
                    out |= {
                        f"{self.name}.{k}": v for k, v in where.items() if not isinstance(v, (dict, list))
                    }
            out[f"{self.name}.created_at"] = first.get("created_at")
            out[f"{self.name}.id"] = first.get("id")
        return out, False


def add_arguments(ap: Any) -> None:
    """The join's options, the same on label-from-capture and label-coverage."""
    ap.add_argument("--outcomes", help="another capture holding the outcome (an outside system's records)")
    ap.add_argument(
        "--outcomes-as",
        help="the name the rules read its fields under, NAME.field (default: the capture's id); keep one name "
        "across later captures of the same source",
    )
    ap.add_argument(
        "--join", help="ITEM_FIELD=RECORD_FIELD: what ties a decision to the other capture's record"
    )
    ap.add_argument(
        "--within", help="a window after the item's time, -1m,+15m: only records made in it match"
    )
    ap.add_argument(
        "--identity",
        help="ITEM_FIELD=RECORD_FIELD that must also agree: a reused id is gone, not another's outcome",
    )
    ap.add_argument(
        "--gone-if-missing",
        action="store_true",
        help="the other capture holds the very object each item names (a GlitchTip issue): an item whose key no "
        "record carries is gone from the source (its own class); not for a window join, where no match is no outcome",
    )


def argv(raw: list[str] | None = None) -> list[str]:
    """The command line with `--within -1m,+15m` joined into `--within=-1m,+15m`: before Python 3.12 argparse reads a
    value starting with "-" as another option ("expected one argument"), and this is how a window is written."""
    import sys  # noqa: PLC0415

    args = list(sys.argv[1:] if raw is None else raw)
    out: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--within" and i + 1 < len(args) and args[i + 1].startswith("-"):
            out.append(f"--within={args[i + 1]}")
            i += 2
            continue
        out.append(args[i])
        i += 1
    return out


class Joins:
    """Every outside capture an item's outcome is read from, each under its own name: the rules see them all."""

    def __init__(self, joins: list[Join]) -> None:
        names = [j.name for j in joins]
        twice = sorted({n for n in names if names.count(n) > 1})
        if twice:
            die(
                f"--outcomes: two captures read under the same name ({', '.join(twice)}): name each with --outcomes-as",
                "bad-argument",
            )
        self.joins = joins

    @property
    def doc(self) -> dict[str, Any]:
        """The latest of the captures' read times: what a label's maturity is measured to."""
        times = [str(j.doc.get("captured_at")) for j in self.joins if j.doc.get("captured_at")]
        return {"captured_at": max(times, key=lambda t: parse_time(t) or t)} if times else {}

    @property
    def capture(self) -> str:
        return ", ".join(j.capture for j in self.joins)

    def source(self) -> list[dict[str, Any]]:
        """What the label set records about each outside capture (its provenance)."""
        return [j.source() for j in self.joins]

    def outcome(self, rec: dict) -> tuple[dict[str, Any], bool]:
        """(the fields the rules see from every outside capture, whether an outside object is gone or its id reused)."""
        out: dict[str, Any] = {}
        for j in self.joins:
            seen, gone = j.outcome(rec)
            if gone:
                return {}, True
            out |= seen
        return out, False


_VALUED = {"--outcomes-as": "outcomes_as", "--join": "join", "--within": "within", "--identity": "identity"}


def groups(raw: list[str] | None = None) -> list[dict[str, Any]]:
    """Each `--outcomes CAPTURE` with the join options after it, up to the next `--outcomes`. With one `--outcomes`,
    every join option is its own wherever it stands (the MCP server writes a tool call's options in name order)."""
    args = argv(raw)
    if sum(1 for a in args if a == "--outcomes" or a.startswith("--outcomes=")) == 1:
        first = next(i for i, a in enumerate(args) if a == "--outcomes" or a.startswith("--outcomes="))
        width = 1 if "=" in args[first] else 2
        args = args[first : first + width] + args[:first] + args[first + width :]
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(args):
        name, eq, val = args[i].partition("=") if args[i].startswith("--") else (args[i], "", "")
        if name == "--outcomes" or name in _VALUED:
            if not eq:
                i += 1
                val = args[i] if i < len(args) else ""
            if name == "--outcomes":
                out.append({"outcomes": val})
            else:
                if not out:
                    die(f"{name}: after the --outcomes CAPTURE it belongs to", "bad-argument")
                if _VALUED[name] in out[-1]:
                    die(f"{name}: given twice for --outcomes {out[-1]['outcomes']}", "bad-argument")
                out[-1][_VALUED[name]] = val
        elif name == "--gone-if-missing":
            if not out:
                die("--gone-if-missing: after the --outcomes CAPTURE it belongs to", "bad-argument")
            out[-1]["gone_if_missing"] = True
        i += 1
    return out


def from_args(args: Any, raw: list[str] | None = None) -> Joins | None:
    """The joins the command line asks for (one per `--outcomes`, each with the options after it), or None."""
    del args  # the options' order says which capture each belongs to, which the parsed namespace has lost
    gs = groups(raw)
    if not gs:
        return None
    return Joins(
        [
            Join(
                g["outcomes"],
                g.get("join"),
                g.get("within"),
                g.get("identity"),
                g.get("gone_if_missing", False),
                g.get("outcomes_as"),
            )
            for g in gs
        ]
    )
