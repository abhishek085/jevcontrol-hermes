"""Search-result picker (`transform_tool_result` on `web_search`).

Scores every search result for "does this help answer the user's request?" in one batched decision-model call, then
removes the results it is fairly sure are unrelated (original order kept). Fewer, better results means fewer tokens re-read on every later model call and better
pages opened next. The result keeps Hermes' JSON shape; a short note says how many results were dropped.
"""

from __future__ import annotations

import json


def _results(result: str):
    try:
        data = json.loads(result)
    except (TypeError, ValueError):
        return None, None
    web = ((data or {}).get("data") or {}).get("web") if isinstance(data, dict) else None
    return (data, web) if isinstance(web, list) and web else (None, None)


def pick(result: str, query: str, request: str, jev, cfg) -> tuple[str | None, dict]:
    """-> (new result string or None to leave it unchanged, log record)."""
    data, web = _results(result)
    if web is None or len(web) <= int(cfg("search_min_keep")):
        return None, {"why": "nothing to drop"}
    lines = [f"Result {i + 1}: {r.get('title', '')} | {r.get('url', '')}\n{str(r.get('description') or '')[:500]}"
             for i, r in enumerate(web)]
    state = f"User request: {request[:600] or query}\nSearch query: {query}\n\n" + "\n\n".join(lines)
    probs, ms = jev.yes_probs(state, [f"Is result {i + 1} likely to contain information needed for the user's "
                                      "request?" for i in range(len(web))])
    # Drop only results the model is fairly sure are useless; keep the search engine's order. (v1 kept the top 3 by
    # score and re-ranked; on a task asking for an "official page" that dropped the page, and the agent fell back to
    # many browser steps.)
    keep = [i for i in range(len(web)) if probs[i] >= float(cfg("search_tau"))]
    for i in sorted(range(len(web)), key=lambda i: -probs[i]):  # never leave fewer than search_min_keep
        if len(keep) >= int(cfg("search_min_keep")):
            break
        if i not in keep:
            keep.append(i)
    keep = sorted(keep)[: int(cfg("search_max_keep"))]
    rec = {"n": len(web), "kept": len(keep), "probs": [round(p, 3) for p in probs], "ms": round(ms)}
    if len(keep) == len(web):
        return None, rec
    data["data"]["web"] = [web[i] for i in keep]
    data["jev_note"] = (f"jev-control removed {len(web) - len(keep)} of {len(web)} results as unrelated to the request; "
                        "search again with other terms if they are not enough.")
    return json.dumps(data, ensure_ascii=False, indent=2), rec
