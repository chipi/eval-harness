# references/ — ground truth

    gold/     human-authored. The thing you actually want to be right about.
    silver/   model-generated. Cheap, plentiful, and not the same thing.

Each reference has a `manifest.json` (`schemas/reference.schema.json`): its tier, its item count
and the checksum of every item's text. `evh reference-create` writes it; for gold a script builds,
`evh reference-manifest`. The manifest is committed even when the texts are not, and `evh validate`
(V16) checks the texts present against it.

**They are not interchangeable.** A run scored against a mix of the two is
reporting a number nobody can interpret. If you use silver because gold is
expensive, say so wherever the number is published.
