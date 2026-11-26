"""The one rule for an id a person names (a dataset, a system, a goal, a scorer, a field set, a label set, a reference, a
run, a round, a model, a deployment): ASCII letters and digits, and the punctuation the kind allows.

An id is a file name, an arm id's part (`<label>/<dataset>/<system>`) and a URL segment, so what keeps it safe stays: it
starts with a letter or digit (never `.` or `-`), holds no `..`, no space, no control character, no path separator, and,
for a kind that is lowercase, no capital. The JSON schemas that pattern an id use `IdRule.pattern`, so they say the same.

0.8.2 let an id be spelled in any script and 0.8.3 took that back: a writer refuses a letter outside ASCII, but a project
may hold ids 0.8.2 made, so a read (`read=True`) takes any letter or digit under the same safety rules.
"""

from __future__ import annotations

_DIGITS = "0123456789"
_LOWER = "abcdefghijklmnopqrstuvwxyz"


class IdRule:
    """One kind of id: `lower` (lowercase only), `punct` (the punctuation allowed after the first character) and the
    length limit `max_len` (None: none)."""

    def __init__(self, *, lower: bool, punct: str = "._-", max_len: int | None = None) -> None:
        self.lower = lower
        self.punct = punct
        self.max_len = max_len
        self._letters = _LOWER + _DIGITS if lower else _LOWER + _LOWER.upper() + _DIGITS

    def __repr__(self) -> str:
        return f"IdRule(lower={self.lower}, punct={self.punct!r}, max_len={self.max_len})"

    def says(self) -> str:
        """The rule in words, for a refusal that says what an id may be."""
        shown = " ".join(f"'{c}'" for c in self.punct)
        return (
            f"ASCII {'lowercase letters' if self.lower else 'letters'} and digits"
            + (f", {shown}" if shown else "")
            + (f" (at most {self.max_len})" if self.max_len else "")
            + ", starting with a letter or digit"
        )

    def problem(self, value: object, read: bool = False) -> str | None:
        """Why `value` is not an id of this kind, or None when it is one. `read`: an id already on disk, where a letter or
        digit of any script passes (0.8.2 made some); a writer's check leaves it False."""
        if not isinstance(value, str) or not value:
            return "an id is a non-empty text"
        if self.max_len is not None and len(value) > self.max_len:
            return f"longer than {self.max_len} characters"
        for i, c in enumerate(value):
            if c in "/\\":
                return f"a path separator at {i}"
            if not ((c.isalnum() if read else c in self._letters) or (i > 0 and c in self.punct)):
                if not c.isascii():
                    return f"{c!r} at {i} is not an ASCII letter or digit"
                return f"{c!r} at {i} is not allowed" + (
                    " (an id starts with a letter or digit)" if i == 0 else ""
                )
        if ".." in value:
            return "'..' is not allowed"
        if self.lower and value.lower() != value:
            return "not lowercase"
        return None

    def ok(self, value: object, read: bool = False) -> bool:
        """Whether `value` is an id of this kind."""
        return self.problem(value, read) is None

    def fullmatch(self, value: object) -> bool:
        """`re.Pattern.fullmatch`'s shape, so an Entity takes a rule where it took a pattern."""
        return self.ok(value)

    def check(self, value: str, what: str) -> str:
        """The id, or ValueError naming `what` and why it is not one."""
        why = self.problem(value)
        if why:
            raise ValueError(f"{what} {str(value)[:60]!r}: {why} ({self.says()})")
        return value

    @property
    def pattern(self) -> str:
        """The rule as a JSON schema pattern."""
        letters = "a-z0-9" if self.lower else "A-Za-z0-9"
        tail = letters + "".join(c for c in self.punct if c != "-") + ("-" if "-" in self.punct else "")
        count = "*" if self.max_len is None else "{0," + str(self.max_len - 1) + "}"
        guard = "(?!.*\\.\\.)" if "." in self.punct else ""
        return f"^{guard}[{letters}][{tail}]{count}$"


#: A dataset, a system, a capture, a reference, a run, a scorer: capitals allowed.
NAME = IdRule(lower=False)
#: A model, a deployment, a record's default: lowercase.
LOWER = IdRule(lower=True)
#: A label set's, a tag set's, a failure-mode set's own name.
SET = IdRule(lower=True, max_len=100)
#: A goal, a field set.
SNAKE = IdRule(lower=True, punct="_")
#: A study.
STUDY = IdRule(lower=True, punct="_-", max_len=61)
#: A dataset in the exposure register, a scorer a sheet names.
EXPOSURE = IdRule(lower=False, max_len=200)
SHEET_SCORER = IdRule(lower=False, max_len=100)

#: The kinds a JSON schema patterns (the rule each schema says, `pattern`).
NAMED = (NAME, LOWER, SET, SNAKE)
