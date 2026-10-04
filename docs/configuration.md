# Configuration reference

All settings live under `plugins.entries.jev-control.settings` in `~/.hermes/config.yaml`. Set one with
`hermes config set plugins.entries.jev-control.settings.<key> <value>`. `hermes jev-control setup` writes a sensible set for you.

## Decision model

| Key | Default | Meaning |
|---|---|---|
| `spark_url` | `http://localhost:8102/v1` | Base URL of the decision server (include `/v1`). |
| `spark_api` | `chat` | `decide`: Jev-style typed API, `POST {spark_url}/decide`. `chat`: OpenAI-compatible server that returns logprobs, `POST {spark_url}/chat/completions`. |
| `spark_model` | `spark-s1` | Model name. With `decide` it is sent as `model` unless it is exactly `spark-s1`; with `chat` it is the chat `model`. |
| `jev_timeout_s` | `10` | Timeout per decision call. A timeout counts as an error: the feature fails open. |

## Privacy guard

| Key | Default | Meaning |
|---|---|---|
| `privacy_guard` | `off` | `off`, `monitor` (log only) or `enforce` (block). |
| `privacy_tau` | `0.8` | Minimum model confidence to block on the model layer. Fixed credential patterns block regardless. |

Checks `web_search` queries, `web_extract` URLs, all `browser_*` tool arguments, and `terminal` / `execute_code` calls that
contain a network command. Calls that send nothing out are not checked.

## Memory gatekeeper

| Key | Default | Meaning |
|---|---|---|
| `memory_gate` | `off` | `off`, `monitor` or `enforce`. |
| `memory_tau` | `0.7` | Minimum confidence to block a write that is not a durable fact. Secrets always block. |

Only `add` / `replace` / `update` writes are checked; removals and reads always pass.

## Search picker

| Key | Default | Meaning |
|---|---|---|
| `search_pick` | `off` | `true`/`on` enables it. |
| `search_tau` | `0.15` | A result is removed only if P(related) is below this. Lower = more conservative. |
| `search_min_keep` | `2` | Never leave fewer results than this. |
| `search_max_keep` | `10` | Keep at most this many. |

## Context compressor

Needs `compressor: true` **and** Hermes' `context.engine: jev`.

| Key | Default | Meaning |
|---|---|---|
| `compressor` | `false` | Registers the `jev` context engine. |
| `compress_threshold` | `0.5` | Trigger as a fraction of the context window. |
| `compress_threshold_tokens` | `0` | Optional absolute trigger (lower of the two applies). `0` = off. |
| `compress_keep_last` | `6` | Most recent messages that are never touched. |
| `compress_need_tau` | `0.5` | Old tool outputs with P(still needed) below this become one-line stubs. |
| `compress_trim_chars` | `4000` | Outputs judged needed but longer than this are trimmed to head and tail. |

## Approval guard

| Key | Default | Meaning |
|---|---|---|
| `guard_autostart` | `false` | Start the guard endpoint inside Hermes. Several Hermes processes share one: the first to bind the port serves it. |
| `guard_host`, `guard_port` | `127.0.0.1`, `8765` | Where it listens. Keep it on localhost. |
| `guard_approve_tau` | `0.9` | Minimum confidence to answer APPROVE. Below it the answer is ESCALATE (Hermes asks you). |
| `guard_deny_tau` | `0.7` | Minimum confidence to answer DENY. |

Hermes must be pointed at the endpoint: `auxiliary.approval.provider: custom`, `base_url: http://127.0.0.1:8765/v1`, any
non-empty `api_key`, `model: jev-guard`. With `provider: auto` Hermes silently ignores `base_url`.

## Logging

| Key | Default | Meaning |
|---|---|---|
| `log_timing` | `false` | Also log every main-model call's duration and token counts (no content) and auxiliary-call timings. |
| `log_content` | `false` | Include prompts, tool arguments and conversation text in the local log. Off unless you need to debug. |

The log is `~/.hermes/logs/jev_routing.jsonl` (profile-aware). Feature verdicts are always logged without content.

## Experimental: tool-step routing

Off by default and not recommended: it showed no significant speed-up (see [results](results.md)).

| Key | Default | Meaning |
|---|---|---|
| `routing_mode` | `off` | `cascade` lets a rule and the decision model, in agreement, take a routine first step (search / open / read) without calling the main model. |
| `skip_families` | none | Which families may be routed: `search`, `extract`, `read`. |
| `cascade_tau` | `0.9` | Minimum confidence. |
| `keep_warm_s` | `0` | Ping the decision model every N seconds so its weights stay resident. |
