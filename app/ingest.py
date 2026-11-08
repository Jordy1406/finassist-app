"""Ingest public documents in docs/ into a local vector index.

Chunking is structure-aware:
- Wikipedia articles split on markdown headings (section path kept as metadata),
- statutes (front matter `title` starting with "Undang-Undang") split per Pasal, with the
  Penjelasan part labelled separately,
- any section longer than the word limit is cut into overlapping word windows.

Run:  python -m app.ingest            (chunk + embed via Ollama, write INDEX_PATH)
      python -m app.ingest --dry-run  (chunk only, print counts)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.config import Settings, get_settings

FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
PASAL = re.compile(r"^Pasal\s+(\d+[A-Z]?)\s*$")
BAB = re.compile(r"^BAB\s+([IVXLC]+)\s*$")
# In the Penjelasan, the PDF extraction sometimes leaves "Pasal N" mid-line ("... Cukup jelas Pasal 104 Cukup jelas").
INLINE_PASAL = re.compile(r"\s(Pasal\s+\d+[A-Z]?)(?:\.{3})?(?=\s+(?:Cukup jelas|Ayat\s*\(|Yang dimaksud|Huruf\s)|\s*$)")
# Sub-headings inside a BAB ("Bagian Kesatu Bursa Efek", "Paragraf 1 Perizinan") are structure, not pasal text.
SUBHEADING = re.compile(r"^(?:Bagian\s+(?:Ke\w+|Pertama)\b|Paragraf\s+\d+\b)")
# A heading glued to its first sentence ("Pasal 35 Perusahaan Efek dilarang:"); only trusted when it is
# the next number in sequence, so a reference such as "Pasal 93, Pasal 95 ... diancam" is not split.
GLUED_PASAL = re.compile(r"^Pasal\s+(\d+)\s+(\S.*)$")
END_MATTER = re.compile(r"\s*TAMBAHAN LEMBARAN NEGARA.*$", re.S)
EMPTY_PHRASES = re.compile(r"(?:(?:Ayat|Huruf|Angka)\s*\(?\w{1,3}\)?|Cukup jelas\.?|\s)+", re.I)
# Sections that are only link lists on Wikipedia.
SKIP_SECTIONS = {"lihat juga", "pranala", "pranala luar", "referensi", "catatan", "daftar pustaka", "bacaan lanjutan"}


@dataclass
class Chunk:
    id: str
    doc_id: str
    title: str
    source: str
    license: str
    section: str
    position: int
    text: str
    n_words: int = 0
    embedding: list[float] = field(default_factory=list)


def parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    """Split `---` front matter (simple `key: value` lines) from the body."""
    m = FRONT_MATTER.match(raw.replace("\r\n", "\n"))
    if not m:
        return {}, raw
    meta = {}
    for line in m.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    return meta, raw.replace("\r\n", "\n")[m.end():]


def clean(text: str) -> str:
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def split_markdown_sections(body: str) -> list[tuple[str, str]]:
    """Return (section path, text) pairs; the path joins nested headings with ' > '."""
    sections, path, buf = [], [], []

    def flush():
        text = clean("\n".join(buf))
        if text:
            sections.append((" > ".join(h for _, h in path) or "Pembuka", text))
        buf.clear()

    for line in body.splitlines():
        m = HEADING.match(line)
        if m:
            flush()
            level = len(m.group(1))
            path[:] = [p for p in path if p[0] < level] + [(level, m.group(2))]
        else:
            buf.append(line)
    flush()
    return [(s, t) for s, t in sections if s.split(" > ")[-1].strip().lower() not in SKIP_SECTIONS]


def is_empty_penjelasan(text: str) -> bool:
    """True when the text is only "Cukup jelas" markers, e.g. "Ayat (1) Cukup jelas Huruf a Cukup jelas"."""
    return "cukup jelas" in text.lower() and EMPTY_PHRASES.fullmatch(text) is not None


def split_pasal_sections(body: str) -> list[tuple[str, str]]:
    """Split a statute into Pembukaan, each Pasal, Penjelasan Umum and Penjelasan Pasal N."""
    sections, buf = [], []
    label, bab, in_penjelasan, in_bab_title = "Pembukaan", "", False, False
    last_pasal, skip_title = 0, False

    def flush():
        text = END_MATTER.sub("", re.sub(r"\s*\.\.\.$", "", clean("\n".join(buf))))  # page marker, LN footer
        if text and not (label.startswith("Penjelasan Pasal") and is_empty_penjelasan(text)):
            sections.append((label, text))
        buf.clear()

    def expand(lines):
        # Only the Penjelasan has "Pasal N" glued mid-line; in the body, "dalam Pasal 3" is a reference.
        seen_penjelasan = False
        for line in lines:
            seen_penjelasan = seen_penjelasan or line.strip() == "PENJELASAN"
            if seen_penjelasan and "Pasal" in line:
                yield from INLINE_PASAL.sub(r"\n\1\n", f" {line}").strip().split("\n")
            else:
                yield line

    for line in expand(body.splitlines()):
        s = line.strip()
        if s == "PENJELASAN" and not in_penjelasan:
            flush()
            in_penjelasan, label, bab, in_bab_title = True, "Penjelasan Umum", "", False
            continue
        if (b := BAB.match(s)) and not in_penjelasan:
            flush()
            bab, in_bab_title = f"BAB {b.group(1)}", True
            continue
        if in_bab_title and s and s.isupper():
            bab = f"{bab} {s.title()}"
            continue
        if SUBHEADING.match(s):
            # "Bagian Kesatu" alone on a line is followed by its title on the next line
            skip_title = bool(re.fullmatch(r"Bagian\s+\w+|Paragraf\s+\d+", s))
            continue
        if skip_title and s:
            skip_title = False
            if not PASAL.match(s) and not GLUED_PASAL.match(s):
                continue
        glued = None if in_penjelasan else GLUED_PASAL.match(s)
        if glued and int(glued.group(1)) != last_pasal + 1:
            glued = None
        if (p := PASAL.match(s)) or glued:
            flush()
            in_bab_title = False
            num = (p or glued).group(1)
            if not in_penjelasan and num.isdigit():
                last_pasal = int(num)
            label = f"Penjelasan Pasal {num}" if in_penjelasan else f"Pasal {num}"
            if bab and not in_penjelasan:
                label = f"{bab} > {label}"
            if glued:
                buf.append(glued.group(2))
            continue
        if s:
            in_bab_title = False
        buf.append(line)
    flush()
    return sections


def window(words: list[str], max_words: int, overlap: int) -> list[list[str]]:
    """Cut a word list into windows of at most `max_words`, consecutive windows sharing `overlap` words."""
    if max_words <= 0:
        raise ValueError("max_words must be positive")
    if not 0 <= overlap < max_words:
        raise ValueError("overlap must be >= 0 and smaller than max_words")
    if len(words) <= max_words:
        return [words] if words else []
    step = max_words - overlap
    out = []
    for start in range(0, len(words), step):
        out.append(words[start:start + max_words])
        if start + max_words >= len(words):
            break
    return out


def is_statute(meta: dict[str, str]) -> bool:
    return meta.get("title", "").lower().startswith("undang-undang")


def chunk_document(path: Path, settings: Settings) -> list[Chunk]:
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
    statute = is_statute(meta)
    sections = split_pasal_sections(body) if statute else split_markdown_sections(body)
    limit = settings.chunk_max_words_law if statute else settings.chunk_max_words
    chunks: list[Chunk] = []
    for section, text in sections:
        for part in window(text.split(), limit, settings.chunk_overlap_words):
            pos = len(chunks)
            chunks.append(Chunk(
                id=f"{path.stem}#{pos:03d}", doc_id=path.stem, title=meta.get("title", path.stem),
                source=meta.get("source", ""), license=meta.get("license", ""), section=section,
                position=pos, text=" ".join(part), n_words=len(part),
            ))
    return chunks


def embed(texts: list[str], settings: Settings, batch: int = 32) -> list[list[float]]:
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch):
        resp = httpx.post(
            f"{settings.ollama_host}/api/embed",
            json={"model": settings.embed_model, "input": texts[i:i + batch]},
            timeout=settings.request_timeout_s,
        )
        resp.raise_for_status()
        vectors.extend(resp.json()["embeddings"])
    return vectors


def source_documents(docs_dir: str) -> list[Path]:
    """Corpus files only: markdown with a `source:` in its front matter.

    Project notes kept in docs/ (SOURCES.md, KNOWN_RISKS.md, ...) have no front matter and must never reach the index.
    """
    out = []
    for p in sorted(Path(docs_dir).glob("*.md")):
        meta, _ = parse_front_matter(p.read_text(encoding="utf-8"))
        if meta.get("source"):
            out.append(p)
    return out


def build_index(settings: Settings, dry_run: bool = False) -> list[Chunk]:
    docs = source_documents(settings.docs_dir)
    chunks: list[Chunk] = []
    for path in docs:
        doc_chunks = chunk_document(path, settings)
        words = sum(c.n_words for c in doc_chunks)
        print(f"{path.name:40} {len(doc_chunks):4} chunks {words:7} words")
        chunks.extend(doc_chunks)
    print(f"{'TOTAL':40} {len(chunks):4} chunks from {len(docs)} documents")
    if dry_run:
        return chunks
    vectors = embed([c.text for c in chunks], settings)
    for c, v in zip(chunks, vectors):
        c.embedding = v
    out = Path(settings.index_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "embed_model": settings.embed_model,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "chunking": {"max_words": settings.chunk_max_words, "max_words_law": settings.chunk_max_words_law,
                     "overlap_words": settings.chunk_overlap_words},
        "chunks": [asdict(c) for c in chunks],
    }, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out} ({len(chunks)} chunks, dim {len(vectors[0]) if vectors else 0})")
    return chunks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chunk docs/ and build the local vector index.")
    parser.add_argument("--dry-run", action="store_true", help="chunk only; skip embedding and writing the index")
    args = parser.parse_args(argv)
    try:
        build_index(get_settings(), dry_run=args.dry_run)
    except httpx.HTTPError as exc:
        print(f"Embedding failed (is Ollama running with the embed model pulled?): {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
