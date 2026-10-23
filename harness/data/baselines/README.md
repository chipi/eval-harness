# baselines/ — promoted numbers

The number future work is judged against. Created by `make run-promote`, which
refuses a run from a dirty tree, refuses a run whose build is unknown, and
refuses a one-word reason — because in six months *"why is this the baseline?"*
has to have an answer.

**Never edited.** Promoting another run replaces the baseline; git keeps the one it
replaced, and `validate` (V6) fails a baseline that no longer matches its run.

These are worth committing.
