# RFC-019: Datasets from production: import, label, split, references from outcomes

- **Status**: Draft for the owner's review (2026-10-29), aimed at 0.4.6 (the owner, 2026-10-29); scheduled
  harvests are out of scope by the owner's word ("for now, not scheduled harvests")
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-006](../prd/PRD-006-datasets-versions-fields.md) (versions, item fields),
  0.5.0's PRD-012 (agents), 0.5.0's PRD-013 (dev and heldout,
  looks)
- **Related RFCs**: [RFC-006](RFC-006-item-fields-and-url-items.md) (field sets, URL items),
  0.5.0's RFC-013 (declarations, consent), 0.5.0's RFC-016 (MCP
  tools), 0.5.0's RFC-017 (records; these three on branch `050`), [RFC-018](RFC-018-read-only-mcp-server.md) (the MCP server, 0.4.5) and 0.4.5's dataset
  profiles (`evh dataset-profile`)

## Abstract

A project improves its product by evaluating on what its product actually meets. This RFC lets a project build
datasets from its production records, over time: **import** records from a source into a **harvest** (a candidate
pool, never yet evidence), **scrub** what may not be kept, **select** items from it (filters, de-duplication, a
sample), **freeze** them as a new dataset version with lineage, **label** the dataset (where it came from, which
environment, what for) and its items (fields), **split** it into dev and heldout for a goal, and take **references
from outcomes** production already recorded (what a person decided, what a user rated). Sources are importers: one
generic format in the harness, the rest in the project or in `examples/`, so the core names no vendor. Agents do
the same through MCP tools and a skill; freezing a dataset made from production records is the person's decision.

## Problem Statement

- Today a dataset is frozen from a directory of files (`dataset-create --source-dir`) or from pinned URLs (RFC-006).
  Records that live in a tracing system, a log store or an issue tracker reach a dataset only by a script each project
  writes, with no record of the query that chose them, no scrubbing, no sampling rule, and no link back to the record.
- The owner's two cases (2026-10-28):
  1. **The homelab's own production data**: the podcast pipeline's model calls are traced in Langfuse (`podcast-prod`,
     `podcast-dev`; each trace one episode, each generation one pipeline stage), its errors in GlitchTip, its logs in
     VictoriaLogs (handbook `agent-access.md`, sections 5–8). A dataset of real episodes and stages, kept current, is
     what continuous improvement of that pipeline needs.
  2. **The agentic fleets**: the triage fleet records one Langfuse trace per decision (project `agents`) and keeps
     ledgers of what it decided and filed (`~/signal-fleet/results/*.tsv`, signal-fleet runbook); what happened next
     to each filed issue is on GitHub. A dataset of its decisions, with the outcome as the reference, is how a change
     to the fleet is measured instead of guessed. Triage is the only fleet working today; bug fixing and ops come later.
- Words: the owner wrote "test/dev/prod datasets". The harness already has **dev** and **heldout** as a dataset's
  role in a goal (vocabulary kept, 0.4.0). Here **environment** (`prod`, `staging`, `dev`: where the records came
  from) is a label, and dev/heldout stay the role. The RFC does not rename either.

## Design

### 1. Importers

- An importer is a class in the project (`importers/langfuse.py:Importer`, named in `config.yaml` or on the command
  line), with one method: `records(query) -> Iterator[Record]`. A `Record` is `{id, text | fields, created_at,
  source: {system, project, url}, labels, outcome}`: `id` is the record's own id in its system (a trace id, an issue
  number), `url` opens it there, `outcome` is what happened after (below, 6).
- **In the harness: one importer, `jsonl`** (one record per line, the fields above). Anything can be exported to it.
- **In `examples/importers/`**, maintained with this repository, not in the package: `langfuse` (traces and
  generations through `/api/public/traces`, filtered by project, environment, name, time; a generation's input as the
  item, its output and scores as fields), `github_issues` (issues and their timeline through the REST API, for the
  triage fleet), `victorialogs` (a LogsQL query). The core names no vendor (the owner's rule: the package offers hooks;
  specifics live outside it).
- `query` is the importer's own (a time window, a project, a filter); the harvest records it verbatim (2).

### 2. Harvests

- `evh dataset-harvest --importer langfuse --query '{...}' --harvest H` writes
  `data/harvests/<H>/harvest.json` (the importer, its code hash, the query, when, who, how many records, each record's
  id, source url and content sha256) and `data/harvests/<H>/records/<id>.json` (the records themselves).
- **The records are not committed.** Production records may hold personal or private data and may not be
  re-fetchable later (a source's retention), so `records/` is gitignored and kept where the project keeps private
  data (a path or a private store named in `config.yaml`). `harvest.json` is committed: it holds ids, hashes and urls,
  no text.
- A harvest is a candidate pool, never evidence: no run is scored against it and no page counts it.

### 3. Scrub

- Before anything is frozen, `evh harvest-scrub H --rules scrub.yaml` applies the project's rules to every record:
  regular expressions and field drops (`email`, `phone`, an API key's shape, named fields), each replaced by a typed
  placeholder (`<EMAIL>`). The rules file and its hash are recorded; the scrubbed copy is what is frozen; the report
  says how many of each were replaced. Without a rules file, freezing a harvest from a source marked `private` is
  refused.
- What is not caught by rules is not claimed as caught: the report says "N replacements by these rules", never "no
  personal data".

### 4. Select

- `evh dataset-from-harvest H --dataset-id D [--from D_prev] [--where F:V] [--dedup exact|text] [--sample N
  --by F --seed S]`: filters on fields, removes exact or normalised-text duplicates (and items already in `--from`),
  samples N, stratified by a field when given, seeded. The selection rule is recorded in the dataset's file
  (`made_from: {harvest, query, filters, dedup, sample, seed}`), so "why these items" has an answer.
- `--from D_prev` makes it a new version of an existing dataset with 0.4.0's lineage (added, removed, changed): a
  dataset grows by versions, and the previous version stays frozen.

### 5. Labels and fields

- **Dataset labels**: `labels: {source, environment, purpose, owner, privacy}` in the dataset's file (outside its
  identity, as fields are: changing a label never changes a dataset's id). `privacy: public | private` decides what
  the catalog may show (the 0.4.5 profile still never holds text; `private` also hides the source links).
- **Item fields** from the record (RFC-006 field sets): provenance (`trace_id`, `created_at`, `environment`,
  `stage`), and the project's own (`area`, `severity`). Public only by opt-in, as today.
- The catalog's datasets page groups and filters on labels; `evh datasets --label environment=prod`.

### 6. References from outcomes

- What production already recorded after the fact is often the best reference there is:
  - the triage fleet: the issue's fate (kept open and fixed, closed as a duplicate, relabelled, closed as noise),
    read from GitHub, is the gold for "was this triage decision right";
  - a Langfuse score or user feedback on a generation, for a judgement of the output;
  - a ticket's resolution code.
- An importer returns it as `outcome`; `evh reference-from-outcomes --dataset-id D --map outcomes.yaml` writes a gold
  reference (`authored_by: {kind: "outcome", source, mapping}`), the mapping (outcome → label) recorded and hashed.
- An item whose outcome is not yet known (an issue still open) has no reference; the reference says how many items it
  covers, and the coverage check (0.4.0) refuses a comparison that would silently drop them.

### 7. Splits and growth

- `evh dataset-split D --goal G --heldout 0.3 --seed S` assigns each item to dev or heldout by a hash of its id and
  the seed, so a later version keeps every earlier item where it was, and new items fall in proportion. 0.5.0's test
  looks (RFC-015) count against the heldout part.
- **Drift is visible, not corrected**: each version's profile (0.4.5) shows its lengths and label balance; the
  dataset page compares a version with the one it came from.

### 8. Continuous experimentation, by hand or by an agent (no schedule)

A round, repeated when the person (or an agent, asked) chooses: harvest the last window, scrub, make the next version
from it, run the baseline and the candidates on it (0.5.0's runners), compare against the baseline, and read the
trends. Each step is a command; the catalog shows the versions, their profiles and the comparisons. A scheduler is
out of scope here.

### 9. Agents

- Read tools (0.4.5): `datasets`, `dataset-items`, and `harvests` (new: list harvests and their counts).
- Write tools (0.5.0, RFC-013 declarations): `dataset-harvest`, `harvest-scrub`, `dataset-from-harvest`,
  `dataset-split`, `reference-from-outcomes`. **Freezing a dataset from a harvest of a `private` source needs the
  person's `--confirm`**: what production data becomes a committed dataset is a person's decision. An agent can
  prepare everything up to it and hand the person the exact command.
- A skill, `evh-dataset-from-production`, walks an agent through the steps above.

## Not in scope

- Scheduled or continuous harvests (the owner, 2026-10-28).
- A labelling interface for people (references here come from outcomes, a model, or files).
- Storing private records for a project: the harness records where they are and their hashes, never holds them.

## Alternatives considered

- **Importers in the core for Langfuse and GitHub.** Rejected for now: the core stays generic; a vendor's API changes
  on its own schedule. The examples are maintained here, and a project copies or imports them.
- **Committing scrubbed records.** Rejected by default: scrubbing by rules is not anonymisation, and a public
  repository would publish whatever the rules missed. A project that decides otherwise commits them itself.
- **Splitting by time (older dev, newer heldout).** Kept as an option (`--split time`) rather than the default: it
  tests the future, but makes dev and heldout differ in more than chance.

## Open questions for the review

1. Is `outcome` per record the right shape for the triage fleet's gold, or should the GitHub timeline be read when the
   reference is made (outcomes change after the harvest)?
2. Where do private records live: a gitignored directory only, or a named private store (a second repository, S3)
   the harness can verify against `harvest.json`?
3. Should freezing a harvest of a `public` source also need the person's confirmation?
4. Which first: the Langfuse importer for the podcast pipeline, or the GitHub importer for the triage fleet?

## Testing (when built)

- An importer contract test any importer runs (`evh importer-check`): ids unique, hashes stable, `created_at` parsed.
- `jsonl` end to end: harvest, scrub (planted emails replaced, counts right), select (dedup, a seeded sample that
  repeats), a version with lineage, a split that keeps earlier items in place, an outcome reference with coverage.
- The examples' importers against recorded responses (no network in CI).
