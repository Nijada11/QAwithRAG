import json
from types import SimpleNamespace

import pytest

from src.config import RagConfig, Settings
from src.ingest import Chunk
from src.llm import Citation, LLMAnswer, is_idk, parse_response, search_result_blocks
from src.rag import build_sources
from src.store import Hit


def chunk(i: int, text: str = "First paragraph.\n\nSecond paragraph.") -> Chunk:
    return Chunk(f"doc{i}#0", f"doc{i}", f"Doc {i}", f"https://example.org/{i}", "Setup", None, text)


# --- store ---------------------------------------------------------------------------------


def test_search_modes_find_the_right_document(rag):
    for mode in ("vector", "keyword", "hybrid", "hybrid+rerank"):
        hits = rag.index.search("failed sign-in attempts lockout", 2, mode)
        assert hits[0].chunk.doc_id == "lockout", mode


def test_keyword_search_ignores_stopwords_only_queries(rag):
    assert rag.index.keyword_search("what is the", 5) == []


def test_unknown_mode_is_rejected(rag):
    with pytest.raises(ValueError):
        rag.index.search("x", 1, "magic")


def test_reupload_replaces_document(rag):
    before = rag.index.count()
    rag.add_document(b"# Smart lockout\n\nNew text only.", "lockout.md", "lockout")
    assert rag.index.count() == before
    texts = [c.text for c in rag.index.all_chunks() if c.doc_id == "lockout"]
    assert texts == ["New text only."]


def test_empty_index_says_it_does_not_know(make_rag, answerer):
    answer = make_rag().ask("anything?")
    assert not answer.answered and answer.sources == []
    assert answerer.calls == []


# --- llm -----------------------------------------------------------------------------------


def test_search_result_blocks_have_one_text_block_per_paragraph():
    [block] = search_result_blocks([Hit(chunk(1), 0.9)])
    assert block["type"] == "search_result"
    assert block["source"] == "https://example.org/1"
    assert block["title"] == "Doc 1 — Setup"
    assert block["citations"] == {"enabled": True}
    assert [c["text"] for c in block["content"]] == ["First paragraph.", "Second paragraph."]


def test_parse_response_marks_cited_blocks_and_prices_tokens():
    cite = SimpleNamespace(
        type="search_result_location", search_result_index=1, cited_text="Second paragraph. "
    )
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", text=""),
            SimpleNamespace(type="text", text="Intro: ", citations=None),
            SimpleNamespace(type="text", text="the fact", citations=[cite, cite]),
            SimpleNamespace(type="text", text=".", citations=None),
        ],
        usage=SimpleNamespace(input_tokens=1_000_000, output_tokens=1_000_000),
    )
    answer = parse_response(response, "claude-haiku-5-5", 1.5)
    assert answer.text == "Intro: the fact[2]."
    assert [c.quote for c in answer.citations] == ["Second paragraph.", "Second paragraph."]
    assert answer.usage.cost_usd == pytest.approx(0.60)


@pytest.mark.parametrize(
    "text,expected", [("I don't know.", True), ("I don’t know", True), ("Yes, I know.", False)]
)
def test_is_idk(text, expected):
    assert is_idk(text) is expected


# --- rag -----------------------------------------------------------------------------------


def test_build_sources_keeps_cited_hits_and_renumbers():
    hits = [Hit(chunk(i), 1.0) for i in range(4)]
    llm_answer = LLMAnswer(
        "A[3] B[1][3] C[9]",
        [Citation(2, "q2"), Citation(0, "q0"), Citation(2, "q2"), Citation(2, "q2b"), Citation(8, "bad")],
    )
    text, sources = build_sources(hits, llm_answer)
    assert text == "A[1] B[2][1] C"
    assert [(s.n, s.chunk_id, s.quotes) for s in sources] == [
        (1, "doc2#0", ["q2", "q2b"]),
        (2, "doc0#0", ["q0"]),
    ]


def test_ask_returns_sources_and_logs_usage(rag, rag_config):
    answer = rag.ask("How long is a temporary access pass valid?")
    assert answer.answered
    assert answer.sources[0].url == "https://example.org/tap.md"
    assert answer.answer == "Here is the answer.[1]"
    record = json.loads(rag_config.usage_log.read_text().splitlines()[-1])
    assert record["input_tokens"] == 1000 and record["cost_usd"] > 0
    assert record["total_ms"] >= record["retrieval_ms"]
    assert "question" not in record  # questions can contain personal data; only the length is logged


def test_idk_answer_has_no_sources(rag, answerer):
    answerer.idk = True
    answer = rag.ask("How do I reset a Google password?")
    assert not answer.answered and answer.sources == []


# --- config --------------------------------------------------------------------------------


def test_settings_fail_closed_without_api_key(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        Settings.from_env()


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("API_KEY", "k")
    monkeypatch.setenv("RETRIEVAL", "hybrid")
    monkeypatch.setenv("CHUNK_WORDS", "250")
    monkeypatch.setenv("USAGE_LOG", "")
    settings = Settings.from_env()
    assert settings.rag.retrieval == "hybrid" and settings.rag.collection == "docs_w250_o50"
    assert settings.rag.usage_log is None


def test_invalid_retrieval_mode_is_rejected():
    with pytest.raises(ValueError):
        RagConfig(retrieval="nope")
