# ADR-0018 — The catalog's period is counted from today, in the browser (0.4.2)

**Status:** Accepted (2026-10-27), as built.
**Date:** 2026-10-27
**Detail:** [PRD-004](../prd/PRD-004-catalog-and-inspector.md) (FR1.8 to FR1.12),
[UXS-001](../uxs/UXS-001-catalog.md#the-period-every-listing-page) (the period on every page),
[UXS-003](../uxs/UXS-003-cli-and-onboarding.md) (`--period` on every list)

## Context

The catalog is static: `evh catalog` builds it once and a deployment serves the files until the
next build. Until 0.4.1 its one period, "last 14 days", counted back from the newest run, so a
quiet project still showed its last burst of work. The owner asked for calendar periods (this
week, last month, this year) and for the count on every home tile to carry a trend and to open
a page that shows the rows behind it, for the same period. A calendar period fixed at build time
goes stale: a catalog built on Friday would still call Friday "today" on Monday. (The number
this decision carries, ADR-0018, follows the 0.7.0 drafts on the `070` branch.)

## Decision

- **From today, in the browser.** Each page carries its rows' dated facts, per day (runs as
  `[day, arm]`, spend as `[day, usd]`, tokens, events, the day a row is new: `home.js`,
  `<page>-rows.js`), and `period.js` works the period out from the viewer's date. No count for
  a period is fixed in the build.
- **One builder per page.** `catalog_build.period_datasets`, `period_goals`,
  `period_references`, `period_metrics`, `period_activity` and `catalog_arms.period_arms` give
  each page's rows; the page writes them, and the list commands (`evh datasets --period P`, `evh goals`, `evh arms`, ...) read the same ones and
  compute the period with `catalog_periods` (the same periods and trends). The browser check
  holds the two to the same bounds on 118 days and the same tile numbers.
- **The period travels in the link** (`#p30d`), never in storage: nothing is remembered between
  visits.
- **A trend compares with the same days of the period before**; all time has none.

## Consequences

- A week-old catalog is still right about this week; only the facts (the runs) are as old as
  the build.
- The pages carry per-day facts besides counts and means; still no item text (ADR-0002).
- Without a script a page shows all time.
- Two implementations of the period bounds (`catalog_periods.py`, `period.js`), held equal by a
  test, rather than one.
