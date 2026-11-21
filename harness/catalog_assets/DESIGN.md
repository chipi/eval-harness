---
name: eval catalog and run inspector
description: Every goal, dataset, arm and model in a project's committed runs, kept in columns you can sort, filter and check.
colors:
  ink-black: "#0b0b0a"
  surface: "#141413"
  surface-raised: "#1c1c1a"
  paper-ink: "#f0efec"
  ink-secondary: "#b9b7ad"
  muted: "#8a8880"
  hairline: "#2a2a27"
  axis: "#3a3a36"
  highlighter-lime: "#c8ff3d"
  goals-violet: "#9085e9"
  data-blue: "#3987e5"
  arms-green: "#199e70"
  work-amber: "#c98500"
  series-ember: "#d95926"
  series-rose: "#d55181"
  series-leaf: "#008300"
  series-coral: "#e66767"
  gold-tier-bg: "#4a3a0c"
  gold-tier-ink: "#f3d77a"
  silver-tier-bg: "#3a3d42"
  silver-tier-ink: "#dde2e8"
  source-person: "#7fb3d5"
  source-model: "#b39ddb"
  source-rule: "#a5c9a0"
  paper-light: "#f6f5f1"
  surface-light: "#fcfcfb"
  ink-light: "#0b0b0b"
  muted-light: "#66645e"
  hairline-light: "#dddbd3"
  highlighter-olive-light: "#3d5c00"
typography:
  page-title:
    fontFamily: "Inter Tight, Inter, Helvetica Neue, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "clamp(34px, 5.5vw, 72px)"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.035em"
  item-title:
    fontFamily: "Inter Tight, Inter, Helvetica Neue, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "clamp(26px, 3.2vw, 38px)"
    fontWeight: 800
    lineHeight: 1.1
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.6
  table:
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "ui-monospace, SF Mono, JetBrains Mono, Menlo, Consolas, monospace"
    fontSize: "11px"
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "0.1em"
  tile-number:
    fontFamily: "Inter Tight, Inter, Helvetica Neue, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "22px"
    fontWeight: 600
    lineHeight: 1.2
rounded:
  tag: "4px"
  action: "8px"
  tile: "10px"
  card: "14px"
  pill: "999px"
spacing:
  gutter-phone: "16px"
  gutter: "24px"
  section: "112px"
  container: "1180px"
components:
  action-button:
    textColor: "{colors.paper-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.action}"
    padding: "9px 14px"
  chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.muted}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "7px 11px"
  chip-on:
    backgroundColor: "{colors.highlighter-lime}"
    textColor: "{colors.ink-black}"
    rounded: "{rounded.pill}"
    padding: "7px 11px"
  tile:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.tile}"
    padding: "12px 14px"
  tier-gold:
    backgroundColor: "{colors.gold-tier-bg}"
    textColor: "{colors.gold-tier-ink}"
    rounded: "{rounded.pill}"
    padding: "4px 9px"
  tier-silver:
    backgroundColor: "{colors.silver-tier-bg}"
    textColor: "{colors.silver-tier-ink}"
    rounded: "{rounded.pill}"
    padding: "4px 9px"
---

# Design System: eval catalog and run inspector

## Overview

**Creative North Star: "The Notebook's Ledger"**

The catalog is the site's lab notebook turned to its tables. The site states a finding; the catalog keeps every run
behind it, in columns a person can sort, filter and check, and the inspector reopens any comparison item by item. It
shares the site's foundation (near-black and warm paper, Highlighter Lime, a heavy grotesk over a calm sans,
monospace for everything exact) and spends it on reading rather than on occasion: titles are smaller, tables are the
main surface, and colour is wayfinding.

The voice is the same, confident and plain, at working density. A page opens with a short title and one sentence on
what it holds, then tiles and tables. Tables are comfortable to read: a row has room for a second line (a model's
provider, a rescore's change), and a long table shows ten rows at a time. Nothing on a page writes to the project: a
decision it suggests is the command that makes it.

**Key Characteristics:**

- The site's tokens, with muted text darkened to 4.5:1 on every surface and a visible lime focus ring.
- Four group colours as wayfinding: goals violet, data blue, arms green, work and spend amber.
- Sortable, filterable, paged tables as the main surface; on a phone each row becomes a card.
- Reference tiers as pills in their own colours (gold, silver), never in the accent or the group colours.
- Monospace for every id, number, label, chip and action.

## Colors

The site's palette for the page and the accent; four group colours for wayfinding; an eight-colour series palette for
charts; tier and source colours for references and labels.

### Primary

- **Highlighter Lime** (`highlighter-lime`): the current page, a section number, a selected chip, the focus ring, an
  action's tint and arrow. **Highlighter Olive** (`highlighter-olive-light`) in the light theme.

### Secondary

- **Goals Violet** (`goals-violet`), **Data Blue** (`data-blue`), **Arms Green** (`arms-green`), **Work Amber**
  (`work-amber`): which part of the catalog a tile, table or chart line belongs to, on a 3px top rule and the line's
  colour.
- **Series colours** (the four above with `series-ember`, `series-rose`, `series-leaf`, `series-coral`): the eight
  categorical slots charts assign to arms or datasets, each checked at 3:1 against the surface in the light theme.

### Tertiary

- **Gold tier** (`gold-tier-bg`, `gold-tier-ink`) and **Silver tier** (`silver-tier-bg`, `silver-tier-ink`): a
  reference set's tier, as a pill.
- **Source colours** (`source-person`, `source-model`, `source-rule`): who wrote a label set, as an outlined tag.

### Neutral

- The site's neutrals: **Ink Black** (`ink-black`), **Surface** (`surface`), **Surface Raised** (`surface-raised`),
  **Paper Ink** (`paper-ink`), **Ink Secondary** (`ink-secondary`), **Hairline** (`hairline`), **Axis** (`axis`).
- **Muted** (`muted`) is darker than the site's, so table heads and captions keep 4.5:1; **Muted** in the light theme
  is `muted-light`.

### Named Rules

**The Wayfinding Rule.** A group colour says which part of the catalog something belongs to, never whether it is good:
a trend is tinted in its group's colour whichever way it moves.

**The Three To One Rule.** A data or series colour is 3:1 or more against every surface of its theme (WCAG 1.4.11); the
light theme takes a darker step of the same hue where the dark one would fall under it (the fourth critique measured
the series amber at 1.9:1, rose 2.3, green 2.4, ember 2.8).

**The Tier Is Its Own Colour Rule.** Gold and silver belong to reference tiers only; a label set's source has a
neutral colour of its own, never a tier's.

**The Highlighter Rule.** As on the site: the accent marks what is current or selected, never a value.

## Typography

**Display Font:** Inter Tight (with Inter, Helvetica Neue and the system sans)
**Body Font:** Inter (with the system sans)
**Label/Mono Font:** the system monospace

**Character:** the site's pairing at working size: the heavy grotesk only for page and item titles, the sans for
reading, the monospace for every id, number and control.

### Hierarchy

- **Page title** (800, clamp 34–72px, 1.0): a list page's name ("Arms and systems").
- **Item title** (800, clamp 26–38px, 1.1): one goal's, dataset's or arm's page.
- **Body** (400, 17px, 1.6): a page's one sentence on what it holds.
- **Table** (400, 15px): table cells; ids in monospace, numbers with tabular figures.
- **Label** (500 monospace, 11–12px, 0.06–0.1em, uppercase): table heads, eyebrows, tile labels, fact keys.
- **Note** (400 sans, 12px, Muted): a cell's or a heading's second line (a derived arm's move, a group's count); never
  under 12px in the sans. A chart's words render at 11px or more at the size the chart is drawn.
- **Tile number** (600, up to 22px, scaled to the tile's width): a count on a home tile.

## Layout

The site's 1180px column and gutters (24px, 16px on a phone). A list page: eyebrow, title, one sentence, the period
switch, then numbered sections, each a filter bar and a table. Tables page ten rows at a time ("show 10 more", "show
all") and keep their filter and sort over every row. A goal or dataset page reads as a definition list (a 200px key
column beside its value) above its tables. At 640px or less a table of four or more columns becomes one card per row:
its first cell the title, every other cell after its column's name, and a "sort by" menu in place of the hidden
headers; the label sheet stays a sheet that scrolls across the arms.

## Elevation & Depth

Flat, as the site: hairlines and one tone step. The one floating element is the navigation's drop-down list, which has
the site's float shadow. A row the reader opened in the inspector is shown by a tone (Surface Raised), not a shadow.

### Shadow Vocabulary

- **Float** (`box-shadow: 0 8px 24px rgba(0, 0, 0, .18)`): the navigation's drop-down list only.

## Shapes

Smaller corners than the site's cards, for denser things: 10px tiles, 8px actions, 4px tags, full pills for chips and
tiers, 14px only where a site card appears. A group's 3px top rule on a tile; an inset rule on the first cell of a
tinted row (3px, 1px for a label set; see Tables).

## Components

### Tiles

- **Shape:** 10px corners, a 3px top rule in the group's colour, Surface background, hairline border.
- **Content:** a monospace label, a number scaled to the tile's width, a trend pill, a sparkline in the group's
  colour. Hover and focus turn the border the group's colour.

### Chips (filters and groupings)

- **Style:** pills on Surface, monospace, Muted text with a hairline border.
- **State:** pressed is Highlighter Lime with Ink Black text; hover turns the text ink and the border lime.

### Actions

- **Shape:** 8px corners, 9px by 14px, monospace 12px, sized to sit in a table row.
- **Colour:** the accent at 12% over Surface with a border at 38%; a link action ends in a lime arrow; hover deepens
  the tint to 24%.

### Tables

- Monospace uppercase heads in Muted, a hairline under each row, sortable heads that say their direction (an arrow in
  the accent), a filter above and a pager below. Row tints mark how an arm was scored, each a faint tint and a 3px
  inset rule on the first cell, keyed above the table: against silver in the silver tier's ink, by a judge in the
  model source's colour (a model scored it), by the arm that wrote its reference in the local series colour,
  against a label set in Muted with a 1px rule (told from silver by weight, not hue alone); gold is unmarked. None
  uses a model kind's data colour.
- A role badge is a pill, 2px by 7px inside: a result (leader, recommended) in bold ink on an Ink tint (14%), an arm
  left out drawn as an outline, a baseline plain on Surface Raised; never a group or status colour. "wrote its own
  reference" is an outline in the local series colour.
- An element marked hidden stays hidden whatever its display rule (`[hidden] { display: none !important }`).

### Reference tiers and label sources

- **Tier pill:** gold or silver, uppercase monospace, filled in the tier's colour with an inset ring.
- **Source tag:** person, model or rule, an outlined monospace tag in its own colour.

### Navigation

- The site's bar with the catalog's sections (Overview, Goals, Data, Arms, Activity, Inspector), two of them
  drop-downs, and a search field; on a phone the search is a button that opens a row under the bar.

## Do's and Don'ts

### Do:

- **Do** mark which part of the catalog something belongs to with its group colour, on a 3px rule or a chart line.
- **Do** keep muted text at 4.5:1 or more and the lime focus ring on everything that takes focus.
- **Do** show a suggested decision as the command that makes it.
- **Do** keep tables comfortable: room for a second line, ten rows a page, filter and sort over every row.

### Don't:

- **Don't** use a group colour, the accent or a tier colour to say a value is good or bad.
- **Don't** give a label set's source a tier's gold or silver.
- **Don't** add a shadow to a tile, a table or a card.
- **Don't** let a page write to the project.
