"""A custom adapter of a coding bake-off's shape: it declares kinds and no directions, and prices a model by its params."""

from evaluation_harness.adapter import Result

PRIMARY_METRIC = "pass"
METRIC_KINDS = {"turns": "descriptive", "checks_frac": "descriptive"}


def call_system(text, params):
    """A reply as long as the item, at no cost: a zero-priced local model."""
    n = len(text.split())
    return Result(output=text[: 8 + n], tokens_in=40 + n, tokens_out=12, cost_usd=0.0, extra={"turns": 2.0})


def score(output, reference=None):
    """Its own checks, no reference needed: an even-length reply passes."""
    ok = 1.0 if len(output) % 2 == 0 else 0.0
    return {"pass": ok, "checks_frac": 0.5 + 0.5 * ok}
