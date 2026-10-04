import math
from jev_control.jev_client import Jev


def decide_reply(picks):
    return {"decisions": {k: {"selected": v[0], "probabilities": v[1]} for k, v in picks.items()}}


def test_decide_choice_and_yes_probs(serve, cfg):
    def handler(body):
        qs = {q["id"]: q for q in body["questions"]}
        if "q" in qs:
            return 200, decide_reply({"q": ("search", {"search": 0.9, "answer": 0.1})})
        return 200, decide_reply({k: ("true", {"true": 0.8 - i * 0.3, "false": 0.2 + i * 0.3}) for i, k in enumerate(qs)})
    cfg["spark_url"] = serve({"/decide": handler}) + ""
    jev = Jev(cfg)
    r = jev.choice("state", "q?", {"search": "s", "answer": "a"})
    assert r["pick"] == "search" and abs(r["p"] - 0.9) < 1e-9
    yes, ms = jev.yes_probs("state", ["one?", "two?"])
    assert [round(x, 2) for x in yes] == [0.8, 0.5]


def test_decide_retries_once_on_a_5xx(serve, cfg):
    calls = []

    def handler(body):
        calls.append(1)
        return (500, {"detail": "boom"}) if len(calls) == 1 else (200, decide_reply({"q": ("a", {"a": 1.0})}))
    cfg["spark_url"] = serve({"/decide": handler})
    assert Jev(cfg).choice("s", "q", {"a": "x", "b": "y"})["pick"] == "a" and len(calls) == 2


def test_chat_mode_reads_probabilities_from_logprobs(serve, cfg):
    seen = {}

    def handler(body):
        seen["body"] = body
        top = [{"token": "B", "logprob": math.log(0.7)}, {"token": "A", "logprob": math.log(0.2)}, {"token": "the", "logprob": -5}]
        return 200, {"choices": [{"logprobs": {"content": [{"top_logprobs": top}]}}]}
    cfg["spark_url"] = serve({"/chat/completions": handler})
    cfg["spark_api"] = "chat"
    r = Jev(cfg).choice("the state", "which?", {"first": "", "second": ""})
    assert r["pick"] == "second" and abs(r["p"] - 0.7 / 0.9) < 1e-6
    b = seen["body"]
    assert b["max_tokens"] == 1 and b["logprobs"] is True and "A. first" in b["messages"][1]["content"]
    assert "the state" in b["messages"][1]["content"]


def test_chat_mode_yes_probs_runs_one_question_each(serve, cfg):
    n = []

    def handler(body):
        n.append(1)
        top = [{"token": "A", "logprob": math.log(0.9)}, {"token": "B", "logprob": math.log(0.1)}]
        return 200, {"choices": [{"logprobs": {"content": [{"top_logprobs": top}]}}]}
    cfg["spark_url"] = serve({"/chat/completions": handler})
    cfg["spark_api"] = "chat"
    yes, _ = Jev(cfg).yes_probs("s", ["a?", "b?", "c?"])
    assert len(n) == 3 and all(abs(x - 0.9) < 1e-6 for x in yes)
