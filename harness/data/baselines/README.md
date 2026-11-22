# baselines/ — promoted numbers

The number future work is judged against (RFC-027). `data/baselines/<goal>/<dataset>/<n>.json` is version `n` of
a goal's baseline on a dataset; `_dataset/<dataset>/<n>.json` is a dataset's own, for runs with no goal. Created
by `evh run-promote`, which refuses a run from a dirty tree, a run whose build is unknown, a reason under three
words and an actor it cannot name, because in six months *"why is this the baseline, and who decided?"* has to
have an answer.

**Written once.** Promoting writes the next version with the paired test against the one it replaces frozen in;
`evh baseline-rollback` goes back as another version. `validate` (V6) fails a version that no longer matches its
run, or a line whose versions do not run 1..n. `evh baselines` lists them.

These are worth committing.
