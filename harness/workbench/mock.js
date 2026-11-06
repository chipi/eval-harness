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
 }
};
