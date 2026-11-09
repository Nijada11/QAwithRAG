"""Turn files into chunks: extract text, clean it, split it with overlap.

Each chunk keeps where it came from (source URL, title, section heading and, for PDFs, the
page number), because the answer has to cite it.

Chunks are packed from whole paragraphs, so a sentence is never cut in half unless a single
paragraph is longer than the chunk size. The overlap repeats the last paragraphs of one
chunk at the start of the next, so a fact that straddles a boundary is complete in at least
one of them.
"""

from __future__ import annotations

import html
import io
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from pypdf import PdfReader

SUPPORTED_SUFFIXES = {".pdf", ".md", ".markdown", ".txt", ".html", ".htm"}


class UnsupportedFileError(ValueError):
    pass


@dataclass
class Block:
    """A paragraph-sized piece of text with its position in the document."""

    text: str
    section: str = ""
    page: int | None = None

    @property
    def words(self) -> int:
        return len(self.text.split())


@dataclass
class Document:
    doc_id: str
    title: str
    url: str
    blocks: list[Block] = field(default_factory=list)


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    url: str
    section: str
    page: int | None
    text: str

    @property
    def metadata(self) -> dict:
        # Chroma metadata values cannot be None.
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "url": self.url,
            "section": self.section,
            "page": self.page or 0,
        }


# --- Extraction ----------------------------------------------------------------------------

_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_DROP_LINE = re.compile(r"^\s*(>\s*)?(\[!INCLUDE|\[!div|:::|<!--|-->|---\s*$|\*\*\*\s*$)", re.IGNORECASE)
_ALERT = re.compile(r"^>\s*\[!(NOTE|IMPORTANT|TIP|WARNING|CAUTION)\]\s*$", re.IGNORECASE)


def _clean_inline(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)  # images
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # links -> their text
    text = re.sub(r"<[^>]+>", "", text)  # inline HTML
    text = text.replace("**", "").replace("__", "")
    return html.unescape(text).strip()


def parse_markdown(text: str) -> tuple[str, list[Block]]:
    """Return (title, blocks). Learn-style markup (includes, images, zones) is dropped."""
    title = ""
    match = _FRONT_MATTER.match(text)
    if match:
        title_match = re.search(r"^title:\s*(.+)$", match.group(1), re.MULTILINE)
        title = title_match.group(1).strip().strip("'\"") if title_match else ""
        text = text[match.end() :]
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    blocks: list[Block] = []
    headings: dict[int, str] = {}
    paragraph: list[str] = []
    in_code = False

    def section() -> str:
        # The H1 repeats the page title, so the section path starts at H2.
        return " > ".join(headings[level] for level in sorted(headings) if level > 1)

    def flush() -> None:
        joined = "\n".join(paragraph).strip()
        if joined:
            blocks.append(Block(joined, section()))
        paragraph.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            paragraph.append(line)
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            headings = {k: v for k, v in headings.items() if k < level}
            headings[level] = _clean_inline(heading.group(2))
            if level == 1 and not title:
                title = headings[1]
            continue
        if _DROP_LINE.match(line) or _ALERT.match(line):
            continue
        if not line.strip():
            flush()
            continue
        line = re.sub(r"^\s*>\s?", "", line)  # blockquote marker of NOTE/TIP boxes
        cleaned = _clean_inline(line)
        if cleaned:
            paragraph.append(cleaned)
    flush()
    return title, blocks


def parse_pdf(data: bytes) -> tuple[str, list[Block]]:
    reader = PdfReader(io.BytesIO(data))
    title = (reader.metadata.title if reader.metadata else None) or ""
    blocks: list[Block] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        for paragraph in re.split(r"\n\s*\n", text):
            # pypdf ends every visual line with \n; rejoin lines inside a paragraph.
            joined = re.sub(r"-\n(?=\w)", "", paragraph)
            joined = re.sub(r"\s*\n\s*", " ", joined).strip()
            if joined:
                blocks.append(Block(joined, page=page_number))
    return title, blocks


class _TextFromHTML(HTMLParser):
    BLOCK_TAGS = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre"}
    SKIP_TAGS = {"script", "style", "nav", "header", "footer", "noscript"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip_depth:
            self.parts.append(data)


def parse_html(text: str) -> tuple[str, list[Block]]:
    parser = _TextFromHTML()
    parser.feed(text)
    return parser.title.strip(), parse_plain("".join(parser.parts))


def parse_plain(text: str) -> list[Block]:
    paragraphs = (re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text))
    return [Block(p) for p in paragraphs if p]


def load_document(data: bytes, filename: str, doc_id: str, url: str = "", title: str = "") -> Document:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        found_title, blocks = parse_pdf(data)
    elif suffix in {".md", ".markdown"}:
        found_title, blocks = parse_markdown(data.decode("utf-8", "replace"))
    elif suffix in {".html", ".htm"}:
        found_title, blocks = parse_html(data.decode("utf-8", "replace"))
    elif suffix == ".txt":
        found_title, blocks = "", parse_plain(data.decode("utf-8", "replace"))
    else:
        raise UnsupportedFileError(
            f"Unsupported file type {suffix or '(none)'}; use one of " + ", ".join(sorted(SUPPORTED_SUFFIXES))
        )
    return Document(doc_id, title or found_title or Path(filename).stem, url, blocks)


# --- Chunking ------------------------------------------------------------------------------


def _split_long(block: Block, max_words: int) -> list[Block]:
    """Split a block longer than a whole chunk (big tables, PDF pages without blank lines)."""
    words = block.text.split()
    if len(words) <= max_words:
        return [block]
    return [
        Block(" ".join(words[i : i + max_words]), block.section, block.page)
        for i in range(0, len(words), max_words)
    ]


def chunk_document(doc: Document, chunk_words: int = 600, overlap_words: int = 100) -> list[Chunk]:
    if overlap_words >= chunk_words:
        raise ValueError("overlap must be smaller than the chunk size")
    # Pieces of a split paragraph leave room for the overlap carried in front of them.
    piece_words = chunk_words - overlap_words
    blocks = [piece for block in doc.blocks for piece in _split_long(block, piece_words)]

    chunks: list[Chunk] = []
    current: list[Block] = []

    def emit() -> None:
        first = current[0]
        # The section the chunk is mostly about: the one contributing the most words.
        weight: dict[str, int] = {}
        for block in current:
            weight[block.section] = weight.get(block.section, 0) + block.words
        section = max(weight, key=weight.get) if weight else first.section
        chunks.append(
            Chunk(
                chunk_id=f"{doc.doc_id}#{len(chunks)}",
                doc_id=doc.doc_id,
                title=doc.title,
                url=doc.url,
                section=section,
                page=first.page,
                text="\n\n".join(block.text for block in current),
            )
        )

    size = 0
    for block in blocks:
        if current and block.page != current[-1].page:
            # A chunk never spans a page break, so its page number is right for every
            # passage in it. No overlap across pages, for the same reason.
            emit()
            current, size = [], 0
        elif current and size + block.words > chunk_words:
            emit()
            # Carry the tail of the finished chunk into the next one as overlap.
            carried: list[Block] = []
            carried_words = 0
            for previous in reversed(current):
                if carried_words + previous.words > overlap_words:
                    break
                carried.insert(0, previous)
                carried_words += previous.words
            current, size = carried, carried_words
        current.append(block)
        size += block.words
    if current:
        emit()
    return _drop_overlap_only_tail(chunks)


def _drop_overlap_only_tail(chunks: list[Chunk]) -> list[Chunk]:
    """A last chunk made only of carried-over text adds nothing; drop it."""
    if len(chunks) >= 2 and chunks[-2].text.endswith(chunks[-1].text):
        return chunks[:-1]
    return chunks


def embedding_text(chunk: Chunk) -> str:
    """What gets embedded: the passage plus where it sits, so short passages keep context."""
    heading = f"{chunk.title} > {chunk.section}" if chunk.section else chunk.title
    return f"{heading}\n\n{chunk.text}"
