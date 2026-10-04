import json
from jev_control import search_pick


def result(n):
    return json.dumps({"success": True, "data": {"web": [{"url": f"https://e.com/{i}", "title": f"t{i}", "description": "d" * 50} for i in range(n)]}})


def pick(res, yes, cfg, fake_jev):
    new, rec = search_pick.pick(res, "q", "user request", fake_jev(yes=yes), cfg)
    return (json.loads(new) if new else None), rec


def test_drops_only_clearly_unrelated_results_and_keeps_order(cfg, fake_jev):
    out, rec = pick(result(5), [0.9, 0.05, 0.8, 0.01, 0.6], cfg, fake_jev)
    assert [r["url"] for r in out["data"]["web"]] == ["https://e.com/0", "https://e.com/2", "https://e.com/4"]
    assert rec["n"] == 5 and rec["kept"] == 3 and "removed 2 of 5" in out["jev_note"]


def test_everything_relevant_leaves_the_result_untouched(cfg, fake_jev):
    new, rec = search_pick.pick(result(4), "q", "r", fake_jev(yes=[0.9, 0.8, 0.95, 0.5]), cfg)
    assert new is None and rec["kept"] == 4


def test_never_leaves_fewer_than_min_keep(cfg, fake_jev):
    out, _ = pick(result(5), [0.01, 0.02, 0.03, 0.001, 0.0], cfg, fake_jev)
    assert len(out["data"]["web"]) == cfg("search_min_keep")


def test_max_keep_caps_the_list(cfg, fake_jev):
    cfg["search_max_keep"] = 3
    out, _ = pick(result(6), [0.9] * 6, cfg, fake_jev)
    assert len(out["data"]["web"]) == 3


def test_malformed_or_tiny_results_pass_through(cfg, fake_jev):
    assert search_pick.pick("not json", "q", "r", fake_jev(), cfg)[0] is None
    assert search_pick.pick(result(2), "q", "r", fake_jev(), cfg)[0] is None
    assert search_pick.pick(json.dumps({"error": "x"}), "q", "r", fake_jev(), cfg)[0] is None
