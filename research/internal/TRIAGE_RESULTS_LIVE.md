# Triage experiment: results so far (live)

Updated 2026-10-30T19:49Z. Every finished run re-scored under the owner's rules of 2026-10-30: the combined cost (a missed real problem = 5 false alarms; @3 and @10 shown) decides, among the arms whose false alarms are at or under the ceiling (production's mean over its 4 passes: 85 of 124 = 21.25 of 31, 0.6855; set 2026-10-30, replacing its single pass of 21). 65 owner-labelled decisions (34 real problems, 31 noise). One pass per arm unless the passes column says more; the paired test and the repeats decide, not this table. Self-hosted arms run on Ollama 0.40.13; their cost in tokens is $0.

| # | model | where | passes | cost @5 | @3 | @10 | misses /34 | false alarms /31 | model's own cost @5 | no decision /65 | $ / decision | s / decision | ceiling |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | nemotron_35_bolt_e4b | DGX (NVIDIA) | 1 | **0.523** | 0.431 | 0.754 | 3.0 | 19.0 | 1.246 | 0 | 0.00000 | 15.3 | ok |
| 2 | nemotron_35_lightning_30b | X3 (AMD) | 1 | **0.523** | 0.431 | 0.754 | 3.0 | 19.0 | 1.046 | 0 | 0.00000 | 39.5 | ok |
| 3 | gemini_35_flash_lite | OpenRouter | 1 | **0.538** | 0.446 | 0.769 | 3.0 | 20.0 | 2.031 | 0 | 0.00137 | 3.5 | ok |
| 4 | gpt_oss_20b | Mac (M4 Pro) | 1 | **0.554** | 0.462 | 0.785 | 3.0 | 21.0 | 1.431 | 18 | 0.00000 | 20.0 | ok |
| 5 | haiku_55 | OpenRouter | 4 | **0.604** | 0.481 | 0.912 | 4.0 | 19.2 | 0.962 | 0 | 0.00102 | 7.6 | ok |
| 6 | gpt_6_luna | OpenRouter | 4 | **0.615** | 0.500 | 0.904 | 3.7 | 21.3 | 0.665 | 0 | 0.00069 | 11.7 | ok |
| 7 | gpt_oss_120b | DGX (NVIDIA) | 1 | **0.615** | 0.492 | 0.923 | 4.0 | 20.0 | 1.600 | 0 | 0.00000 | 16.0 | ok |
| 8 | gpt_oss_120b | OpenRouter (open weights) | 1 | **0.677** | 0.523 | 1.062 | 5.0 | 19.0 | 1.646 | 0 | 0.00085 | 17.0 | ok |
| 9 | nemotron_35_super_120b | DGX (NVIDIA) | 1 | **0.677** | 0.523 | 1.062 | 5.0 | 19.0 | 1.508 | 0 | 0.00000 | 41.0 | ok |
| 10 | gemma4_31b | Mac (M4 Pro) | 1 | **0.677** | 0.523 | 1.062 | 5.0 | 19.0 | 1.646 | 0 | 0.00000 | 100.9 | ok |
| 11 | gemma4_31b | X3 (AMD) | 1 | **0.692** | 0.538 | 1.077 | 5.0 | 20.0 | 1.723 | 0 | 0.00000 | 72.1 | ok |
| 12 | sonnet_55 | OpenRouter | 1 | **0.708** | 0.554 | 1.092 | 5.0 | 21.0 | 1.492 | 0 | 0.02266 | 12.0 | ok |
| 13 | gemma4_31b | OpenRouter (open weights) | 1 | **0.723** | 0.538 | 1.185 | 6.0 | 17.0 | 2.154 | 0 | 0.00090 | 10.5 | ok |
| 14 | deepseek_41flash | OpenRouter | 1 | **0.754** | 0.569 | 1.215 | 6.0 | 19.0 | 2.246 | 0 | 0.00086 | 9.8 | ok |
| 15 | nemotron_35_bolt_e4b | Mac (M4 Pro) | 1 | **0.754** | 0.569 | 1.215 | 6.0 | 19.0 | 1.292 | 0 | 0.00000 | 23.1 | ok |
| 16 | baseline_pro | OpenRouter | 4 | **0.769** | 0.592 | 1.212 | 5.7 | 21.2 | 1.712 | 0 | 0.00508 | 25.4 | ok |
| 17 | ministral_3_14b | X3 (AMD) | 1 | **0.815** | 0.600 | 1.354 | 7.0 | 18.0 | 2.508 | 0 | 0.00000 | 22.1 | ok |
| 18 | mistral_medium_35 | OpenRouter (open weights) | 1 | **0.877** | 0.631 | 1.492 | 8.0 | 17.0 | 1.662 | 0 | 0.01154 | 6.1 | ok |
| 19 | qwen38_27b | X3 (AMD) | 1 | **0.908** | 0.662 | 1.523 | 8.0 | 19.0 | 2.292 | 0 | 0.00000 | 46.2 | ok |
| 20 | mistral_medium_35_128b | DGX (NVIDIA) | 1 | **1.000** | 0.723 | 1.692 | 9.0 | 20.0 | 1.662 | 0 | 0.00000 | 117.5 | ok |
| 21 | qwen35_122b | OpenRouter (open weights) | 1 | **1.077** | 0.769 | 1.846 | 10.0 | 20.0 | 1.692 | 0 | 0.00335 | 17.7 | ok |
| 22 | qwen35_122b | DGX (NVIDIA) | 1 | **1.138** | 0.800 | 1.985 | 11.0 | 19.0 | 1.800 | 0 | 0.00000 | 38.0 | ok |
| 23 | llama31_8b | X3 (AMD) | 1 | **0.415** | 0.415 | 0.415 | 0.0 | 27.0 | 1.062 | 0 | 0.00000 | 5.8 | out |
| 24 | gpt_61_sol | OpenRouter | 4 | **0.604** | 0.504 | 0.854 | 3.2 | 23.0 | 0.531 | 0 | 0.01090 | 12.1 | out |
| 25 | gemini_4_argon | OpenRouter | 1 | **0.646** | 0.523 | 0.954 | 4.0 | 22.0 | 1.185 | 0 | 0.01362 | 30.1 | out |
| 26 | kimi_k31_pro | OpenRouter | 1 | **0.646** | 0.523 | 0.954 | 4.0 | 22.0 | 0.969 | 0 | 0.01913 | 46.1 | out |
| 27 | phi4_14b | X3 (AMD) | 1 | **0.769** | 0.615 | 1.154 | 5.0 | 25.0 | 0.862 | 0 | 0.00000 | 16.9 | out |
| 28 | mistral_large_4 | OpenRouter | 1 | **0.800** | 0.615 | 1.262 | 6.0 | 22.0 | 1.923 | 0 | 0.00687 | 17.3 | out |
| 29 | llama4_scout | DGX (NVIDIA) | 1 | **1.262** | 0.923 | 2.108 | 11.0 | 27.0 | 1.569 | 0 | 0.00000 | 13.4 | out |

## Read with care

- **gpt-oss:20b on the Mac** ranks high, but 18 of its 65 decisions are not the model's: its last reply was empty
  (fleet bug F7), and the replay records the fleet's own fallback, an escalation. An escalation counts as catching a
  real problem, so the empty replies help its misses. Its own decisions score 1.431, against 0.554 for the whole
  step. The "no decision" column counts these; runs made before the column existed would have crashed instead, so
  their 0 is real.
- **gpt-oss:120b on the DGX** ran an older build (pulled 2026-06-05, model layer `6be6d66a`); the current build
  (`a5b03e4c`, on X3 since 2026-10-30) differs in its weights only. The owner chose a re-pull and a re-run
  (2026-10-30); this row is kept until then, and then leaves the set of record.
- **Mac speed, 17:11–17:38Z:** prod pulled two models on the Mac during that window, so the s / decision of
  gpt-oss:20b (17:12–17:34Z, all of it) and the start of gemma4:31b may be slower than the Mac really is. The
  repeats measure speed again.

## Skipped for now, to troubleshoot after the runs (owner, 2026-10-30)

- **gemma4:12b** (all three machines). The Mac stopped at 0 of 65: the first decision timed out 8 times at 600 s
  each. X3 stopped at 12 of 65 under the fleet's old 90 s limit. On a one-line question the same model on the Mac
  answers in 15 s (81 tokens at about 39 tokens/s, thinking included), so the hang is specific to the triage prompt;
  the cause is not known yet. The partial runs are kept, uncommitted, for the troubleshooting.
