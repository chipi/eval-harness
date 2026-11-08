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
 }
};
