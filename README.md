# FinAssist ID

Target system for an AI Quality Engineering portfolio: a Bahasa Indonesia assistant over **public** capital-market
education documents (RAG), plus an agent that trades against a **mock** broker with fictional data.
Later projects (P1–P4) test, evaluate and red-team this system.

> Status: skeleton (P0, week 0). Endpoints: `GET /health`, `POST /chat` (proxied to a local Ollama model).

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Install [Ollama](https://ollama.com) and pull a small model:

```bash
ollama pull llama3.2:3b
```

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

Unit tests mock the LLM, so they pass without Ollama running.

## Roadmap

- [x] Skeleton: `/health`, `/chat` via Ollama
- [ ] Ingest + chunking of public docs (P0-01)
- [ ] RAG answers with citations and refusal (P0-02)
- [ ] Mock broker + agent tools (P0-03, P0-04)
- [ ] Docker Compose (P0-05)
