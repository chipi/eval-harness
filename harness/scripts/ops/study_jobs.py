"""The study and prompt commands, as operations that run as jobs (RFC-032 step 9 P3, step 8): a study opened and run,
its agent sampler's ask and tell, its stop, its confirmation on a test set (a decision: one look), a past loop imported,
and a prompt version recorded or written out. A study is named `<goal>/<study_id>`: one input, `study`, which a route's
`{goal}` and `{study}` parts make together (`study_parts`). Each is a POST on its resource and answers 202 with the job;
an operation that spends takes `max_cost_usd`."""

from __future__ import annotations

from evaluation_harness.ops.registry import Op

_C = "evaluation_harness._study_cmd"
_P = "evaluation_harness._prompt_cmd"
_PARTS = "evaluation_harness.ops.study_jobs:study_parts"
#: Both parts of a study's route fill the one input that names it.
_STUDY_PARTS = {"goal": "study", "study": "study"}
_STUDY = {"type": "string", "description": "the study: <goal>/<study_id>, or its id when one goal has it"}


def study_parts(goal: str, study: str) -> dict[str, str]:
    """The inputs a study's route gives: its goal and id, as the one `study` input names them."""
    return {"study": f"{goal}/{study}"}


OPS = (
    Op("study-run", "work", "open a study and run it (RFC-029): research on validation items, never evidence",
       "POST", "/goals/{goal}/studies/{study}", f"{_C}:run_study_body", "",
       locks=(("study-loop:{study}", True),), spends=True, parts=_STUDY_PARTS, parts_fn=_PARTS,
       required=("study",), inputs={
           "study": {**_STUDY, "description": "<goal>/<study_id>"},
           "spec": {"type": "string", "format": "path", "x-file": "upload",
                    "description": "the spec, written into data/studies/<goal>/<study_id>.yaml first"},
           "resume": {"type": "boolean", "description": "continue a study after its last finished trial"},
           "dry_run": {"type": "boolean", "description": "check the spec and print the plan; call nothing"},
       }),
    Op("study-ask", "work", "the state of a study for the agent sampler, with an ask id (RFC-029)",
       "POST", "/goals/{goal}/studies/{study}/ask", f"{_C}:ask_body", "",
       locks=(), parts=_STUDY_PARTS, parts_fn=_PARTS, required=("study",), inputs={"study": _STUDY}),
    Op("study-tell", "work", "run the agent's proposal as a study's next trial (RFC-029)",
       "POST", "/goals/{goal}/studies/{study}/tell", f"{_C}:tell_body", "",
       locks=(("study-loop:{study}", True),), spends=True, parts=_STUDY_PARTS, parts_fn=_PARTS,
       required=("study", "ask"), exclusive=(("proposal", "proposal_json"),), one_of=("proposal", "proposal_json"),
       tool_hidden=("proposal",), inputs={
           "study": _STUDY,
           "ask": {"type": "string", "description": "the ask id study-ask gave"},
           "proposal": {"type": "string", "format": "path",
                        "description": 'a JSON file: {"params": {"a.b": v}, "prompts": {name: text}, '
                                       '"hypothesis": "...", "rationale": "..."}'},
           "proposal_json": {"type": "string", "x-file": "no",
                             "description": "the same proposal as JSON text (an MCP tool call sends this)"},
       }),
    Op("study-stop", "work", "stop a study (RFC-029): the loop stops after its trial; the study ends",
       "POST", "/goals/{goal}/studies/{study}/stop", f"{_C}:stop_body", "",
       locks=(), parts=_STUDY_PARTS, parts_fn=_PARTS, required=("study",), inputs={"study": _STUDY}),
    Op("study-confirm", "decision",
       "confirm a study's best trial on a test set: one look, one-sided at its level (RFC-029)",
       "POST", "/goals/{goal}/studies/{study}/confirm", f"{_C}:confirm_body", "",
       locks=(("dataset:{test}", True),), spends=True, parts=_STUDY_PARTS, parts_fn=_PARTS,
       required=("study", "test", "rule"), inputs={
           "study": _STUDY,
           "test": {"type": "string", "description": "the test set (a goal's role: test dataset, or a sealed side)"},
           "rule": {"type": "string", "enum": ["superiority", "noninferiority"],
                    "description": "given before any test item is read"},
           "trial": {"type": "integer", "description": "this trial instead of the best kept one"},
           "margin": {"type": "number", "description": "noninferiority: the margin (default: the study's accept.margin)"},
           "dry_run": {"type": "boolean", "description": "the items, the look and whether it can succeed; run nothing"},
           "confirm_extra_look": {"type": "boolean", "description": "past the set's limit: the person's consent"},
           "override_no_evidence": {"type": "boolean",
                                    "description": "items that cannot show it: run anyway, inconclusive"},
       }),
    Op("study-import", "work", "import a past loop's results.tsv as a closed study (RFC-029; not confirmable)",
       "POST", "/goals/{goal}/study-imports", f"{_C}:import_tsv_body", "",
       locks=(), required=("file", "goal", "study"), inputs={
           "file": {"type": "string", "format": "path", "x-file": "upload", "description": "the results.tsv"},
           "goal": {"type": "string", "description": "the goal the study belongs to"},
           "study": {"type": "string", "description": "the study id to give it"},
       }),
    Op("prompt-version", "work", "record a prompt version (RFC-028), from a file or a text, with its parent and a note",
       "POST", "/prompts/versions", f"{_P}:version_body", "",
       locks=(), required=("name", "note"), exclusive=(("from_file", "text"),), one_of=("from_file", "text"),
       inputs={
           "name": {"type": "string", "description": "the prompt's name, as systems declare it"},
           "from_file": {"type": "string", "format": "path", "x-file": "upload",
                         "description": "the version's bytes, from this file"},
           "text": {"type": "string", "description": "the version's text"},
           "parent": {"type": "string", "description": "the version it was made from (<name>/<sha16>)"},
           "note": {"type": "string", "description": "what changed and why"},
       }),
    Op("prompt-export", "work", "write a prompt version out (RFC-028), for a person to commit",
       "POST", "/prompts/versions/export", f"{_P}:export_body", "",
       locks=(), required=("id", "to"), inputs={
           "id": {"type": "string", "description": "the version, <name>/<sha16>"},
           "to": {"type": "string", "format": "path", "x-file": "artifact", "description": "where to write it"},
       }),
)  # fmt: skip
