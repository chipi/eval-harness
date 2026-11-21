"""The commands that write the project as a whole, as operations that run as jobs (RFC-032 step 9 P3, step 8): a setting
created, changed or deleted (the data page's save and delete, UXS-004), a run deleted, the data brought to this
release's format, the data moved between files and the database (RFC-025), and the catalog's pages built. A migration
holds the whole project, exclusive. Each is a POST on its resource and answers 202 with the job."""

from __future__ import annotations

from evaluation_harness.ops.registry import Op

_PATH = {
    "type": "string",
    "x-file": "no",
    "description": "the setting, relative to data/ (goals/x.yaml, systems/x.yaml, validate.json, ...)",
}

OPS = (
    Op("data-put", "work", "create or change a setting (system, goal, fieldset, ...), checked first",
       "POST", "/data/file", "evaluation_harness.data_put:body", "",
       locks=(("settings", True),), required=("path",),
       one_of=("file", "set", "unset"), inputs={
           "path": _PATH,
           "file": {"type": "string", "format": "path", "x-file": "upload",
                    "description": "the file holding its whole new text (- on the command line: standard input)"},
           "set": {"type": "object", "description": "fields to set, KEY=VALUE: a dotted key (datasets.0.role), "
                                                    "the value read as YAML"},
           "unset": {"type": "array", "items": {"type": "string"}, "x-metavar": "KEY",
                     "description": "fields to remove, by their dotted key"},
           "check": {"type": "boolean", "description": "only check it; save nothing"},
           "new": {"type": "boolean", "description": "refuse a setting that exists already"},
       }),
    Op("data-rm", "work", "delete a setting, or a whole run",
       "POST", "/data/file/remove", "evaluation_harness.data_rm:body", "",
       locks=(), locks_fn="evaluation_harness.ops.locks:data_rm_locks", required=("path",), inputs={
           "path": {**_PATH, "description": "a setting (goals/x.yaml) or a run's folder (runs/<run id>), relative "
                                            "to data/"},
           "dry_run": {"type": "boolean", "description": "say what would go; delete nothing"},
       }),
    Op("migrate", "work",
       "bring the project's data to this release's formats: runs, datasets, records, fingerprints, once (idempotent)",
       "POST", "/project/migrate", "evaluation_harness.migrate:body", "",
       locks="project", exclusive=(("check", "dry_run"),), inputs={
           "check": {"type": "boolean", "description": "only compare the data's format with this release's"},
           "dry_run": {"type": "boolean", "description": "say what each step would change; write nothing"},
       }),
    Op("data-migrate", "work", "move the project's data/ into its SQLite database or back (RFC-025)",
       "POST", "/project/store/move", "evaluation_harness.data_migrate:body", "",
       locks="project", required=("to",), inputs={
           "to": {"type": "string", "enum": ["files", "sqlite"], "description": "the store to move the data into"},
           "dry_run": {"type": "boolean", "description": "count what would move; move nothing"},
       }),
    Op("catalog", "work", "build the catalog: static pages over the runs, by dataset",
       "POST", "/catalog/build", "evaluation_harness.catalog_build:body", "",
       locks=(("catalog", True),), tool_hidden=("out", "adapter", "head", "about"), inputs={
           "out": {"type": "string", "format": "path", "description": "where the pages go (default .build/catalog)"},
           "adapter": {"type": "string", "description": "path/to/file.py:Class (default: config.yaml "
                                                        "catalog.adapter, else the harness's own layout)"},
           "link": {"type": "array", "items": {"type": "string"}, "x-metavar": "LABEL=URL",
                    "description": "a part of the publication the catalog belongs to, for the header's switcher, in "
                                   "order; URL . is the catalog itself, else it comes first as Catalog. E.g. --link "
                                   "Site=https://evals.example.org/ --link Catalog=. --link "
                                   "Docs=https://evals.example.org/docs/"},
           "brand": {"type": "string", "default": "eval catalog", "description": "the name beside the logo"},
           "api": {"type": "string", "default": "/api/",
                   "description": "where the inspector's API answers, for pages served under a path"},
           "head": {"type": "string", "format": "path", "x-metavar": "FILE",
                    "description": "HTML added to every page's <head>, for a deployment's own analytics or tags "
                                   "(none by default)"},
           "about": {"type": "string", "format": "path", "x-metavar": "FILE",
                     "description": "HTML shown on the overview, under its description: which project this catalog "
                                    "shows, and where its findings are (none by default)"},
           "repo": {"type": "string", "x-metavar": "URL",
                    "description": "where the project's files can be read, e.g. https://github.com/o/r/blob/main/: a "
                                   "project path in a goal's links or a guardrail's source links there"},
           "mcp": {"type": "string", "x-metavar": "URL",
                   "description": "the deployment's MCP server (evh mcp --http): every page's footer names its tool "
                                  "call beside its terminal command"},
           "card": {"type": "string", "x-metavar": "URL",
                    "description": "the image a shared link's card shows (https://..., 1200x630; none by default)"},
           "mcp_howto": {"type": "string", "x-metavar": "URL",
                         "description": "--mcp: where to read how to connect an agent (default: the harness's "
                                        "INTEGRATION guide)"},
       }),
)  # fmt: skip
