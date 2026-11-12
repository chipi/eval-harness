# Product: the public site

<!-- impeccable:product-schema 1 -->

The shared product record is the repository's root PRODUCT.md. This file holds what is particular to the public site,
evals.humancopilot.eu.

## Platform

web

## Users

The primary reader is an engineer or a team lead deciding whether to adopt the harness (owner, 2026-11-12). They read
the published evals and the method to judge whether to trust it and use it on their own data.

## Product Purpose

The site shows the method working on six public benchmarks, explains the method, and gets an adopter from reading to
a first run on their own data. Success is a reader who installs the harness and runs it, or who knows exactly why it
does not fit them.

## Operating Context

- **Pages:** home, evals (one page each: AG News, DBpedia, Few-NERD, SciFact, summarisation, SummEval, judging),
  method, use, releases, privacy, and the docs under `/docs/`.
- **Build:** a static site built by `site/build.py` into `site/public/` and deployed from main. The docs are MkDocs
  (`mkdocs.yml`).

## Capabilities and Constraints

- **Every claim on the site is checked.** A checker re-verifies the reports' claims against the committed runs on
  every commit.
- **The install pin** names the newest released version.
- **Scripts load only from allowed sources** (`site/csp.py`).

## Evidence on Hand

- The six evals' committed runs, the judging re-measurement, and the figures built from them.
- The social cards: `site/assets/social.png` and `social-home.png`.

## Shared with the other apps

Copied word for word from the root PRODUCT.md, because a tool reading this app's record reads only this file. A change there is made here too.

### Positioning

The harness's method is its product. It freezes the data, puts a fingerprint on every run, tests every ranking for
significance and refuses a comparison that is unsound instead of computing it anyway. The six published evals are
worked examples of that method, not a benchmark.

### Capabilities and Constraints

These are the rules every surface keeps (`docs/uxs/index.md`):

- **The catalog is read-only.** Writing and running happen in the Workbench or the terminal. A decision a page
  suggests is shown as the command that makes it.
- **Command-line parity.** Every view and action in the UI also exists as an `evh` command. It asks the same adapter
  and computes with the same functions, so a number on a page is the number in the terminal.
- **No item text in static pages**, unless the repository already publishes it. Outputs, references and items
  otherwise reach a browser only through the local inspector server.
- **Say what a number is measured against.** Every row of arms names its reference or judge.
- **Refuse, do not guess.** A comparison that cannot be made is refused, or set aside with the reason.
- **Vocabulary is fixed** and not renamed without the owner: run, eval, comparison, reference set, validation/test,
  significant, contenders.

### Brand Commitments

- The name is "eval-harness", and the command is `evh`.
- The icon is `site/assets/icon.svg`, with its PNG sizes beside it.
- Analytics are cookieless and self-hosted (Umami); there are no cookies and no tracking across sites.
- The license is MIT.

### Product Principles

1. **Trust before speed.** A number is shown with what it was measured against and whether it is significant, or not
   at all.
2. **Refuse rather than mislead.** An unsound comparison is refused, with the reason and the way to make it sound.
3. **The terminal and the page agree.** Every surface has its command, and the same functions compute both.
4. **Plain words over jargon.** Plain words are used where they are true; the fixed vocabulary is kept.

### Accessibility & Inclusion

- **Standard:** WCAG 2.2 AA (owner, 2026-11-12).
- **Phone:** every screen works well at phone width (390 px), in light and dark themes. There is no sideways page
  scroll, and wide tables either stack or scroll inside their own box. The owner reviews from a phone.
