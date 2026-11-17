# The Workbench on the site: what changes, how to position and promote it (0.8.0)

Written 2026-11-18 for the owner's review (owner: "after you finish the docs, review the site and see how all of these
changes it, and think of what we need to evolve and how we promote and position this new UI"). Nothing here is built
or published: each item below waits for the owner's decision, and promotion waits for the release (owner, 2026-11-18:
no release now; review and testing first).

## Recommendation, in short

Keep the method as the product and present the Workbench as **the second way into the same method**: "the loop on
screens, every action showing the command it runs". It is not a no-code pitch. The site today says the harness lives
in the terminal and the catalog is where results are read; with 0.8.0 that is half the story, and the Workbench is
the half that lets the people who decide (a team lead, the domain expert who labels and reviews) take part without a
terminal, while the engineer's terminal and an agent's MCP calls run the same operations. Change four places on the
site (home, Use it, a Workbench section with real screenshots, the releases page) when 0.8.0 is released, and
promote it with two or three short posts in the owner's simpler style, each with one screenshot and one link.

## What the site says today, and what 0.8.0 changes

| place | what it says now | what is no longer the whole story |
| --- | --- | --- |
| Home, the intro | "Three parts: this site …; the catalog …, with an inspector …; and the docs" | a fourth part: the Workbench, where a project's evaluation is set up and run |
| Home, 03 "What the harness does" | six ideas, one adapter file; everything shown as commands | each idea now also has a screen (goal, dataset, systems, rounds, the held-out test) |
| Use it, the loop | each stage "lives in your terminal", with "In the guide" and "Ours, in the catalog" | each stage also lives on a screen of the Workbench; tutorial 8 walks them |
| Docs | the guide and tutorials 1 to 7 | tutorial 8, the Workbench (added in this build) |
| Releases | the CHANGELOG's sections | 0.8.0's section should open with the Workbench |
| site/PRODUCT.md | pages: home, evals, method, use, releases, privacy, docs | a Workbench section or page |

What does not change: the catalog stays read-only and public; the Workbench is local only (it is never served
publicly or behind a proxy: D8), so the site cannot link to a live one. Showing it means screenshots, a short
recording, or the reader running it (tutorial 8).

## Positioning

- **Who it is for.** The site's reader is an engineer or a team lead deciding whether to adopt the harness
  (site/PRODUCT.md). The Workbench widens who in their team uses it: the person who owns the decision opens a round,
  reads the evidence and closes it with a conclusion; the domain expert labels a sheet or reviews two arms blind; the
  engineer and the agent keep the terminal and MCP. One method, three ways in, the same numbers.
- **The line.** "Rigour without a terminal" overclaims (the setup still needs an adapter). Candidates:
  "The same method, on screens: every action shows the command it runs." or "Set up and run an evaluation on
  screens; nothing on them the terminal cannot do." The owner picks.
- **What to show, in order of strength.** (1) A round: its question, the arms, the evidence with the raw p and its
  threshold, an arm retired with why, the round closed with its conclusion and the leader promoted: the method made
  visible. (2) Prompts as versions: which text each run sent, in a manual eval and in a study. (3) The held-out test:
  sealed, read items left out, opened once for one candidate. (4) Unsent changes kept, jobs with a cap first.
- **What not to claim.** That it is hosted or multi-user (it is a local server with a token); that it replaces the
  terminal; any number not recomputed from committed runs (the site's rule).

## The site: what to evolve (each a decision)

1. **Home intro: four parts.** Add the Workbench to "Three parts", one sentence, linking tutorial 8.
2. **Use it: each stage on a screen.** Beside "lives in your terminal", name the Workbench screen for the stage
   (Dataset → step 2, Materialized → step 3, Arms → step 4, Tests → the eval, Re-measure → the reference set and
   the judge, Next round → the eval). One line each.
3. **A Workbench section with real screenshots.** On the home or its own page: four or five screenshots of the
   live Workbench on the tutorial project, desktop and phone, made by a script from the browser tests (as the
   figures are recomputed from the runs, so they stay current with the code). The frozen mockup is not used: its
   data and wording predate RFC-032.
4. **Releases: 0.8.0 opens with the Workbench**, in the paragraph RELEASING step 2 asks for.
5. **A short recording (optional).** 60 to 90 seconds, one goal from a question to a decision. The site's CSP
   (`site/csp.py`) and hosting decide whether it can be embedded or only linked; not checked yet.
6. **Later, a product idea, not 0.8.0:** on a local catalog (the same server), an "open in the Workbench" link on a
   goal's page.

## Promotion (after the release)

- **Posts, in the owner's simpler style** (fewer specifics, no jargon), each one screenshot and one link to a site
  section, body links to the site, Medium links in the first comment as before:
  1. "The method, on screens" (the round: a question, the evidence, a decision kept with its reason).
  2. "A prompt is a version" (which text each run sent; a person's edits and an agent's proposals alike).
  3. "Look at the test set once" (the held-out test, sealed, opened for one candidate).
- **The existing series** (`/work/eval-harness/linkedin-posts.md`): post 8 "An agent reads, a person decides" pairs
  naturally with the Workbench: the person deciding is on its screens.
- **A Medium piece, optional:** "From terminal to screens without losing the method", once the posts have run.

## Before any of this: the owner's review and test

The owner reviews and tests the Workbench first (2026-11-18). To try it: in a project (`evh init --store files
--tutorial`, then getting started), `evh catalog`, `evh catalog-serve`, open the Workbench link it prints; tutorial 8
walks every screen. Feedback then decides the site's screenshots and wording.

## Decisions for the owner

1. The line (one of the candidates above, or another).
2. Who the Workbench is pitched to: the whole team (recommended) or engineers only.
3. Screenshots only, or screenshots and a recording.
4. A Workbench section on the home, or a page of its own.
5. Whether the promotion posts join the existing series or start a 0.8.0 series.
