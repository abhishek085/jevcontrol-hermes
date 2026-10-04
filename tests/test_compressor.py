import pytest

pytest.importorskip("agent.context_engine", reason="needs a Hermes checkout on PYTHONPATH")


def build(n_old_tools=3, big=3000):
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "research X and write a table"}]
    for i in range(n_old_tools):
        msgs.append({"role": "assistant", "content": "", "tool_calls": [{"id": f"c{i}", "type": "function", "function": {"name": "web_search", "arguments": "{}"}}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": f"result {i} " + "x" * big})
    msgs.append({"role": "assistant", "content": "", "tool_calls": [{"id": "last", "type": "function", "function": {"name": "web_search", "arguments": "{}"}}]})
    msgs.append({"role": "tool", "tool_call_id": "last", "content": "latest " + "y" * big})
    return msgs


def engine(cfg, fake_jev, yes):
    from jev_control.compressor import JevCompressor
    logs = []
    e = JevCompressor(cfg, fake_jev(yes=yes), logs.append)
    e.threshold_tokens = 10_000  # room to spare: only outputs judged unneeded are dropped
    return e, logs


def test_unneeded_outputs_become_stubs_and_structure_is_unchanged(cfg, fake_jev):
    msgs = build()
    e, logs = engine(cfg, fake_jev, yes=[0.9, 0.05, 0.1])
    out = e.compress(msgs)
    assert [m["role"] for m in out] == [m["role"] for m in msgs]
    assert [m.get("tool_call_id") for m in out] == [m.get("tool_call_id") for m in msgs]
    assert out[3]["content"].startswith("result 0")                 # needed: kept
    assert out[5]["content"].startswith("[jev-compressor:")          # not needed: stub
    assert out[-1]["content"].startswith("latest")                   # protected tail untouched
    assert logs[-1]["event"] == "compress" and logs[-1]["dropped"] == 2


def test_nothing_to_compress_returns_messages_unchanged(cfg, fake_jev):
    msgs = build(n_old_tools=0)
    e, logs = engine(cfg, fake_jev, yes=[])
    assert e.compress(msgs) == msgs and logs[-1]["event"] == "compress_skip"


def test_decision_model_failure_still_returns_a_valid_list(cfg, fake_jev):
    class Boom:
        def yes_probs(self, *a):
            raise RuntimeError("down")
    from jev_control.compressor import JevCompressor
    logs = []
    e = JevCompressor(cfg, Boom(), logs.append)
    e.threshold_tokens = 100
    out = e.compress(build())
    assert len(out) == len(build()) and any(r["event"] == "compress_error" for r in logs)


def test_still_over_budget_drops_the_least_needed_even_if_wanted(cfg, fake_jev):
    e, logs = engine(cfg, fake_jev, yes=[0.9, 0.8, 0.7])
    e.threshold_tokens = 200  # tiny budget: wanted outputs must go too, least needed first
    out = e.compress(build())
    assert out[7]["content"].startswith("[jev-compressor:") and logs[-1]["dropped"] >= 2


def test_trigger_logic(cfg, fake_jev):
    e, _ = engine(cfg, fake_jev, yes=[])
    e.threshold_tokens = 100
    assert e.should_compress(150) and not e.should_compress(50)
