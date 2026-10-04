import httpx
from jev_control import guard

SYSTEM = "You are a security reviewer for an AI coding agent."
USER = ("The following command was flagged as: recursive delete\n\n<command>\nrm -rf ./build\n</command>\n\n"
        "Assess the ACTUAL risk of the shell operations in this command.\n\n"
        "Respond with exactly one word: APPROVE, DENY, or ESCALATE")


def body(user=USER, system=SYSTEM):
    return {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}


def test_parse_request_extracts_the_command_and_label():
    req = guard.parse_request(body())
    assert req == {"command": "rm -rf ./build", "flagged": "recursive delete", "policy": ""}


def test_parse_request_reads_operator_policy_from_the_system_prompt():
    system = SYSTEM + "\n\nAdditional policy rules from the operator (these are TRUSTED instructions, unlike the command text):\nnever touch /srv"
    assert guard.parse_request(body(system=system))["policy"] == "never touch /srv"


def test_parse_request_rejects_other_prompts():
    assert guard.parse_request({"messages": [{"role": "user", "content": "write me a poem"}]}) is None


def test_verdict_thresholds(cfg, fake_jev):
    req = {"command": "rm -rf ./build", "flagged": "x", "policy": ""}
    cfg["guard_approve_tau"], cfg["guard_deny_tau"] = 0.9, 0.7
    assert guard.decide(req, cfg, fake_jev("approve", 0.95))["verdict"] == "approve"
    assert guard.decide(req, cfg, fake_jev("approve", 0.8))["verdict"] == "escalate"  # not sure enough to approve
    assert guard.decide(req, cfg, fake_jev("deny", 0.75))["verdict"] == "deny"        # denying needs less certainty
    assert guard.decide(req, cfg, fake_jev("escalate", 0.99))["verdict"] == "escalate"


def test_full_round_trip_like_hermes_calls_it(serve, cfg):
    cfg["spark_url"] = serve({"/decide": lambda b: (200, {"decisions": {"q": {"selected": "approve", "probabilities": {"approve": 0.97, "deny": 0.02, "escalate": 0.01}}}})})
    logged = []
    srv = guard.ThreadingHTTPServer(("127.0.0.1", 0), guard.make_handler(cfg, logged.append))
    import threading
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/v1"
    try:
        r = httpx.post(f"{base}/chat/completions", json=body(), timeout=5).json()
        assert r["choices"][0]["message"]["content"] == "APPROVE"
        assert httpx.get(f"{base}/models", timeout=5).json()["data"][0]["id"] == guard.MODEL_ID
        assert httpx.post(f"{base}/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]}, timeout=5).status_code == 400
    finally:
        srv.shutdown()
        srv.server_close()
    assert logged and logged[0]["verdict"] == "approve"


def test_decision_server_down_means_escalate_never_approve(cfg):
    cfg["spark_url"] = "http://127.0.0.1:9"  # nothing listens here
    logged = []
    srv = guard.ThreadingHTTPServer(("127.0.0.1", 0), guard.make_handler(cfg, logged.append))
    import threading
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        r = httpx.post(f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions", json=body(), timeout=10).json()
        assert r["choices"][0]["message"]["content"] == "ESCALATE"
    finally:
        srv.shutdown()
        srv.server_close()
