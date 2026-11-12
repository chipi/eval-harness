// The Workbench mockup's data, read from this project by its extractor (never invented).
window.MOCK = {
 "goal": {
  "goal_id": "news_summary_cnn",
  "title": "Short news summaries (CNN)",
  "statement": "Pick a model that writes a short summary of a CNN-style news article, at a known cost, for a reader who wants the story's main points.",
  "decision": "Which models can be told apart on summary quality, and what each costs per article.",
  "measure": "coverage",
  "direction": "higher",
  "strategy": "balanced"
 },
 "measures": [
  "concision",
  "correct",
  "coverage",
  "f1",
  "ndcg_10",
  "tau",
  "triage_cost"
 ],
 "goals": [
  "entities_few_nerd",
  "entity_topic_dbpedia",
  "news_summary_cnn",
  "news_topic_ag",
  "scientific_retrieval_scifact",
  "summary_judge_summeval",
  "triage_orrery"
 ],
 "datasets": [
  {
   "id": "ag_news_20",
   "items": 20
  },
  {
   "id": "ag_news_200",
   "items": 200
  },
  {
   "id": "cnn_dailymail_20",
   "items": 20
  },
  {
   "id": "cnn_dailymail_200",
   "items": 200
  },
  {
   "id": "cnn_dailymail_dm200",
   "items": 200
  },
  {
   "id": "dbpedia_280",
   "items": 280
  },
  {
   "id": "dbpedia_56",
   "items": 56
  },
  {
   "id": "few_nerd_280",
   "items": 280
  },
  {
   "id": "few_nerd_56",
   "items": 56
  },
  {
   "id": "fleet_dedup_v1",
   "items": 100
  },
  {
   "id": "orrery_triage_smoke",
   "items": 2
  },
  {
   "id": "orrery_triage_v1",
   "items": 233
  },
  {
   "id": "orrery_triage_v1_labelled",
   "items": 65
  },
  {
   "id": "orrery_triage_v1_labelled_v2",
   "items": 65
  },
  {
   "id": "scifact_200",
   "items": 200
  },
  {
   "id": "scifact_40",
   "items": 40
  },
  {
   "id": "smoke_v1",
   "items": 5
  },
  {
   "id": "summeval_100",
   "items": 100
  },
  {
   "id": "tiny_v1",
   "items": 2
  }
 ],
 "source": {
  "provider": "huggingface",
  "ref": "abisee/cnn_dailymail",
  "url": "https://huggingface.co/datasets/abisee/cnn_dailymail",
  "revision": "690bb95a2ac2c5a99d7bde63ac1401539ddd3967",
  "config": "1.0.0",
  "split": "test",
  "rows": 200,
  "licence": "Apache-2.0",
  "split_rows": 11490
 },
 "items": [
  {
   "id": "f001ec5c4704938247d27a44948eebb37ae98d01",
   "row": 0,
   "article": "(CNN)The Palestinian Authority officially became the 123rd member of the International Criminal Court on Wednesday, a step that gives the court jurisdiction over alleged crimes in Palestinian territories. The formal accession was marked with a ceremony at The Hague, in the Netherlands, where the court is based. The Palestinians signed the ICC's founding Rome Statute in January, when they also accepted its jurisdiction over alleged crimes committed \"in the occupied Palestinian territory, including East Jerusalem, since June 13, 2014.\" Later that month, the ICC opened a preliminary examination i",
   "highlights": "Membership gives the ICC jurisdiction over alleged crimes committed in Palestinian territories since last June . Israel and the United States opposed the move, which could open the door to war crimes investigations against Israelis ."
  },
  {
   "id": "230c522854991d053fe98a718b1defa077a8efef",
   "row": 1,
   "article": "(CNN)Never mind cats having nine lives. A stray pooch in Washington State has used up at least three of her own after being hit by a car, apparently whacked on the head with a hammer in a misguided mercy killing and then buried in a field -- only to survive. That's according to Washington State University, where the dog -- a friendly white-and-black bully breed mix now named Theia -- has been receiving care at the Veterinary Teaching Hospital. Four days after her apparent death, the dog managed to stagger to a nearby farm, dirt-covered and emaciated, where she was found by a worker who took he",
   "highlights": "Theia, a bully breed mix, was apparently hit by a car, whacked with a hammer and buried in a field . \"She's a true miracle dog and she deserves a good life,\" says Sara Mellado, who is looking for a home for Theia ."
  },
  {
   "id": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
   "row": 2,
   "article": "(CNN)If you've been following the news lately, there are certain things you doubtless know about Mohammad Javad Zarif. He is, of course, the Iranian foreign minister. He has been U.S. Secretary of State John Kerry's opposite number in securing a breakthrough in nuclear discussions that could lead to an end to sanctions against Iran -- if the details can be worked out in the coming weeks. And he received a hero's welcome as he arrived in Iran on a sunny Friday morning. \"Long live Zarif,\" crowds chanted as his car rolled slowly down the packed street. You may well have read that he is \"polished\"",
   "highlights": "Mohammad Javad Zarif has spent more time with John Kerry than any other foreign minister . He once participated in a takeover of the Iranian Consulate in San Francisco . The Iranian foreign minister tweets in English ."
  },
  {
   "id": "a38e72fed88684ec8d60dd5856282e999dc8c0ca",
   "row": 3,
   "article": "(CNN)Five Americans who were monitored for three weeks at an Omaha, Nebraska, hospital after being exposed to Ebola in West Africa have been released, a Nebraska Medicine spokesman said in an email Wednesday. One of the five had a heart-related issue on Saturday and has been discharged but hasn't left the area, Taylor Wilson wrote. The others have already gone home. They were exposed to Ebola in Sierra Leone in March, but none developed the deadly virus. They are clinicians for Partners in Health, a Boston-based aid group. They all had contact with a colleague who was diagnosed with the diseas",
   "highlights": "17 Americans were exposed to the Ebola virus while in Sierra Leone in March . Another person was diagnosed with the disease and taken to hospital in Maryland . National Institutes of Health says the patient is in fair condition after weeks of treatment ."
  }
 ],
 "profile": {
  "n": 200,
  "words": {
   "min": 102,
   "p25": 283,
   "median": 465,
   "p75": 774,
   "max": 1497
  },
  "reference": {
   "id": "gold/cnn_dailymail_200",
   "items": 200,
   "words": {
    "histogram": [
     [
      14,
      19,
      6
     ],
     [
      20,
      25,
      34
     ],
     [
      26,
      31,
      44
     ],
     [
      32,
      37,
      42
     ],
     [
      38,
      43,
      26
     ],
     [
      44,
      49,
      34
     ],
     [
      50,
      55,
      8
     ],
     [
      56,
      61,
      4
     ],
     [
      62,
      67,
      2
     ]
    ],
    "max": 67,
    "median": 34,
    "min": 14,
    "p25": 26,
    "p75": 43
   }
  },
  "items_sha256": "257feda902391b934b8cde940c15e91201096dbe96ec5a81337e9da007ce3ec7",
  "histogram": [
   [
    102,
    241,
    32
   ],
   [
    242,
    381,
    45
   ],
   [
    382,
    521,
    34
   ],
   [
    522,
    661,
    21
   ],
   [
    662,
    801,
    21
   ],
   [
    802,
    941,
    16
   ],
   [
    942,
    1081,
    16
   ],
   [
    1082,
    1221,
    7
   ],
   [
    1222,
    1361,
    5
   ],
   [
    1362,
    1501,
    3
   ]
  ]
 },
 "models": [
  {
   "id": "baai-bge-small-en-v1.5",
   "kind": "ml",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 1,
   "cnn_rank": null
  },
  {
   "id": "claude-haiku-5.5",
   "kind": "llm",
   "weights": "proprietary",
   "where": "self-hosted",
   "onboarding": "probed 2026-10-31",
   "arms": 10,
   "cnn_rank": null
  },
  {
   "id": "claude-sonnet-5.5",
   "kind": "llm",
   "weights": "proprietary",
   "where": "self-hosted",
   "onboarding": "probed 2026-10-31",
   "arms": 5,
   "cnn_rank": null
  },
  {
   "id": "deepseek-4.1-flash",
   "kind": "llm",
   "weights": "open",
   "where": "self-hosted",
   "onboarding": "pass 2026-10-31",
   "arms": 19,
   "cnn_rank": 2
  },
  {
   "id": "eval-claude-haiku",
   "kind": "llm",
   "weights": "proprietary",
   "where": "—",
   "onboarding": "none",
   "arms": 10,
   "cnn_rank": 14
  },
  {
   "id": "eval-claude-sonnet",
   "kind": "llm",
   "weights": "proprietary",
   "where": "—",
   "onboarding": "none",
   "arms": 10,
   "cnn_rank": 15
  },
  {
   "id": "eval-deepseek-flash",
   "kind": "llm",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 11,
   "cnn_rank": 9
  },
  {
   "id": "eval-deepseek-pro",
   "kind": "llm",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 10,
   "cnn_rank": 7
  },
  {
   "id": "eval-gemma-26b",
   "kind": "llm",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 11,
   "cnn_rank": 20
  },
  {
   "id": "eval-gemma-3-27b",
   "kind": "llm",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 11,
   "cnn_rank": 22
  },
  {
   "id": "eval-glm-45-air",
   "kind": "llm",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 13,
   "cnn_rank": 19
  },
  {
   "id": "eval-glm-46",
   "kind": "llm",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 11,
   "cnn_rank": 8
  },
  {
   "id": "eval-glm-5",
   "kind": "llm",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 10,
   "cnn_rank": 21
  },
  {
   "id": "eval-gpt-55",
   "kind": "llm",
   "weights": "proprietary",
   "where": "—",
   "onboarding": "none",
   "arms": 10,
   "cnn_rank": 11
  },
  {
   "id": "eval-gpt-6sol",
   "kind": "llm",
   "weights": "proprietary",
   "where": "—",
   "onboarding": "none",
   "arms": 10,
   "cnn_rank": 12
  },
  {
   "id": "eval-gpt-mini",
   "kind": "llm",
   "weights": "proprietary",
   "where": "—",
   "onboarding": "none",
   "arms": 10,
   "cnn_rank": 17
  },
  {
   "id": "eval-llama-70b",
   "kind": "llm",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 11,
   "cnn_rank": 4
  },
  {
   "id": "eval-llama-maverick",
   "kind": "llm",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 12,
   "cnn_rank": 3
  },
  {
   "id": "eval-llama-scout",
   "kind": "llm",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 12,
   "cnn_rank": 6
  },
  {
   "id": "eval-mistral-large",
   "kind": "llm",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 10,
   "cnn_rank": 24
  },
  {
   "id": "eval-mistral-medium",
   "kind": "llm",
   "weights": "proprietary",
   "where": "—",
   "onboarding": "none",
   "arms": 10,
   "cnn_rank": 26
  },
  {
   "id": "eval-mistral-small",
   "kind": "llm",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 11,
   "cnn_rank": 13
  },
  {
   "id": "eval-opus-5",
   "kind": "llm",
   "weights": "proprietary",
   "where": "—",
   "onboarding": "none",
   "arms": 10,
   "cnn_rank": 18
  },
  {
   "id": "eval-qwen-37max",
   "kind": "llm",
   "weights": "proprietary",
   "where": "—",
   "onboarding": "none",
   "arms": 1,
   "cnn_rank": null
  },
  {
   "id": "eval-qwen-37plus",
   "kind": "llm",
   "weights": "proprietary",
   "where": "—",
   "onboarding": "none",
   "arms": 10,
   "cnn_rank": 27
  },
  {
   "id": "eval-qwen-3max",
   "kind": "llm",
   "weights": "proprietary",
   "where": "—",
   "onboarding": "none",
   "arms": 9,
   "cnn_rank": 23
  },
  {
   "id": "eval-qwen-flash",
   "kind": "llm",
   "weights": "proprietary",
   "where": "—",
   "onboarding": "none",
   "arms": 16,
   "cnn_rank": 25
  },
  {
   "id": "fabriceyhc-bert-base-uncased-ag_news",
   "kind": "ml",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 3,
   "cnn_rank": null
  },
  {
   "id": "fabriceyhc-bert-base-uncased-dbpedia_14",
   "kind": "ml",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 2,
   "cnn_rank": null
  },
  {
   "id": "facebook-bart-large-cnn",
   "kind": "ml",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 10,
   "cnn_rank": 1
  },
  {
   "id": "facebook-bart-large-mnli",
   "kind": "ml",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 3,
   "cnn_rank": null
  },
  {
   "id": "facebook-bart-large-xsum",
   "kind": "ml",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 7,
   "cnn_rank": 29
  },
  {
   "id": "fleet-triage-pro",
   "kind": "llm",
   "weights": "—",
   "where": "self-hosted",
   "onboarding": "pass 2026-10-31",
   "arms": 17,
   "cnn_rank": null
  },
  {
   "id": "gemini-3.5-flash-lite",
   "kind": "llm",
   "weights": "proprietary",
   "where": "self-hosted",
   "onboarding": "probed 2026-10-31",
   "arms": 5,
   "cnn_rank": null
  },
  {
   "id": "gemini-4-argon",
   "kind": "llm",
   "weights": "proprietary",
   "where": "self-hosted",
   "onboarding": "probed 2026-10-31",
   "arms": 5,
   "cnn_rank": null
  },
  {
   "id": "gemma4-12b",
   "kind": "llm",
   "weights": "open",
   "where": "self-hosted",
   "onboarding": "probed 2026-10-31",
   "arms": 10,
   "cnn_rank": null
  },
  {
   "id": "gemma4-31b",
   "kind": "llm",
   "weights": "open",
   "where": "self-hosted",
   "onboarding": "pass 2026-10-31",
   "arms": 43,
   "cnn_rank": 16
  },
  {
   "id": "gpt-6-luna",
   "kind": "llm",
   "weights": "proprietary",
   "where": "self-hosted",
   "onboarding": "pass 2026-10-31",
   "arms": 11,
   "cnn_rank": null
  },
  {
   "id": "gpt-6.1-sol",
   "kind": "llm",
   "weights": "proprietary",
   "where": "self-hosted",
   "onboarding": "probed 2026-10-31",
   "arms": 10,
   "cnn_rank": null
  },
  {
   "id": "gpt-oss-120b",
   "kind": "llm",
   "weights": "open",
   "where": "self-hosted",
   "onboarding": "pass 2026-10-31",
   "arms": 14,
   "cnn_rank": null
  },
  {
   "id": "gpt-oss-20b",
   "kind": "llm",
   "weights": "open",
   "where": "self-hosted",
   "onboarding": "probed 2026-10-31",
   "arms": 21,
   "cnn_rank": null
  },
  {
   "id": "guishe-span-marker-generic-ner-v1-fewnerd-fine-super",
   "kind": "ml",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 1,
   "cnn_rank": null
  },
  {
   "id": "intfloat-e5-base-v2",
   "kind": "ml",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 1,
   "cnn_rank": null
  },
  {
   "id": "kimi-k3.1-pro",
   "kind": "llm",
   "weights": "—",
   "where": "self-hosted",
   "onboarding": "pass 2026-10-31",
   "arms": 7,
   "cnn_rank": null
  },
  {
   "id": "llama3.1-8b",
   "kind": "llm",
   "weights": "open",
   "where": "self-hosted",
   "onboarding": "probed 2026-10-31",
   "arms": 15,
   "cnn_rank": null
  },
  {
   "id": "llama4-scout",
   "kind": "llm",
   "weights": "open",
   "where": "self-hosted",
   "onboarding": "probed 2026-10-31",
   "arms": 5,
   "cnn_rank": null
  },
  {
   "id": "mingzhong-unieval-sum",
   "kind": "ml",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 2,
   "cnn_rank": null
  },
  {
   "id": "ministral-3-14b",
   "kind": "llm",
   "weights": "open",
   "where": "self-hosted",
   "onboarding": "check 2026-10-31",
   "arms": 15,
   "cnn_rank": null
  },
  {
   "id": "mistral-large-4",
   "kind": "llm",
   "weights": "—",
   "where": "self-hosted",
   "onboarding": "pass 2026-10-31",
   "arms": 7,
   "cnn_rank": null
  },
  {
   "id": "mistral-medium-3.5",
   "kind": "llm",
   "weights": "open",
   "where": "self-hosted",
   "onboarding": "probed 2026-10-31",
   "arms": 10,
   "cnn_rank": null
  },
  {
   "id": "mrm8488-bert-mini-finetuned-age_news-classification",
   "kind": "ml",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 3,
   "cnn_rank": null
  },
  {
   "id": "nemotron-3.5-bolt-e4b",
   "kind": "llm",
   "weights": "open",
   "where": "self-hosted",
   "onboarding": "pass 2026-10-31",
   "arms": 25,
   "cnn_rank": null
  },
  {
   "id": "nemotron-3.5-lightning-30b",
   "kind": "llm",
   "weights": "open",
   "where": "self-hosted",
   "onboarding": "pass 2026-10-31",
   "arms": 21,
   "cnn_rank": null
  },
  {
   "id": "nemotron-3.5-super-120b",
   "kind": "llm",
   "weights": "open",
   "where": "self-hosted",
   "onboarding": "none",
   "arms": 7,
   "cnn_rank": null
  },
  {
   "id": "phi4-14b",
   "kind": "llm",
   "weights": "open",
   "where": "self-hosted",
   "onboarding": "probed 2026-10-31",
   "arms": 15,
   "cnn_rank": null
  },
  {
   "id": "qwen3-30b-a3b",
   "kind": "llm",
   "weights": "open",
   "where": "self-hosted",
   "onboarding": "probed 2026-10-31",
   "arms": 25,
   "cnn_rank": null
  },
  {
   "id": "qwen3.5-122b",
   "kind": "llm",
   "weights": "open",
   "where": "self-hosted",
   "onboarding": "pass 2026-10-31",
   "arms": 14,
   "cnn_rank": null
  },
  {
   "id": "qwen3.8-27b",
   "kind": "llm",
   "weights": "open",
   "where": "self-hosted",
   "onboarding": "pass 2026-10-31",
   "arms": 21,
   "cnn_rank": null
  },
  {
   "id": "sentence-transformers-all-minilm-l6-v2",
   "kind": "ml",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 1,
   "cnn_rank": null
  },
  {
   "id": "sentence-transformers-all-mpnet-base-v2",
   "kind": "ml",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 1,
   "cnn_rank": null
  },
  {
   "id": "sshleifer-distilbart-cnn-12-6",
   "kind": "ml",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 7,
   "cnn_rank": 5
  },
  {
   "id": "sshleifer-distilbart-cnn-6-6",
   "kind": "ml",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 8,
   "cnn_rank": 10
  },
  {
   "id": "textattack-bert-base-uncased-ag-news",
   "kind": "ml",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 3,
   "cnn_rank": null
  },
  {
   "id": "urchade-gliner_medium-v2.1",
   "kind": "ml",
   "weights": "open",
   "where": "—",
   "onboarding": "none",
   "arms": 1,
   "cnn_rank": null
  }
 ],
 "prompt": "Summarise this news article in 2-3 short sentences, in the terse style of a news wire summary. Output only the summary.",
 "arms": [
  {
   "config_id": "cnn_bart_l_n200_v1",
   "arm": "bart_l",
   "rank": 1,
   "coverage": 0.346,
   "rouge1": 0.3477,
   "delta": null,
   "p": null,
   "verdict": null,
   "baseline": true,
   "recommended": true,
   "usd_per_item": 0.0,
   "p50_ms": 10724.0,
   "total_usd": 0.0,
   "model": "facebook/bart-large-cnn",
   "family": "bart",
   "tier": "free",
   "temperature": null,
   "max_tokens": null,
   "prompt_file": null,
   "provider": "hf_local",
   "run_id": "cnn_bart_l_n200_v1_20260926T153757Z",
   "created_at": "2026-09-26T16:14:46Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority becomes the 123rd member of the International Criminal Court. The move gives the court jurisdiction over alleged crimes in Palestinian territories. Israel and the United States opposed the Palestinians' efforts to join the body. But Palestinian Foreign Minister Riad al-Malki said it was a move toward greater justice.",
     "coverage": 0.5294117647,
     "cost_usd": 0.0,
     "latency_ms": 9911.015
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "Theia, a one-year-old bully breed mix, was hit by a car and buried in a field. She managed to stagger to a nearby farm, dirt-covered and emaciated. She suffered a dislocated jaw, leg injuries and a caved-in sinus cavity.",
     "coverage": 0.4418604651,
     "cost_usd": 0.0,
     "latency_ms": 12527.579
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Mohammad Javad Zarif is the Iranian foreign minister. He has been John Kerry's opposite number in securing a breakthrough in nuclear discussions. He received a hero's welcome as he arrived in Iran on a sunny Friday morning. But there are some facts about Zarif that are less well-known.",
     "coverage": 0.4285714286,
     "cost_usd": 0.0,
     "latency_ms": 11023.886
    }
   ]
  },
  {
   "config_id": "cnn_deepseek_m_n200_v1",
   "arm": "deepseek_m",
   "rank": 2,
   "coverage": 0.346,
   "rouge1": 0.3612,
   "delta": -0.0,
   "p": "0.9923",
   "verdict": "not significant",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.000191,
   "p50_ms": 1497.0,
   "total_usd": 0.03810836,
   "model": "eval-deepseek-41flash",
   "family": "deepseek",
   "tier": "mid",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_deepseek_m_n200_v1_20260925T233650Z",
   "created_at": "2026-09-25T23:42:13Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority became the 123rd member of the International Criminal Court on Wednesday, giving the court jurisdiction over alleged crimes in Palestinian territories. The ICC opened a preliminary examination in January into possible war crimes, including against Israelis, though Palestinians may face counter-charges. Israel and the US, neither of which is an ICC member, opposed the move.",
     "coverage": 0.4705882353,
     "cost_usd": 0.0003054,
     "latency_ms": 1986.14
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A stray dog in Washington State survived being hit by a car, struck in the head with a hammer and buried in a field, then staggered to a nearby farm four days later. The one-year-old bully breed mix, now named Theia, is receiving care at Washington State University's veterinary hospital for a dislocated jaw, leg injuries and a caved-in sinus cavity. A fundraising page for her treatment has surpassed its $10,000 targe",
     "coverage": 0.4418604651,
     "cost_usd": 0.000255075,
     "latency_ms": 1395.66
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif, a key figure in nuclear talks with the U.S., received a hero's welcome upon returning to Iran. Lesser-known facts about Zarif include his 2013 Rosh Hashanah tweet disavowing Holocaust denial, his education and family ties in the U.S., and his involvement in the 1979 takeover of the Iranian Consulate in San Francisco.",
     "coverage": 0.2857142857,
     "cost_usd": 0.00036138,
     "latency_ms": 1405.212
    }
   ]
  },
  {
   "config_id": "cnn_llama_l_n200_v1",
   "arm": "llama_l",
   "rank": 3,
   "coverage": 0.339,
   "rouge1": 0.3636,
   "delta": -0.007,
   "p": "0.4015",
   "verdict": "not significant",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.000195,
   "p50_ms": 3646.0,
   "total_usd": 0.03891013,
   "model": "eval-llama-maverick",
   "family": "llama",
   "tier": "large",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_llama_l_n200_v1_20260926T000443Z",
   "created_at": "2026-09-26T00:16:21Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "Palestinian Authority becomes 123rd member of International Criminal Court, granting jurisdiction over alleged crimes in Palestinian territories since 2014. Israel and US opposed move, warning it could hinder peace talks. ICC may investigate war crimes on both sides, including those committed during last summer's Gaza conflict.",
     "coverage": 0.4705882353,
     "cost_usd": 0.00017781,
     "latency_ms": 3700.683
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A stray dog in Washington State survived being hit by a car, beaten with a hammer, and buried, before being found and taken to a vet for treatment. The dog, named Theia, is undergoing care for multiple injuries at a veterinary hospital. A fundraising campaign has raised over $10,000 to support her medical treatment.",
     "coverage": 0.4186046512,
     "cost_usd": 0.0001453425,
     "latency_ms": 4457.239
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif has played a key role in nuclear talks with US Secretary of State John Kerry. Zarif, who has been described as \"polished\" and \"jovial\", has a lesser-known history that includes education in the US and involvement in the Iranian Revolution. He has spent more time with Kerry than any other foreign minister.",
     "coverage": 0.4,
     "cost_usd": 0.000226875,
     "latency_ms": 4857.237
    }
   ]
  },
  {
   "config_id": "cnn_llama_m_n200_v1",
   "arm": "llama_m",
   "rank": 4,
   "coverage": 0.338,
   "rouge1": 0.3477,
   "delta": -0.008,
   "p": "0.4170",
   "verdict": "not significant",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.000165,
   "p50_ms": 2682.0,
   "total_usd": 0.03296087,
   "model": "eval-llama-70b",
   "family": "llama",
   "tier": "mid",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_llama_m_n200_v1_20260925T235110Z",
   "created_at": "2026-09-26T00:04:43Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority has officially joined the International Criminal Court, giving the court jurisdiction over alleged crimes in Palestinian territories. The move, opposed by Israel and the US, paves the way for possible war crimes investigations against Israelis and Palestinians. The ICC will review evidence and determine whether to investigate suspects on both sides.",
     "coverage": 0.5,
     "cost_usd": 9.384e-05,
     "latency_ms": 2432.186
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A stray dog in Washington State has survived being hit by a car, bludgeoned with a hammer, and buried alive. The dog, named Theia, was found four days later and is receiving care at a veterinary hospital for injuries including a dislocated jaw and leg injuries. Donors have raised over $10,000 to cover her medical expenses.",
     "coverage": 0.3953488372,
     "cost_usd": 7.714e-05,
     "latency_ms": 14014.146
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif, key to nuclear talks with US, has received a hero's welcome in Iran. Less well-known facts about Zarif include his education in the US and past involvement in protests at Iranian diplomatic missions. Zarif is set to continue negotiations with US Secretary of State John Kerry to meet a June 30 deadline for a nuclear agreement.",
     "coverage": 0.3714285714,
     "cost_usd": 0.00024568,
     "latency_ms": 5473.799
    }
   ]
  },
  {
   "config_id": "cnn_bart_m_n200_v1",
   "arm": "bart_m",
   "rank": 5,
   "coverage": 0.337,
   "rouge1": 0.3457,
   "delta": -0.009,
   "p": "0.1607",
   "verdict": "not significant",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.0,
   "p50_ms": 4649.0,
   "total_usd": 0.0,
   "model": "sshleifer/distilbart-cnn-12-6",
   "family": "bart",
   "tier": "free",
   "temperature": null,
   "max_tokens": null,
   "prompt_file": null,
   "provider": "hf_local",
   "run_id": "cnn_bart_m_n200_v1_20260930T083949Z",
   "created_at": "2026-09-30T08:57:12Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority becomes the 123rd member of the International Criminal Court . The move gives the court jurisdiction over alleged crimes in Palestinian territories . Israel and the United States opposed the Palestinians' efforts to join the court . Rights group Human Rights Watch welcomed the move, saying it was a step toward justice .",
     "coverage": 0.5588235294,
     "cost_usd": 0.0,
     "latency_ms": 4583.812
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "Theia is a one-year-old bully breed mix who was hit by a car and buried in a field . She was found by a worker who took her to a vet for help . She suffered a dislocated jaw, leg injuries and a caved-in sinus cavity . A fundraising page has raised enough money to pay for her treatment .",
     "coverage": 0.5348837209,
     "cost_usd": 0.0,
     "latency_ms": 4422.998
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Mohammad Javad Zarif is the Iranian foreign minister . He has helped secure a breakthrough in nuclear talks that could lead to an end to sanctions against Iran . Zarif received a hero's welcome as he arrived in Iran on a sunny Friday morning . But there are some facts about Zarif that are less well-known .",
     "coverage": 0.3428571429,
     "cost_usd": 0.0,
     "latency_ms": 5340.206
    }
   ]
  },
  {
   "config_id": "cnn_llama_s_n200_v1",
   "arm": "llama_s",
   "rank": 6,
   "coverage": 0.333,
   "rouge1": 0.3526,
   "delta": -0.013,
   "p": "0.1591",
   "verdict": "not significant",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.000111,
   "p50_ms": 2204.0,
   "total_usd": 0.02218123,
   "model": "eval-llama-scout",
   "family": "llama",
   "tier": "small",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_llama_s_n200_v1_20260926T071608Z",
   "created_at": "2026-09-26T07:24:08Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority has officially become the 123rd member of the International Criminal Court, giving the court jurisdiction over alleged crimes in Palestinian territories. The move was opposed by Israel and the US, which do not recognize Palestine as a state. The ICC will now begin a preliminary examination of alleged war crimes committed in Palestinian territories since June 2014.",
     "coverage": 0.4411764706,
     "cost_usd": 9.53e-05,
     "latency_ms": 1474.508
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A stray dog in Washington State was hit by a car, apparently killed with a hammer, and buried, but miraculously survived and was found days later. The dog, now named Theia, is receiving treatment at a veterinary hospital and has raised over $10,000 in donations to cover her care. Despite her ordeal, Theia is described as gentle and loving, and is expected to make a full recovery with further surgery and care.",
     "coverage": 0.3720930233,
     "cost_usd": 8.12e-05,
     "latency_ms": 2119.779
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif received a hero's welcome in Tehran after nuclear talks with US Secretary of State John Kerry. Zarif, 54-56, has a background in international relations and spent time in the US, where he earned degrees and had children. He has played a key role in Iran's re-entry into the international community and will continue talks with Kerry to finalize a nuclear agreement.",
     "coverage": 0.4571428571,
     "cost_usd": 0.00022038,
     "latency_ms": 3726.639
    }
   ]
  },
  {
   "config_id": "cnn_deepseek_l_n200_v1",
   "arm": "deepseek_l",
   "rank": 7,
   "coverage": 0.332,
   "rouge1": 0.3547,
   "delta": -0.014,
   "p": "0.1248",
   "verdict": "not significant",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.000694,
   "p50_ms": 2354.0,
   "total_usd": 0.13889572,
   "model": "eval-deepseek-pro",
   "family": "deepseek",
   "tier": "large",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_deepseek_l_n200_v1_20260925T234213Z",
   "created_at": "2026-09-25T23:51:10Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority joined the ICC as its 123rd member, granting the court jurisdiction over alleged crimes in Palestinian territories since June 2014. The ICC has opened a preliminary examination that could lead to war crimes investigations against Israelis and Palestinians. Israel and the United States, non-members, opposed the move.",
     "coverage": 0.5294117647,
     "cost_usd": 0.000893664,
     "latency_ms": 2012.427
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A Washington state stray dog survived being hit by a car, struck with a hammer, and buried for four days before staggering to a nearby farm. The one-year-old bully breed mix, now named Theia, is receiving veterinary care for severe injuries including a dislocated jaw and caved-in sinus cavity. A fundraiser for her treatment has surpassed its goal, with excess funds to be donated to help other animals.",
     "coverage": 0.4186046512,
     "cost_usd": 0.0010635717,
     "latency_ms": 3319.059
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif, hailed for his role in nuclear talks, has a complex background including US education, disputed birth year, and past federal investigation. He previously engaged in revolutionary-era consulate takeovers and has spent more time with John Kerry than any other foreign minister.",
     "coverage": 0.4,
     "cost_usd": 0.0005069662,
     "latency_ms": 1966.99
    }
   ]
  },
  {
   "config_id": "cnn_glm_m_n200_v1",
   "arm": "glm_m",
   "rank": 8,
   "coverage": 0.332,
   "rouge1": 0.3517,
   "delta": -0.014,
   "p": "0.1152",
   "verdict": "not significant",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.000497,
   "p50_ms": 1848.0,
   "total_usd": 0.09947665,
   "model": "eval-glm-46",
   "family": "glm",
   "tier": "mid",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_glm_m_n200_v1_20260926T101254Z",
   "created_at": "2026-09-26T10:23:44Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority became the 123rd member of the International Criminal Court, granting the body jurisdiction over alleged crimes in Palestinian territories. The move, opposed by Israel and the U.S., paves the way for possible war crimes investigations and subjects Palestinians to potential counter-charges. The ICC had already opened a preliminary examination into the situation.",
     "coverage": 0.4117647059,
     "cost_usd": 0.0005055,
     "latency_ms": 1843.771
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A Washington State dog survived being hit by a car, struck with a hammer, and buried alive, later staggering to a farm for help. The one-year-old bully mix, named Theia, is recovering from severe injuries with support from a foster owner and public donations. The case echoes a similar survival story of a cat in Florida.",
     "coverage": 0.3953488372,
     "cost_usd": 0.0003512,
     "latency_ms": 2398.103
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif, a key negotiator in the nuclear talks, has a lesser-known past including U.S. education and a federal investigation. Despite a hero's welcome at home, his biography contains conflicting details about his age. Zarif continues to work closely with U.S. Secretary of State John Kerry to finalize the agreement by a June 30 deadline.",
     "coverage": 0.2571428571,
     "cost_usd": 0.0006285,
     "latency_ms": 2520.128
    }
   ]
  },
  {
   "config_id": "cnn_deepseek_s_n200_v1",
   "arm": "deepseek_s",
   "rank": 9,
   "coverage": 0.328,
   "rouge1": 0.3504,
   "delta": -0.018,
   "p": "0.0460",
   "verdict": "not significant",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 6.9e-05,
   "p50_ms": 2237.0,
   "total_usd": 0.01372885,
   "model": "eval-deepseek-flash",
   "family": "deepseek",
   "tier": "small",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_deepseek_s_n200_v1_20260925T232736Z",
   "created_at": "2026-09-25T23:36:50Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority became the 123rd member of the International Criminal Court (ICC) on Wednesday, granting the court jurisdiction over alleged crimes in Palestinian territories. The move, opposed by Israel and the US, opens the door to potential war crimes investigations against both Israelis and Palestinians.",
     "coverage": 0.4705882353,
     "cost_usd": 9.358e-05,
     "latency_ms": 1141.449
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A one-year-old stray dog in Washington State survived being hit by a car, struck on the head with a hammer in an apparent mercy killing, and buried for four days before staggering to a farm. Named Theia, she is now receiving veterinary care for severe injuries including a dislocated jaw and caved-in sinus cavity. Donors have exceeded a $10,000 fundraising goal for her treatment.",
     "coverage": 0.3953488372,
     "cost_usd": 3.26893e-05,
     "latency_ms": 1530.437
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif, key in nuclear talks with the U.S., has a lesser-known past including U.S. education, a disputed birth year, and a federal probe. He once tweeted Rosh Hashanah greetings and denied Iran's Holocaust denial.",
     "coverage": 0.3428571429,
     "cost_usd": 9.5914e-05,
     "latency_ms": 2534.149
    }
   ]
  },
  {
   "config_id": "cnn_bart_s_n200_v1",
   "arm": "bart_s",
   "rank": 10,
   "coverage": 0.328,
   "rouge1": 0.3418,
   "delta": -0.019,
   "p": "0.0158",
   "verdict": "not significant",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.0,
   "p50_ms": 3683.0,
   "total_usd": 0.0,
   "model": "sshleifer/distilbart-cnn-6-6",
   "family": "bart",
   "tier": "free",
   "temperature": null,
   "max_tokens": null,
   "prompt_file": null,
   "provider": "hf_local",
   "run_id": "cnn_bart_s_n200_v1_20260930T091438Z",
   "created_at": "2026-09-30T09:29:44Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority officially becomes the 123rd member of the International Criminal Court . The move gives the court jurisdiction over alleged crimes in Palestinian territories . Israel and the United States, neither of which is an ICC member, opposed the Palestinians' efforts to join the body . The United States says it \"strongly\" disagreed with the court",
     "coverage": 0.5294117647,
     "cost_usd": 0.0,
     "latency_ms": 3935.705
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "Theia, a white-and-black bully breed mix, was hit by a car and buried in a field in Washington State . She was found by a worker who took her to a vet for help . She suffered a dislocated jaw, leg injuries and a caved-in sinus cavity .",
     "coverage": 0.5348837209,
     "cost_usd": 0.0,
     "latency_ms": 3398.35
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Mohammad Javad Zarif has been U.S. Secretary of State John Kerry's opposite number in securing a breakthrough in nuclear discussions . He has gone a long way to bring Iran in from the cold and allow it to rejoin the international community . But there are some facts about Zarif that are less well-known .",
     "coverage": 0.3428571429,
     "cost_usd": 0.0,
     "latency_ms": 4177.524
    }
   ]
  },
  {
   "config_id": "cnn_openai_m_n200_v1",
   "arm": "openai_m",
   "rank": 11,
   "coverage": 0.327,
   "rouge1": 0.3599,
   "delta": -0.019,
   "p": "0.0390",
   "verdict": "not significant",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.005358,
   "p50_ms": 1719.0,
   "total_usd": 1.07168,
   "model": "eval-gpt-55",
   "family": "openai",
   "tier": "mid",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_openai_m_n200_v1_20260926T065459Z",
   "created_at": "2026-09-26T07:00:52Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority formally joined the International Criminal Court, giving it jurisdiction over alleged crimes in Palestinian territories since June 2014. Israel and the United States opposed the move, while Palestinians and rights groups hailed it as a step toward justice.",
     "coverage": 0.5588235294,
     "cost_usd": 0.00522,
     "latency_ms": 1682.972
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A stray dog in Washington state survived being hit by a car, apparently struck with a hammer and buried, later staggering to a farm four days later. Theia, now in veterinary care, needs surgery for jaw, leg and sinus injuries, with donors surpassing a $10,000 fundraising goal.",
     "coverage": 0.3488372093,
     "cost_usd": 0.004565,
     "latency_ms": 1564.715
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif has become a prominent figure in nuclear talks with the U.S., drawing praise at home after a breakthrough framework. Less-known details include his U.S. education, past revolutionary activism, disputed birth date, and a previously alleged but unsettled link to a foundation accused of evading sanctions.",
     "coverage": 0.2857142857,
     "cost_usd": 0.006785,
     "latency_ms": 1922.259
    }
   ]
  },
  {
   "config_id": "cnn_openai_l_n200_v1",
   "arm": "openai_l",
   "rank": 12,
   "coverage": 0.327,
   "rouge1": 0.362,
   "delta": -0.019,
   "p": "0.0382",
   "verdict": "not significant",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.002181,
   "p50_ms": 1735.0,
   "total_usd": 0.43618,
   "model": "eval-gpt-6sol",
   "family": "openai",
   "tier": "large",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_openai_l_n200_v1_20260926T001621Z",
   "created_at": "2026-09-26T00:22:20Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority became the 123rd member of the International Criminal Court, giving it jurisdiction over alleged crimes in Palestinian territories since June 2014. The court has opened a preliminary examination that could lead to investigations of suspects on both sides. Israel and the United States opposed the move.",
     "coverage": 0.5,
     "cost_usd": 0.002086,
     "latency_ms": 1769.372
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A stray dog in Washington state survived being hit by a car, reportedly struck with a hammer and buried, then reached a farm four days later. The dog, now named Theia, is receiving veterinary care for serious injuries; donations have surpassed $10,000 to help pay for treatment.",
     "coverage": 0.3488372093,
     "cost_usd": 0.001678,
     "latency_ms": 1473.4
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif received a hero’s welcome after helping secure a framework nuclear deal that could lead to sanctions relief. Educated in the United States, he has worked closely with U.S. Secretary of State John Kerry; negotiators now face a June 30 deadline to settle the details.",
     "coverage": 0.3714285714,
     "cost_usd": 0.002544,
     "latency_ms": 2587.612
    }
   ]
  },
  {
   "config_id": "cnn_mistral_s_n200_v1",
   "arm": "mistral_s",
   "rank": 13,
   "coverage": 0.326,
   "rouge1": 0.3285,
   "delta": -0.021,
   "p": "0.0301",
   "verdict": "not significant",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 8.9e-05,
   "p50_ms": 2573.0,
   "total_usd": 0.01787276,
   "model": "eval-mistral-small",
   "family": "mistral",
   "tier": "small",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_mistral_s_n200_v1_20260926T111901Z",
   "created_at": "2026-09-26T11:28:29Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority became the 123rd member of the International Criminal Court, granting it jurisdiction over alleged crimes in Palestinian territories. The move, opposed by Israel and the U.S., could lead to war crimes investigations against both sides. The ICC's preliminary examination, opened in January, will review evidence dating back to June 2014.",
     "coverage": 0.5588235294,
     "cost_usd": 8.91563e-05,
     "latency_ms": 2433.272
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A stray dog in Washington State, named Theia, survived being hit by a car, struck with a hammer, and buried before digging herself out and seeking help. She suffered severe injuries but is recovering with the aid of a Good Samaritan Fund and a fundraising campaign. Donors have already exceeded $10,000 to cover her medical costs.",
     "coverage": 0.3720930233,
     "cost_usd": 6.95937e-05,
     "latency_ms": 2669.337
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif, a key figure in nuclear talks with the U.S., received a hero's welcome upon returning home. Less known details include his U.S. education, past ties to the Alavi Foundation, and early role in the Iranian Revolution. He and U.S. Secretary Kerry aim to finalize a nuclear deal by June 30.",
     "coverage": 0.3142857143,
     "cost_usd": 0.0001102813,
     "latency_ms": 3980.169
    }
   ]
  },
  {
   "config_id": "cnn_anthropic_s_n200_v1",
   "arm": "anthropic_s",
   "rank": 14,
   "coverage": 0.324,
   "rouge1": 0.3259,
   "delta": -0.022,
   "p": "0.0138",
   "verdict": "not significant",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.001305,
   "p50_ms": 1982.0,
   "total_usd": 0.261061,
   "model": "eval-claude-haiku",
   "family": "anthropic",
   "tier": "small",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_anthropic_s_n200_v1_20260926T064810Z",
   "created_at": "2026-09-26T06:54:59Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority became the 123rd member of the International Criminal Court on Wednesday, granting the court jurisdiction over alleged crimes in Palestinian territories since June 2014. The move, opposed by Israel and the United States, opens the door for possible war crimes investigations against Israelis, though Palestinians may also face counter-charges. The ICC's preliminary examination will review evid",
     "coverage": 0.5,
     "cost_usd": 0.001221,
     "latency_ms": 1863.712
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A stray dog in Washington State survived being hit by a car, struck with a hammer in an attempted mercy killing, and buried in a field, only to stumble to a nearby farm four days later. The one-year-old bully breed mix, now named Theia, is receiving treatment at Washington State University's Veterinary Teaching Hospital for a dislocated jaw, leg injuries, and sinus damage. Her rescuer has launched a fundraising campa",
     "coverage": 0.4418604651,
     "cost_usd": 0.001167,
     "latency_ms": 2215.203
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif, who has been negotiating a nuclear deal with U.S. Secretary of State John Kerry, received a hero's welcome upon returning to Iran. Despite his polished public image, less-known facts about Zarif include discrepancies in his official birth year, his education in the United States during Iran's revolution, and his involvement with the Alavi Foundation under federal investi",
     "coverage": 0.3142857143,
     "cost_usd": 0.001629,
     "latency_ms": 2119.244
    }
   ]
  },
  {
   "config_id": "cnn_anthropic_m_n200_v1",
   "arm": "anthropic_m",
   "rank": 15,
   "coverage": 0.324,
   "rouge1": 0.3347,
   "delta": -0.023,
   "p": "0.0095",
   "verdict": "not significant",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.003739,
   "p50_ms": 2992.0,
   "total_usd": 0.747834,
   "model": "eval-claude-sonnet",
   "family": "anthropic",
   "tier": "mid",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_anthropic_m_n200_v1_20260926T002220Z",
   "created_at": "2026-09-26T00:32:31Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority formally joined the International Criminal Court on Wednesday, becoming its 123rd member and giving the court jurisdiction over alleged crimes in Palestinian territories. The move follows a preliminary ICC examination opened in January into possible war crimes, which Israel and the United States have strongly opposed, arguing Palestine is not a state eligible for membership. Rights groups we",
     "coverage": 0.4411764706,
     "cost_usd": 0.00385,
     "latency_ms": 2851.093
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A stray dog named Theia survived being hit by a car, hit with a hammer, and buried, before staggering to a nearby farm four days later. She is now recovering at Washington State University's veterinary hospital, with fundraising efforts surpassing $10,000 to cover her medical treatment.",
     "coverage": 0.3488372093,
     "cost_usd": 0.00257,
     "latency_ms": 2261.801
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif, key negotiator in the Iran nuclear talks with US Secretary of State John Kerry, is known publicly as polished and jovial, but lesser-known facts reveal a more complex history. These include his education in the US during Iran's 1979 revolution, conflicting birth years listed by his own ministry, past investigation over an Iranian charity accused of laundering money, and ",
     "coverage": 0.3142857143,
     "cost_usd": 0.004824,
     "latency_ms": 3738.659
    }
   ]
  },
  {
   "config_id": "cnn_gemma_l_n200_v1",
   "arm": "gemma_l",
   "rank": 16,
   "coverage": 0.32,
   "rouge1": 0.3511,
   "delta": -0.026,
   "p": "0.0049",
   "verdict": "not significant",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.000119,
   "p50_ms": 1817.0,
   "total_usd": 0.02370875,
   "model": "eval-gemma-31b",
   "family": "gemma",
   "tier": "large",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_gemma_l_n200_v1_20260926T072408Z",
   "created_at": "2026-09-26T07:32:50Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority officially joined the International Criminal Court Wednesday as its 123rd member. The move grants the court jurisdiction to investigate alleged war crimes in Palestinian territories, including East Jerusalem. Israel and the United States opposed the accession, arguing it is counterproductive to peace.",
     "coverage": 0.5,
     "cost_usd": 9.404e-05,
     "latency_ms": 1132.78
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A one-year-old dog in Washington State survived being hit by a car, struck with a hammer, and buried alive. The dog, named Theia, is receiving extensive veterinary care for jaw and sinus injuries funded by public donations.",
     "coverage": 0.3255813953,
     "cost_usd": 0.00046675,
     "latency_ms": 533.989
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif is leading nuclear negotiations with U.S. Secretary of State John Kerry to end sanctions. Zarif is a U.S.-educated diplomat with a complex history, including early revolutionary activism and past U.S. federal investigations. The two officials are working toward a June 30 deadline to finalize a nuclear agreement.",
     "coverage": 0.3142857143,
     "cost_usd": 0.00015384,
     "latency_ms": 3762.203
    }
   ]
  },
  {
   "config_id": "cnn_openai_s_n200_v1",
   "arm": "openai_s",
   "rank": 17,
   "coverage": 0.317,
   "rouge1": 0.3506,
   "delta": -0.029,
   "p": "0.0020",
   "verdict": "significant: worse",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.000836,
   "p50_ms": 1238.0,
   "total_usd": 0.1672275,
   "model": "eval-gpt-mini",
   "family": "openai",
   "tier": "small",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_openai_s_n200_v1_20260926T070053Z",
   "created_at": "2026-09-26T07:05:11Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority formally joined the International Criminal Court as its 123rd member, giving the court jurisdiction over alleged crimes in Palestinian territories since June 13, 2014. Israel and the United States opposed the move, while Palestinians and rights groups said it could advance accountability and justice.",
     "coverage": 0.5882352941,
     "cost_usd": 0.000828,
     "latency_ms": 1096.901
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A stray dog in Washington state survived being hit by a car, struck on the head and buried alive before staggering to a nearby farm four days later, according to Washington State University. Now named Theia, the one-year-old dog is being treated for severe injuries, while a fundraising campaign for her care has topped $10,000.",
     "coverage": 0.2790697674,
     "cost_usd": 0.00071625,
     "latency_ms": 1171.893
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif, praised for helping secure a nuclear breakthrough with the U.S., is a U.S.-educated diplomat with a less familiar past. The article notes his long American stay, disputed birth year, and earlier revolutionary activism, as talks with John Kerry now move toward a June 30 deadline.",
     "coverage": 0.2857142857,
     "cost_usd": 0.00101775,
     "latency_ms": 1404.076
    }
   ]
  },
  {
   "config_id": "cnn_anthropic_l_n200_v1",
   "arm": "anthropic_l",
   "rank": 18,
   "coverage": 0.315,
   "rouge1": 0.3289,
   "delta": -0.031,
   "p": "0.0008",
   "verdict": "significant: worse",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.009826,
   "p50_ms": 3259.0,
   "total_usd": 1.965235,
   "model": "eval-opus-5",
   "family": "anthropic",
   "tier": "large",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_anthropic_l_n200_v1_20260926T063645Z",
   "created_at": "2026-09-26T06:48:09Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority became the 123rd member of the International Criminal Court on Wednesday, giving the court jurisdiction over alleged crimes in Palestinian territories. The ICC opened a preliminary examination in January into the situation there, potentially paving the way for war crimes investigations against Israelis, though Palestinians could also face counter-charges. Israel and the United States, both n",
     "coverage": 0.4117647059,
     "cost_usd": 0.00975,
     "latency_ms": 2665.905
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A stray dog in Washington State survived being hit by a car, struck on the head with a hammer and buried, staggering to a nearby farm four days later. Named Theia, the one-year-old suffered a dislocated jaw, leg injuries and a caved-in sinus cavity, and still needs surgery to breathe. Her foster carer's fundraising page has passed its $10,000 target, with extra money to be given to other animals.",
     "coverage": 0.3953488372,
     "cost_usd": 0.0075,
     "latency_ms": 2940.513
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif received a hero's welcome in Tehran after outlining a nuclear framework deal with world powers. Zarif, US-educated with degrees from San Francisco State and the University of Denver, has publicly distanced Iran from Holocaust denial and was once among students who seized Iran's San Francisco consulate. He and US Secretary of State John Kerry face a June 30 deadline to fin",
     "coverage": 0.3714285714,
     "cost_usd": 0.010985,
     "latency_ms": 3380.354
    }
   ]
  },
  {
   "config_id": "cnn_glm_s_n200_v1",
   "arm": "glm_s",
   "rank": 19,
   "coverage": 0.314,
   "rouge1": 0.3489,
   "delta": -0.032,
   "p": "0.0012",
   "verdict": "significant: worse",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.000152,
   "p50_ms": 1580.0,
   "total_usd": 0.03037138,
   "model": "eval-glm-45-air",
   "family": "glm",
   "tier": "small",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_glm_s_n200_v1_20260926T102344Z",
   "created_at": "2026-09-26T10:29:09Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "Palestinian Authority became the 123rd member of the International Criminal Court, granting the body jurisdiction over alleged crimes in Palestinian territories. The move, opposed by Israel and the U.S., allows the ICC to pursue possible war crimes investigations against Israelis and Palestinians.",
     "coverage": 0.4705882353,
     "cost_usd": 0.00014732,
     "latency_ms": 1372.275
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A Washington state dog survived being hit by a car, bludgeoned with a hammer, and buried alive, staggering to a farm four days later. The one-year-old bully mix, named Theia, is now receiving extensive medical care after a fundraising campaign surpassed its $10,000 goal.",
     "coverage": 0.3720930233,
     "cost_usd": 0.00012634,
     "latency_ms": 2100.772
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif, a key figure in nuclear talks, has a complex history including U.S. education, a past role in the Iranian Revolution, and discrepancies in his official biography. He has engaged in public diplomacy, such as tweeting about the Holocaust, and has spent significant time negotiating with U.S. Secretary of State John Kerry.",
     "coverage": 0.4,
     "cost_usd": 0.00018112,
     "latency_ms": 1432.51
    }
   ]
  },
  {
   "config_id": "cnn_gemma_m_n200_v1",
   "arm": "gemma_m",
   "rank": 20,
   "coverage": 0.314,
   "rouge1": 0.3442,
   "delta": -0.033,
   "p": "0.0006",
   "verdict": "significant: worse",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 7.7e-05,
   "p50_ms": 1388.0,
   "total_usd": 0.01538231,
   "model": "eval-gemma-26b",
   "family": "gemma",
   "tier": "mid",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_gemma_m_n200_v1_20260926T073250Z",
   "created_at": "2026-09-26T07:39:07Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority officially became the 123rd member of the International Criminal Court on Wednesday, granting the court jurisdiction over alleged crimes in Palestinian territories. The move, welcomed by human rights groups, faces strong opposition from Israel and the United States. The ICC's preliminary examination into the region could lead to war crimes investigations against both Israeli and Palestinian ",
     "coverage": 0.3529411765,
     "cost_usd": 6.909e-05,
     "latency_ms": 1996.736
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A stray dog in Washington State survived being hit by a car, struck with a hammer, and buried in a field. The dog, now named Theia, was discovered alive four days later and is receiving medical treatment at Washington State University. Fundraising efforts for her extensive surgeries have already exceeded $10,000.",
     "coverage": 0.4418604651,
     "cost_usd": 7.39e-05,
     "latency_ms": 578.51
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif is working to finalize a nuclear deal with U.S. Secretary of State John Kerry ahead of a June 30 deadline. Despite his polished diplomatic image, Zarif's background includes U.S. education, past involvement in student protests, and a previous federal investigation into a foundation linked to Iranian interests.",
     "coverage": 0.2857142857,
     "cost_usd": 8.1675e-05,
     "latency_ms": 1184.895
    }
   ]
  },
  {
   "config_id": "cnn_glm_l_n200_v1",
   "arm": "glm_l",
   "rank": 21,
   "coverage": 0.312,
   "rouge1": 0.3334,
   "delta": -0.034,
   "p": "0.0004",
   "verdict": "significant: worse",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.000766,
   "p50_ms": 2351.0,
   "total_usd": 0.15321223,
   "model": "eval-glm-5",
   "family": "glm",
   "tier": "large",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_glm_l_n200_v1_20260926T095351Z",
   "created_at": "2026-09-26T10:12:54Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority officially joined the International Criminal Court on Wednesday, gaining the body jurisdiction over alleged crimes in Palestinian territories. The move paves the way for possible war crimes investigations against Israel, which opposes the accession alongside the United States. Palestinian officials hailed the membership as a step toward justice, while noting it exposes Palestinians to potent",
     "coverage": 0.4705882353,
     "cost_usd": 0.00057348,
     "latency_ms": 2938.79
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A stray dog in Washington State survived being hit by a car, struck with a hammer, and buried in a field. The dog, named Theia, requires extensive surgery for severe injuries, prompting a fundraising campaign that has exceeded its goal. Her foster owner describes the one-year-old bully breed mix as a \"miracle dog\" who is gentle and loving despite her ordeal.",
     "coverage": 0.3953488372,
     "cost_usd": 0.00046752,
     "latency_ms": 2365.448
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif received a hero's welcome following the recent nuclear framework agreement. Lesser-known facts about Zarif include his U.S. education, a past tweet acknowledging the Holocaust, and an early role in revolutionary student takeovers of Iranian consulates. He continues to work closely with U.S. Secretary of State John Kerry ahead of a June 30 deadline.",
     "coverage": 0.2857142857,
     "cost_usd": 0.0011916,
     "latency_ms": 1216.859
    }
   ]
  },
  {
   "config_id": "cnn_gemma_s_n200_v1",
   "arm": "gemma_s",
   "rank": 22,
   "coverage": 0.312,
   "rouge1": 0.3215,
   "delta": -0.034,
   "p": "0.0002",
   "verdict": "significant: worse",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.0001,
   "p50_ms": 5933.0,
   "total_usd": 0.02001605,
   "model": "eval-gemma-3-27b",
   "family": "gemma",
   "tier": "small",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_gemma_s_n200_v1_20260926T073908Z",
   "created_at": "2026-09-26T08:02:22Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "Palestinian Authority officially joined the International Criminal Court, granting the ICC jurisdiction over alleged crimes in Palestinian territories since 2014. The move, opposed by Israel and the US, allows for potential war crimes investigations of both Israelis and Palestinians. ICC prosecutor will conduct an independent analysis, beginning with the 2014 Gaza conflict.",
     "coverage": 0.5,
     "cost_usd": 0.000102774,
     "latency_ms": 2753.574
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "Stray dog in Washington State survived being hit by a car, a failed \"mercy killing\" attempt, and burial. Theia, a one-year-old mix, was found alive days later and is now receiving veterinary care for severe injuries. Public fundraising has exceeded $10,000 to cover her ongoing medical expenses.",
     "coverage": 0.3255813953,
     "cost_usd": 7.9888e-05,
     "latency_ms": 5440.121
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif is central to ongoing nuclear negotiations with the U.S. Despite a public image as jovial, Zarif has a complex past including studying in the US during the Iranian Revolution and past allegations of financial misconduct. He has engaged directly with critics and demonstrated a willingness to address past Iranian policies, like Holocaust denial.",
     "coverage": 0.3428571429,
     "cost_usd": 0.000129354,
     "latency_ms": 3415.05
    }
   ]
  },
  {
   "config_id": "cnn_qwen_l_n200_v1",
   "arm": "qwen_l",
   "rank": 23,
   "coverage": 0.311,
   "rouge1": 0.3309,
   "delta": -0.035,
   "p": "0.0003",
   "verdict": "significant: worse",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.000844,
   "p50_ms": 2732.0,
   "total_usd": 0.16887312,
   "model": "eval-qwen-3max",
   "family": "qwen",
   "tier": "large",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_qwen_l_n200_v1_20260926T080222Z",
   "created_at": "2026-09-26T08:12:14Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority became the 123rd member of the International Criminal Court, granting the court jurisdiction over alleged crimes in Palestinian territories since June 13, 2014. Israel and the U.S., both non-members, opposed the move, while rights groups welcomed it as a step toward justice; the ICC has opened a preliminary examination that could lead to war crimes investigations involving both Israelis and ",
     "coverage": 0.5,
     "cost_usd": 0.00091182,
     "latency_ms": 2182.519
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A stray dog in Washington State survived being hit by a car, bludgeoned with a hammer, and buried alive, later staggering to a farm where she was rescued. Named Theia, the one-year-old bully mix suffered severe injuries but is recovering thanks to veterinary care and over $10,000 in public donations. Her story echoes that of a Florida cat recently found alive days after burial following a similar ordeal.",
     "coverage": 0.3953488372,
     "cost_usd": 0.00075816,
     "latency_ms": 2569.19
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif, a key figure in nuclear talks with the U.S., is known for his diplomatic finesse and U.S. education but has a complex past, including involvement in revolutionary-era protests and disputed biographical details. Despite past controversies, he now works closely with U.S. Secretary of State John Kerry to finalize a nuclear deal by the June 30 deadline.",
     "coverage": 0.3428571429,
     "cost_usd": 0.00107016,
     "latency_ms": 3588.214
    }
   ]
  },
  {
   "config_id": "cnn_mistral_l_n200_v1",
   "arm": "mistral_l",
   "rank": 24,
   "coverage": 0.308,
   "rouge1": 0.3188,
   "delta": -0.038,
   "p": "0.0001",
   "verdict": "significant: worse",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.000486,
   "p50_ms": 2272.0,
   "total_usd": 0.0972915,
   "model": "eval-mistral-large",
   "family": "mistral",
   "tier": "large",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_mistral_l_n200_v1_20260926T102910Z",
   "created_at": "2026-09-26T11:10:06Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "**Palestinian Authority becomes 123rd ICC member, granting court jurisdiction over alleged crimes in Palestinian territories. Israel and the U.S. oppose the move, while rights groups welcome it. A preliminary ICC examination into possible war crimes since June 2014 is underway.**",
     "coverage": 0.5,
     "cost_usd": 0.000468,
     "latency_ms": 1392.119
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "**Stray dog in Washington survives being hit by a car, hammer attack, and burial—found alive days later with severe injuries. Now named Theia, she’s recovering after $10K+ in donations for surgery. A Florida cat also recently \"rose from the dead\" after being buried post-car accident.**",
     "coverage": 0.2790697674,
     "cost_usd": 0.00037,
     "latency_ms": 1591.925
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "**Iranian FM Zarif, key nuclear negotiator, returns to hero’s welcome amid progress on sanctions deal. Less known: his U.S. education, disputed birth year, and past ties to Alavi Foundation probe. Zarif’s diplomacy with Kerry aims to finalize accord by June 30.**",
     "coverage": 0.1142857143,
     "cost_usd": 0.00058,
     "latency_ms": 1625.692
    }
   ]
  },
  {
   "config_id": "cnn_qwen_s_n200_v1",
   "arm": "qwen_s",
   "rank": 25,
   "coverage": 0.307,
   "rouge1": 0.336,
   "delta": -0.039,
   "p": "<0.0001",
   "verdict": "significant: worse",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.000135,
   "p50_ms": 7855.0,
   "total_usd": 0.02702255,
   "model": "eval-qwen-flash",
   "family": "qwen",
   "tier": "small",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_qwen_s_n200_v1_20260926T081215Z",
   "created_at": "2026-09-26T09:53:50Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority officially became the 123rd member of the International Criminal Court, granting it jurisdiction over alleged crimes in Palestinian territories. Israel and the United States opposed the accession, while human rights groups welcomed the move as a step toward ending impunity.",
     "coverage": 0.4705882353,
     "cost_usd": 0.00013872,
     "latency_ms": 1652.177
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A one-year-old stray dog in Washington State survived being hit by a car, struck with a hammer, and buried after staggering to a nearby farm four days later. Named Theia, the bully breed mix is now receiving extensive medical care for severe injuries, including a dislocated jaw and caved-in sinus cavity, funded by public donations exceeding $10,000.",
     "coverage": 0.4186046512,
     "cost_usd": 0.00011972,
     "latency_ms": 6841.687
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif, a key figure in nuclear negotiations with the U.S., is profiled for his lesser-known background, including his U.S. education and past involvement in seizing an Iranian consulate. Despite his diplomatic prominence and \"jovial\" public image, questions remain regarding his birth date and prior legal scrutiny over alleged sanctions evasion.",
     "coverage": 0.3428571429,
     "cost_usd": 0.00018191,
     "latency_ms": 2438.888
    }
   ]
  },
  {
   "config_id": "cnn_mistral_m_n200_v1",
   "arm": "mistral_m",
   "rank": 26,
   "coverage": 0.304,
   "rouge1": 0.3197,
   "delta": -0.042,
   "p": "<0.0001",
   "verdict": "significant: worse",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.000435,
   "p50_ms": 2495.0,
   "total_usd": 0.0870584,
   "model": "eval-mistral-medium",
   "family": "mistral",
   "tier": "mid",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_mistral_m_n200_v1_20260926T111007Z",
   "created_at": "2026-09-26T11:19:01Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "Palestine officially joined the ICC as its 123rd member, granting the court jurisdiction over alleged crimes in Palestinian territories since June 2014. Israel and the US opposed the move, while Palestinian officials hailed it as a step toward justice. The ICC has opened a preliminary examination into possible war crimes by both sides.",
     "coverage": 0.5,
     "cost_usd": 0.0004484,
     "latency_ms": 2397.781
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "Stray dog in Washington survives being hit by a car, buried after a hammer blow, and staggering to a farm; now named Theia, she needs surgery for severe injuries. Fundraising exceeds $10,000 for her care, with excess aiding other animals. A similar case involved a Florida cat surviving burial after a car accident.",
     "coverage": 0.2790697674,
     "cost_usd": 0.0003688,
     "latency_ms": 2264.625
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif, key in nuclear talks with the U.S., received a hero's welcome in Tehran. Less known: he studied in the U.S., tweeted Jewish New Year greetings, and was once investigated over ties to a sanctioned foundation. He now works closely with U.S. Secretary of State John Kerry ahead of a June 30 nuclear deal deadline.",
     "coverage": 0.4285714286,
     "cost_usd": 0.0005552,
     "latency_ms": 1047.614
    }
   ]
  },
  {
   "config_id": "cnn_qwen_m_n200_v1",
   "arm": "qwen_m",
   "rank": 27,
   "coverage": 0.303,
   "rouge1": 0.3164,
   "delta": -0.043,
   "p": "<0.0001",
   "verdict": "significant: worse",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.000331,
   "p50_ms": 1531.0,
   "total_usd": 0.06614944,
   "model": "eval-qwen-37plus",
   "family": "qwen",
   "tier": "mid",
   "temperature": 0.0,
   "max_tokens": 1200,
   "prompt_file": "prompt.txt",
   "provider": "litellm",
   "run_id": "cnn_qwen_m_n200_v1_20260925T232115Z",
   "created_at": "2026-09-25T23:26:25Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinian Authority officially became the 123rd member of the International Criminal Court on Wednesday, granting the body jurisdiction over alleged crimes in Palestinian territories since June 2014. The move, opposed by Israel and the United States, paves the way for potential war crimes investigations against both Palestinians and Israelis.",
     "coverage": 0.4705882353,
     "cost_usd": 0.00032256,
     "latency_ms": 1585.785
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A Washington State dog named Theia survived a car accident, blunt force trauma, and burial to emerge from a field four days later with severe injuries. Her rescuer has raised over $10,000 for necessary surgeries, including jaw and sinus repairs, as the \"miracle dog\" recovers at a veterinary hospital.",
     "coverage": 0.2325581395,
     "cost_usd": 0.0002608,
     "latency_ms": 1316.688
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Iranian Foreign Minister Mohammad Javad Zarif, hailed as a hero for securing a nuclear breakthrough with the U.S., holds a complex history including U.S. education and past revolutionary activism. Despite previous Justice Department investigations into his alleged ties to sanctions-busting entities, Zarif remains central to ongoing negotiations aimed at finalizing a deal by June 30.",
     "coverage": 0.2571428571,
     "cost_usd": 0.00040288,
     "latency_ms": 1673.195
    }
   ]
  },
  {
   "config_id": "cnn_lead3_n200_v1",
   "arm": "lead3",
   "rank": 28,
   "coverage": 0.272,
   "rouge1": 0.302,
   "delta": -0.074,
   "p": "<0.0001",
   "verdict": "significant: worse",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.0,
   "p50_ms": 0.057,
   "total_usd": 0.0,
   "model": null,
   "family": "lead",
   "tier": "free",
   "temperature": null,
   "max_tokens": null,
   "prompt_file": null,
   "provider": "lead_k",
   "run_id": "cnn_lead3_n200_v1_20260926T153351Z",
   "created_at": "2026-09-26T15:33:53Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "(CNN)The Palestinian Authority officially became the 123rd member of the International Criminal Court on Wednesday, a step that gives the court jurisdiction over alleged crimes in Palestinian territories. The formal accession was marked with a ceremony at The Hague, in the Netherlands, where the court is based. The Palestinians signed the ICC's founding Rome Statute in January, when they also accepted its jurisdictio",
     "coverage": 0.3529411765,
     "cost_usd": 0.0,
     "latency_ms": 0.076
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "(CNN)Never mind cats having nine lives. A stray pooch in Washington State has used up at least three of her own after being hit by a car, apparently whacked on the head with a hammer in a misguided mercy killing and then buried in a field -- only to survive. That's according to Washington State University, where the dog -- a friendly white-and-black bully breed mix now named Theia -- has been receiving care at the Ve",
     "coverage": 0.3023255814,
     "cost_usd": 0.0,
     "latency_ms": 0.047
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "(CNN)If you've been following the news lately, there are certain things you doubtless know about Mohammad Javad Zarif. He is, of course, the Iranian foreign minister. He has been U.S.",
     "coverage": 0.3142857143,
     "cost_usd": 0.0,
     "latency_ms": 0.083
    }
   ]
  },
  {
   "config_id": "cnn_bart_l_xsum_n200_v1",
   "arm": "bart_l_xsum",
   "rank": 29,
   "coverage": 0.207,
   "rouge1": 0.2836,
   "delta": -0.139,
   "p": "<0.0001",
   "verdict": "significant: worse",
   "baseline": false,
   "recommended": false,
   "usd_per_item": 0.0,
   "p50_ms": 4433.0,
   "total_usd": 0.0,
   "model": "facebook/bart-large-xsum",
   "family": "bart",
   "tier": "free",
   "temperature": null,
   "max_tokens": null,
   "prompt_file": null,
   "provider": "hf_local",
   "run_id": "cnn_bart_l_xsum_n200_v1_20260930T092945Z",
   "created_at": "2026-09-30T09:45:18Z",
   "replies": [
    {
     "item": "f001ec5c4704938247d27a44948eebb37ae98d01",
     "text": "The Palestinians have formally joined the International Criminal Court, paving the way for possible war crimes investigations against Israelis.",
     "coverage": 0.2352941176,
     "cost_usd": 0.0,
     "latency_ms": 4076.578
    },
    {
     "item": "230c522854991d053fe98a718b1defa077a8efef",
     "text": "A dog that apparently died after being hit by a car and buried in a field has been hailed as a \"miracle dog\" after raising more than $10,000 for medical treatment.",
     "coverage": 0.3255813953,
     "cost_usd": 0.0,
     "latency_ms": 4996.882
    },
    {
     "item": "4495ba8f3a340d97a9df1476f8a35502bcce1f69",
     "text": "Mohammad Javad Zarif, the Iranian foreign minister, has spent more time with US Secretary of State John Kerry than any other foreign minister in the world.",
     "coverage": 0.6,
     "cost_usd": 0.0,
     "latency_ms": 6594.891
    }
   ]
  }
 ],
 "rounds": [
  {
   "id": "r1",
   "status": "closed",
   "question": "Which of 24 hosted LLMs (8 vendors × 3 price tiers) and local BART summarisers covers a CNN article's gold highlights best, and at what cost?",
   "opened": "2026-09-25T23:26:25Z",
   "closed": "2026-09-30T09:45:18Z",
   "from": null,
   "retired": 0,
   "conclusion": "On coverage, bart_l (BART-large-CNN, $0, 11.0 s per article on a 12-core Mac CPU) scores 0.3461 and the best hosted arm, deepseek_m ($191 per 1M articles, 1.6 s), 0.3460: not significant (p = 0.99). Use bart_l if you can run a free 1.6 GB model on CPU and your text looks like CNN news; rent deepseek_m if you need speed; do not buy anthropic_l. (REPORT_SUMMARIZATION, executive summary.)",
   "promoted": "cnn_bart_l_n200_v1_20260926T153757Z"
  },
  {
   "id": "r2",
   "status": "closed",
   "question": "Do the local arms reproduce, and how fast are they, re-run on one Linux machine?",
   "opened": "2026-09-30T14:41:34Z",
   "closed": "2026-09-30T15:48:17Z",
   "from": "r1",
   "retired": 5,
   "conclusion": "All five local arms reproduced 200 of 200 outputs byte-identically (bart_m, bart_s and bart_l_xsum on the same Linux machine; bart_l and lead3 on a different one): their run-to-run variance is zero. (REPORT_SUMMARIZATION, the local contrast.)",
   "promoted": null
  },
  {
   "id": "r3",
   "status": "closed",
   "question": "Does a local arm's output change when it is run again on the same machine?",
   "opened": "2026-09-30T09:12:12Z",
   "closed": "2026-09-30T09:12:12Z",
   "from": "r2",
   "retired": 1,
   "conclusion": "bart_s re-ran 200 of 200 outputs byte-identical on the same machine (three times, counting the resumed run). (REPORT_SUMMARIZATION.)",
   "promoted": null
  }
 ],
 "answer": "bart_l (BART-large-CNN, MIT, $0 on a CPU) leads on coverage at 0.3461, not significantly different from deepseek_m (0.3460, p = 0.99), for CNN-style text; rent deepseek_m if you need speed. REPORT_SUMMARIZATION, executive summary.",
 "detectable": "Detectable: with 28 candidate(s) on 200 items, a contender can be shown (80% of the time, if it is truly as good) only within a margin of about 0.0363 or more; this goal's is 0.01731: raise the margin, compare fewer arms, or add items.",
 "home": [
  {
   "id": "entities_few_nerd",
   "title": "Named-entity extraction (Few-NERD)",
   "measure": "f1",
   "direction": "higher",
   "strategy": "balanced",
   "datasets": [
    "few_nerd_280",
    "few_nerd_56"
   ],
   "references": [],
   "rounds": 1,
   "open": [],
   "last": "r1",
   "deployed": false
  },
  {
   "id": "entity_topic_dbpedia",
   "title": "Encyclopedia topic classification (DBpedia)",
   "measure": "correct",
   "direction": "higher",
   "strategy": "frugal",
   "datasets": [
    "dbpedia_280",
    "dbpedia_56"
   ],
   "references": [],
   "rounds": 2,
   "open": [],
   "last": "r2",
   "deployed": false
  },
  {
   "id": "news_summary_cnn",
   "title": "Short news summaries (CNN)",
   "measure": "coverage",
   "direction": "higher",
   "strategy": "balanced",
   "datasets": [
    "cnn_dailymail_200",
    "cnn_dailymail_20",
    "cnn_dailymail_dm200"
   ],
   "references": [
    "gold/cnn_dailymail_200"
   ],
   "rounds": 3,
   "open": [],
   "last": "r3",
   "deployed": false
  },
  {
   "id": "news_topic_ag",
   "title": "News topic classification (AG News)",
   "measure": "correct",
   "direction": "higher",
   "strategy": "balanced",
   "datasets": [
    "ag_news_200",
    "ag_news_20"
   ],
   "references": [
    "gold/ag_news_200",
    "gold/ag_news_200_adj1"
   ],
   "rounds": 2,
   "open": [],
   "last": "r2",
   "deployed": false
  },
  {
   "id": "scientific_retrieval_scifact",
   "title": "Evidence retrieval for scientific claims (SciFact)",
   "measure": "ndcg_10",
   "direction": "higher",
   "strategy": "frugal",
   "datasets": [
    "scifact_200",
    "scifact_40"
   ],
   "references": [],
   "rounds": 3,
   "open": [],
   "last": "r3",
   "deployed": false
  },
  {
   "id": "summary_judge_summeval",
   "title": "A scorer that agrees with experts on summaries (SummEval)",
   "measure": "tau",
   "direction": "higher",
   "strategy": "frugal",
   "datasets": [
    "summeval_100"
   ],
   "references": [],
   "rounds": 2,
   "open": [],
   "last": "r2",
   "deployed": false
  },
  {
   "id": "triage_orrery",
   "title": "Triage decisions on Orrery's error signals",
   "measure": "triage_cost",
   "direction": "lower",
   "strategy": "frugal",
   "datasets": [
    "orrery_triage_v1_labelled",
    "orrery_triage_v1_labelled_v2"
   ],
   "references": [
    "gold/orrery_triage_v1_labelled",
    "gold/orrery_triage_v1_labelled_v2"
   ],
   "rounds": 4,
   "open": [],
   "last": "r4",
   "deployed": true
  }
 ],
 "onboard": {
  "pass": {
   "id": "deepseek-4.1-flash",
   "name": "DeepSeek 4.1 Flash",
   "weights": "open",
   "licence": "MIT",
   "deployments": [
    {
     "id": "hosted",
     "where": "homelab LiteLLM (the fleet's gateway)",
     "endpoint": {
      "provider": "litellm",
      "base_url": "http://homelab:4001/v1",
      "model": "eval-deepseek-41flash"
     },
     "onboarding": {
      "status": "pass",
      "at": "2026-10-31T14:09:01Z",
      "flags": [],
      "report": {
       "endpoint": {
        "provider": "litellm",
        "base_url": "http://homelab:4001/v1",
        "model": "eval-deepseek-41flash"
       },
       "digest_found": null,
       "default": {
        "s": 1.56,
        "tokens_out": 43,
        "reasoned": true,
        "finish": "stop"
       },
       "chosen": {
        "s": 0.66,
        "tokens_out": 24,
        "reasoned": false,
        "finish": "stop",
        "settings": {
         "reasoning_effort": "none"
        }
       },
       "tokens_per_s": 36.2,
       "deterministic": true,
       "json_valid": true
      }
     }
    }
   ],
   "settings": {
    "reasoning_effort": "none"
   },
   "settings_why": {
    "reasoning_effort": "it reasoned by default on the onboarding probe (2026-10-31); off unless a task needs it (RUNBOOK §16): left at the server's default, one model reasons at length and the next not at all"
   },
   "accepted": {
    "where it ran": "a hosted gateway serves the provider's current build; there is no digest, revision or hash to pin",
    "determinism": "a hosted provider batches requests, so temperature 0 does not repeat exactly; repeats measure it"
   }
  },
  "check": {
   "id": "ministral-3-14b",
   "name": "Ministral 3 14B",
   "weights": "open",
   "licence": "Apache-2.0",
   "deployments": [
    {
     "id": "x3",
     "where": "x3",
     "endpoint": {
      "provider": "openai",
      "base_url": "http://127.0.0.1:11434/v1",
      "model": "ministral-3:14b"
     },
     "onboarding": {
      "status": "check",
      "at": "2026-10-31T14:05:49Z",
      "flags": [
       "format: the JSON probe's answer is not valid JSON"
      ],
      "report": {
       "endpoint": {
        "provider": "openai",
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "ministral-3:14b"
       },
       "digest_found": "4760c35aeb9d9e9c6174c2492562c0b999e80a222804fd96b1915ab72bbcdcf7",
       "default": {
        "s": 7.85,
        "tokens_out": 92,
        "reasoned": false,
        "finish": "stop"
       },
       "chosen": {
        "s": 3.84,
        "tokens_out": 92,
        "reasoned": false,
        "finish": "stop",
        "settings": {}
       },
       "tokens_per_s": 23.9,
       "deterministic": true,
       "json_valid": false
      }
     }
    },
    {
     "id": "dgx",
     "where": "dgx",
     "endpoint": {
      "provider": "openai",
      "base_url": "http://100.69.49.126:11434/v1",
      "model": "ministral-3:14b"
     },
     "onboarding": {
      "status": "check",
      "at": "2026-10-31T14:07:46Z",
      "flags": [
       "format: the JSON probe's answer is not valid JSON"
      ],
      "report": {
       "endpoint": {
        "provider": "openai",
        "base_url": "http://100.69.49.126:11434/v1",
        "model": "ministral-3:14b"
       },
       "digest_found": "4760c35aeb9d9e9c6174c2492562c0b999e80a222804fd96b1915ab72bbcdcf7",
       "default": {
        "s": 8.45,
        "tokens_out": 85,
        "reasoned": false,
        "finish": "stop"
       },
       "chosen": {
        "s": 3.42,
        "tokens_out": 85,
        "reasoned": false,
        "finish": "stop",
        "settings": {}
       },
       "tokens_per_s": 24.8,
       "deterministic": true,
       "json_valid": false
      }
     }
    },
    {
     "id": "mac",
     "where": "mac",
     "endpoint": {
      "provider": "openai",
      "base_url": "http://127.0.0.1:11435/v1",
      "model": "ministral-3:14b"
     },
     "onboarding": {
      "status": "pass",
      "at": "2026-10-31T13:55:45Z",
      "flags": [],
      "report": {
       "endpoint": {
        "provider": "openai",
        "base_url": "http://127.0.0.1:11435/v1",
        "model": "ministral-3:14b"
       },
       "digest_found": "4760c35aeb9d9e9c6174c2492562c0b999e80a222804fd96b1915ab72bbcdcf7",
       "default": {
        "s": 8.35,
        "tokens_out": 32,
        "reasoned": false,
        "finish": "stop"
       },
       "chosen": {
        "s": 1.37,
        "tokens_out": 32,
        "reasoned": false,
        "finish": "stop",
        "settings": {}
       },
       "tokens_per_s": 23.4,
       "deterministic": true,
       "json_valid": true
      }
     }
    }
   ],
   "settings": null,
   "settings_why": null,
   "accepted": null
  }
 },
 "silver": {
  "rows": [
   {
    "arm": "anthropic_m",
    "rank": 1,
    "coverage": 0.491,
    "verdict": "leader",
    "p": null
   },
   {
    "arm": "deepseek_m",
    "rank": 2,
    "coverage": 0.471,
    "verdict": "significant: worse",
    "p": "0.0087"
   },
   {
    "arm": "anthropic_s",
    "rank": 3,
    "coverage": 0.469,
    "verdict": "significant: worse",
    "p": "0.0010"
   },
   {
    "arm": "deepseek_l",
    "rank": 4,
    "coverage": 0.399,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "qwen_l",
    "rank": 5,
    "coverage": 0.398,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "glm_m",
    "rank": 6,
    "coverage": 0.389,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "llama_s",
    "rank": 7,
    "coverage": 0.388,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "deepseek_s",
    "rank": 8,
    "coverage": 0.388,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "openai_s",
    "rank": 9,
    "coverage": 0.384,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "mistral_s",
    "rank": 10,
    "coverage": 0.382,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "qwen_m",
    "rank": 11,
    "coverage": 0.381,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "glm_l",
    "rank": 12,
    "coverage": 0.375,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "openai_l",
    "rank": 13,
    "coverage": 0.371,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "llama_l",
    "rank": 14,
    "coverage": 0.37,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "openai_m",
    "rank": 15,
    "coverage": 0.359,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "llama_m",
    "rank": 16,
    "coverage": 0.358,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "gemma_s",
    "rank": 17,
    "coverage": 0.35,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "gemma_m",
    "rank": 18,
    "coverage": 0.342,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "gemma_l",
    "rank": 19,
    "coverage": 0.342,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "mistral_l",
    "rank": 20,
    "coverage": 0.337,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "qwen_s",
    "rank": 21,
    "coverage": 0.334,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "mistral_m",
    "rank": 22,
    "coverage": 0.32,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "bart_m",
    "rank": 23,
    "coverage": 0.32,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "bart_l",
    "rank": 24,
    "coverage": 0.317,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "bart_s",
    "rank": 25,
    "coverage": 0.306,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "glm_s",
    "rank": 26,
    "coverage": 0.303,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "lead3",
    "rank": 27,
    "coverage": 0.3,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "bart_l_xsum",
    "rank": 28,
    "coverage": 0.137,
    "verdict": "significant: worse",
    "p": "<0.0001"
   },
   {
    "arm": "anthropic_l",
    "rank": 29,
    "coverage": 1.0,
    "verdict": "leader",
    "p": null
   }
  ],
  "authored_by": "anthropic_l",
  "cost_usd": 1.965235,
  "caveat": "SILVER: promoted as silver from a model's run, its outputs (model · cnn_anthropic_l_n200_v1_20260926T063645Z): consistent, not a claim that any arm is right. Good enough to RANK arms against each other; say so wherever a number scored against it is published.",
  "created_at": "2026-10-25T16:22:49Z"
 },
 "judge": {
  "id": "judge-summ-v2",
  "judges": [
   {
    "id": "openai_l",
    "model": "eval-gpt-6sol",
    "family": "openai"
   },
   {
    "id": "anthropic_l",
    "model": "eval-opus-5",
    "family": "anthropic"
   }
  ],
  "protocol": {
   "listwise": true,
   "outputs_per_call": 16,
   "blinding": true,
   "order_seed": 0,
   "position_check_fraction": 0.1,
   "noise_check_fraction": 0.1,
   "contested_threshold": 0.5
  },
  "cost_cap_usd": 15.0,
  "prompt": "examples/summeval-judging/prompt.txt",
  "validation": {
   "dataset": "summeval_100",
   "metric": "tau",
   "what": "mean Kendall tau-b against the mean of three expert annotators, over 4 dimensions and 100 articles",
   "runs": [
    {
     "judge": "openai_l",
     "run": "se_openai_l_n100_v1_20261018T114806Z",
     "value": 0.539751,
     "min_metric": 0.371714
    },
    {
     "judge": "anthropic_l",
     "run": "se_anthropic_l_n100_v1_20261018T115657Z",
     "value": 0.528268,
     "min_metric": 0.371714
    }
   ]
  },
  "checks": {
   "goyal2022-cnn": {
    "source": "Goyal, Li & Durrett 2022, cnn_human.json (CC BY 4.0)",
    "articles": 100,
    "judges": {
     "openai_l": {
      "best_pick_agreement": "35/82",
      "billed_usd": 0.2717,
      "rate": 0.5183,
      "ci95": [
       0.4118,
       0.6232
      ],
      "chance": 0.3333
     },
     "anthropic_l": {
      "best_pick_agreement": "37/82",
      "billed_usd": 0.9468,
      "rate": 0.5366,
      "ci95": [
       0.4294,
       0.6404
      ],
      "chance": 0.3333
     }
    }
   }
  }
 },
 "production": {
  "goal": "triage_orrery",
  "title": "Triage decisions on Orrery's error signals",
  "capture": "orrery_2026_10_v2",
  "captured_at": "2026-11-04T13:30:45Z",
  "records": 233,
  "first": "2026-07-25T09:58:27.018946Z",
  "last": "2026-10-29T16:33:47.779688Z",
  "dataset": "orrery_triage_v1_labelled_v2",
  "rows": [
   {
    "arm": "triage_prompt_own_code_loads_v1",
    "triage_cost": 0.446,
    "vs": "—",
    "usd_per_item": "$0.004968"
   },
   {
    "arm": "triage_noise_gate_v1",
    "triage_cost": 0.503,
    "vs": "+0.056, p 0.4425, not significant",
    "usd_per_item": "$0.005516"
   },
   {
    "arm": "triage_prompt_noise_classes_v1",
    "triage_cost": 0.749,
    "vs": "+0.303, p 0.0119, significant: worse",
    "usd_per_item": "$0.005836"
   },
   {
    "arm": "triage_baseline_pro_v2data_v1",
    "triage_cost": 0.872,
    "vs": "+0.426, p 0.0014, significant: worse",
    "usd_per_item": "$0.005562"
   }
  ],
  "labels": [
   "gold_orrery_triage_v1_labelled",
   "silver_orrery_triage_v1_labelled_hand",
   "silver_orrery_triage_v1_labelled_outcomes"
  ],
  "decides": "triage_cost, lower is better"
 },
 "modes": [
  {
   "id": "narration",
   "description": "1 when the output thinks out loud (\"the user wants\", \"let me draft\", think tags) instead of only summarising: its quality numbers describe something else."
  },
  {
   "id": "label",
   "description": "1 when the output opens with a label such as \"Summary:\" the prompt did not ask for."
  },
  {
   "id": "markdown",
   "description": "1 when the output opens with markdown (bold, a heading, a quote) the prompt did not ask for."
  },
  {
   "id": "bullets",
   "description": "1 when the output has bullet lines where the prompt asks for sentences."
  },
  {
   "id": "paragraphs",
   "description": "1 when the output has more than one paragraph where the prompt asks for 2-3 short sentences."
  },
  {
   "id": "overlong",
   "description": "1 when the output runs past 90 words where the prompt asks for 2-3 short sentences."
  },
  {
   "id": "truncated",
   "description": "1 when the provider cut the reply off at the token ceiling (finish_reason \"length\", and in most adapters a completion that reached 98% of max_tokens), else 0. An arm with truncated above 0 has scores that partly describe the ceiling, not the model."
  }
 ],
 "axes": {
  "rouge1": {
   "direction": "higher"
  }
 },
 "sources": {
  "zenodo": {
   "query": {
    "record": 10157504,
    "file": "sts_gold_tweet.csv",
    "text": "tweet",
    "id": "id",
    "fields": [
     "polarity"
    ],
    "limit": 4
   },
   "describe": {
    "source": {
     "provider": "zenodo",
     "ref": "10157503",
     "url": "https://doi.org/10.5281/zenodo.10157504",
     "revision": "10157504",
     "description_sha256": "18edb2d88e15078406f61c9cb33778ff34b1a32211ee23bfb7f10c5ae3dc8e61"
    },
    "description": "Datasets for Sentiment Analysis",
    "licence": "CC-BY-4.0"
   },
   "rows": [
    {
     "id": "1467933112",
     "text": "the angel is going to miss the athlete this weekend ",
     "fields": {
      "polarity": "0"
     }
    },
    {
     "id": "2323395086",
     "text": "It looks as though Shaq is getting traded to Cleveland to play w/ LeBron... Too bad for Suns' fans. The Big Cactus is no more ",
     "fields": {
      "polarity": "0"
     }
    },
    {
     "id": "1467968979",
     "text": "@clarianne APRIL 9TH ISN'T COMING SOON ENOUGH ",
     "fields": {
      "polarity": "0"
     }
    },
    {
     "id": "1990283756",
     "text": "drinking a McDonalds coffee and not understanding why someone would hurt me for no apparent reason. ",
     "fields": {
      "polarity": "0"
     }
    }
   ]
  },
  "openml": {
   "query": {
    "dataset": 61,
    "text": "class",
    "fields": [
     "sepallength"
    ],
    "limit": 4
   },
   "error": "ValueError: https://data.openml.org/datasets/0000/0061/dataset_61.pq: HTTP Error 503: Service Temporarily Unavailable"
  },
  "kaggle": {
   "query": {
    "ref": "uciml/iris",
    "version": 2,
    "file": "Iris.csv",
    "text": "Species",
    "fields": [
     "SepalLengthCm"
    ],
    "limit": 4
   },
   "describe": {
    "source": {
     "provider": "kaggle",
     "ref": "uciml/iris",
     "url": "https://www.kaggle.com/datasets/uciml/iris",
     "revision": "2",
     "description_sha256": "be7683bc621d244a0e3b6db9e69b59dc74b12b2da6379c850b72f556edec380c"
    },
    "description": "Iris Species",
    "licence": "CC0-1.0"
   },
   "rows": [
    {
     "id": "row_0",
     "text": "Iris-setosa",
     "fields": {
      "SepalLengthCm": "5.1"
     }
    },
    {
     "id": "row_1",
     "text": "Iris-setosa",
     "fields": {
      "SepalLengthCm": "4.9"
     }
    },
    {
     "id": "row_2",
     "text": "Iris-setosa",
     "fields": {
      "SepalLengthCm": "4.7"
     }
    },
    {
     "id": "row_3",
     "text": "Iris-setosa",
     "fields": {
      "SepalLengthCm": "4.6"
     }
    }
   ]
  },
  "croissant": {
   "query": {
    "path": "build/cnn_dailymail_20.croissant.json",
    "text": "text",
    "id": "item_id",
    "limit": 4
   },
   "error": "ValueError: field text: only a column of one FileObject is read; this one is a FileSet of text/plain (which files it holds is the host's to say, and only the Hub lists a Hugging Face description's files)"
  },
  "folder": {
   "query": {
    "path": "data/sources/cnn_dailymail_20",
    "glob": "*.txt"
   },
   "describe": {
    "source": {
     "provider": "folder",
     "ref": "data/sources/cnn_dailymail_20"
    }
   },
   "rows": [
    {
     "id": "0d3c8c276d079c4c225f034c69aa024cdab7869d",
     "text": "(CNN)Andrew Getty, one of the heirs to billions of oil money, appears to have died of natural causes, a Los Angeles Police Department spokesman said. The coroner's preliminary assessment is there was no foul play involved in the death of Ge",
     "fields": {}
    },
    {
     "id": "1b2cc634e2bfc6f2595260e7ed9b42f77ecbb0ce",
     "text": "(CNN)He's a blue chip college basketball recruit. She's a high school freshman with Down syndrome. At first glance Trey Moses and Ellie Meredith couldn't be more different. But all that changed Thursday when Trey asked Ellie to be his prom ",
     "fields": {}
    },
    {
     "id": "1dd00c89d71a5611797bb34da8a6eada8f058405",
     "text": "(CNN)A year ago Bloomberg published a story with the following headline: Mike Pence, a Koch Favorite, Mulls 2016 Run for President. The story ticked off items on Pence's conservative things-to-do list while also noting his close ties to the",
     "fields": {}
    },
    {
     "id": "203886369feea77bbc35715e6d7e518b751f57de",
     "text": "(CNN)Seventy years ago, Anne Frank died of typhus in a Nazi concentration camp at the age of 15. Just two weeks after her supposed death on March 31, 1945, the Bergen-Belsen concentration camp where she had been imprisoned was liberated -- ",
     "fields": {}
    }
   ]
  }
 },
 "reruns": {
  "cnn_bart_l_n200_v1": {
   "run_id": "cnn_bart_l_n200_v1_20260930T152617Z",
   "coverage": 0.3461,
   "p50_ms": 6265.427,
   "created_at": "2026-09-30T15:48:17Z"
  },
  "cnn_bart_l_xsum_n200_v1": {
   "run_id": "cnn_bart_l_xsum_n200_v1_20260930T150959Z",
   "coverage": 0.2071,
   "p50_ms": 3938.039,
   "created_at": "2026-09-30T15:26:16Z",
   "delta": -0.139,
   "p": "<0.0001"
  },
  "cnn_bart_m_n200_v1": {
   "run_id": "cnn_bart_m_n200_v1_20260930T145345Z",
   "coverage": 0.3367,
   "p50_ms": 4120.604,
   "created_at": "2026-09-30T15:09:58Z",
   "delta": -0.0095,
   "p": "0.1607"
  },
  "cnn_bart_s_n200_v1": {
   "run_id": "cnn_bart_s_n200_v1_20260930T144134Z",
   "coverage": 0.3276,
   "p50_ms": 3389.068,
   "created_at": "2026-09-30T14:53:44Z",
   "delta": -0.0186,
   "p": "0.0158"
  },
  "cnn_lead3_n200_v1": {
   "run_id": "cnn_lead3_n200_v1_20260930T144131Z",
   "coverage": 0.2718,
   "p50_ms": 0.063,
   "created_at": "2026-09-30T14:41:34Z",
   "delta": -0.0743,
   "p": "<0.0001"
  }
 },
 "wrong": [
  {
   "id": "orrery-ORRERY-J-2026-08-06T21:52:38Z",
   "decided": "cleanup",
   "people": "escalate or file",
   "cost": "5.0",
   "date": "2026-08-06",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-5-2026-08-18T18:38:10Z",
   "decided": "dismiss",
   "people": "escalate or file",
   "cost": "5.0",
   "date": "2026-08-18",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-7-2026-08-18T18:48:08Z",
   "decided": "dismiss",
   "people": "escalate or file",
   "cost": "5.0",
   "date": "2026-08-18",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-6-2026-08-18T18:48:08Z",
   "decided": "dismiss",
   "people": "escalate or file",
   "cost": "5.0",
   "date": "2026-08-18",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-PROD-5-2026-09-01T16:52:52Z",
   "decided": "file",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-09-01",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-PROD-3-2026-09-03T10:42:29Z",
   "decided": "cleanup",
   "people": "escalate or file",
   "cost": "5.0",
   "date": "2026-09-03",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-PROD-8-2026-09-04T10:42:38Z",
   "decided": "dismiss",
   "people": "escalate or file",
   "cost": "5.0",
   "date": "2026-09-04",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-PROD-9-2026-09-10T06:35:05Z",
   "decided": "escalate",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-09-10",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-PROD-H-2026-09-12T14:18:41Z",
   "decided": "file",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-09-12",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-PROD-I-2026-09-12T14:19:18Z",
   "decided": "file",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-09-12",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-PROD-J-2026-09-13T14:29:00Z",
   "decided": "file",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-09-13",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-P-2026-09-28T14:29:20Z",
   "decided": "escalate",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-09-28",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-O-2026-09-28T14:29:49Z",
   "decided": "escalate",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-09-28",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-M-2026-09-28T14:30:34Z",
   "decided": "escalate",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-09-28",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-L-2026-09-28T14:30:54Z",
   "decided": "escalate",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-09-28",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-T-2026-09-28T22:39:04Z",
   "decided": "file",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-09-28",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-S-2026-09-28T22:39:57Z",
   "decided": "dismiss",
   "people": "escalate or file",
   "cost": "5.0",
   "date": "2026-09-28",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-R-2026-09-28T22:49:15Z",
   "decided": "file",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-09-28",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-PROD-1D-2026-10-16T13:02:46Z",
   "decided": "file",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-10-16",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-PROD-U-2026-10-16T16:02:48Z",
   "decided": "file",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-10-16",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-PROD-1F-2026-10-16T16:03:15Z",
   "decided": "escalate",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-10-16",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-PROD-18-2026-10-16T16:03:49Z",
   "decided": "escalate",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-10-16",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-13-2026-10-16T19:42:45Z",
   "decided": "escalate",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-10-16",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-16-2026-10-19T08:12:37Z",
   "decided": "escalate",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-10-19",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-PROD-1O-2026-10-20T10:43:08Z",
   "decided": "dismiss",
   "people": "file",
   "cost": "5.0",
   "date": "2026-10-20",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-17-2026-10-21T13:22:56Z",
   "decided": "escalate",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-10-21",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-PROD-1T-2026-10-22T20:42:51Z",
   "decided": "file",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-10-22",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-PROD-1U-2026-10-23T21:23:10Z",
   "decided": "file",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-10-23",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-PROD-1V-2026-10-25T08:23:12Z",
   "decided": "file",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-10-25",
   "stage": "propose"
  },
  {
   "id": "orrery-ORRERY-19-2026-10-26T03:02:55Z",
   "decided": "escalate",
   "people": "dismiss",
   "cost": "1.0",
   "date": "2026-10-26",
   "stage": "propose"
  }
 ],
 "sheet": "item_id,item,proposal,label,also right,note\n012819ffa2547138101055add33deebe7beaa3d4,\"(CNN)Mullah Mohammed Omar is \"\"still the leader\"\" of the Taliban's self-declared Islamic Emirate of Afghanistan. That appears to be the primary message of a biog…\",,,,\n04c28c2d6c524d96e046cadf32eb44803f83a98c,\"Charleston, South Carolina (CNN)Police officers Saturday accompanied the hearse carrying the body of Walter Scott to his South Carolina funeral service, where …\",,,,\n054ccc280767c3d59e7da55572425d2fdcb6e711,\"(CNN)A judge this week sentenced a former TSA agent to six months in jail for secretly videotaping a female co-worker while she was in the bathroom, prosecutor…\",,,,\n07f60889bcd1f3d2c48b715220f13df8d2c5e158,(CNN)There's an old saying which states the Cape Verde Islands are home to a greater number of musicians per square kilometer than any other country in the wor…,,,,\n0a6b027b3384e79929c19b94062882db8c7f91fc,(CNN)Arsenal kept their slim hopes of winning this season's English Premier League title alive by beating relegation threatened Burnley 1-0 at Turf Moor. A fir…,,,,\n0b66cb7ebcfd16de6d6d7623036c2dd9161f032b,(The Hollywood Reporter)The original cast of Twin Peaks is backing David Lynch in his salary standoff with Showtime. The stars have teamed together for a video…,,,,\n0d3c8c276d079c4c225f034c69aa024cdab7869d,\"(CNN)Andrew Getty, one of the heirs to billions of oil money, appears to have died of natural causes, a Los Angeles Police Department spokesman said. The coron…\",,,,\n0f39feebc34fee03b8c647d1557eb40bb20f4e8b,(CNN)The mother of a quadriplegic man who police say was left in the woods for days cannot be extradited to face charges in Philadelphia until she completes an…,,,,\n12a3eec84bff4a1cfa3391479c9a259ecca5741b,\"(CNN)Malala Yousafzai's stellar career has included a Nobel Peace Prize. Last week, she made it into outer space. A NASA astrophysicist has named an asteroid a…\",,,,\n12d18fce81557ef7d4e34874e709376defd1819d,\"(CNN)Gastrointestinal illness has gripped 100 people on the cruise ship Celebrity Infinity, according to a report from the Centers for Disease Control. Of the …\",,,,\n130663882dcf622a6069d2ab429acde689b9f428,\"(CNN)\"\"Star Wars\"\" is once again back in our lives, the Burger-King couple helped us believe love can be found in fast food, and Mindy Kaling's brother had a sho…\",,,,\n17412737648b2cad59669560765fcb5169fc8116,(CNN)The FBI charged a Philadelphia woman on Thursday with trying to travel overseas to fight for ISIS. She's one of three women arrested this week on terror c…,,,,\n18e1af12d67995d1f20580b30bf7a7c8379a9009,\"(CNN)HBO just whetted our appetite for a new season of \"\"True Detective.\"\" The network released a teaser video for season 2 of the critically acclaimed show, and…\",,,,\n192bf513d8adb0c0dd49d0dae337632838a1090e,\"(CNN)Authorities identified and charged a man Monday in connection with the discovery of human remains in a duffel bag in Cambridge, Massachusetts, over the we…\",,,,\n1b2cc634e2bfc6f2595260e7ed9b42f77ecbb0ce,(CNN)He's a blue chip college basketball recruit. She's a high school freshman with Down syndrome. At first glance Trey Moses and Ellie Meredith couldn't be mo…,,,,\n1c26bc664022ab5ffb8bca0d077c5d72cac7976f,\"(CNN)In 2013, \"\"The Bible\"\" broke ratings records on the History Channel, so of course, a sequel was ordered up -- and this one is on NBC. The new miniseries fro…\",,,,\n1dd00c89d71a5611797bb34da8a6eada8f058405,\"(CNN)A year ago Bloomberg published a story with the following headline: Mike Pence, a Koch Favorite, Mulls 2016 Run for President. The story ticked off items …\",,,,\n1ecb11d97cc3290881a814fa863c1b06b6b96502,\"(CNN)The new emojis are here! On Thursday, Apple released a new version of its mobile operating system that includes more diversity than ever when it comes to …\",,,,\n202a51397a4de6483e6a7427d1952c46fca69d81,\"(CNN)When singer Avril Lavigne went missing from the music scene, there was tons of speculation. Was she pregnant? In rehab? Going through a split from her hus…\",,,,\n203886369feea77bbc35715e6d7e518b751f57de,\"(CNN)Seventy years ago, Anne Frank died of typhus in a Nazi concentration camp at the age of 15. Just two weeks after her supposed death on March 31, 1945, the…\",,,,\n20a6b5894c4cd75e32f6f4946467854aeb539337,\"(CNN)Two Alabama college students are accused of gang raping a woman while on spring break at Florida's Panama City Beach. Ryan Calhoun and Delonte Martistee, …\",,,,\n230c522854991d053fe98a718b1defa077a8efef,\"(CNN)Never mind cats having nine lives. A stray pooch in Washington State has used up at least three of her own after being hit by a car, apparently whacked on…\",,,,\n23b01320d93bb8a0fce96fb0dc37bcebf3f179cb,\"(CNN)The FBI has confirmed that one of its most wanted terrorists, the Malaysian bomb maker known as Marwan, was killed in an otherwise disastrous raid in the …\",,,,\n2549d3c10d5bc8ede708af559dd095271e0225e1,\"(CNN)The outlines of a nuclear deal with Iran are in place. Unfortunately, it seems like too many in President Barack Obama's administration have forgotten tha…\",,,,\n25a52d1de3a385d6d1405272f7dff0813fcd3b2d,\"(CNN)This is the end. Beautiful friend, the end. For the 1960s, the end arrived with -- depending on your ideals and your tribe -- either the Rolling Stones' A…\",,,,\n2af3d5505559f8c3d1728dbfac48da66b81af909,(CNN)Anyone who has given birth -- or been an observer of the event -- knows how arduous it can be. But to do it live on the Internet? With two hooves sticking…,,,,\n2b1b6a434b171e198413479aaba118f0cd20c843,\"Durham, North Carolina (CNN)President Obama's nomination of Loretta Lynch to become the country's first African-American woman attorney general is a historic p…\",,,,\n2b4eb5a283f51b54e1b0318936ae9bcfa70ce243,\"Kabul, Afghanistan (CNN)Three people were killed and five others were wounded Thursday afternoon when a group of armed assailants stormed into the attorney gen…\",,,,\n2bd8ada1de6a7b02f59430cc82045eb8d29cf033,\"(CNN)For the first time in eight years, a TV legend returned to doing what he does best. Contestants told to \"\"come on down!\"\" on the April 1 edition of \"\"The Pri…\",,,,\n2c05ddcc2bf50bd20dfc8c16f124d32867075b32,\"(CNN)Blues legend B.B. King was hospitalized for dehydration, though the ailment didn't keep him out for long. King's dehydration was caused by his Type II dia…\",,,,\n2dac7b4a9ed9eb9cfcabae0e8e0eb07abc5b8860,\"(CNN)After two days of deliberation, jurors found Dzhokhar Tsarnaev guilty on all counts in the Boston Marathon bombing. The verdict isn't surprising. What mig…\",,,,\n2f6106809de41d59f422d527900a6b344174c5b2,\"(CNN)A trip to a former heavyweight champ's gaudy, abandoned mansion. The tallest and fastest \"\"giga-coaster\"\" in the world. A dramatic interview with a famed sp…\",,,,\n2ffe3bdf91bdd8e12fc00fa02267545d8a0cb6da,\"London (CNN)The Pentagon released a map this week showing coalition forces have taken back 25-30% of Iraqi territory seized by ISIS. The map, above, shows gain…\",,,,\n32655a04c9e4733a1ae4b210a045bc6e0d443d85,Atlanta (CNN)A passenger on an Atlanta-bound Air Canada flight told a CNN reporter on the plane Friday that a stranger sitting behind him tried to choke him. O…,,,,\n32a7125a655a052b3ea62350a8e02f0245cc220e,\"(CNN)When Hong Kong police answered a call in the early hours of a Saturday morning last November, they encountered a grisly scene and an alleged crime that sh…\",,,,\n32f8af7757d529a19067a7a375316a0f5440c037,\"(CNN)In her 40 years living in Rochelle, Illinois, Cathy Olson had never seen a tornado that big. \"\"I saw the top of the funnel cloud, and it was absolutely mas…\",,,,\n33cab1f129c3b1f6578e597ea1a278a0c8338965,\"(CNN)That's some rich \"\"American Pie.\"\" The lyrics to the famed Don McLean song sold for $1.2 million Tuesday morning at an auction held by Christie's. \"\"Don McLe…\",,,,\n346c39e1a89203f1035541a114e7406521ff8b4e,(CNN)The commissioner-general of the United Nations Relief and Works Agency will make an emergency visit to the Yarmouk Palestinian refugee camp in Syria on Sa…,,,,\n357a3c6ad7f5add7f35198fa68585da8195367b4,\"(CNN)Residents of central Sanaa, the Yemeni capital, have learned the hard way that key strategic bombing targets are located in their neighborhoods: Detonatin…\",,,,\n36ac591f1b7a4eb01b7301b50912c5791c38386a,\"(CNN)Former Australia cricket captain and legendary broadcaster Richie Benaud has died at the age of 84. Benaud, whose witty one-liners from the commentary box…\",,,,\n37477ed1fc065f438021ee3b6d3e2b827e270353,(CNN)Sky watchers in western North America are in for a treat: a nearly five-minute total lunar eclipse this morning. Here's how it's unfolding: . It started a…,,,,\n3783ef06d42f795f34533caf346c2cb9d3c844dd,\"(CNN)A federal grand jury has charged millionaire real estate heir Robert Durst, a convicted felon, with unlawful possession of a firearm. In this week's indic…\",,,,\n384175be1c8d41610fbeddbd9d9cb46e716e2529,(CNN)Paul Walker is hardly the first actor to die during a production. But Walker's death in November 2013 at the age of 40 after a car crash was especially ee…,,,,\n386b182672cd041d574a3fe0e9ccf2f16b751f2e,\"(CNN)What do we have for the contestant on \"\"The Price Is Right\"\"? A brand-new car! Whoops. That wasn't supposed to happen. On Thursday's edition of the popular …\",,,,\n38a207accfb31afc694f16531d23d2cda79ac85d,\"(CNN)\"\"Jake the dog and Finn the human. The fun will never end. Adventure Time.\"\" So begins the dreamy theme song intro to the strangely addictive Cartoon Networ…\",,,,\n3bfe27dc86f0424787f32deb16df09a902c6a8e6,\"(CNN)It was like a scene out of \"\"Make Way for Ducklings\"\" on Tuesday on a rainy street in Washington. CNN Situation Room correspondent Brian Todd and photojourn…\",,,,\n3cf7f404fef8bef1cc9dab35b6931647a83c7ccd,\"Marseille, France (CNN)Investigators have collected all the main evidence from the site where Germanwings Flight 9525 crashed, a French national police officia…\",,,,\n3fbdee096ce9d027da681c5f9c89eb319ff21a9f,\"Havana, Cuba (CNN)All eyes are going to be on the new kid finally allowed to play and the big kid who for so long wanted nothing to do with him -- Cuba and the…\",,,,\n41592d02ca324abe370ff063962b97ca5d976e73,\"(CNN)\"\"Sell all that you own and distribute the money to the poor, and you will have treasure in heaven; then come, follow me,\"\" Jesus tells the rich man in one …\",,,,\n41c6edecee127c396d17e2e9115a4a89252cc52b,(CNN)The California Public Utilities Commission on Thursday said it is ordering Pacific Gas & Electric Co. to pay a record $1.6 billion penalty for unsafe oper…,,,,\n42c49513463e57bfb455edac643d5c05724940e0,\"(CNN)Lauren Hill, who took her inspirational fight against brain cancer onto the basketball court and into the hearts of many, has died at age 19. The Indiana …\",,,,\n43f18fc9b20fe64405d7f18a08fb8d9ef932ed8b,\"(CNN)A mammoth fire broke out Friday morning in a Kentucky industrial park, sending plumes of thick smoke over the area as authorities worked to contain the da…\",,,,\n4495ba8f3a340d97a9df1476f8a35502bcce1f69,\"(CNN)If you've been following the news lately, there are certain things you doubtless know about Mohammad Javad Zarif. He is, of course, the Iranian foreign mi…\",,,,\n44d681105bcab063dfa0c80ce9cf96393677f9cc,\"(CNN)A Connecticut teen who has been forced to have chemotherapy to treat Hodgkin lymphoma will remain in temporary custody of the state for the time being, ac…\",,,,\n454434c7bf77d898feba8ff0e38a2d1dd68c44ba,\"(CNN)\"\"Hamlet.\"\" \"\"Romeo and Juliet.\"\" \"\"A Midsummer Night's Dream.\"\" For centuries, these plays and three dozen more by William Shakespeare have formed history's mo…\",,,,\n469c6ac05092ca5997728c9dfc19f9ab6b936e40,\"Marseille, France (CNN)The French prosecutor leading an investigation into the crash of Germanwings Flight 9525 insisted Wednesday that he was not aware of any…\",,,,\n4bd20bce9066eb3e0950299a340faa935026fe5a,\"(CNN)Emy Afalava is a loyal American and decorated veteran. He was born in American Samoa, a U.S. territory since 1900. He has been subject to American law his…\",,,,\n4cc5744a14d8a07414760b271c1801c670149f68,(CNN)Blue Bell ice cream has temporarily shut down one of its manufacturing plants over the discovery of listeria contamination in a serving of ice cream origi…,,,,\n4fbf675fb79046440d1cf01dd4fc2e505f2b5169,\"(CNN)The terrorist group Al-Shabaab has claimed an attack on Garissa University College in eastern Kenya, in which many people have been killed and still more …\",,,,\n5139ccfabee55ddb83e7937f5802c0a67aee8975,\"(CNN)After a Russian fighter jet intercepted a U.S. reconnaissance plane in an \"\"unsafe and unprofessional manner\"\" earlier this week, the United States is compl…\",,,,\n5231a93ff48e3dcdc22ea9df981237c26a474714,\"(CNN)A hooded angel with black wings appeared on Tuesday near the spot where Walter Scott was shot and killed by a police officer in North Charleston, South Ca…\",,,,\n5362f24162b3ed6f36037319ee66fbaaddc50650,(CNN)Eyewitness video showing white North Charleston police Officer Michael Slager shooting to death an unarmed black man has exposed discrepancies in the repo…,,,,\n5493b9481b00e8ca9d83320d00abe09266bbeaef,\"Irbil, Iraq (CNN)ISIS claimed it controlled part of Iraq's largest oil refinery Sunday, posting images online that purported to show the storming of the facili…\",,,,\n574767c29dfee14ea227639f45387c07437a55e5,\"(CNN)Recently, Nashville's district attorney banned prosecutors from offering female sterilization in plea deals. Believe it or not, Nashville prosecutors have…\",,,,\n578677b3280b0f5ab8b45fdd948707262c9ffed3,\"(CNN)Over the last year more than 25,000 people, a population about the size of Key West, Florida, have fought Ebola infections. More than 10,000 have not surv…\",,,,\n58b9fcb9a3537d014d3499b0ad4d4123cfd3eac0,\"(CNN)After years of making the case that the education of athletes is paramount, the NCAA now says it has no legal responsibility to make sure education is act…\",,,,\n599bf6f13bc8477d50aa7599baf53123a6e57708,\"Hong Kong (CNN)Six people were hurt after an explosion at a controversial chemical plant in China's southeastern Fujian province sparked a huge fire, provincia…\",,,,\n5a4f7f0a9cc7a0e70ec80fd9238ed98b531ecbbb,(CNN)I'm haunted by the video of Officer Michael Slager firing eight shots at Walter Scott as he fled his encounter with North Charleston police -- his back tu…,,,,\n5a650587a76e9eb9c03612c7064bbee9f552ebec,(CNN)The VII Summit of the Americas was supposed to be all about the symbolic handshake between the United States and Cuba. But insert Venezuela into the mix a…,,,,\n61a6105642804ffdb55a3b78f74380f8d099cde6,\"(CNN)A nuclear submarine being repaired at a Russian shipyard has caught on fire, according to a law enforcement source speaking to Russia's state-run news age…\",,,,\n6222f33c2c79b80be437335eeb3f488509e92cf5,(CNN)Filipinos are being warned to be on guard for flash floods and landslides as tropical storm Maysak approached the Asian island nation Saturday. Just a few…,,,,\n6302a6cf8564e4bb4753e2dc3dae328f13edae50,\"(CNN)Deion Sanders is such a dad. The NFL legend called out Deion Sanders Jr. on Twitter for saying he only eats \"\"hood doughnuts.\"\" In response, the elder Sande…\",,,,\n6344c9689865cf86da50fbe90acf13c3407d5429,\"(CNN)For 12 years Adelma Cifuentes felt worthless, frightened and alone, never knowing when her abusive husband would strike. But as a young mother in rural Gu…\",,,,\n63e19d477469e39e3fc4143919e6a5acb58dbc23,\"(CNN)Police in the Indian city of Malegaon, in the western state of Maharashtra, are requiring identity cards for an unusual group of residents: Cattle. Follow…\",,,,\n63ee59d69982f3f73bb33da9880747c8138dbea4,\"(CNN)Police in India are putting aside their batons in favor of an overhead solution to angry and unruly crowds: pepper-spraying drones. Yashasvi Yadav, Senior…\",,,,\n646cba2e8b30945a2079ec4c671740d5db5676e2,\"(CNN)\"\"A long, long, time ago...\"\" Those five words, when uttered or sung, makes baby boomers immediately think of Don McLean's pop masterpiece \"\"American Pie.\"\" I…\",,,,\n68382576e6999d52ff2d16777add23a5cea605f0,\"London (CNN)It wasn't messrs Clooney, Pitt and their nine accomplices who sailed down an elevator shaft and cracked open dozens of safety deposit boxes at a Lo…\",,,,\n695fecd970abb3f1679615e6d2cdd9d65f94f9f4,\"(CNN)Bring your own beaker, goblet or vase and slurp it up. 7-Eleven is hosting the first Bring-Your-Own-Cup Slurpee Day at United States stores from 11 a.m. t…\",,,,\n69af3b9fc4ba1fa6bd272c82d17ec318da5ff97a,\"(CNN)When I was elected to the Kentucky State Senate in 1967, I became the first woman and the first person of color to serve in the body. Five decades later, …\",,,,\n69e1f777e41bf67d5a22b7c69ae76f0ae873cf43,(CNN)What was supposed to be a fantasy sports car ride at Walt Disney World Speedway turned deadly when a Lamborghini crashed into a guardrail. The crash took …,,,,\n6c4ed9b048e05aebceee87dc492ef555e0dca128,(CNN)It took prosecutors months to present 131 witnesses to support their claim that former NFL star Aaron Hernandez killed semi-pro player Odin Lloyd. On Mond…,,,,\n6ce9f3ddbed94dc2223aea4b851ebedbb67f8c56,\"(CNN)Last month Wu Rongrong was taken into custody for planning to protest on International Women's Day against sexual harassment in China. Since then, the Chi…\",,,,\n6da088a4a4c512402649d361e95ac8b256ddf529,\"Des Moines, Iowa (CNN)Martin O'Malley told reporters in Iowa on Friday that inevitability -- a term bandied about regarding Democratic presidential frontrunner…\",,,,\n72610cfcc7b8bc1e90a08d8cac4f7b53a1e1389b,\"(CNN)Ursula Ward kept repeating her son's name -- Odin. She steadied herself against the podium in the Fall River, Massachusetts, courtroom and occasionally pa…\",,,,\n72df456684b62acd43db2ac9bb23f509b9b53942,\"Cedar Falls, Iowa (CNN)As aides politely tried to rush Ted Cruz from an event in Cedar Falls to one in Cedar Rapids, Iowa, on Thursday, the presidential candid…\",,,,\n74b24c60df8b6c07fc2714997a7cb0b59c4d2e2a,\"(CNN)For superhero fans, the cup runneth over. Most of us know the members of the Avengers by now: Iron Man, Captain America, Hulk and the rest, and the fact t…\",,,,\n74e99c26d8bb7ef87afa0784082c2918927e753e,\"(CNN)Desperate migrants from Africa and the Middle East keep heading to Europe, with 978 rescued Friday in the Mediterranean Sea, the Italian Coast Guard said …\",,,,\n76a518ad3aa590fbac1b9e6e68634fe4709270ed,(CNN)A French-language global television network regained control of one of its 11 channels Thursday after a cyberattack a day earlier crippled its broadcasts …,,,,\n78a670384c908a15617cab7f575fd50dc5999937,\"(CNN)Film director David Lynch has confirmed he will no longer direct the revival of \"\"Twin Peaks\"\" -- a cult 1990s television show that was set to return in 201…\",,,,\n7b8bb308a48e838c9d7f3fee08d4670efd305463,(CNN)The nation's top stories will be unfolding Tuesday in courthouses and political arenas across the country. Massachusetts is hosting two of the highest-pro…,,,,\n7d5b44afe30b34c03f77f0e5ebf5eb88498ee71c,(CNN)Tornado sirens blared Wednesday night in Kansas as several storms brought reports of twisters. Spotters reported a tornado about 6 miles northwest of Godd…,,,,\n7e4d197d5fe8272c0471199cf9987f3786a80c2b,(CNN)Jodi Arias was sentenced to life in prison Monday for the gruesome 2008 murder of her ex-boyfriend Travis Alexander. Maricopa County Judge Sherry Stephens…,,,,\n7fb513044e371fa3354fc08eaac50975cf65666a,\"(CNN)The presence of a harmful pesticide at a luxury villa in the U.S. Virgin Islands may have resulted in the illness of a Delaware family, the U.S. Environme…\",,,,\n8012ab9261e117ab47a2759b3c0b628f2a007a82,\"(CNN)According to an outside review by Columbia Journalism School professors, \"\"(a)n institutional failure at Rolling Stone resulted in a deeply flawed article …\",,,,\n82461522ee90f8f5be2ec226e2016ad40588866d,\"Atlanta (CNN)It was a scene worthy of any top cop show on TV -- bullets flying, banged-up cars and the FBI chasing an armed robbery suspect. In the end, two ag…\",,,,\n837970f6b544e927c6fe2261a81f74f8313f2bdf,(CNN)Getting caught napping on the job is never good. Getting caught napping on the job in the cargo hold of a plane takes it to a whole different level. Alask…,,,,\n84c9dd43080eba5a11a28798a570ccaea75ff42d,\"(CNN)Craig Hicks, who is charged in the deaths of three Muslim college students in Chapel Hill, North Carolina, earlier this year, can face the death penalty, …\",,,,\n84dabfdd73c25b81b7ea0ce23e74638cc6c559ce,\"(CNN)An Amnesty International report is calling for authorities to address the number of attacks on women's rights activists in Afghanistan. The report, entitl…\",,,,\n8610ead0a43054be202a1fc756620415a6d572fe,\"(CNN)Recently, a New York judge issued an opinion authorizing service of divorce papers on a husband completely via Facebook. What exactly is \"\"service of proce…\",,,,\n88e7dac40f3e6c159e4edc0747d0cc0f50886fbb,\"(CNN)The Rev. Robert H. Schuller, California televangelist and founder of the television ministry \"\"Hour of Power,\"\" died Thursday, according to his family. He w…\",,,,\n8911c07945c382306d5aba8cf6c513c0c8ce61d0,(CNN)Four workers died in a massive oil rig fire that raged for hours off the coast of Mexico Wednesday. Mexican state oil company Pemex said 45 workers were i…,,,,\n89daa80db49b6e36c1cd0bde9b253ca7fa143811,\"(CNN)A new Kansas law banning a common second-term abortion procedure is the first of its kind in the United States. The law, signed by Kansas Gov. Sam Brownba…\",,,,\n8ba20bec4358b39f84a8a07264f71566bb3c5e8e,(CNN)A popular Chinese television host known for impromptu satire is now the subject of controversy after being caught on camera cursing the late Chairman Mao …,,,,\n8be49747e364357d7c5d32fca516ec230e5083ed,\"(CNN)A University of Kentucky basketball player is apologizing for the \"\"poor choice of words\"\" he muttered under his breath after the team's stunning loss to Wi…\",,,,\n8ec9aabea31ae79f0d429e9ab2e4a1a4f8d1b605,\"(CNN)For those wondering if we would ever hear from the Bluth family again, the answer would appear to be yes. \"\"Arrested Development\"\" executive producer Brian …\",,,,\n934a2d9235022c9e8a6aeec5e7e941b127569b76,\"(CNN)The world's biggest and most powerful physics experiment is taking place as you read this. The Large Hadron Collider (LHC), a particle accelerator and the…\",,,,\n9378a8d4b9a6d21fed266f63692b1da961172363,\"Washington (CNN)An Iranian military observation aircraft flew within 50 yards of an armed U.S. Navy helicopter over the Persian Gulf this month, sparking conce…\",,,,\n947b339a524aac1f43384a8c68e5a3a624ed309f,\"Boston (CNN)Guilty across the board. But will he face death? After deliberating for 11½ hours, jurors found Dzhokhar Tsarnaev guilty on Wednesday of all 30 cou…\",,,,\n947eeb8bbfec54f46a6ee0dd066b7bd6007dc630,\"New Delhi, India (CNN)Police have arrested four employees of a popular Indian ethnic-wear chain after a minister spotted a security camera overlooking the chan…\",,,,\n970f75d6e5b23e11c15b05c59a109ccbb160b289,\"(CNN)Since Iran's Islamic Revolution in 1979, women have been barred from attending most sports events involving men. But the situation appears set to improve …\",,,,\n978a6fc6a910592f6be5add104474e7d9ba428c5,New Delhi (CNN)An Indian software pioneer and nine others have been sentenced to seven years in jail for their role in what has been dubbed India's biggest cor…,,,,\n97c0670cd614dc25fe1371f8c5e03b043f0efdc9,\"(CNN)All Elizabeth Sedway wanted was to leave paradise and head home. But she couldn't. Why? Because, according to her, she has cancer. That's what she said in…\",,,,\n996940764a066a9c16f622c873ad041ac5521fa3,\"(CNN)Kayahan, one of Turkey's best-loved singers and songwriters, died of cancer Friday at the age of 66. He had performed most recently in Istanbul on Valenti…\",,,,\n9a2ffa6ad643d52e6b99b0b08e497f41ba23b2b2,\"Washington (CNN)Israeli Prime Minister Benjamin Netanyahu criticized the deal six world powers struck to thwart Iran's nuclear ambitions, saying he sees better…\",,,,\n9b54bd1709bdcad40b3d57f57f59a7631868132b,Washington (CNN)Washington was rocked late Thursday by shootings -- one at the gates of the U.S. Census Bureau's headquarters and another in a popular area pac…,,,,\n9bea5cbe9a0184eec4086a08452066dead185173,\"(CNN)Imprisoned soldier Chelsea Manning can now communicate with the world -- in 140 characters or less. Manning, who is serving a 35-year prison sentence for …\",,,,\n9dc3325d901844d26713549fd93f7b42b70efe5b,\"(CNN)Hip-hop star Nelly has been arrested on drug charges in Tennessee after a state trooper pulled over the private bus in which he was traveling, authorities…\",,,,\n9eb7dd37e50b863e99b554ed340e7b766c1b6329,(CNN)A Delaware father is in stable condition and improving as his two boys remain in critical condition after they became sick -- perhaps from pesticide expos…,,,,\n9f051fe922a8f45b315a366a5af1aab58d93f050,\"(CNN)Just as mimeograph machines and photocopiers were in their day, online activity -- blogs, YouTube channels, even social media platforms like Facebook and …\",,,,\n9fbd984bd3a49c69074601a62d5d1d05bbeb2237,\"(CNN)Just kill it already. That was the sentiment of many \"\"Vampire Diaries\"\" fans on Tuesday after star Nina Dobrev announced she will be leaving the CW show at…\",,,,\na168d9139450678679e8dd7ddfa9fd5b8f8d1c7b,\"(CNN)Even in the horror of Syria's civil war, there are few places that showcase the scale of the destruction -- and the senselessness of the loss of life -- m…\",,,,\na2363d02185ba79b223bf7290b390cf65f81dd50,\"(CNN)Are we alone in the cosmos? Or might there be intelligent life elsewhere? Last week, NASA scientists discussed in very concrete terms the steps to discove…\",,,,\na2a2ac30f4650050ee114a48316e7451936692ca,\"(CNN)A 32-year-old Massachusetts man is facing murder charges, authorities said Wednesday, four days after another man's remains were found in a duffel bag. Th…\",,,,\na2b66e4376258cd41604d654a395f7540d2e8514,\"(CNN)Kanye West has settled a lawsuit with a paparazzi photographer he assaulted -- and the two have shaken on it. The photographer, Daniel Ramos, had filed th…\",,,,\na2ee2faeb2dc4e5eab43b1d14233c4ac658f0a8f,\"(CNN)President Barack Obama tied himself to the mast of a nuclear deal with Iran even before he became the Democratic candidate for president. Reaching a good,…\",,,,\na37f0005819d1973a72a8bac4cbee8bbb28c16dd,(CNN)It's a good thing -- a lucky thing -- that a bystander had the courage and presence of mind to record the shocking video that shows a white police officer…,,,,\na38e72fed88684ec8d60dd5856282e999dc8c0ca,\"(CNN)Five Americans who were monitored for three weeks at an Omaha, Nebraska, hospital after being exposed to Ebola in West Africa have been released, a Nebras…\",,,,\na43893ac704663476a285673392de84c0c17d4e5,\"(CNN)Mark Ronson's \"\"Uptown Funk!,\"\" featuring Bruno Mars, is the longest-leading Billboard Hot 100 of the 2010s, ruling the chart for a 13th week. It's also jus…\",,,,\na8c1b6fc67380b8b4a542a6a2512a2f3c2d07d45,\"(CNN)Pardon us, \"\"Lost\"\" fans, but April 8 wasn't only your day. Yes, we know the significance of April 8, 2015, and the alignment of 4:23.42 p.m. on that date t…\",,,,\nafd04a7bf645f376ba6d6ba5880a4725431793c1,\"(The Hollywood Reporter)\"\"Grace of Monaco,\"\" starring Nicole Kidman as star-turned-princess Grace Kelly, is heading straight to Lifetime. The critically-panned f…\",,,,\nb10db3ae83abe1eec4236126d9c195ed7db90cc3,\"(CNN)One of Tokyo's most prominent districts has taken a small, but potentially significant step to recognizing same-sex unions in Japan. The government of Shi…\",,,,\nb21cd549314996de79ba0ca2636c8ced66468267,\"Los Angeles (CNN)It's more than just one state's internal problem. The historic California drought hurts the rest of the union, too. That's because California …\",,,,\nb3619076f8eba9b3dcd53d10a5c54b590bfab1e2,\"(CNN)The University of Michigan has decided to proceed with a screening of the film \"\"American Sniper\"\" despite objections from some students. More than 200 stud…\",,,,\nb540aeae06b011f092bff5efc36df3bdc64215cb,\"(Billboard)From Channing Tatum twerking for Jennifer Lopez to host Amy Schumer's archery fail, there were plenty of highlights and misfires from the 2015 MTV M…\",,,,\nb7c282a0373913300e4cb1d5bb529c068b550618,(CNN)Those poor fish must have been wondering what the heck was happening to them. The Oregon Parks and Recreation Department has reported that a section of a …,,,,\nb882ed05925f8879660ec4f9efdcded1d5e45561,\"(CNN)One year after it was perpetrated, the kidnapping of nearly 300 schoolgirls by a jihadist group in Nigeria remains a crime almost too horrifying to compre…\",,,,\nb8e56b3cb5faa8d68341738b5708168e5cf18e2f,\"(CNN)Easter is unique on the Christian calendar, a major point in the cycle of the religious year, and one that has always been able to resist the commercializ…\",,,,\nbbdc0e58a203b016166f896936d9862ae9fd11be,\"Nairobi, Kenya (CNN)Kenya froze dozens of accounts linked to suspected terror supporters after militants massacred 147 people last week at a university in Gari…\",,,,\nbbe26fc38175793719dd50c23605f1c96c579b08,\"(CNN)What would you do if a complete stranger asked you for $100, or offered you an apple in a parking lot without explanation? These are only two of the 100 c…\",,,,\nbe5d8524bf21d485e203425d764ed60a3bf71b8d,\"(CNN)No prostitutes. No ifs, ands or buts -- and yes, that includes when and where prostitution is perfectly legal. That was the message Friday from Attorney G…\",,,,\nc0340e53445e1d38aaf9a2681c2ae2e950a98860,\"(CNN)The killing of an employee at Wayne Community College in Goldsboro, North Carolina, may have been a hate crime, authorities said Tuesday. Investigators ar…\",,,,\nc222979bd1cfbc7d3ff821e9c738e3dbd29b14f4,\"(CNN)On May 28, 2014, some 7,000 people gathered in a stadium in China's northwestern Xinjiang region. But they had not come to watch the local football team o…\",,,,\nc27cf1b136cc270023de959e7ab24638021bc43f,\"(CNN)A Duke student has admitted to hanging a noose made of rope from a tree near a student union, university officials said Thursday. The prestigious private …\",,,,\nc34d84d38ccfd021ba0b3712dc23feadd455af5b,\"(The Hollywood Reporter)Richard Dysart, the Emmy-winning actor who portrayed the cranky senior partner Leland McKenzie in the slick, long-running NBC drama \"\"L.…\",,,,\nc5390093fa60d62c4dc9013977ca09a8edf7c32b,\"(CNN)Easter is a cornerstone event in the Christian faith, but it's surrounded by interesting quirks. It celebrates the completion of Christ's mission of salva…\",,,,\nc67a5be9af71197193435ab7073e964298851089,(CNN)Comedian Chris Rock made light of racial disparities in police treatment of whites and blacks with a tongue-in-cheek guide to not being beaten by the poli…,,,,\nc71b08cede3b6edb662a2f2c95f8b543fa65e405,\"Atlanta (CNN)Robert Lewis Burns Jr., the original drummer in Southern rock band Lynyrd Skynyrd, died Friday night in a car crash, a Georgia State Patrol spokes…\",,,,\nc7a2fff8169408776d5f35229fb5c3fcb9b2523c,\"(CNN)#UporDown? That's the trending question on social media, thanks to a photo of a cat coming down some stairs. Or is it going up some stairs? (And you thoug…\",,,,\nc7caf9181c2e94a79d9102da6e11cde48c880aa5,\"(CNN)The United States and its negotiating partners reached a very strong framework agreement with Iran in Lausanne, Switzerland, on Thursday that limits Iran'…\",,,,\nc811d9ae87c9bfbf31481bf8a916dc0b8e083a60,(CNN)There was a larger message in the article about a purported gang rape that Rolling Stone retracted on Sunday night -- a part of the story that was never d…,,,,\nca1c3b587b7216654c8c719a66738de80d495179,\"(CNN)Chris Copeland of the Indiana Pacers was stabbed after leaving a trendy New York nightclub early Wednesday, and two Atlanta Hawks -- who had just finished…\",,,,\ncb56840e21bbf8a71cd0337b5908d3f783862ae0,\"(CNN)They're not gonna take it anymore. Really. Twisted Sister says that its 2016 tour will be its last, according to a press release. Next year marks the band…\",,,,\ncc86a588b4e4e038e2591c363b4b895e46edbeda,\"(CNN)Buzz has surrounded HBO's new documentary \"\"Going Clear: Scientology and the Prison of Belief,\"\" but Scientologist John Travolta is not a fan. Travolta told…\",,,,\ncd745b3c66da579d0538e668fde2922c0b3bc9f5,\"(CNN)Fans of the late actor Paul Walker knew that watching him in \"\"Furious 7\"\" would be bittersweet. Even so, many moviegoers said the final scenes of the new f…\",,,,\ncf3f7388c3b51980ead39a8e701c7a4860d9f77c,\"(CNN)Where do you go from here? The fourth season of \"\"Game of Thrones\"\" saw massive battles, major deaths (Tywin!) and White Walkers, but what can fans expect S…\",,,,\ncf7094270cbb4c8fad5029bd2c2da694f1411870,\"(CNN)It's the kind of thing you see in movies, like Robert Redford's role in \"\"All Is Lost\"\" or Ang Lee's \"\"Life of Pi.\"\" But, in real life, it's hard to swallow t…\",,,,\nd71e9a0213b10081afe70fa288f6fd351d942468,\"(CNN)\"\"Star Wars\"\" fans will get more than they bargained for when the saga comes to digital HD on Friday. The collection of the first six \"\"Star Wars\"\" movies wil…\",,,,\nd8aee1ae4b1130afbf0572a49afc2f5366b181c9,(CNN)Rebekah Gregory blinked back tears as she thought about the verdict. It had been almost two years since Dzhokhar Tsarnaev and his brother planted bombs at…,,,,\nd96576c5c5e667d33e2f2117584bf796bd66389a,\"Beijing (CNN)China's state prosecutors on Friday formally charged the country's former security czar with accepting bribes, making him the highest-ranking Chin…\",,,,\nda9588f556b1c3575e7ad2109967fa3156699813,\"(CNN)For more than four days, police say, a 21-year-old quadriplegic with cerebral palsy was left lying in the woods of Philadelphia's Cobbs Creek Park with on…\",,,,\ndc833f8b55e381011ce23f89ea909b9a141b5a66,\"(CNN)As goes Walmart, so goes the nation? Everyone from Apple CEO Tim Cook to the head of the NCAA slammed religious freedom laws being considered in several s…\",,,,\ndc8bb8429f624c4cceea3caae72874acb85e69b3,\"(CNN)I remember the day I stopped praying. It was the day after my little brother, Jimmy, died of cancer. He was 25. I was so angry at God. I was 27 at the tim…\",,,,\ndd4f726200355d742f631777aaa7b265533c0baf,\"(CNN)Their relationship led to jail time for her, but Mary Kay Letourneau Fualaau wants the world to know that she and her husband, Vili Fualaau, are still hap…\",,,,\ne21f3aefeb41b20bc197297ad55d2e2a8933fc45,(CNN)Hillary Clinton finally answered the question we've all been asking for years: Will she run for president in 2016? With official news of her candidacy jus…,,,,\ne2706dce6cf26bc61b082438188fdb6e130d9e40,\"(CNN)Governments around the world are using the threat of terrorism -- real or perceived -- to advance executions, Amnesty International alleges in its annual …\",,,,\ne2bccd4dec93c9bb7b327827dae004c2d494ec31,\"(CNN)The classic video game \"\"Space Invaders\"\" was developed in Japan back in the late 1970's -- and now their real-life counterparts are the topic of an earnest…\",,,,\ne30518a464ea7096b1aa5a17b45570631e3cf080,\"(CNN)Boston native Mark Wahlberg will star in a film about the Boston Marathon bombing and the manhunt that followed, Deadline reported Wednesday. Wahlberg's f…\",,,,\ne3f8ceb7a6271bb978b2bb47978054f58390852e,\"Waterloo, Iowa (CNN)Martin O'Malley and Jim Webb share little in common. Both Democrats are toying with a presidential run, both are facing long odds in that e…\",,,,\ne4fcad9e8cf8acbf076000d7232e9513dafb6743,\"(CNN)Nine British citizens were arrested in Turkey on Wednesday, suspected of trying to cross illegally into Syria, the Turkish military said on its website. T…\",,,,\ne65440d2469c8d9fc44b6121ca6e7fd25e272eab,\"(CNN)The United States Department of Justice has named a new defendant in the war on drugs, and the charges are serious indeed. A 15-count indictment filed in …\",,,,\ne67604ecb75aa21391e1d15a577d16b8db990de5,(CNN)One hundred and forty-seven victims. Many more families affected. Even more broken hopes and dreams. As Kenyans mourned those killed last week in one of t…,,,,\ne6c7c16699d2400824d9ea25f8dca04c575ba677,\"(CNN)When photographer Johan Bavman became a father for the first time, he took more than a passing wonder about how his native Sweden is said to be the most g…\",,,,\ne709f9942da05f8747aa6bc61952de27090512ac,\"Washington (CNN)President Barack Obama says he is \"\"absolutely committed to making sure\"\" Israel maintains a military advantage over Iran. His comments to The Ne…\",,,,\ne8c90d557031700caa1afb66dfc85358ef719108,\"(CNN)The United States has seemingly erupted this week about what it means to live your religion, especially in Indiana, where its new Religious Freedom Restor…\",,,,\neaf4a7864208468af3cdc858185b807d54110e95,\"(CNN)Five young Chinese feminists, whose detention has provoked an international outcry, may face up to five years in prison over their campaign for gender equ…\",,,,\neb39e1395ad10fd27f5688d5f7f589e1eac61738,\"(CNN)Tejano star Selena, who died 20 years ago, is coming back in a big way: with a hologram-like figure. Billboard reports that the singer's family is creatin…\",,,,\nec4b5fef725b4cc81545689603ff84c8e19bd6dc,\"(CNN)Michele Bachmann is comparing President Obama to the co-pilot of the doomed Germanwings flight. \"\"With his Iran deal, Barack Obama is for the 300 million s…\",,,,\necb2616fc4fbb5b42ee775ed80b21f08b6e304e8,\"(CNN)A year after its Cannes debut and finally seeing a theatrical release, \"\"Lost River\"\" is still causing quite a stir. Booed at its premiere and mocked by rev…\",,,,\nee17dfb574feca82ccac5689595e47483bd23f12,\"London (CNN)A 19-year-old man was charged Wednesday with terror offenses after he was arrested as he returned to Britain from Turkey, London's Metropolitan Pol…\",,,,\neeafdc8b2d8130cabda5aafe352eab1198d0b9f8,\"(CNN)If you're famous and performing the American national anthem, be prepared to become a national hero or a national disgrace. Facts are facts. Just ask Vinc…\",,,,\nef92201afc2d9a4aa64448a9f5ae8b6a712fa9e4,\"(CNN)The graffiti, written in a French chalk quarry and dating back almost 100 years, is plain and stark. \"\"HJ Leach. Merely a private. 13/7/16. SA Australia,\"\" …\",,,,\nf001ec5c4704938247d27a44948eebb37ae98d01,\"(CNN)The Palestinian Authority officially became the 123rd member of the International Criminal Court on Wednesday, a step that gives the court jurisdiction ov…\",,,,\nf1c555fe64f94df1f8c6afecf1ae4c0d78f6efa8,(CNN)Anthony Ray Hinton is thankful to be free after nearly 30 years on Alabama's death row for murders he says he didn't commit. And incredulous that it took …,,,,\nf309d4d0aabf03a015bb1125544d916aa6fe520d,\"(CNN)Danny Kahneman, my good friend and co-author who got a Nobel Prize in economics, once helped to run an experiment involving patients undergoing colonoscop…\",,,,\nf555b81fb888354a9a83ba9acc1bdb18791441ca,\"(CNN)Saturday at the Masters, like any PGA tournament, has been dubbed 'Moving Day'. It's the day after the fat has been cut and the big dogs make their move u…\",,,,\nf66c8ff2cad2a7c8fcfae64e5e00f0bce75334b2,\"New York (CNN)When Liana Barrientos was 23 years old, she got married in Westchester County, New York. A year later, she got married again in Westchester Count…\",,,,\nf78024d271fd21f0667f5da6843516314af71f8f,(CNN)Standing up for what you believe. What does it cost you? What do you gain? Memories Pizza in the Indiana town of Walkerton is finding out. The family-run …,,,,\nf78fb08d7ccc8bf7d4a376d5a885c5ab54026a6f,\"(CNN)You may know Mindy Kaling from Fox's cult hit comedy \"\"The Mindy Project,\"\" in which she plays Mindy Lahiri, a perky, quirky OB/GYN juggling her career and …\",,,,\nf7c2eb465479b965669b81535234e24735915ebf,(CNN)A high temperature of 63.5 degrees Fahrenheit might sound like a pleasant day in early spring -- unless you're in Antarctica. The chilly continent recorde…,,,,\nf8e429a6906f299a0925f6d70e2570834a7b8dc6,\"(CNN)Do you remember the talk about plans for Iraqi-led force to try to take back Mosul this spring? Well, you might want to forget it. Nearly three months aft…\",,,,\nf97442bee2acf684b1b8d5e653acea2307fc5dad,\"(CNN)Irish betting company Paddy Power is backtracking after tweeting that \"\"Newcastle have suffered more Kop beatings over the last 20 years than an unarmed Af…\",,,,\nf97b9b19e5a90dce0fc0b098f2a7f70ec36445fb,\"(CNN)Police added attempted murder to the list of charges against the mother of a quadriplegic man who was left in the woods for days, Philadelphia police spok…\",,,,\nf9f5d81bc74d6cf6d713d6fa6be4a30427b46e68,\"Seoul, South Korea (CNN)The man accused of stabbing U.S. Ambassador Mark Lippert in Seoul last month is now charged with attempted murder, a South Korean court…\",,,,\nfcd69b35b0bdae540d8357d0029369ab3cef1363,\"(CNN)The first daughter to be married from the hit reality show \"\"19 Kids and Counting\"\" has also become the first mother. People magazine reports that Jill (Dug…\",,,,\nfd0e8622b9ee38d1d6fff2fff59f0566f1a2f8f7,\"(CNN)Universal's \"\"Furious 7\"\" continues to build momentum at the Friday box office for a weekend debut in the $135 million-$138 million range, the largest openi…\",,,,\nff42fad959e8b522b562b7b715c8d558270a79f2,\"(CNN)Just as the agency begins to recover from a series of high-profile missteps, the Secret Service is facing yet another scandal. A female employee accused X…\",,,,\nff4cf78e837bd36ead5799c8051d22a8d7b9b178,(CNN)Hillary Clinton is finally announcing her candidacy for the 2016 presidential election. Although she has watched her standing in the polls sag in recent m…,,,,\nff866754ef03f2e2e4a2148c6a8ef2b8bda84832,(CNN)Change is coming to Ferguson. In the next few weeks the Department of Justice (DOJ) will begin to negotiate in earnest with the city to restructure the po…,,,,\nff9c1536bfa6ee669b800b6e9db04d9a9751dda1,\"Abu Dhabi, United Arab Emirates (CNN)Lost luggage after a long flight is a common, frustrating occurrence of modern air travel. And sometimes, airlines lose th…\",,,,\nffff11a2f44d731cd80c86819a89b7e227581415,\"Norfolk, Virginia (CNN)The second mate of the Houston Express probably couldn't believe what he was seeing. Hundreds of miles from land there was a small boat …\",,,,\n",
 "round5": {
  "baseline": {
   "goal": "news_summary_cnn",
   "dataset": "cnn_dailymail_200",
   "current": 1,
   "promoted_from": "cnn_bart_l_n200_v1_20260926T153757Z",
   "promoted_at": "2026-10-25T14:08:24Z",
   "reason": "bart_l (BART-large-CNN, MIT, $0 on a CPU) leads on coverage at 0.3461, not significantly different from deepseek_m (0.3460, p = 0.99), for CNN-style text; rent deepseek_m if you need speed. REPORT_SUMMARIZATION, executive summary.",
   "actor": {
    "from": "migration",
    "name": "before 0.8.0",
    "type": "unknown"
   },
   "history": [],
   "migrated": true
  },
  "baselines": 8,
  "study": {
   "goal": "g",
   "study": "s1",
   "status": "ended",
   "round": "r1",
   "baseline": "one_v1",
   "trials": [
    {
     "actor": {
      "from": "environment",
      "name": "owner",
      "type": "person"
     },
     "at": "2026-11-12T12:49:26Z",
     "change": {
      "params": {
       "sentences": 2
      },
      "prompts": []
     },
     "config_id": "s1-t1",
     "cost_usd": 0.0,
     "event": "trial",
     "from": "one_v1",
     "hypothesis": "sentences = 2 (how much of a ticket to keep)",
     "k": 1,
     "nominal": true,
     "outcome": "kept",
     "rationale": "grid: the next value of the group",
     "reason": "beat the best so far by 0.25 (needed more than 0)",
     "runs": [
      "s1-t1_20261112T124925Z"
     ],
     "shown": [],
     "vs_baseline": {
      "delta": 0.2500000000000001,
      "error": null,
      "n": 12,
      "p": 0.00048828125,
      "verdict": "SIGNIFICANT"
     },
     "vs_best": {
      "delta": 0.2500000000000001,
      "error": null,
      "n": 12,
      "p": 0.00048828125,
      "verdict": "SIGNIFICANT"
     },
     "group": "length"
    },
    {
     "actor": {
      "from": "environment",
      "name": "owner",
      "type": "person"
     },
     "at": "2026-11-12T12:49:27Z",
     "change": {
      "params": {
       "sentences": 3
      },
      "prompts": []
     },
     "config_id": "s1-t2",
     "cost_usd": 0.0,
     "event": "trial",
     "from": "s1-t1",
     "hypothesis": "sentences = 3 (how much of a ticket to keep)",
     "k": 2,
     "nominal": true,
     "outcome": "dropped",
     "rationale": "grid: the next value of the group",
     "reason": "gained -0.1667 on the best so far, not more than 0",
     "runs": [
      "s1-t2_20261112T124926Z"
     ],
     "shown": [],
     "vs_baseline": {
      "delta": 0.08333333333333337,
      "error": null,
      "n": 12,
      "p": 0.00048828125,
      "verdict": "SIGNIFICANT"
     },
     "vs_best": {
      "delta": -0.16666666666666674,
      "error": null,
      "n": 12,
      "p": 0.00048828125,
      "verdict": "SIGNIFICANT"
     },
     "group": "length"
    },
    {
     "actor": {
      "from": "environment",
      "name": "owner",
      "type": "person"
     },
     "at": "2026-11-12T12:49:28Z",
     "change": {
      "params": {
       "sentences": 4
      },
      "prompts": []
     },
     "config_id": "s1-t3",
     "cost_usd": 0.0,
     "event": "trial",
     "from": "s1-t1",
     "hypothesis": "sentences = 4 (how much of a ticket to keep)",
     "k": 3,
     "nominal": true,
     "outcome": "dropped",
     "rationale": "grid: the next value of the group",
     "reason": "gained -0.2593 on the best so far, not more than 0",
     "runs": [
      "s1-t3_20261112T124927Z"
     ],
     "shown": [],
     "vs_baseline": {
      "delta": -0.00925925925925919,
      "error": null,
      "n": 12,
      "p": 0.00048828125,
      "verdict": "SIGNIFICANT"
     },
     "vs_best": {
      "delta": -0.2592592592592593,
      "error": null,
      "n": 12,
      "p": 0.00048828125,
      "verdict": "SIGNIFICANT"
     },
     "group": "length"
    }
   ],
   "best": {
    "actor": {
     "from": "environment",
     "name": "owner",
     "type": "person"
    },
    "at": "2026-11-12T12:49:26Z",
    "change": {
     "params": {
      "sentences": 2
     },
     "prompts": []
    },
    "config_id": "s1-t1",
    "cost_usd": 0.0,
    "event": "trial",
    "from": "one_v1",
    "hypothesis": "sentences = 2 (how much of a ticket to keep)",
    "k": 1,
    "nominal": true,
    "outcome": "kept",
    "rationale": "grid: the next value of the group",
    "reason": "beat the best so far by 0.25 (needed more than 0)",
    "runs": [
     "s1-t1_20261112T124925Z"
    ],
    "shown": [],
    "vs_baseline": {
     "delta": 0.2500000000000001,
     "error": null,
     "n": 12,
     "p": 0.00048828125,
     "verdict": "SIGNIFICANT"
    },
    "vs_best": {
     "delta": 0.2500000000000001,
     "error": null,
     "n": 12,
     "p": 0.00048828125,
     "verdict": "SIGNIFICANT"
    },
    "group": "length"
   },
   "start": {
    "actor": {
     "from": "environment",
     "name": "owner",
     "type": "person"
    },
    "at": "2026-11-12T12:49:24Z",
    "baseline": "one_v1",
    "event": "start",
    "instruction": null,
    "references_sha256": "fb3a6d8ac4975e4c11739561e7824fbe734044c23a651c468e94a5b113f3bc54",
    "round": "r1",
    "scorer_sha256": "0516696e645371a44285eef1bfdfc45705731de9d38321a7822d35aa4bcd6681",
    "spec_sha256": "3854e527aa28c7c70d18836261e06ddc02a74d706d9a934d2cd60479c65975d0"
   },
   "spent_usd": 0.0,
   "open_ask": null,
   "end": {
    "actor": {
     "from": "environment",
     "name": "owner",
     "type": "person"
    },
    "at": "2026-11-12T12:49:28Z",
    "event": "end",
    "reason": "the space is exhausted",
    "spent_usd": 0.0,
    "summary": "3 trial(s), 1 kept; best: s1-t1 (sentences = 2 (how much of a ticket to keep)). Research: no evidence; study-confirm on a test set is the one step that gives it."
   },
   "confirms": [],
   "started_at": "2026-11-12T12:49:24Z"
  },
  "confirm": {
   "at": "2026-11-12T12:49:30Z",
   "actor": {
    "type": "person",
    "name": "owner",
    "from": "environment"
   },
   "event": "confirm",
   "phase": "verdict",
   "trial": 1,
   "test": "tk_test",
   "rule": "superiority",
   "outcome": "better",
   "delta": 0.2500000000000001,
   "p_one_sided": 0.000244140625,
   "n": 12,
   "runs": {
    "s1-t1-on-tk_test": [
     "s1-t1-on-tk_test_20261112T124929Z"
    ],
    "one_v1-on-tk_test": [
     "one_v1-on-tk_test_20261112T124929Z"
    ]
   },
   "validation_delta": 0.2500000000000001,
   "look": {
    "key": "ad1fdc02010b6e10",
    "number": 1,
    "level": 0.01519817754635067,
    "set": "876b4306dfca95b7a4a77901a3e3604453814e18e5c4efb2cfc70552e54e3d0f",
    "dataset_id": "tk_test",
    "harness": "0.7.2",
    "beyond_limit": false
   }
  },
  "looks": [
   {
    "dataset_id": "tk_test",
    "test_set": true,
    "looks": [
     {
      "beyond_limit": false,
      "dataset_id": "tk_test",
      "harness": "0.7.2",
      "key": "ad1fdc02010b6e10",
      "level": 0.01519817754635067,
      "number": 1,
      "set": "876b4306dfca95b7a4a77901a3e3604453814e18e5c4efb2cfc70552e54e3d0f",
      "what": "study-confirm s1",
      "actor": {
       "from": "environment",
       "name": "owner",
       "type": "person"
      },
      "at": "2026-11-12T12:49:28Z"
     },
     {
      "beyond_limit": false,
      "dataset_id": "tk_test",
      "harness": "0.7.2",
      "key": "ad1fdc02010b6e10",
      "level": 0.01519817754635067,
      "number": 1,
      "set": "876b4306dfca95b7a4a77901a3e3604453814e18e5c4efb2cfc70552e54e3d0f",
      "what": "study-confirm s1",
      "actor": {
       "from": "environment",
       "name": "owner",
       "type": "person"
      },
      "at": "2026-11-12T12:49:30Z"
     }
    ],
    "next": 2,
    "next_level": 0.0037995443865876674,
    "limit": 10,
    "prior_use": 0
   }
  ],
  "prompts": [
   {
    "name": "cnn_summary",
    "versions": 1,
    "latest": "cnn_summary/d98ecfbd4054a474",
    "runs": 0
   }
  ],
  "jobs": [
   {
    "argv": [
     "--run-id",
     "one_v1_20261112T124930-76944d",
     "--config",
     "data/configs/one_v1.yaml"
    ],
    "by": "person:owner",
    "command": "run",
    "created_at": "2026-11-12T12:49:30Z",
    "harness": "0.7.2",
    "id": "20261112T124930-76944d",
    "locks": [
     [
      "config:one_v1",
      true
     ],
     [
      "dataset:tk_val",
      false
     ],
     [
      "project",
      false
     ]
    ],
    "reason": null,
    "run_id": "one_v1_20261112T124930-76944d",
    "ended_at": "2026-11-12T12:49:31Z",
    "exit": 0,
    "pgid": 59193,
    "refusal": null,
    "started_at": "2026-11-12T12:49:30Z",
    "state": "succeeded",
    "supervisor_pid": 59191,
    "waiting_for": null
   }
  ],
  "job_started": {
   "argv": [
    "--run-id",
    "one_v1_20261112T124930-76944d",
    "--config",
    "data/configs/one_v1.yaml"
   ],
   "by": "person:owner",
   "command": "run",
   "created_at": "2026-11-12T12:49:30Z",
   "env": {
    "EVAL_MAX_COST_USD": "1.0"
   },
   "harness": "0.7.2",
   "id": "20261112T124930-76944d",
   "locks": [
    [
     "config:one_v1",
     true
    ],
    [
     "dataset:tk_val",
     false
    ],
    [
     "project",
     false
    ]
   ],
   "reason": null,
   "run_id": "one_v1_20261112T124930-76944d",
   "state": "queued",
   "waiting_for": null,
   "result": null
  },
  "sealed_counts": {
   "counts": {
    "held-out items": {
     "2026-11-02": {
      "n": 1,
      "kind=question": 1
     },
     "2026-11-03": {
      "n": 1,
      "kind=bug": 1
     },
     "2026-11-08": {
      "n": 1,
      "kind=access": 1
     },
     "2026-11-09": {
      "n": 1,
      "kind=bug": 1
     },
     "2026-11-10": {
      "n": 1,
      "kind=question": 1
     }
    }
   },
   "said": "for safety only, never to judge effect (RFC-031): counts, no item"
  },
  "exposure": {
   "dataset_id": "sup_v1_test",
   "items": 5,
   "exposed": 2,
   "reads": 2,
   "by": {
    "agent:homelab": 1,
    "person:owner": 1
   },
   "what": {
    "decision and reason": 1,
    "named in a public repo (tickets-public)": 1
   }
  },
  "exposure_check": {
   "dataset_id": "sup_v1_test",
   "named": 1,
   "new": 1,
   "sealed_at": "2026-11-12T12:49:31Z"
  },
  "unseal": [
   "  look 1: decisions on it are tested one-sided at 1.5198% (evh looks)",
   "data/datasets/sup_v1_test.json  unsealed for sup_cand_v1 against sup_base_v1 (look 1 at this held-out side; hypothesis committed 7c56bef3)",
   "  now open to: sup_base_v1, sup_cand_v1"
  ],
  "heldout_pair": {
   "a": "sup_cand_v1",
   "b": "sup_base_v1",
   "metric": "overlap_f1",
   "n": 3,
   "delta": 0.06760475140070038,
   "p": 0.25,
   "verdict": "NOT-SIGNIFICANT",
   "left_out_exposed": {
    "sup_v1_test": 2
   },
   "with_exposed": {
    "n": 5,
    "delta": 0.041374539152108536
   },
   "look": null
  },
  "faithfulness": {
   "n": 1,
   "counts": {
    "items": 20,
    "agree": 20,
    "differ": 0,
    "replay_errors": 0,
    "production_missing": 0
   },
   "commits": {
    "39297819d8d72ae469531b068f0e067fbb26781c": 8,
    "0deb11044f5a85f6d5c1b4d318dc6dfb139ffd45": 6,
    "035e0b768f721d968788397796f4f6f7703eac2a": 6
   },
   "adapter": null,
   "coverage": {
    "035e0b768f721d968788397796f4f6f7703eac2a": {
     "files": 1,
     "defined": 5,
     "entered": 4,
     "never": [
      "filing.py:_cron_waits"
     ],
     "never_count": 1
    },
    "0deb11044f5a85f6d5c1b4d318dc6dfb139ffd45": {
     "files": 1,
     "defined": 4,
     "entered": 4,
     "never": [],
     "never_count": 0
    },
    "39297819d8d72ae469531b068f0e067fbb26781c": {
     "files": 1,
     "defined": 4,
     "entered": 4,
     "never": [],
     "never_count": 0
    }
   }
  },
  "replay_scores": {
   "replay": 0.95,
   "candidate": 0.55,
   "confound": {
    "items": 1,
    "of": 20
   },
   "replay_confound": {
    "items": 0,
    "of": 20
   }
  },
  "periods": [
   {
    "period": 1,
    "from": "2026-10-02T00:00:00+00:00",
    "to": "2026-10-03T00:00:00+00:00",
    "commit": "39297819d8d72ae469531b068f0e067fbb26781c",
    "dated_by": null,
    "items": 8,
    "faithfulness": {
     "agreed": 8,
     "items": 8,
     "exceptions": [],
     "run": "toy_filing/1",
     "at": "2026-11-12T12:49:34Z"
    }
   },
   {
    "period": 2,
    "from": "2026-10-03T00:00:00+00:00",
    "to": "2026-10-04T00:00:00+00:00",
    "commit": "0deb11044f5a85f6d5c1b4d318dc6dfb139ffd45",
    "dated_by": null,
    "items": 6,
    "faithfulness": {
     "agreed": 6,
     "items": 6,
     "exceptions": [],
     "run": "toy_filing/1",
     "at": "2026-11-12T12:49:34Z"
    }
   },
   {
    "period": 3,
    "from": "2026-10-04T00:00:00+00:00",
    "to": null,
    "commit": "035e0b768f721d968788397796f4f6f7703eac2a",
    "dated_by": null,
    "items": 6,
    "faithfulness": {
     "agreed": 6,
     "items": 6,
     "exceptions": [],
     "run": "toy_filing/1",
     "at": "2026-11-12T12:49:34Z"
    }
   }
  ],
  "period_compare": [
   {
    "period": "period 1 (39297819d8d7)",
    "from": "2026-10-02T00:00:00+00:00",
    "to": "2026-10-03T00:00:00+00:00",
    "items": 8,
    "metric": "exact",
    "production": 0.875,
    "as_run": 0.875,
    "candidate": 0.875,
    "counts": true,
    "disagree": 0,
    "delta": 0.0,
    "p": 1.0,
    "history_confound": {
     "filing_candidate_v3_hidden": {
      "items": 1,
      "of": 20
     }
    }
   },
   {
    "period": "period 2 (0deb11044f5a)",
    "from": "2026-10-03T00:00:00+00:00",
    "to": "2026-10-04T00:00:00+00:00",
    "items": 6,
    "metric": "exact",
    "production": 1.0,
    "as_run": 1.0,
    "candidate": 0.3333333333333333,
    "counts": true,
    "disagree": 0,
    "delta": -0.6666666666666666,
    "p": 0.125,
    "history_confound": {
     "filing_candidate_v3_hidden": {
      "items": 1,
      "of": 20
     }
    }
   },
   {
    "period": "period 3 (035e0b768f72)",
    "from": "2026-10-04T00:00:00+00:00",
    "to": null,
    "items": 6,
    "metric": "exact",
    "production": 1.0,
    "as_run": 1.0,
    "candidate": 0.3333333333333333,
    "counts": true,
    "disagree": 0,
    "delta": -0.6666666666666666,
    "p": 0.125,
    "history_confound": {
     "filing_candidate_v3_hidden": {
      "items": 1,
      "of": 20
     }
    }
   }
  ],
  "code_records": [
   {
    "model": "toy_filing",
    "kind": "code",
    "where": "—",
    "weights": "—",
    "build": "035e0b768f72",
    "deployments": "—",
    "settings": "defaults",
    "onboarding": "3 version(s), 3 checked for faithfulness",
    "arms": 2,
    "goals": "filing",
    "best result": "filing #2 of 3"
   }
  ],
  "label_coverage": {
   "counts": {
    "labelled": 4,
    "skipped": 0,
    "not_mature": 1,
    "unmatched": 0,
    "no_record": 0,
    "gone": 1
   },
   "rules": [
    {
     "rule": 1,
     "text": "rule 1: label file (when)",
     "now": 1,
     "when_mature": 0,
     "first_matures": null,
     "last_matures": null
    },
    {
     "rule": 2,
     "text": "rule 2: label dismiss (when, min_age_days)",
     "now": 3,
     "when_mature": 1,
     "first_matures": "2026-11-23T12:49:36+00:00",
     "last_matures": "2026-11-23T12:49:36+00:00"
    }
   ],
   "by_item": [
    {
     "item_id": "t01_login",
     "class": "labelled",
     "rule": 1,
     "label": [
      "file"
     ]
    },
    {
     "item_id": "t02_invoice",
     "class": "not_mature",
     "rule": 2,
     "matures": "2026-11-23T12:49:36+00:00",
     "today": null
    },
    {
     "item_id": "t03_export",
     "class": "labelled",
     "rule": 2,
     "label": [
      "dismiss"
     ]
    },
    {
     "item_id": "t04_api",
     "class": "labelled",
     "rule": 2,
     "label": [
      "dismiss"
     ]
    },
    {
     "item_id": "t05_delete",
     "class": "gone",
     "last_seen": "2026-10-13T12:49:36Z"
    },
    {
     "item_id": "t06_mobile",
     "class": "labelled",
     "rule": 2,
     "label": [
      "dismiss"
     ]
    }
   ],
   "captured_at": "2026-11-12T12:49:36Z"
  },
  "label_set": {
   "source": {
    "as_of": "2026-11-12T12:49:36+00:00",
    "capture": "decisions",
    "capture_sha256": "23e26cd0ee875c08f88b5ddeeca5cab7edf0d34905239353a3f9a155032ca679",
    "captured_at": "2026-11-12T12:49:36Z",
    "gone": 1,
    "kind": "rule",
    "mapping": "rules.yaml",
    "mapping_sha256": "847b3738bffd55f7d6f180117d4edf8e15027ea76480d16c935086f35f28db42",
    "matched": 4,
    "no_record": 0,
    "not_mature": 1,
    "outcomes": {
     "as": "issue",
     "capture": "issues",
     "capture_sha256": "feba5584b278c29ba7a7727b409ac453b4e2c78021eab8a66b0edefa529808e9",
     "captured_at": "2026-11-12T12:49:36Z",
     "gone_if_missing": false,
     "identity": "first_seen=first_seen",
     "join": "fp=fp",
     "within": "-1m,+15m"
    },
    "skipped": 0,
    "unmatched": 0
   },
   "items": {
    "t01_login": {
     "happened_at": "2026-10-15T12:49:36+00:00",
     "item_sha256": "933f3670443b2db518e9029009cc20aba278d14bf2af1d8719962ff34ae6712a",
     "knowable_at": "2026-10-15T12:49:36+00:00",
     "sha256": "8b911a8716b94442f9ca3dff20584048536e4c2f47b8b5bb9096cbd43c3432d5",
     "under_action": "file",
     "label": "file"
    },
    "t03_export": {
     "item_sha256": "8c5fafabd25867b726a8687f72ab2c241e1f99ead4d89641a58f741eb33e3fbd",
     "knowable_at": "2026-10-27T12:49:36+00:00",
     "sha256": "b09e710e641f0a4b8dfc942068ac368d86acf134b3a795db5d4b305bbcb8dc13",
     "label": "dismiss"
    },
    "t04_api": {
     "item_sha256": "ec3adf1a26bf245b3d13028a6f660bddbf6bea0288c14653b93e840d0937d365",
     "knowable_at": "2026-10-27T12:49:36+00:00",
     "sha256": "b09e710e641f0a4b8dfc942068ac368d86acf134b3a795db5d4b305bbcb8dc13",
     "label": "dismiss"
    },
    "t06_mobile": {
     "item_sha256": "5bf7be3c776a6d5820a0c4f987e45440717cc431af25044e847718779e4ac94f",
     "knowable_at": "2026-11-06T12:49:36+00:00",
     "sha256": "b09e710e641f0a4b8dfc942068ac368d86acf134b3a795db5d4b305bbcb8dc13",
     "label": "dismiss"
    }
   },
   "gone": {
    "t05_delete": "2026-10-13T12:49:36Z"
   }
  },
  "label_mutants": {
   "mutants": [
    {
     "mutant": "rule 1: when issue.state_reason replaced",
     "moved": 1
    },
    {
     "mutant": "rule 2: min_age_days halved (14 -> 7)",
     "moved": 0
    },
    {
     "mutant": "rule 2: min_age_days one and a half times (14 -> 21)",
     "moved": 1
    },
    {
     "mutant": "rule 2: when issue.count replaced",
     "moved": 4
    },
    {
     "mutant": "rules 1 and 2 swapped",
     "moved": 0
    },
    {
     "mutant": "the join's window moved an hour later (-1m,+15m -> +59m,+75m)",
     "moved": 1
    }
   ],
   "survived": [
    "rule 2: min_age_days halved (14 -> 7)",
    "rules 1 and 2 swapped"
   ],
   "labelled": 4
  }
 }
};
