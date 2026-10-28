# PRD-013: Baselines per goal, the host beside the hash, non-inferiority, heldout looks, one grammar

- **Status**: Draft (0.5.0), revision 3 (2026-10-27): the grammar only for versioned things and runs; no equivalence
  claim; the MDE is the formula. Revision 2 (2026-10-27): versions are collision-free ids, not numbers; looks are
  counted from decisions; continuous non-inferiority from 100 items at half the level
- **Authors**: Marko Dragoljevic
- **Related RFCs**: [RFC-001](../rfc/RFC-001-fingerprint-and-code-identity.md) (the fingerprint, to gain
  version 5), [RFC-004](../rfc/RFC-004-experiment-rounds.md) (rounds and baselines); [RFC-014](../rfc/RFC-014-identity-baselines-migration.md) (these changes
  and the migration script), [RFC-015](../rfc/RFC-015-noninferiority-looks-power.md) (non-inferiority, verdicts, test
  looks, power)
- **Related ADRs**: [ADR-0006](../adr/ADR-0006-goal-axes-and-strategies.md) (goal ties, superseded in part by
  this PRD)
- **Related PRDs**: [PRD-001](PRD-001-experiments-and-comparison.md),
  [PRD-005](PRD-005-goals-and-rounds.md) (amended by this PRD), [PRD-009](PRD-009-prompts-and-optimisation.md),
  [PRD-010](PRD-010-runners.md), [PRD-011](PRD-011-evidence-registry.md), [PRD-012](PRD-012-agent-ready.md)

## Summary

The 0.5.0 reviews found things in 0.4.0 that the new work would build on and get wrong, and three review
rounds sharpened the fixes. A baseline belongs to a **dataset**; it should belong to a goal on a dataset.
The **host** label is inside the fingerprint's hash, so the same arm on two machines reads as an
uncontrolled comparison. A goal calls an arm **tied** with the leader on absence of evidence, against a
margin computed from the data being judged. Tie-breaks become **non-inferiority** tests against a margin
the goal **declares**, decided by p, with a test that is valid for the measure (a score test for 0/1
measures, where the sign-flip test's error rate was measured at up to 30% for a nominal 2.5%). **Test
items** become a budgeted resource: each look at them spends part of the level, counted per item set.
Two runs started in the same second share a **run directory**. Versioned things need **one grammar**. And
the committed data needs a **migration**: a one-time release script, run here and in the podcast
project (the two projects known to use the harness), not a permanent command.

## Background & Context

- `run-promote` names a baseline `<dataset_id>_baseline` (`promote_baseline.py:141`). The name and the
  `baselines/` folder are read in `promote_baseline.py`, `rounds.py`, `validate_tree.py`,
  `catalog_adapter.py`, `list_runs.py`, `catalog_serve.py`, `_common.py` and the harness Makefile; several
  catalog paths take "the last baseline for a dataset" without filtering by goal, among them two that 0.4.2
  added (the goals page's "what happened in the period" and the arms page's "what changed"). This repository has 7
  baselines, all with the default name, one without a goal (`smoke_v1`), two without a fingerprint hash
  (promoted from derived runs); the podcast project has none.
- `_host_identity` (`_fingerprint.py:258-273`) records the host label, the platform and architecture, the
  kernel release, the processor, the CPU count and the Python version, all inside the hash
  (`_fingerprint.py:370`); `run-compare` reports any difference outside `arm` as a confound. The accelerator
  stack (CUDA, torch) that changes a local model's numbers is not recorded. An imported run's host is the
  machine that imported it.
- Every stored hash in both repositories recomputes from its stored body (140 here; 242 imported runs in
  the podcast project, where `imported` is added after hashing); 173 derived runs carry no hash by design.
  Nothing in `validate` recomputes a hash today.
- ADR-0006: an arm ties the quality leader when it is "not separated, and within the margin"; the default
  margin is 2% of the leader's observed mean; `frugal` admits anything the paired test cannot separate.
- `stats.exact_ci` inverts the sign-flip test (95%, two-sided) up to 30 items, uses a t interval above, and
  gives none at 5 items or fewer. On a continuous measure, the bound and a direct one-sided 2.5% test at
  the margin agreed in all 398 cases simulated (6 to 14 items). On a 0/1 measure the shifted sign-flip test
  is invalid: with sparse disagreement its error rate at the margin was 0.078 to 0.299 for a nominal 0.025
  (the final statistics review's simulation, reproduced). Tango's score test for paired proportions (1998)
  is built for this case.
- Goal dataset roles are free text: here `heldout` (6), `dev` (5), `generalization` (1); in the podcast
  project also `smoke`, `prod_sample` and others, and one dataset is test for four goals and validation
  for a fifth. Every dev slice in this repository is nested in its heldout set. All 13 closed rounds
  here compared arms on heldout items; 6 promoted.
- Run ids are the config id and a timestamp to the second (`experiment_run.py:586`), directories created
  with `exist_ok=True`; derived copies keep their source's id, so 59 ids appear in more than one directory.
- No migration command exists.

## Goals

- A baseline answers one goal on one dataset; promotion, rounds, studies and baselines agree on it.
- The same arm on two hosts compares as controlled on quality when only the host label differs; a
  difference that can change results still shows.
- A tie-break is a claim the data supports, by a valid test, against a margin chosen before the data.
- Heldout items are spent knowingly: every look is counted and costs part of the level.
- No two runs share a directory, and a job's run id is known before it starts.
- One grammar names every versioned thing.
- Every verdict says how large the difference is and how precisely it is known; a test that cannot
  separate anything says so before it runs.
- Both projects migrate with one script, a dry run, a stated way back, and a check that proves it.

## Non-Goals

- No change to the test that separates arms on continuous measures (the paired sign-flip test with Holm).
- No automatic choice of a margin: a goal without one gets no tie-breaks.

## Personas

- **The team lead** with two goals on one dataset.
- **The engineer** running the same arm on a GPU host and a laptop.
- **Anyone reading a verdict.**
- **A project on the harness** upgrading to 0.5.0.

## User Stories

- _As a team lead, I promote one baseline for "summary quality" and another for "cheap summaries" on the
  same dataset, and each goal's page shows its own._
- _As an engineer, I compare an arm run on the GPU host with the same arm on my laptop; quality compares as
  controlled, and the page says the host label differs and flags the speed comparison._
- _As a reader, a goal page recommends a cheaper arm only when a valid test shows it non-inferior to the
  leader by the goal's declared margin; otherwise it says "inconclusive" and why._
- _As a team lead, I see that our CNN heldout set has been looked at 7 times of its 10, and that the next
  comparison on it is tested at its smaller share._
- _As a project, I run `python -m evaluation_harness.migrate_0_5_0 --dry-run`, read what will change, what it refuses and what its tag
  cannot restore, run it, and `evh validate` proves every hash._

## Functional Requirements

- **FR1: Baselines per goal and dataset.** A baseline is the current baseline of a goal on a dataset
  ([PRD-011](PRD-011-evidence-registry.md)); `run-promote`, `round-close --promote` and every command or page
  that reads a baseline use it, filtering by goal. A run with no goal promotes to the dataset's goal-less
  baseline (goal `_` in the grammar of FR7).
- **FR2: Fingerprint version 5.**
  - **FR2.1**: The host label, kernel release, processor string and CPU count sit beside the hash; the
    platform and architecture, the Python version and, when the system declares it, the accelerator stack
    (CUDA and driver, torch) stay inside it. For an imported run the whole host block sits beside the hash
    (it describes the importing machine). Runs migrated from version 4 record the accelerator stack as
    not recorded, never inferred.
  - **FR2.2**: The hash excludes an explicit, versioned list of fields (the hash itself, the v4 hash kept
    beside it, `imported`, the reason a derived run has no hash, the host fields beside it).
  - **FR2.3**: `evh validate` recomputes every stored hash from the stored body and fails a mismatch.
  - **FR2.4**: `run-compare` reports a host-label difference as such, not as a confound on quality, and
    flags speed and cost comparisons across hosts.
- **FR3: Non-inferiority, declared, decided by a valid test.**
  - **FR3.1**: A goal declares its margin per measure (the smallest difference that matters, in the
    measure's units) before its runs are judged. A goal without one gets no tie-breaks: its recommendation
    is the quality leader, and `validate` notes the missing margin.
  - **FR3.2**: An arm is **non-inferior** to a reference when a one-sided test of H0: Δ ≤ −margin rejects at
    the level in force (2.5%, or a look's share, FR9). For 0/1 measures the test is the score test for
    paired proportions (Tango); for continuous measures the studentized bootstrap at half the level,
    from 100 items, inconclusive below (RFC-015 has the rule and its simulations). The
    shifted sign-flip test is not used: simulation showed it invalid for 0/1 measures and for skewed
    continuous ones ([RFC-015](../rfc/RFC-015-noninferiority-looks-power.md) has the tables; Tango, and the bootstrap at half the level from 100 items, hold the level there).
    **Inconclusive**: the test does not reject, or cannot (too few items). No claim of "no difference"
    (equivalence) is made: nothing decides on it.
  - **FR3.3**: Strategies: `balanced` and `frugal` recommend, among arms non-inferior to the leader, the best
    on the tie-break (default cost, then speed), `frugal` with the goal's wider declared margin for cost if
    it has one; `quality_first` recommends the leader only. The non-inferiority tests of the candidate arms
    against the leader form one family, corrected by Holm at the one-sided level. An inconclusive arm is
    never recommended on a tie-break. (The leader is chosen from the same data, which makes the comparison
    conservative.)
  - **FR3.4**: An arm separated as worse than the leader but shown non-inferior is reported **non-inferior
    (worse, within margin)** and is eligible for a tie-break.
  - **FR3.5**: ADR-0006 is superseded in part by an ADR that records this. [PRD-005](PRD-005-goals-and-rounds.md)
    is amended: its `non_inferior` direction
    uses this test, and its round suggestions about arms "tied with the leader" use non-inferiority. The
    recommendations that change on this repository's goals are listed in the release notes, each with its
    reason.
- **FR4: Unique run ids.** A run id adds milliseconds and a short random suffix that can never look like a
  repeat suffix (`_r<n>`); a job records its run id when it is queued, so a resumed job finds its run;
  creating a run refuses an existing directory.
- **FR5: Effects beside verdicts.** Every verdict (`pair-test`, `family-test`, the inspector, goal pages,
  rounds, studies) shows the effect as the mean paired difference in the measure's units, with its 95%
  interval (labelled unadjusted, since Holm applies to separation) and, when a look's level is below 2.5%,
  the interval at that level too, beside p and the threshold. **Verdicts are decided by p against the
  threshold; intervals are shown, never used to decide.**
- **FR6: Power before spending.**
  - **FR6.1**: The smallest p a set of items can reach: for superiority 1/2^n′ one-sided, n′ counting items
    whose paired difference is not zero; for non-inferiority of a 0/1 measure, the score test's p at its best
    case (every discordant item favouring the arm); "at best" (all items) before any run. It is compared with
    the level of the next look divided by the size of the family tested. For non-inferiority of a continuous
    measure, possibility is judged by power instead (FR6.2: the smallest provable margin against the goal's
    margin), since a bootstrap p can reach its floor on any data.
  - **FR6.2**: The minimum detectable effect at 80% power: (z₁₋α/m + z₀.₈₀) · σ_d / √n, with σ_d the
    standard deviation of paired differences taken as the upper quartile over existing arm pairs on the
    dataset, or from a pilot pair (for 0/1 measures σ_d² = p₊ + p₋ − (p₊ − p₋)²). For non-inferiority the
    same formula gives the smallest margin provable at 80% power when Δ = 0. At 30 items or fewer, or with
    fewer than 20 discordant items, it is labelled approximate. `rank-stability` reports it; a dry run
    reports it when such data exists.
- **FR7: One grammar.** Every versioned thing is `<kind>:<path>/<version>` (a fixed version) or, for a
  baseline, `<kind>:<path>@current` (the newest); a version is a collision-free id (a time-and-suffix id or
  a content hash), never a sequential number, so two clones cannot make the same one; "version 3" is a
  display number. Kinds are a closed list of the versioned things and runs (`baseline`, `prompt`, `study`,
  `trial`, `run`); goals, datasets, references, rounds and job sets keep their plain 0.4.0 ids. A baseline names its goal and dataset
  (`baseline:news_summary/cnn_200/<version>`, `baseline:news_summary/cnn_200@current`; goal-less
  `baseline:_/smoke_v1/<version>`). A run is named with its runs directory (`run:runs-silver/<run_id>`), since
  derived copies share ids. Baselines are stored as `data/baselines/<goal>/<dataset>/<version>.json`, written
  once, with no index or pointer file (RFC-017).
- **FR8: The 0.5.0 migration script.** A one-time release script, `harness/scripts/migrate_0_5_0.py`,
  shipped in the package (a project that installs the harness has it) and run as
  `python -m evaluation_harness.migrate_0_5_0` (not an `evh` command: no manifest entry, MCP tool or
  skill), migrates a project's committed data to the 0.5.0 format; `UPGRADING.md` documents it, and it is removed in a later release, staying in git
  history. It runs in this order:
  1. Pre-flight (read-only): a clean tree for the data it touches, the harness version, the directories in
     effect, and the shapes of the files it rewrites; `evh validate` is run with the pinned release (0.4.4 here) before the pin moves
     (the upgrade guide says so). The script can be run again: it skips what is done.
  2. Every stored hash is checked against the version-4 rule from the stored body only (never by re-reading
     items, references or code, which may be absent or changed). Any mismatch other than a derived run's
     null refuses the migration.
  3. `--dry-run` prints the plan: every file and field to change, every refusal with the command that
     resolves it, each heldout dataset's use before 0.5.0 (shown, not counted), and the files a tag cannot restore.
  4. A tag per repository (`pre-0.5.0-migrate`) records the starting point; the plan lists what it does not
     cover (files git ignores, such as run files and caches; other repositories; the published site), and
     the migration refuses when those files would be touched.
  5. Fingerprints are restructured to version 5 from the stored body; the version-4 hash is kept beside the
     new one; derived runs keep a null hash with the same host split.
  6. Each per-dataset baseline becomes its goal's baseline on that dataset, version 1 (recording the old id and the version-5 fingerprint hash);
     the old `baselines/` folder is removed.
  7. Dataset roles are not renamed: `dev` and `heldout` stay.
  8. Each heldout dataset's use before 0.5.0 is computed from the runs and shown beside its looks, not counted as looks (FR9.4); nothing is written for looks.
  9. A silver reference's record of the run it came from keeps its version-4 hash (it is part of the
     reference's identity), and the manifest records the version that hash follows outside that record, so
     the reference's digest does not move.
  10. `evh validate` (with the hash recomputation of FR2.3) and a catalog build run after it; the pages show
      the same baselines as before, including the arms page's badges and the goals page's dated baseline events.
  It refuses only real ambiguity among baselines (a custom baseline id; two goals sharing one baseline; a
  goal-less baseline on a dataset a goal uses), never runs in general. This repository migrates first, then
  the podcast project after its pin moves to 0.5.0.
- **FR9: Heldout looks are a budget.**
  - **FR9.1**: A **look** is a decision recorded on heldout items by a command that writes one: a confirmation
    (`study-confirm`), `run-promote`, `round-close --promote`. A recorded look with the same two
    arms, measure and rule is reused, not repeated. Pages and read commands never take a look: on heldout data
    they show the nominal result labelled as not a look.
  - **FR9.2**: Looks are counted per **heldout dataset** (its items, by content hash, in any order), across goals:
    two goals that share a heldout dataset share its budget, and any subset of it spends the dataset's budget.
  - **FR9.3**: Each heldout dataset spends a one-sided α of 2.5% over all its looks, front-loaded (the owner's
    decision): look k is tested at α · 6/(π²k²), so the first at 1.52%, the second at 0.38%, the tenth at
    0.015%; several comparisons within one look share it by Holm. Past a protective limit of K looks (default
    10, declarable per goal) a look needs the person's consent; its level continues the series.
  - **FR9.4**: At migration no looks are counted (the owner's decision): each heldout dataset starts at look 0,
    and the number of distinct configurations that had runs on it in the heldout role before 0.5.0 is computed
    and shown beside its looks.
  - **FR9.5**: Looks are counted from the recorded decisions, never stored apart; two decisions that took
    the same look number (on two machines, or two branches) are reported by `validate` after a merge.
  - **FR9.6**: Goal pages and `evh goals` show each heldout dataset's looks taken, the next look's level, the
    protective limit and its use before 0.5.0.

## Success Criteria

- The migration script runs cleanly on this repository and on the podcast project's data; goal pages show the same
  baselines as before; `validate` recomputes every hash and passes.
- A test shows two goals on one dataset with different baselines; a run pair differing only in host label
  compares as controlled on quality; a pair differing in Python version does not.
- The score test's error rate at the margin, on the review's simulation grid, is at or below the nominal
  level; a planted cheaper arm equal in quality is non-inferior at 200 items and inconclusive at 10; a
  planted worse arm is never recommended.
- A heldout dataset looked at K times refuses look K + 1 without consent, and tests it at the next level of the
  series when consent is given.

## Related Documents

- [RFC-014](../rfc/RFC-014-identity-baselines-migration.md), [RFC-015](../rfc/RFC-015-noninferiority-looks-power.md); [ADR-0006](../adr/ADR-0006-goal-axes-and-strategies.md).
  References ([INFLUENCES](../INFLUENCES.md)): Schuirmann 1987 and Lakens 2017 (equivalence and
  non-inferiority), Tango 1998 (paired proportions), Tian and Ramdas (online familywise error control),
  Dwork et al. 2015 (reusable holdout), Miller 2024 (error bars), Card et al. 2020 (power).
