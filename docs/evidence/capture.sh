#!/bin/bash
OUT="$(cd "$(dirname "$0")" && pwd)"
echo '{' > "$OUT/model_facts.json"
echo '  "captured_at": "2026-09-29", "source": "HuggingFace API /api/models/<id>",' >> "$OUT/model_facts.json"
echo '  "models": {' >> "$OUT/model_facts.json"
first=1
for r in deepseek-ai/DeepSeek-V4-Pro deepseek-ai/DeepSeek-V4.1-Flash deepseek-ai/DeepSeek-V4-Flash \
         google/gemma-4-31b-it google/gemma-4-26b-a4b-it google/gemma-3-27b-it \
         meta-llama/Llama-4-Maverick-17B-128E-Instruct meta-llama/Llama-3.3-70B-Instruct \
         meta-llama/Llama-4-Scout-17B-16E-Instruct mistralai/Mistral-Small-3.2-24B-Instruct-2506 \
         mistralai/Mistral-Large-3 zai-org/GLM-5 zai-org/GLM-4.6 zai-org/GLM-4.5-Air \
         facebook/bart-large-cnn facebook/bart-large-mnli BAAI/bge-small-en-v1.5 \
         intfloat/e5-base-v2 sentence-transformers/all-MiniLM-L6-v2 \
         sentence-transformers/all-mpnet-base-v2 urchade/gliner_medium-v2.1 \
         guishe/span-marker-generic-ner-v1-fewnerd-fine-super \
         mrm8488/bert-mini-finetuned-age_news-classification; do
  # ?blobs=true so the response carries every file's SIZE IN BYTES. Without it the only
  # size signal is `safetensors.parameters`, an ELEMENT count per dtype, and deriving
  # bytes from that assumes one byte per int8 element. For the three DeepSeek
  # checkpoints that assumption is wrong by up to 1.85x: they report 763B "I8" elements
  # but occupy 510 GB, because the tensors are packed at roughly 4 bits. Found by
  # external review.
  # RETRY, because ?blobs=true is heavier and gets rate-limited where the plain call
  # does not. The first version of this made one attempt and, on failure, wrote an
  # error record OVER a model whose licence and parameter counts had been captured
  # correctly for weeks -- a refresh that can silently degrade the evidence is worse
  # than no refresh. Nine of twenty-three models were lost that way in one run.
  j=""
  for attempt in 1 2 3 4 5; do
    j=$(curl -s -L --max-time 90 "https://huggingface.co/api/models/$r?blobs=true")
    printf '%s' "$j" | head -c 1 | grep -q '{' && break
    echo "    retry $attempt for $r" >&2
    sleep $((attempt * 5))
  done
  [ $first -eq 0 ] && echo ',' >> "$OUT/model_facts.json"
  first=0
  # printf, NOT echo: under /bin/sh echo interprets backslash escapes, which corrupts
  # any JSON containing them. That is why adding ?blobs=true appeared to "fail" for
  # nine models -- curl returned HTTP 200 and valid JSON every time, and echo mangled
  # the larger payloads on the way to python.
  printf '%s' "$j" | python3 -c "
import json,sys
# A FETCH THAT FAILS MUST STILL EMIT A RECORD. The first version of the blobs change
# crashed here on one un-fetchable repo and left model_facts.json truncated mid-object --
# an evidence file that no longer parses is worse than a stale one.
raw = sys.stdin.read()
try:
    d = json.loads(raw)
    if not isinstance(d, dict):
        raise ValueError('not an object')
except Exception as exc:
    print('    %s: %s' % (json.dumps('$r'),
          json.dumps({'exists': False, 'fetch_error': type(exc).__name__})), end='')
    raise SystemExit(0)
sv=d.get('safetensors') or {}
# MEASURED BYTES, and the shard shape they came from. A consolidated.safetensors is a
# second copy of the same weights that some repos (Mistral) ship alongside the shards,
# so it is reported separately rather than summed in -- counting both doubles the model.
sib=[x for x in (d.get('siblings') or []) if x.get('rfilename','').endswith('.safetensors')]
# WHICH FILES ARE THE MODEL, when a repo ships the same weights twice. Mistral-Small
# has model-00001-of-00010.safetensors AND a 48 GB consolidated.safetensors; summing
# both doubles it. But Mistral-Large-3's ONLY copy is 272 shards named
# consolidated-00001-of-00272.safetensors, so 'consolidated is the duplicate' is wrong
# there and would report the model as 0 bytes. The test is therefore whether a
# model-*/model.safetensors copy EXISTS: if it does, that is the copy and anything else
# is the spare; if it does not, whatever is there is the copy.
prim=[x for x in sib if x.get('rfilename','').startswith('model')]
shards = prim if prim else sib
dup    = [x for x in sib if x not in shards]
rec={'exists': not bool(d.get('error')),
     'safetensors_bytes': sum(x.get('size') or 0 for x in shards) or None,
     'safetensors_files': len(shards),
     'duplicate_copy_bytes': (sum(x.get('size') or 0 for x in dup) or None),
     'license': next((t[8:] for t in d.get('tags',[]) if t.startswith('license:')), None),
     'gated': d.get('gated'),
     'params_total': sv.get('total'),
     'params_by_dtype': sv.get('parameters'),
     'pipeline_tag': d.get('pipeline_tag'),
     'sha': d.get('sha')}
print('    %s: %s' % (json.dumps('$r'), json.dumps(rec)), end='')
" >> "$OUT/model_facts.json"
  sleep 1.5
done
echo '' >> "$OUT/model_facts.json"
echo '  }' >> "$OUT/model_facts.json"
echo '}' >> "$OUT/model_facts.json"
python3 -c "import json;d=json.load(open('$OUT/model_facts.json'));print('  captured %d models' % len(d['models']))"
