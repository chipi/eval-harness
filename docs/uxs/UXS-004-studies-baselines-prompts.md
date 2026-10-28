# UXS-004: Studies, baselines and prompts

- **Status**: Draft (0.5.0), revision 3 (2026-10-27): no baselines pages (the goal page shows each baseline); one
  kind of study, evidence from a confirmation; consent only by the person's own command. Revision 2: studies on one dev
  dataset with grid, command and agent samplers; baseline versions written once; prompt versions by content, without
  aliases
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-009](../prd/PRD-009-prompts-and-optimisation.md) (prompts, studies),
  [PRD-011](../prd/PRD-011-evidence-registry.md) (baselines, evidence), [PRD-013](../prd/PRD-013-identity-and-ties.md)
  (looks, non-inferiority)
- **Related RFCs**: [RFC-009](../rfc/RFC-009-prompt-versions.md), [RFC-010](../rfc/RFC-010-studies.md),
  [RFC-012](../rfc/RFC-012-evidence-registry.md), [RFC-014](../rfc/RFC-014-identity-baselines-migration.md),
  [RFC-015](../rfc/RFC-015-noninferiority-looks-power.md)
- **Related UX specs**: [UXS-001](UXS-001-catalog.md) (the shell, tokens, tints, tables, the goal page),
  [UXS-002](UXS-002-inspector.md), [UXS-003](UXS-003-cli-and-onboarding.md) (the commands),
  [UXS-005](UXS-005-agents.md) (the same surfaces for agents)
- **Implementation paths**: `harness/scripts/catalog_build.py` (new pages), `catalog_views.py`,
  `view_baselines.py`, `view_studies.py`, `view_prompts.py`, `harness/catalog_assets/catalog.css`

## Summary

0.5.0 adds two kinds of page to the catalog, a **study** (an optimisation loop and what it found) and a **prompt**
(the versions of a prompt file and where each was used), and a section to the goal page: each **baseline** (what the
goal runs on a dataset now, the evidence for each change, and its history). Each is also a command. They use
UXS-001's shell, tokens, tables and row tints unchanged.

## Principles

- **Research is not evidence, and the page says which is which.** A study's trials are shown as research
  (nominal numbers on dev items); only a confirmation is evidence, shown apart
  and labelled with its look.
- **Every verdict says what it spent.** "look 2 of cnn_dailymail_200, at 0.38%", or "nominal: not
  tested on held-out items". A number from a page that is not a look says so.
- **The person decides.** A page that suggests a promotion shows the command; it never promotes, and a
  study never does.
- **Who acted is visible.** Every promotion, trial and version shows its actor ("agent:claude for
  person:marko", "person:marko", "unknown:marko") and, when one was given, the instruction.

## Scope

**In scope:** a baseline as the goal page shows it; the studies page and a study's page; the prompts page and a
prompt's page; the header's new links.

**Non-goals:** job progress (live state under `.evh/`, not committed: `evh jobs-status`, UXS-003); any
control that writes; showing prompt text on public pages unless the project publishes it (below).

## The header

The nav keeps 0.4.2's groups and gains **Studies** and **Prompts** under Experiments: Overview, Goals,
Data ▾ (Datasets, References), Experiments ▾ (Arms, Configs, Studies, Prompts, Metrics), Activity, Inspector. On a
phone the ☰ menu lists every page, a group's under its name ([UXS-001](UXS-001-catalog.md#the-shell-every-page)).
Search indexes studies (by id, goal and hypothesis) and prompt names; a baseline is found through its goal.

Both pages are listing pages: they carry the period ([UXS-001](UXS-001-catalog.md#the-period-every-listing-page)),
from their own builders (`period_studies`, `period_prompts`), which their commands read too.

## Words and marks

These words and chips are the same on every page, in the inspector and in the commands.

| verdict | chip | meaning |
| --- | --- | --- |
| separated: better | ▲ `separated: better`, border `--open` | better than the reference arm, the test rejected (0.4.0's chip) |
| non-inferior | ≈ `non-inferior`, border `--open` | not worse than the reference arm by more than the goal's margin |
| non-inferior (worse, within margin) | ≈ `non-inferior · worse within margin`, border `--open`, `--local` text | separated as worse, but within the margin |
| separated: worse | ▼ `separated: worse`, border `--local` | separated as worse (0.4.0's chip) |
| inconclusive | plain `inconclusive`, with its reason after it ("too few items", "skewed, too few items", "no variation") | the test did not decide |

| look label | when |
| --- | --- |
| `look k · <dataset> · at 0.38%` | a decision recorded on a heldout dataset (the level is the look's) |
| `nominal · not a look` | a comparison shown by a page or a read command on heldout items |
| `nominal · not tested on held-out items` | a comparison on a dev dataset |
| `research · dev` | a study's trial against its best so far |

| actor | shown as |
| --- | --- |
| a person | `person:marko` |
| an agent acting for a person | `agent:claude for person:marko` |
| unnamed, not at a terminal | `unknown:marko`, muted, with the title "not named: an agent or a script" |

A consent is shown beside the actor: "confirmed by person:marko".

## A baseline, on the goal page

There is no separate baselines page: a baseline belongs to a goal on a dataset, and the goal page is where it is read
([UXS-001](UXS-001-catalog.md#050-changes-draft)). Per dataset of the goal, the page shows:

- **now**: an answer box: "version 3, promoted <date> by <actor> · scored against <tier>", the arm in bold, the
  reason, **inspect it** and **against version 2** buttons (the inspector, with version 2's run as baseline);
  "No baseline yet" and the command otherwise.
- **the evidence**: the frozen comparison, never recomputed: "against version 2 on rouge_l", the verdict chip, Δ with
  its interval, p and the level, the look label, the items (n, and "of 200" when fewer were shared); the axes side by
  side ("cost per item $0.0011 against $0.0024; speed p50 1,830 ms against 2,410 ms"); the round or study it came
  from, linked; for a study's winner, its confirmation; "first baseline: nothing to compare", "promoted in 0.4.0:
  evidence not recorded" or "not comparable: the reference differs" when that is the case. A muted line: "Frozen
  when promoted on <date> with harness 0.5.0. `evh pair-test` recomputes it today; that is a new comparison, not this
  evidence."
- **how to reproduce it**, folded: config id and params (credentials never shown, as on the arm page), prompts (each
  name, version and hash, linked to the prompt's page), the system (model, declared code ref, accelerator), the
  adapter, the harness, the dataset with its items digest, the reference with its digest, the stages.
- **history**, folded: every version, newest first: **version**, **when**, **by**, **why**, **replaced**, and marks:
  "rollback of version 2: <reason>", and "fork: promoted on two branches" when two versions replaced the same one
  (RFC-017). Version numbers are display numbers, in order of promotion.
- Command: `evh baselines --goal G --dataset D [--all-versions]`; `evh baselines --json` is what a production system
  reads (no page: it is a document).

## The goal page, with studies

UXS-001's goal page changes as [UXS-001](UXS-001-catalog.md#050-changes-draft) lists: each dataset shows its baseline
(above), each heldout dataset shows its looks, and the rounds table shows a study's round with a `study` tag linking to
the study's page.

## The studies page

- Hero: kicker `studies`, "Optimisation loops: what each tried and what it found. A kept trial is
  research; only a confirmation is evidence."
- `01 studies`: **study** (linked), **goal**, **sampler**
  ("agent:claude", "grid", "command: optuna_sampler.py", "imported"),
  **trials** ("12: 3 kept, 8 dropped, 1 failed"), **status** (running, waiting for consent, stopped:
  <reason>, closed), **outcome** (its confirmation's chip and look label; "research: no evidence" when there
  is none; "imported: cannot be confirmed"), **started**, **by**, and in the period **trials in period** and
  **spend in period**, with their trends. Filterable, paged.
- The period bar in the hero, and over the table the **all / new in period / active in period** chips. A study is
  new on the day of its `start` event, active on any day with a trial.
- Command: `evh studies [--goal G] [--period P]`.

## A study's page

1. **Hero:** kicker `study`, the study id, its goal (linked), the sampler, and its status;
   "started <date> by <actor>", and the instruction when given ("Make the summaries shorter without
   losing facts").
2. `01 the outcome`, the answer first:
   - **confirmed:** a box per confirmation (`evh study-confirm`): the rule, the verdict chip, "trial 7 against the baseline
     on 180 heldout items (20 excluded: 12 in the dev set, 8 shown to the sampler)", Δ with its interval, p,
     the look label, and beside it "on dev the same trial was +0.034": the drop from dev to
     heldout is the optimizer's curse, and the line names it. When the outcome meets the declared rule:
     "Suggested: promote trial 7's run", with the command in a code chip and a **copy** button
     ([UXS-001](UXS-001-catalog.md#the-goal-page)'s chip). Otherwise the reason ("inconclusive: the rule
     was not met; the study does not suggest a promotion").
   - **a confirmation refused:** "No confirmation without possible evidence: the smallest p these 10 items
     can reach is 0.001, the look's level is 0.0004" and, when the person overrode it, "run anyway at
     <actor>'s consent; its outcome is labelled inconclusive".
   - **not confirmed:** "Research: no evidence. Best trial 7 on dev: +0.034." and the command that would
     confirm it (`evh study-confirm … --heldout <dataset> --rule …`), in a code chip.
   - **imported:** "Imported from <file> on <date>: a record of a past loop; its trials cannot be confirmed."
3. `02 trials`: a chart, then the table.
   - **The chart**: the decisive score of each trial (one dot, `--muted` when dropped, `--accent` when
     kept, a cross when failed) against its number, and the best so far as a step line. Hovering a dot
     shows the trial's change and hypothesis. Below 700px, a list instead.
   - **The table**, one row per trial, newest first: **k**, **change** (parameters as `num_beams 2 → 3`;
     prompts as `summary/user v3 → v4`, linked to the diff on the prompt's page), **hypothesis**,
     **outcome** (`kept`, `dropped`, `failed`, `no effect`; the reason in the tooltip and the
     folded row), **Δ vs best so far** (with `research · dev`), **limits**
     ("ok", or the limit that failed and by how much, against the baseline), **cost** (system, judge),
     **runs** (links to the trial's arms). A row unfolds to the trial's rationale, its config (the baseline's
     with the trial's changes), and what was shown to the sampler and where. Paged.
4. `03 money and stop`: spent against the dollar cap (system and judges, each shown); GPU hours; wall time;
   the stop rule that fired ("patience: 3 trials without a kept one"; "budget: system $5.00 reached";
   "stopped by person:marko"). A study waiting for consent shows the question it is waiting on and
   "answer with `evh study-run --resume <id> --confirm`" (the exact command).
5. `04 the spec`: the spec as it was when the study started, with its hash; the dev dataset; the acceptance rule ("point: +0.5% relative", or "test"); the
   limits; the test rule; the stop rules; the frozen files with their hashes;
   the space of changes as groups in order, each with its reason and move-on rule.
6. `05 items shown`: per trial, how many items were shown to the sampler and from which dataset, and the items
   now excluded from confirmations on the goal.
7. Commands: `evh study-status <study> [--trials] [--json]` (the same sections in order), `evh studies`.

## The prompts page

- Hero: kicker `prompts`, "The prompt files the arms declare, each version a snapshot of its bytes. The
  prompts stay where the project keeps them; these are their versions."
- `01 prompts`: **prompt** (the name, linked), **versions**, **used by the baseline** (`v3`, for each goal whose baseline uses it), **latest**
  (version, date, by), **used by** (runs, and the best score on each goal that decides on one), and in the period
  **versions in period** and **runs in period**, with their trends. Filterable.
- The period bar in the hero and the **all / new in period / active in period** chips. A prompt is new on its first
  version's `created_at`, active on any day with a version or a run that used it.
- Command: `evh prompts [--period P]`.

## A prompt's page

- Hero: kicker `prompt`, the name, where it lives (the declared path), and the baselines that use one of its versions.
- `01 versions`: one row per version, newest first: **version**, **created** (date, actor), **source**
  (the path and commit it was recorded from, linked through `evh catalog --repo` when given, else named; or the study
  and trial that proposed it), **parent** (when
  someone stated one; empty otherwise, not guessed), **note**, **size**, **sha256** (short), **used by**
  (runs, linked, each with its score on the goal's measure). Paged.
- `02 changes`: the diff between each version and its parent (or the previous version, labelled
  "previous, not a stated parent"), unified, with added and removed lines in `--open` and `--local`
  tints. **Only when the deployment publishes prompts** (`evh catalog --publish prompts`, as
  `catalog-serve --publish outputs,references` publishes text through the API): prompts can be private, and the
  static pages may be published. Otherwise the section reads "Prompt text is not published; see the diff with
  `evh prompt-diff <a> <b>`."
- Command: `evh prompts <name>`, `evh prompt-diff <a> <b>`.

## Key states

- **Empty:** "No studies yet: write a spec (`data/studies/<goal>/<id>.yaml`) and `evh study-run <spec>
  --dry-run`." / "No prompts declared: add `prompts:` to a config." / baselines as above.
- **Running:** a study's page built while it runs shows the trials so far and "running: <n> trials, as of
  <time>"; the catalog is static, so it says to rebuild for more, or to follow `evh study-status`.
- **Not comparable:** a baseline version whose evidence is `verdict: null` shows "not comparable:
  <fields>" instead of a chip.

## Checklist for a change to these pages

- Every verdict carries its look label; every actor its type.
- A page that suggests a decision shows the command, never a control that makes it.
- The same view is a command with the same numbers (`evh baselines`, `studies`, `study-status`,
  `prompts`), or the command gains it in the same change.
- Prompt text appears only when the deployment publishes it.
- A page's period numbers come from its builder (`period_*`), never computed twice; a table that shows the period
  keeps the new badge, the row chips and the trends' form (UXS-001).
- Colours come from classes in `catalog.css`, never a `style` attribute: the deployment's content security policy
  forbids them (`style-src 'self'`, since 0.4.1).
- No page needs a new inspector API route; the inspector answers only `/api/health`, `/api/compare` and
  `/api/item` (0.4.3).
