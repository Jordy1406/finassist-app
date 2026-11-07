# CLAUDE.md — finassist-app (P0)

## KONTEKS
Repo ini bagian dari portofolio AI Quality Engineer milik Jordy (org GitHub: `finassist-quality`).
Sistem target bernama **FinAssist ID**: chatbot RAG atas dokumen publik pasar modal (Bahasa Indonesia)
+ agent dengan tools `get_quote`, `get_portfolio`, `place_order` ke MOCK broker (data fiktif).

- **Repo ini:** P0 — FinAssist ID (sistem target).
- **Tujuan:** Sistem AI buatan sendiri yang stabil sebagai target uji (P1–P4 akan menguji sistem ini).
- **MINIMUM:** FastAPI; RAG atas 30 dokumen publik (sumber dicatat); agent 3 tools ke mock broker in-memory
  (saldo fiktif, batas order, jam pasar); model via env (Ollama/Claude API); Docker Compose.
- **STRETCH:** UI chat sederhana; switch beberapa model untuk perbandingan.
- **Selesai jika:** `docker compose up` jalan; README arsitektur + diagram; sengaja menyisakan kelemahan
  yang akan ditemukan P1–P4.

## STACK
Python 3.12 (venv: `py -3.12 -m venv .venv`), FastAPI, pytest, Ollama (dev), Docker, GitHub Actions.

## STRUKTUR
```
app/      main.py (endpoint), config.py (settings dari env), llm.py (klien Ollama)
tests/    pytest
docs/     dokumen publik untuk RAG + SOURCES.md
```

## CARA RUN
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |  macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
pytest
uvicorn app.main:app --reload     # http://localhost:8000/docs
```
`/chat` butuh Ollama jalan di `OLLAMA_HOST` dengan model `OLLAMA_MODEL` sudah di-pull.

## ATURAN
- Jelaskan rencana dulu, tunggu persetujuan, baru tulis kode.
- 1 sesi = 1 fitur = 1 commit/PR kecil. Pesan commit format Conventional Commits.
- Kerjakan MINIMUM dulu; STRETCH hanya jika diminta.
- Jangan tambah dependency tanpa alasan; catat di README jika menambah.
- Data hanya publik atau fiktif. Rahasia hanya di `.env` (dan `.env` di `.gitignore`).
- Desain eval (dataset, rubrik, label) dikerjakan Jordy; Claude bantu implementasi dan menjelaskan.
- Setelah tiap fitur: jalankan test, laporkan hasil, usulkan pesan commit.
