"""Sheets a person fills in a spreadsheet and the harness reads back (RFC-023): written so Excel opens them, read
as Excel saves them.

Written as UTF-8 with a byte-order mark (Excel reads a CSV without one in the machine's legacy encoding, so accents
and quotes come out garbled). Read with or without that mark, and with `,`, `;` (Excel's separator where the comma
is the decimal mark) or a tab between columns. An Excel workbook (.xlsx) is refused with what to do instead: the
harness reads CSV only.

The allowed answers, when the sheet has them (`label-sheet --choices`), travel in the label column's own header,
`label [file|dismiss|escalate]`, so the sheet that comes back still says what was allowed; `label-import` refuses
any other answer, naming the rows.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any

from evaluation_harness import _store
from evaluation_harness._common import die

LABEL, ALSO, NOTE = "label", "also right", "note"
_CHOICES = re.compile(r"^label \[(.+)\]$")


def label_header(choices: list[str] | None) -> str:
    """The label column's header: `label`, or `label [a|b|c]` with the allowed answers."""
    return f"{LABEL} [{'|'.join(choices)}]" if choices else LABEL


def write_csv(header: list[str], rows: list[list[Any]], path: Path | None = None) -> str:
    """The sheet as CSV text (a byte-order mark first, for Excel); written to `path` when one is given."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(header)
    w.writerows(rows)
    text = "\ufeff" + buf.getvalue()
    if path is not None:
        _store.mkdir(path.parent, parents=True, exist_ok=True)
        _store.write_text(path, text, encoding="utf-8", newline="")
    return text


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str] | None]:
    """A filled sheet's rows, each keyed by column (the label column as `label` whatever its header), and the
    allowed answers its header names (None when it names none)."""
    raw = _store.read_bytes(path)
    if path.suffix.lower() in (".xlsx", ".xls", ".ods") or raw[:2] == b"PK":
        die(
            f"{path}: a spreadsheet workbook, not CSV. In Excel: File > Save As > CSV UTF-8 (Comma delimited); "
            "a `;`-separated CSV is read too.",
            "invalid-file",
        )
    text = raw.decode("utf-8-sig")
    first = text.split("\n", 1)[0]
    delimiter = max((",", ";", "\t"), key=first.count)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        return [], None
    choices = None
    for k, h in enumerate(header):
        m = _CHOICES.match(h)
        if m:
            choices = [c.strip() for c in m.group(1).split("|") if c.strip()]
            header[k] = LABEL
    rows = [dict(zip(header, (c.strip() for c in r))) for r in reader if any(c.strip() for c in r)]
    return rows, choices
