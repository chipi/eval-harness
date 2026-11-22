"""The dataset sources that come with the harness (PLAN_0.8.0 E5), one module each.

Each is `Source(options)` with `describe(query)` and `items(query)`, loaded by name by `_sources.resolve`; the core
never imports this package otherwise. They use the standard library only.
"""
