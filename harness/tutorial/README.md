# Tutorial kit

Six invented support tickets (`tickets/`) and a one-line summary of each written by a
person (`gold/`) — a small golden dataset. [`docs/GUIDE.md`](../../docs/GUIDE.md) walks
through freezing them, authoring references, running and comparing arms, and promoting a
baseline, entirely offline. Nothing here is real customer data.

Step 10 of the guide, optional, re-measures the arms' summaries with an LLM judge:
`scorers/tickets-judge-v1.yaml` is a judge scorer whose two judges are `provider: fake`
(offline, $0, never validated), with a `task` block for tickets, and `judge_prompt.txt` is
its prompt. Swap the judges for real models to use it for real.
