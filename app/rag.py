"""Retrieval-augmented answers: Bahasa Indonesia, only from retrieved context, with citations.

Rules enforced in code (not only in the prompt), so they hold even when the model drifts:
- best retrieval score below MIN_SCORE  -> refuse without calling the model,
- model says refused, or cites nothing valid -> fixed refusal text, no sources,
- recommendation-style question        -> "bukan saran investasi" disclaimer appended.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app import llm, retrieval
from app.config import Settings

REFUSAL = "Maaf, saya tidak menemukan jawabannya di dokumen yang saya miliki."
DISCLAIMER = "Catatan: informasi ini bersifat edukasi, bukan saran investasi."

RECOMMENDATION = re.compile(
    r"\b(sebaiknya|rekomendasi(?:kan)?|sarankan|saran|layak|cocok|bagus|menguntungkan|untung"
    r"|pilih|beli|jual|investasi(?:kan)?\s+(?:di|ke)|harus\s+(?:beli|jual|investasi))\b",
    re.I,
)

SYSTEM_PROMPT = """Kamu adalah FinAssist ID, asisten edukasi pasar modal Indonesia.
Aturan:
1. Jawab dalam Bahasa Indonesia, HANYA berdasarkan KONTEKS yang diberikan. Jangan memakai pengetahuan lain.
2. Jika jawabannya tidak ada di KONTEKS, isi "refused": true dan "answer": "".
3. Jika menjawab, isi "citations" dengan nomor sumber KONTEKS yang kamu pakai, misalnya [1, 3].
4. Jangan memberi rekomendasi membeli atau menjual efek tertentu.
5. Jawab ringkas, maksimal 5 kalimat.
Balas hanya dengan JSON sesuai skema."""

SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "refused": {"type": "boolean"},
        "citations": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["answer", "refused", "citations"],
}


@dataclass
class Source:
    id: str
    title: str
    section: str
    url: str
    score: float


@dataclass
class RagAnswer:
    answer: str
    refused: bool
    sources: list[Source] = field(default_factory=list)


def is_recommendation(question: str) -> bool:
    return RECOMMENDATION.search(question) is not None


def build_context(hits: list[retrieval.Hit]) -> str:
    return "\n\n".join(f"[{i}] {h.title} — {h.section}\n{h.text}" for i, h in enumerate(hits, start=1))


def _with_disclaimer(text: str, question: str) -> str:
    if is_recommendation(question) and "bukan saran investasi" not in text.lower():
        return f"{text}\n\n{DISCLAIMER}"
    return text


def _refusal(question: str) -> RagAnswer:
    return RagAnswer(answer=_with_disclaimer(REFUSAL, question), refused=True, sources=[])


def answer(question: str, settings: Settings) -> RagAnswer:
    hits = retrieval.search(question, settings)
    if not hits or hits[0].score < settings.min_score:
        return _refusal(question)

    user = f"KONTEKS:\n{build_context(hits)}\n\nPERTANYAAN: {question}"
    out = llm.chat_json(SYSTEM_PROMPT, user, SCHEMA, settings)

    cited = sorted({c for c in out.get("citations", []) if isinstance(c, int) and 1 <= c <= len(hits)})
    text = str(out.get("answer", "")).strip()
    if out.get("refused") is True or not text or not cited:
        return _refusal(question)

    sources = [Source(h.id, h.title, h.section, h.source, h.score) for h in (hits[i - 1] for i in cited)]
    return RagAnswer(answer=_with_disclaimer(text, question), refused=False, sources=sources)
