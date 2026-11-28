# Shape fixtures

Small projects (`config.yaml` and `data/`) in the shape of the beta projects' data, with invented names, numbers and text.
Written once and frozen: edit one by hand, never regenerate it with the current code, or the test no longer reads data
this checkout did not make. `tests/test_reader_agreement_shapes.py` reads each through every reader, in both stores and in
three time zones.

| Project | Shape |
| --- | --- |
| `fleet` | runs with no goal; a `--repeat 2` set (`_r1`, `_r2`) and a repeat of one of them (`of`, an equal hash); two goals on one dataset family; stamps either side of a UTC midnight |
| `podcast` | every run imported (no goal, `dirty: null`, free-text build refs, scorer `none`), no declared direction, goals whose measures and dataset entries are prose |
| `bakeoff` | no run; three zero-priced local models and one with no price; a custom `adapter.py`; datasets of 3 and 22 items |

The very old format is `fixtures/formats/0`, taken through `evh migrate` by the test.
