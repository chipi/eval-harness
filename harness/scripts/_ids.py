"""The one rule for an id a person names (a dataset, a system, a goal, a scorer, a field set, a label set, a reference, a
run, a round, a model, a deployment): the letters and digits of any script, and the punctuation the kind allows.

An id is a file name, an arm id's part (`<label>/<dataset>/<system>`) and a URL segment, so what keeps it safe stays:
it starts with a letter or digit (never `.` or `-`), holds no `..`, no space, no control or format character
(Unicode categories C* and Z*), no path separator, and, for a kind that is lowercase, is its own `str.lower()` (defined
for every script: CJK, which has no case, passes). It is also in Unicode NFC: a macOS file system and a paste would
otherwise make two spellings of one id (`é` and `e` + U+0301). A letter or digit is what `str.isalnum()` says, which is
what `[^\\W_]` matches in a Python pattern: the JSON schemas that pattern an id use `IdRule.pattern`, so they match the same set.
Combining marks (Unicode M*) are not letters; a script that needs them (Devanagari vowel signs) cannot be spelled.
"""

from __future__ import annotations

import unicodedata

#: The ASCII upper-case letters a lowercase schema pattern can refuse; a regular expression cannot say "lowercase" for
#: other scripts, so `IdRule.pattern` is a superset there and `IdRule.problem` is the rule.
_UPPER_ASCII = "(?!.*[A-Z])"


class IdRule:
    """One kind of id: `lower` (lowercase only), `punct` (the punctuation allowed after the first character) and the
    length limit `max_len` (None: none)."""

    def __init__(self, *, lower: bool, punct: str = "._-", max_len: int | None = None) -> None:
        self.lower = lower
        self.punct = punct
        self.max_len = max_len

    def __repr__(self) -> str:
        return f"IdRule(lower={self.lower}, punct={self.punct!r}, max_len={self.max_len})"

    def says(self) -> str:
        """The rule in words, for a refusal that says what an id may be."""
        shown = " ".join(f"'{c}'" for c in self.punct)
        return (
            f"{'lowercase letters' if self.lower else 'letters'} and digits of any script"
            + (f", {shown}" if shown else "")
            + (f" (at most {self.max_len})" if self.max_len else "")
            + ", starting with a letter or digit, in Unicode NFC"
        )

    def problem(self, value: object) -> str | None:
        """Why `value` is not an id of this kind, or None when it is one."""
        if not isinstance(value, str) or not value:
            return "an id is a non-empty text"
        nfc = unicodedata.normalize("NFC", value)
        if nfc != value and self.problem(nfc) is None:
            return f"not in Unicode NFC: write {nfc!r}"
        if self.max_len is not None and len(value) > self.max_len:
            return f"longer than {self.max_len} characters"
        for i, c in enumerate(value):
            cat = unicodedata.category(c)
            if cat[0] in "CZ":
                return (
                    f"a {'control or format character' if cat[0] == 'C' else 'space'} (U+{ord(c):04X}) at {i}"
                )
            if c in "/\\":
                return f"a path separator at {i}"
            if not (c.isalnum() or (i > 0 and c in self.punct)):
                return f"{c!r} at {i} is not allowed" + (
                    " (an id starts with a letter or digit)" if i == 0 else ""
                )
        if ".." in value:
            return "'..' is not allowed"
        if self.lower and value.lower() != value:
            return "not lowercase"
        return None

    def ok(self, value: object) -> bool:
        """Whether `value` is an id of this kind."""
        return self.problem(value) is None

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
        """The rule as a JSON schema pattern (Python `re`: `[^\\W_]` is exactly `str.isalnum()` less the underscore). It
        cannot say NFC, and for a lowercase kind refuses only the ASCII capitals: the schema is never stricter than the
        rule, `problem` is the rule."""
        extra = "".join(sorted((c for c in self.punct if c != "_"), key=lambda c: c == "-"))
        if "_" in self.punct:
            tail = r"[\w" + extra + "]" if extra else r"\w"
        else:
            tail = r"(?:[^\W_]|[" + extra + "])" if extra else r"[^\W_]"
        count = "*" if self.max_len is None else "{0," + str(self.max_len - 1) + "}"
        guards = ("(?!.*\\.\\.)" if "." in self.punct else "") + (_UPPER_ASCII if self.lower else "")
        return f"^{guards}[^\\W_]{tail}{count}$"


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
