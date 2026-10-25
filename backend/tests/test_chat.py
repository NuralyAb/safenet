from fastapi.testclient import TestClient

from app.main import app
from app.services import chat


def test_mock_answer_is_grounded_and_offline(monkeypatch):
    import app.services.runtime_config as rc
    monkeypatch.setattr(rc, "get_value", lambda k: "mock")            # force offline, no LLM call
    assert "риск" in chat.answer(None, "как считается риск?").lower()
    assert "охват" in chat.answer(None, "что значит охват?").lower()
    assert chat.answer(None, "привет").strip()                       # greeting -> non-empty


def test_context_line_safe_without_db():
    assert isinstance(chat.context_line(None), str)                  # never raises


def test_chat_endpoint_requires_auth():
    assert TestClient(app).post("/api/v1/chat", json={"message": "привет"}).status_code == 401
