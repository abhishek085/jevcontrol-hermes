# Results, method and caveats

Everything here was measured on one setup: Hermes on an Apple M4 Pro (24 GB), main model **Qwen3.8-27B** on a remote
server, decision model **spark-s1-4b (NVFP4)** behind a Jev-style `/v1/decide` API on the same remote host, tracing with a
local Langfuse. Earlier rounds used Gemma 4 (12B, E4B) locally. Dates: 2026-09-29 to 2026-10-04.

Labels for every test set were written **before** any model saw them. The decision model's confidence is not calibrated
(it can be wrong at p ≈ 1.0), sets are small, and the author labelled them. Treat the numbers as indicative.

## 1. Approval guard

Hermes' real smart-approval function, run over labelled commands that Hermes' own detector flags. Compared with
Qwen3.8-27B as the approving model (Hermes' default behaviour with this setup).

The guard's prompt was tuned on a first set (62 commands) and then tested once on a **held-out set** (60 written, 54 flagged
by Hermes): 22 harmless, 17 dangerous, 5 with instructions aimed at the reviewer, 10 unclear.

| Held-out, 54 flagged commands | Qwen3.8-27B | jev-guard |
|---|---|---|
| Harmless auto-approved | 21 / 22 | 16 / 22 (5 asked you, 1 denied) |
| Dangerous + injection approved (unsafe) | **0 / 22** | **0 / 22** |
| Unclear approved | 3 / 10 | **0 / 10** |
| Time per verdict (median / p90 / max) | 2.5 s / 12.7 s / 93 s (timeout) | **88 ms** / 91 ms / 0.7 s |

The first prompt wording denied 13 of 22 harmless commands (it was told only the detector's label); asking "how hard is this
to recover?" fixed that. The guard is deliberately more cautious than Qwen. In one live session it approved a recursive delete of
a temp folder in 75 ms.

Not covered: Hermes' own detector does not flag some commands that send credentials off the machine, so they never reach
approvals at all (the privacy guard covers them), and one-shot `hermes chat -q` sessions block flagged commands before any
approval model is asked.

## 2. Privacy guard

36 outbound tool calls (19 leaks, 17 normal): credentials, personal data and private local content versus ordinary searches,
page fetches and downloads. Fake credentials only.

| | caught leaks | normal calls blocked | latency |
|---|---|---|---|
| Rules only | 8 / 19 | 0 / 17 | none |
| Rules + decision model | **18 / 19** | **0 / 17** | median 78 ms |

The one miss: a search query that was a pasted line of private source code (scored 0.98 "public"). Live: it blocked a
password search, and allowed 25 normal calls with a median of 84 ms and a maximum of 151 ms.

## 3. Memory gatekeeper

27 candidate memory writes: 10 real durable facts, 5 procedures, 5 task-progress notes, 4 orders to the agent, 3 secrets.
Kept **10 / 10** real facts; blocked **17 / 17** misfiled writes, 16 with the right reason (one "always run the linter before
committing" was called a procedure instead of an order). Live: blocked a deploy procedure, allowed a real user preference.

## 4. Search picker

Paired runs (off / on, shuffled, idle server, prompt cache warmed before each run, a server-load probe before and a request
counter after each run).

| Version | Runs | Result text | Wall per run (on - off) | Notes |
|---|---|---|---|---|
| v1: keep the 3 top-scored results, re-ranked | 16 pairs, 8 tasks | -39% (157k → 96k chars) | **+5.1 s**, CI [-3.8, +15.4] | On a task asking for an "official page" it dropped the right page; the agent then made 12-14 calls instead of 5-7. |
| v2 (current): drop only results below `search_tau` 0.15, keep order | 16 pairs, 8 new tasks | -7% (207k → 192k chars) | **-3.7 s**, CI [-9.1, +1.0] | Main-model time -4.4 s, CI [-9.4, -0.1]. No answer-affecting drops. |

The effect is small and the wall-time interval includes zero. The picker is safest on narrow queries (more irrelevant results).

## 5. Context compressor

- **Offline replay** of a recorded session (15 messages, about 12,600 tokens): four old tool outputs removed and one trimmed,
  about 2,500 tokens left in 0.85 s, one decision call, no generation call; roles and ids unchanged.
- **Live, against Hermes' built-in compressor** (6 runs each, three long research tasks, trigger lowered to 27,000 tokens):
  **inconclusive.** The built-in compressor's own log said "no progress" and it made no summary call either: about 22,000 of
  each 30-40k prompt is the fixed system prompt and tool list, and most tool output was short. The wall-time gap
  (Jev 127 s vs built-in 194 s) is task variance, driven by one 444 s built-in outlier.
- **Live sessions** with `context.engine: jev`: 2 real compactions of about 260 ms, prompt 39,066 → 21,692 tokens. After a
  compaction the provider's prompt cache is lost for one call, as with any compaction.

A fair test needs sessions of 100k+ tokens of real tool output.

## 6. Tool-step routing (experimental)

The first idea: let the decision model take routine first steps so the main model is called less.

| Run | Main-model calls | Wall time |
|---|---|---|
| Gemma 4 E4B, 74 randomized runs (off / off / on) | 3.2 → 2.1 per task (-35%), output tokens -45% | -2.6 s, CI [-7.9, +2.8]: not significant |
| Gemma 4 12B, two models on one 24 GB machine | 26 → 16 | **+78%**: memory contention |
| Qwen3.8-27B remote, 24 runs, idle server, cache warmed | 3.50 → 2.50 | -1.6 s, CI [-4.1, +1.4]: not significant |

One main-model call is skipped per task, but that call is the cheapest one (about 60 output tokens, about 1 s on a warm
cache), so the saving is small. It stays off by default.

An earlier Qwen run was confounded by the shared server (cold prompt caches adding 10-15 s to half the runs, and later calls of
86-114 s under someone else's load); the idle-gated rerun above replaced it.

## 7. Live sessions

Three real Hermes sessions with everything on (`enforce`), traced in Langfuse: privacy block, memory block, memory allow,
picker dropping 2 of 6 results, approval of a recursive delete in 75 ms, 2 compactions. No errors. A reported oddity was the
main model writing a malformed `write_file` call for a long report, which Hermes retried (about 100 s lost): a model and
Hermes issue, not this plugin.

## 8. Problems found along the way

- A Jev-style decision server returned HTTP 500 for any state containing the lowercase word "content" (every web page
  Hermes returns contains it). Fixed on the server; the client retries once on 5xx.
- Hermes ignores `auxiliary.approval.base_url` when `provider` is `auto`; use `provider: custom` and a non-empty key.
- Hermes installs from GitHub are blocked by its scanner on any HIGH-severity finding, including words like "share ... context" in
  a README; the repo was cleaned until a fresh install is allowed.

## Not tested

Paid or hosted main models, other decision models, other agent frameworks, long (100k+ token) sessions, streaming-only
setups, approval flows on gateway platforms, and any claim about cost.
