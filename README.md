# jevcontrol-hermes

Beta Hermes plugin (`jev-control`) that can answer a narrow set of routine tool-selection steps (web search, open URL,
read file) with a small local decision model instead of the main LLM, plus a trace-review tool.

**Status: experimental. Routing is OFF by default. No speed or cost benefit has been demonstrated** (see limits below).

## Install
```bash
hermes plugins install abhishek085/jevcontrol-hermes   # or copy this folder to ~/.hermes/plugins/jev-control
hermes plugins enable jev-control
```

## Config (`~/.hermes/config.yaml`, under `plugins.entries.jev-control.settings`)
| key | default | meaning |
|---|---|---|
| routing_mode | off | `off`, or `cascade` (rules + decision model must agree) |
| skip_families | none | families allowed to be routed: `search`, `extract`, `read` |
| cascade_tau | 0.9 | minimum decision-model confidence score |
| spark_url / spark_model | localhost:8102 / (set yours) | OpenAI-compatible decision-model endpoint |
| log_content | false | when true, logs prompts, tool arguments and conversations to `~/.hermes/logs/jev_routing.jsonl` |
| keep_warm_s | 0 | ping the decision model (can slow the main model on a small machine) |

Any failure falls back to the normal main-model call.

## Known limits
- Tested on one Apple M4 Pro 24 GB with Gemma 4 (12B, E4B) and spark-s1; small sample (8 tasks).
- In those runs the cascade reduced main-model calls but did not reduce wall time; two of eight paired tasks returned
  different factual answers. Output equivalence is not established.
- Only the `chat_completions` API mode is handled; streaming and approval flows are not yet tested.
