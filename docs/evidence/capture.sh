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
  j=$(curl -s -L --max-time 25 "https://huggingface.co/api/models/$r")
  [ $first -eq 0 ] && echo ',' >> "$OUT/model_facts.json"
  first=0
  echo "$j" | python3 -c "
import json,sys
d=json.load(sys.stdin)
sv=d.get('safetensors') or {}
rec={'exists': not bool(d.get('error')),
     'license': next((t[8:] for t in d.get('tags',[]) if t.startswith('license:')), None),
     'gated': d.get('gated'),
     'params_total': sv.get('total'),
     'params_by_dtype': sv.get('parameters'),
     'pipeline_tag': d.get('pipeline_tag'),
     'sha': d.get('sha')}
print('    %s: %s' % (json.dumps('$r'), json.dumps(rec)), end='')
" >> "$OUT/model_facts.json"
  sleep 0.2
done
echo '' >> "$OUT/model_facts.json"
echo '  }' >> "$OUT/model_facts.json"
echo '}' >> "$OUT/model_facts.json"
python3 -c "import json;d=json.load(open('$OUT/model_facts.json'));print('  captured %d models' % len(d['models']))"
