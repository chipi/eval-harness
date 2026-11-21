# Product: the catalog and the run inspector

<!-- impeccable:product-schema 1 -->

The shared product record is the repository's root PRODUCT.md. This file holds what is particular to the catalog
(`evh catalog`, `evh catalog-serve`) and the run inspector.

## Platform

web

## Users

An engineer or a team lead reading their own project's results: what each goal decided, which arm leads, whether the
lead is significant, and what each output says (owner, 2026-11-12).

## Product Purpose

The catalog shows what a project has and what it decided. The inspector opens per-item scores and outputs for the arms
a person picked. Success is a person who can read a ranking, see why it is or is not real, and find the item that
explains it.

## Operating Context

- **Catalog pages:** home, goals, datasets, arms and systems, models, metrics, references, labels, captures, activity,
  and a page per goal, dataset, arm and metric.
- **Inspector:** the paired comparison with verdicts, per item; the label sheet; outputs side by side.
- **How it runs:** a static build from a project's data. Item text appears only through the local server
  (`catalog-serve`).
- **Specs:** UXS-001 (catalog) and UXS-002 (inspector).

## Capabilities and Constraints

- **Read-only:** a page suggests a decision as the command that makes it.
- **Row tints** mark the arms not scored against gold (UXS-001).
- **Tables sort, filter and page.** On a phone a wide table stacks into one card per row, with a "sort by" menu. The
  label sheet stays a sheet that scrolls across the arms.

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
