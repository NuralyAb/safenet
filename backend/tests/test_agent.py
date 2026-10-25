from app.services import agent


def test_choose_mock_routes_by_intent():
    assert agent._choose_mock("проанализируй https://youtu.be/x")["tool"] == "analyze_url"
    assert agent._choose_mock("открой граф @scam")["tool"] == "open_view"
    assert agent._choose_mock("сводка по @vip")["tool"] == "account_summary"
    assert agent._choose_mock("топ материалов")["tool"] == "top_materials"
    assert agent._choose_mock("покажи статистику")["tool"] == "stats"
    assert agent._choose_mock("как считается риск?")["tool"] is None


def test_choose_mock_extracts_args():
    a = agent._choose_mock("открой граф @casino")
    assert a["args"]["view"] == "graph" and a["args"]["target"] == "@casino"
    u = agent._choose_mock("проверь https://vt.tiktok.com/abc")
    assert u["args"]["url"].startswith("https://")


def test_open_view_returns_navigate_action():
    out = agent._t_open_view(None, {"view": "graph", "target": "@x"})
    assert out["action"] == {"type": "navigate", "view": "graph", "target": "@x"}
    bad = agent._t_open_view(None, {"view": "nonsense"})
    assert bad["action"]["view"] == "dashboard"          # unknown view -> safe default


def test_run_general_question_falls_back_to_chat(monkeypatch):
    import app.services.runtime_config as rc
    monkeypatch.setattr(rc, "get_value", lambda k: "mock")
    out = agent.run(None, "как считается риск?")
    assert "риск" in out["reply"].lower()
    assert out.get("action") is None                     # no tool -> plain answer
