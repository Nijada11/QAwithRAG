"""Test doubles: a hashing embedder instead of a downloaded model, and a scripted answerer
instead of the Claude API. Chroma is real (in a temporary directory)."""

import hashlib
import math

import pytest
from fastapi.testclient import TestClient

from src.config import RagConfig, Settings
from src.llm import Citation, LLMAnswer, Usage
from src.main import create_app
from src.rag import RAG
from src.store import Index, tokenize

API_KEY = "test-key"
AUTH = {"X-API-Key": API_KEY}


class HashEmbedder:
    """Bag-of-words vectors: texts sharing words are close. Enough to test the plumbing."""

    dims = 256

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dims
        for token in tokenize(text):
            vector[int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dims] += 1.0  # noqa: S324
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts):
        return [self._embed(t) for t in texts]

    def embed_query(self, text):
        return self._embed(text)


class WordOverlapReranker:
    def score(self, query, texts):
        q = set(tokenize(query))
        return [len(q & set(tokenize(t))) for t in texts]


class ScriptedAnswerer:
    """Cites the first hit, or says it doesn't know when told to."""

    model = "claude-haiku-5-5"

    def __init__(self):
        self.idk = False
        self.error: Exception | None = None
        self.calls: list[tuple[str, list]] = []

    def answer(self, question, hits):
        self.calls.append((question, hits))
        if self.error:
            raise self.error
        if self.idk:
            return LLMAnswer("I don't know. The sources cover other topics.", [], Usage(900, 20, 0.0001), 0.2)
        quote = hits[0].chunk.text.split("\n\n")[0]
        return LLMAnswer("Here is the answer.[1]", [Citation(0, quote)], Usage(1000, 50, 0.000125), 0.5)


DOCS = {
    "tap.md": (
        "---\ntitle: Temporary Access Pass\n---\n# Temporary Access Pass\n\n"
        "A Temporary Access Pass is a time-limited passcode.\n\n"
        "## Lifetime\n\nThe maximum lifetime of a pass is 30 days.\n\n"
        "[!INCLUDE [note](includes/note.md)]\n\n"
        ':::image type="content" source="media/x.png" alt-text="Screenshot.":::\n'
    ),
    "lockout.md": (
        "---\ntitle: Smart lockout\n---\n# Smart lockout\n\n"
        "Smart lockout locks an account after 10 failed sign-in attempts.\n"
    ),
}


@pytest.fixture
def rag_config(tmp_path) -> RagConfig:
    return RagConfig(index_dir=tmp_path / "index", usage_log=tmp_path / "usage.jsonl", retrieval="hybrid")


@pytest.fixture
def answerer() -> ScriptedAnswerer:
    return ScriptedAnswerer()


@pytest.fixture
def make_rag(rag_config, answerer):
    def build(**overrides) -> RAG:
        config = rag_config.with_(**overrides)
        index = Index(str(config.index_dir), config.collection, HashEmbedder(), WordOverlapReranker())
        return RAG(config, index=index, answerer=answerer)

    return build


@pytest.fixture
def rag(make_rag) -> RAG:
    pipeline = make_rag()
    for name, text in DOCS.items():
        pipeline.add_document(text.encode(), name, name.removesuffix(".md"), f"https://example.org/{name}")
    return pipeline


@pytest.fixture
def make_client(rag):
    """Build a client on a fresh app, so rate-limit counters never leak between tests."""

    def build(**overrides) -> TestClient:
        settings = {"api_key": API_KEY, "rate_limit": "1000/minute", **overrides}
        return TestClient(create_app(Settings(**settings), rag=rag), raise_server_exceptions=False)

    return build


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()
