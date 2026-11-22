#!/usr/bin/env python3
"""llms.txt, the agent-facing index of this repository's docs (llmstxt.org), made from tools/llms.in.txt and the docs.

    python tools/llms_txt.py           write llms.txt
    python tools/llms_txt.py --check   exit 1 when llms.txt is not what this would write, a link or an anchor does not
                                       resolve, a path in backticks does not exist, a per-type index misses one of its
                                       documents, or the file outgrows its budget

The template's prose and maps are kept by hand; what can go stale is generated: a `{{doc PATH | note}}` line is the
document's own title (its H1) and status (its Status line), `{{agent-rules}}` lists AGENTS.md's sections,
`{{decision-sets}}` the ADR, RFC, PRD and UXS indexes with their counts by status, `{{guides}}` the guides, and
`{{tutorials}}` and `{{reports}}` the tutorials and the worked evals' reports.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "tools" / "llms.in.txt"
OUT = ROOT / "llms.txt"
#: llmstxt.org: short enough to load whole (the fleet's brief: under about 8k tokens).
BUDGET_BYTES = 30_000
SETS = (
    ("docs/adr", "ADRs", "the decisions that shape the architecture"),
    ("docs/rfc", "RFCs", "the technical designs, with their alternatives"),
    ("docs/prd", "PRDs", "what users need, and why"),
    ("docs/uxs", "UXS", "what users see and type"),
)
GUIDES = (
    "docs/REPRODUCE.md",
    "harness/docs/SCENARIO.md",
    "harness/docs/INTEGRATION.md",
    "harness/docs/UPGRADING.md",
)
STATUS = re.compile(r"^\s*(?:-\s*)?\*\*Status(?:\*\*:|:\*\*)\s*(.*)$", re.M)
LINK = re.compile(r"\]\(([^)\s]+)\)")
TICKED = re.compile(r"`([A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]*)+)`")


def title(path: Path) -> str:
    """A document's H1."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    raise SystemExit(f"llms.txt: {path.relative_to(ROOT)} has no H1")


def status_line(path: Path) -> str:
    """A document's whole Status line (wrapped onto indented lines too), links as their text."""
    text = path.read_text(encoding="utf-8")
    m = STATUS.search(text)
    if not m:
        return ""
    s = m.group(1)
    for line in text[m.end() :].splitlines()[1:]:
        if not line.startswith("  ") or line.lstrip().startswith("- "):
            break
        s += " " + line.strip()
    return re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s).strip()


def status(path: Path) -> str:
    """A document's status as shown: its first clause, up to the first ';' or '. '."""
    s = re.split(r";|\.\s", status_line(path), maxsplit=1)[0].strip().rstrip(".")
    return s if len(s) <= 90 else s[:87].rstrip() + "..."


def doc_line(rel: str, note: str) -> str:
    p = ROOT / rel
    if not p.is_file():
        raise SystemExit(f"llms.txt: {rel} does not exist")
    st = status(p)
    return f"- [{title(p)}]({rel}): {note.strip()}" + (f" (status: {st})" if st else "")


def slug(heading: str) -> str:
    """GitHub's anchor for a heading."""
    s = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return s.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    return {
        slug(ln.lstrip("#"))
        for ln in path.read_text(encoding="utf-8").splitlines()
        if re.match(r"#{1,6} ", ln)
    }


def agent_rules() -> str:
    lines = []
    for h in re.findall(r"^## (.+)$", (ROOT / "AGENTS.md").read_text(encoding="utf-8"), re.M):
        lines.append(
            f"- [AGENTS.md: {h}](AGENTS.md#{slug(h)}): the rules for this area, read before changing it"
        )
    return "\n".join(lines)


#: A status in one word, the first that applies: a document partly superseded counts as superseded, one accepted and
#: built as built.
KINDS = (
    ("superseded", "superseded"),
    ("retired", "retired"),
    ("draft", "draft"),
    ("proposed", "proposed"),
    ("built", "built"),
    ("completed", "built"),
    ("implemented", "built"),
    ("accepted", "accepted"),
    ("active", "active"),
)


def kind(path: Path) -> str:
    """The status's own first word when it is one of KINDS' (accepted and built counts as built), else the first of
    KINDS' words it holds ("Partly superseded by ..."): "Built ..., from its third draft" is built."""
    s = status_line(path).lower()
    lead = dict(KINDS).get(s.split(" ", 1)[0].strip(",:—") if s else "")
    if lead == "accepted" and "built" in s:
        return "built"
    return lead or next((k for word, k in KINDS if word in s), "unstated")


def decision_sets() -> str:
    lines = []
    for folder, name, what in SETS:
        docs = [p for p in sorted((ROOT / folder).glob("*.md")) if p.name != "index.md"]
        counts = Counter(kind(p) for p in docs)
        by = ", ".join(f"{n} {k.lower()}" for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
        lines.append(
            f"- [{name}]({folder}/index.md): {what}; {len(docs)} documents, each with its status ({by})"
        )
    return "\n".join(lines)


def listed(rels: list[str], note) -> str:
    return "\n".join(doc_line(r, note(r)) for r in rels)


def render() -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    tutorials = [str(p.relative_to(ROOT)) for p in sorted((ROOT / "docs/tutorials").glob("*.md"))]
    reports = [str(p.relative_to(ROOT)) for p in sorted((ROOT / "research").glob("REPORT_*.md"))]
    blocks = {
        "agent-rules": agent_rules(),
        "decision-sets": decision_sets(),
        "guides": listed(list(GUIDES), lambda r: "a guide"),
        "tutorials": listed(tutorials, lambda r: "a tutorial, step by step"),
        "reports": listed(reports, lambda r: "a worked eval's report"),
    }
    for k, v in blocks.items():
        text = text.replace("{{" + k + "}}", v)
    text = re.sub(r"\{\{doc ([^|}]+)\|([^}]+)\}\}", lambda m: doc_line(m.group(1).strip(), m.group(2)), text)
    left = re.findall(r"\{\{[^}]*\}\}", text)
    if left:
        raise SystemExit(f"llms.txt: unknown template marks {left}")
    return text


def problems(text: str) -> list[str]:
    out = []
    for target in LINK.findall(text):
        if target.startswith(("http://", "https://")):
            continue
        rel, _, anchor = target.partition("#")
        p = ROOT / rel
        if not p.exists():
            out.append(f"a link to {rel}, which does not exist")
        elif anchor and p.suffix == ".md" and anchor not in anchors(p):
            out.append(f"a link to {rel}#{anchor}: no such heading")
    for path in TICKED.findall(text):
        if not (ROOT / path.rstrip("/")).exists():
            out.append(f"`{path}`: no such path")
    for folder, _, _ in SETS:
        index = (ROOT / folder / "index.md").read_text(encoding="utf-8")
        linked = {t.split("#")[0] for t in LINK.findall(index)}
        for p in sorted((ROOT / folder).glob("*.md")):
            if p.name != "index.md" and p.name not in linked:
                out.append(f"{folder}/index.md does not list {p.name}")
    if len(text.encode()) > BUDGET_BYTES:
        out.append(f"{len(text.encode()):,} bytes, over the {BUDGET_BYTES:,} budget")
    return out


def main() -> int:
    text = render()
    if "--check" in sys.argv[1:]:
        found = problems(text)
        if not OUT.is_file() or OUT.read_text(encoding="utf-8") != text:
            found.insert(0, "llms.txt is not what tools/llms_txt.py writes: run `make llms`")
        for p in found:
            print(f"FAIL llms.txt: {p}")
        print(
            f"llms.txt: {len(text.encode()):,} bytes, {text.count(chr(10) + '- ')} links"
            + (" ok" if not found else "")
        )
        return 1 if found else 0
    found = problems(text)
    if found:
        for p in found:
            print(f"FAIL llms.txt: {p}")
        return 1
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote llms.txt: {len(text.encode()):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
