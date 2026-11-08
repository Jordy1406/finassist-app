# FinAssist ID

Target system for an AI Quality Engineering portfolio: a Bahasa Indonesia assistant over **public** capital-market
education documents (RAG), plus an agent that trades against a **mock** broker with fictional data.
Later projects (P1–P4) test, evaluate and red-team this system.

> Status: P0, week 1. Endpoints: `GET /health`, `POST /chat` (proxied to a local Ollama model).
> Document ingest + local vector index is in place; retrieval in `/chat` comes next (P0-02).

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Install [Ollama](https://ollama.com) and pull the chat and embedding models:

```bash
ollama pull llama3.2:3b
ollama pull nomic-embed-text
```

## Build the document index

```bash
python -m app.ingest            # chunk docs/*.md, embed with nomic-embed-text, write data/index.json
python -m app.ingest --dry-run  # chunk only and print counts per document
```

Current corpus (10 public documents, see [docs/SOURCES.md](docs/SOURCES.md)): **382 chunks**, 768-dim embeddings,
about 70 s to embed on a laptop GPU. `data/` is git-ignored; rebuild it after changing `docs/` or chunk settings.

### Chunking

Structure-aware rather than fixed-size, so every chunk can be cited precisely:

| Document type | Split on | Max words | Section label example |
|---|---|---|---|
| Wikipedia articles | Markdown headings (path kept) | `CHUNK_MAX_WORDS` = 300 | `Saham > Jenis > Saham preferen` |
| Statute (UU 8/1995) | Each Pasal; Penjelasan labelled separately | `CHUNK_MAX_WORDS_LAW` = 400 | `BAB IV Reksa Dana > Pasal 23` |

Sections over the limit are cut into windows sharing `CHUNK_OVERLAP_WORDS` = 50 words.
Cleaning drops link-only Wikipedia sections ("Lihat juga", "Pranala luar"), Penjelasan entries that only say
"Cukup jelas", BAB/Bagian/Paragraf sub-headings, and PDF page artefacts. A heading glued to its first sentence
("Pasal 35 Perusahaan Efek dilarang…") is only split when it is the next Pasal number, so cross-references like
"Pasal 93, Pasal 95 … diancam pidana" stay intact. All 116 Pasal of the statute are covered.

Each chunk stores `id`, `doc_id`, `title`, `source` URL, `license`, `section`, `position`, `text`, `n_words` and its embedding.

**Why not Chroma?** ~400 chunks fit in a JSON file and a brute-force cosine search; no extra dependency needed yet.

### Known retrieval weaknesses (left in on purpose for P1–P2)

- Definition lookups miss Pasal 1: "Apa yang dimaksud dengan afiliasi?" ranks Penjelasan Pasal 23/31 above
  Pasal 1, because the long list of definitions is split across windows and each window mixes many terms.
- The statute is ~50% of all words, so legal text can crowd out the encyclopedia articles for broad questions.
- The statute is the original 1995 text; parts were amended by UU 4/2023 (P2SK).

## Run

```bash
uvicorn app.main:app --reload
# open http://localhost:8000/docs
curl -X POST localhost:8000/chat -H "Content-Type: application/json" -d '{"message":"Apa itu saham?"}'
```

## Test

```bash
pytest
```

23 tests. Unit tests mock the LLM and the chunking tests use small fixtures, so they pass without Ollama running.

## Roadmap

- [x] Skeleton: `/health`, `/chat` via Ollama
- [x] Ingest + structure-aware chunking + local vector index (P0-01)
- [ ] RAG answers with citations and refusal (P0-02)
- [ ] Mock broker + agent tools (P0-03, P0-04)
- [ ] Docker Compose (P0-05)
- [ ] Known risks backlog (P0-06)

Next steps:
1. P0-02: top-k retrieval over `data/index.json` in `/chat`, answer only from context, JSON `{answer, sources[], refused}`.
2. Add the disclaimer "bukan saran investasi" for recommendation questions.
3. Grow the corpus from 10 to 30 public documents.
