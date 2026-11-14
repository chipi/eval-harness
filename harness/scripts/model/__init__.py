"""The harness's data model (RFC-032): its entities, each with one schema and one place in the store, read and written
only here, and the views computed from them. The command line, the API, the MCP server and jobs are surfaces over it
(`evaluation_harness.ops`); none of them builds a path to an entity's file.

Entities move here one at a time (RFC-032's build order); the goal is the first. A command whose entity has not moved
still reads and writes its files as before.
"""
