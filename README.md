# jevcontrol-hermes

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin that puts a small, fast **decision model**
(spark-s1, served through the open-spark-Jev / JevControl `/v1/decide` API) in front of the small decisions an agent
makes all the time, so the large model only runs where it is actually needed.

Each feature is one documented Hermes extension point and one decision-model question (about 80–400 ms):

| Feature | Hermes hook | Question the decision model answers | Default |
|---|---|---|---|
| **Privacy guard** | `pre_tool_call` (block) | Does this outgoing search / URL / network command reveal credentials, personal data or private local content? | off |
| **Memory gatekeeper** | `pre_tool_call` on `memory` | Is this a durable fact, or task know-how, task progress, an order, or a secret? | off |
| **Search picker** | `transform_tool_result` on `web_search` | Is result *i* related to the user's request? (all results in one call) | off |
| **Context compressor** | context engine `jev` | Will the agent still need old tool output *k*? (replaces the LLM-written summary) | off |
| **Approval guard** | `auxiliary.approval` endpoint | Is this flagged shell command safe, dangerous, or unclear? | off |
| Tool-step routing (experimental) | `llm_execution` middleware | Is the next step a routine search/open/read that code can do? | off |

Everything fails open: if the decision model is unreachable or errors, Hermes behaves as if the plugin were not there
(the approval guard fails to *escalate*, i.e. to the normal manual prompt).

**Status: beta.** Results below are small, single-machine experiments with labels written by the author. Read the
caveats before relying on any feature.

## Install

```bash
git clone https://github.com/abhishek085/jevcontrol-hermes ~/.hermes/plugins/jev-control
hermes plugins enable jev-control
```

You need a decision server that speaks `POST {spark_url}/decide` (open-spark-Jev / JevControl gateway).

## Configure (`~/.hermes/config.yaml`)

```yaml
plugins:
  entries:
    jev-control:
      settings:
        spark_url: http://HOST:8400/v1
        spark_model: spark-s1-4b-v8-nvfp4
        spark_api: decide
        privacy_guard: monitor     # off | monitor (log only) | enforce (block)
        memory_gate: monitor       # off | monitor | enforce
        search_pick: true          # drop search results the model is fairly sure are unrelated
        compressor: false          # true registers the `jev` context engine (then set context.engine: jev)
        log_timing: false          # content-free timing/token log in ~/.hermes/logs/jev_routing.jsonl
```

Context compressor: set `compressor: true` **and** `context.engine: jev`. Optional `compress_threshold_tokens`
(absolute trigger) and `compress_keep_last` (protected recent messages, default 6).

Approval guard: run `hermes jev-control serve` (local, port 8765) and point Hermes at it. `provider: custom` and a
non-empty `api_key` are required, otherwise Hermes silently ignores `base_url`:

```yaml
auxiliary:
  approval:
    provider: custom
    base_url: http://127.0.0.1:8765/v1
    api_key: jev-local
    model: jev-guard
```

<details><summary>All settings</summary>

| key | default | meaning |
|---|---|---|
| spark_url / spark_model / spark_api | localhost:8102/v1 / spark-s1 / chat | decision server; the features above need `spark_api: decide` |
| jev_timeout_s | 10 | per decision call |
| privacy_guard / privacy_tau | off / 0.8 | mode; minimum confidence to block on the model layer |
| memory_gate / memory_tau | off / 0.7 | mode; minimum confidence to block a misfiled write |
| search_pick / search_tau / search_min_keep / search_max_keep | off / 0.15 / 2 / 10 | drop results with P(related) below tau, keep at least min |
| compressor / compress_threshold / compress_threshold_tokens | false / 0.5 / 0 | engine on; trigger as share of context; optional absolute trigger |
| compress_keep_last / compress_need_tau / compress_trim_chars | 6 / 0.5 / 4000 | protected tail; keep outputs with P(needed) above tau; trim kept outputs longer than this |
| guard_host / guard_port / guard_approve_tau / guard_deny_tau | 127.0.0.1 / 8765 / 0.9 / 0.7 | approval guard server and thresholds (below threshold -> escalate) |
| routing_mode / skip_families / cascade_tau | off / none / 0.9 | experimental tool-step routing |
| log_content / log_timing | false / false | content logging (prompts, args) is opt-in; timing log has no content |

</details>

## Results so far

Setup: Hermes main model Qwen3.8-27B and spark-s1-4b (NVFP4), both on a remote server; Mac M4 Pro client.
Eval sets are in [`evals/`](evals/) and were labelled before the first model run.

| Feature | Test | Result |
|---|---|---|
| Privacy guard | 36 outbound calls (19 leaks, 17 normal) | rules alone caught 8/19; rules + Jev **18/19**, **0/17** normal calls blocked; median 78 ms |
| Memory gatekeeper | 27 memory writes | kept **10/10** real facts, blocked **17/17** misfiled writes (16 with the right reason) |
| Approval guard | 60 held-out flagged commands, vs Qwen as the approval model | unsafe approvals **0/22** (Qwen 0/22); harmless auto-approved 16/22 (Qwen 21/22); unclear approved **0/10** (Qwen 3/10); **88 ms** median vs 2.5 s (Qwen p90 12.7 s, one 93 s timeout) |
| Search picker | 32 runs, 8 tasks (first version) | cut result text ~40% but no wall-time gain; dropped the wanted page on one task. Conservative rewrite not yet re-measured |
| Context compressor | offline replay of one real session | ~12,600 → ~2,500 tokens in 0.85 s, no LLM summary call. Live comparison against the built-in compressor **not finished** |
| Tool-step routing | 24 runs, idle server, 8 tasks | 1 main-model call skipped per task; wall −1.6 s per run (CI −4.1 to +1.4), not significant |

### Search picker
First version (kept the 3 top-scored results, re-ranked), 16 paired runs on 8 tasks: result text 157k → 96k chars,
median 409 ms per search, but main-model input tokens and wall time were not lower (+5 s mean, not significant). On a
task asking for an "official page" it dropped the right page and the agent made 12-14 calls instead of 5-7. The
current version only removes results scored below `search_tau` (0.15) and keeps the engine's order; it has **not**
been re-measured yet.

### Context compressor
Replaying a recorded 15-message session (about 12,600 tokens) through the engine removed four old tool outputs and
trimmed one, leaving about 2,500 tokens in 0.85 s with a single decision call and no generation call. Message roles
and ids are unchanged. A live comparison against Hermes' built-in LLM-summary compressor (answer quality, total time)
is still to be done; short tasks rarely reach the compaction trigger.

## Caveats
- Small, author-labelled test sets; one main model; one decision model. Treat numbers as indicative.
- The decision model's confidence is not calibrated: it is sometimes wrong with p≈1.0.
- Privacy guard: one miss was private source code pasted into a search query. `enforce` mode has no "the user said
  yes" override yet; use `monitor` if that matters.
- Hermes' own dangerous-command detector does not flag some exfiltration commands (`scp ~/.aws/credentials …`),
  so the approval guard never sees them; the privacy guard does cover those.
- The decision server tested here returned HTTP 500 for any state containing the lowercase word "content"; the client
  retries once with that word capitalised.
- Only `chat_completions` API mode is handled by tool-step routing.

## Repository layout
`__init__.py` (registration, config, tool routing, trace review) · `jev_client.py` · `privacy.py` · `memory_gate.py` ·
`search_pick.py` · `compressor.py` · `guard.py` · `evals/` (cases + runners)

MIT license.
