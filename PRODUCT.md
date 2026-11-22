# Product

<!-- impeccable:product-schema 1 -->

The eval-harness repository holds three apps, each with its own PRODUCT.md for what is particular to it:

- the public site, evals.humancopilot.eu (`site/PRODUCT.md`);
- the catalog and the run inspector (`harness/catalog_assets/PRODUCT.md`);
- the Workbench (`harness/workbench/PRODUCT.md`).

This file holds what the three share.

## Platform

web

## Users

People. Agents use the same harness through `evh`, the MCP server and the files, and are not the audience of these
apps.

The primary user is an engineer or a team lead choosing between AI systems on their own frozen data. They want to know
whether a ranking is real or a lucky sample, what each option costs, and what to deploy. They work on a laptop, and
they also read and review on a phone. The owner is the first such user.

## Product Purpose

A drop-in harness for evaluating AI systems on your own data. It asks the question most leaderboards skip: is this
ranking real, or a lucky sample?

A person freezes a dataset, runs their systems against it, and gets an answer that says whether one system is
actually better than another or only ahead on this sample, with cost and latency beside quality. Success is a choice
a person can defend: the comparison was sound, or it was refused with the reason.

## Positioning

The harness's method is its product. It freezes the data, puts a fingerprint on every run, tests every ranking for
significance and refuses a comparison that is unsound instead of computing it anyway. The six published evals are
worked examples of that method, not a benchmark.

## Operating Context

- **The loop:** a goal, a frozen dataset, arms (a model with its prompt and settings), a comparison, and a round that
  ends in a choice kept with its reason.
- **Production feedback:** datasets from production captures, labels from what happened later, and the code that ran
  replayed. Flotilla, the owner's fleet platform, is the main source of these use cases.
- **Interfaces:** every view and action has an `evh` command; the apps are a comfort over it.
- **Stores:** a project's data lives in files under `data/`, or in one SQLite database.

## Capabilities and Constraints

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

## Brand Commitments

- The name is "eval-harness", and the command is `evh`.
- The icon is `site/assets/icon.svg`, with its PNG sizes beside it.
- Analytics are cookieless and self-hosted (Umami); there are no cookies and no tracking across sites.
- The license is MIT.

## Evidence on Hand

- **The six published evals and their committed runs:** AG News, DBpedia, Few-NERD, SciFact, summarisation and
  SummEval.
- **The judging re-measurement**, also committed.
- **The method page, the docs, the PRDs and the UX specs** (`docs/prd/`, `docs/uxs/`).

No testimonials, customers or third-party adoption exist. Do not invent them.

## Product Principles

1. **Trust before speed.** A number is shown with what it was measured against and whether it is significant, or not
   at all.
2. **Refuse rather than mislead.** An unsound comparison is refused, with the reason and the way to make it sound.
3. **The terminal and the page agree.** Every surface has its command, and the same functions compute both.
4. **Plain words over jargon.** Plain words are used where they are true; the fixed vocabulary is kept.

## Accessibility & Inclusion

- **Standard:** WCAG 2.2 AA (owner, 2026-11-12).
- **Phone:** every screen works well at phone width (390 px), in light and dark themes. There is no sideways page
  scroll, and wide tables either stack or scroll inside their own box. The owner reviews from a phone.
