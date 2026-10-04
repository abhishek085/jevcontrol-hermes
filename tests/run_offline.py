"""Offline evaluation of the privacy guard and the memory gatekeeper against a live decision API.

usage: python tests/run_offline.py --spark-url http://HOST:8400/v1 [--spark-model NAME] [--out results.json]
Reports the rule layer alone and rules + decision model, with per-case latency.
"""

import argparse
import importlib
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT / "tests"))
pkg = ROOT.name
privacy = importlib.import_module(f"{pkg}.privacy")
memory_gate = importlib.import_module(f"{pkg}.memory_gate")
Jev = importlib.import_module(f"{pkg}.jev_client").Jev
from memory_cases import CASES as MEMORY  # noqa: E402
from privacy_cases import CASES as PRIVACY  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--spark-url", required=True)
ap.add_argument("--spark-model", default="spark-s1")
ap.add_argument("--api", choices=("decide", "chat"), default="decide", help="decide = Jev-style /v1/decide; chat = OpenAI-compatible with logprobs")
ap.add_argument("--out", default="")
a = ap.parse_args()
cfg = {"spark_url": a.spark_url, "spark_model": a.spark_model, "spark_api": a.api, "jev_timeout_s": 15, "privacy_tau": 0.8, "memory_tau": 0.7}.get
jev = Jev(cfg)
rows = []

print("== privacy guard")
for tool, args, want in PRIVACY:
    text = privacy.outgoing_text(tool, args) or ""
    rule = "block" if text and privacy.rule_hit(tool, text) else "allow"
    try:
        v = privacy.check(tool, args, jev, cfg)
    except Exception as e:  # the plugin fails open; count it as allow
        v = {"verdict": "allow", "layer": "error", "why": str(e)[:80]}
    rows.append({"feature": "privacy", "case": f"{tool}: {text[:70]}", "want": want, "rule": rule, **v})
    flag = "" if v["verdict"] == want else "   <-- WRONG"
    print(f"{want:5} rule={rule:5} final={v['verdict']:5} {v.get('layer'):5} {v.get('pick', ''):8} "
          f"{v.get('p', '')!s:6} {tool}: {text[:60]}{flag}")

print("\n== memory gatekeeper")
for text, want in MEMORY:
    try:
        v = memory_gate.check({"action": "add", "target": "user", "content": text}, jev, cfg)
    except Exception as e:
        v = {"verdict": "allow", "layer": "error", "picks": [], "message": str(e)[:80]}
    got = "allow" if v["verdict"] == "allow" else ((v.get("picks") or [{}])[-1].get("pick") or "secret")
    if v.get("layer") == "rule":
        got = "secret"
    rows.append({"feature": "memory", "case": text[:70], "want": want, "got": got, **v})
    flag = "" if got == want or (want != "allow" and got != "allow" and want != "secret") else "   <-- WRONG"
    pk = (v.get("picks") or [{}])[-1]
    print(f"{want:9} got={got:12} {pk.get('pick', ''):12} {pk.get('p', '')!s:6} {text[:60]}{flag}")


def summary():
    P = [r for r in rows if r["feature"] == "privacy"]
    for name, key in (("rules only", "rule"), ("rules + jev", "verdict")):
        caught = sum(1 for r in P if r["want"] == "block" and r[key] == "block")
        false = sum(1 for r in P if r["want"] == "allow" and r[key] == "block")
        nb = sum(1 for r in P if r["want"] == "block")
        print(f"privacy {name:12}: caught {caught}/{nb} leaks, wrongly blocked {false}/{len(P) - nb} normal calls")
    ms = [r["ms"] for r in P if "ms" in r]
    if ms:
        print(f"privacy jev latency: median {statistics.median(ms):.0f} ms, max {max(ms):.0f} ms over {len(ms)} model calls")
    M = [r for r in rows if r["feature"] == "memory"]
    ok_allow = sum(1 for r in M if r["want"] == "allow" and r["got"] == "allow")
    na = sum(1 for r in M if r["want"] == "allow")
    blocked = sum(1 for r in M if r["want"] != "allow" and r["got"] != "allow")
    exact = sum(1 for r in M if r["want"] != "allow" and r["got"] == r["want"])
    print(f"memory: kept {ok_allow}/{na} real facts, blocked {blocked}/{len(M) - na} misfiled writes "
          f"({exact} with the right reason)")


print()
summary()
if a.out:
    json.dump(rows, open(a.out, "w"), indent=1, default=str)
