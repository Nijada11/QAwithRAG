"""The question-answering pipeline: retrieve, answer, cite, and log cost and latency."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.config import ROOT, RagConfig
from src.ingest import Chunk, chunk_document, load_document
from src.llm import IDK, Answerer, is_idk
from src.store import CrossEncoderReranker, Hit, Index, SentenceTransformerEmbedder

logger = logging.getLogger("rag.pipeline")


@dataclass
class Source:
    n: int
    title: str
    url: str
    section: str
    page: int | None
    chunk_id: str
    quotes: list[str] = field(default_factory=list)


@dataclass
class Answer:
    answer: str
    sources: list[Source]
    answered: bool
    # Everything below is for evaluation and monitoring, not for the end user.
    retrieved: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    retrieval_ms: float = 0.0
    llm_ms: float = 0.0
    total_ms: float = 0.0


def build_sources(hits: list[Hit], llm_answer) -> tuple[str, list[Source]]:
    """Keep only the hits the answer cites, number them 1..n, and rewrite the markers."""
    order: list[int] = []
    quotes: dict[int, list[str]] = {}
    for citation in llm_answer.citations:
        if not 0 <= citation.hit_index < len(hits):
            continue
        if citation.hit_index not in order:
            order.append(citation.hit_index)
        if citation.quote and citation.quote not in quotes.setdefault(citation.hit_index, []):
            quotes[citation.hit_index].append(citation.quote)
    renumber = {hit_index: n for n, hit_index in enumerate(order, start=1)}

    def replace(match: re.Match) -> str:
        n = renumber.get(int(match.group(1)) - 1)
        return f"[{n}]" if n else ""

    text = re.sub(r"\[(\d+)\]", replace, llm_answer.text)
    sources = []
    for hit_index in order:
        chunk = hits[hit_index].chunk
        sources.append(
            Source(
                n=renumber[hit_index],
                title=chunk.title,
                url=chunk.url,
                section=chunk.section,
                page=chunk.page,
                chunk_id=chunk.chunk_id,
                quotes=quotes.get(hit_index, []),
            )
        )
    return text, sources


class RAG:
    def __init__(self, config: RagConfig, index: Index | None = None, answerer: Answerer | None = None):
        self.config = config
        self.index = index or Index(
            str(config.index_dir),
            config.collection,
            SentenceTransformerEmbedder(config.embed_model),
            CrossEncoderReranker(config.rerank_model) if "rerank" in config.retrieval else None,
            config.rerank_candidates,
        )
        self._answerer = answerer
        self._log_lock = threading.Lock()

    @property
    def answerer(self) -> Answerer:
        # Created on first use, so retrieval-only work (indexing, retrieval eval) needs no key.
        if self._answerer is None:
            from src.llm import ClaudeAnswerer

            self._answerer = ClaudeAnswerer(self.config.llm_model, self.config.llm_effort)
        return self._answerer

    # --- indexing --------------------------------------------------------------------------

    def chunk(self, data: bytes, filename: str, doc_id: str, url: str = "", title: str = "") -> list[Chunk]:
        doc = load_document(data, filename, doc_id, url, title)
        return chunk_document(doc, self.config.chunk_words, self.config.overlap_words)

    def add_document(
        self, data: bytes, filename: str, doc_id: str, url: str = "", title: str = ""
    ) -> list[Chunk]:
        chunks = self.chunk(data, filename, doc_id, url, title)
        self.index.delete_document(doc_id)  # re-uploading a file replaces it
        self.index.add(chunks)
        return chunks

    def build_from_manifest(self, data_dir: Path = ROOT / "data") -> int:
        """Index every document listed in data/manifest.jsonl. Returns the chunk count."""
        chunks: list[Chunk] = []
        with open(data_dir / "manifest.jsonl", encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line)
                path = data_dir / entry["file"]
                chunks += self.chunk(
                    path.read_bytes(), path.name, entry["doc_id"], entry["url"], entry["title"]
                )
        self.index.add(chunks)
        return len(chunks)

    # --- answering -------------------------------------------------------------------------

    def retrieve(self, question: str) -> list[Hit]:
        return self.index.search(question, self.config.top_k, self.config.retrieval)

    def ask(self, question: str) -> Answer:
        started = time.perf_counter()
        hits = self.retrieve(question)
        retrieval_ms = (time.perf_counter() - started) * 1000

        if not hits:
            answer = Answer(f"{IDK}. No documents are indexed yet.", [], False)
        else:
            llm_answer = self.answerer.answer(question, hits)
            text, sources = build_sources(hits, llm_answer)
            answered = not is_idk(text)
            answer = Answer(
                answer=text,
                sources=sources if answered else [],
                answered=answered,
                retrieved=[h.chunk.chunk_id for h in hits],
                input_tokens=llm_answer.usage.input_tokens,
                output_tokens=llm_answer.usage.output_tokens,
                cost_usd=llm_answer.usage.cost_usd,
                llm_ms=llm_answer.latency_s * 1000,
            )
        answer.retrieval_ms = round(retrieval_ms, 1)
        answer.llm_ms = round(answer.llm_ms, 1)
        answer.total_ms = round((time.perf_counter() - started) * 1000, 1)
        self._log_usage(question, answer)
        return answer

    def _log_usage(self, question: str, answer: Answer) -> None:
        record = {
            "time": datetime.now(UTC).isoformat(),
            "model": self.config.llm_model,
            "retrieval": self.config.retrieval,
            "question_chars": len(question),
            **{k: v for k, v in asdict(answer).items() if k not in ("answer", "sources", "retrieved")},
        }
        logger.info("answered", extra={"fields": record})
        if self.config.usage_log:
            path = Path(self.config.usage_log)
            path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_lock, open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
