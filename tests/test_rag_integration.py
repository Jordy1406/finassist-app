"""P0-02 acceptance: three sample questions against the real index and a running Ollama.

Run with:  pytest -m integration
Skipped automatically when Ollama or data/index.json is not available.
"""

from pathlib import Path

import httpx
import pytest

from app import rag
from app.config import get_settings

settings = get_settings()


def _ollama_up() -> bool:
    try:
        return httpx.get(f"{settings.ollama_host}/api/version", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not Path(settings.index_path).exists(), reason="run python -m app.ingest first"),
    pytest.mark.skipif(not _ollama_up(), reason="Ollama is not running"),
]


def test_in_scope_question_is_answered_with_sources():
    out = rag.answer("Apa perbedaan saham biasa dan saham preferen?", settings)
    assert out.refused is False, out.answer
    assert out.sources, "answer must cite at least one source"
    assert any(s.title == "Saham" for s in out.sources)


def test_out_of_scope_question_is_refused():
    out = rag.answer("Bagaimana resep nasi goreng?", settings)
    assert out.refused is True
    assert out.sources == []


def test_recommendation_question_carries_disclaimer():
    out = rag.answer("Saham apa yang bagus dibeli sekarang?", settings)
    assert "bukan saran investasi" in out.answer.lower()
