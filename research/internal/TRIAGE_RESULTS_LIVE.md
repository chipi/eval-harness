# Triage experiment: results so far (live)

Updated 2026-10-31T09:08Z. Every finished run re-scored under the owner's rules of 2026-10-30: the combined cost (a missed real problem = 5 false alarms; @3 and @10 shown) decides, among the arms whose false alarms are at or under the ceiling (production's mean over its 4 passes: 85 of 124 = 21.25 of 31, 0.6855; set 2026-10-30, replacing its single pass of 21). 65 owner-labelled decisions (34 real problems, 31 noise). One pass per arm unless the passes column says more; the paired test and the repeats decide, not this table. Self-hosted arms run on Ollama 0.40.13; their cost in tokens is $0.

| # | model | where | passes | cost @5 | @3 | @10 | misses /34 | false alarms /31 | model's own cost @5 | no decision /65 | $ / decision | s / decision | ceiling |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | vllm_qwen3_30b_a3b_nvfp4 | DGX (NVIDIA) | 1 | **0.400** | 0.369 | 0.477 | 1.0 | 21.0 | 1.138 | 0 | 0.00000 | 7.8 | ok |
| 2 | gpt_oss_20b | X3 (AMD) | 1 | **0.400** | 0.369 | 0.477 | 1.0 | 21.0 | 0.969 | 16 | 0.00000 | 17.2 | ok |
| 3 | gpt_oss_20b | DGX (NVIDIA) | 1 | **0.477** | 0.415 | 0.631 | 2.0 | 21.0 | 1.277 | 15 | 0.00000 | 13.5 | ok |
| 4 | nemotron_35_bolt_e4b | DGX (NVIDIA) | 1 | **0.523** | 0.431 | 0.754 | 3.0 | 19.0 | 1.246 | 0 | 0.00000 | 15.3 | ok |
| 5 | nemotron_35_lightning_30b | X3 (AMD) | 1 | **0.523** | 0.431 | 0.754 | 3.0 | 19.0 | 1.046 | 0 | 0.00000 | 39.5 | ok |
| 6 | gemini_35_flash_lite | OpenRouter | 1 | **0.538** | 0.446 | 0.769 | 3.0 | 20.0 | 2.031 | 0 | 0.00137 | 3.5 | ok |
| 7 | gpt_oss_20b | Mac (M4 Pro) | 1 | **0.554** | 0.462 | 0.785 | 3.0 | 21.0 | 1.431 | 18 | 0.00000 | 20.0 | ok |
| 8 | gemma4_12b (reasoning off) | DGX (NVIDIA) | 1 | **0.585** | 0.462 | 0.892 | 4.0 | 18.0 | 1.600 | 0 | 0.00000 | 5.7 | ok |
| 9 | gemma4_12b (reasoning off) | Mac (M4 Pro) | 1 | **0.585** | 0.462 | 0.892 | 4.0 | 18.0 | 1.662 | 0 | 0.00000 | 9.2 | ok |
| 10 | nemotron_35_bolt_e4b | X3 (AMD) | 1 | **0.600** | 0.477 | 0.908 | 4.0 | 19.0 | 1.015 | 0 | 0.00000 | 22.3 | ok |
| 11 | haiku_55 | OpenRouter | 4 | **0.604** | 0.481 | 0.912 | 4.0 | 19.2 | 0.962 | 0 | 0.00102 | 7.6 | ok |
| 12 | gpt_6_luna | OpenRouter | 4 | **0.615** | 0.500 | 0.904 | 3.7 | 21.3 | 0.665 | 0 | 0.00069 | 11.7 | ok |
| 13 | gpt_oss_120b | OpenRouter (open weights) | 1 | **0.677** | 0.523 | 1.062 | 5.0 | 19.0 | 1.646 | 0 | 0.00085 | 17.0 | ok |
| 14 | gemma4_31b | DGX (NVIDIA) | 1 | **0.677** | 0.523 | 1.062 | 5.0 | 19.0 | 1.631 | 0 | 0.00000 | 58.9 | ok |
| 15 | nemotron_35_super_120b | DGX (NVIDIA) | 1 | **0.677** | 0.523 | 1.062 | 5.0 | 19.0 | 1.508 | 0 | 0.00000 | 41.0 | ok |
| 16 | gemma4_31b | Mac (M4 Pro) | 1 | **0.677** | 0.523 | 1.062 | 5.0 | 19.0 | 1.646 | 0 | 0.00000 | 100.9 | ok |
| 17 | gpt_oss_120b | DGX (NVIDIA) | 1 | **0.692** | 0.538 | 1.077 | 5.0 | 20.0 | 1.523 | 0 | 0.00000 | 14.8 | ok |
| 18 | gemma4_31b | X3 (AMD) | 1 | **0.692** | 0.538 | 1.077 | 5.0 | 20.0 | 1.723 | 0 | 0.00000 | 72.1 | ok |
| 19 | qwen3_30b_a3b | OpenRouter (open weights) | 1 | **0.708** | 0.523 | 1.169 | 6.0 | 16.0 | 1.508 | 0 | 0.00070 | 18.0 | ok |
| 20 | sonnet_55 | OpenRouter | 1 | **0.708** | 0.554 | 1.092 | 5.0 | 21.0 | 1.492 | 0 | 0.02266 | 12.0 | ok |
| 21 | gemma4_31b | OpenRouter (open weights) | 1 | **0.723** | 0.538 | 1.185 | 6.0 | 17.0 | 2.154 | 0 | 0.00090 | 10.5 | ok |
| 22 | qwen3_30b_a3b | X3 (AMD) | 1 | **0.723** | 0.508 | 1.262 | 7.0 | 12.0 | 1.862 | 0 | 0.00000 | 6.9 | ok |
| 23 | deepseek_41flash | OpenRouter | 1 | **0.754** | 0.569 | 1.215 | 6.0 | 19.0 | 2.246 | 0 | 0.00086 | 9.8 | ok |
| 24 | nemotron_35_bolt_e4b | Mac (M4 Pro) | 1 | **0.754** | 0.569 | 1.215 | 6.0 | 19.0 | 1.292 | 0 | 0.00000 | 23.1 | ok |
| 25 | baseline_pro | OpenRouter | 4 | **0.769** | 0.592 | 1.212 | 5.7 | 21.2 | 1.712 | 0 | 0.00508 | 25.4 | ok |
| 26 | ministral_3_14b | X3 (AMD) | 1 | **0.815** | 0.600 | 1.354 | 7.0 | 18.0 | 2.508 | 0 | 0.00000 | 22.1 | ok |
| 27 | ministral_3_14b | DGX (NVIDIA) | 1 | **0.831** | 0.585 | 1.446 | 8.0 | 14.0 | 2.262 | 0 | 0.00000 | 20.5 | ok |
| 28 | qwen38_27b | DGX (NVIDIA) | 1 | **0.831** | 0.615 | 1.369 | 7.0 | 19.0 | 2.354 | 0 | 0.00000 | 37.8 | ok |
| 29 | ministral_3_14b | Mac (M4 Pro) | 1 | **0.831** | 0.615 | 1.369 | 7.0 | 19.0 | 2.415 | 1 | 0.00000 | 27.4 | ok |
| 30 | qwen3_30b_a3b | Mac (M4 Pro) | 1 | **0.831** | 0.585 | 1.446 | 8.0 | 14.0 | 1.862 | 0 | 0.00000 | 9.0 | ok |
| 31 | stub_dismiss | control (no model) | 1 | **0.862** | 0.646 | 1.400 | 7.0 | 21.0 | 2.615 | 0 | 0.00000 | 0.0 | ok |
| 32 | mistral_medium_35 | OpenRouter (open weights) | 1 | **0.877** | 0.631 | 1.492 | 8.0 | 17.0 | 1.662 | 0 | 0.01154 | 6.1 | ok |
| 33 | qwen3_30b_a3b | DGX (NVIDIA) | 1 | **0.892** | 0.615 | 1.585 | 9.0 | 13.0 | 2.108 | 0 | 0.00000 | 5.9 | ok |
| 34 | qwen38_27b | X3 (AMD) | 1 | **0.908** | 0.662 | 1.523 | 8.0 | 19.0 | 2.292 | 0 | 0.00000 | 46.2 | ok |
| 35 | mistral_medium_35_128b | DGX (NVIDIA) | 1 | **1.000** | 0.723 | 1.692 | 9.0 | 20.0 | 1.662 | 0 | 0.00000 | 117.5 | ok |
| 36 | qwen38_27b | Mac (M4 Pro) | 1 | **1.046** | 0.738 | 1.815 | 10.0 | 18.0 | 2.277 | 0 | 0.00000 | 69.7 | ok |
| 37 | qwen35_122b | OpenRouter (open weights) | 1 | **1.077** | 0.769 | 1.846 | 10.0 | 20.0 | 1.692 | 0 | 0.00335 | 17.7 | ok |
| 38 | qwen35_122b | DGX (NVIDIA) | 1 | **1.138** | 0.800 | 1.985 | 11.0 | 19.0 | 1.800 | 0 | 0.00000 | 38.0 | ok |
| 39 | llama31_8b | DGX (NVIDIA) | 1 | **0.415** | 0.415 | 0.415 | 0.0 | 27.0 | 1.092 | 0 | 0.00000 | 5.8 | out |
| 40 | llama31_8b | Mac (M4 Pro) | 1 | **0.415** | 0.415 | 0.415 | 0.0 | 27.0 | 1.062 | 0 | 0.00000 | 7.8 | out |
| 41 | llama31_8b | X3 (AMD) | 1 | **0.415** | 0.415 | 0.415 | 0.0 | 27.0 | 1.062 | 0 | 0.00000 | 5.8 | out |
| 42 | stub_escalate | control (no model) | 1 | **0.477** | 0.477 | 0.477 | 0.0 | 31.0 | 0.477 | 0 | 0.00000 | 0.0 | out |
| 43 | gpt_61_sol | OpenRouter | 4 | **0.604** | 0.504 | 0.854 | 3.2 | 23.0 | 0.531 | 0 | 0.01090 | 12.1 | out |
| 44 | gemini_4_argon | OpenRouter | 1 | **0.646** | 0.523 | 0.954 | 4.0 | 22.0 | 1.185 | 0 | 0.01362 | 30.1 | out |
| 45 | kimi_k31_pro | OpenRouter | 1 | **0.646** | 0.523 | 0.954 | 4.0 | 22.0 | 0.969 | 0 | 0.01913 | 46.1 | out |
| 46 | nemotron_35_lightning_30b | DGX (NVIDIA) | 1 | **0.646** | 0.523 | 0.954 | 4.0 | 22.0 | 1.138 | 0 | 0.00000 | 40.0 | out |
| 47 | nemotron_35_lightning_30b | Mac (M4 Pro) | 1 | **0.646** | 0.523 | 0.954 | 4.0 | 22.0 | 1.446 | 0 | 0.00000 | 66.0 | out |
| 48 | phi4_14b | DGX (NVIDIA) | 1 | **0.662** | 0.538 | 0.969 | 4.0 | 23.0 | 0.785 | 0 | 0.00000 | 17.0 | out |
| 49 | phi4_14b | Mac (M4 Pro) | 1 | **0.754** | 0.600 | 1.138 | 5.0 | 24.0 | 0.785 | 0 | 0.00000 | 21.8 | out |
| 50 | phi4_14b | X3 (AMD) | 1 | **0.769** | 0.615 | 1.154 | 5.0 | 25.0 | 0.862 | 0 | 0.00000 | 16.9 | out |
| 51 | mistral_large_4 | OpenRouter | 1 | **0.800** | 0.615 | 1.262 | 6.0 | 22.0 | 1.923 | 0 | 0.00687 | 17.3 | out |
| 52 | llama4_scout | DGX (NVIDIA) | 1 | **1.262** | 0.923 | 2.108 | 11.0 | 27.0 | 1.569 | 0 | 0.00000 | 13.4 | out |

## Read with care

- **gpt-oss:20b on the Mac** ranks high, but 18 of its 65 decisions are not the model's: its last reply was empty
  (fleet bug F7), and the replay records the fleet's own fallback, an escalation. An escalation counts as catching a
  real problem, so the empty replies help its misses. Its own decisions score 1.431, against 0.554 for the whole
  step. The "no decision" column counts these; runs made before the column existed would have crashed instead, so
  their 0 is real.
- **gpt-oss:120b on the DGX** first ran an older build (pulled 2026-06-05, model layer `6be6d66a`, cost 0.615); the current build
  (`a5b03e4c`, on X3 since 2026-10-30) differs in its weights only. The owner chose a re-pull and a re-run
  (2026-10-30). Re-run 2026-10-31 on the current build: 0.692 (5 misses, 20 false alarms); the June run left the table.
- **Self-hosted runs are deterministic per machine, not across machines** (measured 2026-10-30). The fleet calls
  the model at `temperature: 0` with JSON mode (`mvp/triage.py:255`). A second Bolt e4b pass on X3 matched the
  first byte for byte: 65 of 65 raw outputs identical, 0 decisions different. Against the DGX and the Mac, all 65
  raw outputs differ and 14 and 10 decisions differ. So a self-hosted row is one fixed draw, repeats on the same
  machine add nothing, and the spread between machines (Bolt 0.523 / 0.600 / 0.754) is the run-to-run noise.
  Hosted repeats do vary (the providers are not deterministic).
- **Mac speed, 17:11–17:38Z:** prod pulled two models on the Mac during that window, so the s / decision of
  gpt-oss:20b (17:12–17:34Z, all of it) and the start of gemma4:31b may be slower than the Mac really is. The
  repeats measure speed again.

## Skipped for now, to troubleshoot after the runs (owner, 2026-10-30)

- **gemma4:12b** (all three machines), with the server's default reasoning: it reasons in a loop and never answers. Set up normally (reasoning off, 1024-token cap, 30 s limit) it runs: see the "(reasoning off)" rows. Before that: the Mac stopped at 0 of 65: the first decision timed out 8 times at 600 s
  each. X3 stopped at 12 of 65 under the fleet's old 90 s limit. On a one-line question the same model on the Mac
  answers in 15 s (81 tokens at about 39 tokens/s, thinking included), so the hang is specific to the triage prompt;
  the cause is not known yet. The partial runs are kept, uncommitted, for the troubleshooting.
