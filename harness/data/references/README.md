# references/ — ground truth

    gold/     the answers a decision rests on. The thing you actually want to be right about.
    silver/   consistent, not correct: good enough to rank arms against each other.

A reference is a label set promoted on purpose (`evh reference-promote --tier … --reason …`): the tier is
chosen then, with a reason, and the source (a person, a model, a rule) is recorded beside it, never taken
as the tier. Each reference has a `manifest.json` (`schemas/reference.schema.json`): its tier, its item
count, where it was promoted from and the checksum of every item's text. `reference-promote` writes it;
for gold a script builds, `evh reference-manifest`. The manifest is committed even when the texts are
not, and `evh validate` (V16) checks the texts present against it. A reference promoted from a label set
kept out of git (`label-from-run --not-redistributed`) names the command that rebuilds its texts.

**They are not interchangeable.** A run scored against a mix of the two is
reporting a number nobody can interpret. If you use silver because gold is
expensive, say so wherever the number is published.
