"""FastAPI application: HTTP concerns only. Retrieval and answering live in rag.py."""

import logging
import re
import secrets
import threading
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Security, UploadFile
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIASGIMiddleware
from slowapi.util import get_remote_address

from src.config import Settings
from src.ingest import SUPPORTED_SUFFIXES, UnsupportedFileError
from src.llm import LLMError
from src.logging_config import configure_logging
from src.middleware import BodySizeLimitMiddleware, RequestLogMiddleware
from src.rag import RAG

logger = logging.getLogger("rag.api")

API_KEY_HEADER = "X-API-Key"
MULTIPART_OVERHEAD_BYTES = 64 * 1024


class AskRequest(BaseModel):
    question: str = Field(
        min_length=3, max_length=1000, examples=["How long is a Temporary Access Pass valid?"]
    )


class SourceOut(BaseModel):
    n: int = Field(description="The number used in the answer's [n] markers.")
    title: str
    url: str
    section: str
    page: int | None = Field(description="Page number for PDFs; null for web pages.")
    chunk_id: str
    quotes: list[str] = Field(description="The exact passages the answer relied on.")


class AskResponse(BaseModel):
    answer: str
    answered: bool = Field(description="False when the assistant said it doesn't know.")
    sources: list[SourceOut]


class DocumentResponse(BaseModel):
    doc_id: str
    title: str
    chunks: int


def _doc_id(filename: str | None) -> str:
    """Build a stable id from the upload's name; the client's filename is untrusted."""
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename or "").stem).strip("._")
    return f"uploads/{stem or 'document'}"


def create_app(settings: Settings | None = None, rag: RAG | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging()

    # Loading the embedding model takes a few seconds, so it happens on the first request
    # that needs it, not at import time; /health stays fast for the container probe.
    pipeline: dict[str, RAG] = {}
    pipeline_lock = threading.Lock()
    write_lock = threading.Lock()

    def get_rag() -> RAG:
        with pipeline_lock:
            if "rag" not in pipeline:
                pipeline["rag"] = rag or RAG(settings.rag)
            return pipeline["rag"]

    def is_valid_key(key: str | None) -> bool:
        return key is not None and secrets.compare_digest(key.encode(), settings.api_key.encode())

    def rate_limit_key(request: Request) -> str:
        # Authenticated callers get their own bucket; invalid keys share the address bucket,
        # which stops anyone escaping the limit by sending a new random key each time.
        key = request.headers.get(API_KEY_HEADER)
        return f"key:{key}" if is_valid_key(key) else get_remote_address(request)

    limiter = Limiter(key_func=rate_limit_key, default_limits=[settings.rate_limit])

    def require_api_key(
        key: Annotated[str | None, Security(APIKeyHeader(name=API_KEY_HEADER, auto_error=False))],
    ) -> None:
        if not is_valid_key(key):
            raise HTTPException(status_code=401, detail="Missing or invalid API key.")

    app = FastAPI(
        title="Document Q&A",
        version="0.1.0",
        description="Answers questions from Microsoft Entra ID documentation and cites the passages it used.",
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIASGIMiddleware)
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_body_bytes=settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES,
    )
    app.add_middleware(RequestLogMiddleware)

    @app.get("/health")
    @limiter.exempt
    def health() -> dict:
        return {"status": "ok"}

    @app.post(
        "/ask",
        dependencies=[Depends(require_api_key)],
        responses={
            401: {"description": "Missing or invalid API key."},
            429: {"description": "Rate limit exceeded."},
            502: {"description": "The language model could not answer."},
        },
    )
    def ask(body: AskRequest) -> AskResponse:
        """Answer a question from the indexed documents. Every claim is followed by a [n]
        marker pointing at an entry in `sources`, which holds the exact quoted passages.
        If the documents don't contain the answer, `answered` is false."""
        try:
            answer = get_rag().ask(body.question)
        except LLMError as e:
            logger.warning("llm_failed", extra={"fields": {"error": str(e)}})
            raise HTTPException(status_code=502, detail=str(e)) from None
        return AskResponse(
            answer=answer.answer,
            answered=answer.answered,
            sources=[SourceOut(**vars(s)) for s in answer.sources],
        )

    @app.post(
        "/documents",
        status_code=201,
        dependencies=[Depends(require_api_key)],
        responses={
            401: {"description": "Missing or invalid API key."},
            413: {"description": "File too large."},
            415: {"description": "Unsupported file type."},
            422: {"description": "No text could be extracted."},
            429: {"description": "Rate limit exceeded."},
        },
    )
    def add_document(
        file: Annotated[UploadFile, File(description=f"One of: {', '.join(sorted(SUPPORTED_SUFFIXES))}.")],
        url: Annotated[str, Form(description="Where the document is published; shown in citations.")] = "",
        title: Annotated[str, Form(description="Defaults to the title found in the file.")] = "",
    ) -> DocumentResponse:
        """Add a document to the index. Uploading a file with the same name again replaces
        the earlier version."""
        data = file.file.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail=f"File exceeds {settings.max_upload_bytes} bytes.")
        doc_id = _doc_id(file.filename)
        try:
            with write_lock:
                chunks = get_rag().add_document(data, file.filename or "", doc_id, url, title)
        except UnsupportedFileError as e:
            raise HTTPException(status_code=415, detail=str(e)) from None
        except Exception as e:  # pypdf raises many types for damaged files
            if type(e).__module__.startswith("pypdf"):
                raise HTTPException(status_code=422, detail="Could not read the PDF.") from None
            raise
        if not chunks:
            raise HTTPException(status_code=422, detail="No text could be extracted from the file.")
        logger.info("document_added", extra={"fields": {"doc_id": doc_id, "chunks": len(chunks)}})
        return DocumentResponse(doc_id=doc_id, title=chunks[0].title, chunks=len(chunks))

    return app
