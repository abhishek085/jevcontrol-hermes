"""Minimal client for a typed decision API (`POST {spark_url}/decide`, served by open-spark-Jev / JevControl).

Every jev-control feature asks its questions through here, so retries, timeouts and the model name live in one place.
"""

from __future__ import annotations

import re
import time

import httpx


class Jev:
    def __init__(self, cfg):
        self._cfg = cfg  # callable: key -> setting value

    def decide(self, state: str, questions: list[dict]) -> tuple[dict, float]:
        """Ask several questions about one state in a single call -> ({question id: decision}, ms)."""
        body = {"state": state, "questions": questions}
        model = self._cfg("spark_model")
        if model and model != "spark-s1":
            body["model"] = model
        t = time.perf_counter()
        for attempt in (0, 1):
            r = httpx.post(f"{self._cfg('spark_url')}/decide", json=body, timeout=float(self._cfg("jev_timeout_s")))
            if r.status_code < 500 or attempt:
                break
            # Workaround: the open-spark-Jev decision server tested here (Oct 2026) returns 500 for any state that
            # contains the lowercase word "content". Retry once with that word capitalised.
            body = dict(body, state=re.sub(r"content", "Content", state))
        r.raise_for_status()
        return r.json()["decisions"], (time.perf_counter() - t) * 1000

    def choice(self, state: str, instructions: str, options: dict[str, str]) -> dict:
        """-> {"pick", "p", "probs", "ms"} for one multiple-choice question."""
        q = {"id": "q", "type": "choice", "instructions": instructions,
             "options": [{"id": k, "definition": v} for k, v in options.items()]}
        d, ms = self.decide(state, [q])
        d = d["q"]
        probs = {k: float(v) for k, v in (d.get("probabilities") or {}).items()}
        pick = d.get("selected") or max(probs, key=probs.get)
        return {"pick": pick, "p": probs.get(pick, float(d.get("confidence") or 0.0)), "probs": probs, "ms": ms}

    def yes_probs(self, state: str, instructions: list[str]) -> tuple[list[float], float]:
        """P(yes) for several yes/no questions about one state, in one call."""
        qs = [{"id": f"b{i}", "type": "boolean", "instructions": text} for i, text in enumerate(instructions)]
        d, ms = self.decide(state, qs)
        return [float((d[f"b{i}"].get("probabilities") or {}).get("true", 0.0)) for i in range(len(qs))], ms
