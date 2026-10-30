# Publishing the triage data on Hugging Face: what we create, and how it works

Status: 2026-10-30, the plan for the first publish (owner's decision: Hugging Face is the dataset's own git).
Written to be read once before doing it. The parts marked **check on first publish** are how I understand Hugging
Face works and have not been tried from here yet.

## 1. What a Hugging Face dataset is

- **A git repository** at `https://huggingface.co/datasets/<owner>/<name>`. Its files are versioned like code; a
  version is a commit, and a **tag** names one (`v1`). Large files are stored by Hugging Face's own large-file
  layer; you use it like ordinary git.
- **`README.md` is the dataset card.** It has two parts:
  - a **YAML header**: the licence, the task, tags, and `configs`, which tell Hugging Face which files make up
    which part of the dataset;
  - **the text** a reader sees: what an item is, how the data was made, what it is for and not for.
- **The dataset viewer.** For JSONL (and Parquet) files, the website shows the rows in a browsable table, with no
  extra work. That is where our profile's per-item links will point.
- **Public or private.** A repository can start private and be made public later.
- **Pinning.** A reader downloads a file at a revision (a tag or a commit sha):
  `https://huggingface.co/datasets/<owner>/<name>/resolve/<revision>/<path>`. Tags are not meant to move, so
  `v1` keeps meaning the same bytes. Our own sha256 per item checks that anyway.

## 2. What we create

Two repositories, one per type of data (the types are defined in DATA_INVENTORY §3a).

### 2.1 `<owner>/orrery-triage`: agent decisions captured from production, with their verdicts

```
README.md                    the dataset card
data/decisions.jsonl         one line per triage decision (the items)
data/verdicts.jsonl          one line per labelled decision (the references)
```

**Two `configs`**, so the viewer and a reader see two tables: `decisions` and `verdicts`.

**A line of `decisions.jsonl`**, one decision:

| key | what it holds |
|---|---|
| `id` | the occurrence id, e.g. `glitchtip:ORRERY-PROD-3@2026-08-31T06:52:21Z` |
| `created_at` | when the fleet decided |
| `evidence_level` | `exact`, `full-rebuild`, `no-traces`, `no-logs` or `ledger-only` |
| `signal` | what the agent received: source, alert name, labels, summary |
| `probes` | the answer to every probe the agent could ask, keyed by probe and arguments |
| `probe_source` | per probe: `verbatim` (what the model saw), `rebuilt` (read again for that time window), `unavailable` (the store had nothing), `static` |
| `fleet_decision` | what production did: disposition, model, prompt version and sha, gates, reason |
| `outcome` | what happened afterwards: the issue, its verdict (fixed, noise, duplicate, open), reopened, seen again, age |

**A line of `verdicts.jsonl`**, one label:

| key | what it holds |
|---|---|
| `id` | the decision it labels |
| `label` | `file`, `dismiss`, `escalate` or `cleanup` |
| `source` | `owner-issue-verdict` (the owner's verdict on the issue, carried to the decision), `owner-item-label` (the owner labelled the decision itself), `outcome-mapping` (computed from the outcome; shown, never decisive), or `fixture` (the fleet's old hand labels) |
| `issue` | the GitHub issue number, when there is one |
| `note` | the owner's own words, when he wrote any |

**The card, `README.md`.** The YAML header:

```yaml
license: <owner's choice>
pretty_name: Orrery triage decisions
task_categories: [text-classification]
tags: [agents, evaluation, observability, triage, llm-as-classifier]
size_categories: [n<1K]
configs:
  - config_name: decisions
    data_files: data/decisions.jsonl
  - config_name: verdicts
    data_files: data/verdicts.jsonl
```

The text, in sections:
1. **What this is.** A triage agent's real decisions on production error signals, with what it could see and
   what happened next. An evaluation set for one agent step, replayable through the agent's own code.
2. **What an item is.** The two tables above.
3. **How it was made.** The fleet's build script (its commit), what each store kept and for how long, how probes
   were anchored to the decision's time, and the scrubber (its commit). No secrets were found after scrubbing.
4. **The evidence levels**, and what "rebuilt" means. Only `exact` items are what the model saw.
5. **The verdicts**: who gave them, and how, and why the outcome mapping is shown but never decides.
6. **Intended use**: comparing models or prompts for this agent step, arm against arm, on the same items. **Not
   intended**: training, or ranking models in general (one project, one fleet, one prompt).
7. **Limitations.**
   - Most items have thin evidence (89% of the labelled items lack logs).
   - The labels are thin: 22 fingerprints carry a `file` label.
   - Items share fingerprints: 172 distinct fingerprints across 236 decisions.
   - There are test signals in the ledger, which were removed.
8. **Versions**: a table of tags, with the date range and item count of each.
9. **How it is used**: a link to the evaluation harness's experiment and to the fleet.

**The tag `v1`**: the 236 decisions from 2026-07-25 to 2026-10-29, minus the test signals, and their verdicts.

### 2.2 `<owner>/signal-fleet-dedup`: signals for a deterministic stage

```
README.md                    the dataset card
data/signals.jsonl           the 100 scrubbed signals (the fleet's reference-dedup corpus)
```

Its card is shorter. It says the signals replay through the fleet's de-duplication functions, that there is no
model and no label, and that the reference is the current code's output, so the dataset guards against
regressions. Tag `v1`.

## 3. How it is made (the steps, and who does each)

1. **The owner decides:**
   - the **account** (the connector is logged in as `chipi-nbgd`; an organisation is possible);
   - the **licence**. CC-BY-4.0 is the common choice for a dataset that should be reused with credit;
   - whether to **start private** and make it public after reading the card.
2. **Rebuild** `decisions.jsonl` with the close comments and the better join (homelab, on the mini), and scrub it.
   **Write** `verdicts.jsonl` from the owner's verdicts and labels (the labelling sheet), plus the outcome and
   fixture labels, each marked with its `source`.
3. **Scrub, then check, before anything leaves the machine.** Three layers:
   - **The fleet's scrubber** (`signal-fleet/mvp/scrub.py`), in two tiers:
     - secrets are redacted, and the scrub fails if any remain;
     - production identifiers are mapped to stable fake ones (`acme/orrery`, hosts, paths, commit shas).

     It runs on both files, `verdicts.jsonl` included: the close comments name commits and repositories.
   - **Our own check** of the scrubbed files:
     - gitleaks;
     - a pattern scan for IP addresses, emails, tailnet host names, home paths, real domains and repository
       names, tokens, keys and JWTs, and the operator's host names.

     The v1 file as delivered (2026-10-30): **0 hits on all of them**. 266 IPs were already `<ip>`, and 300
     identifiers already fake.
   - **One open item: browser user-agent strings.** 64 occurrences (15 distinct) in GlitchTip event details,
     from Orrery's visitors. Proposal: reduce each to the browser family and major version ("Chrome 141"),
     either as a rule in the fleet's scrubber (the fleet's repository) or as a pass in the build script. Owner's
     call.

   Nothing is uploaded unless all three layers pass. The repository starts **private**.
4. **Create the repository and upload.** **Check on first publish:**
   - with the `huggingface_hub` Python package, `create_repo(repo_type="dataset")`, `upload_folder(...)`,
     `create_tag("v1")`;
   - it needs a Hugging Face token with write access. The owner runs `hf auth login` once, or gives a token in an
     environment variable;
   - the package goes into this worktree's own virtual environment, not a shared one, and is a development tool,
     not a harness dependency.
5. **Read it back.** Check the viewer shows both tables, download `resolve/v1/data/decisions.jsonl`, and compare
   its sha256 with the file we uploaded.
6. **The owner reads the card and a sample**, then the repository is made public, if it started private.

## 4. How this repository uses it

- **`examples/triage-fleet/fetch.py`** downloads `resolve/v1/data/decisions.jsonl` with the standard library,
  writes each item into `data/sources/orrery_triage_v1/` (gitignored), and **fails if any item's sha256 differs**
  from the committed dataset file. This is the same contract as the six experiments' fetchers. It also writes the
  row numbers (`data/sources/orrery_triage_v1.rows.json`), so the catalog's profile links each item to its row in
  the Hugging Face viewer, as the other experiments do.
- **Committed here:**
  - the dataset file (ids, sha256s, fields, `made_from` with the capture);
  - `gold/orrery_triage_v1`, made from `verdicts.jsonl`'s owner rows;
  - the two silver references;
  - the runs;
  - the goal;
  - the revision `v1`, in `fetch.py` and in the capture's query.
- **Not committed here:** the items themselves.

## 5. A new month

1. The fleet's per-decision captures for the month are exported and scrubbed.
2. They are appended to `decisions.jsonl`, and the month's verdicts to `verdicts.jsonl`.
3. The commit is tagged `v2`. `v1` still names exactly what it named.
4. Here: `evh capture --since-capture …` from `v2`, then `evh dataset-from-capture --from orrery_triage_v1`, which
   makes `orrery_triage_v2` with its lineage.

## 6. What it costs, and what can go wrong

- **Hugging Face hosting** of a public dataset this size is free.
- **A tag moved by mistake** changes what `v1` returns. Our per-item hashes catch it: fetch fails rather than
  silently changing the data.
- **A secret that got past the scrubber** would be public. Two defences: gitleaks runs on the files before upload,
  and the owner reads the card and a sample while the repository is still private.
- **Hugging Face being down** stops a fresh fetch, not anything already fetched or committed.
