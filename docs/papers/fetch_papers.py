#!/usr/bin/env python3
"""Download the papers cited by this repo, for offline reading. STDLIB ONLY.

    python docs/papers/fetch_papers.py          # only those whose licence permits mirroring
    python docs/papers/fetch_papers.py --all    # every cited paper, PERSONAL USE ONLY

WHY THE DEFAULT IS THE SMALLER SET, AND WHY NOTHING IS COMMITTED

  Twelve of the twenty-four works cited here are CC BY or CC BY-SA and may be
  redistributed with attribution. The other twelve may not: ten arXiv papers carry
  `arxiv.org/licenses/nonexclusive-distrib/1.0`, which grants ARXIV a distribution right
  and says nothing about anyone else, and two are behind ACM and JSTOR paywalls.

  Downloading any of them to read is fine. REDISTRIBUTING the second group is not, so
  this directory's output is gitignored and `--all` prints a reminder of which files it
  has just written that must not be committed.

  Licences were read from each publisher's own page on 2026-09-29 and are recorded in
  README.md beside every entry. Re-check before relying on them: a paper can be
  relicensed, and arXiv shows the licence of the version you are looking at.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: (slug, url, licence, redistributable). PDF urls are the publisher's canonical ones.
PAPERS = [
    # ── CC BY / CC BY-SA: mirroring permitted with attribution ───────────────
    ("lin-2004-rouge", "https://aclanthology.org/W04-1013.pdf", "CC BY 4.0", True),
    ("conll-2003-ner", "https://aclanthology.org/W03-0419.pdf", "CC BY 4.0", True),
    ("dror-2018-significance", "https://aclanthology.org/P18-1128.pdf", "CC BY 4.0", True),
    ("kryscinski-2019-summarization-critique", "https://aclanthology.org/D19-1051.pdf", "CC BY 4.0", True),
    ("wadden-2020-scifact", "https://aclanthology.org/2020.emnlp-main.609.pdf", "CC BY 4.0", True),
    ("ding-2021-few-nerd", "https://aclanthology.org/2021.acl-long.248.pdf", "CC BY 4.0", True),
    ("reimers-2019-sentence-bert", "https://arxiv.org/pdf/1908.10084", "CC BY-SA 4.0", True),
    ("thakur-2021-beir", "https://arxiv.org/pdf/2104.08663", "CC BY-SA 4.0", True),
    ("he-2021-deberta-v3", "https://arxiv.org/pdf/2111.09543", "CC BY 4.0", True),
    ("wang-2022-e5", "https://arxiv.org/pdf/2212.03533", "CC BY 4.0", True),
    ("zaratiana-2023-gliner", "https://arxiv.org/pdf/2311.08526", "CC BY 4.0", True),
    ("zhang-2024-gsm1k", "https://arxiv.org/pdf/2405.00332", "CC BY 4.0", True),
    # ── arXiv non-exclusive: read, do not redistribute ───────────────────────
    ("hermann-2015-cnn-dailymail", "https://arxiv.org/pdf/1506.03340", "arXiv non-exclusive", False),
    ("zhang-2015-char-cnn", "https://arxiv.org/pdf/1509.01626", "arXiv non-exclusive", False),
    ("nallapati-2016-abstractive", "https://arxiv.org/pdf/1602.06023", "arXiv non-exclusive", False),
    ("see-2017-pointer-generator", "https://arxiv.org/pdf/1704.04368", "arXiv non-exclusive", False),
    ("guo-2017-calibration", "https://arxiv.org/pdf/1706.04599", "arXiv non-exclusive", False),
    ("devlin-2018-bert", "https://arxiv.org/pdf/1810.04805", "arXiv non-exclusive", False),
    ("yin-2019-zero-shot-nli", "https://arxiv.org/pdf/1909.00161", "arXiv non-exclusive", False),
    ("lewis-2019-bart", "https://arxiv.org/pdf/1910.13461", "arXiv non-exclusive", False),
    ("song-2020-mpnet", "https://arxiv.org/pdf/2004.09297", "arXiv non-exclusive", False),
    ("xiao-2023-c-pack-bge", "https://arxiv.org/pdf/2309.07597", "arXiv non-exclusive", False),
]

#: Cited, and not fetchable: no open PDF exists to download.
PAYWALLED = [
    ("Järvelin & Kekäläinen (2002), nDCG", "https://dl.acm.org/doi/10.1145/582415.582418", "© ACM"),
    ("Holm (1979), sequentially rejective procedure", "Scand. J. Statist. 6(2):65-70", "© journal"),
    ("Demšar (2006), classifier comparisons", "https://www.jmlr.org/papers/v7/demsar06a.html", "no licence stated"),
]


def get(url: str, dest: Path, delay: float) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": "eval-harness-paper-fetch/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            body = r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        print(f"  FAILED {dest.name}: {exc}")
        return False
    if not body.startswith(b"%PDF"):
        # A publisher serving an interstitial instead of the file. Writing it would leave
        # an HTML page wearing a .pdf extension, which is worse than no file.
        print(f"  FAILED {dest.name}: response is not a PDF ({len(body)} bytes)")
        return False
    dest.write_bytes(body)
    print(f"  {dest.name}  {len(body) / 1024:.0f} KB")
    time.sleep(delay)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--all", action="store_true",
                    help="also fetch papers that may NOT be redistributed (personal use)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    ap.add_argument("--out", type=Path, default=HERE)
    args = ap.parse_args()

    want = [p for p in PAPERS if p[3] or args.all]
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"fetching {len(want)} paper(s) into {args.out}\n")

    ok = restricted = 0
    for slug, url, lic, redist in want:
        dest = args.out / f"{slug}.pdf"
        if dest.exists():
            print(f"  {dest.name}  (already here)")
            ok += 1
            continue
        if get(url, dest, args.delay):
            ok += 1
            restricted += 0 if redist else 1

    print(f"\n{ok} of {len(want)} fetched")
    if restricted:
        print(f"\n  {restricted} of them are NOT redistributable — arXiv's non-exclusive")
        print("  licence covers arXiv, not you. Read them; do not commit them. This")
        print("  directory is gitignored for exactly that reason.")
    print("\nCited but not fetchable:")
    for name, where, lic in PAYWALLED:
        print(f"  {name:<46} {lic:<18} {where}")
    print("\nLicences were read from each publisher's page on 2026-09-29 and are listed")
    print("in README.md. Re-check before relying on them — papers can be relicensed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
