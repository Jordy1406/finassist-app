"""Container entrypoint: build the document index if it is missing, then start the API.

Kept in Python (not a shell script) so it runs the same on Windows checkouts, where .sh files can
pick up CRLF line endings and fail inside a Linux container.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

from app import ingest
from app.config import get_settings


def ensure_index() -> None:
    settings = get_settings()
    if Path(settings.index_path).exists():
        print(f"[serve] index found at {settings.index_path}", flush=True)
        return
    print(f"[serve] no index at {settings.index_path}; building it from {settings.docs_dir}/ ...", flush=True)
    if ingest.main([]) != 0:
        # Keep the API up: /health and /agent work without the index; /chat returns 503 with the reason.
        print("[serve] index build failed; /chat will return 503 until `python -m app.ingest` succeeds", file=sys.stderr,
              flush=True)


def main() -> None:
    ensure_index()
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))


if __name__ == "__main__":
    main()
