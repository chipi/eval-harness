#!/usr/bin/env python3
"""No reader works out one of RFC-041's six facts itself: each is asked of its one owner (R6).

  python tests/test_one_source.py

A fact a reader derives again from clues (a run id's suffix, the value's truth, the local date) is how three projects each
found a different bug on v0.8.0. This reads the tokens of every `harness/scripts` module, as `test_cap_shown.py` does, and
lists each place that works one of these out outside its owner:

- F1 which way is better: `_runs.direction` and the words it feeds (the name table's own callers, a table of metric
  names, a declared direction read apart; `test_direction.py` lists who asks an adapter and `test_goal_block_direction.py`
  who reads a goal's `direction`);
- F2 which runs make an arm: `model.runs.arm_of`, `same_measurement`, `set_of`, `latest`, `runs_of_arm`;
- F3 unknown, none and zero cost: `_spend.shown` for the cap (`test_cap_shown.py`), and a cost that is not recorded
  read as 0 or as false;
- F4 whether this is a public server: `_visibility.public()` and `prompt_shown()`;
- F5 the day: `_common.today()`, in UTC (`test_today.py` asks for the machine's date alone);
- F6 a goal's baseline: `_baselines` and a baseline chosen by its goal.

Every site found is a fix, or a line of ALLOWED with its reason; an ALLOWED line that no longer matches fails, so the list
cannot outlive its code. Each pattern is shown to bite on a probe that works the fact out itself.
"""

import io
import re
import sys
import tokenize
from pathlib import Path
from typing import NamedTuple

HARNESS = Path(__file__).resolve().parents[1]
SCRIPTS = HARNESS / "scripts"
sys.path.insert(0, str(HARNESS))
from evaluation_harness import _common  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

SKIP = {tokenize.COMMENT, tokenize.NL, tokenize.INDENT, tokenize.DEDENT}
STRINGS = {tokenize.STRING, getattr(tokenize, "FSTRING_MIDDLE", tokenize.STRING)}
OPEN, SHUT = {"(": ")", "[": "]", "{": "}"}, {")", "]", "}"}


class Hit(NamedTuple):
    """One place that works a fact out: the pattern that found it, the file, the def it is in and the line."""

    pattern: str
    rel: str
    fn: str
    line: int
    text: str


class Source:
    """A module's significant tokens, each with the def it is in and the logical line it is part of."""

    def __init__(self, src: str, rel: str):
        """Tokenize `src`: no comments or blank lines; a NEWLINE token ends each logical line."""
        self.rel = rel
        self.lines = src.splitlines()
        self.toks = [t for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type not in SKIP]
        self.fn: list[str] = []
        self.first: list[int] = []
        defs: list[tuple[int, str]] = []
        fresh, start = True, 0
        for i, t in enumerate(self.toks):
            if fresh:
                start = i
                while defs and defs[-1][0] >= t.start[1]:
                    defs.pop()
                fresh = False
            if t.type == tokenize.NAME and i and self.toks[i - 1].string == "def":
                defs.append((self.toks[i - 1].start[1], t.string))
            self.fn.append(defs[-1][1] if defs else "")
            self.first.append(start)
            fresh = t.type == tokenize.NEWLINE

    def s(self, i: int) -> str:
        """The text of token i, "" past either end."""
        return self.toks[i].string if 0 <= i < len(self.toks) else ""

    def is_str(self, i: int) -> bool:
        """Whether token i is (a piece of) a string literal."""
        return 0 <= i < len(self.toks) and self.toks[i].type in STRINGS

    def value(self, i: int) -> str:
        """A string token's text without its quotes and prefix; "" for any other token."""
        if not self.is_str(i):
            return ""
        return re.sub(r"""^[a-zA-Z]*("{3}|'{3}|"|')|("{3}|'{3}|"|')$""", "", self.s(i))

    def logical(self, i: int) -> list[str]:
        """The token texts of the logical line token i is in."""
        j = self.first[i]
        out = []
        while j < len(self.toks) and self.toks[j].type != tokenize.NEWLINE:
            out.append(self.s(j))
            j += 1
        return out

    def close(self, i: int) -> int:
        """The index of the bracket that closes the one at i."""
        depth = 0
        for j in range(i, len(self.toks)):
            if self.s(j) in OPEN:
                depth += 1
            elif self.s(j) in SHUT:
                depth -= 1
                if depth == 0:
                    return j
        return len(self.toks) - 1

    def open_of(self, i: int) -> int:
        """The index of the bracket that the closing one at i shuts, -1 when there is none."""
        depth = 0
        for j in range(i, self.first[i] - 1, -1):
            if self.s(j) in SHUT:
                depth += 1
            elif self.s(j) in OPEN:
                depth -= 1
                if depth == 0:
                    return j
        return -1

    def opener(self, i: int) -> int:
        """The index of the bracket that opens the one i sits in, -1 when it sits in none."""
        depth = 0
        for j in range(i - 1, self.first[i] - 1, -1):
            if self.s(j) in SHUT:
                depth += 1
            elif self.s(j) in OPEN:
                if depth == 0:
                    return j
                depth -= 1
        return -1

    def loops(self, i: int) -> bool:
        """Whether the `in` at i belongs to a `for` (not a membership test)."""
        for j in range(i - 1, max(self.first[i], i - 10) - 1, -1):
            if self.s(j) in {
                "if",
                "elif",
                "while",
                "and",
                "or",
                "return",
                "assert",
                "=",
                ":",
                "lambda",
                "else",
            }:
                return False
            if self.s(j) == "for":
                return True
        return False

    def equated(self, i: int) -> bool:
        """Whether the string at i is an operand of `==` or `!=`."""
        return self.s(i - 1) in {"==", "!="} or self.s(i + 1) in {"==", "!="}

    def listed(self, i: int) -> bool:
        """Whether the string at i is a member of a literal collection tested with `in` (not looped over with `for`)."""
        if self.s(i - 1) == "in" and not self.loops(i - 1):
            return True
        op = self.opener(i)
        return op >= 0 and self.s(op - 1) == "in" and not self.loops(op - 1)

    def searched(self, i: int) -> bool:
        """Whether the string at i is the left side of `in` (`"latency" in metric`): a part of a name looked for."""
        return self.s(i + 1) == "in" or (self.s(i + 1) == "not" and self.s(i + 2) == "in")

    def hit(self, pattern: str, i: int) -> Hit:
        """The hit of `pattern` at token i."""
        line = self.toks[i].start[0]
        return Hit(pattern, self.rel, self.fn[i], line, self.lines[line - 1].strip())


# -- F1: which way is better ---------------------------------------------------------------------------------------
#: The name table's metric names: what `_common.lower_is_better` and `is_descriptive` know, read from it so that a name
#: added there is watched here.
TABLE_NAMES = (
    set(_common.COST_KEYS)
    | set(_common.SPEED_KEYS)
    | set(_common.ERROR_RATE_KEYS)
    | set(_common.DESCRIPTIVE_KEYS)
)
#: Pieces of a name the table matches by prefix or that a reader might match by substring.
TABLE_PARTS = {"total_tokens", "latency"}
TABLE_FUNCS = {"lower_is_better", "is_descriptive"}
WORDS = {"lower", "higher"}
F1_OWNER_FILES = {"_runs.py"}
F1_OWNER_FNS = {("_common.py", "lower_is_better"), ("_common.py", "is_descriptive"), ("_common.py", "")}


def f1(S: Source) -> list[Hit]:
    """F1: the name table asked, or retyped, or a declared direction read, anywhere but `_runs`."""
    if S.rel in F1_OWNER_FILES:
        return []
    mine = {S.s(i + 1) for i in range(len(S.toks)) if S.s(i) == "def"}
    out = []
    for i, t in enumerate(S.toks):
        if t.type == tokenize.NAME and t.string in TABLE_FUNCS and S.s(i + 1) == "(" and S.s(i - 1) != "def":
            if (S.s(i - 1) == "." and S.s(i - 2) == "_common") or (
                S.s(i - 1) != "." and t.string not in mine
            ):
                out.append(S.hit("F1/name-table-call", i))
        elif t.type == tokenize.NAME and t.string in {
            "COST_KEYS",
            "SPEED_KEYS",
            "ERROR_RATE_KEYS",
            "DESCRIPTIVE_KEYS",
        }:
            out.append(S.hit("F1/name-table-name", i))
        elif S.is_str(i):
            v = S.value(i)
            if v in TABLE_NAMES and (S.equated(i) or S.listed(i)):
                out.append(S.hit("F1/metric-name-compared", i))
            elif v in TABLE_PARTS and (S.searched(i) or S.s(i - 2) == "startswith"):
                out.append(S.hit("F1/metric-name-part", i))
            elif v in {"metric_directions", "METRIC_DIRECTIONS"}:
                out.append(S.hit("F1/declared-directions-read", i))
            elif "neutral: a description" in v:
                out.append(S.hit("F1/better-word", i))
            elif v in WORDS and S.s(i + 1) == "," and S.value(i + 2) in WORDS and S.opener(i) >= 0:
                out.append(S.hit("F1/declared-direction-read", i))
    return [h for h in out if (h.rel, h.fn) not in F1_OWNER_FNS]


# -- F2: which runs make an arm ------------------------------------------------------------------------------------
F2_OWNER_FILES = {"model/runs.py"}
SUFFIX = re.compile(r"_r(?:\d|\{|\\d|\[0-9\])")
SORTERS = {"sorted", "max", "min", "sort"}


def f2(S: Source) -> list[Hit]:
    """F2: an arm's runs, its repeat set or its latest run worked out by a run id, a label or a sort, not `model.runs`."""
    if S.rel in F2_OWNER_FILES:
        return []
    out = []
    for i, t in enumerate(S.toks):
        if S.is_str(i):
            v = S.value(i)
            if SUFFIX.search(v) or v == "_r":
                out.append(S.hit("F2/run-id-suffix", i))
            elif v in {"repeat", "repeats"} and (S.equated(i) or S.listed(i) or S.searched(i)):
                out.append(S.hit("F2/purpose-or-label", i))
            elif v == "repeat_index":
                out.append(S.hit("F2/repeat-index", i))
        elif t.type == tokenize.NAME and t.string in SORTERS and S.s(i + 1) == "(" and S.s(i - 1) != "def":
            end = S.close(i + 1)
            words = {S.value(j) or S.s(j) for j in range(i, end + 1)}
            keyed = "key" in words or (t.string == "sort" and "lambda" in words)
            if "created_at" in words and keyed:
                out.append(S.hit("F2/order-by-time", i))
            elif "run_id" in words and t.string in {"max", "min"}:
                out.append(S.hit("F2/order-by-id", i))
            elif (
                t.string == "sorted"
                and [S.s(end + 1), S.s(end + 2), S.s(end + 3)] == ["[", "-", "1"]
                and any("run" in w or "score" in w for w in S.logical(i))
            ):
                out.append(S.hit("F2/last-of-sorted", i))
        if t.string == "[" and S.s(i + 1) == "-" and S.s(i + 2) == "1" and S.s(i + 3) == "]" and i:
            j = i - 1
            while S.s(j) == "]":
                j = S.open_of(j) - 1 if S.open_of(j) >= 0 else -1
            if j >= 0 and S.toks[j].type == tokenize.NAME and re.search(r"run", S.s(j)):
                out.append(S.hit("F2/last-run", i))
    return out


# -- F3: unknown, none and zero ------------------------------------------------------------------------------------
F3_OWNER_FNS = {("_spend.py", "shown")}
COSTY = re.compile(r"cost|usd")
NOT_A_COST = re.compile(r"known|^is_|^has_|_source$|^per_|_per_|recost|^costs$|^[a-z_]*costs$")
TRUTH_BEFORE = {"if", "elif", "and", "or", "not", "while"}
TRUTH_ENDS = {":", ")", "]", ",", "else", "and", "or", "if"}


def f3(S: Source) -> list[Hit]:
    """F3: a cost that was not recorded read as 0 (`or 0`, `get(..., 0)`) or as false (`if cost`)."""
    out = []
    for i, t in enumerate(S.toks):
        if t.string == "or" and S.s(i + 1) in {"0", "0.0"}:
            back = [S.value(j) or S.s(j) for j in range(max(S.first[i], i - 8), i)]
            if any(COSTY.search(w.lower()) for w in back):
                out.append(S.hit("F3/cost-or-zero", i))
        elif t.string == "get" and S.s(i + 1) == "(" and S.s(i + 3) == "," and S.s(i + 4) in {"0", "0.0"}:
            if COSTY.search(S.value(i + 2).lower()) and S.s(i + 5) == ")":
                out.append(S.hit("F3/cost-get-zero", i))
        elif (
            t.type == tokenize.NAME
            and COSTY.search(t.string.lower())
            and not NOT_A_COST.search(t.string.lower())
            and t.string != t.string.upper()
        ):
            ends = i + 1 < len(S.toks) and (
                S.s(i + 1) in TRUTH_ENDS or S.toks[i + 1].type == tokenize.NEWLINE
            )
            asked = S.s(i - 1) in TRUTH_BEFORE and ends
            ternary = (
                S.s(i + 1) in {"or", "if"}
                and S.s(i - 1) not in {".", "def"}
                and S.s(i + 2) not in {"0", "0.0"}
            )
            if asked or ternary:
                out.append(S.hit("F3/cost-truth", i))
    return [h for h in out if (h.rel, h.fn) not in F3_OWNER_FNS]


# -- F4: whether this is the public server -------------------------------------------------------------------------
F4_OWNER_FILES = {"_visibility.py"}


def f4(S: Source) -> list[Hit]:
    """F4: the public server's env, its hosts or its published list read apart from `_visibility.public()`."""
    if S.rel in F4_OWNER_FILES:
        return []
    out = []
    for i, t in enumerate(S.toks):
        if t.type == tokenize.NAME and t.string in {"public_env", "_PUBLIC"}:
            out.append(S.hit("F4/public-env", i))
        elif S.is_str(i):
            v = S.value(i)
            if v == "EVH_PUBLIC":
                out.append(S.hit("F4/public-env", i))
            elif v == "hosts" and S.s(i - 1) in {"[", "("} and S.s(i - 2) in {"LIMITS", "get"}:
                out.append(S.hit("F4/hosts", i))
            elif v == "publish" and S.s(i - 1) in {"[", "("} and S.s(i - 2) in {"LIMITS", "get"}:
                out.append(S.hit("F4/publish", i))
            elif v == "prompts" and (S.equated(i) or S.listed(i) or S.searched(i)):
                out.append(S.hit("F4/prompts", i))
    return out


# -- F5: which day it is -------------------------------------------------------------------------------------------
F5_OWNER_FNS = {("_common.py", "today")}


def f5(S: Source) -> list[Hit]:
    """F5: the day taken from the machine's clock, or from a now, apart from `_common.today()`."""
    out = []
    for i, t in enumerate(S.toks):
        if t.type != tokenize.NAME:
            continue
        call = S.s(i + 1) == "("
        end = S.close(i + 1) if call else i
        args = {S.s(j) for j in range(i + 2, end)}
        zoned = bool(args & {"timezone", "utc", "UTC", "tz", "tzinfo"}) or any("tz" in a for a in args)
        dated = t.string == "today" and call and S.s(i - 1) == "." and S.s(i - 2) in {"date", "datetime"}
        if dated or (t.string in {"localtime", "utcnow"} and call):
            out.append(S.hit("F5/machine-date", i))
        elif t.string == "now" and call and S.s(i - 1) == "." and S.s(i - 2) == "datetime":
            if end == i + 2:
                out.append(S.hit("F5/machine-date", i))
            elif S.s(end + 1) == "." and S.s(end + 2) == "date":
                out.append(S.hit("F5/day-of-now", i))
            elif S.s(end + 1) == "." and S.s(end + 2) == "strftime" and S.is_str(end + 4):
                fmt = S.value(end + 4)
                if fmt.startswith("%Y-%m-%d") and "%H" not in fmt:
                    out.append(S.hit("F5/day-of-now", i))
        elif t.string == "fromtimestamp" and call and not zoned:
            out.append(S.hit("F5/machine-date", i))
        elif (
            t.string == "strftime"
            and call
            and S.s(i - 1) == "."
            and S.s(i - 2) == "time"
            and S.s(end - 1) != ")"
        ):
            if "," not in {S.s(j) for j in range(i + 2, end)}:
                out.append(S.hit("F5/machine-date", i))
        elif t.string == "now" and call and end == i + 2 and S.s(end + 1) == "[":
            out.append(S.hit("F5/day-of-now", i))
    return [h for h in out if (h.rel, h.fn) not in F5_OWNER_FNS]


# -- F6: a goal's baseline -----------------------------------------------------------------------------------------
F6_OWNER_FILES = {"_baselines.py"}


def f6(S: Source) -> list[Hit]:
    """F6: a dataset's baselines read with no goal in the line that reads them, or the baselines' folder read apart."""
    if S.rel in F6_OWNER_FILES:
        return []
    out = []
    for i, t in enumerate(S.toks):
        if t.type == tokenize.NAME and t.string == "BASELINES":
            out.append(S.hit("F6/baselines-folder", i))
        elif S.is_str(i) and S.value(i) == "baselines":
            if S.s(i - 1) == "/":
                out.append(S.hit("F6/baselines-folder", i))
            elif (
                (S.s(i - 1) == "(" and S.s(i - 2) == "get") or (S.s(i - 1) == "[" and S.s(i + 1) == "]")
            ) and not any("goal" in w.lower() for w in S.logical(i)):
                out.append(S.hit("F6/baselines-without-goal", i))
    return out


FINDERS = (f1, f2, f3, f4, f5, f6)


def scan(src: str, rel: str) -> list[Hit]:
    """Every site in `src` (as module `rel`) that works one of the six facts out itself."""
    S = Source(src, rel)
    return [h for finder in FINDERS for h in finder(S)]


#: (pattern, file, def) -> why that place may ask for itself. A def of "" is module level. One line each; the check fails
#: when an entry matches nothing.
ALLOWED: dict[tuple[str, str, str], str] = {
    # F1
    (
        "F1/declared-direction-read",
        "_adapter.py",
        "metric_directions",
    ): "reads an adapter's own `METRIC_DIRECTIONS`, keeping "
    "its two valid words; `_runs.recorded_direction` reads it back from the run",
    (
        "F1/declared-direction-read",
        "axes.py",
        "axes_of",
    ): "an axis's declared word; an undeclared one asks `direction_of`, which is `_runs.direction`",
    (
        "F1/declared-direction-read",
        "promote_baseline.py",
        "evidence",
    ): "passes the goal's declaration on to the pair test; "
    "none leaves it to the rule (also in test_goal_block_direction's READS)",
    (
        "F1/declared-direction-read",
        "validate_tree.py",
        "v14_goals",
    ): "V14 checks what a goal declares against what the runs record, so it reads the declaration",
    (
        "F1/declared-direction-read",
        "model/goals.py",
        "direction_warning",
    ): "warns that a goal's own declared word is not a direction (V14, goal-new, goal-set); it decides no direction",
    (
        "F1/declared-directions-read",
        "_adapter.py",
        "metric_directions",
    ): "the reader of an adapter's declaration, for the writers that record it",
    (
        "F1/declared-directions-read",
        "catalog_adapter.py",
        "_recorded_on",
    ): "whether a run records the metric: a key present, not which way it goes",
    (
        "F1/declared-directions-read",
        "migrations/m0004_runs.py",
        "",
    ): "the score record's keys, which the migration moves",
    (
        "F1/declared-directions-read",
        "model/runs.py",
        "",
    ): "the score record's keys, which a score carries over from its run",
    (
        "F1/declared-directions-read",
        "rescore.py",
        "rescore_one",
    ): "copies the run's recorded declaration onto the new score (a writer)",
    (
        "F1/metric-name-compared",
        "axes.py",
        "value_text",
    ): "formats a cost in dollars and a speed in ms: the unit, not which way is better",
    ("F1/metric-name-compared", "axes.py", "cell_text"): "the same: the axis's unit",
    ("F1/metric-name-compared", "catalog_build.py", "axis_fmt"): "the same: the axis's unit",
    ("F1/metric-name-compared", "catalog_build.py", "tradeoff_charts"): "the same: the axis's unit",
    ("F1/metric-name-compared", "catalog_build.py", "strip_fmt"): "formats a latency in seconds: the unit",
    ("F1/metric-name-compared", "catalog_build.py", "metric_value"): "the same: the unit",
    (
        "F1/metric-name-part",
        "model/compare.py",
        "_conditions",
    ): "which measures are timings, to warn that a machine's "
    "speed differs: a condition of the measurement, not its direction",
    ("F1/name-table-name", "model/compare.py", ""): "the same: imports the timing names",
    ("F1/name-table-name", "model/compare.py", "_conditions"): "the same",
    (
        "F1/name-table-name",
        "_common.py",
        "classify_metrics",
    ): "the table's kinds (cost, speed, description) for a "
    "metric no run declared a kind for; `_runs.direction` still decides the direction",
    # F2
    (
        "F2/last-run",
        "catalog_charts.py",
        "cumulative",
    ): "`runs` is a chart's series of numbers, not run records",
    ("F2/order-by-time", "_outcome_join.py", "__init__"): "a label set's records of one key, not runs",
    ("F2/order-by-time", "_prompts.py", "versions"): "a prompt's versions, not runs",
    (
        "F2/order-by-time",
        "catalog_adapter.py",
        "arm_runs",
    ): "the adapter's listing, oldest first as its contract says; "
    "the latest run of an arm is `_latest`, which is `model.runs.latest`",
    ("F2/purpose-or-label", "run.py", "_run"): "a writer: asks where a repeat will be read before it runs "
    "(`_repeat_reading`, the owner's); R4 is on the writers",
    (
        "F2/purpose-or-label",
        "score_preview.py",
        "_set_of",
    ): "names the arms `arm_of` put under the `repeats` label",
    (
        "F2/purpose-or-label",
        "validate_tree.py",
        "v29_repeats_and_the_arms_that_read_them",
    ): "V29 validates the record's own `of` link, so it reads the purpose the writer recorded",
    (
        "F2/repeat-index",
        "cost_report.py",
        "_repeat_names",
    ): "names a row by the pass the run records; it decides no membership",
    (
        "F2/run-id-suffix",
        "run.py",
        "taken",
    ): "a writer: names the passes of `--repeat N`; membership is `repeat_index` (`model.runs.set_of`)",
    ("F2/run-id-suffix", "run.py", "_run"): "the same",
    # F3
    ("F3/cost-or-zero", "_jobs.py", "spent"): "a total: a job that recorded no spend has spent nothing yet",
    ("F3/cost-or-zero", "_spend.py", "run_child"): "a total of what a child recorded",
    (
        "F3/cost-or-zero",
        "_spend.py",
        "_run_spend",
    ): "a total of recorded costs: the cap's ledger adds what is known",
    ("F3/cost-or-zero", "_spend.py", "round_left"): "the same",
    (
        "F3/cost-or-zero",
        "catalog_adapter.py",
        "smoke_spend",
    ): "a total of the items' recorded costs, for a report with no "
    "`spent_usd`; a smoke of no spend adds no event",
    (
        "F3/cost-or-zero",
        "cost_report.py",
        "billed_and_recorded",
    ): "a total of recorded costs, beside the billed ones",
    ("F3/cost-or-zero", "judge_score.py", "stored_cost"): "a total of the verdicts' recorded costs",
    ("F3/cost-or-zero", "judge_score.py", "run_judging"): "the same",
    ("F3/cost-or-zero", "judge_score.py", "summarise"): "the same",
    (
        "F3/cost-or-zero",
        "judge_validate.py",
        "body",
    ): "a total of the judges' estimates; each line says `unpriced`",
    (
        "F3/cost-or-zero",
        "model/rounds.py",
        "_evidence",
    ): "a total of the runs' recorded costs, against the round's budget",
    (
        "F3/cost-or-zero",
        "model/spend.py",
        "judge_costs",
    ): "a total of the verdicts' costs, billed and estimated apart",
    ("F3/cost-or-zero", "model/studies.py", "state"): "a total of the trials' recorded costs",
    (
        "F3/cost-or-zero",
        "rescore.py",
        "_rescore_row",
    ): "compares a bill with the old recorded cost to say a row was re-costed (a writer)",
    ("F3/cost-or-zero", "run.py", "_run"): "a total of the runs made (a writer)",
    ("F3/cost-truth", "_spend.py", "add"): "adding 0 or nothing to the running total changes nothing",
    ("F3/cost-truth", "_spend.py", "net"): "the same",
    ("F3/cost-truth", "catalog_adapter.py", "smoke_spend"): "a smoke that spent nothing is no spend event",
    (
        "F3/cost-truth",
        "leaderboard.py",
        "_frontier",
    ): "`cost` is the name of the cost measure the reader chose, not a value",
    # F4
    (
        "F4/hosts",
        "catalog_serve.py",
        "allowed",
    ): "transport: the listener's host allow-list, not whether the surface is public; it decides which host names "
    "this listener answers to and whether a token is asked (an in-process EVH_PUBLIC call has no listener)",
    (
        "F4/hosts",
        "catalog_serve.py",
        "_api",
    ): "transport: the listener's host allow-list, not whether the surface is public; the origins a viewer's page may "
    "call from",
    (
        "F4/hosts",
        "catalog_serve.py",
        "do_HEAD",
    ): "transport: the listener's host allow-list, not whether the surface is public; a listener with hosts serves no "
    "file: nginx does",
    (
        "F4/hosts",
        "catalog_serve.py",
        "_get",
    ): "transport: the listener's host allow-list, not whether the surface is public; a client header is trusted only "
    "behind the named hosts",
    (
        "F4/hosts",
        "catalog_serve.py",
        "_json",
    ): "transport: the listener's host allow-list, not whether the surface is public; it tells the Workbench's page it "
    "is a viewer, on a listener with hosts",
    (
        "F4/hosts",
        "catalog_serve.py",
        "main",
    ): "transport: the listener's host allow-list, not whether the surface is public; sets the hosts from `--public`",
    (
        "F4/publish",
        "catalog_serve.py",
        "main",
    ): "sets and checks `--publish`; `_visibility.published` reads it back",
    (
        "F4/publish",
        "_prompts.py",
        "published",
    ): "reads the project's config; `_visibility.published` is its one caller",
    ("F4/prompts", "_prompts.py", "published"): "the same",
    (
        "F4/public-env",
        "_cmdline.py",
        "_run",
    ): "removes EVH_PUBLIC from a child's environment so that a command it runs is "
    "never public by inheritance",
    # F6
    ("F6/baselines-folder", "_common.py", "_paths"): "defines the folder",
    ("F6/baselines-folder", "_common.py", ""): "the same",
    ("F6/baselines-folder", "baselines_migrate.py", "plan"): "a migration reads the old layout",
    ("F6/baselines-folder", "fingerprint_migrate.py", "step"): "a migration reads every version file",
    (
        "F6/baselines-folder",
        "migrations/m0005_rounds.py",
        "_baselines",
    ): "a migration reads the layout of its day",
    ("F6/baselines-folder", "validate_tree.py", ""): "validate checks the files as they lie",
    ("F6/baselines-folder", "validate_tree.py", "v1_schemas"): "validate checks the files as they lie",
    ("F6/baselines-folder", "validate_tree.py", "v6_baselines"): "validate checks the files as they lie",
    ("F6/baselines-folder", "validate_tree.py", "v14_goals"): "validate checks the files as they lie",
    (
        "F6/baselines-without-goal",
        "catalog_arms.py",
        "render_arms",
    ): "lists every goal's baseline on the dataset, each with its own goal",
    ("F6/baselines-without-goal", "catalog_build.py", "events"): "the same",
    (
        "F6/baselines-without-goal",
        "catalog_build.py",
        "render_dataset",
    ): "the same: the cell names the goal beside each",
    ("F6/baselines-without-goal", "catalog_views.py", "print_dataset_catalog"): "the same",
    (
        "F6/baselines-without-goal",
        "ops/datasets.py",
        "show_dataset",
    ): "hands over every goal's baseline, each with its goal",
    ("F6/baselines-without-goal", "ops/records.py", "say_baselines"): "the same",
}


def pattern_of(h: Hit) -> tuple[str, str, str]:
    """The ALLOWED key of a hit."""
    return h.pattern, h.rel, h.fn


found: list[Hit] = []
for p in sorted(SCRIPTS.rglob("*.py")):
    rel = p.relative_to(SCRIPTS).as_posix()
    if rel.startswith("catalog_assets"):
        continue
    found += scan(p.read_text(encoding="utf-8"), rel)

if "--list" in sys.argv:
    for h in sorted(set(found), key=lambda h: (h.pattern, h.rel, h.line)):
        print(f"{h.pattern:32} {h.rel}:{h.line} in {h.fn or 'module'}: {h.text[:110]}")
    sys.exit(0)

for fact in ("F1", "F2", "F3", "F4", "F5", "F6"):
    mine = [h for h in found if h.pattern.startswith(fact + "/")]
    unlisted = [
        f"{h.pattern} {h.rel}:{h.line} in {h.fn or 'module'}: {h.text[:100]}"
        for h in mine
        if pattern_of(h) not in ALLOWED
    ]
    check(f"{fact}: no reader works the fact out itself, but where ALLOWED says why", not unlisted, unlisted)

stale = sorted(k for k in ALLOWED if k not in {pattern_of(h) for h in found})
check("ALLOWED lists only places the checks still find", not stale, stale)

# -- each pattern bites: a module that works the fact out itself is flagged ----------------------------------------
#: pattern -> source that works its fact out itself, as a module that is not the owner.
PROBES: dict[str, str] = {
    "F1/name-table-name": "from evaluation_harness._common import COST_KEYS\nlower = metric in COST_KEYS\n",
    "F1/name-table-call": "from evaluation_harness import _common\nlower = _common.lower_is_better(metric)\n",
    "F1/metric-name-compared": 'def which(metric):\n    return metric in ("wer", "cer")\n',
    "F1/metric-name-part": 'def which(metric):\n    return metric.startswith("total_tokens")\n',
    "F1/declared-direction-read": 'def which(goal):\n    return goal["direction"] in ("lower", "higher")\n',
    "F1/declared-directions-read": 'def which(rec):\n    return rec.get("metric_directions")\n',
    "F1/better-word": 'WORD = "neutral: a description"\n',
    "F2/run-id-suffix": 'import re\ndef rep(run_id):\n    return re.search(r"_r\\d+$", run_id)\n',
    "F2/order-by-time": 'def latest(runs):\n    return sorted(runs, key=lambda r: r["created_at"])[-1]\n',
    "F2/order-by-id": 'def latest(runs):\n    return max(runs, key=lambda r: r["run_id"])\n',
    "F2/last-of-sorted": "def latest(run_dirs):\n    return sorted(run_dirs)[-1]\n",
    "F2/last-run": "def latest(runs):\n    return runs[-1]\n",
    "F2/purpose-or-label": 'def is_repeat(rec):\n    return rec.get("purpose") == "repeat"\n',
    "F2/repeat-index": 'def part(rec):\n    return rec.get("repeat_index")\n',
    "F3/cost-or-zero": 'def cost(m):\n    return float(m.get("cost_usd") or 0)\n',
    "F3/cost-get-zero": 'def cost(m):\n    return m.get("cost_usd", 0)\n',
    "F3/cost-truth": 'def show(cost):\n    return f"${cost}" if cost else "-"\n',
    "F4/public-env": 'import os\ndef public():\n    return bool(os.environ.get("EVH_PUBLIC"))\n',
    "F4/hosts": 'def public():\n    return bool(LIMITS["hosts"])\n',
    "F4/publish": 'def shown():\n    return LIMITS.get("publish") or ()\n',
    "F4/prompts": 'def shown(pub):\n    return "prompts" in pub\n',
    "F5/machine-date": "from datetime import date\ndef day():\n    return date.today()\n",
    "F5/day-of-now": "from datetime import datetime, timezone\ndef day():\n    return datetime.now(timezone.utc).date()\n",
    "F6/baselines-without-goal": 'def base(v):\n    return v.get("baselines")[-1]\n',
    "F6/baselines-folder": 'def base(data, ds):\n    return data / "baselines" / ds\n',
}
#: more ways to work a fact out, each flagged by the pattern named.
ALSO: list[tuple[str, str]] = [
    ("F1/metric-name-compared", 'def which(metric):\n    return metric == "latency_ms"\n'),
    ("F1/metric-name-part", 'def which(metric):\n    return "latency" in metric\n'),
    ("F1/name-table-call", "def which(metric):\n    return is_descriptive(metric)\n"),
    ("F2/run-id-suffix", 'def rid(base, i):\n    return f"{base}_r{i}"\n'),
    ("F2/order-by-time", 'def latest(runs):\n    return max(runs, key=lambda r: r["created_at"])\n'),
    ("F2/last-run", "def latest(run_ids):\n    return run_ids[-1]\n"),
    ("F3/cost-truth", "def show(cost_usd):\n    if not cost_usd:\n        return '-'\n"),
    ("F4/hosts", 'def public():\n    return LIMITS.get("hosts")\n'),
    ("F5/machine-date", "from datetime import datetime\ndef day():\n    return datetime.now()\n"),
    ("F5/machine-date", "import time\ndef day():\n    return time.localtime()\n"),
    (
        "F5/machine-date",
        "from datetime import datetime\ndef day(ts):\n    return datetime.fromtimestamp(ts)\n",
    ),
    ("F5/machine-date", "import time\ndef day():\n    return time.strftime('%Y-%m-%d')\n"),
    ("F5/machine-date", "from datetime import datetime\ndef day():\n    return datetime.today()\n"),
    ("F5/day-of-now", "def day():\n    return now()[:10]\n"),
    ("F5/day-of-now", "def day():\n    return datetime.now(timezone.utc).strftime('%Y-%m-%d')\n"),
    ("F6/baselines-folder", "def base():\n    return BASELINES\n"),
]
in_source = set(re.findall(r'S\.hit\("(F\d/[a-z-]+)"', Path(__file__).read_text(encoding="utf-8")))
check("every pattern has a probe", in_source == set(PROBES), sorted(in_source ^ set(PROBES)))
for pat, probe in [*PROBES.items(), *ALSO]:
    got = {h.pattern for h in scan(probe, "probe.py")}
    check(f"{pat} bites on: {probe.splitlines()[-1].strip()}", pat in got, sorted(got))

#: the same work, done by the owner, is not flagged.
OWNERS: list[tuple[str, str, str]] = [
    (
        "F1",
        "_runs.py",
        'def direction(metric):\n    return "lower" if metric in ("wer", "cer") else "higher"\n',
    ),
    ("F2", "model/runs.py", 'def latest(runs):\n    return max(runs, key=lambda r: r["created_at"])\n'),
    ("F3", "_spend.py", 'def shown(cap):\n    return "NONE" if cap is None else f"${cap:.2f}"\n'),
    ("F4", "_visibility.py", 'import os\ndef public_env():\n    return bool(os.environ.get("EVH_PUBLIC"))\n'),
    ("F5", "_common.py", "def today():\n    return datetime.now(timezone.utc).date()\n"),
    ("F6", "_baselines.py", 'def folder(data, ds):\n    return data / "baselines" / ds\n'),
]
for fact, rel, src in OWNERS:
    owned = [h.pattern for h in scan(src, rel) if h.pattern.startswith(fact)]
    check(f"{fact}: the owner's own code ({rel}) is not flagged", not owned, owned)
quiet = (
    "from datetime import datetime, timezone\nimport time\n"
    'def stamps(ts, fmt):\n    a = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")\n'
    "    b = datetime.fromtimestamp(ts, tz=timezone.utc)\n    c = time.strftime(fmt, time.gmtime())\n"
    '    d = [x for x in v.get("baselines", []) if x.get("goal") == g]\n    return a, b, c, d\n'
)
check(
    "a timestamp in UTC, a time given its struct and a baseline chosen by its goal are not flagged",
    not scan(quiet, "probe.py"),
    scan(quiet, "probe.py"),
)

# -- the other source checks of these facts are still there ------------------------------------------------------------
suite = (HARNESS / "tests" / "self_test.py").read_text(encoding="utf-8")
for name in (
    "test_cap_shown.py",
    "test_today.py",
    "test_direction.py",
    "test_goal_block_direction.py",
    "test_one_source.py",
):
    check(f"{name} is in the suite", f'"{name}"' in suite and (HARNESS / "tests" / name).exists(), name)

sys.exit(summary())
