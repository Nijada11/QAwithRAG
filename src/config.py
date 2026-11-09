"""Settings, read from environment variables.

RagConfig is everything the retrieval and answer steps need; the API, the Gradio app and the
eval all build one. Settings adds the HTTP concerns (auth, rate limit, upload size).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RETRIEVAL_MODES = ("vector", "keyword", "hybrid", "hybrid+rerank")


@dataclass(frozen=True)
class RagConfig:
    index_dir: Path = ROOT / "index"
    embed_model: str = "BAAI/bge-small-en-v1.5"
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    llm_model: str = "claude-haiku-5-5"
    llm_effort: str = "low"
    chunk_words: int = 250
    overlap_words: int = 50
    retrieval: str = "hybrid"
    top_k: int = 5
    # How many candidates the re-ranker re-scores before keeping top_k.
    rerank_candidates: int = 20
    usage_log: Path | None = ROOT / "logs" / "usage.jsonl"

    def __post_init__(self) -> None:
        if self.retrieval not in RETRIEVAL_MODES:
            raise ValueError(f"retrieval must be one of {RETRIEVAL_MODES}, not {self.retrieval!r}")

    @property
    def collection(self) -> str:
        # One collection per chunking setup, so experiments never overwrite each other.
        return f"docs_w{self.chunk_words}_o{self.overlap_words}"

    def with_(self, **changes) -> RagConfig:
        return replace(self, **changes)

    @classmethod
    def from_env(cls) -> RagConfig:
        env = os.environ.get
        defaults = cls()
        usage_log = env("USAGE_LOG", str(defaults.usage_log))
        return cls(
            index_dir=Path(env("INDEX_DIR", str(defaults.index_dir))),
            embed_model=env("EMBED_MODEL", defaults.embed_model),
            rerank_model=env("RERANK_MODEL", defaults.rerank_model),
            llm_model=env("LLM_MODEL", defaults.llm_model),
            llm_effort=env("LLM_EFFORT", defaults.llm_effort),
            chunk_words=int(env("CHUNK_WORDS", defaults.chunk_words)),
            overlap_words=int(env("OVERLAP_WORDS", defaults.overlap_words)),
            retrieval=env("RETRIEVAL", defaults.retrieval),
            top_k=int(env("TOP_K", defaults.top_k)),
            usage_log=Path(usage_log) if usage_log else None,
        )


@dataclass(frozen=True)
class Settings:
    api_key: str
    max_upload_bytes: int = 20 * 1024 * 1024
    rate_limit: str = "30/minute"
    rag: RagConfig = field(default_factory=RagConfig)

    @classmethod
    def from_env(cls) -> Settings:
        api_key = os.environ.get("API_KEY")
        if not api_key:
            # Fail closed: without this check a misconfigured deploy would run wide open.
            raise RuntimeError("API_KEY environment variable is required.")
        return cls(
            api_key=api_key,
            max_upload_bytes=int(os.environ.get("MAX_UPLOAD_BYTES", cls.max_upload_bytes)),
            rate_limit=os.environ.get("RATE_LIMIT", cls.rate_limit),
            rag=RagConfig.from_env(),
        )
