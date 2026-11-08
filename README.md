# FinAssist ID

Target system for an AI Quality Engineering portfolio: a Bahasa Indonesia assistant over **public** capital-market
education documents (RAG), plus an agent that trades against a **mock** broker with fictional data.
Later projects (P1–P4) test, evaluate and red-team this system.

> Status: P0, week 1. `POST /chat` answers in Bahasa Indonesia from retrieved public documents, with citations,
> refusals and an investment disclaimer. Mock broker + agent come next (P0-03, P0-04).

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
- Retrieval scores cannot separate in-scope from out-of-scope questions: "Bagaimana resep nasi goreng?" scores 0.650
  and "Berapa harga emas hari ini?" 0.698, above "Apa itu saham?" (0.626) and "Apa itu sukuk?" (0.625).
  Refusal therefore depends on the model reading the context; `MIN_SCORE` is only a floor.
- Hallucinated answer with a valid-looking citation: "Apa itu sukuk?" (see table above).
- The recommendation regex over-triggers on educational questions that contain "beli"/"jual"
  (e.g. "Apa itu jual kosong?"); the extra disclaimer is harmless but measurable.

## Run

```bash
python -m app.ingest            # once, builds data/index.json
uvicorn app.main:app --reload   # open http://localhost:8000/docs
curl -X POST localhost:8000/chat -H "Content-Type: application/json" -d '{"message":"Apa itu saham?"}'
```

## `/chat` (RAG)

Request `{"message": "..."}` → response:

```json
{
  "answer": "Saham preferen memiliki prioritas lebih tinggi dalam pembagian dividen ...",
  "refused": false,
  "sources": [{"id": "wiki_saham#003", "title": "Saham", "section": "Saham > Jenis > Saham preferen",
               "url": "https://id.wikipedia.org/wiki/Saham", "score": 0.7809}]
}
```

Pipeline: embed the question → cosine top-k (`TOP_K`=4) over `data/index.json` → `llama3.2:3b` at temperature 0 with a
JSON schema (`answer`, `refused`, `citations`) → rules applied in code:

| Rule | Enforced by |
|---|---|
| Answer only from context, in Bahasa Indonesia | system prompt |
| Best retrieval score < `MIN_SCORE` (0.5) → refuse without calling the model | code |
| Model sets `refused`, gives an empty answer or cites no valid context number → fixed refusal text, no sources | code |
| `sources` = only the chunks the model cited | code |
| Recommendation-style question (sebaiknya, beli, layak, rekomendasi, …) → append "bukan saran investasi" | code (regex), also on refusals |
| Backend down / non-JSON reply / index missing → HTTP 503 with the reason | code |

Sample run (2026-11-08, `llama3.2:3b`, temperature 0):

| Question | refused | Result |
|---|---|---|
| Apa perbedaan saham biasa dan saham preferen? | false | Correct; cites *Saham > Jenis > Saham preferen* |
| Berapa harga emas hari ini? | true | Fixed refusal text |
| Sebaiknya saya beli reksa dana atau obligasi? | false | Neutral comparison + disclaimer, 3 sources |
| Apa yang dimaksud dengan afiliasi? | false | Narrow answer from Penjelasan Pasal 31, misses the Pasal 1 definition |
| Apa itu sukuk? | false | **Wrong**: describes a warrant and cites UU Pasal 61; the Sukuk article is not retrieved |

## Test

```bash
pytest
```

46 unit tests run offline (the LLM, embeddings and index are faked). The three P0-02 acceptance questions run
against a real Ollama and index:

```bash
pytest -m integration   # in-scope answer with sources, out-of-scope refusal, recommendation disclaimer
```

## Roadmap

- [x] Skeleton: `/health`, `/chat` via Ollama
- [x] Ingest + structure-aware chunking + local vector index (P0-01)
- [x] RAG answers with citations, refusal and disclaimer (P0-02)
- [ ] Mock broker + agent tools (P0-03, P0-04)
- [ ] Docker Compose (P0-05)
- [ ] Known risks backlog (P0-06)

Next steps:
1. P0-03: in-memory mock broker (fictional tickers, lot size 100, market hours, order limits) with unit tests.
2. P0-04: `/agent` with `get_quote`, `get_portfolio`, `place_order` and explicit confirmation before orders.
3. Grow the corpus from 10 to 30 public documents.
