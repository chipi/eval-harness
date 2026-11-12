---
name: eval-harness, the public site
description: Is the ranking real, or a lucky sample? The method and six worked evals, set like a lab notebook.
colors:
  ink-black: "#0b0b0a"
  surface: "#141413"
  surface-raised: "#1c1c1a"
  paper-ink: "#f0efec"
  ink-secondary: "#b9b7ad"
  muted: "#7d7b74"
  hairline: "#2a2a27"
  axis: "#3a3a36"
  highlighter-lime: "#c8ff3d"
  proprietary-blue: "#3987e5"
  local-ember: "#d95926"
  open-weights-green: "#199e70"
  baseline-grey: "#6f6d66"
  paper-light: "#f6f5f1"
  surface-light: "#fcfcfb"
  ink-light: "#0b0b0b"
  ink-secondary-light: "#4a4945"
  hairline-light: "#dddbd3"
  highlighter-olive-light: "#3d5c00"
typography:
  display:
    fontFamily: "Inter Tight, Inter, Helvetica Neue, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "clamp(48px, 9vw, 128px)"
    fontWeight: 800
    lineHeight: 0.92
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "Inter Tight, Inter, Helvetica Neue, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "clamp(36px, 5.6vw, 76px)"
    fontWeight: 800
    lineHeight: 0.98
    letterSpacing: "-0.035em"
  title:
    fontFamily: "Inter Tight, Inter, Helvetica Neue, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "22px"
    fontWeight: 800
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.6
  lede:
    fontFamily: "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
    fontSize: "clamp(18px, 1.8vw, 21px)"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "ui-monospace, SF Mono, JetBrains Mono, Menlo, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "0.14em"
  number:
    fontFamily: "ui-monospace, SF Mono, JetBrains Mono, Menlo, Consolas, monospace"
    fontSize: "clamp(34px, 4.6vw, 56px)"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "-0.03em"
rounded:
  small: "6px"
  panel: "12px"
  card: "14px"
  pill: "999px"
spacing:
  gutter-phone: "16px"
  gutter: "24px"
  grid-gap: "16px"
  section: "112px"
  container: "1180px"
components:
  button-primary:
    backgroundColor: "{colors.highlighter-lime}"
    textColor: "{colors.ink-black}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "14px 18px"
  button-secondary:
    textColor: "{colors.paper-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "14px 18px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
    padding: "26px"
  chart-frame:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
    padding: "22px 22px 14px"
  terminal:
    textColor: "{colors.paper-ink}"
    rounded: "{rounded.small}"
    padding: "18px 20px"
  icon-button:
    textColor: "{colors.ink-secondary}"
    size: "30px"
---

# Design System: eval-harness, the public site

## Overview

**Creative North Star: "The Lab Notebook"**

The site reads like a working scientist's notebook made public. Every page states a finding in the largest type it can
hold, then shows the measurement underneath: the number, what it was measured against, whether it is significant. The
one colour that is not ink is a highlighter, used the way a person marks the line they want read again, and it never
stands for data.

The voice is confident and plain. Headlines state findings ("Small models lead, largely on disputed labels."), text
underneath is quiet and grey, and nothing decorative appears unless it carries meaning: the faint grid behind the hero
is graph paper, the glow is the highlighter's bleed. It is dark-first, on near-black, with a warm-paper light theme
that keeps every role.

**Key Characteristics:**

- Very large, tightly set display headlines (800 weight, -0.035em), usually one clause turned in Highlighter Lime.
- Monospace for every label, kicker, eyebrow, navigation link and number; a humanist sans for reading.
- Flat surfaces separated by hairlines and a single tone step, never by shadow.
- Three categorical colours for the kinds of model, kept apart from the accent.
- No web fonts and no external requests: the type falls back to the system's sans and mono.

## Colors

Near-black ink and warm grey text, one highlighter, three data colours. The light theme keeps every role on warm paper.

### Primary

- **Highlighter Lime** (`highlighter-lime`): the marked line. A headline's turn ("a lucky sample?"), the current page's
  underline, a kicker's lead word, a note's left rule, the section number, the primary button. In the light theme it
  becomes **Highlighter Olive** (`highlighter-olive-light`), dark enough to read as text on paper.

### Secondary

- **Proprietary Blue** (`proprietary-blue`): an arm served by a proprietary model, in charts and legends only.
- **Local Ember** (`local-ember`): an arm that runs on local hardware, in charts and legends only.
- **Open-Weights Green** (`open-weights-green`): an arm with open weights served by a provider, in charts and legends
  only.
- **Baseline Grey** (`baseline-grey`): a plain baseline (a keyword rule, a first-k sentence pick) in charts.

### Neutral

- **Ink Black** (`ink-black`): the page in the dark theme, and the text on the lime button.
- **Surface** (`surface`) and **Surface Raised** (`surface-raised`): a card, a chart frame, a floating panel, one step
  above the page.
- **Paper Ink** (`paper-ink`): headlines and body text in the dark theme.
- **Ink Secondary** (`ink-secondary`): ledes, captions, navigation at rest.
- **Muted** (`muted`): eyebrows, table heads, figure captions, the footer.
- **Hairline** (`hairline`) and **Axis** (`axis`): every border and rule; a chart's axis.
- The light theme's counterparts: **Paper** (`paper-light`), **Surface** (`surface-light`), **Ink** (`ink-light`),
  **Ink Secondary** (`ink-secondary-light`), **Hairline** (`hairline-light`).

### Named Rules

**The Highlighter Rule.** The accent marks what to read; it never encodes a value. A chart never uses it for a series,
and a table never uses it for a number.

**The Three Kinds Rule.** Blue, ember and green always mean proprietary, local and open weights, wherever they appear,
and nothing else.

## Typography

**Display Font:** Inter Tight (with Inter, Helvetica Neue and the system sans)
**Body Font:** Inter (with the system sans)
**Label/Mono Font:** the system monospace (SF Mono, JetBrains Mono, Menlo, Consolas)

**Character:** a condensed, heavy grotesk that states findings at poster size, over a calm sans for reading and a
monospace that labels everything a person might copy, count or navigate.

### Hierarchy

- **Display** (800, clamp 48–128px, 0.92): the hero question on each page, at most 13 characters wide.
- **Headline** (800, clamp 36–76px, 0.98): a section's claim, at most 16 characters wide.
- **Title** (800, 22–30px): a card's eval name, a finding's heading.
- **Lede** (400, clamp 18–21px, 1.5): the paragraph under a headline, at most 62 characters wide, in Ink Secondary.
- **Body** (400, 17px, 1.6; 16px on a phone): running text.
- **Label** (500 monospace, 11–13px, 0.1–0.14em, uppercase): kickers, eyebrows, table heads, fact keys, navigation.
- **Number** (600 monospace, clamp 34–56px, tabular figures): a headline statistic.

### Named Rules

**The Mono Means Exact Rule.** Anything a reader might copy, count or click to navigate is set in monospace: commands,
ids, numbers, labels, links in the bar. Prose never is.

## Layout

A single 1180px column with 24px gutters (16px on a phone). Sections are generous: 112px above and below, each closed
by a hairline. Two-column layouts (a chapter's 300px aside beside its text; a lede beside a chart at 1.15 : 1) stack
to one column under 900px. Card grids fill columns of at least 320px (270px for patterns) with 16px gaps. Statistics sit
in a four-column ruled strip that becomes two columns under 760px. The bar is sticky, 56px tall, blurred over the page;
under 760px its links fold into a menu. Text never runs wider than 62–66 characters.

## Elevation & Depth

Flat by default. Surfaces are told apart by a 1px hairline and one tone step (page, then surface), and the hero's depth
is a faint graph-paper grid and a soft lime glow behind the headline. One shadow exists, for what floats over the page:
the menu and the search results.

### Shadow Vocabulary

- **Float** (`box-shadow: 0 8px 24px rgba(0, 0, 0, .18)`): the menu and the search results, nothing else.

### Named Rules

**The Flat-By-Default Rule.** A card, a chart and a table sit on the page with a hairline. A shadow means the element
floats above the page and will close.

## Shapes

Soft-cornered frames for content (14px on cards and chart frames, 12px on floating panels, 6px on a terminal block and
a tooltip), pills for buttons and the section switcher (999px), circles for icon buttons and legend dots. Rules are
1px hairlines; a note and a habit carry a 2–3px lime rule on their left edge.

## Components

### Buttons

- **Shape:** a pill (999px), monospace label, 14px by 18px.
- **Primary:** Highlighter Lime with Ink Black text; hover brightens it slightly.
- **Secondary:** transparent with a hairline border and ink text; hover turns the text lime.
- **Icon buttons:** 30–38px circles with a hairline border; hover turns the icon and border lime.

### Cards / Containers

- **Corner Style:** 14px.
- **Background:** Surface, on the page.
- **Shadow Strategy:** none (Flat-By-Default).
- **Border:** a 1px hairline.
- **Internal Padding:** 26px for an eval card, 22px for a chart frame.
- An eval card leads with a monospace task label, an 800-weight name, a sentence in Ink Secondary, and a ruled
  monospace meta row at the foot.

### Navigation

- The bar: brand mark and name in monospace, a pill switcher between the four parts (Harness, Catalog, Docs, MCP),
  page links in 13px monospace in Ink Secondary. The current page is ink with a 2px lime underline offset 6px; hover
  turns a link lime. An on-page row of section links sits under it. On a phone the links fold into a circular menu
  button whose panel floats with the one shadow.

### Notes and habits

- A note: a 2px lime rule on the left, 18px in, text in Ink Secondary at 15px. A habit (the method page): a 3px rule on
  a Surface panel, its label in lime monospace above the text.

### Charts

- A Surface frame with a hairline, the legend in monospace above, the caption in Muted below. Series use the three kinds'
  colours and Baseline Grey; a band of the accent at 9% shows a region, never a series.

### Terminal

- A command block in monospace at 13.5px, on a faint panel with a hairline and a 6px corner, scrolling sideways inside
  itself.

## Do's and Don'ts

### Do:

- **Do** state the finding in the headline and turn one clause of it in Highlighter Lime.
- **Do** set every label, number, command and id in monospace with tabular figures.
- **Do** separate surfaces with a 1px hairline and one tone step.
- **Do** keep blue, ember and green for proprietary, local and open-weights arms only.
- **Do** keep both themes complete: every colour is a token defined for dark and light.

### Don't:

- **Don't** use the lime accent for a data series, a value or a status.
- **Don't** add a shadow to a card, a chart or a table; only a floating panel has one.
- **Don't** load a web font or any other external resource.
- **Don't** add decoration that carries no meaning: the grid is graph paper, the glow is the highlighter.
