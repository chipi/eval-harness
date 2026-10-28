# Site sketches: the brief

The illustrations on the site, the catalog's companion pages and the docs share one hand. This
file is the brief every generation follows; change it here first, then regenerate.

## The identity

- **The mark.** The logo is a dot on a line between two square brackets: a measurement and its
  interval. Every sketch carries it somewhere, drawn by hand: brackets, a dot, the line.
- **The through-line.** Every sketch has one straight, horizontal, unbroken ink line at exactly
  half its height, running off both edges. Placed side by side, the sketches join into one axis.
- **The chart grammar, sketched.** A system is a dot on that line; the dearest model is a ringed
  dot; the systems the test cannot tell apart sit under one wash of green.
- **No words, no letters, no numbers** in an image. The page carries the words.

## The look

- Brush-pen and ink: confident, inky strokes with visible brush movement (thick to thin), a few
  loose construction strokes, light hatching for shadow.
- A watercolour touch: transparent washes with soft, uneven edges and a little granulation, the
  paper showing through.
- Paper: warm off-white (#f6f5f1), plain or with a very faint grid. Never a heavy or dark grid.
- Ink: near-black (#0b0b0b). The one colour: a fresh, lighter sap green (about #8db14b) laid as a
  wash. Darker greens read as flat blocks.
- Spare and quiet: generous empty paper, one idea per sketch. No ink splatter, no clip art.

## The pipeline

1. An SVG sketch in `site/art/sketches/` fixes the composition and what it means (the comment at
   its top says it in one sentence).
2. It is rendered to a 2048 px PNG and passed to Higgsfield as the reference image, with the style
   prompt below and the sketch's subject line.
3. The raw result is the master (`site/art/masters/`, committed), with its prompt, model and job
   id beside it. The site serves a desktop and a phone size built from it.

## The style prompt (v2)

> Reinterpret this schematic as a hand-drawn illustration from a researcher's notebook, in brush
> pen and ink with a light watercolour touch. Confident, inky brush strokes with visible movement,
> thick to thin, a few loose construction strokes and light hatching. Transparent watercolour
> washes with soft uneven edges and a little granulation. Warm off-white paper (#f6f5f1) with a
> very faint, barely visible square grid. Near-black ink (#0b0b0b) and exactly one colour: a fresh,
> light sap green (about #8db14b) used only as a watercolour wash [where]. KEEP the composition of
> the reference: one perfectly straight, horizontal, unbroken ink line at exactly half the image's
> height, from the left edge to the right edge; [the elements]. No words, no letters, no numbers
> anywhere. No ink splatter. Spare and quiet, generous empty paper. Not photorealistic, not a flat
> vector chart, not clip art. Subject: [one sentence].

## Locked after round 3 (2026-10-28)

- **One object per idea.** The idea becomes a thing you would recognise with no caption: the
  frozen dataset is a block of ice, the tie is a podium with everyone on the top step. Objects
  come back from sketch to sketch (the ice cube in 04 and 06), so the set reads as one story.
- **No grid.** Plain warm paper.
- **The style anchor** is round 2's ice cube (job `47e6c433-c167-4eb9-8aaa-3c5185f92182`): every
  generation passes the sketch first and the anchor second, "match the second exactly".
- **The masters** are `site/art/masters/01-frozen-dataset.png` (round 3, a) and
  `03-leaderboard-argues.png` (round 3, b), each with its prompt and job id in the `.json` beside it.
- **What the generator will not do**, after three rounds: put a dot exactly on the line, or always
  run the line to both edges. Do not depend on either; the page draws the joining line itself.
- **The model**: `nano_banana_pro` is requested; every job reported `nano_banana_2`. Both are
  recorded in each master's `.json`.

## What the pilot taught (2026-10-28)

- Kept: the brush and ink of 03-a and 03-b; the brush movement of 01-b; the watercolour surface of
  03-b.
- Changed: the grid of 01-b was too heavy (now very faint or none); the green was too dark (now a
  light sap green wash); 01 did not read as "frozen" (now an ice block); 03-a's line tilted and
  03-b put a dot beyond the leader (the prompt now pins the line, and the sketch has no dot right
  of the leader).
