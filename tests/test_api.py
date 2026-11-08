import json

from src.llm import LLMError
from src.main import _doc_id
from tests.conftest import AUTH
from tests.test_ingest import make_pdf

# --- /health and docs ----------------------------------------------------------------------


def test_health_needs_no_key(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_docs_and_schema_are_public(client):
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "X-API-Key" in json.dumps(schema["components"]["securitySchemes"])


def test_health_is_not_rate_limited(make_client):
    client = make_client(rate_limit="1/minute")
    assert {client.get("/health").status_code for _ in range(5)} == {200}


# --- /ask ----------------------------------------------------------------------------------


def test_ask_requires_key(client):
    assert client.post("/ask", json={"question": "hello?"}).status_code == 401
    assert client.post("/ask", json={"question": "hello?"}, headers={"X-API-Key": "wrong"}).status_code == 401


def test_ask_returns_answer_and_sources(client):
    response = client.post("/ask", json={"question": "What is the maximum TAP lifetime?"}, headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["answered"] is True
    assert body["answer"].endswith("[1]")
    [source] = body["sources"]
    assert source["n"] == 1
    assert source["url"].startswith("https://example.org/")
    assert source["quotes"]


def test_ask_validates_question(client):
    assert client.post("/ask", json={"question": ""}, headers=AUTH).status_code == 422
    assert client.post("/ask", json={"question": "x" * 1001}, headers=AUTH).status_code == 422


def test_ask_maps_llm_failure_to_502(client, answerer):
    answerer.error = LLMError("Claude API returned 529: overloaded")
    response = client.post("/ask", json={"question": "anything at all"}, headers=AUTH)
    assert response.status_code == 502
    assert "529" in response.json()["detail"]


def test_ask_is_rate_limited(make_client):
    client = make_client(rate_limit="2/minute")
    codes = [client.post("/ask", json={"question": "lockout?"}, headers=AUTH).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


# --- /documents ----------------------------------------------------------------------------


def test_upload_markdown_then_ask_about_it(client, answerer):
    files = {"file": ("vpn guide.md", b"# VPN\n\nThe VPN gateway address is vpn.contoso.example.")}
    response = client.post("/documents", files=files, data={"url": "https://intranet/vpn"}, headers=AUTH)
    assert response.status_code == 201
    assert response.json() == {"doc_id": "uploads/vpn_guide", "title": "VPN", "chunks": 1}

    client.post("/ask", json={"question": "What is the VPN gateway address?"}, headers=AUTH)
    _, hits = answerer.calls[-1]
    assert hits[0].chunk.url == "https://intranet/vpn"


def test_upload_pdf(client):
    files = {"file": ("policy.pdf", make_pdf(["Passwords expire after 90 days"]), "application/pdf")}
    response = client.post("/documents", files=files, headers=AUTH)
    assert response.status_code == 201
    assert response.json()["chunks"] == 1


def test_upload_requires_key(client):
    assert client.post("/documents", files={"file": ("a.md", b"# A\n\ntext")}).status_code == 401


def test_upload_rejects_unsupported_type(client):
    response = client.post("/documents", files={"file": ("a.exe", b"MZ")}, headers=AUTH)
    assert response.status_code == 415


def test_upload_rejects_empty_and_broken_files(client):
    assert client.post("/documents", files={"file": ("e.md", b"   ")}, headers=AUTH).status_code == 422
    assert (
        client.post("/documents", files={"file": ("b.pdf", b"%PDF-1.4 garbage")}, headers=AUTH).status_code
        == 422
    )


def test_upload_size_limit(make_client):
    client = make_client(max_upload_bytes=100)
    response = client.post("/documents", files={"file": ("big.txt", b"word " * 100)}, headers=AUTH)
    assert response.status_code == 413


def test_doc_id_is_sanitized():
    assert _doc_id("../../etc/pass wd.md") == "uploads/pass_wd"
    assert _doc_id(None) == "uploads/document"
