"""`hermes jev-control report`: what each feature did, from ~/.hermes/logs/jev_routing.jsonl (no content is logged)."""

from __future__ import annotations

import collections
import json
import statistics
import time


def _ms(xs):
    xs = [x for x in xs if x is not None]
    return f"median {statistics.median(xs):.0f} ms, max {max(xs):.0f} ms (n={len(xs)})" if xs else "n/a"


def report(since_minutes: float = 0.0) -> None:
    from hermes_constants import get_hermes_home
    path = get_hermes_home() / "logs" / "jev_routing.jsonl"
    if not path.exists():
        print(f"No log at {path} yet.")
        return
    cutoff = time.time() - since_minutes * 60 if since_minutes else 0
    ev = collections.defaultdict(list)
    for line in path.open():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if cutoff and r.get("ts", 0) < cutoff:
            continue
        ev[r["event"]].append(r)

    print("== Privacy guard (outgoing search / URL / network commands)")
    P = ev["privacy_guard"]
    blocked = [r for r in P if r.get("verdict") == "block"]
    print(f"  checked {len(P)}; would block / blocked {len(blocked)}; model latency {_ms([r.get('ms') for r in P])}")
    for r in blocked[-5:]:
        print(f"    - {r.get('tool')}: {r.get('why')} ({r.get('layer')}, mode {r.get('mode')})")

    print("== Memory gatekeeper (writes to long-term memory)")
    M = ev["memory_gate"]
    mb = [r for r in M if r.get("verdict") == "block"]
    print(f"  checked {len(M)}; would block / blocked {len(mb)}")
    for r in mb[-5:]:
        picks = r.get("picks") or []
        print(f"    - classified as {picks[-1].get('pick') if picks else '?'} ({r.get('layer')}, mode {r.get('mode')})")

    print("== Search picker")
    S = ev["search_pick"]
    n, k = sum(r.get("n", 0) for r in S), sum(r.get("kept", 0) for r in S)
    cb, ca = sum(r.get("chars_before", 0) for r in S), sum(r.get("chars_after", 0) for r in S)
    print(f"  {len(S)} searches; results {n} -> {k}; text {cb} -> {ca} chars" + (f" ({100 * (1 - ca / cb):.0f}% less)" if cb else "")
          + f"; latency {_ms([r.get('ms') for r in S])}")

    print("== Approval guard (flagged shell commands)")
    G = ev["guard"]
    c = collections.Counter(r.get("verdict") for r in G)
    print(f"  {len(G)} verdicts: approve {c['approve']}, deny {c['deny']}, escalate {c['escalate']}; latency {_ms([r.get('ms') for r in G])}")
    for r in G[-5:]:
        print(f"    - {r.get('verdict')} p={r.get('p')} ({r.get('flagged')})")

    print("== Context compressor")
    C = ev["compress"]
    print(f"  {len(C)} compactions; skipped (nothing to drop) {len(ev['compress_skip'])}")
    for r in C[-5:]:
        print(f"    - {r.get('tokens_before')} -> {r.get('tokens_after')} est. tokens, dropped {r.get('dropped')}, "
              f"trimmed {r.get('trimmed')}, {r.get('ms')} ms")

    errs = {k: len(v) for k, v in ev.items() if k.endswith("_error")}
    print("== Errors (all fail open):", errs or "none")
    L = ev["llm"]
    if L:
        print(f"== Main model: {len(L)} calls, {_ms([r.get('llm_ms') for r in L])}")
