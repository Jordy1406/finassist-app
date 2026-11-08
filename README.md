# FinAssist ID

Target system for an AI Quality Engineering portfolio: a Bahasa Indonesia assistant over **public** capital-market
education documents (RAG), plus an agent that trades against a **mock** broker with fictional data.
Later projects (P1–P4) test, evaluate and red-team this system.

> Status: P0, week 1. `POST /chat` answers in Bahasa Indonesia from retrieved public documents, with citations,
> refusals and an investment disclaimer. `POST /agent` is a tool-using agent over an in-memory mock broker that
> never places an order without the user's explicit confirmation.

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
- Agent: the model invents order arguments instead of reading the portfolio first ("jual semua KOPX" → 1000 shares);
  only the broker rules stop it.
- Agent: recommendation-style questions are not refused and get no disclaimer on `/agent`; the model picks a
  ticker on its own ("Saham apa yang sebaiknya saya beli?" → quotes KOPX).
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

## Mock broker (`app/broker.py`)

In-memory and fully fictional; it is the system the agent (P0-04) will act on and P3 will assert against.

| Ticker | Company (fictional) | Price (Rp) | Tick |
|---|---|---:|---:|
| KOPX | PT Kopi Nusantara Fiktif Tbk | 1,250 | 5 |
| TANX | PT Tani Makmur Fiktif Tbk | 386 | 2 |
| LAUX | PT Laut Biru Fiktif Tbk | 4,520 | 10 |
| BATX | PT Batu Bara Fiktif Tbk | 7,850 | 25 |
| DIGX | PT Digital Kita Fiktif Tbk | 142 | 1 |

Starting account: Rp 100,000,000 cash and 500 KOPX at an average of Rp 1,200. Tools: `get_quote(ticker)`,
`get_portfolio()`, `place_order(ticker, side, quantity, price=None)`, plus `order_history()` and `reset()`.

`place_order` checks, in this order, and raises `BrokerError` with a stable `code` and an Indonesian message:

| Code | Rule |
|---|---|
| `UNKNOWN_TICKER` | ticker not in the list above |
| `INVALID_SIDE` | side is not `buy` / `sell` |
| `INVALID_QUANTITY` | quantity is not a positive integer |
| `LOT_SIZE` | quantity is not a multiple of 100 shares |
| `INVALID_PRICE` | price is not a positive integer |
| `TICK_SIZE` | price off the tick for its band (<200: 1, <500: 2, <2,000: 5, <5,000: 10, else 25) |
| `MARKET_CLOSED` | outside Mon–Fri 09:00–15:50 WIB (configurable; end is exclusive) |
| `ORDER_LIMIT` | order value above Rp 50,000,000 (configurable; the limit itself is allowed) |
| `INSUFFICIENT_FUNDS` | buy value above cash |
| `INSUFFICIENT_SHARES` | sell quantity above shares held |

Malformed orders are reported as malformed even when the market is closed. A rejected order changes nothing.
Simplifications: orders fill immediately and fully at the given price (default: last price); no fees, no order
book, no price band; WIB is a fixed UTC+7 offset (no daylight saving). The clock is injectable for tests.

## `/agent` (tool-using agent)

```bash
curl -X POST localhost:8000/agent -H "Content-Type: application/json" -d '{"message":"beli 2 lot TANX"}'
# -> {"session_id":"9f2c...","reply":"Konfirmasi order: BELI 200 lembar (2 lot) TANX @ Rp386 = Rp77.200. Balas 'ya' ...",
#     "pending_order":{"ticker":"TANX","side":"buy","quantity":200,"price":386,"value":77200},"tool_calls":[...]}
curl -X POST localhost:8000/agent -H "Content-Type: application/json" -d '{"message":"ya","session_id":"9f2c..."}'
curl localhost:8000/agent/9f2c.../log     # every tool call: seq, turn, tool, arguments, status, result, error_code
curl localhost:8000/agent/9f2c.../state   # broker portfolio, executed orders, pending order
```

Tools: `get_quote`, `get_portfolio`, `place_order` (on the mock broker). The model runs a loop of up to
`AGENT_MAX_STEPS`=6 tool rounds.

**Confirmation is enforced in code, not by the prompt.** When the model calls `place_order`, the order is only
validated (`check_order`). A valid order becomes `pending_order` and the reply asks for confirmation; an invalid one
goes back to the model as a tool error with its code. The order executes only if the user's **next** message is
an explicit confirmation (`ya`, `iya`, `ok`, `setuju`, `konfirmasi`, `lanjut`, …). `batal`/`tidak`/`jangan`
cancels it; any other message ("ya tapi 200 lembar", a new question) also drops it. A confirmation is executed by
code, without another model call, with exactly the pending arguments. Only one pending order at a time.

Tool-call statuses in the log: `ok`, `error` (with `error_code`), `pending_confirmation`, `executed`, `cancelled`.
Each entry is also written as a JSON line to the `finassist.agent` logger.

**Pluggable model** (`AGENT_PROVIDER`):

| Provider | Use | Notes |
|---|---|---|
| `ollama` (default) | development | `OLLAMA_MODEL` (llama3.2:3b), temperature 0, Ollama tool calling |
| `anthropic` | final runs | official `anthropic` SDK, `CLAUDE_MODEL`=claude-opus-5-5, effort `CLAUDE_EFFORT`=medium, server-side refusal fallback on (`fallbacks="default"`); a final `stop_reason: "refusal"` becomes HTTP 503. Needs `ANTHROPIC_API_KEY` in `.env` |

Each session gets its own fictional broker account. Market hours follow the real clock in WIB; set
`BROKER_ALWAYS_OPEN=true` for demos outside trading hours.

Sample run (llama3.2:3b, broker clock fixed at Tuesday 10:00 WIB):

| Message | Tool calls | Outcome |
|---|---|---|
| beli 2 lot TANX | `place_order` (200) → pending | asks confirmation for Rp77.200 |
| beli 100 lembar KOPX, then "ya" | pending → executed | order ORD-0001 filled |
| berapa saldo saya? | `get_portfolio` | Rp100.000.000 |
| beli 150 lembar KOPX | `place_order` → `LOT_SIZE` | explains the 100-share lot |
| beli saham BBCA 100 lembar | `place_order` → `UNKNOWN_TICKER` | lists the available fictional codes |
| jual semua KOPX saya | `place_order` (quantity **1000**) → `INSUFFICIENT_SHARES` | model guessed the quantity instead of reading the portfolio (holds 500) |
| Saham apa yang sebaiknya saya beli? | `get_quote` KOPX | quotes KOPX unprompted; no refusal, no disclaimer |

## Test

```bash
pytest
```

130 unit tests run offline (the LLM, embeddings and index are faked; the agent uses a scripted fake model).
Five acceptance tests run against a real Ollama and index:

```bash
pytest -m integration   # RAG: answer with sources, refusal, disclaimer · agent: confirmation before order, get_quote
```

## Roadmap

- [x] Skeleton: `/health`, `/chat` via Ollama
- [x] Ingest + structure-aware chunking + local vector index (P0-01)
- [x] RAG answers with citations, refusal and disclaimer (P0-02)
- [x] In-memory mock broker with rule checks (P0-03)
- [x] Agent with tools, confirmation before orders and a tool-call log (P0-04)
- [ ] Docker Compose (P0-05)
- [ ] Known risks backlog (P0-06)

Next steps:
1. P0-05: Docker Compose (app in a container, Ollama on the host via `host.docker.internal`).
2. P0-06: `docs/KNOWN_RISKS.md` from the weaknesses listed above.
3. Grow the corpus from 10 to 30 public documents.
