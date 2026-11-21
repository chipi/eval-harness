"""The reports that are jobs (RFC-032 step 9 P3): `evh cost-report` and its resource, `POST /api/v1/reports/cost`. Its body
reads the runs and the judges' verdicts and prints what they cost; it writes nothing, so its job holds the project only."""

from __future__ import annotations

from evaluation_harness.ops.registry import Op

OPS = (
    Op("cost-report", "work", "billed cost per arm, and what judging cost",
       "POST", "/reports/cost", "evaluation_harness.cost_report:body", "",
       locks=(), inputs={
           "dataset_id": {"type": "string", "description": "only this dataset; default every dataset"},
           "match": {"type": "string", "description": "only runs whose system_id contains this (judging, which is not by arm, is then left out)"},
       }),
)  # fmt: skip
