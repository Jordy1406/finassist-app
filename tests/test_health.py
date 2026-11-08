from fastapi.testclient import TestClient

from app import llm, rag, retrieval
from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_chat_returns_answer_sources_and_refused_flag(monkeypatch):
    fake = rag.RagAnswer(
        answer="Saham adalah tanda penyertaan modal.",
        refused=False,
        sources=[rag.Source("wiki_saham#000", "Saham", "Saham", "https://id.wikipedia.org/wiki/Saham", 0.71)],
    )
    monkeypatch.setattr(rag, "answer", lambda message, settings: fake)
    resp = client.post("/chat", json={"message": "Apa itu saham?"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"answer", "sources", "refused"}
    assert body["refused"] is False
    assert body["sources"][0] == {
        "id": "wiki_saham#000", "title": "Saham", "section": "Saham",
        "url": "https://id.wikipedia.org/wiki/Saham", "score": 0.71,
    }


def test_chat_returns_503_when_backend_down(monkeypatch):
    def boom(message, settings):
        raise llm.LLMError("down")

    monkeypatch.setattr(rag, "answer", boom)
    assert client.post("/chat", json={"message": "halo"}).status_code == 503


def test_chat_returns_503_with_hint_when_index_missing(monkeypatch):
    def missing(message, settings):
        raise retrieval.IndexMissing("Index data/index.json not found. Run: python -m app.ingest")

    monkeypatch.setattr(rag, "answer", missing)
    resp = client.post("/chat", json={"message": "halo"})
    assert resp.status_code == 503
    assert "app.ingest" in resp.json()["detail"]


def test_chat_rejects_empty_message():
    assert client.post("/chat", json={"message": ""}).status_code == 422
