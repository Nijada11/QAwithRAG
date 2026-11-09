import pytest

from src.ingest import (
    Block,
    Document,
    UnsupportedFileError,
    chunk_document,
    embedding_text,
    load_document,
    parse_markdown,
)
from tests.conftest import DOCS


def make_pdf(pages: list[str]) -> bytes:
    """A minimal valid PDF with one line of text per page."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>")
    font_id = 3 + 2 * len(pages)
    for i, text in enumerate(pages):
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>"
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = "%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return out.encode("latin-1")


def test_markdown_keeps_text_and_sections_and_drops_learn_markup():
    title, blocks = parse_markdown(DOCS["tap.md"])
    assert title == "Temporary Access Pass"
    texts = [b.text for b in blocks]
    assert "The maximum lifetime of a pass is 30 days." in texts
    assert not any("INCLUDE" in t or ":::" in t for t in texts)
    assert blocks[-1].section == "Lifetime"


def test_markdown_cleans_inline_markup_and_keeps_code():
    text = (
        "# T\n\nUse **Security info** at [aka.ms/mysecurityinfo](https://aka.ms/x).\n"
        "![screenshot](a.png)\n\n> [!NOTE]\n> Notes are kept.\n\n```powershell\nGet-MgUser\n```\n"
    )
    _, blocks = parse_markdown(text)
    texts = [b.text for b in blocks]
    assert texts[0] == "Use Security info at aka.ms/mysecurityinfo."
    assert "Notes are kept." in texts
    assert "Get-MgUser" in texts


def test_nested_headings_build_a_path():
    _, blocks = parse_markdown("# Title\n\n## A\n\n### B\n\ntext\n\n## C\n\nmore\n")
    assert [b.section for b in blocks] == ["A > B", "C"]


def test_pdf_blocks_carry_page_numbers():
    doc = load_document(make_pdf(["First page text", "Second page text"]), "f.pdf", "f")
    assert [(b.text, b.page) for b in doc.blocks] == [("First page text", 1), ("Second page text", 2)]
    # Even with room for both pages, a chunk stops at the page break.
    chunks = chunk_document(doc, chunk_words=600, overlap_words=100)
    assert [(c.text, c.page) for c in chunks] == [("First page text", 1), ("Second page text", 2)]


def test_html_and_text_are_supported():
    html = (
        b"<html><head><title>Page</title><script>x()</script></head>"
        b"<body><p>Hello there</p><p>Second</p></body></html>"
    )
    doc = load_document(html, "p.html", "p")
    assert doc.title == "Page"
    assert [b.text for b in doc.blocks] == ["Hello there", "Second"]
    assert load_document(b"one\n\ntwo", "t.txt", "t").title == "t"


def test_unsupported_type_is_rejected():
    with pytest.raises(UnsupportedFileError):
        load_document(b"x", "sheet.xlsx", "s")


def _doc(paragraph_words: list[int]) -> Document:
    blocks = [Block(" ".join(f"p{i}w{j}" for j in range(n))) for i, n in enumerate(paragraph_words)]
    return Document("d", "Doc", "https://example.org", blocks)


def test_chunks_respect_size_and_overlap():
    chunks = chunk_document(_doc([40] * 10), chunk_words=100, overlap_words=40)
    assert all(len(c.text.split()) <= 100 for c in chunks)
    # The last paragraph of each chunk opens the next one.
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert a.text.split("\n\n")[-1] == b.text.split("\n\n")[0]
    # Every paragraph lands in some chunk.
    joined = " ".join(c.text for c in chunks)
    assert all(f"p{i}w0" in joined for i in range(10))


def test_long_paragraph_is_split_and_overlap_fits():
    chunks = chunk_document(_doc([500]), chunk_words=100, overlap_words=20)
    assert all(len(c.text.split()) <= 100 for c in chunks)
    assert len(chunks) >= 5


def test_no_chunk_made_only_of_overlap():
    chunks = chunk_document(_doc([30, 30, 30]), chunk_words=60, overlap_words=30)
    assert not chunks[-1].text == chunks[-2].text.split("\n\n")[-1]


def test_overlap_must_be_smaller_than_chunk():
    with pytest.raises(ValueError):
        chunk_document(_doc([10]), chunk_words=50, overlap_words=50)


def test_embedding_text_includes_title_and_section():
    doc = load_document(DOCS["tap.md"].encode(), "tap.md", "tap")
    chunk = chunk_document(doc, 600, 100)[0]
    assert embedding_text(chunk).startswith("Temporary Access Pass > ")
