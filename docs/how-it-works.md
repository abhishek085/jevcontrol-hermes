# How it works

Every feature has the same shape: **one agent decision → one closed question → one decision-model call → act only if
confident**. The decision model never writes text for the user. It picks one of a few fixed options, and gives a
probability for each.

## The decision model

[spark-s1 v8](https://huggingface.co/abhishek085/spark-s1-4b-v8-nvfp4) is a 4B model trained to answer multiple-choice questions about a
*state* (untrusted text) and to be calibrated about it. The plugin reaches it two ways (`spark_api`):

- `decide`: `POST /v1/decide` with `{"state", "questions": [...]}`. Questions may be `choice` (with options) or `boolean`;
  several questions about one state go in one call. The server returns probabilities per option.
- `chat`: a lettered menu is sent to any OpenAI-compatible server (`max_tokens=1`, `logprobs=true`), and the probabilities
  are read from the first token's logprobs over the option letters. One forward pass.

Both are in [`jev_client.py`](../jev_client.py). A failed call is retried once on a 5xx, then the feature fails open.

## Privacy guard (`pre_tool_call`)

1. Pick out the part of the call that leaves the machine: the query of `web_search`, the URLs of `web_extract`, the
   arguments of `browser_*`, or the command/code of `terminal` / `execute_code` **if** it contains a network command.
2. **Rules first**: fixed patterns for private keys, cloud and API keys, tokens, `password=` assignments, passwords in
   URLs, and credential files piped to the network. A hit blocks immediately (no model call).
3. **Decision model**: classify the text as `public`, `secret`, `personal` (data about a real person) or `local`
   (private files, source code, internal documents). Block if the answer is not `public` and the probability is at least
   `privacy_tau`.
4. `enforce` returns Hermes' documented block directive with a message that tells the agent to rewrite the call or ask the
   user; `monitor` only logs.

## Memory gatekeeper (`pre_tool_call` on `memory`)

Hermes' own prompt says memory is for declarative facts that matter in every session; procedures belong in skills and task
progress belongs nowhere. Each write is classified as `durable_fact`, `procedure`, `transient` or `directive` (an order to
the agent, which later sessions read as an instruction). Anything but a durable fact, above `memory_tau`, is blocked with
advice on where it belongs. Secrets are refused by rule. Removals and reads are never checked.

## Search picker (`transform_tool_result` on `web_search`)

One batched call asks, for every result, "does this help with the user's request?" The user's latest message is tracked
per session through `pre_llm_call`. Results with P(related) below `search_tau` are removed (original order kept, never fewer
than `search_min_keep`), and a one-line note tells the agent how many were removed and to search again if needed. The
result keeps Hermes' JSON shape.

## Context compressor (context engine `jev`)

Hermes' built-in compressor asks an LLM to write a summary of the middle of the conversation. This engine keeps every
message and its identity and instead asks one batched question per old tool output: "will the agent still need the full
content of this?" Outputs judged unneeded become a one-line stub (what tool, how long, how it began); long outputs still
needed are trimmed to head and tail; if the result is still over budget the least-needed outputs go too. No generation call
is made. Roles, tool-call ids and the protected recent tail are untouched. A decision-model failure falls back to dropping
the oldest half.

## Approval guard (local endpoint)

Hermes' *smart approvals* send flagged shell commands to an auxiliary model and expect one word: `APPROVE`, `DENY` or
`ESCALATE`. `hermes jev-control serve` (or `guard_autostart`) runs a small OpenAI-compatible endpoint on localhost that
recognises that request, asks the decision model "approve / deny / escalate" about the command and returns the word.
Anything it cannot parse, any decision-model error, and any answer below its threshold becomes `ESCALATE`, which Hermes
turns into the normal prompt to you. The guard can therefore only ever make you see *more* prompts than its thresholds
imply, never fewer. Any other request is refused.

## Tool-step routing (experimental, `llm_execution` middleware)

A rule over the conversation and the decision model must agree on the next step family (search / open / read), the
confidence must clear `cascade_tau`, and the arguments must be buildable from text already in the conversation. Then a
synthetic tool-call response is returned instead of calling the main model. Otherwise the call goes through.

## Failure modes

| What breaks | What happens |
|---|---|
| Decision server down or slow | Each feature logs `<feature>_error` and does nothing. Hermes behaves as if the plugin were absent. |
| Approval guard cannot decide | Answers `ESCALATE`: Hermes asks you. |
| Decision model wrong (it can be, at p ≈ 1.0) | A wrong block: use `monitor`, raise the threshold. A wrong allow: the privacy rules and Hermes' own detectors still apply. |
| Compressor decision model down | Drops the oldest half of old tool output and keeps the rest, valid message list preserved. |

## What data goes where

The decision server receives the text being judged (outgoing search or command, memory note, result snippets, tool
output). Nothing is sent anywhere else. The local log has verdicts, scores and timings only (`log_content: true` adds
text and is off by default).
