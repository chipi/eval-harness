"""Do the Hub's safetensors conversion PRs reproduce the six torch-2.6 arms on torch 2.2.2?

The six arms added on 2026-09-30 load `main`'s `pytorch_model.bin`, which transformers
refuses to `torch.load` below torch 2.6 (CVE-2025-32434). Each checkpoint also has a
safetensors conversion PR on the Hub. This checks two claims about each one, on
torch 2.2.2 (the newest Intel-Mac wheel):

  1. loading `main` is refused;
  2. loading the conversion PR succeeds, and through the arm's own adapter, with the
     arm's own params, it reproduces the committed outputs byte for byte.

Run it under torch 2.2.2, from the repo root, with the datasets materialised:

    uv run --no-project --python 3.11 --with torch==2.2.2 --with transformers==4.55.4 \\
        --with 'numpy<2' --with pyyaml --with sentencepiece --with rouge_score \\
        --index https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match \\
        python docs/evidence/conversion_pr_check.py [--bart-items 20]

The BERT arms are checked on every item. The BART arms are checked on the first
`--bart-items` items in dataset order, because beam search on a CPU costs 3-6 s per item.
The result is written to docs/evidence/conversion_pr_check.json.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "harness"
EX = ROOT / "examples"

#: (config path, conversion-PR revision, "bert" | "bart")
ARMS = [
    ("classification-ag-news/configs/arm_bert_base_ta_n200.yaml", "refs/pr/1", "bert"),
    ("classification-ag-news/configs/arm_bert_base_fy_n200.yaml", "refs/pr/1", "bert"),
    ("classification-dbpedia-14/configs/arm_bert_base_fy_n200.yaml", "refs/pr/1", "bert"),
    ("summarization-cnn-dailymail/configs/arm_bart_m_n200.yaml", "refs/pr/29", "bart"),
    ("summarization-cnn-dailymail/configs/arm_bart_s_n200.yaml", "refs/pr/2", "bart"),
    ("summarization-cnn-dailymail/configs/arm_bart_l_xsum_n200.yaml", "refs/pr/9", "bart"),
]


def _adapter(path: Path):
    spec = importlib.util.spec_from_file_location(f"adapter_{path.parent.name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod      # a @dataclass in the adapter looks itself up here
    spec.loader.exec_module(mod)
    return mod


def _recorded_run(config_id: str) -> Path:
    hits = sorted((HARNESS / "data" / "runs").glob(f"{config_id}_*"))
    if len(hits) != 1:
        sys.exit(f"expected one recorded run for {config_id}, found {len(hits)}")
    return hits[0]


def _main_refused(model: str, kind: str) -> str:
    import transformers  # noqa: PLC0415

    cls = (transformers.AutoModelForSeq2SeqLM if kind == "bart"
           else transformers.AutoModelForSequenceClassification)
    try:
        cls.from_pretrained(model, revision="main", use_safetensors=False)
    except Exception as e:  # noqa: BLE001 - the refusal is the point
        return f"{type(e).__name__}: {str(e).splitlines()[0][:160]}"
    return "LOADED"


def _compare(adapter, params, items, mat, run) -> dict:
    same, diffs = 0, []
    for it in items:
        text = (mat / (it.get("source_path") or it["item_id"])).read_text(
            encoding="utf-8", errors="replace")
        got = adapter.call_system(text, params).output
        want = (run / "outputs" / f"{it['item_id']}.txt").read_text(encoding="utf-8")
        if got == want:
            same += 1
        else:
            diffs.append(it["item_id"])
    return {"byte_identical": same, "differing_items": diffs[:10]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bart-items", type=int, default=20)
    args = ap.parse_args()

    import torch  # noqa: PLC0415
    import transformers  # noqa: PLC0415

    out = {"torch": torch.__version__, "transformers": transformers.__version__,
           "bart_items": args.bart_items, "arms": {}}
    print(f"torch {torch.__version__}  transformers {transformers.__version__}")
    for rel, rev, kind in ARMS:
        cfg_path = EX / rel
        cfg = yaml.safe_load(cfg_path.read_text())
        params = dict(cfg["params"])
        adapter = _adapter((cfg_path.parent / cfg["adapter"]).resolve())
        run = _recorded_run(cfg["config_id"])
        items = json.loads((HARNESS / "data" / "datasets" /
                            f"{cfg['dataset_id']}.json").read_text())["items"]
        if kind == "bart":
            items = items[: args.bart_items]
        mat = HARNESS / "data" / "materialized" / cfg["dataset_id"]

        refused = _main_refused(params["model"], kind)
        params["revision"] = rev
        rec = {"model": params["model"], "revision": rev, "main": refused,
               "items_checked": len(items), "recorded_run": run.name}
        try:
            adapter.warmup(params)
            rec["loaded_dtype"] = str(next(adapter._PIPE.model.parameters()).dtype) \
                if getattr(adapter, "_PIPE", None) is not None else None
            rec.update(_compare(adapter, params, items, mat, run))
        except RuntimeError as e:
            # distilbart-cnn-6-6 is stored at fp16 and the pipeline keeps it there. torch
            # 2.14 has fp16 LayerNorm on CPU; torch 2.2.2 does not. Cast to fp32 and say so:
            # that is a different computation from the recorded run, not a reproduction.
            rec["error"] = f"{type(e).__name__}: {str(e).splitlines()[0][:160]}"
            pipe = adapter._local_pipeline(params)
            rec["loaded_dtype"] = str(next(pipe.model.parameters()).dtype)
            pipe.model.float()
            rec["fp32_cast"] = _compare(adapter, params, items, mat, run)
        out["arms"][cfg["config_id"]] = rec
        res = rec.get("fp32_cast", rec)
        print(f"{cfg['config_id']:28s} main: {refused[:40]!s:42s} {rev:11s} "
              f"{rec['loaded_dtype']}  {res['byte_identical']}/{len(items)} byte-identical"
              + ("  (only after an fp32 cast)" if "fp32_cast" in rec else ""))
    dest = Path(__file__).with_suffix(".json")
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
