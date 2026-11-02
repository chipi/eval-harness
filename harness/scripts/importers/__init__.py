"""The importers that come with the harness (RFC-019), one module each.

Each is `Importer(options).records(query)`, loaded by name by `_importers.resolve`; the core never
imports this package otherwise. They use the standard library only (and `gh` for GitHub).
"""
