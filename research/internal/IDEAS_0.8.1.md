# Ideas for 0.8.1

The list of ideas for release 0.8.1. One entry each: what it is, why, where it came from.

## An installed command to validate a judge

Today, validating a judge is an ordinary eval whose arms are the judges, run over items people have already rated. The scorer's `validation` block names those runs ([RUNBOOK](../../harness/docs/RUNBOOK.md), §12, "Validating a judge: what the gate needs").

The repository's `harness/tools/validate_judge_goyal.py` and `harness/tools/validate_judge_zhang.py` write such runs, but `tools/` is not in the pip package. An installed user has no command for it, and the Workbench's "A judge for this goal" screen can only explain the route: it says a validation is an ordinary eval run with `evh run`, and points to the RUNBOOK.

The idea is an `evh` command, with its Workbench action, that does what those scripts do. Both scripts are specific to one download and to the news-summary judge (as RUNBOOK §12 says), so the command takes the human-rated dataset and the scorer as inputs.

Origin: the 0.8.0 newcomer scenario (2026-11-20). Owner, the same day: for 0.8.1. It needs a short RFC first: what the command writes, how it fills the scorer's `validation` block, and how much of the two scripts' dataset-specific logic generalizes.
