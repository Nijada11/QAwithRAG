"""Vector store and retrieval.

- Vector search: chunks embedded with a sentence-transformers model, stored in Chroma.
- Keyword search: BM25 over the same chunks, built in memory from what Chroma holds.
- Hybrid: both lists merged with reciprocal rank fusion (RRF), which needs no score
  calibration between the two retrievers.
- Re-ranking: a cross-encoder re-scores the top candidates against the question.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Protocol

import chromadb
from rank_bm25 import BM25Okapi

from src.ingest import Chunk, embedding_text

RRF_K = 60  # The constant from the original RRF paper; damps the weight of rank 1 vs rank 2.
_TOKEN = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")
_STOPWORDS = frozenset(
    "a an and are as at be by can do does for from how i if in is it my of on or "
    "the to what when where which who why with you your".split()
)


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class Reranker(Protocol):
    def score(self, query: str, texts: list[str]) -> list[float]: ...


class SentenceTransformerEmbedder:
    # BGE models are trained with this instruction in front of queries (not passages).
    BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name, device="cpu")
        self.query_prefix = self.BGE_QUERY_PREFIX if "bge" in model_name.lower() else ""

    @property
    def max_tokens(self) -> int:
        return self.model.max_seq_length

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            texts, batch_size=32, normalize_embeddings=True, show_progress_bar=len(texts) > 200
        )
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode(self.query_prefix + text, normalize_embeddings=True).tolist()


class CrossEncoderReranker:
    def __init__(self, model_name: str):
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_name, device="cpu")

    def score(self, query: str, texts: list[str]) -> list[float]:
        return self.model.predict([(query, text) for text in texts]).tolist()


class LuceneBM25(BM25Okapi):
    """BM25 with Lucene's IDF, log(1 + (N - n + 0.5) / (n + 0.5)), which is never negative.

    rank_bm25's Okapi IDF goes to zero or below for a term in half or more of the chunks, so
    on a small index (a few uploaded files) keyword search would return nothing at all.
    """

    def _calc_idf(self, nd):
        for word, freq in nd.items():
            self.idf[word] = math.log(1 + (self.corpus_size - freq + 0.5) / (freq + 0.5))


@dataclass
class Hit:
    chunk: Chunk
    score: float


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


def _chunk_from(chunk_id: str, text: str, meta: dict) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id=meta["doc_id"],
        title=meta["title"],
        url=meta["url"],
        section=meta["section"],
        page=meta["page"] or None,
        text=text,
    )


class Index:
    def __init__(
        self,
        path: str,
        collection: str,
        embedder: Embedder,
        reranker: Reranker | None = None,
        rerank_candidates: int = 20,
    ):
        self.client = chromadb.PersistentClient(path=str(path))
        self.collection = self.client.get_or_create_collection(collection, metadata={"hnsw:space": "cosine"})
        self.embedder = embedder
        self.reranker = reranker
        self.rerank_candidates = rerank_candidates
        self._bm25: LuceneBM25 | None = None
        self._bm25_chunks: list[Chunk] = []

    # --- writing ---------------------------------------------------------------------------

    def add(self, chunks: list[Chunk], batch_size: int = 256) -> None:
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            self.collection.upsert(
                ids=[c.chunk_id for c in batch],
                documents=[c.text for c in batch],
                metadatas=[c.metadata for c in batch],
                embeddings=self.embedder.embed_documents([embedding_text(c) for c in batch]),
            )
        self._bm25 = None

    def delete_document(self, doc_id: str) -> None:
        self.collection.delete(where={"doc_id": doc_id})
        self._bm25 = None

    # --- reading ---------------------------------------------------------------------------

    def count(self) -> int:
        return self.collection.count()

    def all_chunks(self) -> list[Chunk]:
        got = self.collection.get(include=["documents", "metadatas"])
        return [
            _chunk_from(i, t, m)
            for i, t, m in zip(got["ids"], got["documents"], got["metadatas"], strict=True)
        ]

    def document_ids(self) -> set[str]:
        got = self.collection.get(include=["metadatas"])
        return {m["doc_id"] for m in got["metadatas"]}

    def vector_search(self, query: str, k: int) -> list[Hit]:
        if self.count() == 0:
            return []
        result = self.collection.query(
            query_embeddings=[self.embedder.embed_query(query)],
            n_results=min(k, self.count()),
            include=["documents", "metadatas", "distances"],
        )
        return [
            Hit(_chunk_from(i, t, m), 1.0 - d)
            for i, t, m, d in zip(
                result["ids"][0],
                result["documents"][0],
                result["metadatas"][0],
                result["distances"][0],
                strict=True,
            )
        ]

    def keyword_search(self, query: str, k: int) -> list[Hit]:
        if self._bm25 is None:
            self._bm25_chunks = self.all_chunks()
            if not self._bm25_chunks:
                return []
            corpus = [tokenize(embedding_text(c)) for c in self._bm25_chunks]
            self._bm25 = LuceneBM25(corpus)
        scores = self._bm25.get_scores(tokenize(query))
        best = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [Hit(self._bm25_chunks[i], float(scores[i])) for i in best if scores[i] > 0]

    def hybrid_search(self, query: str, k: int, candidates: int = 50) -> list[Hit]:
        ranked_lists = [
            self.vector_search(query, candidates),
            self.keyword_search(query, candidates),
        ]
        fused: dict[str, float] = {}
        chunks: dict[str, Chunk] = {}
        for hits in ranked_lists:
            for rank, hit in enumerate(hits):
                cid = hit.chunk.chunk_id
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
                chunks[cid] = hit.chunk
        best = sorted(fused, key=fused.get, reverse=True)[:k]
        return [Hit(chunks[cid], fused[cid]) for cid in best]

    def rerank(self, query: str, hits: list[Hit], k: int) -> list[Hit]:
        if self.reranker is None:
            raise RuntimeError("re-ranking requested but no re-ranker is configured")
        if not hits:
            return []
        scores = self.reranker.score(query, [embedding_text(h.chunk) for h in hits])
        rescored = [Hit(h.chunk, s) for h, s in zip(hits, scores, strict=True)]
        return sorted(rescored, key=lambda h: h.score, reverse=True)[:k]

    def search(self, query: str, k: int, mode: str = "vector") -> list[Hit]:
        if mode == "vector":
            return self.vector_search(query, k)
        if mode == "keyword":
            return self.keyword_search(query, k)
        if mode == "hybrid":
            return self.hybrid_search(query, k)
        if mode == "hybrid+rerank":
            candidates = self.hybrid_search(query, self.rerank_candidates)
            return self.rerank(query, candidates, k)
        raise ValueError(f"unknown retrieval mode {mode!r}")
