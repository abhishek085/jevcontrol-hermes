"""Context engine `jev`: compaction by triage instead of summarization.

The built-in compressor asks an LLM to write a summary of the middle of the conversation. This engine keeps every
message and its identity, and instead asks the decision model, in one batched call, which old tool outputs the
agent still needs. Outputs it does not need are replaced by a one-line stub; very long outputs it still needs are
trimmed to their head and tail. No generation call is made. Activate with `context.engine: jev`.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from agent.context_engine import ContextEngine

_MIN_CHARS = 600  # tool outputs shorter than this are left alone
_BATCH = 24


def _text(content) -> str:
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return content if isinstance(content, str) else json.dumps(content, default=str)


def _tokens(messages) -> int:
    return sum(len(_text(m.get("content"))) + len(json.dumps(m.get("tool_calls") or "")) for m in messages) // 4


class JevCompressor(ContextEngine):
    def __init__(self, cfg, jev, log):
        self._cfg, self._jev, self._log = cfg, jev, log
        self.threshold_percent = float(cfg("compress_threshold"))
        self.protect_last_n = int(cfg("compress_keep_last"))

    @property
    def name(self) -> str:
        return "jev"

    def update_model(self, model: str, context_length: int, *args, **kwargs) -> None:
        super().update_model(model, context_length, *args, **kwargs)
        cap = int(self._cfg("compress_threshold_tokens") or 0)  # optional absolute trigger, like compression.threshold_tokens
        if cap:
            self.threshold_tokens = min(self.threshold_tokens or cap, cap)

    def update_from_response(self, usage: Dict[str, Any]) -> None:
        self.last_prompt_tokens = int(usage.get("prompt_tokens") or 0)
        self.last_completion_tokens = int(usage.get("completion_tokens") or 0)
        self.last_total_tokens = int(usage.get("total_tokens") or self.last_prompt_tokens + self.last_completion_tokens)

    def should_compress(self, prompt_tokens: int = None) -> bool:
        tokens = prompt_tokens if prompt_tokens is not None else self.last_prompt_tokens
        return bool(self.threshold_tokens) and tokens >= self.threshold_tokens

    def should_compress_preflight(self, messages: List[Dict[str, Any]]) -> bool:
        return bool(self.threshold_tokens) and _tokens(messages) >= self.threshold_tokens

    def compress(self, messages: List[Dict[str, Any]], current_tokens: Optional[int] = None,
                 focus_topic: Optional[str] = None, force: bool = False, memory_context: str = "") -> List[Dict[str, Any]]:
        t0 = time.perf_counter()
        msgs = list(messages)
        tail_start = max(0, len(msgs) - self.protect_last_n)
        names = {tc.get("id"): (tc.get("function") or {}).get("name", "tool")
                 for m in msgs if m.get("role") == "assistant" for tc in (m.get("tool_calls") or [])}
        cand = [i for i, m in enumerate(msgs[:tail_start]) if m.get("role") == "tool"
                and len(_text(m.get("content"))) >= _MIN_CHARS and not _text(m.get("content")).startswith("[jev-compressor")]
        if not cand:
            self._log({"event": "compress_skip", "why": "no old tool output outside the protected tail"})
            return msgs
        users = [_text(m.get("content")) for m in msgs if m.get("role") == "user"]
        task = (users[0][:800] if users else "") + (f"\nLatest request: {users[-1][:400]}" if len(users) > 1 else "")
        if focus_topic:
            task += f"\nFocus: {focus_topic}"
        need = {}
        try:
            for s in range(0, len(cand), _BATCH):
                chunk = cand[s:s + _BATCH]
                parts = []
                for k, i in enumerate(chunk):
                    t = _text(msgs[i].get("content"))
                    parts.append(f"Output {k + 1} (from {names.get(msgs[i].get('tool_call_id'), 'tool')}, {len(t)} chars):\n"
                                 f"{t[:500]}{' ... ' + t[-150:] if len(t) > 650 else ''}")
                probs, ms = self._jev.yes_probs(f"Task: {task}\n\n" + "\n\n".join(parts),
                                                [f"Will the agent still need the full content of output {k + 1} to "
                                                 "finish the task?" for k in range(len(chunk))])
                need.update(zip(chunk, probs))
        except Exception as e:  # decision model down: fall back to dropping the oldest half, keep the rest trimmed
            self._log({"event": "compress_error", "error": str(e)[:200]})
            need = {i: (0.0 if n < len(cand) // 2 else 1.0) for n, i in enumerate(cand)}
        before = _tokens(msgs)
        tau, trim = float(self._cfg("compress_need_tau")), int(self._cfg("compress_trim_chars"))
        target = int(self.threshold_tokens * 0.6) if self.threshold_tokens else 0
        dropped = trimmed = 0

        def stub(i):
            t = _text(msgs[i].get("content"))
            msgs[i] = dict(msgs[i], content=f"[jev-compressor: {names.get(msgs[i].get('tool_call_id'), 'tool')} output "
                                            f"({len(t)} chars) removed as no longer needed. It began: {t[:240]}]")

        for i in cand:
            if need[i] < tau:
                stub(i)
                dropped += 1
            elif len(_text(msgs[i].get("content"))) > trim:
                t = _text(msgs[i].get("content"))
                msgs[i] = dict(msgs[i], content=t[: trim * 3 // 4] + f"\n[jev-compressor: {len(t) - trim} chars trimmed]\n"
                                                + t[-trim // 4:])
                trimmed += 1
        for i in sorted((i for i in cand if need[i] >= tau), key=lambda i: need[i]):  # still too big: least needed first
            if not target or _tokens(msgs) <= target:
                break
            stub(i)
            dropped += 1
        self.compression_count += 1
        self.last_prompt_tokens = 0  # "no real usage yet": the next check uses the rough estimate
        self._log({"event": "compress", "candidates": len(cand), "dropped": dropped, "trimmed": trimmed,
                   "tokens_before": before, "tokens_after": _tokens(msgs),
                   "ms": round((time.perf_counter() - t0) * 1000)})
        return msgs
