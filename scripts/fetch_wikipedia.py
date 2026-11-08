"""Fetch Indonesian Wikipedia articles into docs/ as plain-text markdown with a license header.

Usage:
    python scripts/fetch_wikipedia.py            # fetch titles in scripts/wiki_titles.txt that have no file yet
    python scripts/fetch_wikipedia.py --refresh  # re-fetch every title (new revisions)

Uses the MediaWiki API (plain-text extracts). Reference-only sections ("Referensi", "Pranala luar", ...) are dropped.
Each file records the exact revision so answers can be traced to the text that was indexed.
"""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
TITLES = ROOT / "scripts" / "wiki_titles.txt"
DOCS = ROOT / "docs"
API = "https://id.wikipedia.org/w/api.php"
UA = {"User-Agent": "finassist-portfolio/0.1 (non-commercial research; https://github.com/Jordy1406/finassist-app)"}
DROP_SECTIONS = {"Referensi", "Pranala luar", "Lihat pula", "Lihat juga", "Bacaan lanjutan", "Catatan", "Daftar pustaka"}


def slug(title: str) -> str:
    return "wiki_" + re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def clean(text: str) -> str:
    out, skip = [], False
    for line in text.splitlines():
        m = re.match(r"^(=+)\s*(.+?)\s*\1$", line)
        if m:
            skip = m.group(2) in DROP_SECTIONS
            if not skip:
                out.append("#" * len(m.group(1)) + " " + m.group(2))
            continue
        if not skip:
            out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def fetch(title: str, client: httpx.Client) -> dict:
    data = client.get(API, params={
        "action": "query", "prop": "extracts|info|revisions", "explaintext": 1, "exsectionformat": "wiki",
        "inprop": "url", "rvprop": "ids|timestamp", "titles": title, "redirects": 1, "format": "json",
        "formatversion": 2,
    }).raise_for_status().json()
    page = data["query"]["pages"][0]
    if page.get("missing"):
        raise LookupError(f"Wikipedia page not found: {title}")
    return page


def write_doc(page: dict, retrieved: str) -> Path:
    rev = page["revisions"][0]
    body = clean(page["extract"])
    header = (
        f"---\ntitle: {page['title']}\nsource: {page['fullurl']}\n"
        f"revision: {rev['revid']} ({rev['timestamp']})\n"
        f"license: CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/)\n"
        f"attribution: Wikipedia contributors, Wikipedia bahasa Indonesia\n"
        f"retrieved: {retrieved}\nlanguage: id\n---\n\n# {page['title']}\n\n"
    )
    path = DOCS / f"{slug(page['title'])}.md"
    path.write_text(header + body + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--refresh", action="store_true", help="re-fetch titles that already have a file")
    args = parser.parse_args(argv)
    titles = [t.strip() for t in TITLES.read_text(encoding="utf-8").splitlines() if t.strip() and not t.startswith("#")]
    today = date.today().isoformat()
    with httpx.Client(headers=UA, timeout=30) as client:
        for title in titles:
            if not args.refresh and (DOCS / f"{slug(title)}.md").exists():
                continue
            page = fetch(title, client)
            path = write_doc(page, today)
            words = len(path.read_text(encoding="utf-8").split())
            print(f"{path.name:52} {words:6} words  rev {page['revisions'][0]['revid']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
