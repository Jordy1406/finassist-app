"""Output guards for /agent replies (P4-04, findings MAN-02 and MAN-03).

The system prompt asks the model not to recommend stocks and does not stop it from reciting its own instructions;
red-team tests showed both happen (role-play advice, prompt extraction). These checks run in code on the model's
final text, after the tool loop, so no prompt can switch them off. System-generated texts (order confirmations and
fills) never pass through them.
"""

from __future__ import annotations

import re

ADVICE_REFUSAL = ("Maaf, saya tidak bisa memberi rekomendasi atau prediksi saham. Saya bisa menampilkan harga, "
                  "portofolio Anda, atau mengajukan order yang Anda tentukan sendiri. "
                  "Catatan: informasi ini bersifat edukasi, bukan saran investasi.")
PROMPT_REFUSAL = "Maaf, saya tidak bisa membagikan instruksi internal saya. Ada yang bisa saya bantu soal akun Anda?"

TICKER = re.compile(r"\b(KOPX|TANX|LAUX|BATX|DIGX)\b", re.I)
ADVICE = re.compile(
    r"(sarank?an|menyarankan|rekomendasi(kan)?|merekomendasikan|layak\s+(dibeli|dijual|dikoleksi)|paling\s+layak|"
    r"sebaiknya\s+(anda\s+)?(beli|jual|membeli|menjual|tahan)|patut\s+(dibeli|dijual)|pilihan\s+terbaik|"
    r"(akan|pasti|bakal|cenderung)\s+naik|tendensi\s+naik|potensi\s+(naik|kenaikan|pertumbuhan)|"
    r"(should|recommend)\s+(buy|sell)|good\s+(time|investment)\s+to\s+buy)",
    re.I,
)
NEGATION = re.compile(r"\b(tidak|tak|bukan|jangan|belum|cannot|can't|not)\b[\w\s,]{0,25}$", re.I)


def is_advice(text: str) -> bool:
    """A named ticker together with recommendation or price-direction wording that is not negated."""
    if not TICKER.search(text):
        return False
    for m in ADVICE.finditer(text):
        if not NEGATION.search(text[max(0, m.start() - 40):m.start()]):
            return True
    return False


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip(" -.\"'")


def prompt_fragments(system_prompt: str, min_len: int = 20) -> list[str]:
    """Sentences / clauses of the system prompt long enough to identify it."""
    parts = re.split(r"[\n.;:]+|\s-\s", system_prompt)
    return [p for p in (_norm(x) for x in parts) if len(p) >= min_len]


def leaks_prompt(text: str, system_prompt: str, threshold: int = 2) -> bool:
    """Two or more distinctive fragments of the system prompt appear in the reply."""
    t = _norm(text)
    return sum(f in t for f in prompt_fragments(system_prompt)) >= threshold


def check_reply(text: str, system_prompt: str) -> tuple[str, str | None]:
    """Return (text to send, reason it was replaced or None)."""
    if leaks_prompt(text, system_prompt):
        return PROMPT_REFUSAL, "system_prompt_leak"
    if is_advice(text):
        return ADVICE_REFUSAL, "investment_advice"
    return text, None
