"""`hermes jev-control ...`: setup, doctor, report, serve."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

PRESETS = {
    # log-only: nothing is blocked or changed, you just see what the features would do
    "observe": {"privacy_guard": "monitor", "memory_gate": "monitor", "search_pick": False, "compressor": False,
                "approvals": False},
    # recommended starting point: block leaks, drop unrelated search results, fast approvals; memory only logged
    "balanced": {"privacy_guard": "enforce", "memory_gate": "monitor", "search_pick": True, "compressor": False,
                 "approvals": True},
    # everything on, including the context engine and memory blocking
    "full": {"privacy_guard": "enforce", "memory_gate": "enforce", "search_pick": True, "compressor": True,
             "approvals": True},
}
_P = "plugins.entries.jev-control.settings."


def _hermes() -> list[str]:
    exe = sys.argv[0] if "hermes" in os.path.basename(sys.argv[0]) else (shutil.which("hermes") or "hermes")
    return [exe]


def _set(key: str, value, dry: bool) -> bool:
    text = str(value).lower() if isinstance(value, bool) else str(value)
    print(f"  hermes config set {key} {text}")
    if dry:
        return True
    r = subprocess.run(_hermes() + ["config", "set", key, text], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"    FAILED: {(r.stderr or r.stdout).strip()[:200]}")
    return r.returncode == 0


def setup(args, cfg) -> int:
    preset = PRESETS[args.preset]
    url = args.spark_url or cfg("spark_url")
    model = args.spark_model or cfg("spark_model")
    api = args.api or cfg("spark_api")
    print(f"jev-control setup  (preset: {args.preset}{', dry run' if args.dry_run else ''})\n")
    ok = True
    for key, value in (("spark_url", url), ("spark_model", model), ("spark_api", api),
                       ("privacy_guard", preset["privacy_guard"]), ("memory_gate", preset["memory_gate"]),
                       ("search_pick", preset["search_pick"]), ("compressor", preset["compressor"]),
                       ("guard_autostart", preset["approvals"]), ("routing_mode", "off")):
        ok &= _set(_P + key, value, args.dry_run)
    ok &= _set("context.engine", "jev" if preset["compressor"] else "compressor", args.dry_run)
    if preset["approvals"]:
        for key, value in (("approvals.mode", "smart"), ("auxiliary.approval.provider", "custom"),
                           ("auxiliary.approval.base_url", f"http://{cfg('guard_host')}:{cfg('guard_port')}/v1"),
                           ("auxiliary.approval.api_key", "jev-local"), ("auxiliary.approval.model", "jev-guard"),
                           ("auxiliary.approval.timeout", 30)):
            ok &= _set(key, value, args.dry_run)
    print("\nDone. Start Hermes as usual (restart a running gateway). Check everything with: hermes jev-control doctor"
          if ok else "\nSome settings failed; fix them by hand with `hermes config edit`.")
    return 0 if ok else 1


def _config_file() -> dict | None:
    """Hermes' config.yaml as a dict, or None when it cannot be read (reported by the doctor, never silent)."""
    try:
        from hermes_constants import get_hermes_home
        text = (get_hermes_home() / "config.yaml").read_text()
    except Exception:
        return None
    try:
        from ruamel.yaml import YAML  # what Hermes itself uses
        return YAML(typ="safe").load(text) or {}
    except ImportError:
        pass
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except Exception:
        return None


def doctor(cfg) -> int:
    from .jev_client import Jev
    fails = 0

    def line(ok, what, detail=""):
        nonlocal fails
        fails += 0 if ok else 1
        print(f"  {'OK  ' if ok else 'FAIL'} {what}{(' - ' + detail) if detail else ''}")

    print("jev-control doctor\n")
    print("Decision model")
    jev = Jev(cfg)
    try:
        r = jev.choice("A user asked for the weather and the agent already has the answer.",
                       "What should the agent do next?",
                       {"answer": "give the answer to the user", "search": "search for more information"})
        line(True, f"{cfg('spark_api')} API at {cfg('spark_url')} (model {cfg('spark_model')})",
             f"answered '{r['pick']}' p={r['p']:.2f} in {r['ms']:.0f} ms")
        line(r["p"] > 0.6, "answer is sensible and confident", "" if r["p"] > 0.6 else
             "low confidence on an easy question: wrong model, thinking mode on, or no logprobs support")
    except Exception as e:
        line(False, f"{cfg('spark_api')} API at {cfg('spark_url')}", f"{type(e).__name__}: {str(e)[:120]}")
        print("       Is the decision server running? For `chat` it must return logprobs; for `decide` it must serve "
              "POST /v1/decide. See the README, section 'Decision server'.")

    print("\nFeatures (from config)")
    on = lambda v: str(v).lower() not in ("off", "false", "none", "0", "")
    for key in ("privacy_guard", "memory_gate", "search_pick", "compressor"):
        v = cfg(key)
        print(f"       {key:14} {'off' if not on(v) else v}")
    conf = _config_file()
    if conf is None:
        line(False, "read Hermes config.yaml", "no YAML library found; skipping the context-engine and approval checks")
        conf = {}
    engine = (conf.get("context") or {}).get("engine", "compressor")
    if on(cfg("compressor")) and conf:
        line(engine == "jev", "context engine", f"context.engine is '{engine}'" + ("" if engine == "jev" else " - set it to 'jev'"))
    aux = ((conf.get("auxiliary") or {}).get("approval") or {})
    if on(cfg("guard_autostart")) and conf:
        want = f"http://{cfg('guard_host')}:{cfg('guard_port')}/v1"
        wired = str(aux.get("base_url", "")).rstrip("/") == want and aux.get("provider") == "custom" and bool(aux.get("api_key"))
        line(wired, "approval guard wired into Hermes",
             "" if wired else f"auxiliary.approval needs provider: custom, api_key (any non-empty), base_url: {want}")
        try:
            import httpx
            httpx.get(f"{want}/models", timeout=3).raise_for_status()
            line(True, "approval guard server listening", want)
        except Exception as e:
            line(False, "approval guard server listening", f"{type(e).__name__} (it starts with Hermes; try `hermes jev-control serve`)")
    try:
        from hermes_constants import get_hermes_home
        d = get_hermes_home() / "logs"
        d.mkdir(parents=True, exist_ok=True)
        line(os.access(d, os.W_OK), "log directory writable", str(d / "jev_routing.jsonl"))
    except Exception as e:
        line(False, "log directory", str(e)[:80])
    print("\nAll good." if not fails else f"\n{fails} problem(s) found.")
    return 1 if fails else 0


def add_arguments(subparser) -> None:
    subs = subparser.add_subparsers(dest="jev_command")
    s = subs.add_parser("setup", help="Write the recommended settings into your Hermes config")
    s.add_argument("--preset", choices=sorted(PRESETS), default="balanced",
                   help="observe (log only) | balanced (default) | full (everything, incl. context engine)")
    s.add_argument("--spark-url", default=None, help="decision server base URL, e.g. http://localhost:8400/v1")
    s.add_argument("--spark-model", default=None, help="decision model name")
    s.add_argument("--api", choices=("decide", "chat"), default=None,
                   help="decide = Jev-style /v1/decide API; chat = OpenAI-compatible server with logprobs")
    s.add_argument("--dry-run", action="store_true", help="print the commands without running them")
    subs.add_parser("doctor", help="Check the decision server and the config")
    r = subs.add_parser("report", help="Summarize what each feature did (from the local log)")
    r.add_argument("--since-minutes", type=float, default=0, help="only events from the last N minutes")
    g = subs.add_parser("serve", help="Run the approval-guard server in the foreground (normally it starts with Hermes)")
    g.add_argument("--host", default=None)
    g.add_argument("--port", type=int, default=None)


def run(args, cfg, log) -> int:
    cmd = getattr(args, "jev_command", None)
    if cmd == "setup":
        return setup(args, cfg)
    if cmd == "doctor":
        return doctor(cfg)
    if cmd == "report":
        from .report import report
        report(args.since_minutes)
        return 0
    if cmd == "serve":
        from . import guard
        guard.serve(args.host or cfg("guard_host"), int(args.port or cfg("guard_port")), cfg, log)
        return 0
    print("Usage: hermes jev-control {setup,doctor,report,serve} ...   (try: hermes jev-control setup --dry-run)")
    return 0
