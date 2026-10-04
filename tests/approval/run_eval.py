"""Run Hermes' real smart-approval function over the labelled commands with one guard configuration.

usage (from a Hermes checkout, with its venv):
  HERMES_HOME=<temp home whose config.yaml sets auxiliary.approval> python run_eval.py <label> <out.jsonl> [heldout_commands|dev_commands]
Only commands that Hermes' own detector flags are evaluated (others never reach smart approval).
"""
import json, sys, time
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import importlib; _m = importlib.import_module(sys.argv[3] if len(sys.argv) > 3 else "heldout_commands"); SAFE, DANGEROUS, INJECTION, AMBIGUOUS = _m.SAFE, _m.DANGEROUS, _m.INJECTION, _m.AMBIGUOUS
from tools.approval_detection import detect_dangerous_command
from tools.approval_smart import _smart_approve

label, out = sys.argv[1], sys.argv[2]
with open(out, "w") as f:
    for cat, cmds in (("safe", SAFE), ("dangerous", DANGEROUS), ("injection", INJECTION), ("ambiguous", AMBIGUOUS)):
        for cmd in cmds:
            flagged, key, desc = detect_dangerous_command(cmd)
            if not flagged:
                f.write(json.dumps({"guard": label, "cat": cat, "cmd": cmd, "flagged": False}) + "\n")
                continue
            t = time.perf_counter()
            verdict = _smart_approve(cmd, desc)
            ms = (time.perf_counter() - t) * 1000
            f.write(json.dumps({"guard": label, "cat": cat, "cmd": cmd, "flagged": True, "desc": desc,
                                "verdict": verdict, "ms": round(ms)}) + "\n")
            f.flush()
            print(f"{label:5} {cat:9} {verdict:8} {ms:7.0f}ms  {cmd[:70]}", flush=True)
