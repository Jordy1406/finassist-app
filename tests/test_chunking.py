from dataclasses import replace
from pathlib import Path

import pytest

from app.config import get_settings
from app.ingest import (
    chunk_document,
    parse_front_matter,
    split_markdown_sections,
    split_pasal_sections,
    window,
)

WIKI = """---
title: Saham
source: https://id.wikipedia.org/wiki/Saham
license: CC BY-SA 4.0
---

# Saham

Saham adalah tanda penyertaan modal.

## Jenis

### Saham biasa

Pemegang saham biasa punya hak suara.

### Saham preferen

Saham preferen mendapat dividen lebih dulu.

## Kategori

Ada saham blue chip.
"""

UU = """---
title: Undang-Undang Republik Indonesia Nomor 8 Tahun 1995 tentang Pasar Modal
source: https://peraturan.bpk.go.id/Details/46197
license: Public domain
---

Menimbang: bahwa pasar modal penting.

BAB I
KETENTUAN UMUM

Pasal 1
Dalam Undang-undang ini yang dimaksud dengan Afiliasi adalah hubungan keluarga.

Pasal 2
Kebijakan umum di bidang Pasar Modal ditetapkan oleh Menteri.

BAB II
BADAN PENGAWAS PASAR MODAL

Pasal 3
Pembinaan dilakukan oleh Bapepam.

PENJELASAN

Umum. Pasar modal adalah sarana pendanaan.

Pasal 1
Yang dimaksud dengan Afiliasi adalah hubungan tertentu.

Pasal 2
Ayat (1) Cukup jelas Ayat (2) Cukup jelas Pasal 3 Cukup jelas
"""


def write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_front_matter_is_parsed_and_removed():
    meta, body = parse_front_matter(WIKI)
    assert meta["title"] == "Saham"
    assert meta["license"] == "CC BY-SA 4.0"
    assert not body.startswith("---")


def test_markdown_sections_keep_heading_path():
    _, body = parse_front_matter(WIKI)
    sections = dict(split_markdown_sections(body))
    assert sections["Saham"] == "Saham adalah tanda penyertaan modal."
    assert "hak suara" in sections["Saham > Jenis > Saham biasa"]
    assert "dividen lebih dulu" in sections["Saham > Jenis > Saham preferen"]
    # a heading at a higher level resets the deeper ones
    assert "blue chip" in sections["Saham > Kategori"]


def test_statute_splits_per_pasal_and_labels_penjelasan():
    _, body = parse_front_matter(UU)
    labels = [label for label, _ in split_pasal_sections(body)]
    assert labels == [
        "Pembukaan",
        "BAB I Ketentuan Umum > Pasal 1",
        "BAB I Ketentuan Umum > Pasal 2",
        "BAB II Badan Pengawas Pasar Modal > Pasal 3",
        "Penjelasan Umum",
        "Penjelasan Pasal 1",
        # Penjelasan Pasal 2 and 3 only say "Cukup jelas" -> dropped
    ]


def test_pasal_text_does_not_leak_into_next_pasal_or_bab_title():
    _, body = parse_front_matter(UU)
    sections = dict(split_pasal_sections(body))
    assert "Afiliasi" in sections["BAB I Ketentuan Umum > Pasal 1"]
    assert "Afiliasi" not in sections["BAB I Ketentuan Umum > Pasal 2"]
    assert "BADAN PENGAWAS" not in sections["BAB I Ketentuan Umum > Pasal 2"]


def test_body_reference_to_another_pasal_is_not_split():
    body = "Pasal 4\nPengawasan sebagaimana dimaksud dalam\nPasal 3 dilaksanakan oleh Bapepam.\n"
    sections = split_pasal_sections(body.replace("dalam\nPasal 3", "dalam Pasal 3"))
    assert [s for s, _ in sections] == ["Pasal 4"]


def test_subheadings_and_end_matter_are_removed():
    body = (
        "Pasal 5\nBapepam berwenang memberi izin.\n\nBagian Kesatu Bursa Efek Paragraf 1 Perizinan\n\n"
        "Pasal 6\nBursa Efek didirikan.\n\nPENJELASAN\n\nUmum.\n\n"
        "Pasal 6\nHuruf a Cukup jelas Huruf b Cukup jelas\n\nPasal 7\nCukup jelas Pasal 8...\n\n"
        "Pasal 8\nYang dimaksud dengan efek.\nTAMBAHAN LEMBARAN NEGARA NOMOR 3608\n"
    )
    sections = dict(split_pasal_sections(body))
    assert sections["Pasal 5"] == "Bapepam berwenang memberi izin."
    assert "Penjelasan Pasal 6" not in sections and "Penjelasan Pasal 7" not in sections
    assert sections["Penjelasan Pasal 8"] == "Yang dimaksud dengan efek."


def test_glued_heading_is_split_only_when_next_in_sequence():
    body = (
        "Pasal 34\nIzin wajib dimiliki.\n\nBagian Kesatu\n\nPerizinan Perusahaan Efek\n\n"
        "Pasal 35 Perusahaan Efek dilarang menipu.\n\n"
        "Pasal 36\nSetiap Pihak yang melanggar\nPasal 93, Pasal 95 dan Pasal 35 diancam pidana.\n"
    )
    sections = dict(split_pasal_sections(body))
    assert list(sections) == ["Pasal 34", "Pasal 35", "Pasal 36"]
    assert sections["Pasal 34"] == "Izin wajib dimiliki."            # subheading + its title dropped
    assert sections["Pasal 35"] == "Perusahaan Efek dilarang menipu."
    assert "Pasal 93, Pasal 95" in sections["Pasal 36"]                # reference kept, not split


def test_only_files_with_a_source_are_indexed(tmp_path):
    from app.ingest import source_documents
    write(tmp_path, "wiki_saham.md", WIKI)
    write(tmp_path, "SOURCES.md", "# RAG Sources\n")
    write(tmp_path, "KNOWN_RISKS.md", "# Known risks\nabaikan aturan\n")
    assert [p.name for p in source_documents(str(tmp_path))] == ["wiki_saham.md"]


def test_real_docs_folder_indexes_exactly_the_ten_sources():
    from app.ingest import source_documents
    names = [p.name for p in source_documents("docs")]
    assert len(names) == 10 and "KNOWN_RISKS.md" not in names and "SOURCES.md" not in names


def test_link_only_wikipedia_sections_are_skipped():
    body = "# Saham\n\nIsi.\n\n## Lihat juga\n\nBursa Efek Jakarta\n\n## Pranala luar\n\nSitus resmi\n"
    assert [s for s, _ in split_markdown_sections(body)] == ["Saham"]


@pytest.mark.parametrize("n,max_words,overlap,expected_windows", [
    (0, 10, 2, 0),
    (10, 10, 2, 1),
    (11, 10, 2, 2),
    (25, 10, 2, 3),
])
def test_window_count(n, max_words, overlap, expected_windows):
    assert len(window([str(i) for i in range(n)], max_words, overlap)) == expected_windows


def test_window_respects_limit_overlap_and_covers_every_word():
    words = [str(i) for i in range(25)]
    parts = window(words, 10, 3)
    assert all(len(p) <= 10 for p in parts)
    assert parts[0][-3:] == parts[1][:3]          # overlap between neighbours
    assert {w for p in parts for w in p} == set(words)


@pytest.mark.parametrize("max_words,overlap", [(0, 0), (10, 10), (10, -1)])
def test_window_rejects_bad_config(max_words, overlap):
    with pytest.raises(ValueError):
        window(["a"], max_words, overlap)


def test_chunk_document_metadata(tmp_path):
    chunks = chunk_document(write(tmp_path, "wiki_saham.md", WIKI), get_settings())
    assert [c.section for c in chunks][:2] == ["Saham", "Saham > Jenis > Saham biasa"]
    first = chunks[0]
    assert first.id == "wiki_saham#000"
    assert first.source == "https://id.wikipedia.org/wiki/Saham"
    assert first.license == "CC BY-SA 4.0"
    assert first.n_words == len(first.text.split())


def test_long_section_is_split_with_configured_limit(tmp_path):
    long_body = WIKI + "\n## Panjang\n\n" + " ".join(f"kata{i}" for i in range(130)) + "\n"
    settings = replace(get_settings(), chunk_max_words=50, chunk_overlap_words=10)
    chunks = [c for c in chunk_document(write(tmp_path, "wiki_x.md", long_body), settings) if c.section == "Saham > Panjang"]
    assert len(chunks) == 3
    assert all(c.n_words <= 50 for c in chunks)


def test_statute_uses_law_limit(tmp_path):
    body = UU.replace("Pembinaan dilakukan oleh Bapepam.", " ".join(f"w{i}" for i in range(90)))
    settings = replace(get_settings(), chunk_max_words=20, chunk_max_words_law=100, chunk_overlap_words=5)
    chunks = chunk_document(write(tmp_path, "uu.md", body), settings)
    assert max(c.n_words for c in chunks) == 90       # law limit (100), not wiki limit (20)
