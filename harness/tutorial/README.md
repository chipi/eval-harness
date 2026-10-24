# Tutorial kit

Six invented support tickets (`tickets/`) and a one-line summary of each written by a
person (`gold/`) — a small golden dataset — with four arm configs (`configs/`), a goal
(`goals/`), the tickets' fields (`fields/`, `ticket_fields.csv`) and a judge scorer
(`scorers/`, `judge_prompt.txt`). `evh init --tutorial` copies it into a new project. Nothing
here is real customer data.

[Getting started](https://docs.evals.humancopilot.eu/GUIDE/) walks through creating a
dataset, running the arms, making a reference from a run, comparing them and choosing a
baseline, entirely offline. The tutorials that follow it use the rest of the kit:
[tutorial 3](https://docs.evals.humancopilot.eu/tutorials/3-frontier-reference-and-judging/)
the gold summaries and the judge scorer, whose two judges are `provider: fake` (offline, $0,
never validated; swap them for real models to use it for real),
[tutorial 4](https://docs.evals.humancopilot.eu/tutorials/4-rounds-and-versions/) the goal's
rounds, and [tutorial 5](https://docs.evals.humancopilot.eu/tutorials/5-catalog-and-inspector/)
the fields. `judge_panel.yaml` is the judge panel's config (`evh judge --config
tutorial/judge_panel.yaml --use-fake-judge`).
