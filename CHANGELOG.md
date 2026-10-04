# Changelog

## 0.2.0 - 2026-10-04

First public version of the Jev decision layer for Hermes.

### Added
- **Privacy guard**: blocks outgoing searches, URLs, browser scripts and network commands that would reveal credentials,
  personal data or private local content (`pre_tool_call`).
- **Memory gatekeeper**: files each memory write as a durable fact, task know-how, task progress or an order to the agent,
  and refuses secrets (`pre_tool_call` on `memory`).
- **Search picker**: removes web-search results the decision model is fairly sure are unrelated (`transform_tool_result`).
- **Context compressor**: a Hermes context engine (`jev`) that drops old tool output the agent no longer needs, with no
  summary-writing LLM call.
- **Approval guard**: a local OpenAI-compatible endpoint for Hermes' smart approvals, answered by the decision model;
  it starts with Hermes (`guard_autostart`).
- `hermes jev-control setup | doctor | report | serve` commands, three presets (`observe`, `balanced`, `full`).
- Decision-model client with two transports: a Jev-style `/v1/decide` API, or any OpenAI-compatible server that returns
  logprobs.
- Unit tests (`tests/`), GitHub Actions workflow, documentation (`docs/`).

### Changed
- Tool-step routing (from 0.1.0) is now clearly marked experimental and stays off by default.
- Content logging stays opt-in; the local log never contains prompts, arguments or conversation text unless
  `log_content` is enabled.
- Plugin no longer imports Hermes internals at load time.

## 0.1.0 - 2026-09-30

Initial beta: trace review tool and experimental tool-step routing (`routing_mode: cascade`), off by default.
