# RAG Sources

Public documents used by FinAssist ID's RAG pipeline: **30 documents** (29 Indonesian Wikipedia articles + 1 statute).
Content license differs from the code license: Wikipedia text is **CC BY-SA 4.0** (attribution: Wikipedia contributors,
Wikipedia bahasa Indonesia; derived chunks stay CC BY-SA); Indonesian statutes carry no copyright (UU No. 28/2014, Art. 42(b)).

Wikipedia articles are fetched with `python scripts/fetch_wikipedia.py` from the list in `scripts/wiki_titles.txt`
(MediaWiki plain-text extracts; "Referensi", "Pranala luar", "Lihat juga" sections removed; **tables are not kept**).
Each file's front matter records the exact revision. The statute text was extracted from the BPK PDF with `pdftotext`
(file: https://peraturan.bpk.go.id/Download/34758/UU%20Nomor%208%20Tahun%201995.pdf); it is the original 1995 text,
partly amended by UU No. 4/2023 (P2SK).

Only files with a `source:` in their front matter are indexed; project notes in this folder are skipped.

| # | Title | URL | License | Retrieved | File | Words |
|---|-------|-----|---------|-----------|------|------:|
| 1 | Analisis fundamental | https://id.wikipedia.org/wiki/Analisis_fundamental | CC BY-SA 4.0 | 2026-11-08 | wiki_analisis_fundamental.md | 1,787 |
| 2 | Badan Pengawas Pasar Modal dan Lembaga Keuangan | https://id.wikipedia.org/wiki/Badan_Pengawas_Pasar_Modal_dan_Lembaga_Keuangan | CC BY-SA 4.0 | 2026-11-08 | wiki_badan_pengawas_pasar_modal_dan_lembaga_keuangan.md | 464 |
| 3 | Bursa Efek Indonesia | https://id.wikipedia.org/wiki/Bursa_Efek_Indonesia | CC BY-SA 4.0 | 2026-11-08 | wiki_bursa_efek_indonesia.md | 6,562 |
| 4 | Dana tukar-dagang | https://id.wikipedia.org/wiki/Dana_tukar-dagang | CC BY-SA 4.0 | 2026-11-08 | wiki_dana_tukar_dagang.md | 1,467 |
| 5 | Derivatif | https://id.wikipedia.org/wiki/Derivatif | CC BY-SA 4.0 | 2026-11-08 | wiki_derivatif.md | 927 |
| 6 | Dividen | https://id.wikipedia.org/wiki/Dividen | CC BY-SA 4.0 | 2026-11-08 | wiki_dividen.md | 579 |
| 7 | Efek | https://id.wikipedia.org/wiki/Efek | CC BY-SA 4.0 | 2026-11-08 | wiki_efek.md | 165 |
| 8 | Hak memesan efek terlebih dahulu | https://id.wikipedia.org/wiki/Hak_memesan_efek_terlebih_dahulu | CC BY-SA 4.0 | 2026-11-08 | wiki_hak_memesan_efek_terlebih_dahulu.md | 824 |
| 9 | Indeks Harga Saham Gabungan | https://id.wikipedia.org/wiki/Indeks_Harga_Saham_Gabungan | CC BY-SA 4.0 | 2026-11-08 | wiki_indeks_harga_saham_gabungan.md | 361 |
| 10 | Indeks LQ45 | https://id.wikipedia.org/wiki/Indeks_LQ45 | CC BY-SA 4.0 | 2026-11-08 | wiki_indeks_lq45.md | 144 |
| 11 | Investasi | https://id.wikipedia.org/wiki/Investasi | CC BY-SA 4.0 | 2026-11-08 | wiki_investasi.md | 1,729 |
| 12 | Jakarta Islamic Index | https://id.wikipedia.org/wiki/Jakarta_Islamic_Index | CC BY-SA 4.0 | 2026-11-08 | wiki_jakarta_islamic_index.md | 610 |
| 13 | Kapitalisasi pasar | https://id.wikipedia.org/wiki/Kapitalisasi_pasar | CC BY-SA 4.0 | 2026-11-08 | wiki_kapitalisasi_pasar.md | 496 |
| 14 | Kliring Penjaminan Efek Indonesia | https://id.wikipedia.org/wiki/Kliring_Penjaminan_Efek_Indonesia | CC BY-SA 4.0 | 2026-11-08 | wiki_kliring_penjaminan_efek_indonesia.md | 979 |
| 15 | Kontrak berjangka | https://id.wikipedia.org/wiki/Kontrak_berjangka | CC BY-SA 4.0 | 2026-11-08 | wiki_kontrak_berjangka.md | 2,362 |
| 16 | Kustodian Sentral Efek Indonesia | https://id.wikipedia.org/wiki/Kustodian_Sentral_Efek_Indonesia | CC BY-SA 4.0 | 2026-11-08 | wiki_kustodian_sentral_efek_indonesia.md | 489 |
| 17 | Manajemen investasi | https://id.wikipedia.org/wiki/Manajemen_investasi | CC BY-SA 4.0 | 2026-11-08 | wiki_manajemen_investasi.md | 1,449 |
| 18 | Obligasi | https://id.wikipedia.org/wiki/Obligasi | CC BY-SA 4.0 | 2026-11-08 | wiki_obligasi.md | 4,648 |
| 19 | Obligasi Negara Ritel | https://id.wikipedia.org/wiki/Obligasi_Negara_Ritel | CC BY-SA 4.0 | 2026-11-08 | wiki_obligasi_negara_ritel.md | 84 |
| 20 | Opsi (keuangan) | https://id.wikipedia.org/wiki/Opsi_(keuangan) | CC BY-SA 4.0 | 2026-11-08 | wiki_opsi_keuangan.md | 1,634 |
| 21 | Otoritas Jasa Keuangan | https://id.wikipedia.org/wiki/Otoritas_Jasa_Keuangan | CC BY-SA 4.0 | 2026-11-08 | wiki_otoritas_jasa_keuangan.md | 763 |
| 22 | Pasar modal | https://id.wikipedia.org/wiki/Pasar_modal | CC BY-SA 4.0 | 2026-11-08 | wiki_pasar_modal.md | 3,126 |
| 23 | Penawaran umum perdana | https://id.wikipedia.org/wiki/Penawaran_umum_perdana | CC BY-SA 4.0 | 2026-11-08 | wiki_penawaran_umum_perdana.md | 1,985 |
| 24 | Perusahaan efek | https://id.wikipedia.org/wiki/Perusahaan_efek | CC BY-SA 4.0 | 2026-11-08 | wiki_perusahaan_efek.md | 330 |
| 25 | Pialang saham | https://id.wikipedia.org/wiki/Pialang_saham | CC BY-SA 4.0 | 2026-11-08 | wiki_pialang_saham.md | 729 |
| 26 | Reksa dana | https://id.wikipedia.org/wiki/Reksa_dana | CC BY-SA 4.0 | 2026-11-08 | wiki_reksa_dana.md | 3,912 |
| 27 | Saham | https://id.wikipedia.org/wiki/Saham | CC BY-SA 4.0 | 2026-11-08 | wiki_saham.md | 2,088 |
| 28 | Sukuk | https://id.wikipedia.org/wiki/Sukuk | CC BY-SA 4.0 | 2026-11-08 | wiki_sukuk.md | 698 |
| 29 | Waran | https://id.wikipedia.org/wiki/Waran | CC BY-SA 4.0 | 2026-11-08 | wiki_waran.md | 148 |
| 30 | Undang-Undang Republik Indonesia Nomor 8 Tahun 1995 tentang Pasar Modal (beserta Penjelasan) | https://peraturan.bpk.go.id/Details/46197/uu-no-8-tahun-1995 | Public domain (statute) | 2026-11-08 | uu_8_1995_pasar_modal.md | 24,673 |

Reference-only (not copied into this repo): OJK SikapiUangmu, KSEI FAQ, idx.co.id — no explicit reuse permission found.
