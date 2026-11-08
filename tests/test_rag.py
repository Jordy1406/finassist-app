import json

import httpx
import pytest

from app import llm, rag, retrieval
from app.config import get_settings

HITS = [
    retrieval.Hit("wiki_saham#003", "Saham", "Saham > Jenis > Saham preferen", "https://id.wikipedia.org/wiki/Saham",
                  "Saham preferen mendapat dividen lebih dulu.", 0.84),
    retrieval.Hit("wiki_saham#004", "Saham", "Saham > Jenis > Saham biasa", "https://id.wikipedia.org/wiki/Saham",
                  "Pemegang saham biasa punya hak suara.", 0.80),
    retrieval.Hit("wiki_dividen#000", "Dividen", "Dividen", "https://id.wikipedia.org/wiki/Dividen",
                  "Dividen adalah pembagian laba.", 0.62),
]


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def calls(monkeypatch):
    """Patch retrieval + model; returns a dict where tests set the model reply and read call counts."""
    state = {"hits": HITS, "reply": {}, "llm_calls": 0}
    monkeypatch.setattr(retrieval, "search", lambda q, s: state["hits"])

    def fake_chat_json(system, user, schema, s):
        state["llm_calls"] += 1
        state["last_user"] = user
        return state["reply"]

    monkeypatch.setattr(llm, "chat_json", fake_chat_json)
    return state


def test_answer_keeps_only_cited_sources(calls, settings):
    calls["reply"] = {"answer": "Saham preferen dapat dividen lebih dulu, saham biasa punya hak suara.",
                      "refused": False, "citations": [2, 1]}
    out = rag.answer("Apa beda saham biasa dan preferen?", settings)
    assert out.refused is False
    assert [s.id for s in out.sources] == ["wiki_saham#003", "wiki_saham#004"]   # sorted, no uncited dividen
    assert rag.DISCLAIMER not in out.answer


def test_low_retrieval_score_refuses_without_calling_model(calls, settings):
    calls["hits"] = [retrieval.Hit("x#0", "X", "X", "", "teks", settings.min_score - 0.01)]
    out = rag.answer("Bagaimana resep nasi goreng?", settings)
    assert out.refused is True and out.answer == rag.REFUSAL and out.sources == []
    assert calls["llm_calls"] == 0


def test_model_refusal_returns_fixed_text_and_no_sources(calls, settings):
    calls["reply"] = {"answer": "Nasi goreng dibuat dari nasi.", "refused": True, "citations": [1]}
    out = rag.answer("Bagaimana resep nasi goreng?", settings)
    assert out.refused is True and out.answer == rag.REFUSAL and out.sources == []


@pytest.mark.parametrize("citations", [[], [0], [9], ["1"]])
def test_answer_without_valid_citation_is_refused(calls, settings, citations):
    calls["reply"] = {"answer": "Jawaban tanpa sumber.", "refused": False, "citations": citations}
    assert rag.answer("Apa itu saham?", settings).refused is True


def test_empty_answer_is_refused(calls, settings):
    calls["reply"] = {"answer": "  ", "refused": False, "citations": [1]}
    assert rag.answer("Apa itu saham?", settings).refused is True


def test_recommendation_question_gets_disclaimer(calls, settings):
    calls["reply"] = {"answer": "Saham preferen mendapat dividen lebih dulu.", "refused": False, "citations": [1]}
    out = rag.answer("Sebaiknya saya beli saham preferen?", settings)
    assert out.answer.endswith(rag.DISCLAIMER)


def test_recommendation_refusal_also_gets_disclaimer(calls, settings):
    calls["reply"] = {"answer": "", "refused": True, "citations": []}
    out = rag.answer("Saham apa yang bagus dibeli sekarang?", settings)
    assert out.refused is True and rag.DISCLAIMER in out.answer


def test_disclaimer_not_duplicated(calls, settings):
    calls["reply"] = {"answer": "Ini bukan saran investasi.", "refused": False, "citations": [1]}
    out = rag.answer("Rekomendasi saham?", settings)
    assert out.answer.lower().count("bukan saran investasi") == 1


@pytest.mark.parametrize("question,expected", [
    ("Saham apa yang bagus dibeli sekarang?", True),
    ("Sebaiknya saya pilih reksa dana atau obligasi?", True),
    ("Apakah layak investasi di sukuk?", True),
    ("Apa itu saham?", False),
    ("Apa perbedaan saham biasa dan saham preferen?", False),
    ("Kapan Bursa Efek Jakarta didirikan?", False),
])
def test_is_recommendation(question, expected):
    assert rag.is_recommendation(question) is expected


def test_context_is_numbered_from_one_with_title_and_section(calls, settings):
    calls["reply"] = {"answer": "a", "refused": False, "citations": [1]}
    rag.answer("Apa itu saham?", settings)
    assert "[1] Saham — Saham > Jenis > Saham preferen" in calls["last_user"]
    assert "[3] Dividen — Dividen" in calls["last_user"]
    assert "PERTANYAAN: Apa itu saham?" in calls["last_user"]


def test_chat_json_rejects_non_json_reply(monkeypatch, settings):
    def fake_post(url, json=None, timeout=None):
        return httpx.Response(200, json={"message": {"content": "bukan json"}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(llm.LLMError, match="invalid JSON"):
        llm.chat_json("s", "u", rag.SCHEMA, settings)


def test_chat_json_sends_schema_and_temperature_zero(monkeypatch, settings):
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent.update(json)
        content = __import__("json").dumps({"answer": "a", "refused": False, "citations": [1]})
        return httpx.Response(200, json={"message": {"content": content}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    assert llm.chat_json("s", "u", rag.SCHEMA, settings)["answer"] == "a"
    assert sent["format"] == rag.SCHEMA and sent["options"]["temperature"] == 0


def test_search_ranks_by_cosine(monkeypatch, tmp_path, settings):
    index = {"chunks": [
        {"id": "a#0", "title": "A", "section": "A", "source": "", "text": "a", "embedding": [1.0, 0.0]},
        {"id": "b#0", "title": "B", "section": "B", "source": "", "text": "b", "embedding": [0.0, 1.0]},
        {"id": "c#0", "title": "C", "section": "C", "source": "", "text": "c", "embedding": [0.7, 0.7]},
    ]}
    path = tmp_path / "index.json"
    path.write_text(json.dumps(index), encoding="utf-8")
    monkeypatch.setattr(llm, "embed", lambda texts, s: [[0.0, 1.0]])
    from dataclasses import replace
    hits = retrieval.search("q", replace(settings, index_path=str(path), top_k=2))
    assert [h.id for h in hits] == ["b#0", "c#0"]
    assert hits[0].score == 1.0


def test_search_raises_when_index_missing(tmp_path, settings):
    from dataclasses import replace
    with pytest.raises(retrieval.IndexMissing):
        retrieval.search("q", replace(settings, index_path=str(tmp_path / "nope.json")))
