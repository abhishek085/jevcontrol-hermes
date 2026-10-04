import pytest
from jev_control import memory_gate


def add(text, **kw):
    return {"action": "add", "target": "user", "content": text, **kw}


def test_durable_fact_is_allowed(cfg, fake_jev):
    v = memory_gate.check(add("User prefers concise answers."), fake_jev("durable_fact"), cfg)
    assert v["verdict"] == "allow"


@pytest.mark.parametrize("pick,word", [("procedure", "skill"), ("transient", "current task"), ("directive", "declarative")])
def test_misfiled_writes_are_blocked_with_advice(cfg, fake_jev, pick, word):
    v = memory_gate.check(add("something"), fake_jev(pick), cfg)
    assert v["verdict"] == "block" and word in v["message"]


def test_low_confidence_does_not_block(cfg, fake_jev):
    assert memory_gate.check(add("something"), fake_jev("procedure", p=0.4), cfg)["verdict"] == "allow"


def test_secrets_are_refused_without_the_model(cfg, fake_jev):
    jev = fake_jev("durable_fact")
    v = memory_gate.check(add("password=Hunter2Hunter2"), jev, cfg)
    assert v["verdict"] == "block" and v["layer"] == "rule" and not jev.calls


def test_removals_and_reads_pass_without_the_model(cfg, fake_jev):
    jev = fake_jev("procedure")
    assert memory_gate.check({"action": "remove", "target": "user", "old_text": "x"}, jev, cfg)["verdict"] == "allow"
    assert not jev.calls


def test_batch_blocks_if_any_write_is_misfiled(cfg, fake_jev):
    args = {"action": "batch", "target": "memory", "operations": [{"action": "add", "content": "a"}, {"action": "add", "content": "b"}]}
    assert memory_gate.check(args, fake_jev("transient"), cfg)["verdict"] == "block"
