# Product: the Workbench

<!-- impeccable:product-schema 1 -->

The shared product record is the repository's root PRODUCT.md. This file holds what is particular to the Workbench
(PRD-017, UXS-005).

## Platform

web

## Users

An engineer or a team lead setting up and running an evaluation on their own data, without the terminal (owner,
2026-11-12). Agents already do all of this through `evh`; the Workbench exists because a person cannot do it so
easily.

## Product Purpose

The Workbench is where a person puts things in and runs them: a goal and its data, models, arms, labels, references,
scoring, and the round that ends in a choice. Success is a person who completes each workflow without the terminal, in
either store, with the harness's complexity feeling the way the site explains it: a goal, data, arms, a comparison, a
choice.

## Operating Context

- **Workflows:** goal, dataset, prepare, models, eval (rounds), review and label, a judge, production (labels from
  what happened later, replaying the code that ran), the held-out test, a study, and jobs.
- **Organised around those workflows,** not around the files the harness keeps. The daily and weekly workflows are
  guided; occasional ones are plain.
- **Running is visible:** every run is a job, with its cost before it starts, its progress while it runs, and its
  result after. A job survives the browser closing.
- **Where it runs:** on the person's machine, not as a public multi-user service.

## Capabilities and Constraints

- **State:** a static mockup (round 5), read from this repository's real data and from throwaway projects. Nothing is
  saved. The PRD is a draft for 0.8.0.
- **Forms** ask only what a person decides at that point. Links to other things are pickers, and what commands write
  is shown, never edited.
- **The catalog and inspector stay read-only;** the Workbench links to them for results.
- **Mock data must be real:** every value shown is the harness's own answer, and what is pretended is labelled.

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
