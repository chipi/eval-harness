---
name: evh workbench
description: Where a person sets up and runs an evaluation, one guided step at a time, every run's cost shown before it starts.
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
  status-ok: "#199e70"
  status-warn: "#d9a326"
  status-bad: "#e0533d"
  paper-light: "#f6f5f1"
  surface-light: "#fcfcfb"
  ink-light: "#0b0b0b"
  muted-light: "#66645e"
  hairline-light: "#dddbd3"
  highlighter-olive-light: "#3d5c00"
  status-ok-light: "#0f7550"
  status-warn-light: "#9a6b00"
  status-bad-light: "#b23a26"
  gold-tier-bg: "#4a3a0c"
  gold-tier-ink: "#f3d77a"
  gold-tier-bg-light: "#f6e3a1"
  gold-tier-ink-light: "#5c4300"
typography:
  screen-title:
    fontFamily: "Inter Tight, Inter, Helvetica Neue, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "30px"
    fontWeight: 650
    lineHeight: 1.15
    letterSpacing: "-0.01em"
  part-title:
    fontFamily: "Inter Tight, Inter, Helvetica Neue, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
  lead:
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.55
  hint:
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "ui-monospace, SF Mono, JetBrains Mono, Menlo, Consolas, monospace"
    fontSize: "11px"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0.14em"
rounded:
  tag: "3px"
  control: "6px"
  block: "8px"
  pill: "999px"
spacing:
  screen-pad: "32px"
  part-pad: "18px"
  field-gap: "22px"
  screen: "760px"
  screen-wide: "1000px"
  rail: "220px"
  help: "340px"
components:
  button-primary:
    backgroundColor: "{colors.highlighter-lime}"
    textColor: "{colors.ink-black}"
    rounded: "{rounded.control}"
    padding: "9px 16px"
  button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.paper-ink}"
    rounded: "{rounded.control}"
    padding: "9px 16px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.paper-ink}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
  part:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.block}"
    padding: "18px"
  step-done:
    backgroundColor: "{colors.highlighter-lime}"
    textColor: "{colors.ink-black}"
    size: "22px"
---

# Design System: evh workbench

## Overview

**Creative North Star: "The Lab Bench"**

The Workbench is where the notebook's experiments are set up and run. It is a working tool, not a page to read: one
guided step at a time, every instrument labelled, every run's cost shown before it starts, and the command each step
writes kept at the foot of the screen. It shares the site's and the catalog's foundation (the same tokens, Highlighter
Lime, the heavy grotesk, monospace for everything exact) at an app's scale: titles are 30px, text is 15px, corners are
small, and the screen is organised around a journey rail on the left and a help panel that opens on the right.

The voice stays confident and plain, and it explains. Each field has a one-line hint under it and a "?" that opens more;
the rare settings and the command are folded away; hints can be turned off. Lime marks what is done or current and the
one action a screen asks for; three status colours say how a check came out.

**Key Characteristics:**

- A journey rail: each step a dot, filled lime when done, a lime ring when current.
- Lettered parts on a screen, each a hairline block with its own title, "?" and status.
- Forms on a label column (180px) beside the field, with a hint under each.
- Status colours (ok, warn, bad) kept apart from the accent and from the catalog's data colours.
- The command a screen runs, folded at its foot; every view also an `evh` command.

## Colors

The site's palette for the page and the accent, and three status colours.

### Primary

- **Highlighter Lime** (`highlighter-lime`): a done step's dot, the current step's ring, the one primary action on a
  screen, the focus ring, a selected card's border. **Highlighter Olive** (`highlighter-olive-light`) in the light
  theme.

### Secondary

- **Status OK** (`status-ok`): a check that holds (faithful, caught, set), a step's recorded value.
- **Status Warn** (`status-warn`): something to read before trusting (a survivor, a part needing attention).
- **Status Bad** (`status-bad`): a check that failed (significantly worse, refused).
- Each has a darker light-theme step (`status-ok-light`, `status-warn-light`, `status-bad-light`). The ok step is
  4.9:1 or more on every light surface, a selected row's included (the eval screen's third critique measured the
  earlier `#12805a` at 4.2:1 there).

### Neutral

- The site's neutrals: **Ink Black** (`ink-black`), **Surface** (`surface`), **Surface Raised** (`surface-raised`),
  **Paper Ink** (`paper-ink`), **Ink Secondary** (`ink-secondary`), **Muted** (`muted`), **Hairline** (`hairline`),
  **Axis** (`axis`), with their light-theme counterparts.
- **Muted** is the catalog's, not the site's: 4.81:1 or more on every surface in dark, 5.09:1 or more in light (the
  eval screen's critique found the site's step at 3.8–4.4:1).

### Named Rules

**The Done Is Lime Rule.** Lime says a step is done or current, or names the one action to take; a check's result is
always a status colour.

**The Status Is Not Data Rule.** Green, amber and red say how a check came out, never what kind of model an arm is
(the catalog's colours do that). A comparison's leader and an arm the goal recommends are results: the ok status, not
lime.

**The Gold Tier Rule.** A baseline's or reference's gold is the catalog's gold tier (`gold-tier-bg`, `gold-tier-ink`),
never a colour of its own.

**The Two Rules Rule.** Two blocks carry a left rule, and only these: the answer so far, 3px in lime (what to read),
and a note, 2px in Axis (an aside). No other card, row or callout has one. The answer's focus ring is Ink
Secondary, so it is not read as a second lime rule.

## Typography

**Display Font:** Inter Tight (with Inter, Helvetica Neue and the system sans)
**Body Font:** Inter (with the system sans)
**Label/Mono Font:** the system monospace

**Character:** the shared pairing at a tool's size: the grotesk only for screen and part titles, set lighter (650) than
the site's, the sans for fields and hints, monospace for kickers, ids, commands and status.

### Hierarchy

- **Screen title** (650, 30px, 1.15): a screen's task ("Set the goal").
- **Part title** (600, 18px): a lettered part; 15px for a row in a list of steps.
- **Lead** (400, 16px, Ink Secondary): one or two sentences under the title, at most 62 characters wide.
- **Body** (400, 15px, 1.55): fields and values.
- **Hint** (400, 13px, Muted): the line under a field; hidden when hints are off.
- **Label** (500 monospace, 11–12px, uppercase): kickers ("Step 1 of 5"), the rail's headings, status, commands.
- **Control** (sans, 14px): buttons, the rail's steps, a fold's summary, the help panel's definitions.
- **Caption** (sans, 12px, Muted): a chart's caption and legend, a refusal's text, fine print under a table, a
  verdict's Δ and p line.
- **Question** (600 display, 20px): a round's question, read as the round's title.
- **Stat** (600, 17px): a figure in an arm's panel.
- **Start title** (display, 38px): the empty project's one question, the only screen without the journey.
- A chart's words render at 11px or more at the size it is drawn: 12.5 units on a desktop (drawn at ~0.885), 20 on
  a phone (drawn at ~0.56).
- **Round answer** (sans, 16px, its lead in bold): the one line that answers a round's question, above its table.

## Layout

A three-column app shell: the journey rail (220px) on the left, the screen in the middle, the help panel (340px) on the
right when a "?" is open. A screen is at most 760px wide (1000px for wide screens such as a comparison), padded 32px
and up to 48px at the sides. Under 900px the rail becomes a row of steps above the screen and the help panel a sheet
from the bottom. A form is a 180px label column beside its field, one column under 640px. Parts are stacked 14px
apart; a screen ends with its actions and the folded command. On a phone, tables of four or more columns become one card
per row.

## Elevation & Depth

Flat. Blocks are told apart by a hairline and the Surface tone; a selected card gets an inset lime ring, not a lift. The
help panel is a bordered side panel, not a floating one. The mockup's own strip sits on the accent's band, outside the
app.

### Named Rules

**The No-Lift Rule.** Selection is a lime ring and hover is a darker border; nothing rises.

## Shapes

Small, even corners for a tool: 6px on buttons, inputs and the folded command, 8px on parts, cards and lists of steps,
3px on tags and the brand's mark, full circles for the rail's dots and the "?" buttons, full pills for review chips and a job's progress track.
A table inside a part keeps its own hairline frame (6px): the part is the step, the frame the data; nothing else
nests a framed block in a part.

## Components

### Buttons

- **Shape:** 6px corners, 9px by 16px, sans at 14px, weight 550.
- **Primary:** Highlighter Lime with Ink Black text, one per screen; disabled at 45% opacity.
- **Secondary:** Surface with a hairline border; hover darkens the border.

### Inputs / Fields

- **Style:** Surface, hairline border, 6px corners, 8px by 10px.
- **Focus:** the border turns lime.
- **Field:** a bold label with its "?" in the left column, the field and its hint on the right.

### The journey rail

- Each step a row with a 22px dot: Axis ring when not started, lime ring with a lime number when current, lime fill
  with Ink Black check when done; the current row on Surface Raised.

### Parts

- A Surface block with a hairline and 8px corners: a monospace letter, the part's title, its "?", its status at the
  right, a hint, then the body.

### Help panel

- A bordered panel at the right (a bottom sheet on a phone): the term as its title, a definition list of what it is,
  why, and an example, with monospace keys.

### The folded command

- At a screen's foot, a monospace "the command this runs" that opens a Surface block of the `evh` lines.

### Tags and status

- Tags: 3px corners, monospace, on Surface Raised; a new value on the accent's band; an onboarding result tinted in
  its status colour. Status text in monospace in its status colour.

## Do's and Don'ts

### Do:

- **Do** give each screen one primary action, in lime.
- **Do** put a one-line hint under each field and the rest behind its "?".
- **Do** show a run's cost before it starts and the command each step writes.
- **Do** keep status colours for a check's result and lime for done, current and the next action.

### Don't:

- **Don't** use a status colour for a model's kind, or lime for a check's result.
- **Don't** lift a selected card or block with a shadow; use the lime ring.
- **Don't** put every key of a file in a form: ask only what a person decides at that step.
- **Don't** show a value the harness did not compute; a mockup's pretended value is labelled.
