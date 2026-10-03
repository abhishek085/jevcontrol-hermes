"""Memory gatekeeper (`pre_tool_call` on the `memory` tool).

Hermes' own prompt says memory is only for declarative facts that matter in every session; procedures belong in
skills, and task progress belongs nowhere. The model often saves the wrong things anyway. Each add/replace is
classified with one decision-model call; in `enforce` mode a misfiled write is blocked with a message that tells the
agent where it belongs (or to rephrase it), and secrets are always refused.
"""

from __future__ import annotations

from . import privacy

_QUESTION = ("A personal AI agent wants to save the text in the state to its long-term memory, which is loaded into "
             "every future session and has a small size budget. What kind of text is it?")
OPTIONS = {
    "durable_fact": "a declarative fact that stays true and matters in every future session: who the user is, "
                    "their stable preferences, their environment, standing conventions",
    "procedure": "how to do a particular kind of task: steps, commands, pitfalls or tool tips for that task type",
    "transient": "about the current task only or soon stale: progress, results of today's work, temporary state, "
                 "something that was just done",
    "directive": "worded as an order to the agent (always do X, never do Y) instead of a fact about the user",
}
_ADVICE = {
    "procedure": "This is task know-how; save it as a skill (skill_manage) instead of memory.",
    "transient": "This is about the current task or will be stale soon; do not save it to memory.",
    "directive": "Rephrase it as a declarative fact about the user (e.g. 'User prefers concise answers'), "
                 "not as an order, then save again.",
}


def _writes(args: dict) -> list[str]:
    args = args or {}
    ops = args.get("operations") if args.get("action") == "batch" else [args]
    return [str(op.get("content") or op.get("new_text") or "") for op in (ops or [])
            if (op or {}).get("action") in ("add", "replace", "update") and (op.get("content") or op.get("new_text"))]


def check(args: dict, jev, cfg) -> dict:
    """-> {"verdict": "allow"|"block", "message", "picks"}; removals and reads always pass."""
    picks = []
    target = str((args or {}).get("target") or "memory")
    for text in _writes(args):
        hit = privacy.rule_hit("memory", text)
        if hit:
            return {"verdict": "block", "picks": [{"pick": "secret"}], "layer": "rule",
                    "message": f"BLOCKED by jev-control: this memory entry contains {hit}. Never store credentials."}
        r = jev.choice(f"Memory target: {target}\nText to save:\n{text[:2000]}", _QUESTION, OPTIONS)
        picks.append({"pick": r["pick"], "p": round(r["p"], 4), "ms": round(r["ms"])})
        if r["pick"] != "durable_fact" and r["p"] >= float(cfg("memory_tau")):
            return {"verdict": "block", "picks": picks, "layer": "jev",
                    "message": f"BLOCKED by the jev-control memory gatekeeper: {_ADVICE[r['pick']]}"}
    return {"verdict": "allow", "picks": picks, "layer": "jev" if picks else "none"}
