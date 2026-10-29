# 0.7.0: where it stands and what comes next

Written 2026-10-27, when the design was finished and paused for the owner's review. Branch `070`. On 2026-10-28 the
branch was rebased onto 0.4.4 and the design reconciled with what 0.4.1 to 0.4.4 shipped (below).

## Where it stands

The design is done; no 0.7.0 code is written.

- **PRDs** (what and why): [PRD-008](../../docs/prd/PRD-008-pipelines-and-any-language.md) to
  [PRD-013](../../docs/prd/PRD-013-identity-and-ties.md), with amendments to PRD-001 and PRD-005.
- **RFCs** (how): [RFC-007](../../docs/rfc/RFC-007-stages-and-stage-references.md) to
  [RFC-017](../../docs/rfc/RFC-017-record-store.md).
- **ADRs** (the decisions): ADR-0007 to ADR-0017; ADR-0006's tie rule is superseded by ADR-0015.
- **UXS** (what people and agents see): [UXS-004](../../docs/uxs/UXS-004-studies-baselines-prompts.md) and
  [UXS-005](../../docs/uxs/UXS-005-agents.md) are new; UXS-001 to UXS-003 have "0.7.0 changes (draft)" sections.
- **Mockups**: six screens on a design canvas, <https://claude.ai/artifact/RQ7cy7zf1kah4d6jb6eUE2> (private to the
  owner); their sources are in [mockups-0.7.0/](mockups-0.7.0/) (one `.dc.html` per screen, `canvas.json` the layout).
- **Statistics** behind RFC-015: [stats-0.7.0/](stats-0.7.0/README.md), every table reproducible from its script.

How the design got here, in order: three PRD review rounds; two RFC reviewers (fixes in e4f167f1); revision 2
(records for teams: write-once records, collision-free ids, nothing derivable stored; scope cuts); the 0.4.0
vocabulary kept (baseline, dev, heldout, separated, ERROR, exit 3); revision 3 (a second simplification pass, all 14
accepted); "a study is research, never search". The owner's decisions are recorded in each document's Status line and
in the ADRs.

### Reconciled with 0.4.1 to 0.4.4 (2026-10-28)

An audit of every 0.7.0 document against the 0.4.1–0.4.4 changelog and code found the design silent on what 0.4.2
added to the catalog, and a few statements 0.4.x made wrong. Folded in:

- **The period** (ADR-0018): the studies and prompts pages carry it from their own builders (`period_studies`,
  `period_prompts`), `evh studies` and `evh prompts` take `--period P`, every study event carries `at`, and a list
  command's `--json` names the days it counted (RFC-013).
- **The activity and arms pages**: trials as arms ("trial k of study s2", group by study, folded in what changed),
  stage and process arms in the model column, quality chips on non-inferiority, `judge.cost_usd` billed as judges,
  local / hosted about the provider, not the runner (UXS-001, RFC-007, RFC-008, RFC-010, RFC-015, PRD-010).
- **The nav's groups**: Studies and Prompts go under Experiments (UXS-004).
- **0.4.x's deployment rules**: no `style` attributes (the CSP), no new inspector API route, prompt publishing as a
  flag (`evh catalog --publish prompts`) like `--head`, `--about` and `--repo`, not a `config.yaml` key (RFC-009,
  RFC-013, UXS-002, UXS-004); `llms.txt` at both the docs root and the site root (RFC-016, UXS-005).
- **Readers and references**: the two 0.4.2 baseline readers that ignore the goal (RFC-014, PRD-013),
  `_common.reference_texts` (RFC-007), `data/models.yaml` in how to reproduce a baseline (RFC-012, PRD-011) and in
  RFC-003's adapter protocol (`model_facts`), line references and counts moved by 0.4.x (RFC-013, RFC-014, PRD-012),
  0.4.4's double-module fix as the case RFC-013's import design covers, the inspector's memory bound (RFC-015), the
  migration starting from 0.4.4 (RFC-014, PRD-013), and the test tiers of `harness/docs/TESTING.md` (RFC-013).
- **Contradictions inside the design** found on the way: PRD-001's "no trends" non-goal (now: no quality over time),
  UXS-005's `consent` command (gone in revision 3), INFLUENCES' "a tie is an equivalence claim" (now
  non-inferiority), UXS-001's link to a baselines page (there is none).

## In one paragraph

0.7.0 lets a project improve its real system: a pipeline with stages, prompts and settings, in any language. A
**study** is research after Karpathy's autoresearch: an agent, a grid or an optimiser proposes changes, each is run
on dev items and kept or dropped, and everything is logged; only a **confirmation** on heldout items the study never
saw is evidence, and a person promotes. **Baselines** keep their history and the evidence for each promotion.
Non-inferiority against a declared margin replaces "tied", and heldout sets spend their level over front-loaded looks.
Job sets run long work locally or over ssh. Every command is declared once, with `--json`, exit codes and refusals;
an MCP server and three skills make it the same for agents; consent is always the person running the command.
Records are written once with ids that cannot collide, so teams merge them through git, and a database can later
take their place behind one store contract.

## Next steps

0. **What 0.5.0 and 0.6.0 bring forward** (2026-10-29): 0.5.0 ships a read-only MCP server (`evh mcp`, stdio and
   Streamable HTTP; RFC-018 on `main`) and its public deployment at `evals.humancopilot.eu/mcp`, so 0.7.0's RFC-013 and
   RFC-016 extend a server that exists rather than introduce one; users and permissions on a shared server are a new
   design item in RFC-016 ("Users on a shared server"). Datasets from production (RFC-019) moved to `main`, aimed at
   0.6.0, in review.
1. **The owner reviews** the documents and the mockups. Comments go on the documents (or the canvas); decisions
   go into the ADRs.
2. **A pull request** for `070` against `main`, once the review is done, so the design lands before the code.
3. **Implementation**, in the order the RFCs depend on each other:
   1. RFC-013 (command declarations, `--json`, exit codes, refusals, actor, `config.yaml`, Python 3.10) and
      RFC-017 (the record store);
   2. RFC-014 (fingerprint v5, run ids, the grammar, baselines per goal) and the migration script, run on this
      repository first;
   3. RFC-015 (non-inferiority, looks, power) and the validation suite;
   4. RFC-007 (stages, item failures, batches) and RFC-008 (the process adapter);
   5. RFC-009 (prompt versions);
   6. RFC-011 (job sets, phases, the ssh runner);
   7. RFC-010 (studies, `study-confirm`);
   8. RFC-012 (evidence, `evh baselines --json`, `evidence-check`);
   9. RFC-016 (the MCP server, the skills, llms.txt, the glossary);
   10. the catalog and inspector pages of UXS-001 to UXS-005.
4. **Before release**: each goal here declares its margins in `axes.<axis>.margin`; the migration runs on this
   repository and then on the podcast project after its pin moves; UPGRADING.md and the CHANGELOG list every
   breaking change (exit codes 1 and 2 split, the fingerprint version, baselines per goal); the agent scenario test
   (PRD-012 FR8.2) runs once.

## Not done, and things to know

- **Nothing is implemented**, and no design claim is tested against code beyond what the reviewers checked.
- **The podcast project's adoption** is written "to be confirmed with that project" in PRD-009 and PRD-011: its blend
  weights, its shared-prompt guard (waits for the deferred tracks) and its 40%-contested fallback (waits for the
  deferred contested policies).
- **Deferred on purpose** (RFC-010, PRD-009 FR6): several datasets per study, a built-in LLM sampler, contested-judgement
  policies, column-map imports, budgets per role, data-egress settings; MCP resources and elicitation (RFC-016);
  the HTTP transport (RFC-008); OTLP export (RFC-007).
- **The docs build does not catch broken links between docs**: `site/mkdocs_hooks.py` rewrites a link to a missing
  page into a GitHub URL, so `mkdocs build --strict` passes. A link check script was used by hand during this work.
- **Open from earlier, outside the design**:
  - homelab has not answered about a GlitchTip token that can resolve issues (a superuser session was used);
  - the Umami probe rows of 2026-10-26 are still in the stats (deleting them needs the owner's approval);
  - `autoresearch/1022_gb10_tuning/run_labeled.sh:32` in podcast-scraper-eval-data has a hard-coded default
    `VLLM_API_KEY` in a tracked file (found, not acted on);
  - the podcast project's harness pin move: its main pins `@v0.3.0` (origin, 2026-10-27; the local checkout pins
    `0b2ca8b2`, a 0.4.0 branch commit of 2026-10-25, not a release); the target is v0.4.4, then 0.7.0.
