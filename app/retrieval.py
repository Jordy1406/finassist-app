"""Top-k cosine retrieval over the local index written by `python -m app.ingest`."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app import llm
from app.config import Settings


class IndexMissing(RuntimeError):
    """Raised when data/index.json has not been built yet."""


@dataclass(frozen=True)
class Hit:
    id: str
    title: str
    section: str
    source: str
    text: str
    score: float


@lru_cache(maxsize=2)
def _load(path: str, mtime: float) -> tuple[list[dict], list[float]]:
    chunks = json.loads(Path(path).read_text(encoding="utf-8"))["chunks"]
    norms = [math.sqrt(sum(x * x for x in c["embedding"])) or 1.0 for c in chunks]
    return chunks, norms


def load_index(settings: Settings) -> tuple[list[dict], list[float]]:
    path = Path(settings.index_path)
    if not path.exists():
        raise IndexMissing(f"Index {path} not found. Run: python -m app.ingest")
    return _load(str(path), path.stat().st_mtime)


def search(query: str, settings: Settings) -> list[Hit]:
    chunks, norms = load_index(settings)
    q = llm.embed([query], settings)[0]
    qn = math.sqrt(sum(x * x for x in q)) or 1.0
    scored = sorted(
        ((sum(a * b for a, b in zip(q, c["embedding"])) / (qn * n), c) for c, n in zip(chunks, norms)),
        key=lambda t: t[0], reverse=True,
    )[: settings.top_k]
    return [Hit(c["id"], c["title"], c["section"], c["source"], c["text"], round(s, 4)) for s, c in scored]
