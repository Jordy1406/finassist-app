from fastapi.testclient import TestClient

from app import llm
from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_chat_returns_model_answer(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda message, settings: f"echo: {message}")
    resp = client.post("/chat", json={"message": "Apa itu saham?"})
    assert resp.status_code == 200
    assert resp.json()["answer"] == "echo: Apa itu saham?"


def test_chat_returns_503_when_backend_down(monkeypatch):
    def boom(message, settings):
        raise llm.LLMError("down")

    monkeypatch.setattr(llm, "chat", boom)
    resp = client.post("/chat", json={"message": "halo"})
    assert resp.status_code == 503


def test_chat_rejects_empty_message():
    resp = client.post("/chat", json={"message": ""})
    assert resp.status_code == 422
