"""MkDocs hooks for the documentation site.

1. Add harness/docs/*.md as pages under harness/ without moving them out of the harness,
   where they document the code beside them.
2. Rewrite every link that leaves the documentation -- a report, a script, a PDF, a JSON
   capture, anything outside the built pages -- into a GitHub URL, resolved from the page's
   REAL location in the repo. The docs were written to be read on GitHub; this keeps every
   one of their links working on the site without editing them.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from mkdocs.structure.files import File

ROOT = Path(__file__).resolve().parents[1]
BLOB = "https://github.com/chipi/eval-harness/blob/main"
TREE = "https://github.com/chipi/eval-harness/tree/main"
EXTRA = {"harness/" + p.name: p for p in sorted((ROOT / "harness" / "docs").glob("*.md"))}
LINK = re.compile(r"(\]\()([^)\s]+?)(\))")


def on_files(files, config):
    for dest, src in EXTRA.items():
        files.append(File(dest, src_dir=str(src.parent.parent), dest_dir=config["site_dir"],
                          use_directory_urls=config["use_directory_urls"]))
        # File() derives src_uri from src_dir + path; point it at the real file.
        f = files.get_file_from_path(dest)
        f.abs_src_path = str(src)
    return files


def _real_path(page) -> Path:
    src = page.file.src_uri
    return EXTRA[src] if src in EXTRA else ROOT / "docs" / src


def on_page_markdown(markdown, page, config, files):
    real = _real_path(page)
    built = {f.src_uri for f in files.documentation_pages()}

    def fix(m):
        target = m.group(2)
        if re.match(r"^[a-z][a-z0-9+.-]*:", target) or target.startswith(("#", "/")):
            return m.group(0)
        path, _, anchor = target.partition("#")
        absolute = (real.parent / path).resolve()
        try:
            rel_docs = absolute.relative_to(ROOT / "docs").as_posix()
        except ValueError:
            rel_docs = None
        inv = {str(p.resolve()): k for k, p in EXTRA.items()}
        dest = inv.get(str(absolute)) or (rel_docs if rel_docs in built else None)
        if dest:  # a page of this site: link to it relative to the current page's URI
            rel = os.path.relpath(dest, os.path.dirname(page.file.src_uri) or ".")
            return f"{m.group(1)}{rel}{'#' + anchor if anchor else ''}{m.group(3)}"
        repo_rel = absolute.relative_to(ROOT).as_posix()
        base = TREE if absolute.is_dir() else BLOB
        return f"{m.group(1)}{base}/{repo_rel}{'#' + anchor if anchor else ''}{m.group(3)}"

    return LINK.sub(fix, markdown)
